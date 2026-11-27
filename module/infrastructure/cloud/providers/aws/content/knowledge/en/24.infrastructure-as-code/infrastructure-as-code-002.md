# CloudFormation Templates, Parameters, Outputs, and Intrinsic Functions

> **Chapter:** Infrastructure as Code  
> **Module:** CLOUD_PROVIDERS_AWS — exploring the AWS ecosystem across Region/AZ infrastructure, IAM, VPC, compute services, storage, databases, integration, and serverless. Learners build the ability to choose services and design and deploy applications that are secure, monitored, recoverable, and cost-controlled.

## Learning Objectives

After this lesson, learners will be able to:

1. Explain the role of AWS CloudFormation in Infrastructure as Code (IaC) and the stack lifecycle.
2. Read and structure a CloudFormation template according to standard sections.
3. Declare Parameters with clear data types, default values, constraints, and descriptions.
4. Use Outputs to publish resource identifiers and share data across stacks.
5. Choose the right intrinsic functions such as Ref, GetAtt, Sub, Join, FindInMap, Select, If, ImportValue, and condition functions.
6. Combine pseudo parameters to write templates reusable across accounts, Regions, and environments.
7. Distinguish implicit dependencies from DependsOn, and apply DeletionPolicy/UpdateReplacePolicy appropriately.
8. Safely use dynamic references to Systems Manager Parameter Store and Secrets Manager.
9. Validate, review change sets, deploy, detect drift, and handle rollbacks.
10. Design templates following least privilege, data protection, and cost control principles.

## 1. What Problem Does CloudFormation Solve?

**AWS CloudFormation** lets you describe AWS infrastructure using YAML or JSON templates. CloudFormation reads the template, creates a stack, and orchestrates creating, updating, or deleting resources according to a dependency graph.

For example, an application needs:

- A VPC, subnets, and security groups.
- An S3 bucket to store artifacts.
- An IAM role for the workload.
- An SQS queue for asynchronous processing.
- A CloudWatch log group and alarms.

If each resource is created via the console, configurations can drift across development, staging, and production. When templates are stored in source control, the team can review changes, recreate environments, and deploy using a code-like workflow.

~~~mermaid
flowchart LR
    T["YAML / JSON template"] --> V["Validate + lint"]
    V --> C["Change set"]
    C --> R["Review changes"]
    R --> E["Execute"]
    E --> S["CloudFormation stack"]
    S --> A["AWS resources"]
    A --> D["Drift detection"]
    D --> T
~~~

### 1.1. Core Concepts

| Concept | Meaning |
| --- | --- |
| **Template** | A YAML/JSON infrastructure specification. |
| **Stack** | A collection of resources managed by CloudFormation from a template and parameter values. |
| **Resource** | An AWS resource declared in the Resources section. |
| **Logical ID** | The identifier of a resource inside the template, e.g., AppQueue. |
| **Physical ID** | The actual name/ID created by the AWS service, e.g., queue URL or bucket name. |
| **Parameter** | An input passed when creating or updating a stack. |
| **Output** | A value published by the stack after deployment. |
| **Intrinsic function** | A built-in function to reference parameters, resources, attributes, or compute values at deploy time. |
| **Change set** | A preview of the changes CloudFormation plans to perform. |
| **Drift** | The difference between a resource's actual configuration and the configuration desired by CloudFormation. |

### 1.2. Declarative and Reconciliation

A template describes the **desired state**. The author specifies what resource types are needed and what properties they should have; CloudFormation decides the ordering and API calls to execute.

When updating a stack, CloudFormation compares the new template with the current stack and creates, updates, replaces, or deletes resources. Some property changes require replacement; others update in place. Always check the resource reference and change set before executing.

CloudFormation is not a runtime controller that continuously reverts every drift immediately. If someone edits a resource directly in the console, drift can persist until drift detection is run or a stack operation is executed.

## 2. CloudFormation Template Structure

A template can contain the following sections:

| Section | Required? | Purpose |
| --- | --- | --- |
| AWSTemplateFormatVersion | No | Template format version; currently `2010-09-09` is commonly used. |
| Description | No | Description of the template. |
| Transform | No | Applies macros/extensions such as AWS::LanguageExtensions or AWS::Serverless. |
| Metadata | No | Metadata for the template or tools. |
| Parameters | No | Inputs at stack creation/update time. |
| Rules | No | Validates conditions across parameter values. |
| Mappings | No | Static key/value lookup tables. |
| Conditions | No | Conditions determining whether a resource/property is created/selected. |
| Resources | **Yes** | Declares the resources to manage. |
| Outputs | No | Publishes values from the stack. |

Section order in a template can follow documentation structure for readability; Resources is the required section.

### 2.1. Minimal Deployable Template

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Minimal S3 bucket example

Resources:
  ArtifactsBucket:
    Type: AWS::S3::Bucket
~~~

The Logical ID is ArtifactsBucket; the Type is AWS::S3::Bucket. Because Properties are not declared, CloudFormation creates the bucket with the resource provider's defaults. Production templates should declare encryption, public access block, versioning, lifecycle, logging, and retention as required.

### 2.2. Logical ID and Physical Resource

A Logical ID must be unique within the Resources section of a template. Intrinsic functions referencing a resource typically use the logical ID, not the physical ID.

Example:

~~~yaml
Resources:
  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-processing

Outputs:
  QueueUrl:
    Value: !Ref OrdersQueue
~~~

For AWS::SQS::Queue, Ref returns the queue URL. For each resource type, Ref can return a different type of value. Read the resource reference page to know the exact return value.

A physical name can be auto-generated by CloudFormation if not explicitly set. Auto-generated names avoid collisions when creating multiple stacks. When hardcoding physical names, you must manage uniqueness across accounts/Regions/environments and may run into issues during replacement.

## 3. Parameters: Controlled Inputs for a Stack

Parameters enable reusing the same template across multiple environments. Instead of editing the YAML file to change an instance type, environment, or CIDR, the deployer passes parameter values when creating/updating the stack.

### 3.1. Parameter Structure

A parameter typically includes:

- Type: data type or AWS-specific parameter type.
- Description: explains the purpose.
- Default: default value if any.
- AllowedValues: list of permitted values.
- AllowedPattern: regex validating the string.
- MinLength/MaxLength: length limits.
- MinValue/MaxValue: numeric limits.
- ConstraintDescription: message shown when input is invalid.
- NoEcho: masks the value in certain stack displays/UIs.

Example:

~~~yaml
Parameters:
  Environment:
    Type: String
    Description: Deployment environment
    Default: dev
    AllowedValues:
      - dev
      - test
      - prod

  VpcCidr:
    Type: String
    Description: IPv4 CIDR block for the VPC
    Default: 10.40.0.0/16
    AllowedPattern: '^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$'
    ConstraintDescription: Enter an IPv4 CIDR block such as 10.40.0.0/16.

  QueueRetentionSeconds:
    Type: Number
    Default: 345600
    MinValue: 60
    MaxValue: 1209600
    Description: SQS message retention in seconds
~~~

The regex in the example only checks the string format; it does not verify that every octet and prefix forms a valid CIDR. Use appropriate parameter types/validation and validation tools for additional checks.

### 3.2. Commonly Used Parameter Types

| Type | When to use |
| --- | --- |
| String | Environment name, queue name, CIDR as string. |
| Number | Port, retention seconds, replica count. |
| List<Number> | List of numbers. |
| CommaDelimitedList | Comma-separated list of strings. |
| AWS::EC2::KeyPair::KeyName | Select an existing EC2 key pair in the account/Region. |
| AWS::EC2::VPC::Id | Select an existing VPC. |
| AWS::EC2::Subnet::Id | Select an existing subnet. |
| AWS::SSM::Parameter::Value<String> | Fetch a value from Systems Manager Parameter Store by key. |
| AWS::SSM::Parameter::Value<List<String>> | Fetch a list of values from Parameter Store. |

AWS-specific parameter types can help the console display matching resources in the account/Region. They do not automatically grant permissions to the stack and do not replace IAM.

### 3.3. NoEcho Is Not a Secret Vault

NoEcho masks a parameter value in certain CloudFormation displays, but **is not a complete secrets management mechanism**. Do not pass long-lived passwords/API keys as regular parameters assuming NoEcho protects them everywhere. Values can still appear in resource properties, logs, metadata, or elsewhere depending on the resource/template.

Use Secrets Manager or Systems Manager SecureString dynamic references when a resource property requires a secret. Never put secrets in Outputs, Metadata, Description, or template source control.

### 3.4. Parameter Files and CLI

Example JSON parameters file:

~~~json
[
  {
    "ParameterKey": "Environment",
    "ParameterValue": "staging"
  },
  {
    "ParameterKey": "VpcCidr",
    "ParameterValue": "10.40.0.0/16"
  },
  {
    "ParameterKey": "QueueRetentionSeconds",
    "ParameterValue": "86400"
  }
]
~~~

