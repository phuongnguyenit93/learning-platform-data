# Building Multi-Environment Infrastructure with AWS CDK in Java

An AWS application typically runs across multiple environments: development for experimentation, staging for integration testing, and production for serving end users. When each environment is created manually or with separate templates, configurations easily drift: dev has one subnet layout, staging lacks alarms, production uses a different policy, or a security fix is only applied in one account. AWS Cloud Development Kit (AWS CDK) lets you define infrastructure as code and reuse the same design across multiple AWS accounts and Regions.

This capstone builds a CDK application in Java using AWS CDK v2. A single application architecture is deployed as stacks across multiple environments, each with its own account, Region, CIDR, compute sizing, retention, and protection level. The lesson progresses from project structure, environment configuration, constructs/stacks/stages to bootstrapping, cross-account trust, secrets, testing, and pipeline promotion. Learners will be able to design a repeatable deployment workflow with change control and rollback capability.

CDK is not a replacement for AWS Organizations, IAM governance, or change management processes. CDK generates CloudFormation templates and deploys them via CloudFormation; actual execution permissions still depend on IAM roles, bootstrap permissions, SCPs, resource policies, and service quotas in the target account.

## 1. Capstone Objectives

After completing this capstone, learners will be able to:

- Explain the relationship between CDK App, Construct, Stack, Stage, and CloudFormation stack.
- Initialize a Java CDK v2 project and manage dependencies with Maven.
- Design dev/staging/prod configurations by account and Region.
- Distinguish between environment-specific stacks and environment-agnostic stacks.
- Reuse constructs and stacks while preserving environment-specific settings.
- Separate networking, data, application, and observability along lifecycle boundaries.
- Use context lookups in a controlled way and keep synthesis repeatable.
- Bootstrap multiple accounts/Regions using the modern bootstrap template.
- Configure cross-account deployment trust and CloudFormation execution permissions.
- Protect secrets, IAM roles, KMS keys, and sensitive data.
- Build CDK Pipelines with stage promotion, automated validation, and manual approval.
- Test CloudFormation templates with JUnit and CDK Assertions.
- Use `cdk synth`, `cdk diff`, `cdk deploy`, drift detection, and rollback.
- Build a safe deployment workflow across multiple Regions.

## 2. Architecture Scenario

A company has three independent environments:

| Environment | AWS Account | Region | Purpose |
|---|---|---|---|
| dev | 111111111111 | ap-southeast-1 | Development and rapid testing |
| staging | 222222222222 | ap-southeast-1 | Integration testing, UAT, and performance |
| prod | 333333333333 | ap-southeast-1 | Production traffic |
| prod-dr (optional) | 333333333333 | ap-southeast-2 | Disaster recovery and failover testing |

The account IDs and Regions above are examples; replace them with your organization's values. Account IDs are not secrets, but they must be managed as deployment configuration to prevent deploying to the wrong target.

The sample application includes:

- A VPC with public/private subnets as needed.
- An Application Load Balancer as the entry point.
- A compute layer (ECS Fargate or Lambda) running the API.
- DynamoDB or RDS as the data layer.
- S3 for storing assets/logs/artifacts.
- Secrets Manager for storing credentials.
- KMS for encrypting resources that require customer-managed keys.
- CloudWatch log groups, alarms, and dashboards.

Each environment shares the same structure with different parameters. Production may use more AZs, longer retention, deletion protection, and stricter alarms. Dev can use smaller sizing and allow cleanup after labs.

### 2.1 Deployment Diagram

    Source repository
          |
       CDK Java
          |
       Unit tests
          |
      cdk synth
          |
    Cloud Assembly
          |
       cdk diff
          |
      Dev account
          |
    Smoke/integration tests
          |
     Staging account
          |
    UAT / security review
          |
    Manual approval
          |
      Prod account
          |
    Monitoring / rollback

CDK Pipelines can automate source retrieval, synthesis, asset publishing, cross-account deployment, and validation. Each Stage represents one instance of the application in an environment; a Stage can contain multiple stacks with dependencies.

## 3. Core CDK Concepts

| Component | Role | Example |
|---|---|---|
| App | Root construct and application synthesis entry point | App |
| Construct | Unit modeling a resource or group of resources | Bucket, Vpc, internal constructs |
| Stack | CloudFormation deployment unit | NetworkStack, ApplicationStack |
| Stage | A logical deployment unit containing one or more stacks | ApplicationStage for dev/prod |
| Cloud Assembly | Synthesis output containing templates, assets, and manifest | cdk.out |
| Bootstrap stack | Supporting resources enabling CDK deployments into an account/Region | CDKToolkit |

One Construct can contain other constructs. A Stack is a special construct that synthesizes a CloudFormation template. A Stage is a special construct grouping stacks into a single deployment unit. `cdk synth` produces the Cloud Assembly; `cdk deploy` uses that assembly to deploy.

### 3.1 Splitting Stacks by Lifecycle and Ownership

Avoid creating one monolithic stack containing everything when components have different lifecycles. One way to split them:

| Stack | Responsibilities | Frequent Changes |
|---|---|---|
| NetworkStack | VPC, subnets, routes, endpoints | Network/security changes |
| SecurityStack | KMS, security baseline, shared roles | Governance and encryption |
| DataStack | DynamoDB/RDS/S3/backups | Schema, retention, storage |
| ApplicationStack | ECS/Lambda/API/ALB | Application releases |
| ObservabilityStack | Log groups, alarms, dashboards | SLOs and alert policies |

Stack boundaries should reflect ownership, deployment permissions, and lifecycle. If two stacks always change together and are tightly coupled, keep them in the same stack or Stage. If the data layer needs an independent lifecycle from the app, separate the stacks so application changes do not accidentally replace the database.

### 3.2 Stack Dependencies

Within the same account and Region, CDK can create cross-stack references when one stack uses a resource attribute from another stack. For example, ApplicationStack receives a VPC or security group from NetworkStack. CDK generates CloudFormation exports/imports and orders dependencies.

    NetworkStack
         |
         +---- VPC / Subnets
                    |
              ApplicationStack
                    |
               ALB / Service

Cross-stack references can complicate deleting or renaming resources. Do not delete an export while another stack still imports it. Across accounts or Regions, direct CloudFormation exports/imports do not work like same-environment references; pass ARNs/IDs via configuration, SSM Parameter Store, resource sharing (AWS RAM), DNS, or pipeline outputs as designed.

## 4. Creating a Java CDK v2 Project

### 4.1 Tooling

Prepare:

- A project-compatible LTS JDK, Java 17 or 21 recommended.
- Apache Maven.
- Node.js/npm to install the AWS CDK CLI.
- AWS CLI v2.
- AWS CDK CLI v2.
- Credentials/profiles with permissions for the lab accounts.

Initialize the project:

    mkdir aws-multi-env
    cd aws-multi-env
    cdk init app --language java

CDK Java uses the Maven package `software.amazon.awscdk`. AWS CDK v2 bundles stable service constructs into `aws-cdk-lib`; experimental constructs have separate packages. Pin exact versions in `pom.xml` and update the CLI/runtime in a controlled manner for repeatable builds.

### 4.2 Recommended Project Structure

    aws-multi-env/
    ├── cdk.json
    ├── cdk.context.json
    ├── pom.xml
    ├── README.md
    ├── config/
    │   ├── environments.properties
    │   └── feature-matrix.properties
    ├── src/
    │   ├── main/java/com/example/platform/
    │   │   ├── Main.java
    │   │   ├── config/
    │   │   │   └── EnvironmentConfig.java
    │   │   ├── stages/
    │   │   │   └── ApplicationStage.java
    │   │   ├── stacks/
    │   │   │   ├── NetworkStack.java
    │   │   │   ├── DataStack.java
    │   │   │   ├── ApplicationStack.java
    │   │   │   └── ObservabilityStack.java
    │   │   └── constructs/
    │   │       └── ApiService.java
    │   └── test/java/com/example/platform/
    │       ├── NetworkStackTest.java
    │       └── ApplicationStackTest.java
    └── .gitignore

