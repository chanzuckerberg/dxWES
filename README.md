# dxWES

## Summary

This is a python function you can run on AWS as a lambda. It converts [WES](https://github.com/ga4gh/workflow-execution-schemas) requests into DNAnexus requests. This also contains a Cloudformation template that will set up the lambda function, its permissions, and an API Gateway REST API that looks like WES. You can deploy the API and make requests to it.

Currently only one WES method is implemented, a POST to /workflows. But I think that's the hard one.

## Deploying on AWS

### Prepare the lambda deployment package

The `dx-wes-lambda` directory needs some additional resources before it can be
zipped up and uploaded to S3:

1. The dxWDL jar, available [here](https://github.com/dnanexus/dxWDL/releases)
2. dx-toolkit python dependencies.
    a. Download the dx-toolkit tarball for Ubuntu 14.04 from
[DNAnexus](https://wiki.dnanexus.com/downloads)
    b. Extract the tarball
    c. Copy everything in `dx-toolkit/share/dnanexus/lib/python2.7/site-packages/` into
`dx-wes-lambda`
3. dx-toolkit executables
    a. Make a `dx-wes-lambda/bin` directory.
    b. Copy all the files from dx-toolkit/bin/ into `dx-wes-lambda/bin`

Now zip the directory and upload it to S3:
```
cd dx-wes-lambda && zip -X -r ../dx_wes.zip * && cd ..
aws s3 cp dx_wes.zip s3://my-bucket-name/dx_wes.zip
```

### Create the Cloudformation Stack

You can create the stack via the CLI using the JSON template:
```
aws cloudformation create-stack --stack-name "dx-wes" \
    --template-body file://dx_wes.json \
    --parameters ParameterKey=LambdaCodeBucket,ParameterValue=my-bucket-name \
                 ParameterKey=LambdaCodeKey,ParameterValue=dx_wes.zip \
    --capabilities CAPABILITY_NAMED_IAM
```

### Deploy the API
Follow the "Deploy an API to a Stage" instructions [here](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-deploy-api-with-console.html).

## Test the API

Create a JSON with the workflow request that looks like this:

```
{
    "workflow_descriptor": "task CountLines {\n  File input_file\n  \n  command <<<\n    wc -l ${input_file} > line.count\n  >>>\n  \n  output {\n    String line_count = read_string(\"line.count\")\n  }\n}\n\nworkflow CountLinesWorkflow {\n  File input_file\n  \n  call CountLines {\n    input: input_file=input_file\n  }\n\n  output {\n    String line_count=CountLines.line_count\n  }\n}  \n",
    "workflow_params": "{\"CountLinesWorkflow.input_file\": \"https://path/to/file\"}",
    "key_values": {"dx-project": "project-myprojectid"}
}
```

And you can make the request using httpie:
```
http POST https://path_to_stage/workflows Authorization:'Bearer mydnanexustoken' @simple_test.json
```