Create a stack with a parameter file:

~~~bash
aws cloudformation create-stack \
  --stack-name orders-infrastructure \
  --template-body file://template.yaml \
  --parameters file://parameters.json \
  --region ap-southeast-1
~~~

For templates larger than the inline limit, upload the template to S3 and use a template URL. Never include secret values in committed parameter files.

### 3.5. Parameter Validation with Rules

The Rules section can validate relationships across multiple parameters. For example, if environment `prod` is selected, parameter `MultiAZ` must be `true`:

~~~yaml
Parameters:
  Environment:
    Type: String
    AllowedValues: [dev, test, prod]
  MultiAZ:
    Type: String
    AllowedValues: ['true', 'false']

Rules:
  ProductionRequiresMultiAZ:
    RuleCondition: !Equals [!Ref Environment, prod]
    Assertions:
      - Assert: !Equals [!Ref MultiAZ, 'true']
        AssertDescription: Production requires MultiAZ to be enabled.
~~~

Rules validate parameter inputs during stack creation/update. They do not replace Conditions: Rules reject invalid inputs, whereas Conditions control resources/properties inside the template.

## 4. Mappings: Static Configuration Lookup Tables

Mappings are fixed lookup tables inside a template. Use Fn::FindInMap when choosing a value by Region, environment, or another static dimension.

Example selecting an AMI by Region:

~~~yaml
Mappings:
  RegionAmi:
    ap-southeast-1:
      HVM64: ami-0123456789abcdef0
    ap-northeast-1:
      HVM64: ami-0abcdef1234567890

Parameters:
  InstanceRegion:
    Type: String
    Default: ap-southeast-1
    AllowedValues:
      - ap-southeast-1
      - ap-northeast-1

Resources:
  AppInstance:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: !FindInMap
        - RegionAmi
        - !Ref InstanceRegion
        - HVM64
      InstanceType: t3.micro
~~~

The AMI IDs in the example are illustrative placeholders and are not guaranteed to exist. Production should retrieve AMIs from SSM public parameters or a controlled pipeline updating mappings, because AMI IDs change by Region, architecture, and release.

Mappings are static data inside the template. If values need to be managed dynamically or shared across teams, consider Parameter Store, AppConfig, or a more suitable configuration source.

## 5. Conditions: Creating Resources Conditionally

Conditions are evaluated when CloudFormation creates or updates a stack. They are typically based on Parameters, pseudo parameters, or Mappings; you cannot directly reference resource logical IDs or resource attributes in conditions.

### 5.1. Declaring Conditions

~~~yaml
Parameters:
  Environment:
    Type: String
    AllowedValues: [dev, staging, prod]
    Default: dev

Conditions:
  IsProduction: !Equals [!Ref Environment, prod]
  IsNotDevelopment: !Not
    - !Equals [!Ref Environment, dev]
~~~

### 5.2. Attaching a Condition to a Resource

~~~yaml
Resources:
  ProductionAlarm:
    Type: AWS::CloudWatch::Alarm
    Condition: IsProduction
    Properties:
      AlarmDescription: Alarm enabled only for production
      Namespace: AWS/SQS
      MetricName: ApproximateNumberOfMessagesVisible
      Statistic: Average
      Period: 60
      EvaluationPeriods: 3
      Threshold: 100
      ComparisonOperator: GreaterThanThreshold
      Dimensions:
        - Name: QueueName
          Value: !GetAtt OrdersQueue.QueueName
~~~

When IsProduction is false, this resource is not created. If a parameter update causes the condition to switch from true to false, CloudFormation deletes the resource attached to that condition. Therefore, do not use Conditions to hide critical stateful resources without understanding the deletion consequences.

### 5.3. Fn::If and AWS::NoValue

Fn::If chooses one of two values at deploy time. AWS::NoValue omits the corresponding property from the resource configuration.

~~~yaml
Parameters:
  EnableDeadLetterQueue:
    Type: String
    AllowedValues: ['true', 'false']
    Default: 'true'

Conditions:
  CreateDlq: !Equals [!Ref EnableDeadLetterQueue, 'true']

Resources:
  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      RedrivePolicy: !If
        - CreateDlq
        - deadLetterTargetArn: !GetAtt OrdersDlq.Arn
          maxReceiveCount: 5
        - !Ref AWS::NoValue

  OrdersDlq:
    Type: AWS::SQS::Queue
    Condition: CreateDlq
~~~

In real templates, ensure the resource property schema matches the selected value and the dependent resource's condition. Fn::If can be used within property values or lists/objects to customize configurations.

### 5.4. Condition Functions

| Function | Meaning | Example |
| --- | --- | --- |
| Fn::Equals | Compares two values. | !Equals [!Ref Environment, prod] |
| Fn::And | All conditions are true. | !And [!Condition IsProd, !Condition HasBackup] |
| Fn::Or | At least one condition is true. | !Or [!Condition IsProd, !Condition IsStaging] |
| Fn::Not | Negates a condition value. | !Not [!Condition IsDevelopment] |
| Fn::If | Selects a value based on a condition. | !If [IsProd, 30, 7] |

Fn::And and Fn::Or have operand count limits per the CloudFormation reference. When conditions get complex, name smaller, readable conditions instead of deeply nesting hard-to-review expressions.

## 6. Outputs: Publishing Values After Stack Creation

Outputs let operators, pipelines, or other stacks retrieve information from a deployed stack. Typical values include resource ARNs, queue URLs, bucket names, endpoints, or subnet IDs.

### 6.1. Basic Outputs

~~~yaml
Outputs:
  OrdersQueueUrl:
    Description: URL of the orders processing queue
    Value: !Ref OrdersQueue
  OrdersQueueArn:
    Description: ARN of the orders processing queue
    Value: !GetAtt OrdersQueue.Arn
  DeploymentRegion:
    Description: AWS Region where this stack is deployed
    Value: !Ref AWS::Region
~~~

An Output does not create a resource. It publishes a value that CloudFormation can return in stack details, APIs, or the CLI.

### 6.2. Exporting Outputs for Other Stacks to Import

A network stack can export a VPC ID:

~~~yaml
Outputs:
  VpcId:
    Description: VPC ID shared with application stacks
    Value: !Ref ApplicationVpc
    Export:
      Name: !Sub '${AWS::StackName}-VpcId'
~~~

An application stack imports the value:

~~~yaml
Parameters:
  NetworkStackName:
    Type: String
Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Security group for application
      VpcId:
        Fn::ImportValue:
          Fn::Sub: '${NetworkStackName}-VpcId'
~~~

Export + Fn::ImportValue have important limitations:

- Exports and imports only work within the **same AWS account and same Region**.
- The Export name must be unique within the account/Region.
- While another stack imports an output, the exporting stack cannot be deleted and the exported value cannot be changed.
- To modify or remove an export, all imports must be removed first.
- An Output Export Name cannot depend on Ref/GetAtt of a resource.

This is a strong referential constraint useful for network foundations, but it also creates coupling between stacks. Plan the stack update/deletion order before changing exports.

### 6.3. Fn::GetStackOutput for Cross-Account/Region

CloudFormation provides Fn::GetStackOutput to reference another stack's output without an explicit Export. This function supports cross-account and cross-Region references with appropriate configuration/permissions, but it is a **weak reference**: CloudFormation does not lock the source stack against deletion like Export + ImportValue does.

Use it only when cross-account/Region output sharing is needed and access permissions, deployment order, and failure handling are designed. For stacks in the same account/Region needing referential integrity protection, Export + ImportValue is usually clearer.

### 6.4. Do Not Export Secrets via Outputs

Never put database passwords, API tokens, or secret values into Outputs. Output values can be read by principals with permission to view stack outputs, stored in pipeline logs, or shared with other stacks. Export the secret ARN/name or a safe reference if consumers need to read the secret themselves using an IAM role.

## 7. Intrinsic Functions: Referencing and Computing Values

Intrinsic functions are built-in functions that CloudFormation evaluates during template processing/deployment. They allow using input values, resource attributes, mappings, conditions, and pseudo parameters.

Functions can appear in locations supported by CloudFormation such as resource properties, outputs, metadata, and conditions. Not every property accepts every intrinsic function; check the resource schema.

### 7.1. Ref and Fn::GetAtt

Ref has two common forms: for a Parameter, it returns the parameter value; for a Resource, it returns a value defined by the resource type, typically the physical ID though not always the ARN.

GetAtt retrieves a resource attribute. Attribute names depend on the resource type.

~~~yaml
Resources:
  OrdersQueue:
    Type: AWS::SQS::Queue
  LogsBucket:
    Type: AWS::S3::Bucket