This is a reference layout; smaller projects may have fewer packages. Never put credentials, private keys, passwords, or tokens into config files.

### 4.3 Maven Dependencies

In `pom.xml`, keep dependencies aligned on a tested CDK v2 version line:

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awscdk</groupId>
            <artifactId>aws-cdk-lib</artifactId>
            <version>2.273.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

Versions `aws-cdk-lib` 2.273.0 and JUnit Jupiter 5.12.2 are pinned examples; choose versions tested with your project's JDK/Maven and lock them in source control. Maven pulls `constructs` transitively; if declared directly, choose a version compatible with `aws-cdk-lib`. Run `mvn test` in CI.

### 4.4 cdk.json

`cdk.json` declares the command the CDK CLI uses to run the Java app. Projects generated by `cdk init` include a suitable Maven configuration. Keep this file in source control and adapt it to your project structure rather than creating a separate command for each environment.

`cdk.context.json` stores context lookup values such as VPC/subnet/AMI/AZ data. Both files are part of the CDK app's state; commit them so local and CI runs synthesize identical results.

## 5. Environment Configuration Model

### 5.1 Non-Secret Configuration

Values suitable for storing in the repository:

- Environment name.
- Account ID and Region.
- CIDR/subnet sizing.
- Desired/min/max capacity.
- Log retention.
- Backup retention.
- Deletion protection.
- Non-sensitive feature flags.
- Resource tags and naming conventions.

Values that must never be stored in the repository:

- AWS access keys/secret keys.
- Database passwords.
- API tokens/private keys.
- Third-party credentials.
- Secret connection strings.

Secrets belong in Secrets Manager or SSM Parameter Store SecureString and are read at runtime using an IAM role.

### 5.2 environments.properties

Example configuration file:

    environment.dev.account=111111111111
    environment.dev.region=ap-southeast-1
    environment.dev.vpcCidr=10.10.0.0/16
    environment.dev.logRetentionDays=7
    environment.dev.deletionProtection=false

    environment.staging.account=222222222222
    environment.staging.region=ap-southeast-1
    environment.staging.vpcCidr=10.20.0.0/16
    environment.staging.logRetentionDays=30
    environment.staging.deletionProtection=true

    environment.prod.account=333333333333
    environment.prod.region=ap-southeast-1
    environment.prod.vpcCidr=10.30.0.0/16
    environment.prod.logRetentionDays=365
    environment.prod.deletionProtection=true

CIDRs must be planned so they do not overlap with existing VPCs, VPNs, Transit Gateways, or on-premises networks. Actual log retention must comply with your organization's legal and compliance policies.

### 5.3 EnvironmentConfig in Java

A configuration class should be immutable, validate inputs immediately upon loading, and provide an `Environment` for Stacks:

    package com.example.platform.config;

    import java.util.Locale;
    import software.amazon.awscdk.Environment;

    public final class EnvironmentConfig {
        private final String name;
        private final String account;
        private final String region;
        private final String vpcCidr;
        private final int logRetentionDays;
        private final boolean deletionProtection;

        public EnvironmentConfig(
                String name,
                String account,
                String region,
                String vpcCidr,
                int logRetentionDays,
                boolean deletionProtection) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Environment name is required");
            }
            if (account == null || !account.matches("\\d{12}")) {
                throw new IllegalArgumentException("AWS account must contain 12 digits");
            }
            if (region == null || region.isBlank()) {
                throw new IllegalArgumentException("Region is required");
            }
            if (vpcCidr == null || vpcCidr.isBlank()) {
                throw new IllegalArgumentException("VPC CIDR is required");
            }
            if (logRetentionDays <= 0) {
                throw new IllegalArgumentException("Log retention must be positive");
            }
            this.name = name;
            this.account = account;
            this.region = region;
            this.vpcCidr = vpcCidr;
            this.logRetentionDays = logRetentionDays;
            this.deletionProtection = deletionProtection;
        }

        public Environment toCdkEnvironment() {
            return Environment.builder()
                    .account(account)
                    .region(region)
                    .build();
        }

        public String getName() { return name; }
        public String getAccount() { return account; }
        public String getRegion() { return region; }
        public String getVpcCidr() { return vpcCidr; }
        public int getLogRetentionDays() { return logRetentionDays; }
        public boolean isDeletionProtection() { return deletionProtection; }
        public boolean isProduction() {
            return "prod".equalsIgnoreCase(name)
                    || name.toLowerCase(Locale.ROOT).startsWith("prod-");
        }
    }

This is an abbreviated example. In a complete project, use `Properties` or a configuration library to load the file, validate CIDRs, verify environment names, and reject undeclared values. Never fall back silently to production or a default profile.

### 5.4 Selecting an Environment Explicitly

One way to select an environment is using a system property:

    String target = System.getProperty("targetEnv", "dev");

    if (!environmentConfigs.containsKey(target)) {
        throw new IllegalArgumentException("Unknown targetEnv: " + target);
    }

Synth/deploy commands can pass `-DtargetEnv=staging` when invoking the app. With CDK Pipelines, Stages should be instantiated explicitly from reviewed configurations rather than relying on a local machine's profile.

## 6. Environment-Specific and Environment-Agnostic Stacks

### 6.1 Environment-Specific Stack

A stack bound to a specific account/Region pair:

    StackProps stackProps = StackProps.builder()
            .env(config.toCdkEnvironment())
            .build();

    new NetworkStack(app, "NetworkDev", config, stackProps);

At synthesis time, CDK knows the account and Region, so it can perform context lookups such as `Vpc.fromLookup`, access specific AZ lists, and create resources with environment-dependent logic. This is the right fit for multi-account deployments with explicit configuration.

### 6.2 Environment-Agnostic Stack

If `env` is omitted, the template can be synthesized without binding to a specific account/Region and deployed to multiple environments. This is useful when a stack needs no environment info during synthesis. However:

- Do not use logic depending on `stack.account`, `stack.region`, or specific AZs.
- Do not use `Vpc.fromLookup`, which requires a concrete account and Region.
- Some cross-stack references and context providers require a concrete environment.
- Do not mix agnostic templates with assumptions about resources that only exist in one account.

### 6.3 Avoid Implicit Account Resolution from Profiles in Production

CDK can read `CDK_DEFAULT_ACCOUNT` and `CDK_DEFAULT_REGION` from credentials/profiles. This is convenient for local development, but synthesis can vary by user, machine, or session. For production, declare the target account and Region explicitly in controlled configuration or pipeline Stages.

Do not rely on `--profile prod` as your sole safeguard to target the right account if a Stack already hard-codes another `env`; a Stack's `env` takes precedence over the CLI profile during synthesis.

## 7. Building a CDK App and Stage in Java

### 7.1 Main.java

`App` is the root of the construct tree. `Main` loads configuration, creates Stages, and calls `synth`:

    package com.example.platform;

    import com.example.platform.config.EnvironmentConfig;
    import com.example.platform.config.EnvironmentConfigLoader;
    import com.example.platform.stages.ApplicationStage;
    import software.amazon.awscdk.App;

    public final class Main {
        public static void main(final String[] args) {
            App app = new App();

            EnvironmentConfig dev = EnvironmentConfigLoader.load("dev");
            EnvironmentConfig staging = EnvironmentConfigLoader.load("staging");
            EnvironmentConfig prod = EnvironmentConfigLoader.load("prod");

            new ApplicationStage(app, "Dev", dev);
            new ApplicationStage(app, "Staging", staging);
            new ApplicationStage(app, "Prod", prod);

            app.synth();
        }
    }

`EnvironmentConfigLoader` is a project helper that reads properties and validates them. With CDK Pipelines, Stages are typically instantiated inside `PipelineStack` rather than instantiating all three stages in the local app entry point. Both patterns are valid; pick one that keeps deployment targets unambiguous.

### 7.2 ApplicationStage.java

