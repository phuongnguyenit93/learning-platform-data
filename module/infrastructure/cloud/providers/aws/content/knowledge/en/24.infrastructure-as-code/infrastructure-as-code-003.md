# Dependencies, Nested Stacks, and Cross-Stack References

> **Chapter:** Infrastructure as Code  
> **Module:** `CLOUD_PROVIDERS_AWS` — exploring the AWS ecosystem across Regions/AZs, IAM, VPC, compute services, storage, databases, integration, and serverless; building the ability to select services and design and deploy applications that are secure, monitored, recoverable, and cost-controlled.

An AWS system is typically split into multiple layers: networking, security, data, application, and observability. An EC2 instance needs a VPC and subnet; an application stack needs the VPC ID; a workload needs a security group, IAM role, and database endpoint. When deploying with Infrastructure as Code (IaC), these relationships must be expressed as a clear **dependency graph**.

AWS CloudFormation provides three common mechanisms:

- **Implicit dependency:** CloudFormation infers ordering from `Ref`, `Fn::GetAtt`, and resource reference expressions.
- **Explicit dependency:** `DependsOn` declares ordering relationships that the template cannot infer automatically.
- **Stack composition:** nested stacks and cross-stack references split templates into units with appropriate boundaries, outputs, and lifecycles.

If poorly designed, deployments can suffer from circular dependencies, stack updates locked by imported exports, nested stack rollbacks that are hard to trace, or minor changes forcing manual sequential deployments across many stacks. This lesson focuses on CloudFormation and how AWS CDK represents similar relationships.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the dependency graph and resource create/update/delete order.
2. Distinguish automatically inferred dependencies from `DependsOn`.
3. Split a large template into nested stacks along ownership and lifecycle boundaries.
4. Pass outputs from a nested stack back to the parent using `Fn::GetAtt`.
5. Use CloudFormation Outputs/Exports and `Fn::ImportValue` across independent stacks.
6. Understand Region/account limits, export immutability, and procedures for changing contracts.
7. Identify circular dependencies and choose how to split resources/stacks to break cycles.
8. Design deploy order, rollback, deletion, and migration when stacks depend on each other.
9. Understand how cross-stack references are synthesized by AWS CDK.
10. Test templates and dependency graphs before deploying to AWS.

## 2. Dependency Graph in IaC

A dependency is a relationship stating that **one resource requires another resource to be ready before creation or update**. CloudFormation builds a directed acyclic graph (DAG) from these relationships to determine execution order.

Example of a web application:

~~~mermaid
flowchart TD
    VPC["VPC"] --> SUBNET["Private subnet"]
    VPC --> SG["Application security group"]
    SUBNET --> INSTANCE["Application EC2"]
    SG --> INSTANCE
    ROLE["IAM role"] --> PROFILE["Instance profile"]
    PROFILE --> INSTANCE
    DB["Database"] --> APP["Application configuration"]
    INSTANCE --> APP
~~~

Arrows in the diagram mean **the resource at the start of the arrow must be ready before the resource at the end of the arrow**. This is a logical view; CloudFormation can create independent resources in parallel.

### 2.1. Why Declare Dependencies?

Failing to declare relationships properly can cause:

- A resource to be created before a required network attachment or policy completes.
- An application to receive a non-existent or unready ID/ARN/endpoint.
- Updates to run in an order causing disruption or validation errors.
- A foundational resource to be deleted while another resource still references it.
- A stack to get stuck because an export/import dependency has not been removed.

The dependency graph tells CloudFormation the **order of operations**, but does not guarantee the application is functionally ready. For example, an EC2 instance in `CREATE_COMPLETE` does not mean the application inside the instance passes health checks.

### 2.2. Create, Update, and Delete

CloudFormation creates resources in dependency order: dependencies are created first, and dependent resources are created afterward. During deletion, the order is reversed so dependent resources are deleted before their dependencies.

| Operation | General rule |
| --- | --- |
| Create | Dependencies first, dependents afterward |
| Update | Follows the graph and change type; some changes may trigger replacement |
| Delete | Dependents first, dependencies afterward |
| Rollback | CloudFormation reverts performed changes according to each resource's capability |

A change may require resource replacement, creating a phase where both old and new resources exist. Read the Change Set and the resource's `Update requires` attribute before deploying.

## 3. Implicit Dependencies: Ref, GetAtt, and Sub

CloudFormation automatically infers a dependency when one resource references another resource in its properties.

### 3.1. Ref Example

~~~yaml
Parameters:
  CloudFrontDistributionArn:
    Type: String
    Description: ARN of the distribution allowed to read this bucket

Resources:
  AppBucket:
    Type: AWS::S3::Bucket

  AppBucketPolicy:
    Type: AWS::S3::BucketPolicy
    Properties:
      Bucket: !Ref AppBucket
      PolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: cloudfront.amazonaws.com
            Condition:
              StringEquals:
                AWS:SourceArn: !Ref CloudFrontDistributionArn
            Action: s3:GetObject
            Resource: !Sub "${AppBucket.Arn}/*"
~~~

The `CloudFrontDistributionArn` parameter receives the ARN of the CloudFront distribution allowed to access the bucket. The `AWS:SourceArn` condition restricts the service principal to that distribution rather than allowing any CloudFront distribution.

`Bucket: !Ref AppBucket` creates a clear dependency: the bucket must be created before the bucket policy. `!Sub` referencing `AppBucket.Arn` is also a resource reference, and CloudFormation infers the dependency.

### 3.2. Ref and GetAtt Return Different Values

| Intrinsic function | Typical value |
| --- | --- |
| `Ref` | Default value defined for the resource, typically an ID or name |
| `Fn::GetAtt` | A specific attribute such as ARN, DNS name, endpoint, or output |
| `Fn::Sub` | Interpolated string; references to logical IDs/attributes create dependencies |
| `Fn::Join` | Concatenates strings; elements containing Ref/GetAtt still create dependencies |

Do not assume `Ref` is always an ARN. Check the resource type documentation and the required attribute. For example, `Ref` on an S3 bucket returns the bucket name; the ARN requires `!GetAtt Bucket.Arn`.

### 3.3. VPC and Subnet Example

~~~yaml
Resources:
  AppVpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.40.0.0/16
      EnableDnsSupport: true
      EnableDnsHostnames: true
      Tags:
        - Key: Name
          Value: app-vpc

  AppSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref AppVpc
      CidrBlock: 10.40.10.0/24
      AvailabilityZone: !Select
        - 0
        - !GetAZs ""