Outputs:
  QueueUrl:
    Value: !Ref OrdersQueue
  QueueArn:
    Value: !GetAtt OrdersQueue.Arn
  BucketName:
    Value: !Ref LogsBucket
  BucketArn:
    Value: !GetAtt LogsBucket.Arn
~~~

Do not assume Ref always returns an ARN for every resource. For example, Ref on an SQS Queue returns the queue URL, while the ARN is obtained via GetAtt. Always check the Return values table for the resource type.

### 7.2. Fn::Sub

Sub substitutes placeholders in a string with parameters, pseudo parameters, logical IDs, or resource attributes. It is usually the cleanest way to construct ARNs/URLs.

~~~yaml
Outputs:
  QueueArnText:
    Value: !Sub 'arn:${AWS::Partition}:sqs:${AWS::Region}:${AWS::AccountId}:${OrdersQueue.Arn}'
  QueueUrl:
    Value: !Sub 'https://sqs.${AWS::Region}.${AWS::URLSuffix}/${AWS::AccountId}/${OrdersQueue.QueueName}'
~~~

In Fn::Sub:

- Placeholders like `${Parameter}` are replaced with the parameter value.
- Placeholders like `${LogicalResourceId}` are equivalent to Ref on the resource.
- Placeholders like `${LogicalResourceId.Attribute}` are equivalent to GetAtt.
- Placeholders like `${AWS::Region}` reference a pseudo parameter.
- A variable map can be passed to name variables or use values computed via intrinsic functions.

~~~yaml
Outputs:
  LogGroupArn:
    Value: !Sub
      - 'arn:${Partition}:logs:${Region}:${Account}:log-group:${Name}'
      - Partition: !Ref AWS::Partition
        Region: !Ref AWS::Region
        Account: !Ref AWS::AccountId
        Name: !Ref ApplicationLogGroup
~~~

If you need a literal `${...}` placeholder without Sub substituting it, use the Fn::Sub escaping syntax per AWS documentation. In user data, launch templates, or scripts, also check how the downstream shell/interpreter processes `$` signs.

### 7.3. Fn::Join, Fn::Select, and Fn::Split

Join concatenates a list of values into a string with a delimiter. Split turns a delimited string into a list; Select picks an element by zero-based index.

~~~yaml
Outputs:
  SubnetListText:
    Value: !Join
      - ','
      - - !Ref PublicSubnetA
        - !Ref PublicSubnetB

Parameters:
  AllowedSubnetIds:
    Type: CommaDelimitedList
    Description: Subnet IDs supplied by deployment pipeline

Resources:
  AppInstance:
    Type: AWS::EC2::Instance
    Properties:
      SubnetId: !Select [0, !Ref AllowedSubnetIds]
~~~

Split can also be combined with Select to extract part of a string:

~~~yaml
Parameters:
  ObjectPath:
    Type: String
    Default: artifacts/reports/daily.csv

Outputs:
  SecondPathSegment:
    Value: !Select [1, !Split ['/', !Ref ObjectPath]]
~~~

Select does not check whether the index is out of bounds. If the list is empty or the index does not exist, the stack operation can fail. Validate parameter values and avoid hardcoding indices if element counts can vary. When interpolating strings with multiple values, Fn::Sub is usually more readable than Fn::Join.

### 7.4. Fn::FindInMap

FindInMap retrieves a value from Mappings using three keys: map name, top-level key, and second-level key.

~~~yaml
Mappings:
  EnvironmentConfig:
    dev:
      InstanceType: t3.micro
    prod:
      InstanceType: t3.small

Parameters:
  Environment:
    Type: String
    AllowedValues: [dev, prod]

Resources:
  AppInstance:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: !FindInMap
        - EnvironmentConfig
        - !Ref Environment
        - InstanceType
      ImageId: ami-0123456789abcdef0
~~~

The AMI ID is only an illustrative placeholder and is not guaranteed to exist. Production should retrieve AMIs from SSM public parameters or a controlled pipeline updating mappings, because AMI IDs change by Region, architecture, and release.

Mappings are static data inside the template. If values need to be managed dynamically or shared across teams, consider Parameter Store or a more suitable configuration source.

### 7.5. Fn::GetAZs and Fn::Cidr

GetAZs returns the list of Availability Zones in the specified Region. If an empty string is passed, CloudFormation uses the current Region. Cidr generates a list of child CIDR blocks from a parent CIDR block.

~~~yaml
Parameters:
  NetworkRegion:
    Type: String
    Default: ''
  VpcCidr:
    Type: String
    Default: 10.40.0.0/16

Outputs:
  FirstAvailabilityZone:
    Value:
      Fn::Select:
        - 0
        - Fn::GetAZs:
            Ref: NetworkRegion

Resources:
  PublicSubnetA:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref ApplicationVpc
      AvailabilityZone: !Select [0, !GetAZs '']
      CidrBlock: !Select
        - 0
        - !Cidr [!Ref VpcCidr, 4, 8]
~~~

With a `/16` VPC and 8 additional bits, each subnet is `/24`. Only use indices within the generated CIDR list. AZ counts and AZ ordering can differ across accounts because AZ IDs map differently to AZ names; do not assume every account shares the same physical `az-a`.

### 7.6. Fn::Base64

Base64 encodes a string, commonly used with EC2 UserData:

~~~yaml
Resources:
  AppInstance:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: ami-0123456789abcdef0
      InstanceType: t3.micro
      UserData:
        Fn::Base64: !Sub |
          #!/bin/bash
          echo "Stack=${AWS::StackName}" > /etc/app-stack
~~~

Base64 is encoding, **not encryption**. Do not place credentials/passwords in UserData; user data can be accessed via APIs/instance metadata/logs depending on permissions and system handling.

### 7.7. Fn::ImportValue

ImportValue retrieves an exported output from another stack in the same account/Region.

~~~yaml
Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: App security group
      VpcId:
        Fn::ImportValue:
          Fn::Sub: '${NetworkStackName}-VpcId'
~~~

Use the long form for nested intrinsic functions so the YAML parser and CloudFormation interpret them unambiguously. Short-form `!ImportValue !Sub ...` is invalid in many nested tag forms; the example above is safe and readable.

### 7.8. Condition Functions in Resource Properties

Equals/And/Or/Not can be combined with Condition and If:

~~~yaml
Conditions:
  IsProduction: !Equals [!Ref Environment, prod]
  HasPublicIngress: !And
    - !Condition IsProduction
    - !Equals [!Ref EnablePublicIngress, 'true']

Resources:
  OptionalIngressRule:
    Type: AWS::EC2::SecurityGroupIngress
    Condition: HasPublicIngress
    Properties:
      GroupId: !Ref AppSecurityGroup
      IpProtocol: tcp
      FromPort: 443
      ToPort: 443
      CidrIp: 203.0.113.0/24
~~~

CIDR 203.0.113.0/24 belongs to a documentation example range and should not be used as a real public client range. Public ingress requires a threat model, specific source CIDRs, and security review.

## 8. Pseudo Parameters: Values Provided by CloudFormation

Pseudo parameters are available in every template; they do not need to be declared in Parameters.

| Pseudo parameter | Value |
| --- | --- |
| AWS::AccountId | Account ID containing the stack. |
| AWS::Region | Region where the stack is deployed. |
| AWS::StackName | Name of the current stack. |
| AWS::StackId | ARN of the current stack. |
| AWS::Partition | Partition, e.g., `aws`, `aws-cn`, or `aws-us-gov`. |
| AWS::URLSuffix | DNS suffix matching the partition, e.g., `amazonaws.com`. |
| AWS::NotificationARNs | List of notification topic ARNs configured for the stack. |
| AWS::NoValue | Used in Fn::If to omit a property from the resource configuration. |

Example constructing ARNs without hardcoding partition/account/Region:

~~~yaml
Outputs:
  QueueArn:
    Value: !Sub 'arn:${AWS::Partition}:sqs:${AWS::Region}:${AWS::AccountId}:${OrdersQueue}'
  StackIdentifier:
    Value: !Ref AWS::StackId
~~~

Use AWS::Partition instead of hardcoding `arn:aws:` when the template needs to work in commercial, China, or GovCloud partitions. Do not assume all AWS partitions share the same URL suffix or service availability.

## 9. Dynamic References: Fetching Configuration and Secrets at Deploy Time

Dynamic references allow templates to reference values managed in Systems Manager Parameter Store or Secrets Manager. CloudFormation resolves the reference during stack create/update/change set when passing values to resource properties.

### 9.1. Systems Manager Parameter Store Plaintext

General pattern:

~~~text
{{resolve:ssm:parameter-name:version}}
~~~

Example using a parameter containing an AMI ID:

~~~yaml
Resources:
  AppInstance:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: '{{resolve:ssm:/golden-images/orders/ami-id:7}}'
      InstanceType: t3.micro