A `Stage` groups the stacks forming one deployment of the application:

    package com.example.platform.stages;

    import com.example.platform.config.EnvironmentConfig;
    import com.example.platform.stacks.ApplicationStack;
    import com.example.platform.stacks.DataStack;
    import com.example.platform.stacks.NetworkStack;
    import software.amazon.awscdk.Stage;
    import software.amazon.awscdk.StageProps;
    import software.constructs.Construct;

    public final class ApplicationStage extends Stage {
        public ApplicationStage(
                final Construct scope,
                final String id,
                final EnvironmentConfig config) {
            super(scope, id, StageProps.builder()
                    .env(config.toCdkEnvironment())
                    .build());

            NetworkStack network = new NetworkStack(this, "Network", config);
            DataStack data = new DataStack(this, "Data", config);

            ApplicationStack application = new ApplicationStack(
                    this,
                    "Application",
                    config,
                    network.getVpc(),
                    data.getTable());

            application.addDependency(network);
            application.addDependency(data);
        }
    }

A Stage has a default environment that child stacks inherit for account and Region. If a child stack needs a different environment, declare it explicitly and consider the impact, since doing so alters the deployment boundary.

### 7.3 NetworkStack.java

Example creating a VPC with two AZs and tiered subnets:

    package com.example.platform.stacks;

    import com.example.platform.config.EnvironmentConfig;
    import java.util.List;
    import software.amazon.awscdk.Stack;
    import software.amazon.awscdk.StackProps;
    import software.amazon.awscdk.Tags;
    import software.amazon.awscdk.services.ec2.IpAddresses;
    import software.amazon.awscdk.services.ec2.SubnetConfiguration;
    import software.amazon.awscdk.services.ec2.SubnetType;
    import software.amazon.awscdk.services.ec2.Vpc;
    import software.constructs.Construct;

    public final class NetworkStack extends Stack {
        private final Vpc vpc;

        public NetworkStack(
                final Construct scope,
                final String id,
                final EnvironmentConfig config) {
            super(scope, id, StackProps.builder()
                    .description("Network foundation for " + config.getName())
                    .terminationProtection(config.isDeletionProtection())
                    .build());

            this.vpc = Vpc.Builder.create(this, "Vpc")
                    .ipAddresses(IpAddresses.cidr(config.getVpcCidr()))
                    .maxAzs(2)
                    .natGateways(config.isProduction() ? 2 : 1)
                    .subnetConfiguration(List.of(
                            SubnetConfiguration.builder()
                                    .name("public")
                                    .subnetType(SubnetType.PUBLIC)
                                    .cidrMask(24)
                                    .build(),
                            SubnetConfiguration.builder()
                                    .name("application")
                                    .subnetType(SubnetType.PRIVATE_WITH_EGRESS)
                                    .cidrMask(24)
                                    .build(),
                            SubnetConfiguration.builder()
                                    .name("isolated")
                                    .subnetType(SubnetType.PRIVATE_ISOLATED)
                                    .cidrMask(24)
                                    .build()))
                    .build();

            Tags.of(this).add("Environment", config.getName());
            Tags.of(this).add("ManagedBy", "AWS-CDK");
            Tags.of(this).add("Service", "CLOUD_PROVIDERS_AWS");
        }

        public Vpc getVpc() {
            return vpc;
        }
    }

This is an architectural example; verify the API for your installed CDK version and check CIDR sizing before synthesizing. Two NAT Gateways in production reduce reliance on a single AZ but increase cost. If the workload needs no outbound Internet access, prefer VPC endpoints and appropriate private connectivity.

### 7.4 DataStack.java

`DataStack` can create a DynamoDB table or import an existing resource. Example table with point-in-time recovery and a retain policy:

    package com.example.platform.stacks;

    import com.example.platform.config.EnvironmentConfig;
    import software.amazon.awscdk.RemovalPolicy;
    import software.amazon.awscdk.Stack;
    import software.amazon.awscdk.StackProps;
    import software.amazon.awscdk.services.dynamodb.Attribute;
    import software.amazon.awscdk.services.dynamodb.AttributeType;
    import software.amazon.awscdk.services.dynamodb.BillingMode;
    import software.amazon.awscdk.services.dynamodb.PointInTimeRecoverySpecification;
    import software.amazon.awscdk.services.dynamodb.Table;
    import software.constructs.Construct;

    public final class DataStack extends Stack {
        private final Table table;

        public DataStack(
                Construct scope,
                String id,
                EnvironmentConfig config) {
            super(scope, id, StackProps.builder()
                    .terminationProtection(config.isDeletionProtection())
                    .build());

            this.table = Table.Builder.create(this, "Orders")
                    .partitionKey(Attribute.builder()
                            .name("pk")
                            .type(AttributeType.STRING)
                            .build())
                    .sortKey(Attribute.builder()
                            .name("sk")
                            .type(AttributeType.STRING)
                            .build())
                    .billingMode(BillingMode.PAY_PER_REQUEST)
                    .pointInTimeRecoverySpecification(
                            PointInTimeRecoverySpecification.builder()
                                    .pointInTimeRecoveryEnabled(true)
                                    .recoveryPeriodInDays(35)
                                    .build())
                    .deletionProtection(config.isDeletionProtection())
                    .removalPolicy(config.isDeletionProtection()
                            ? RemovalPolicy.RETAIN
                            : RemovalPolicy.DESTROY)
                    .build();
        }

        public Table getTable() {
            return table;
        }
    }

In environments with deletion protection enabled, `RETAIN` protects data from accidental stack deletion, though it means the resource can remain after stack deletion and requires a separate lifecycle process. `DESTROY` is suitable only for recreatable lab/dev resources; never enable auto-delete for production data.

### 7.5 ApplicationStack.java

`ApplicationStack` receives interfaces from foundational stacks:

    package com.example.platform.stacks;

    import com.example.platform.config.EnvironmentConfig;
    import software.amazon.awscdk.Stack;
    import software.amazon.awscdk.services.dynamodb.ITable;
    import software.amazon.awscdk.services.ec2.IVpc;
    import software.constructs.Construct;

    public final class ApplicationStack extends Stack {
        public ApplicationStack(
                Construct scope,
                String id,
                EnvironmentConfig config,
                IVpc vpc,
                ITable ordersTable) {
            super(scope, id);

            // Create security groups, ECS service, or Lambda functions here.
            // Use vpc and ordersTable to connect to foundational resources.
            // Grant only the permissions required for the application execution role.
        }
    }

The snippet above illustrates dependency boundaries, not a complete deployable application. In actual implementations, use interfaces such as `IVpc` and `ITable` where constructs support them to reduce coupling to concrete constructs.

## 8. Reusing Constructs and Environment-Specific Configuration

### 8.1 Use Props Instead of Reading Global Context Everywhere

Constructs should receive data via props/constructors. For example, `ApiService` accepts a VPC, security group, desired count, log retention, and secret reference. This makes testing easier and prevents a construct from reading environment variables from unclear sources.

### 8.2 Use a Feature Matrix

| Feature | dev | staging | prod |
|---|---|---|---|
| NAT gateways | 1 | 1 | 2 |
| Multi-AZ database | Optional | Yes | Yes |
| Deletion protection | Disabled | Enabled | Enabled |
| Log retention | 7 days | 30 days | Per compliance |
| Backup retention | Short | Medium | Per RPO/RTO |
| Alarm severity | Warning | Warning/Critical | Critical + escalation |
| Manual approval | No | UAT | Required |

Avoid scattering `if/else` branches throughout stacks. Centralize differences in `EnvironmentConfig` or explicit props. If an environment has a fundamentally different architecture, consider a separate Stage or stack rather than packing numerous flags into one construct.

### 8.3 Tags and Naming

Apply standard tags to stacks and resources:

- Application
- Environment
- Owner
- CostCenter
- DataClassification
- ManagedBy
- Repository

Resource names should include environment prefixes while respecting service character limits and global uniqueness constraints. Avoid using identical bucket names across accounts or Regions where bucket names are globally scoped.

## 9. Context Lookups and Synthesis Repeatability

CDK context is key-value metadata sourced from `cdk.json`, `cdk.context.json`, the CLI, or constructs. Context providers can look up AZs, VPCs, hosted zones, AMIs, and other account-specific values.