~~~

`AppSubnet` depends on `AppVpc` because `VpcId` references the VPC. There is no need to add `DependsOn: AppVpc`; the dependency already exists in the template.

### 3.4. Dependencies in Fn::Sub

`Fn::Sub` can reference:

- Parameter: `${EnvironmentName}`
- Pseudo parameter: `${AWS::Region}`
- Resource logical ID: `${AppBucket}`
- Resource attribute: `${AppBucket.Arn}`
- A variable map passed separately to `Fn::Sub`.

Referencing a logical ID or attribute creates an implicit dependency. If you need to keep a variable-like token literal inside a string, use the escaping syntax supported by Fn::Sub instead of letting CloudFormation interpolate it.

## 4. Explicit Dependencies with DependsOn

`DependsOn` is used when the required ordering **is not expressed through a Ref/GetAtt value**. CloudFormation waits for the specified resource to reach a successful creation state before creating the current resource.

### 4.1. Internet Gateway Attachment Example

A route to an Internet Gateway requires the gateway to be attached to the VPC. The route may reference `InternetGateway` without referencing the attachment resource; therefore, an explicit dependency must be declared:

~~~yaml
Resources:
  AppVpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.50.0.0/16

  InternetGateway:
    Type: AWS::EC2::InternetGateway

  GatewayAttachment:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref AppVpc
      InternetGatewayId: !Ref InternetGateway

  PublicRouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref AppVpc

  DefaultInternetRoute:
    Type: AWS::EC2::Route
    DependsOn: GatewayAttachment
    Properties:
      RouteTableId: !Ref PublicRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway
~~~

Here:

- `GatewayAttachment` inherently depends on the VPC and Internet Gateway via `Ref`.
- `DefaultInternetRoute` references the route table and gateway.
- `DependsOn: GatewayAttachment` enforces attaching the gateway before creating the route.

### 4.2. When to Use DependsOn?

Use `DependsOn` when:

- An API requires a resource attachment/association to finish before the next resource.
- A resource must wait for a policy, permission, or association to be created without a direct property reference.
- A real ordering relationship exists that is not represented in resource properties.

Do not add `DependsOn` to every resource. Unnecessary dependencies make the graph rigid, reduce parallelism, and can introduce unwanted update/delete ordering.

### 4.3. DependsOn Is Not a Readiness Check

`DependsOn` only orchestrates the CloudFormation resource lifecycle. It does not:

- Wait for an application health endpoint to return HTTP 200.
- Wait for a database migration to finish.
- Wait for message consumers to drain a queue.
- Guarantee DNS propagation has completed across all resolvers.

For application readiness, use health checks, deployment controllers, custom resources with appropriate timeouts/retries, or pipeline orchestration after the stack completes.

## 5. What Is a Nested Stack?

A **nested stack** is a CloudFormation stack created and managed as a resource inside a parent stack. The parent stack declares a resource of type `AWS::CloudFormation::Stack`, points to the child template via `TemplateURL`, and passes Parameters.

Nested stacks help split a large template into well-structured parts while keeping a unified overall deployment lifecycle:

~~~mermaid
flowchart TB
    P["Root stack: ProductPlatform"]
    P --> N["Nested stack: Network"]
    P --> S["Nested stack: Security"]
    P --> D["Nested stack: Data"]
    P --> A["Nested stack: Application"]
    N --> V["VPC / Subnets / Routes"]
    S --> I["IAM / Security Groups"]
    D --> R["RDS / DynamoDB"]
    A --> E["ECS / Lambda / API"]
~~~

Example split:

- `network.yaml`: VPC, subnets, route tables, endpoints.
- `security.yaml`: security groups, IAM roles/policies.
- `data.yaml`: database, subnet groups, parameter groups.
- `application.yaml`: ECS services, Lambda functions, API.
- `root.yaml`: orchestrates nested stacks and passes outputs.

### 5.1. When to Use Nested Stacks?

Nested stacks are suitable when:

- The parent template is large and needs splitting by domain/resource group.
- Resources are typically deployed, updated, and rolled back as a single unit.
- The team wants to reuse a child template across multiple parent stacks.
- You need to limit the number of resources or complexity in a single template.
- You want a clear parent-child relationship visible in the CloudFormation console and stack events.

Do not create nested stacks merely to keep every file short. Choose boundaries based on **ownership, lifecycle, failure domain, and change frequency**.

### 5.2. Nested Stacks vs. Independent Stacks

| Aspect | Nested stack | Independent stack |
| --- | --- | --- |
| Ownership | Parent stack manages child stack resource | Has its own lifecycle |
| Deploy | Parent update orchestrates child | Pipeline/Operator deploys separately |
| Passing outputs | `Fn::GetAtt Child.Outputs.Name` | Export/ImportValue or other contract |
| Delete | Parent deletes child under default lifecycle | Must handle dependencies and delete separately |
| Reuse | Child template can be reused | Stacks can be independent by environment/domain |
| Failure | Child failure can cause parent update to fail/roll back | Errors are usually isolated to the deployed stack |

A nested stack is not a free-form mechanism for sharing resources across multiple parents. A child stack resource belongs to a specific parent; do not try to manage the same resource from two stacks.

## 6. Creating Nested Stacks and Passing Parameters

The parent stack references the child template via `TemplateURL`. Templates are usually stored in S3; for production pipelines, use immutable object keys/versions or artifacts with checksums so the parent always points to the exact tested version.

### 6.1. Child Template: network.yaml

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Network resources for the product platform

Parameters:
  VpcCidr:
    Type: String
    Default: 10.60.0.0/16

Resources:
  AppVpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: !Ref VpcCidr
      EnableDnsSupport: true
      EnableDnsHostnames: true
      Tags:
        - Key: Name
          Value: product-platform-vpc

  PrivateSubnetA:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref AppVpc
      CidrBlock: 10.60.10.0/24
      AvailabilityZone: !Select
        - 0
        - !GetAZs ""

Outputs:
  VpcId:
    Description: VPC identifier for dependent stacks
    Value: !Ref AppVpc

  PrivateSubnetAId:
    Description: Private subnet identifier
    Value: !Ref PrivateSubnetA
~~~