~~~

With dynamic references outside the Parameters section, SSM dynamic references require specifying a version. An alternative is using an AWS-specific parameter type so CloudFormation fetches the parameter value when creating the stack.

~~~yaml
Parameters:
  GoldenAmi:
    Type: AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>
    Default: /golden-images/orders/ami-id
~~~

### 9.2. Systems Manager SecureString

Pattern:

~~~text
{{resolve:ssm-secure:parameter-name:version}}
~~~

Use when retrieving a secure string from Parameter Store. A secure dynamic reference requires a specific version per AWS syntax. The principal executing the stack operation needs permission to read the parameter and appropriate KMS decrypt permissions.

Do not confuse `AWS::SSM::Parameter::Value<String>` with a SecureString parameter type. When a secure value is needed, use an `ssm-secure` dynamic reference on supported resource properties.

### 9.3. Secrets Manager Dynamic Reference

General pattern:

~~~text
{{resolve:secretsmanager:secret-id:SecretString:json-key:version-stage:version-id}}
~~~

Example fetching the `password` field from a JSON secret:

~~~yaml
Resources:
  DatabaseInstance:
    Type: AWS::RDS::DBInstance
    Properties:
      Engine: postgres
      MasterUsername: orders_admin
      MasterUserPassword: '{{resolve:secretsmanager:orders/database:SecretString:password}}'
~~~

This snippet only illustrates the property and dynamic reference, not a complete production template. Check required DBInstance properties, engine/version, storage, networking, backups, and deletion protection. The stack execution role needs `secretsmanager:GetSecretValue` and appropriate KMS permissions if the secret uses a customer managed key.

### 9.4. Rotation and Resolution Timing

Prefer **versionless references** when using Secrets Manager rotation so CloudFormation fetches the current version during an appropriate stack create/update. However, note:

- Updating the secret value in Secrets Manager alone **does not automatically make CloudFormation update resources** using the reference.
- CloudFormation re-resolves the reference when the resource is created or updated in a relevant stack operation.
- CloudFormation does not track the exact previously resolved secret version as a normal drift attribute.
- If resource properties have not changed, updating the stack may not cause the resource to be updated with the new secret.
- Verify how the target service picks up/applies new credentials; the rotation Lambda and database connection lifecycle are separate responsibilities.

### 9.5. Limitations to Remember

- A single stack template supports up to **60 dynamic references**.
- Do not use secret dynamic references in a resource's primary identifier because plaintext may appear in the resource ID or places derived from the identifier.
- Secure dynamic references are not supported in custom resources.
- Dynamic references are not supported in AWS::CloudFormation::Init metadata or EC2 UserData.
- When using Transform, CloudFormation passes the literal dynamic reference through the transform and resolves it later during the stack operation.
- Do not end a dynamic reference with a backslash because CloudFormation cannot resolve it properly.

Dynamic references reduce the risk of hardcoding secrets in templates, but do not automatically make every resource property safe. Check where the service stores the value after resolution, who can read it, and how rotation is applied.

## 10. AWS::LanguageExtensions and Extended Intrinsic Functions

Several modern intrinsic functions require the `AWS::LanguageExtensions` transform. The transform expands the template before CloudFormation creates resources.

### 10.1. Fn::ForEach

Fn::ForEach iterates over a collection and replicates a template fragment. This function can be used in Conditions, Outputs, and Resources; the transform must be declared.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::LanguageExtensions

Parameters:
  QueueSuffixes:
    Type: CommaDelimitedList
    Default: billing,inventory,analytics

Resources:
  'Fn::ForEach::Queues':
    - Suffix
    - !Ref QueueSuffixes
    - '${Suffix}Queue':
        Type: AWS::SQS::Queue
        Properties:
          SqsManagedSseEnabled: true
          Tags:
            - Key: Workload
              Value: !Ref AWS::StackName
~~~

With the collection `billing, inventory, analytics`, the transform expands three corresponding resources. Each output logical ID must be valid and unique; collection values must be chosen to form valid identifiers.

Fn::ForEach does not increase resource/template size limits: CloudFormation enforces quotas on the expanded template. Do not overuse loops to create hundreds of resources if a module/nested stack or an AWS service managing collections is more appropriate.

When updating a stack that uses AWS::LanguageExtensions, re-submit the original source template stored in source control. Avoid using `UsePreviousTemplate`/`--use-previous-template`: CloudFormation may use the already-transformed template and keep parameter values resolved as literals, preventing subsequent parameter changes from applying as intended.

### 10.2. Fn::Length

Fn::Length returns the number of elements in a list. This function is useful when checking or outputting the count of subnets/targets from a CommaDelimitedList.

~~~yaml
Transform: AWS::LanguageExtensions

Parameters:
  SubnetCidrs:
    Type: CommaDelimitedList
    Default: 10.40.1.0/24,10.40.2.0/24,10.40.3.0/24

Outputs:
  SubnetCount:
    Value:
      Fn::ToJsonString:
        count:
          Fn::Length:
            Ref: SubnetCidrs
~~~

Fn::Length requires the AWS::LanguageExtensions transform. Do not use it as a substitute for validating that a CIDR list contains non-overlapping ranges.

### 10.3. Fn::ToJsonString

ToJsonString converts an object/list into a JSON string. It can be used when a resource property expects JSON text while the template builds an object from parameters/intrinsic functions.

~~~yaml
Transform: AWS::LanguageExtensions

Parameters:
  Environment:
    Type: String
    Default: dev

Outputs:
  RuntimeConfigurationJson:
    Value:
      Fn::ToJsonString:
        environment: !Ref Environment
        region: !Ref AWS::Region
        stack: !Ref AWS::StackName
~~~

This function is helpful for configuration payloads; avoid assembling JSON manually with Fn::Join, which easily introduces escaping, quoting, or data-type errors.

### 10.4. Fn::GetStackOutput

This function reads an output from another stack without requiring an Export in the source stack. It works cross-account/cross-Region; cross-account usage requires a RoleArn with `cloudformation:DescribeStacks` permission and a trust policy allowing the target stack's execution role.

~~~yaml
Parameters:
  NetworkStackName:
    Type: String
    Default: shared-network

Resources:
  AppSubnetAttachment:
    Type: AWS::EC2::NetworkInterface
    Properties:
      SubnetId:
        Fn::GetStackOutput:
          StackName: !Ref NetworkStackName
          OutputName: PrivateSubnetId
          Region: ap-southeast-1
~~~

Fn::GetStackOutput is a **weak reference**: the value is resolved at stack create/update time; when the source output changes or is deleted, consuming stacks are not automatically notified or updated. This function does not support cross-partition references. If using RoleArn, scope `cloudformation:DescribeStacks` to the exact stack ARN and restrict the trust policy.

Do not use short-form `!GetStackOutput` when parameter values contain short-form functions like `!Ref` or `!Sub`; use the full form `Fn::GetStackOutput` as shown.

For cross-account references, add RoleArn and configure a role in the source account allowing `cloudformation:DescribeStacks` on the specific stack ARN; the trust policy must allow the target stack's execution role to AssumeRole. Do not use `Resource: '*'` when you can scope to a single stack.

### 10.5. Choosing Between Functions

| Function | When to use |
| --- | --- |
| Ref | Get a parameter value or resource return value. |
| GetAtt | Get a resource-specific attribute such as ARN, endpoint, or queue name. |
| Sub | Build strings from parameters/resources/pseudo parameters. |
| Join | Concatenate a list into a string. |
| Select | Pick an element from a list by index. |
| Split | Split a string into a list. |
| FindInMap | Look up static data. |
| GetAZs | Get the list of AZs in a Region. |
| Cidr | Compute subnet CIDRs from a parent CIDR. |
| Base64 | Encode text, typically used with UserData. |
| If / Equals / And / Or / Not | Evaluate conditions and select properties/resources. |
| ImportValue | Reference an export in the same account/Region with a strong dependency. |
| GetStackOutput | Reference another stack's output, supporting cross-account/Region as a weak reference. |
| ForEach | Replicate fragments from a collection with LanguageExtensions. |
| Length / ToJsonString | Count list elements or serialize JSON with LanguageExtensions. |

## 11. End-to-End Example: SQS Queue with Optional DLQ

The template below combines Parameters, Conditions, Resources, intrinsic functions, and Outputs in a deployable stack. The queue is encrypted with SQS-managed server-side encryption; the DLQ can be toggled via a parameter.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Orders processing queue with an optional dead-letter queue

Parameters:
  Environment:
    Type: String
    Default: dev
    AllowedValues:
      - dev
      - staging
      - prod
    Description: Deployment environment

  QueueRetentionSeconds:
    Type: Number
    Default: 345600
    MinValue: 60
    MaxValue: 1209600
    Description: Source queue message retention in seconds

  EnableDLQ:
    Type: String
    Default: 'true'
    AllowedValues:
      - 'true'
      - 'false'
    Description: Create a dead-letter queue