### 9.1 Vpc.fromLookup

When a VPC is created outside CDK:

    IVpc existingVpc = Vpc.fromLookup(
            this,
            "SharedVpc",
            VpcLookupOptions.builder()
                    .vpcId("vpc-0123456789abcdef0")
                    .build());

Lookup results are cached in `cdk.context.json`. Commit the context file so CI and developer machines synthesize identical templates. Clearing the cache or refreshing context can change templates if AZs, subnets, or AMIs have changed in the account.

### 9.2 Context Refresh Workflow

1. Identify why context needs to be refreshed.
2. Run `synth` against the target account/Region with lookup permissions.
3. Review the diff in `cdk.context.json`.
4. Review the CloudFormation template diff.
5. Commit the context update alongside the related infrastructure change.
6. Never let the pipeline perform ad-hoc lookups using broad production credentials.

Never commit secrets into context files. Context lookup is not a secret store and does not replace configuration management.

### 9.3 Context and Environments

Lookups require a concrete environment because CDK must know which account and Region to query. If a stack must deploy to multiple accounts/Regions without binding `env` at synthesis time, design it using environment-specific Stages or explicit parameters/references instead of unresolved lookups.

## 10. Protecting Secrets, IAM, and Networking

### 10.1 Keep Secrets Out of Source Code and CloudFormation Templates

CDK provides the `SecretValue` type to represent secret references. Actual secret values should live in Secrets Manager or SSM Parameter Store SecureString. Never use `unsafePlainText` for passwords or tokens; never write plaintext secrets into properties, because those values can surface in synthesized templates, the CloudFormation console, or logs.

Example importing a secret and granting read access to a runtime role:

    ISecret databaseSecret = Secret.fromSecretNameV2(
            this,
            "DatabaseSecret",
            "orders/prod/database");

    Role taskRole = Role.Builder.create(this, "ApiTaskRole")
            .assumedBy(new ServicePrincipal("ecs-tasks.amazonaws.com"))
            .build();

    databaseSecret.grantRead(taskRole);

The application fetches the secret at runtime using the AWS SDK and the task's role. Never read secrets during CDK synthesis and inject their values into Lambda/ECS environment variables.

### 10.2 Secret References in Constructs

If a construct supports `SecretValue`, pass a reference instead of plaintext:

    SecretValue dbPassword = SecretValue.secretsManager(
            "orders/prod/database",
            SecretsManagerSecretOptions.builder()
                    .jsonField("password")
                    .build());

Only pass `SecretValue` to properties explicitly documented by CDK as supporting secrets. If a construct expects a plain string, prefer runtime retrieval. Secret rotation in Secrets Manager does not always trigger a CloudFormation update automatically; applications should fetch secrets at runtime and follow a rotation strategy.

### 10.3 IAM Least Privilege

Separate roles by responsibility:

| Role | Assumed By | Permissions |
|---|---|---|
| CDK deploy role | Pipeline account/CLI | Assume deployment role in target account |
| CloudFormation execution role | CloudFormation | Create/update required resources |
| Application task role | ECS/Lambda runtime | Read secrets, access designated tables/buckets |
| Lookup role | CDK CLI | Read-only lookups during synth |
| Asset publishing role | CDK CLI/pipeline | Upload file assets and container assets |

Never use `AdministratorAccess` as a runtime role. For the bootstrap execution policy, prefer a customer-managed policy scoped to the resources the pipeline is authorized to manage. Overly broad deployment permissions could allow a pipeline to create high-impact IAM roles, policies, and resources.

### 10.4 Network Boundaries

- Run application workloads in private subnets unless public inbound access is required.
- Expose only required listeners/ports on public ALBs; targets should accept traffic only from the ALB security group.
- Databases should accept traffic only from application security groups.
- Use VPC endpoints for S3, ECR, CloudWatch, Secrets Manager, and other services where appropriate.
- Monitor NAT Gateway costs and egress controls.
- Use Network ACLs as a stateless subnet-level layer; Security Groups serve as the primary stateful workload boundary.
- Enable VPC Flow Logs and CloudTrail for auditing and troubleshooting.

### 10.5 Encryption and Data Protection

Configure encryption at rest for S3, EBS, RDS, DynamoDB, EFS, and log destinations per requirements. Use KMS customer-managed keys when key policies, auditing, or separation of duties are required. Verify service roles, application roles, and key policies together; an IAM allow does not override an explicit deny in a key policy or SCP.

## 11. Bootstrapping Multiple Accounts and Regions

CDK requires bootstrapping each environment (account, Region) before deployment. The modern bootstrap template creates staging resources such as an S3 bucket for file assets, an ECR repository for container assets, and IAM roles for deployment, asset publishing, image publishing, and lookups.

### 11.1 Bootstrapping the Pipeline Account

Assume the pipeline resides in account `111111111111`, Region `ap-southeast-1`:

    cdk bootstrap aws://111111111111/ap-southeast-1 \
      --profile platform-admin \
      --termination-protection

The pipeline account must also be bootstrapped because CDK Pipelines creates CodePipeline/CodeBuild resources and requires publishing/deployment infrastructure.

### 11.2 Bootstrapping Target Accounts

Staging and production must trust the pipeline account. Example:

    cdk bootstrap aws://222222222222/ap-southeast-1 \
      --profile staging-admin \
      --trust 111111111111 \
      --trust-for-lookup 111111111111 \
      --cloudformation-execution-policies arn:aws:iam::222222222222:policy/CdkCloudFormationExecutionPolicy \
      --termination-protection

    cdk bootstrap aws://333333333333/ap-southeast-1 \
      --profile prod-admin \
      --trust 111111111111 \
      --trust-for-lookup 111111111111 \
      --cloudformation-execution-policies arn:aws:iam::333333333333:policy/CdkCloudFormationExecutionPolicy \
      --termination-protection

The policy ARN above is an example; craft a policy scoped to the resources and services the pipeline needs to manage and review it with your security team. Do not default to `AdministratorAccess` for every target account.

### 11.3 Bootstrapping Additional Regions

If deploying DR in `ap-southeast-2`, you must bootstrap that account/Region:

    cdk bootstrap aws://333333333333/ap-southeast-2 \
      --profile prod-admin \
      --trust 111111111111 \
      --cloudformation-execution-policies arn:aws:iam::333333333333:policy/CdkCloudFormationExecutionPolicy \
      --termination-protection

Bootstrapping is scoped per account/Region pair. Bootstrapping one Region does not prepare another Region.

### 11.4 Trust and Lookup Trust

- `--trust`: grants the specified account permission to deploy into the environment; must be paired with `--cloudformation-execution-policies`.
- `--trust-for-lookup`: grants read-only context lookup permissions only, e.g., when a CDK app uses VPC lookups.
- The bootstrapped account itself is always trusted.
- When updating the bootstrap stack's trust list, re-specify the complete list of trusted accounts; passing only a new account can remove previously trusted accounts.

Only add `--trust-for-lookup` when pipeline synthesis genuinely needs to look up resources in the target account. If all values are explicitly declared and context cache is committed, cross-account lookup trust can be omitted.

### 11.5 Protecting the Bootstrap Stack

The bootstrap stack is typically named `CDKToolkit`. Never delete this stack or change its qualifier while pipelines depend on it. Deleting the bootstrap stack can destroy S3/ECR staging resources and IAM roles, breaking subsequent deployments. Enable termination protection, manage bootstrap changes through platform infrastructure workflows, and upgrade with `cdk bootstrap` rather than deleting and recreating.

### 11.6 Cross-Account Artifact Encryption

CDK Pipelines deploying across accounts needs an artifact bucket encrypted with an appropriate key. Enable `crossAccountKeys` when the pipeline performs cross-account deployments:

    CodePipeline pipeline = CodePipeline.Builder.create(this, "Pipeline")
            .crossAccountKeys(true)
            .synth(synthStep)
            .build();

KMS keys used to encrypt artifacts have separate costs and lifecycles. Verify that the key policy, pipeline role, and target deployment roles all have the required permissions.