The child template should only output values that other stacks truly need. Do not export every resource attribute; outputs are the template's **public contract**.

### 6.2. Parent Template: root.yaml

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Root stack for the product platform

Parameters:
  NetworkTemplateUrl:
    Type: String
    Description: Immutable S3 URL for the network template

  ApplicationTemplateUrl:
    Type: String
    Description: Immutable S3 URL for the application template

Resources:
  NetworkStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: !Ref NetworkTemplateUrl
      TimeoutInMinutes: 20
      Parameters:
        VpcCidr: 10.60.0.0/16
      Tags:
        - Key: Component
          Value: network

  ApplicationStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: !Ref ApplicationTemplateUrl
      Parameters:
        VpcId: !GetAtt NetworkStack.Outputs.VpcId
        PrivateSubnetId: !GetAtt NetworkStack.Outputs.PrivateSubnetAId

Outputs:
  PlatformVpcId:
    Value: !GetAtt NetworkStack.Outputs.VpcId

  ApplicationEndpoint:
    Value: !GetAtt ApplicationStack.Outputs.ApplicationEndpoint
~~~

`!GetAtt NetworkStack.Outputs.VpcId` creates a dependency between `ApplicationStack` and `NetworkStack`. CloudFormation knows it must create the network nested stack before passing the output to the application stack. There is no need to add `DependsOn: NetworkStack` again.

### 6.3. Child Template: application.yaml

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Application resources that consume network outputs

Parameters:
  VpcId:
    Type: AWS::EC2::VPC::Id
  PrivateSubnetId:
    Type: AWS::EC2::Subnet::Id

Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Application security group
      VpcId: !Ref VpcId
      SecurityGroupEgress:
        - IpProtocol: "-1"
          CidrIp: 0.0.0.0/0

  AppNetworkInterface:
    Type: AWS::EC2::NetworkInterface
    Properties:
      SubnetId: !Ref PrivateSubnetId
      GroupSet:
        - !Ref AppSecurityGroup
      Description: Example interface proving subnet and security group dependencies

Outputs:
  NetworkInterfaceId:
    Value: !Ref AppNetworkInterface

  ApplicationEndpoint:
    Description: Placeholder output for the application endpoint
    Value: !Sub "https://example.invalid/${AWS::Region}/app"
~~~

This template illustrates receiving VPC/subnet IDs. In a real application, the subnet would be attached to an ECS service, EC2 network interface, or Lambda VPC configuration; the security group needs least-privilege ingress/egress for the workload. The placeholder endpoint does not represent a running service.

### 6.4. TemplateURL and Artifact Management

- Templates must be uploaded before the parent stack creates or updates a nested stack.
- The parent role needs permission to read template artifacts; bucket policies/KMS key policies must also allow it.
- Point to versioned, immutable object keys so deployments are reproducible.
- Do not overwrite the same key without recording the deployed content/version.
- Retain artifacts long enough to roll back or redeploy previous versions.
- Check template size limits and CloudFormation's access permissions when fetching templates.

If the template resides in a private S3 bucket, CloudFormation must be able to access the object via a supported mechanism. A URL that opens on a developer's machine does not prove the CloudFormation service has permission to fetch it.

## 7. Nested Stack Outputs and GetAtt

A nested stack resource returns stack attributes, including the child template's outputs. The parent accesses them using the form:

~~~yaml
!GetAtt NestedStackLogicalId.Outputs.OutputKey
~~~

Example:

~~~yaml
Parameters:
  VpcId:
    Type: String

Resources:
  AppStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: https://templates.example.invalid/app.yaml
      Parameters:
        VpcId: !Ref VpcId

  NetworkStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: https://templates.example.invalid/network.yaml

  WorkerStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: https://templates.example.invalid/worker.yaml
      Parameters:
        VpcId: !GetAtt NetworkStack.Outputs.VpcId
        ApplicationEndpoint: !GetAtt AppStack.Outputs.ApplicationEndpoint
~~~

`WorkerStack` depends on both `NetworkStack` and `AppStack`. Therefore, CloudFormation creates those two stacks first before creating the worker stack.

### 7.1. Outputs Are Strings

CloudFormation Outputs have string values. If a child stack needs to output multiple subnet IDs, they can be joined by commas and passed to a list parameter according to schema:

~~~yaml
Outputs:
  PrivateSubnetIds:
    Value: !Join
      - ","
      - - !Ref PrivateSubnetA
        - !Ref PrivateSubnetB
~~~

The parent can pass the output string to a child parameter declared as `List<AWS::EC2::Subnet::Id>` if the value is a valid comma-delimited list. Verify parameter types and intrinsic functions in the actual template; do not assume every output automatically becomes a native list.

### 7.2. Passing Parameters Across Layers

When a parent passes parameters down to a child:

- Parameter types, allowed values, and constraints must match the contract.
- Default values should not mask a parent forgetting to pass a required value.
- Avoid passing secrets directly through nested stack parameters when Secrets Manager/SSM dynamic references can be used.
- Never put credentials or secrets into Outputs; outputs can appear in the CloudFormation console/API and deployment logs.

### 7.3. Keep Output Contracts Small and Stable

A network stack might export VPC ID, subnet IDs, and security group IDs. There is no need to export all logical resource names or internal attributes. A small contract allows the child stack to be refactored without forcing consumer changes.

Name outputs meaningfully according to the consumer contract, such as `VpcId`, `PrivateSubnetIds`, `DatabaseEndpoint`, rather than `Value1` or `ResourceA`.

## 8. Cross-Stack References Between Independent Stacks

A **cross-stack reference** shares an output between independent CloudFormation stacks. The providing stack declares `Export`; the consuming stack uses `Fn::ImportValue`.

Unlike nested stacks, these two stacks have independent lifecycles. CloudFormation does not treat them as parent/child, yet export/import creates an AWS-managed dependency contract.

### 8.1. Providing Stack: network-stack.yaml

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"

Resources:
  SharedVpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.70.0.0/16
      EnableDnsSupport: true
      EnableDnsHostnames: true

Outputs:
  SharedVpcId:
    Description: VPC ID consumed by application stacks
    Value: !Ref SharedVpc
    Export:
      Name: !Sub "${AWS::StackName}-SharedVpcId"
~~~

Export names must be unique within the account and Region. Include stack name/environment/component in the export name to prevent collisions across multiple environments.

### 8.2. Consuming Stack: application-stack.yaml