Conditions:
  CreateDLQ: !Equals [!Ref EnableDLQ, 'true']

Resources:
  OrdersDeadLetterQueue:
    Type: AWS::SQS::Queue
    Condition: CreateDLQ
    Properties:
      MessageRetentionPeriod: 1209600
      SqsManagedSseEnabled: true
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Purpose
          Value: orders-dead-letter

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      MessageRetentionPeriod: !Ref QueueRetentionSeconds
      VisibilityTimeout: 60
      SqsManagedSseEnabled: true
      RedrivePolicy: !If
        - CreateDLQ
        - deadLetterTargetArn: !GetAtt OrdersDeadLetterQueue.Arn
          maxReceiveCount: 5
        - !Ref AWS::NoValue
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Purpose
          Value: orders-processing

Outputs:
  OrdersQueueUrl:
    Description: Queue URL used by application clients
    Value: !Ref OrdersQueue

  OrdersQueueArn:
    Description: Queue ARN used in IAM policies
    Value: !GetAtt OrdersQueue.Arn

  OrdersDLQArn:
    Condition: CreateDLQ
    Description: ARN of the dead-letter queue
    Value: !GetAtt OrdersDeadLetterQueue.Arn

  Environment:
    Description: Environment selected for this stack
    Value: !Ref Environment
~~~

### 11.1. Reading the Template Layer by Layer

- Parameters declare environment, retention, and DLQ selection.
- Condition CreateDLQ determines whether the DLQ is created.
- OrdersDeadLetterQueue is only created when the condition is true.
- OrdersQueue's RedrivePolicy uses Fn::If; when the DLQ is disabled, AWS::NoValue omits the property from the queue configuration.
- GetAtt retrieves the DLQ ARN; Ref on an SQS queue returns the queue URL.
- Outputs publish URLs/ARNs for application deployments or IAM policy pipelines to use.
- Tags help categorize resources and support cost allocation.

This is a foundational example. Production needs queue policies, a KMS customer managed key if required, CloudWatch alarms, a redrive allow policy where appropriate, a retention/replay runbook, and least-privilege IAM permissions.

### 11.2. Testing Parameter Changes

| Environment | EnableDLQ | Expected result |
| --- | --- | --- |
| dev | false | Creates only OrdersQueue; no RedrivePolicy. |
| staging | true | Creates OrdersQueue and OrdersDeadLetterQueue; source queue points to DLQ. |
| prod | true | Creates both queues with prod tags; review policies/alarms/retention before executing. |

If the stack was already created with a DLQ and you update EnableDLQ to false, CloudFormation will delete the OrdersDeadLetterQueue resource per the Condition. Check whether the queue holds messages that must be preserved before running the update.

## 12. Resource Dependencies and Lifecycle Attributes

CloudFormation builds a dependency graph to determine the order for creating, updating, and deleting resources.

### 12.1. Implicit Dependency

When a resource property uses Ref, GetAtt, or Sub to reference another resource, CloudFormation automatically infers the dependency.

~~~yaml
Resources:
  AppQueue:
    Type: AWS::SQS::Queue

  OrdersTopic:
    Type: AWS::SNS::Topic

  QueuePolicy:
    Type: AWS::SQS::QueuePolicy
    Properties:
      Queues:
        - !Ref AppQueue
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: sns.amazonaws.com
            Action: sqs:SendMessage
            Resource: !GetAtt AppQueue.Arn
            Condition:
              ArnEquals:
                aws:SourceArn: !Ref OrdersTopic
~~~

QueuePolicy depends on AppQueue and OrdersTopic due to Ref/GetAtt. CloudFormation creates the referenced resources first, then creates the policy; on deletion, dependencies are processed in reverse order.

### 12.2. DependsOn

Use DependsOn when an ordering dependency exists that is not expressed through resource property references.

~~~yaml
Resources:
  InternetGateway:
    Type: AWS::EC2::InternetGateway

  Vpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.50.0.0/16

  VpcGatewayAttachment:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref Vpc
      InternetGatewayId: !Ref InternetGateway

  PublicRoute:
    Type: AWS::EC2::Route
    DependsOn: VpcGatewayAttachment
    Properties:
      RouteTableId: !Ref PublicRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway
~~~

DependsOn accepts a single logical ID or a list of logical IDs. Do not mechanically add DependsOn to every resource; Ref/GetAtt/Sub already create implicit dependencies. Overusing explicit dependencies reduces parallel deployment capability.

### 12.3. DeletionPolicy

DeletionPolicy determines how CloudFormation handles a resource when it is removed from the template or the stack is deleted.

| Value | Meaning |
| --- | --- |
| Delete | Deletes the resource per the resource type's default behavior. |
| Retain | Keeps the physical resource; the resource is no longer managed by the stack as before. |
| Snapshot | Creates a snapshot before deletion, if supported by the resource type. |
| RetainExceptOnCreate | Retains in most cases, but if the resource was created in an initial stack operation that failed, it can be deleted per the attribute's semantics. |

Example retaining an S3 bucket when deleting a stack:

~~~yaml
Resources:
  AuditBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
~~~

Retain can create orphaned resources that continue incurring charges. Document ownership, backups, lifecycle, and manual deletion procedures when no longer needed.

### 12.4. UpdateReplacePolicy

When changing a property that requires replacement, CloudFormation creates a new physical resource and handles the old resource according to UpdateReplacePolicy.

~~~yaml
Resources:
  Database:
    Type: AWS::RDS::DBInstance
    DeletionPolicy: Snapshot
    UpdateReplacePolicy: Snapshot
    Properties:
      Engine: postgres
      DBInstanceClass: db.t4g.micro
      AllocatedStorage: 20
      MasterUsername: dbadmin
      MasterUserPassword: '{{resolve:secretsmanager:orders/db:SecretString:password}}'
~~~

The RDS snippet above only illustrates attributes and a dynamic reference, not a complete production template. Verify engine/version, subnet group, security groups, backups, storage encryption, KMS, and high availability requirements before deploying.

DeletionPolicy applies when removing a resource from a stack or deleting a stack; UpdateReplacePolicy applies to the old physical resource during replacement. Neither attribute replaces backups/PITR or recovery procedures.

### 12.5. CreationPolicy and UpdatePolicy

CreationPolicy can instruct CloudFormation to wait for signals from a resource (such as an Auto Scaling group/EC2) before marking creation complete. UpdatePolicy controls how certain resources are updated, such as rolling updates for an Auto Scaling group.

Use these attributes when resources require bootstrapping/health checks before the workload is considered ready. Do not assume an EC2 instance in `CREATE_COMPLETE` means the application inside is healthy if the template lacks signaling/health validation.

## 13. Splitting Templates into Nested Stacks and Modules

Large templates should be split along ownership/lifecycle boundaries, such as network foundation, security baseline, data layer, and application workload.

### 13.1. Nested Stacks

A nested stack is an AWS::CloudFormation::Stack resource created inside a parent stack. The parent can pass Parameters and read child Outputs.

~~~yaml
Resources:
  NetworkNestedStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: https://example-bucket.s3.ap-southeast-1.amazonaws.com/templates/network.yaml
      Parameters:
        VpcCidr: 10.60.0.0/16
        Environment: !Ref Environment

Outputs:
  NetworkVpcId:
    Value: !GetAtt NetworkNestedStack.Outputs.VpcId
~~~

TemplateURL must point to a template uploaded to S3 (or a CloudFormation-supported URL). Do not pass a local `file://` URL for a nested stack. Configure bucket/template access permissions and versioning so the parent deploys the intended artifact.

### 13.2. Nested Stack or Export/ImportValue?

| Approach | Best suited when |
| --- | --- |
| Nested stacks | Templates belong to the same stack hierarchy, are deployed/managed with a parent, and pass outputs between child stacks. |
| Export + ImportValue | Independent stacks need to share resource IDs in the same account/Region with CloudFormation-enforced dependencies. |
| Fn::GetStackOutput | Need to reference unexported outputs, cross-account, or cross-Region; weak reference is acceptable. |
| CloudFormation modules | Want to package reusable resource patterns as a module registered in the CloudFormation registry. |

### 13.3. Rules for Splitting Modules

- Split by lifecycle and owner; do not split files merely because a template is long.
- Keep interfaces small: input parameters, clear outputs.
- Do not export every resource; only publish values needed by consumers.
- Avoid circular dependencies between stacks.
- Version nested templates/modules and pin reviewed artifacts.
- Be able to redeploy one module without losing state of other resources when ownership boundaries are clear.
## 14. Validating, Deploying, and Updating Stacks Safely