## 12. Building CDK Pipelines in Java

CDK Pipelines is a construct library for continuous delivery of CDK applications. A pipeline can deploy multiple instances of a Stage into different accounts and Regions. A Stage typically groups multiple stacks belonging to the same release.

### 12.1 PipelineStack

Abbreviated example using a GitHub connection and a Java CDK project:

    package com.example.platform.stacks;

    import java.util.List;
    import software.amazon.awscdk.Stack;
    import software.amazon.awscdk.StackProps;
    import software.amazon.awscdk.pipelines.AddStageOpts;
    import software.amazon.awscdk.pipelines.CodePipeline;
    import software.amazon.awscdk.pipelines.CodePipelineSource;
    import software.amazon.awscdk.pipelines.ConnectionSourceOptions;
    import software.amazon.awscdk.pipelines.ManualApprovalStep;
    import software.amazon.awscdk.pipelines.ShellStep;
    import software.constructs.Construct;

    public final class PipelineStack extends Stack {
        public PipelineStack(Construct scope, String id, StackProps props) {
            super(scope, id, props);

            CodePipeline pipeline = CodePipeline.Builder.create(this, "Pipeline")
                    .crossAccountKeys(true)
                    .synth(ShellStep.Builder.create("Synth")
                            .input(CodePipelineSource.connection(
                                    "my-org/aws-multi-env",
                                    "main",
                                    ConnectionSourceOptions.builder()
                                            .connectionArn(
                                                "arn:aws:codeconnections:ap-southeast-1:111111111111:connection/EXAMPLE")
                                            .build()))
                            .commands(List.of(
                                    "npm install -g aws-cdk@2.273.0",
                                    "mvn test",
                                    "cdk synth"))
                            .build())
                    .build();
        }
    }

Replace the organization, repository, branch, and connection ARN with real values. AWS CodeStar Connections has been renamed to AWS CodeConnections; new connections use the `codeconnections` ARN prefix, while older resources using `codestar-connections` remain supported. A connection ARN is not a credential, but access should still be scoped only to required repositories. The CDK CLI must be installed in the synth environment; Maven compilation of the Java app runs when `cdk synth` executes.

### 12.2 Adding dev, staging, and prod

In `PipelineStack`, create Stages from loaded configurations:

    ApplicationStage dev = new ApplicationStage(this, "Dev", devConfig);
    ApplicationStage staging = new ApplicationStage(this, "Staging", stagingConfig);
    ApplicationStage prod = new ApplicationStage(this, "Prod", prodConfig);

    pipeline.addStage(dev);

    pipeline.addStage(staging, AddStageOpts.builder()
            .post(List.of(ShellStep.Builder.create("StagingSmokeTest")
                    .commands(List.of("./scripts/smoke-test.sh staging"))
                    .build()))
            .build());

    pipeline.addStage(prod, AddStageOpts.builder()
            .pre(List.of(ManualApprovalStep.Builder.create("ApproveProduction")
                    .comment("Review staging test results and change plan")
                    .build()))
            .build());

Stage order defines the promotion path. The staging smoke test runs after deploying staging; manual approval runs before the pipeline promotes to production.

### 12.3 Automated Validation and Manual Approval

Validation steps should include:

- Unit tests and CDK assertions before synth.
- Template/security scans after synth.
- `cdk diff` or CloudFormation change set review.
- Smoke tests after dev/staging deployments.
- Integration tests against real dependencies in staging.
- Manual approval before production.
- Post-deploy health checks and alarm verification.

Manual approvals need an accountable reviewer and clear acceptance criteria. Never use manual approval as an excuse to skip automated tests or policy validation.

### 12.4 Self-Mutating Pipelines

By default, CDK Pipelines can update its own pipeline definition when source changes. Commit and push source code before the first deployment of `PipelineStack`; pipeline self-mutation pulls code from the repository and can overwrite uncommitted changes. When developing the pipeline, understand `selfMutation` and execution modes to avoid two concurrent runs modifying the same stack.

### 12.5 Stage and Region Promotion

You can add Stages across different accounts and Regions:

    ApplicationStage prodPrimary =
            new ApplicationStage(this, "ProdPrimary", prodPrimaryConfig);
    ApplicationStage prodDr =
            new ApplicationStage(this, "ProdDr", prodDrConfig);

Deploy DR only when data replication, DNS failover, secret replication, KMS keys, service quotas, and operational runbooks are ready. Two stacks in two Regions do not automatically synchronize databases or object data simply because they are defined in the same CDK app.

## 13. Testing Java CDK Applications

A CDK application should be tested at multiple layers: Java unit tests for configuration logic, CDK Assertions for CloudFormation templates, static policy checks for security, and deployment tests for actual AWS resource behavior.

### 13.1 Unit Testing Configuration

Verify that constructors reject malformed account IDs, empty Regions, invalid CIDRs, and invalid retention values. Failing fast prevents synthesizing templates for invalid targets.

Example properties loader:

    package com.example.platform.config;

    import java.io.IOException;
    import java.io.InputStream;
    import java.nio.file.Files;
    import java.nio.file.Path;
    import java.util.Properties;

    public final class EnvironmentConfigLoader {
        private EnvironmentConfigLoader() {}

        public static EnvironmentConfig load(String name) {
            Properties properties = new Properties();
            Path path = Path.of("config", "environments.properties");

            try (InputStream input = Files.newInputStream(path)) {
                properties.load(input);
            } catch (IOException error) {
                throw new IllegalStateException("Cannot load environment config", error);
            }

            String prefix = "environment." + name + ".";
            String account = require(properties, prefix + "account");
            String region = require(properties, prefix + "region");
            String cidr = require(properties, prefix + "vpcCidr");
            int retention = Integer.parseInt(require(
                    properties,
                    prefix + "logRetentionDays"));
            String deletionProtectionValue = require(
                    properties,
                    prefix + "deletionProtection");
            if (!"true".equalsIgnoreCase(deletionProtectionValue)
                    && !"false".equalsIgnoreCase(deletionProtectionValue)) {
                throw new IllegalArgumentException(
                        "deletionProtection must be true or false");
            }
            boolean deletionProtection = Boolean.parseBoolean(deletionProtectionValue);

            return new EnvironmentConfig(
                    name, account, region, cidr, retention, deletionProtection);
        }

        private static String require(Properties properties, String key) {
            String value = properties.getProperty(key);
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("Missing configuration: " + key);
            }
            return value.trim();
        }
    }

The loader resides in package `com.example.platform.config` and requires imports `java.io.InputStream`, `java.io.IOException`, `java.nio.file.Files`, `java.nio.file.Path`, and `java.util.Properties`. Add CIDR validation and account/Region allowlist checks in your implementation. In pipelines, config files must be read from the commit being built; never read arbitrary configs from a runner's local machine.

### 13.2 CDK Assertions

Example testing VPC and subnets:

    package com.example.platform;

    import com.example.platform.config.EnvironmentConfig;
    import com.example.platform.stacks.NetworkStack;
    import java.util.Map;
    import org.junit.jupiter.api.Test;
    import software.amazon.awscdk.App;
    import software.amazon.awscdk.assertions.Template;

    public class NetworkStackTest {
        @Test
        void createsExpectedNetworkResources() {
            App app = new App();
            EnvironmentConfig config = new EnvironmentConfig(
                    "test",
                    "111111111111",
                    "ap-southeast-1",
                    "10.10.0.0/16",
                    7,
                    false);

            NetworkStack stack = new NetworkStack(app, "Network", config);
            Template template = Template.fromStack(stack);

            template.resourceCountIs("AWS::EC2::VPC", 1);
            template.resourceCountIs("AWS::EC2::Subnet", 6);
            template.hasResourceProperties(
                    "AWS::EC2::VPC",
                    Map.of("CidrBlock", "10.10.0.0/16"));
        }
    }

Subnet count in the test depends on `maxAzs` and `subnetConfiguration`. Update expectations intentionally if the architecture changes. Do not snapshot entire templates for every test; focus assertions on security, encryption, network isolation, deletion policies, and critical properties.

