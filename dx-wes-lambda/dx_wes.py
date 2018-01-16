#!/usr/bin/env python2
"""Lambda to convert WES to DNAnexus."""
import json
import os
import subprocess

import dxpy
import requests

def dnanexus_workflows_post(event, context):
    """Handle a WES workflows POST request and turn it into a DNAnexus
    /{workflow-id}/run request.

    Uses the DNAnexus python library, dxpy.
    """

    # Set the DNAnexus API token. DNAnexus expects a bearer token with all API
    # requests, so we copy that behavior here. API Gateway is resonsible for
    # taking the token out of the Authorization header and making it available
    # to this lambda.
    # Also, note that this is an absurd thing to do security-wise, and you
    # should never submit a request to any of these endpoints unless you fully
    # control the whole deployment.
    authorization_header = event["headers"]["Authorization"]
    dx_token = authorization_header.replace("Bearer ", "")
    auth_header = {
        "auth_token_type": "Bearer",
        "auth_token": dx_token
    }
    dxpy.set_security_context(auth_header)

    # Set the project context from a key value passed along with the workflow
    # request. The WES spec doesn't have any specific place to specify
    # something like a project id, but here we expect it to be in the
    # optional "key_values" object.
    dx_project_id = event["body"]["key_values"]["dx-project"]
    dxpy.set_project_context(dx_project_id)

    # Pull the WDL out of the request body. We're going to "compile" it with
    # dxWDL.
    wdl_string = event["body"]["workflow_descriptor"]

    # Now transfer input files to DNAnexus. We will need this so dxWDL can
    # create an inputs dict for us. Currently this assumes that all files are
    # available via https, but this could be expanded to handle other
    # protocols.
    inputs_dict = json.loads(event["body"]["workflow_params"])
    dx_localized_input_dict = {}
    for key, value in inputs_dict.items():
        # It would be really nice to actually specify these types somewhere
        # instead of having to sniff them. Unfortunately, WDL's String->File
        # conversion doesn't let us do that.
        if value.startswith("https://"):
            dx_file = dxpy.new_dxfile(
                name=os.path.basename(value),
                mode="w",
                project=dx_project_id)
            response = requests.get(value, stream=True)
            for chunk in response.iter_content(chunk_size=1<<24):
                dx_file.write(chunk)
            dx_file.close()
            # The dx:// prefix is required by dxWDL
            dx_localized_input_dict[key] = 'dx://' + dx_file.id
        else:
            # If it doesn't look like a file, just pass through the value.
            dx_localized_input_dict[key] = value
    
    # AWS Lambda only lets us write to /tmp, so everything goes there.
    with open("/tmp/dx_inputs.json", "w") as inputs_json:
        json.dump(dx_localized_input_dict, inputs_json)

    with open("/tmp/workflow.wdl", "w") as wdl_file:
        wdl_file.write(wdl_string)
    
    # These are both included in the lambda's deployment package.
    dxwdl_jar_path = os.path.abspath("dxWDL-0.57.jar")
    dx_exe_path = os.path.abspath("bin/dx")

    dxwdl_cmd = ["java", "-jar", dxwdl_jar_path, "compile", "/tmp/workflow.wdl",
                 "-inputs", "/tmp/dx_inputs.json"]

    # dxWDL writes an inputs file to the cwd, so we need to change to /tmp so
    # that doesn't fail. But that means we have to be very careful with the
    # PATH and PYTHONPATH so we can continue using the dx-toolkit dependencies.
    proc = subprocess.Popen(
        dxwdl_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/tmp",
        env={"DX_SECURITY_CONTEXT": json.dumps(auth_header),
             "DX_PROJECT_CONTEXT_ID": dx_project_id,
             "PYTHONPATH": ':'.join([os.environ.get("PYTHONPATH", ""), os.path.dirname(os.path.dirname(dx_exe_path))]),
             "PATH": ':'.join([os.environ["PATH"], os.path.dirname(dx_exe_path)])}
    )
    stdout, stderr = proc.communicate()
    workflow_id = stdout.strip()

    # This file should have been created by dxWDL.
    dx_inputs = json.load(open("/tmp/dx_inputs.dx.json"))

    # Finally, actually run the newly created DNAnexus workflow and return its
    # analysis ID. "Workflow" in WES means "analysis" on DNAnexus.
    dx_workflow = dxpy.DXWorkflow(workflow_id)
    dx_analysis = dx_workflow.run(dx_inputs, project=dx_project_id)

    return {"workflow_id": dx_analysis.id}