Do not promote a new template to production merely because a YAML parser accepts the file. Verify syntax, resource schemas, security findings, parameter values, and change set impact.

### 14.1. Structural Validation with CloudFormation

~~~bash
aws cloudformation validate-template \
  --template-body file://template.yaml \
  --region ap-southeast-1
~~~

ValidateTemplate checks the template against the service's structural rules and returns metadata such as parameters/capabilities. It does not replace lint/schema checks for all resource properties, IAM/security rules, or deployment testing.

### 14.2. Linting Templates Before Creating Stacks

AWS CloudFormation Linter (cfn-lint) checks YAML/JSON against resource provider schemas and additional rules.

~~~bash
cfn-lint --regions ap-southeast-1 template.yaml
~~~

Multiple Regions can be passed if the template deploys across several places:

~~~bash
cfn-lint --regions ap-southeast-1 ap-northeast-1 template.yaml
~~~

AWS CloudFormation Validate (cfn-validate) is another local checking tool; it can check structure, references, resource schemas, and built-in rules before deployment:

~~~bash
cfn-validate template.yaml
~~~

Local tools cannot simulate every condition of the target account, quotas, permissions, resource state, or service availability. You must still review the change set and test in a sandbox.

### 14.3. Creating a Change Set for a New Stack

A change set shows resources that will be created/modified before execution:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-infrastructure \
  --change-set-name orders-infrastructure-first-review \
  --change-set-type CREATE \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=Environment,ParameterValue=staging \
    ParameterKey=QueueRetentionSeconds,ParameterValue=86400 \
    ParameterKey=EnableDLQ,ParameterValue=true \
  --region ap-southeast-1
~~~

After creation, inspect the change set:

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-infrastructure \
  --change-set-name orders-infrastructure-first-review \
  --region ap-southeast-1
~~~

Review resource actions, replacement behavior, parameter values, IAM changes, resource deletions, and warnings. For stacks containing IAM resources, declare the appropriate capability when creating the change set:

- CAPABILITY_IAM: acknowledges the template may create IAM resources.
- CAPABILITY_NAMED_IAM: required when the template creates IAM resources with custom names.
- CAPABILITY_AUTO_EXPAND: required in certain cases where macros/transforms need auto expansion.

A capability acknowledges that the deployer reviewed the IAM/macro impact; it does not grant permissions to the caller or execution role.

### 14.4. Executing a Change Set

Execute only after reviewers confirm the planned changes:

~~~bash
aws cloudformation execute-change-set \
  --stack-name orders-infrastructure \
  --change-set-name orders-infrastructure-first-review \
  --region ap-southeast-1
~~~

Monitor progress:

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-infrastructure \
  --region ap-southeast-1

aws cloudformation describe-stack-events \
  --stack-name orders-infrastructure \
  --region ap-southeast-1
~~~

A change set is a preview, not a transaction guaranteeing deployment success. Resource providers can still return errors during execution, quotas can change, or resources may fail to stabilize. If an update fails, inspect stack events and create a new change set after fixing the template.

### 14.5. Updating a Stack

For an existing stack, use `ChangeSetType` `UPDATE` and pass the new template/parameter changes. Use `UsePreviousValue` for unchanged parameters if the CLI/API workflow needs to retain previous values.

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-infrastructure \
  --change-set-name orders-infrastructure-update-review \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=Environment,UsePreviousValue=true \
    ParameterKey=QueueRetentionSeconds,ParameterValue=172800 \
    ParameterKey=EnableDLQ,UsePreviousValue=true \
  --region ap-southeast-1
~~~

After reviewing the change set, execute it with `execute-change-set`. Do not update CloudFormation-managed resources directly via the service console/CLI unless a clear drift reconciliation process exists.

### 14.6. Rollback and Failure Handling

CloudFormation tracks stack operations and normally rolls back changes when creation/update fails according to rollback configuration. When encountering a failure:

1. Open stack Events and find the first resource with `CREATE_FAILED`/`UPDATE_FAILED`/`DELETE_FAILED`.
2. Read `StatusReason` and request ID; classify whether it is a template error, IAM, quota, dependency, or service stabilization issue.
3. Check resource state and service health.
4. Fix the template/permissions/parameters.
5. Create a new change set and review it before re-executing.

Do not disable rollback as a default fix. For `UPDATE_ROLLBACK_FAILED`, use `ContinueUpdateRollback` only after understanding which resource failed to roll back and skipping resources in a controlled way. After recovery, synchronize the template and actual state.

## 15. Drift Detection and Controlling Out-of-Band Changes

Drift occurs when a resource is edited directly outside CloudFormation, causing actual configuration to diverge from template/stack parameters.

### 15.1. Detecting Drift

~~~bash
aws cloudformation detect-stack-drift \
  --stack-name orders-infrastructure \
  --region ap-southeast-1
~~~

The command returns a `DriftDetectionId`. Use that ID to monitor the result:

~~~bash
aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id DRIFT-DETECTION-ID \
  --region ap-southeast-1

aws cloudformation describe-stack-resource-drifts \
  --stack-name orders-infrastructure \
  --region ap-southeast-1
~~~

Drift detection only supports resource types/properties with drift support. `NOT_CHECKED` or `IN_SYNC` is not absolute proof that every runtime setting is correct.

### 15.2. Drift Handling Workflow

- Identify who made the out-of-template change and why.
- Compare desired state against actual state.
- If the change is valid, update the template/parameters to bring it into source control.
- If the change is invalid, create a change set to restore the resource to the desired state after review.
- For stateful resources, assess backup/data impact before modifying or replacing.
- Log an incident/change record and prevent recurring manual changes.

Do not use CloudFormation to accidentally overwrite an approved production change that has not yet been updated in the template.

## 16. IAM, Security, and Stack Governance

### 16.1. CloudFormation Execution Role

A stack can use a service role so CloudFormation calls AWS APIs on behalf of the stack. This role needs least-privilege permissions for the exact resource types/actions managed by the template.

- Callers creating/updating stacks need corresponding CloudFormation permissions and `iam:PassRole` when passing a service role.
- The execution role needs permissions to create/update/delete resources.
- For cross-account references, the role may need scoped `sts:AssumeRole` and `cloudformation:DescribeStacks`.
- Do not attach `AdministratorAccess` to an execution role just to make a template deploy.
- When editing IAM policies in a template, review both newly granted and revoked permissions.

### 16.2. IAM Resources and Capabilities

CloudFormation requires deployers to acknowledge when a template contains IAM resources. `CAPABILITY_IAM`/`CAPABILITY_NAMED_IAM` is only a review acknowledgment; the caller and execution role still need appropriate permissions.

Do not create policies with `Action: '*'` and `Resource: '*'` if the workload only needs a specific queue, secret, topic, or key. Use logical IDs and ARNs from Ref/GetAtt/Sub to reduce hardcoded resource identifiers.

### 16.3. Protecting Sensitive Data

- Never hardcode credentials in templates, Parameters files, Metadata, or Outputs.
- Use Secrets Manager/SSM SecureString dynamic references on supported properties.
- Restrict the execution role to reading only the required secrets/parameters.
- Check KMS key policies and `kms:Decrypt`.
- Avoid putting secrets into UserData, resource primary identifiers, tags, or stack events.
- Control who has `cloudformation:DescribeStacks`/`DescribeStackEvents`/`DescribeChangeSet` permissions and read access to templates/parameters.
- Store templates in source control; avoid storing resolved secret values in build artifacts.

NoEcho only masks parameter values in certain displays; it does not guarantee secrets will not appear in resource properties/logs or downstream systems.

### 16.4. S3, Databases, and Stateful Resources

For S3 buckets, databases, EFS, and data-holding resources:

- Define DeletionPolicy and UpdateReplacePolicy.
- Enable encryption, versioning/PITR/backups according to RPO/RTO.
- Use deletion protection on databases where needed.
- Design retention/lifecycle rules and recovery procedures.
- Check for replacement before modifying immutable properties.
- Do not delete experimental stacks containing resources with `Retain` without an inventory/owner.

### 16.5. Tags and Cost

Apply consistent tags such as `Environment`, `Owner`, `CostCenter`, `Application`, and `DataClassification`. Verify which resource types support stack-level tag propagation and which require declaring `Tags` individually.

Cost Explorer/Cost and Usage Reports can use tags for cost allocation. Account for costs of retained resources, snapshots, logs, NAT gateways, endpoints, KMS keys, and resources not removed upon stack deletion.

### 16.6. YAML Syntax Pitfalls