### 13.3 Security Policy Testing

You can use:

- `cdk-nag` to check security and compliance rules across the construct tree.
- CloudFormation Guard or policy-as-code scanners to validate synthesized templates.
- IAM policy reviews to detect unnecessary wildcard actions or resources.
- Dependency/image scanners for code and container assets.
- AWS Config/Security Hub in target accounts to monitor runtime posture.

A successful `cdk synth` does not mean a design is secure. Static policy checks should run before pipeline promotion.

### 13.4 Integration Tests

Unit tests do not provision real resources. Integration tests should run in a sandbox or staging account to verify:

- VPCs, subnets, and routes are actually provisioned.
- ECS/Lambda can reach dependencies.
- KMS key policies permit the intended workload roles.
- Secret rotation does not disrupt the application.
- Alarms and log groups receive data.
- Backup/restore or failover works as designed.

Integration tests can incur costs and leave long-lived resources behind; enforce tags, TTLs/cleanup, and account limits.

## 14. Synth, Diff, and Deploy Workflow

### 14.1 Common Commands

    cdk ls
    cdk synth NetworkStack
    cdk diff NetworkStack --profile dev
    cdk deploy NetworkStack --profile dev
    cdk deploy ApplicationStack --profile dev

Stack names must match the stack IDs generated in the App/Stage. For pipeline Stages, deployments are usually driven by CDK Pipelines. When deploying locally, target only the intended stack/environment; avoid `cdk deploy --all` when an app contains both production and dev stacks.

### 14.2 Synth

`cdk synth` produces CloudFormation templates and the Cloud Assembly. Review:

- Resource types and logical IDs.
- IAM policies and trust relationships.
- Public access and security group ingress/egress.
- Encryption, KMS keys, and bucket policies.
- Retention, backups, deletion policies, and termination protection.
- Parameters/outputs and cross-stack references.
- Asset sizes, Docker images, and file asset manifests.

Synthesized templates are critical review artifacts before changing AWS infrastructure.

### 14.3 Diff

`cdk diff` compares the deployed template against the newly synthesized template to show resources being added, modified, or deleted. Carefully inspect replacements, deletions, IAM policy broadenings, subnet/route changes, databases, encryption keys, and retention changes.

For production, use CloudFormation change sets and pipeline reviews to inspect the update plan. A simple diff does not replace assessing data impact, downtime, or service quotas.

### 14.4 Controlled Deployments

- Use short-lived credentials via IAM Identity Center/assume role or a pipeline role.
- Verify caller identity and target account/Region before deploying.
- Require approval for high-risk changes.
- Use `cdk deploy --require-approval broadening` to require approval when IAM permissions expand.
- Restrict deployment permissions per environment.
- Archive templates, Cloud Assemblies, diffs, and deployment execution IDs.

### 14.5 Do Not Use Deploy as a Secret Management Mechanism

Never pass passwords via command lines, shell history, or CDK context. Never store secrets in plaintext CloudFormation parameters. Runtime workloads should retrieve secrets from Secrets Manager or SSM using their dedicated roles.

## 15. Managing Drift, Updates, and Rollbacks

### 15.1 CloudFormation Drift

Drift occurs when live resources are modified outside CloudFormation/CDK—for example via console edits, CLI updates, or service automation. CloudFormation drift detection checks only supported resource types and properties and does not catch every runtime change.

Handling workflow:

1. Run drift detection on the stack.
2. Identify the drifted resources and properties.
3. Trace the actor and reason via CloudTrail/change history.
4. Decide whether to codify the change or restore the resource to match the template.
5. Re-run `synth` and `diff` before deploying.

Never blindly overwrite drift without understanding why the change was made; you could erase an emergency hotfix or necessary adjustment.

### 15.2 CloudFormation Rollbacks

When a stack update fails, CloudFormation can roll back to the previous state. Inspect stack events and resource statuses to locate the first failing resource. Some failures—caused by custom resources, quotas, IAM, or replacements—cannot be fixed simply by retrying.

### 15.3 Application and Data Rollbacks

Rolling back infrastructure does not roll back data. When changing a database schema or S3 object format, design backward-compatible migrations:

- Expand: add new fields/tables/indexes while the old version still works.
- Migrate: backfill data in batches and verify completeness.
- Switch: deploy new code reading/writing the new schema.
- Contract: remove the old schema only after no consumers remain.

For high-risk releases, use canary, blue/green, or traffic shifting instead of replacing the entire workload at once.

### 15.4 RemovalPolicy and Termination Protection

`RemovalPolicy.RETAIN` preserves a resource after stack deletion; `DESTROY` deletes the resource as part of the CloudFormation lifecycle if supported by the service. Termination protection prevents accidental deletion of the entire stack. These are distinct mechanisms and should be configured separately for production data, networking, and the bootstrap stack.

Do not rely on termination protection alone to safeguard individual resources, and do not rely on `RemovalPolicy` to protect an entire stack.

## 16. Multi-Region and Disaster Recovery

### 16.1 Same Code, Region-Specific Configuration

A Stage can deploy to another Region if the services and constructs support it. However, not all resources behave identically across Regions:

- Service availability and feature parity.
- AZ counts and subnet capacity.
- Instance types and quotas.
- KMS keys and secret scope.
- Domains, certificates, and DNS.
- Data replication and consistency.
- Pricing and data transfer.

Check AWS service availability and quotas before adding a new Region to the pipeline.

### 16.2 Data Classification and RPO/RTO

| Data Type | Suggested DR Strategy |
|---|---|
| Stateless compute | Re-deploy via CDK in the DR Region |
| S3 objects | Cross-Region Replication where appropriate |
| DynamoDB | Global Tables or backup/restore per RPO |
| RDS | Cross-Region read replicas or snapshot copies |
| Secrets Manager | Secret replication and key access |
| KMS | Provision separate keys in the DR Region with matching policies |
| DNS | Health checks, failover policies, and runbooks |

RPO is the acceptable data loss window; RTO is the target recovery time. CDK provisions resources and configuration; it does not automatically guarantee replication, failover, or consistency.

### 16.3 Cross-Region References

Standard CloudFormation exports/imports are scoped to a single account and Region. To share values across Regions, consider SSM Parameter Store, DNS, resource replication, pipeline outputs, or CDK-supported cross-region reference mechanisms while understanding their limits. Avoid circular dependencies that prevent one Region from deploying independently during an outage in the other Region.

### 16.4 DR Drills

Conduct periodic drills:

1. Verify stacks and bootstrap resources in the DR Region.
2. Verify container images, secrets, KMS keys, networking, and service quotas.
3. Restore data from replicas or backups.
4. Run smoke and integration tests.
5. Shift DNS/traffic according to the runbook.
6. Measure actual RTO and RPO.
7. Fail back or continue operating in the DR Region per plan.

## 17. Cost Governance and Resource Lifecycle

CDK provisions infrastructure; actual costs depend on resources, traffic, storage, data transfer, and lifetime. Build cost controls directly into your configuration:

- Tag `owner`, `environment`, `cost center`, and `application`.
- NAT Gateways, KMS keys, load balancers, EKS clusters, and log ingestion can accrue continuous charges.
- Set log retention and S3 lifecycle rules.
- Choose NAT Gateways vs. VPC endpoints based on traffic patterns.
- Right-size instances and configure autoscaling.
- Enable deletion protection/retain in production and cleanup policies in dev.
- Configure AWS Budgets, Cost Anomaly Detection, and per-environment alarms.
- Account separation simplifies cost attribution and limits blast radius.

Dev environments can automatically shut down compute after hours or tear down TTL-tagged lab stacks. Never auto-delete networking, data, or shared resources without clear ownership and approval.

## 18. Case Study: Three-Environment Order Platform

### 18.1 Requirements

An enterprise is building an Orders API serving a website and mobile app. The API accepts orders, reads/writes DynamoDB, stores invoice files in S3, and emits events to downstream systems. Organizational requirements:

- Dev, staging, and prod run in separate accounts.
- Each environment has network isolation.
- Staging mirrors production closely for testing.
- Production has deletion protection, backups, log retention, and alarms.
- Deployments flow from a source repository through a pipeline.
- Production updates only after staging smoke tests and reviewer approval succeed.
- A DR Region and recovery runbook are in place.

### 18.2 Stack Design

| Stack | Resources | Notes |
|---|---|---|
| NetworkStack | VPC, public/private/isolated subnets, endpoints | Managed per account |
| SecurityStack | KMS keys, IAM roles, security baseline | Environment-specific policies |
| DataStack | DynamoDB table, S3 bucket, backups | Production retain/PITR |
| ApplicationStack | ALB, ECS Fargate service, task role | Release-pinned image digest |
| ObservabilityStack | Log groups, alarms, dashboards | Policy-driven retention |

Each environment's Stage instantiates these stacks and passes resource references within the same account/Region. `PipelineStack` lives in the tooling/dev account; staging and prod target accounts trust the pipeline account via bootstrapping.

### 18.3 Environment Matrix

| Setting | Dev | Staging | Prod |
|---|---|---|---|
| VPC CIDR | 10.10.0.0/16 | 10.20.0.0/16 | 10.30.0.0/16 |
| AZs | 2 | 2 | 2 |
| NAT | 1 | 1 | 2 or endpoints based on traffic |
| ECS desired count | 1 | 2 | Based on load tests/SLOs |
| DynamoDB | On-demand | On-demand | Based on capacity/cost model |
| PITR | Enabled as needed | Enabled | Enabled |
| Deletion protection | Disabled | Enabled | Enabled |
| Log retention | 7 days | 30 days | Per compliance |
| Deploy approval | No | UAT | Required |

These values are illustrative for discussion, not production sizing recommendations. Use load testing, availability targets, traffic forecasts, and a cost model to choose real parameters.

### 18.4 Deployment Path

1. Developer opens a pull request.
2. CI runs Maven tests, CDK assertions, `cdk synth`, and security scans.
3. The pipeline deploys Dev.
4. Smoke tests verify health endpoints, IAM access, and DynamoDB/S3 paths.
5. The pipeline deploys Staging.
6. Integration/UAT tests run against synthetic data.
7. Reviewers inspect diffs, test results, and security findings, then approve production.
8. The pipeline deploys Prod via change set.
9. Post-deploy smoke tests and CloudWatch alarms confirm health.
10. If errors exceed thresholds, roll back the application version and open an incident.

### 18.5 Acceptance Criteria

- All three Stages synthesize stacks with the correct accounts and Regions.
- No plaintext secrets appear in source, context, or synthesized templates.
- Production resources have appropriate encryption, backups, retain policies, and termination protection.
- The IAM task role accesses only the designated table, bucket, and secret.
- The pipeline deploys to staging/prod only via bootstrap trust.
- Staging tests pass before manual approval.
- Production deployments have an audit trail, change set, and rollback plan.
- The DR Region has tested data replication, secret/key access, and a validated runbook.

## 19. Lab A: Create a Java CDK App for Dev and Staging

### Objective

Initialize a Java CDK v2 project and create `EnvironmentConfig`, `Stage`, and `NetworkStack` shared across two environments.

### Step 1: Initialize

    mkdir aws-multi-env-lab
    cd aws-multi-env-lab
    cdk init app --language java

Verify Java/Maven/CDK CLI:

    java -version
    mvn -version
    cdk --version

### Step 2: Create Configuration

Create `environments.properties` with two sandbox accounts and a lab Region. Choose CIDRs that do not overlap existing VPCs. Never write access keys or passwords into the file.

### Step 3: Create EnvironmentConfig

1. Write an immutable configuration class.
2. Validate account ID, Region, CIDR, and retention.
3. Write `EnvironmentConfigLoader`.
4. Write unit tests covering valid and invalid inputs.

### Step 4: Create Stage and Stack

1. Create `NetworkStack` with a VPC and subnets.
2. Create `ApplicationStage` accepting `EnvironmentConfig`.
3. Instantiate two Stages: `Dev` and `Staging`.
4. Set the account/Region environment for each Stage.
5. Add tags and termination protection for staging where appropriate.

### Step 5: Test and Synth

    mvn test
    cdk ls
    cdk synth

Review the Cloud Assembly and confirm both environments have accurate settings and zero secrets. Do not deploy until account/Region targets and bootstrap status have been verified.

## 20. Lab B: Cross-Account Bootstrap and Deployment

### Objective

Prepare the pipeline account and target account, configure trust, and deploy a test stack across account boundaries.

### Step 1: Verify Caller Identity

    aws sts get-caller-identity --profile platform-admin
    aws sts get-caller-identity --profile staging-admin

Verify that actual account IDs match the declared environments.

### Step 2: Bootstrap the Pipeline Account

    cdk bootstrap aws://111111111111/ap-southeast-1 \
      --profile platform-admin \
      --termination-protection

### Step 3: Bootstrap the Target Account

    cdk bootstrap aws://222222222222/ap-southeast-1 \
      --profile staging-admin \
      --trust 111111111111 \
      --cloudformation-execution-policies arn:aws:iam::222222222222:policy/CdkCloudFormationExecutionPolicy \
      --termination-protection

Replace account IDs and policy ARNs with real sandbox values. The policy must be created and reviewed beforehand. Avoid using `AdministratorAccess` just for lab convenience when a scoped policy can be granted.

### Step 4: Diff and Deploy

    cdk diff NetworkStack --profile staging-admin
    cdk deploy NetworkStack --profile staging-admin

Inspect the CloudFormation stack, VPC/subnets, tags, and CloudTrail events. Then deploy the application stack if defined in your lab.

### Step 5: Verify Trust and Clean Up

1. Verify that the pipeline account can assume the deployment role.
2. Verify that an untrusted principal receives `AccessDenied`.
3. Confirm the bootstrap stack has termination protection enabled.
4. Delete lab stacks when no longer needed; keep the bootstrap stack for subsequent labs.

## 21. Lab C: Create a CDK Pipeline with Production Approval

### Objective

Create a CodePipeline using CDK Pipelines to deploy dev → staging → prod and require manual approval before production.

### Step 1: Create Source Connection

1. Create an AWS CodeConnections connection to your repository.
2. Complete OAuth/app installation at the source provider.
3. Store the connection ARN in pipeline configuration.
4. Never store personal tokens in source code.

### Step 2: Create PipelineStack

1. Create `CodePipeline` with a `ShellStep` synth.
2. Install the pinned AWS CDK CLI version matching the project inside the synth environment.
3. Run Maven tests.
4. Run `cdk synth`.
5. Enable `crossAccountKeys` if deploying cross-account.

### Step 3: Add Stages

1. Instantiate `ApplicationStage` `Dev`.
2. Add a post-step smoke test.
3. Instantiate `ApplicationStage` `Staging`.
4. Add integration tests/UAT.
5. Instantiate `ApplicationStage` `Prod`.
6. Add `ManualApprovalStep` to `Prod` pre-steps.

### Step 4: Deploy the Pipeline

1. Commit and push source code.
2. Bootstrap the pipeline account and target accounts.
3. Deploy `PipelineStack` initially using an authorized profile/role.
4. Verify self-mutation and source revision tracking.
5. Make a small change in the app and observe promotion through Stages.

### Step 5: Test the Gate

Intentionally fail a staging test and verify the pipeline does not promote. Then fix the test, re-run, and confirm production proceeds only after approval. Record the execution ID, commit SHA, and deployment history.

## 22. Self-Check Questions

**Question 1.** Which two values define a CDK environment?

**Answer:** An AWS account and an AWS Region.

**Question 2.** How do CDK App, Construct, Stack, and Stage differ?

**Answer:** App is the root; Construct models resources; Stack generates a CloudFormation template; Stage groups one or more stacks into an environment deployment.

**Question 3.** Why should NetworkStack and ApplicationStack be separated?

**Answer:** The two layers have different ownership, lifecycles, and change permissions; separating them reduces blast radius and clarifies dependencies.