~~~yaml
Parameters:
  NetworkStackName:
    Type: String
    Description: Name prefix used by the network stack export

Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Application access in shared VPC
      VpcId:
        Fn::ImportValue:
          Fn::Sub: "${NetworkStackName}-SharedVpcId"
~~~

The consuming stack does not create a new VPC. It imports the value exported by the network stack. The stack must be in the **same AWS account and same Region** as the stack providing the export.

### 8.3. Export Names Must Be Stable

Do not arbitrarily rename an export after consumers have imported it. The export name is part of the contract; changing it is equivalent to breaking an interface between stacks.

A useful convention:

~~~text
<environment>-<domain>-<contract>-<version>

prod-network-vpc-id-v1
staging-network-private-subnets-v1
dev-security-app-sg-id-v1
~~~

A version in the export name helps when parallel migration is required: create export v2, move consumers to v2, then remove v1 once no importers remain.

## 9. Limitations and Lifecycle of ImportValue

`Fn::ImportValue` has important limitations:

1. Imports only work between stacks in the **same account and same Region**.
2. Export names must be unique within the account/Region.
3. A stack exporting a value cannot be deleted while another stack imports that value.
4. An exported output value cannot be removed or modified while dependent importers exist.
5. ImportValue only works with static export names per supported intrinsic function limits; do not use a value depending on a dynamic resource as an export name.

This is why cross-stack references must be treated as an API contract with a lifecycle, not just a way to fetch a string.

### 9.1. What Happens When You Want to Change the VPC?

Suppose:

~~~text
NetworkStack exports: prod-network-vpc-id
ApplicationStack imports: prod-network-vpc-id
WorkerStack imports: prod-network-vpc-id
~~~

If you delete or change the export immediately, CloudFormation rejects the update because consumers still use it. Consumers must migrate first before removing the old export.

### 9.2. Safe Export Change Procedure

~~~mermaid
flowchart TD
    OLD["Export v1 is currently imported by consumers"]
    NEW["Create export v2 in parallel"]
    APP["Update consumers to v2"]
    VERIFY["Verify no v1 importers remain"]
    REMOVE["Remove export v1"]
    OLD --> NEW --> APP --> VERIFY --> REMOVE
~~~

Sequence:

1. Keep export v1 unchanged.
2. Add output/export v2 with a new name without modifying the v1 value currently imported.
3. Deploy the provider stack so v1 and v2 coexist.
4. Update each consumer to import v2.
5. Verify no stacks still import v1.
6. Remove output/export v1 from the provider stack.

This follows an **expand → migrate → contract** pattern. When changing an actual VPC/resource, you also need a plan for shifting workloads/network routes and independent rollbacks; changing only the export string does not migrate running resources.

## 10. Circular Dependencies and Breaking Cycles

The dependency graph must be a DAG. If A depends on B and B depends on A, CloudFormation cannot determine a valid creation order.

~~~mermaid
flowchart LR
    A["Resource A"] --> B["Resource B"]
    B --> A
~~~

Common examples:

- Security group A needs security group B in an ingress rule.
- Security group B also needs security group A in an ingress rule.
- Two stacks import each other's outputs.
- A child nested stack references an output from its parent in a way that creates a reverse dependency loop.
- A resource policy references the ARN of a resource that itself requires the policy to be created.

### 10.1. Security Group Circular Dependency Example

Suppose two workload groups need to allow ingress from each other:

~~~yaml
Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Application security group
      VpcId: !Ref AppVpc
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 8080
          ToPort: 8080
          SourceSecurityGroupId: !Ref WorkerSecurityGroup

  WorkerSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Worker security group
      VpcId: !Ref AppVpc
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 9000
          ToPort: 9000
          SourceSecurityGroupId: !Ref AppSecurityGroup
~~~

Each security group references the other inside its resource definition. This can create a circular dependency because each group needs the other before being created.

### 10.2. Splitting Ingress Rules into Separate Resources

Create both security groups first, then create separate ingress rules:

~~~yaml
Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Application security group
      VpcId: !Ref AppVpc

  WorkerSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Worker security group
      VpcId: !Ref AppVpc

  AppIngressFromWorker:
    Type: AWS::EC2::SecurityGroupIngress
    Properties:
      GroupId: !Ref AppSecurityGroup
      IpProtocol: tcp
      FromPort: 8080
      ToPort: 8080
      SourceSecurityGroupId: !Ref WorkerSecurityGroup

  WorkerIngressFromApp:
    Type: AWS::EC2::SecurityGroupIngress
    Properties:
      GroupId: !Ref WorkerSecurityGroup
      IpProtocol: tcp
      FromPort: 9000
      ToPort: 9000
      SourceSecurityGroupId: !Ref AppSecurityGroup
~~~

Both security groups can be created independently; ingress resources are created after both groups exist. Splitting rules into separate resources breaks the circular dependency in this example.

### 10.3. Resolving Stack-Level Circular Dependencies

- Choose one stack as the **provider** of shared infrastructure; the other stack only consumes outputs.
- Avoid bidirectional export/import between two stacks.
- Extract shared resources into a foundation stack with a clear lifecycle.
- If two resources need each other's IDs, place them in the same stack or extract the association/rule into a third resource.
- Use Parameters/Outputs unidirectionally; do not create a child-to-parent contract looping back to the parent.
- If the dependency is truly runtime discovery, consider service discovery/a configuration store instead of deployment-time imports.

You cannot resolve a circular dependency by adding more `DependsOn` attributes; explicit dependencies also add graph edges and can worsen cycles.

## 11. Deploy Order for Multiple Stacks

When using independent stacks, the pipeline needs to understand dependency order. CloudFormation only manages dependencies within a single stack and export/import contracts; the pipeline is responsible for orchestrating multi-stack deployments.

Example:

~~~mermaid
flowchart TD
    NET["Network stack"] --> SEC["Security stack"]
    NET --> DATA["Data stack"]
    SEC --> APP["Application stack"]
    DATA --> APP
    APP --> OBS["Observability stack"]
~~~

A sensible deploy order:

1. Network foundation.
2. Security/shared identity.
3. Data layer.
4. Application.
5. Observability/integration resources depending on application outputs.

Independent stacks can run in parallel if the pipeline is certain they have no hidden dependencies. Do not order stacks merely by stack name or file order.

### 11.1. Deploying with Change Sets

Before executing:

- Validate templates and parameters.
- Create a Change Set for each stack.
- Review resource additions, modifications, replacements, and deletions.
- Check export/import dependencies and nested stack changes.
- Verify the impact of replacing a VPC, subnet, database, or IAM role.
- Execute in dependency order; verify stack status before moving to the next step.

A Change Set shows what CloudFormation intends to change, but does not replace IAM/security review and does not perfectly predict all runtime behavior.

### 11.2. Multi-Stack Rollback

CloudFormation rolls back within the scope of the stack currently being updated. With multiple independent stacks, the pipeline might deploy the provider successfully while the consumer fails. Determine:

- Can the provider safely keep the new output without impact?
- Can the consumer roll back to the previous version?
- Can the new export be retained temporarily to support rollback?
- Are there irreversible resource replacements or data migrations?
- Is a forward-fix needed rather than rolling back database schema/data?

Do not assume rolling back one stack automatically rolls back previously deployed stacks.

### 11.3. Deploy Order When Changing Contracts

When adding a new output: the provider typically deploys first, then the consumer. When removing an old output: the consumer must stop importing first, then the provider removes the export. The two scenarios have opposite orderings; the pipeline must model the specific dependency direction.

## 12. Nested Stack Updates, Rollbacks, and Deletions

Nested stacks have lifecycles tied to their parent. When the parent is updated, CloudFormation can update the nested stack's template/parameters; a child stack failure can fail the parent operation.

### 12.1. When a Child Template Changes

When modifying a child template:

1. Validate the child template.
2. Upload the new artifact with a clear key/version.
3. Update `TemplateURL` in the parent or update the parameter pointing to the new artifact.
4. Create a Change Set for the parent to inspect the nested stack update.
5. Deploy the parent and monitor stack events for both parent and child.

Do not overwrite a template artifact already used by a deployment if you want reproducibility. Use versioned object keys or artifact digests so you know exactly which content the parent deployed.

### 12.2. Tracing Nested Stack Failures

When a parent stack reports `UPDATE_ROLLBACK_IN_PROGRESS`, the root cause may lie inside a child stack. Check:

- Parent stack events to identify the failing nested stack logical resource.
- Child stack events to find the specific resource and status reason.
- IAM roles, S3 `TemplateURL` access, parameter validation, and quotas.
- Resource replacement/deletion policies.
- Concurrent or locked stack operations.

Read events by timestamp and resource status reason; do not look only at the root stack's final status.

### 12.3. Delete and Retain

By default, deleting a parent stack deletes nested stack resources according to the CloudFormation lifecycle. For data that must be kept, choose an intentional retention strategy:

- Use `DeletionPolicy: Retain` on appropriate data resources such as buckets/tables/databases when you want to preserve them after stack deletion.
- Use `UpdateReplacePolicy: Retain` when replacement must not delete the old resource.
- Establish a process to transfer ownership/import resources if continued management is needed after the parent is deleted.

Do not apply Retain mechanically to every nested stack. Retain can leave resources outside the parent's management lifecycle; you must have an inventory, owner, and cleanup/recovery plan.

### 12.4. Nested Stacks and Data Rollback

CloudFormation can roll back resource configuration, but it does not automatically reverse data changes created by migrations, Lambda custom resources, or application deployments. Database schema migrations require backward-compatible expand/contract patterns, backups, and separate recovery strategies.

## 13. AWS CDK and Cross-Stack References

AWS CDK allows writing infrastructure in a programming language and synthesizing into CloudFormation templates. When a construct in stack A references a resource from stack B, CDK can automatically generate Outputs/Exports and ImportValue if both stacks have compatible environments.

### 13.1. CDK Cross-Stack Reference Example

~~~java
public class NetworkStack extends Stack {
    public final IVpc vpc;

    public NetworkStack(
            Construct scope,
            String id,
            StackProps props) {
        super(scope, id, props);

        this.vpc = Vpc.Builder.create(this, "Vpc")
            .maxAzs(2)
            .natGateways(1)
            .build();
    }
}

public class ApplicationStack extends Stack {
    public ApplicationStack(
            Construct scope,
            String id,
            NetworkStack network,
            StackProps props) {
        super(scope, id, props);

        Cluster cluster = Cluster.Builder.create(this, "Cluster")
            .vpc(network.vpc)
            .build();
    }
}
~~~

This example illustrates CDK for Java; imports and props are omitted for brevity. `ApplicationStack` uses the VPC owned by `NetworkStack`. During synthesis, CDK generates the necessary cross-stack reference using CloudFormation mechanisms.

### 13.2. Environment Requirements

Automatic cross-stack references work best when both stacks have explicit, compatible accounts and Regions. For environment-agnostic stacks or stacks in different accounts/Regions, CDK cannot automatically generate CloudFormation ImportValue across those boundaries.

For cross-account/Region scenarios, choose an appropriate contract and value-passing mechanism, such as:

- Pipeline passing parameters at deploy time.
- Shared SSM Parameter Store or configuration store with proper permissions and scoping.
- AWS Resource Access Manager (RAM) for supported resource types.
- DNS/service discovery or runtime APIs instead of deployment-time references.

Select the mechanism based on data type, security boundary, and lifecycle; do not assume every resource ID can be shared via RAM or Parameter Store.

### 13.3. CDK NestedStack

CDK provides the `NestedStack` construct to group resources into a nested CloudFormation stack. It is useful when a template approaches size/resource limits or needs component-level organization; it is not a default pattern for turning every small construct into a stack.

Cross-stack references between independent CDK stacks and references between nested stacks have different semantics. Inspect synthesized templates to see the actual `AWS::CloudFormation::Stack` resources, Outputs, and ImportValue calls.

### 13.4. Caution When Refactoring CDK Cross-Stack References

CDK can auto-generate export names. If you change construct ownership or remove a reference, the synthesized template may try to delete an export currently imported by another stack. When this happens:

1. Synth both provider and consumer.
2. Compare exports/imports before and after.
3. Keep the old export temporarily if consumers have not migrated yet.
4. Deploy in expand → migrate → contract order.
5. Do not hand-edit synthesized templates as a long-term solution; fix the CDK source and inspect the new output.

## 14. Distinguishing Nested Stacks, Cross-Stack References, and Modules

These concepts are often used together but solve different problems:

| Mechanism | Goal | Lifecycle relationship | How values are shared |
| --- | --- | --- | --- |
| **Nested stack** | Split one deployment into child templates | Parent manages child | `Fn::GetAtt` child Outputs |
| **Cross-stack reference** | Separate independent stacks that need shared outputs | Each stack has its own lifecycle; export/import locks the contract | `Export` and `Fn::ImportValue` |
| **CloudFormation module** | Package reusable resource types/template patterns | Module is used inside a template; does not create a parent-child stack merely by being a module | Resource properties/outputs per module schema |
| **CDK construct** | Reuse abstractions in source code | Belongs to the stack containing the construct | References in the construct tree and synthesized template |
| **CDK Stage** | Group stacks into a unit in a pipeline/application | Pipeline deploys per stage | Cross-stack references still follow CloudFormation rules |

Do not confuse a CloudFormation module with a nested stack. A module is a registered abstraction/resource type used inside a template; a nested stack is a stack resource with its own child template and lifecycle.

## 15. Terraform: Dependencies and Module Outputs (Comparison)

In Terraform, the graph is also inferred from references:

~~~hcl
resource "aws_vpc" "app" {
  cidr_block = "10.80.0.0/16"
}

resource "aws_subnet" "private" {
  vpc_id     = aws_vpc.app.id
  cidr_block = "10.80.10.0/24"
}
~~~

`aws_subnet.private` references `aws_vpc.app.id`, so Terraform automatically infers the dependency. Only use `depends_on` when there is a behavioral dependency that cannot be expressed through a direct reference.

A module can expose an output:

~~~hcl
output "vpc_id" {
  value = aws_vpc.app.id
}
~~~

A consuming module receives outputs through the module call. If state lives in another workspace/backend, remote state or data sources can be used as designed, though state read permissions and contracts/versions must be managed. Terraform remote state is not CloudFormation Export/ImportValue and has its own semantics.

This section is only for conceptual comparison; the CloudFormation/CDK examples above are the core focus of this lesson.

## 16. Security and Ownership When Splitting Stacks

Splitting stacks is an ownership decision. Each stack should have a clear owner, deployment permissions, and resource scope.

### 16.1. Least Privilege for Deploy Roles

- Use separate deployment roles per environment or pipeline boundary.
- Grant permissions only for the required resource types and scopes.
- Restrict `iam:PassRole` to approved application roles.
- Scope S3 read permissions for template artifacts and KMS key usage permissions.
- Do not grant application pipelines permission to delete shared network/data resources unless required.
- Use SCPs/permission boundaries to block actions outside sandbox/production guardrails.

A stack dependency is not a security boundary. An application stack importing a VPC ID does not mean the application role is allowed to modify the VPC; IAM permissions determine allowed actions.

### 16.2. Outputs Are Not a Secret Store

Never export values such as:

- Database passwords.
- API keys or access tokens.
- Private keys or certificate private material.
- Session tokens or long-lived AWS credentials.

CloudFormation Outputs can be read via API/console and may appear in pipeline logs. For secrets, use Secrets Manager or Systems Manager Parameter Store dynamic references and grant appropriate read permissions to the workload.

### 16.3. Template Artifacts and Nested Stacks

- Encrypt the S3 bucket holding templates according to organizational policy.
- Restrict upload/overwrite permissions on template artifacts.
- Keep immutable artifacts and checksums for deployment traceability.
- Never place secrets in literal templates, Metadata, Outputs, or unprotected Parameters.
- Verify the CloudFormation execution role has permission to read artifacts and required KMS keys.

### 16.4. Stack Policy and Termination Protection

These mechanisms serve different purposes:

| Mechanism | What does it protect? | Limitations |
| --- | --- | --- |
| **Stack policy** | Blocks certain update actions on protected resources | Does not replace IAM; does not block all deletes/console actions |
| **Termination protection** | Prevents accidental deletion of the entire stack | Does not prevent updates or resource-level changes |
| **IAM/SCP** | Restricts who can call which API/action | Requires accurate policies and permission testing |
| **DeletionPolicy/Retain** | Defines how resources are handled on stack delete/replacement per policy | Retained resources can lose stack ownership |

For network/data foundation stacks, consider termination protection and restricted deletion permissions. For data-holding resources, consider DeletionPolicy/backups/retention per recovery requirements.

## 17. Testing Dependencies and Stack Contracts

A template that parses cleanly does not guarantee a valid dependency graph. You must verify structure, contracts, lifecycles, and deployment behavior.

### 17.1. Testing Layers

| Layer | Tool/Measure | What to verify |
| --- | --- | --- |
| Syntax/schema | `aws cloudformation validate-template`, `cfn-lint` | YAML/JSON, intrinsic functions, resource properties |
| Policy | CloudFormation Guard or policy-as-code | Security baseline, tags, encryption, public access |
| Dependency | Graph review, cfn-lint, Change Set | Implicit/explicit edges, cycles, replacements |
| Contract | Validate outputs/parameters/exports | Output keys, export names, types, and consumers |
| Integration | Deploy sandbox stack | Nested stack creation, permissions, runtime resource behavior |
| Lifecycle | Update, rollback, delete tests | Export locks, Retain, resource cleanup, and recovery |
| Drift | CloudFormation drift detection | Out-of-IaC changes for drift-supported resources |

### 17.2. Validate Template

AWS CLI can perform basic template checks:

~~~bash
aws cloudformation validate-template \
  --template-body file://root.yaml \
  --region ap-southeast-1
~~~

`validate-template` checks structure and template elements supported by the API; it does not prove all runtime permissions, service quotas, cross-stack contracts, or application readiness are correct.

### 17.3. Using cfn-lint

~~~bash
cfn-lint root.yaml network.yaml application.yaml
~~~

`cfn-lint` detects many schema/resource property errors and best-practice issues. Pin the lint tool version in CI for reproducible results; read rule findings instead of ignoring all warnings.

### 17.4. Using Change Sets Before Updating

~~~bash
aws cloudformation create-change-set \
  --stack-name product-network \
  --change-set-name review-network-update \
  --template-body file://network-stack.yaml \
  --change-set-type UPDATE \
  --region ap-southeast-1

aws cloudformation describe-change-set \
  --stack-name product-network \
  --change-set-name review-network-update \
  --region ap-southeast-1
~~~

These commands illustrate an existing stack with properly configured parameters/capabilities. If the template requires IAM capabilities or parameters, supply the appropriate options per the template. Do not execute the Change Set until resource replacements/deletions and dependency impact have been reviewed.