- Quote String values like `'true'`/`'false'` if the parameter Type is String; leave booleans `true`/`false` unquoted when the property schema expects Boolean.
- Use Number for numeric parameters and pass appropriate values; avoid unnecessary quoting or stringifying that reduces template readability.
- Quote strings containing special characters, colons, `#` signs, or content that a YAML parser might interpret as syntax.
- When nesting intrinsic functions, prefer the full `Fn::...` form if short-form tags cause parser errors or are unsupported.
- Property names are case-sensitive; match the exact resource specification.
- Logical IDs must be stable, valid, and unique; avoid generating unpredictable dynamic names unless necessary.
- CloudFormation YAML includes custom tags such as `!Ref`, `!GetAtt`, `!Sub`; a generic YAML parser may report errors if unaware of these tags.
- Avoid YAML anchors/aliases or YAML features not supported by CloudFormation; stick to the subset accepted by CloudFormation documentation.

If a template parses in an editor yet CloudFormation rejects it, inspect YAML tag syntax, indentation, resource property names, and nested intrinsic function forms.

## 17. Common Pitfalls

| Misconception | Correct understanding |
| --- | --- |
| "A valid YAML template is deployable." | YAML syntax is only one check layer; there are still resource schemas, IAM, quotas, references, and runtime service behavior. |
| "Resources is an optional section." | Resources is a required section in a CloudFormation template. |
| "Ref always returns an ARN." | Ref returns a value per resource type; SQS queue Ref returns the queue URL, while ARN comes from GetAtt. |
| "GetAtt can retrieve any attribute." | Only attributes published by the resource provider are available. |
| "Parameters replace a secret manager." | Normal parameters are stack inputs; secrets should be stored in Secrets Manager/SSM SecureString and used via dynamic references where supported. |
| "NoEcho protects secrets everywhere." | NoEcho only masks certain displays; secrets can still leak in resource properties, outputs, or logs. |
| "Mappings auto-update with new AMIs." | Mappings are static data in the template; they must be updated or replaced with Parameter Store/an AMI pipeline. |
| "Conditions only hide resources without deleting them." | When a condition switches to false during an update, the attached resource can be deleted. |
| "Fn::If false returns null." | AWS::NoValue is used to omit a property from the resource configuration. |
| "Select checks list index bounds." | Out-of-range indices can cause the stack operation to fail. |
| "GetAZs returns the same physical AZ names across all accounts." | AZ names can map differently across accounts; use AZ IDs when physical AZ alignment is required. |
| "Base64 is encryption." | Base64 is only encoding, providing no data confidentiality. |
| "Export + ImportValue works cross-Region." | Same account/Region only; consider Fn::GetStackOutput for cross-account/Region. |
| "You can delete a stack that still has imports." | A stack exporting an Export cannot be deleted or have that output changed until consumers remove their imports. |
| "Fn::GetStackOutput creates a strong dependency." | It is a weak reference and does not lock the source stack against deletion. |
| "Dynamic references auto-update resources after secret rotation." | CloudFormation only resolves them when the resource is created/updated in a relevant stack operation. |
| "Fn::ForEach works without a Transform." | `AWS::LanguageExtensions` must be declared. |
| "DependsOn is needed for every resource." | Ref/GetAtt/Sub create implicit dependencies; DependsOn is only used when ordering cannot be inferred from properties. |
| "DeletionPolicy Retain is a backup." | Retain keeps the resource, without creating backups or verifying restore capability. |
| "UpdateReplacePolicy controls stack deletion." | That attribute handles the old resource during replacement; DeletionPolicy handles stack/template deletion. |
| "Change sets guarantee deployment success." | A change set is a preview; resource providers can still fail during execution. |
| "Drift detection checks every property of every resource." | Only supported resource types/properties are compared. |
| "Resources created via console are automatically managed by CloudFormation." | Out-of-stack changes can cause drift or unmanaged resources. |
| "Stack UPDATE_COMPLETE proves the application is healthy." | CloudFormation tracks resource provisioning; separate application health checks and alarms are needed. |
| "Stack-level tags always propagate to every resource." | Tag propagation depends on the resource type; verify and declare individual Tags when needed. |

## 18. Practice Exercises with Suggested Answers

### Exercise 1 — Parameters for Multiple Environments

**Prompt:** A template needs to deploy dev, staging, and prod with the same resource types but different instance sizes.

**Answer:** Use an `Environment` Parameter with `AllowedValues`; use `Mappings + FindInMap` for static values or pipeline-supplied parameterized values. For frequently changing configs, consider Parameter Store/AppConfig.

### Exercise 2 — Does Ref Return Queue ARN or URL?

**Prompt:** An IAM policy needs the SQS queue ARN, but the template currently uses `Value: !Ref OrdersQueue`.

**Answer:** Ref on `AWS::SQS::Queue` returns the queue URL. Use `!GetAtt OrdersQueue.Arn` to obtain the ARN.

### Exercise 3 — Toggling a DLQ

**Prompt:** Dev does not need a DLQ, production needs a DLQ; you want to use the same template.

**Answer:** Declare parameter `EnableDLQ`, Condition `CreateDLQ`, attach the Condition to the DLQ resource, and use `Fn::If`/`AWS::NoValue` for `RedrivePolicy`. Before disabling a DLQ on an existing stack, check whether messages in the queue need to be preserved.

### Exercise 4 — Splitting a VPC CIDR

**Prompt:** A VPC has a `/16` CIDR, and you want to create four `/24` subnets.

**Answer:** `Fn::Cidr` with count 4 and 8 additional bits. Use `Select` with valid indices to assign each subnet block.

### Exercise 5 — Sharing a VPC Between Two Stacks

**Prompt:** A network stack creates a VPC, and an application stack needs the VPC ID in the same account/Region.

**Answer:** The network stack exports the VPC ID output; the application stack uses `Fn::ImportValue`. Before deleting/changing the export, run `list-imports` to find and remove all consumers.

### Exercise 6 — Cross-Account Output

**Prompt:** An application stack in account B needs a subnet ID from a network stack in account A.

**Answer:** Export/ImportValue does not support cross-account access. Use `Fn::GetStackOutput` with a `RoleArn` in account A granting `cloudformation:DescribeStacks` on the specific stack ARN and a trust policy for account B's execution role.

### Exercise 7 — Secrets in an RDS Template

**Prompt:** You do not want the database password appearing in the template in Git.

**Answer:** Store the secret in Secrets Manager, use a dynamic reference in `MasterUserPassword` if supported by the resource property, grant `GetSecretValue`/KMS permissions to the stack execution role, and do not put the secret in Outputs. Design rotation separately.

### Exercise 8 — Secret Rotated but Database Password Unchanged

**Prompt:** Secrets Manager `AWSCURRENT` rotated, yet the DB instance still uses the old password.

**Answer:** Dynamic references do not automatically update resources when a secret value changes. You need a corresponding resource/stack update or service-supported rotation integration; verify connection pools and target database state.

### Exercise 9 — Fn::Sub Literal

**Prompt:** UserData needs to contain the literal shell string `${HOME}`, but `Fn::Sub` is substituting the placeholder.

**Answer:** Escape the placeholder using `Fn::Sub` syntax and verify the shell receives the exact string. Do not let shell variables be misinterpreted by CloudFormation as parameter/resource references.

### Exercise 10 — Condition Switching from True to False

**Prompt:** A stack already created `ProductionAlarm` with Condition `IsProduction`. `Environment` is updated to `dev`.

**Answer:** Resources attached to a false condition can be deleted. Evaluate deletion/retention before changing parameters; do not rely on Conditions to protect stateful resources without lifecycle design.

### Exercise 11 — Template Needing Multiple Queues

**Prompt:** There are 8 queues with the same structure, and you want to avoid duplicating YAML.

**Answer:** Use `AWS::LanguageExtensions` + `Fn::ForEach` with a `CommaDelimitedList`. Check post-expansion logical IDs, quotas, and template readability.

### Exercise 12 — Resource Must Be Created After Gateway Attachment

**Prompt:** A public route must be created after the VPC gateway attachment, but properties do not reference the attachment.

**Answer:** Use `DependsOn` for `VpcGatewayAttachment`. Do not add `DependsOn` when the dependency is already expressed via Ref/GetAtt/Sub.

### Exercise 13 — Changing Instance Type Causes Replacement

**Prompt:** A change set reports the resource needs replacement; local data on the instance may be lost.

**Answer:** Review the replacement, snapshots/backups, `DeletionPolicy`, and `UpdateReplacePolicy`. If state must persist, separate state into managed storage and prepare a migration/rollback plan.

### Exercise 14 — Stack Drift

**Prompt:** An operator edited a security group rule directly in the console.

**Answer:** Run `detect-stack-drift`, read resource drift details, and determine whether the change was approved. If valid, update the template; if not, create a change set to bring the resource back to the desired state.

### Exercise 15 — Change Set Containing an IAM Role

**Prompt:** A template creates an IAM role with a custom name and policy.

**Answer:** Pass `CAPABILITY_NAMED_IAM` when creating the stack/change set, review principals/actions/resources and the execution role. Capability acknowledgment does not replace actual IAM permissions.