**Question 4.** What is the advantage of an environment-specific stack?

**Answer:** CDK knows the account and Region during synthesis, enabling context lookups and environment-aware logic.

**Question 5.** What is the limitation of an environment-agnostic stack?

**Answer:** It cannot use lookups or synthesis logic that depend on a concrete account, Region, or AZ.

**Question 6.** Why must `cdk.context.json` be committed?

**Answer:** Context lookups are cached there; committing the file ensures local machines and CI synthesize the same values and prevents unexpected template changes.

**Question 7.** What types of resources does CDK bootstrap create?

**Answer:** An S3 staging bucket, an ECR repository, and IAM roles for deployment, asset publishing, image publishing, and lookups.

**Question 8.** Why must every account/Region pair be bootstrapped?

**Answer:** Bootstrap resources are provisioned per environment; bootstrapping one Region does not prepare another Region.

**Question 9.** How does `--trust` differ from `--trust-for-lookup`?

**Answer:** `--trust` grants cross-account deployment permissions; `--trust-for-lookup` grants read-only context lookup permissions only.

**Question 10.** What must you watch out for when updating the bootstrap trust list?

**Answer:** You must re-specify all trusted accounts; passing only a new account can remove previously trusted accounts.

**Question 11.** Why should you avoid deleting the `CDKToolkit` stack?

**Answer:** The stack owns the S3/ECR staging resources and IAM roles required by pipelines; deleting it can break future deployments.

**Question 12.** Why does CDK Pipelines use `crossAccountKeys`?

**Answer:** To encrypt the artifact bucket with KMS when deploying cross-account; account for the additional key cost.

**Question 13.** What does a CDK Pipelines Stage represent?

**Answer:** A deployment of the application consisting of one or more stacks in a target environment.

**Question 14.** Where should `ManualApprovalStep` be placed before production?

**Answer:** In the `pre` steps of the production Stage so approval happens before stack deployment.

**Question 15.** Why must code be committed and pushed before the first deployment of a self-mutating pipeline?

**Answer:** The pipeline updates itself from the source repository; uncommitted code may be ignored or overwritten by the pipeline.

**Question 16.** Why should `SecretValue.unsafePlainText` never be used for passwords?

**Answer:** Plaintext values can appear in source code, synthesized templates, or the CloudFormation console.

**Question 17.** What is `Template.fromStack` used for?

**Answer:** Creating a CDK Assertions template object from a stack's synthesized CloudFormation template to test resources and properties.

**Question 18.** Does `cdk diff` replace production change set reviews?

**Answer:** No. Diff is a tool to inspect changes; production still requires reviewing change sets, replacements, deletions, and data impacts.

**Question 19.** Does CloudFormation drift detection catch all runtime changes?

**Answer:** No. It detects only supported resources and properties; combine it with CloudTrail and operational checks.

**Question 20.** Why is infrastructure rollback insufficient when a database schema has changed?

**Answer:** Data migrations may not be reversible; you need backward-compatible migrations, backups, and a separate data rollback plan.

## 23. Production Readiness Checklist

- [ ] Account IDs and Regions for every Stage are verified.
- [ ] Environment configuration is validated and never falls back silently.
- [ ] CDK CLI, `aws-cdk-lib`, and `constructs` versions are pinned compatibly.
- [ ] `cdk.json` and `cdk.context.json` are committed.
- [ ] Stack boundaries reflect ownership and lifecycle.
- [ ] Cross-stack references are used only within appropriate account/Region scope.
- [ ] CIDRs do not overlap existing networks.
- [ ] Public/private/isolated subnets and routing are reviewed.
- [ ] IAM roles follow least privilege.
- [ ] Secrets live in Secrets Manager/SSM, never in source or templates.
- [ ] KMS key policies and runtime roles are tested.
- [ ] Production data has appropriate backups, PITR, and retention.
- [ ] `RemovalPolicy` and termination protection are explicitly configured.
- [ ] Resource tags include owner, environment, and cost center.
- [ ] Bootstrapping is complete for every account/Region.
- [ ] Bootstrap stacks have termination protection enabled.
- [ ] Cross-account trust and CloudFormation execution policies are reviewed.
- [ ] Bootstrap qualifiers and stack lifecycles are protected.
- [ ] Pipeline artifact encryption/`crossAccountKeys` is configured if needed.
- [ ] Pipeline source connections have scoped permissions.
- [ ] Pipeline synth runs Maven tests and `cdk synth`.
- [ ] CDK assertions and security/policy scans pass.
- [ ] Dev/staging smoke and integration tests pass.
- [ ] Production manual approval has an owner and clear criteria.
- [ ] Change sets/diffs are reviewed before production.
- [ ] Drift detection and CloudTrail auditing have owners.
- [ ] Application rollbacks and data migrations are tested.
- [ ] Multi-Region replication, KMS, secrets, and DNS failover are verified.
- [ ] RPO/RTO targets are defined and DR drills run periodically.
- [ ] Cost budgets, alarms, and cleanup policies are configured.

## 24. Official References

1. [Working with the AWS CDK in Java](https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-java.html) — project initialization, Maven, and Java idioms.
2. [AWS CDK projects](https://docs.aws.amazon.com/cdk/v2/guide/projects.html) — Java project structure and `cdk.json`.
3. [Environments for the AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/environments.html) — account/Region concepts.
4. [Configure environments to use with the AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/configure-env.html) — environment-specific and environment-agnostic stacks.
5. [Context values and the AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/context.html) — context lookups and repeatable synthesis.
6. [Bootstrap your environment for use with the AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping-env.html) — modern bootstrap resources and roles.
7. [Customize AWS CDK bootstrapping](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping-customizing.html) — trust and execution policies.
8. [cdk bootstrap command reference](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-bootstrap.html) — bootstrap CLI options.
9. [Deploying AWS CDK applications](https://docs.aws.amazon.com/cdk/v2/guide/deploy.html) — credentials, bootstrap, and deployment.
10. [CDK Pipelines](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.pipelines-readme.html) — Java pipelines, Stages, ShellStep, and approvals.
11. [Testing AWS CDK applications](https://docs.aws.amazon.com/cdk/v2/guide/testing.html) — unit tests and assertions.
12. [CDK Assertions](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.assertions-readme.html) — `Template`, `Match`, and resource assertions.
13. [SecretValue Java API](https://docs.aws.amazon.com/cdk/api/v2/java/software/amazon/awscdk/SecretValue.html) — secret references and avoiding plaintext.
14. [Get a value from AWS Secrets Manager](https://docs.aws.amazon.com/cdk/v2/guide/get-secrets-manager-value.html) — importing/referencing secrets in CDK.
15. [AWS CDK Construct Library](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib-readme.html) — constructs, props, and secret handling.
16. [Amazon VPC Construct Library](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2-readme.html) — VPC, subnets, and `fromLookup`.
17. [CDK Pipelines cross-account deployment](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.pipelines-readme.html) — `crossAccountKeys` and target environments.
18. [AWS CDK CLI reference](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd.html) — `synth`, `diff`, `deploy`, and `destroy`.
19. [AWS CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html) — detecting drift.
20. [AWS CDK best practices](https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html) — app structure, constructs, and lifecycle.
21. [DynamoDB Table.Builder Java API](https://docs.aws.amazon.com/cdk/api/v2/java/software/amazon/awscdk/services/dynamodb/Table.Builder.html) — configuring tables and point-in-time recovery specifications.
22. [AWS CodeConnections](https://docs.aws.amazon.com/dtconsole/latest/userguide/welcome-connections.html) — creating and managing repository connections.

---

**Conclusion:** CDK Java standardizes multi-environment infrastructure by sharing constructs and stacks while passing account/Region configurations explicitly. A production-ready capstone requires more than resource-creation code: it needs proper bootstrap/trust setup, least-privilege IAM, secret management, repeatable context, template tests, pipeline promotion, approvals, drift handling, rollbacks, and DR. Always synthesize and review before every deployment, roll out sequentially from dev through staging to production, and keep data migration and recovery plans independent from CloudFormation rollbacks.