### 17.5. Finding Export Consumers

~~~bash
aws cloudformation list-imports \
  --export-name prod-network-SharedVpcId \
  --region ap-southeast-1
~~~

`list-imports` identifies which stacks currently import an export name. Run it before deleting/changing an export; verify you are targeting the right account and Region.

### 17.6. Testing Lifecycle, Not Just Create

A stack contract test should verify:

1. Create the provider stack and consumer stack.
2. Confirm the consumer receives the expected output.
3. Update the provider in a non-contract-breaking way.
4. Test changing the contract in a sandbox to confirm importer locks are caught.
5. Switch consumers to export v2.
6. Remove export v1 once no imports remain.
7. Delete the consumer before the provider.
8. Verify retained resources have an owner and recovery path.

Never run destructive deletion or replacement tests on shared production stacks.

## 18. Case Study: Network Foundation and Application Stacks

### 18.1. Context

A platform hosts multiple applications in the same AWS account/Region:

~~~text
Network foundation:
  VPC, public/private subnets, route tables, VPC endpoints

Security foundation:
  Shared security groups, baseline IAM policies

Application A:
  ECS service, ALB, application task role

Application B:
  Lambda functions, API Gateway, execution role
~~~

Networking changes infrequently; applications deploy often. Therefore, networking and applications can be independent stacks sharing outputs via a unidirectional contract.

### 18.2. Dependency Architecture

~~~mermaid
flowchart TD
    N["Network foundation stack"]
    S["Security foundation stack"]
    A["Application A stack"]
    B["Application B stack"]
    N --> A
    N --> B
    S --> A
    S --> B
~~~

The network stack exports VPC/subnet IDs. The security stack exports security group IDs or role ARNs when sharing is truly needed. Application stacks import required outputs and do not own foundational resources.

### 18.3. Initial Deployment Procedure

1. Upload and validate templates.
2. Deploy the network foundation.
3. Deploy the security foundation.
4. Verify exports and outputs.
5. Deploy applications A/B via pipeline; both apps can run in parallel if independent.
6. Run smoke tests and verify resources in the right account/Region.

### 18.4. Adding a New Private Subnet

Suppose the network team wants to add a subnet:

- Update the network stack to create the new subnet.
- Add a versioned output or update the output contract if consumers need the new subnet list.
- If the export is currently imported and its value must change, use a contract migration instead of editing the locked output directly.
- Update application stacks consumer by consumer.
- Verify route table, network ACL, security group, and VPC endpoint behavior.

If the `PrivateSubnetIds` output is a comma-delimited list and the list changes, CloudFormation will not allow changing the exported value while importers remain. Use export v2 or move to a different contract/configuration store when independent updates are needed.

### 18.5. Deleting an Application

When deleting application A:

1. Stop traffic or drain the workload according to the deployment plan.
2. Delete the application stack.
3. Verify application resources and dependencies have been removed.
4. Keep the network/security foundation if other applications still use it.
5. Delete foundational exports/resources only after no consumers remain.

Do not delete the network stack simply because one application stack is retired.

## 19. Troubleshooting Dependencies and Cross-Stack References

| Symptom | Common cause | How to investigate |
| --- | --- | --- |
| **Circular dependency** | Two resources reference each other or `DependsOn` creates a backward edge | Draw the graph; extract association/ingress/policy into a third resource |
| **Export cannot be deleted** | A stack still imports the export | Run `list-imports`, migrate consumers, then delete |
| **Export cannot be modified** | Exported output value is currently imported | Add a new export version and migrate consumer by consumer |
| **No export named ... found** | Wrong name, wrong account/Region, or provider not yet deployed | Compare exact Export Name and deploy order |
| **Nested stack template URL error** | Template not uploaded, wrong URL, or CloudFormation lacks read permission | Check S3 object, role, bucket policy, and KMS |
| **Nested stack parameter validation failed** | Parent passes wrong type/value or child parameter constraints mismatch | Compare Parameters/AllowedValues and stack events |
| **UPDATE_ROLLBACK_IN_PROGRESS** | Resource update or child stack failed | Open parent events, then inspect child stack events |
| **Resource already exists** | Another stack or out-of-IaC action created a resource with the same name | Verify ownership, import/adopt resource per procedure |
| **Delete stack blocked** | Export importer, termination protection, or resource dependency remains | Check imports, protection, retained resources, and resource events |
| **Change Set shows replacement** | Property change requires replacement | Evaluate downtime, data migration, and `UpdateReplacePolicy` |
| **CDK export removal failure** | Refactor caused synth to remove an export still used by another stack | Compare synthesized templates; keep export temporarily and migrate consumers |
| **Dependency order appears wrong** | Missing implicit reference or necessary explicit dependency | Inspect resource properties and `DependsOn`; distinguish resource completion from app readiness |

### 19.1. Quick Investigation Workflow

1. Identify the failing stack operation and logical resource.
2. Read CloudFormation Events by timestamp, starting from the first error.
3. For nested stacks, open child stack events.
4. Inspect dependency edges, Parameters, Outputs, and export/import names.
5. Check account/Region, IAM execution role, artifact access, and quotas.
6. Create a Change Set after fixing to preview impact before executing.

Do not fix only the final status. Find the earliest error in the event stream; subsequent errors are often consequences of rollback.

## 20. Reinforcement Exercises

### Exercise 1 — Implicit Dependency

An EC2 instance has the property `SubnetId: !Ref PrivateSubnet`. Does CloudFormation need `DependsOn: PrivateSubnet`?

**Hint:** No. `Ref` already creates an implicit dependency.

### Exercise 2 — When to Use DependsOn?

A route references an Internet Gateway ID but must wait for the gateway attachment to complete. What relationship should be expressed?

**Hint:** Use `DependsOn` referencing the VPC gateway attachment because the route does not reference the attachment resource.

### Exercise 3 — Nested Stack Output

A parent stack needs the VPC ID created by a child network stack. Which intrinsic function should be used?

**Hint:** `Fn::GetAtt` targeting the `Outputs.VpcId` attribute of the nested stack resource.

### Exercise 4 — Export/Import Region

A network stack in `ap-southeast-1` exports a VPC ID. Can an application stack in `ap-southeast-2` use `Fn::ImportValue`?