### Exercise 16 — CloudFormation Rollback Failed

**Prompt:** A stack is in `UPDATE_ROLLBACK_FAILED`.

**Answer:** Read Events/`StatusReason`, locate the resource that failed to roll back, and restore the dependency/permission/service state. Use `ContinueUpdateRollback` in a controlled manner, skipping resources only when consequences are understood, and synchronize the template afterward.

## 19. Self-Check Questions

**Question 1.** What formats are commonly used for CloudFormation templates?  
**Answer:** YAML or JSON.

**Question 2.** Which section is required in a template?  
**Answer:** Resources.

**Question 3.** What is a stack?  
**Answer:** A collection of resources managed by CloudFormation from a template and parameter values.

**Question 4.** How does a Logical ID differ from a Physical ID?  
**Answer:** A Logical ID is the identifier within the template; a Physical ID is the actual resource identifier created by the AWS service.

**Question 5.** What are Parameters used for?  
**Answer:** Accepting inputs when creating/updating a stack so templates can be reused.

**Question 6.** What does `AllowedValues` do?  
**Answer:** Restricts a parameter to a set of permitted values.

**Question 7.** Is `NoEcho` a secret vault?  
**Answer:** No; it only masks certain displays and does not guarantee secrets cannot leak elsewhere.

**Question 8.** What is `AWS::SSM::Parameter::Value<String>` used for?  
**Answer:** Fetching a parameter value from Systems Manager Parameter Store by key.

**Question 9.** What kind of data do Mappings fit best?  
**Answer:** Static lookup data inside the template, such as configs by Region/environment.

**Question 10.** Which function looks up Mappings?  
**Answer:** Fn::FindInMap.

**Question 11.** Can Conditions reference resource attributes?  
**Answer:** No; conditions are based on parameters, pseudo parameters, mappings, and other conditions.

**Question 12.** When a resource's condition becomes false during an update, what can happen?  
**Answer:** The resource can be deleted from the stack.

**Question 13.** When is `AWS::NoValue` used?  
**Answer:** Inside `Fn::If` to omit a property from a resource configuration.

**Question 14.** What are Outputs used for?  
**Answer:** Publishing resource identifiers/values after a stack deploys.

**Question 15.** What does Ref on an SQS queue return?  
**Answer:** Queue URL; the ARN is retrieved via GetAtt.

**Question 16.** What is `Fn::GetAtt` used for?  
**Answer:** Retrieving a resource-specific attribute such as an ARN, queue name, or endpoint.

**Question 17.** What is the advantage of `Fn::Sub`?  
**Answer:** Substitutes placeholders in a string with parameters, pseudo parameters, resource IDs, or attributes.

**Question 18.** What index does `Fn::Select` start from?  
**Answer:** Zero-based index, starting at 0.

**Question 19.** What does `Fn::GetAZs` return?  
**Answer:** A list of Availability Zones in the specified Region.

**Question 20.** What does `Fn::Cidr` do?  
**Answer:** Generates a list of subnet CIDRs from a parent CIDR block.

**Question 21.** Does Base64 encrypt secrets?  
**Answer:** No; Base64 is only encoding.

**Question 22.** Does `Fn::ImportValue` support cross-Region references?  
**Answer:** No; only the same account and Region.

**Question 23.** When another stack imports an Export, can the source stack be deleted?  
**Answer:** Not until all imports are removed.

**Question 24.** How does `Fn::GetStackOutput` differ from `ImportValue`?  
**Answer:** Does not require Export and supports cross-account/Region, but is a weak reference.

**Question 25.** Which Transform does `Fn::ForEach` require?  
**Answer:** AWS::LanguageExtensions.

**Question 26.** Which group do `Fn::Length` and `Fn::ToJsonString` belong to?  
**Answer:** Intrinsic functions supported via AWS::LanguageExtensions.

**Question 27.** Does a dynamic reference auto-update a resource when a secret rotates?  
**Answer:** No; CloudFormation resolves it when the resource is created/updated in a relevant stack operation.

**Question 28.** How many dynamic references does a template support at most?  
**Answer:** 60 per stack template.

**Question 29.** When is `DependsOn` needed?  
**Answer:** When specifying a dependency order that Ref/GetAtt/Sub do not express automatically.

**Question 30.** What does `DeletionPolicy: Retain` do?  
**Answer:** Preserves the physical resource when removed from the stack or when the stack is deleted; the resource may become unmanaged.

**Question 31.** When does `UpdateReplacePolicy` apply?  
**Answer:** When a resource is replaced during a stack update, applying to the old physical resource.

**Question 32.** Does a change set execute changes automatically?  
**Answer:** No; the change set must be executed after review.

**Question 33.** How does `cfn-lint` help?  
**Answer:** Validates templates against CloudFormation schemas and rules, catching invalid properties/references and common issues.

**Question 34.** Does drift detection check every resource/property?  
**Answer:** No; only supported resource types/properties.

**Question 35.** Why should a CloudFormation execution role follow least privilege?  
**Answer:** Limits the permissions CloudFormation can use to create/update/delete resources, reducing blast radius.

## 20. Production Checklist and References

### 20.1. Pre-Production Checklist

1. Template is in source control with owner, version, and review history.
2. Logical IDs are stable; parameters have sensible types, descriptions, constraints, and defaults.
3. Mappings hold only static data; frequently changing data is retrieved from an appropriate parameter/config service.
4. Conditions do not accidentally delete stateful resources when parameters change.
5. Outputs publish the right values; no secrets are placed in Outputs.
6. Export names are unique; a consumer inventory exists before changing/deleting exports.
7. Intrinsic functions use the right resource return values in schema-supported locations.
8. Pseudo parameters are used instead of hardcoding account/Region/partition where possible.
9. Dynamic references use proper patterns, permissions, version/rotation strategies, and are absent from primary identifiers.
10. AWS::LanguageExtensions/Fn::ForEach declare the transform and expanded template quotas are verified.
11. Dependencies use implicit references first; DependsOn is used only when necessary.
12. DeletionPolicy/UpdateReplacePolicy are defined for databases, buckets, storage, and stateful resources.
13. Nested stacks/modules have small interfaces, versioned artifacts, and no circular dependencies.
14. ValidateTemplate, cfn-lint, or cfn-validate runs in CI.
15. Change sets are reviewed; replacement, IAM changes, resource deletions, and quotas are checked.
16. CloudFormation execution roles and `iam:PassRole` are scoped to least privilege.
17. Tags, encryption, logging, backups/PITR, deletion protection, and retention meet policy.
18. Drift detection and reconciliation have an operational schedule.
19. Rollback, recovery, and resource import/replacement have runbooks.
20. Cost review accounts for retained resources, snapshots, NAT, endpoints, logs, KMS, and downstream dependencies.

### 20.2. Conclusion

A CloudFormation template is a specification of desired infrastructure state. Parameters allow one template to serve multiple environments; Mappings and Conditions select configurations; Outputs publish needed values; intrinsic functions wire template parts together and reference resources at deploy time.

When designing for production, evaluate the template alongside the IAM execution role, resource lifecycle, change sets, dynamic references, drift detection, and rollback procedures. A template can deploy cleanly yet still lack backups, least-privilege permissions, monitoring, or application readiness. Check both resource configuration and how the team operates the stack across multiple updates.

### 20.3. Official AWS Documentation

- [CloudFormation template sections](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-anatomy.html) — template structure, Resources, Parameters, Outputs, Mappings, Conditions, and Transform.
- [Parameters syntax](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html) — parameter types, constraints, and references.
- [Outputs syntax](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html) — outputs and export names.
- [Intrinsic function reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference.html) — function list and supported locations.
- [Fn::GetAtt](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-getatt.html) — resource attributes.
- [Fn::Sub](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-sub.html) — string substitution and variable map.
- [Condition functions](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-conditions.html) — Equals, And, Or, Not, and If.
- [Fn::ForEach](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-foreach.html) — loop expansion and LanguageExtensions.
- [Fn::GetStackOutput](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-getstackoutput.html) — cross-account/Region stack outputs.
- [Cross-stack exports and imports](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html) — Export, ImportValue, and list-imports.
- [Dynamic references](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html) — Parameter Store/Secrets Manager references and limitations.
- [Secrets Manager dynamic references](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-secretsmanager.html) — versionless references and rotation behavior.
- [CloudFormation best practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html) — managing stacks, credentials, and change sets.
- [Create a change set](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-create.html) — previewing stack changes.
- [Validate with cfn-lint](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-lint.html) — local schema/rule validation.
- [Validate stack deployments](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/validate-stack-deployments.html) — deployment validation and change set review.
- [DependsOn attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-dependson.html) — explicit resource dependencies.