**Hint:** No. CloudFormation exports/imports only work within the same account and Region.

### Exercise 5 — Export Currently Imported

You want to delete export v1, yet two application stacks still import it. What is the safe sequence?

**Hint:** Create export v2, deploy the provider, migrate consumers to v2, verify no v1 imports remain, and then delete v1.

### Exercise 6 — Circular Security Groups

Two security groups reference each other in ingress rules. How do you break the dependency cycle?

**Hint:** Create both groups first; declare each ingress rule as a separate `AWS::EC2::SecurityGroupIngress` resource.

### Exercise 7 — Choosing Nested Stack vs. Independent Stack

A network foundation is used by multiple application teams and deployed on its own schedule. Should you choose a nested stack or an independent stack?

**Hint:** An independent stack with unidirectional exports/contracts is usually a better fit because networking has separate ownership and lifecycle.

### Exercise 8 — TemplateURL

A parent stack updates, yet the nested stack reports it cannot fetch the template. List three things to check.

**Hint:** S3 object/URL, read permissions of the CloudFormation execution role, bucket/KMS policy, and artifact version.

### Exercise 9 — CDK Cross-Stack Ref

A CDK stack in account A/Region X directly references a VPC resource in a stack in account B/Region Y. Will CDK automatically create `Fn::ImportValue`?

**Hint:** No. Use an explicit cross-account/Region integration contract such as pipeline parameters, a configuration store, or supported resource sharing.

### Exercise 10 — Delete Order

An application stack imports a VPC ID from a network stack. Which stack should be deleted first?

**Hint:** The application consumer first, then the network provider once no imports remain.

### Exercise 11 — Retain

A parent stack is deleted, yet a database must be preserved. Which mechanism and risks should be considered?

**Hint:** `DeletionPolicy: Retain`; afterward, you must define ownership, backup/recovery, and how to manage the retained resource.

### Exercise 12 — Change Set

A Change Set shows that changing a subnet CIDR requires replacement. What questions must be reviewed before deploying?

**Hint:** Will the new subnet change IDs, will workloads/network routes/security rules be disrupted, what are the data/ENI dependencies, and what are the rollback and migration plans?

## 21. Production Design Checklist

- [ ] Dependency graph has no cycles; implicit edges are formed via Ref/GetAtt/Sub where appropriate.
- [ ] `DependsOn` is added only when a real ordering constraint cannot be expressed via intrinsic references.
- [ ] Dependency ordering is not used as an application readiness/health check.
- [ ] Nested stacks are split by ownership, lifecycle, failure domain, and change frequency.
- [ ] Parent/child Parameters have clear types, constraints, and defaults.
- [ ] Child Outputs are small, stable, and contain no secrets.
- [ ] TemplateURL points to an immutable artifact with checksum/version and appropriate read permissions.
- [ ] Cross-stack references have a clear provider/consumer direction.
- [ ] Export names are unique, stable, and follow a naming convention by environment/domain/version.
- [ ] No attempts to import cross-account or cross-Region via Fn::ImportValue.
- [ ] An expand → migrate → contract migration plan exists before changing an export in active use.
- [ ] Pipeline deploys stacks in dependency order and supports Change Set reviews.
- [ ] Rollback is designed per stack; no assumption of multi-stack transactions.
- [ ] Nested stack events and child stack failures have an investigation runbook.
- [ ] Stack policies, termination protection, DeletionPolicy, and IAM/SCPs are used appropriately.
- [ ] Secrets live in Secrets Manager/SSM; no secrets are published in Outputs.
- [ ] Templates are validated with CloudFormation/cfn-lint/policy checks.
- [ ] Integration tests exist in a sandbox for IAM, networking, quotas, and critical lifecycles.
- [ ] A drift detection/ownership process handles out-of-IaC changes.
- [ ] Retained resources have an owner, retention, backup, and cleanup plan.

## 22. Key Takeaways

1. **The dependency graph** tells CloudFormation the create/update/delete order; independent resources can be processed in parallel.
2. **Implicit dependencies** are typically inferred from `Ref`, `Fn::GetAtt`, and `Fn::Sub`; use `DependsOn` for ordering relationships that cannot be expressed through references.
3. **Nested stacks** split a deployment into parent/child templates with linked lifecycles; the parent passes parameters and reads child outputs via `Fn::GetAtt`.
4. **Cross-stack references** use `Export` and `Fn::ImportValue` for independent stacks in the same account/Region. An export currently being imported cannot be deleted or modified.
5. When changing a contract, use an **expand → migrate → contract** migration: add the new version, switch consumers, and only then remove the old version.
6. Circular dependencies require restructuring the graph; adding `DependsOn` does not break cycles.
7. AWS CDK can automatically create cross-stack exports/imports in compatible environments; review synthesized templates when refactoring.
8. Stack boundaries are decisions about ownership, security, and lifecycle; do not split stacks merely to split files.

Good stack design enables predictable deployment order, reuse of shared infrastructure, smaller blast radius for changes, and safe contract management throughout the system's lifecycle.

### Official Documentation

- [AWS CloudFormation User Guide](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/Welcome.html) — CloudFormation concepts and operations.
- [DependsOn attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-dependson.html) — explicit resource dependencies.
- [Ref intrinsic function](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-ref.html) — parameter/resource references.
- [Fn::GetAtt intrinsic function](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-getatt.html) — retrieving resource attributes.
- [Fn::Sub intrinsic function](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-sub.html) — string substitution and references.
- [Nested stacks](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-nested-stacks.html) — creating and managing nested stacks.
- [Outputs section](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html) — outputs and exports.
- [Fn::ImportValue](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-importvalue.html) — cross-stack import constraints.
- [CloudFormation stack updates](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks.html) — updates, Change Sets, and lifecycle.
- [CloudFormation stack policies](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html) — protecting resources during updates.
- [CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html) — detecting out-of-template changes.
- [AWS CDK guide](https://docs.aws.amazon.com/cdk/v2/guide/home.html) — CDK constructs, stacks, and synthesis.
- [AWS CDK cross-stack references](https://docs.aws.amazon.com/cdk/v2/guide/resources.html#resources_cross_stack) — references across stacks.
- [cfn-lint](https://github.com/aws-cloudformation/cfn-lint) — linting CloudFormation templates.
- [CloudFormation Guard](https://github.com/aws-cloudformation/cloudformation-guard) — policy-as-code for templates.
