# Configuring Spring Boot by Environment and IAM Role

A Spring Boot service may run on a developer workstation, in CI, on Amazon ECS, Amazon EKS, or AWS Lambda. The same JAR file may need to call Amazon S3, SQS, DynamoDB, and Secrets Manager across every environment, yet the **bucket, queue, Region, endpoint, and permissions** differ. Hardcoding values in source code or placing AWS access keys in `application-prod.yml` makes deployments error-prone across environments and introduces credential exposure risks.

A sound design separates three concepts:

- **Spring profile** selects application configuration by environment, such as `dev`, `test`, `staging`, `prod`.
- **Externalized configuration** moves mutable values out to YAML/properties, environment variables, command-line arguments, Systems Manager Parameter Store, or Secrets Manager.
- **Runtime IAM role** defines the AWS identity that the process is allowed to assume. ECS task roles, EKS Pod Identity/IRSA, EC2 instance profiles, and Lambda execution roles supply temporary credentials to the AWS SDK.

**The `prod` profile does not create a production IAM role.** It only selects Spring configuration. AWS identity comes from where the application runs and the IAM trust/permission policies. Separating these two layers allows the same artifact to be deployed safely across multiple environments.

This lesson belongs to the **Java and Spring Boot Applications** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects application configuration with Regions/AZs, IAM, VPCs, compute, storage, databases, integration, and serverless toward deployments that are observable, resilient, and cost-controlled.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish between **Spring profiles**, externalized configuration, secrets, and AWS IAM roles.
2. Organize `application.yml`, `application-dev.yml`, and `application-prod.yml` without producing multiple builds.
3. Understand Spring Boot property source precedence and how environment variables override configuration.
4. Use `@ConfigurationProperties`, validation, and fail-fast behavior to verify configuration at startup.
5. Supply AWS credentials via `DefaultCredentialsProvider` and runtime IAM roles.
6. Distinguish **ECS task roles** from **task execution roles**, EKS Pod Identity from IRSA, Lambda execution roles, and EC2 instance profiles.
7. Use AWS Systems Manager Parameter Store/Secrets Manager with Spring Cloud AWS Config Data imports when appropriate.
8. Design least-privilege IAM, VPC connectivity, Region selection, and multi-account deployments.
9. Test across local/staging/production, verify actual caller identity with STS, and troubleshoot credentials/`AccessDenied` errors.
10. Build deployment workflows with rotation, observability, rollback, and zero secret exposure.

## 2. Configuration model: one artifact, many environments

An application should be built into **a single artifact deployable across multiple environments**. Each environment supplies different values via profiles or external configuration. You do not need to build `orders-api-dev.jar`, `orders-api-staging.jar`, and `orders-api-prod.jar` just because buckets or queues differ.

~~~mermaid
flowchart TD
    JAR["One Spring Boot JAR"] --> ENV{"Runtime environment"}
    ENV --> DEV["Local / dev"]
    ENV --> TEST["Test / staging"]
    ENV --> PROD["Production"]
    DEV --> CFG["Spring Environment<br/>profiles + external config"]
    TEST --> CFG
    PROD --> CFG
    CFG --> APP["ConfigurationProperties<br/>Application beans"]
    DEV --> IDDEV["Developer AWS profile / SSO"]
    TEST --> IDTEST["Test task/pod IAM role"]
    PROD --> IDPROD["Production task/pod/Lambda role"]
    IDDEV --> SDK["AWS SDK credentials provider"]
    IDTEST --> SDK
    IDPROD --> SDK
    APP --> SDK
    SDK --> AWS["S3 / SQS / DynamoDB / Secrets Manager"]
~~~

### 2.1. Classifying configuration data

| Data type | Examples | Appropriate management location |
|---|---|---|
| **Application defaults** | Pagination size, feature defaults, timeout logic | `application.yml` in source |
| **Environment-specific non-secret** | Bucket name, queue URL, endpoint, log level | Profile YAML, environment variables, Parameter Store |
| **Sensitive secrets** | DB password, API key, third-party token | Secrets Manager or an appropriate secret store |
| **AWS identity** | Permissions `s3:GetObject`, `sqs:SendMessage` | IAM role + IAM policy |
| **Deployment/runtime settings** | CPU/memory, task count, port, health checks | ECS task definition, EKS manifests, Lambda configuration |
| **Region/partition** | `ap-southeast-1`, `us-east-1` | Runtime config or AWS region provider |

**Do not treat IAM access keys as application properties.** Access keys/secret keys belong to the credential mechanism. Applications on AWS should receive temporary credentials from an IAM role; only local development typically uses developer-authenticated profiles/SSO.

### 2.2. Profiles are not a security boundary

The `dev` profile may select a test bucket and `DEBUG` logging; the `prod` profile selects the production bucket and `INFO` logging. However, if a production process accidentally receives credentials with permissions into another account, the `prod` profile cannot block those permissions. Security boundaries are **IAM roles, resource policies, SCPs, VPCs, and service-level authorization**, not profile names.

Do not write:

~~~yaml
spring:
  profiles:
    active: prod
aws:
  access-key: "AKIA..."
  secret-key: "..."
~~~

inside files packaged into the JAR. The active profile must be selected by the deployment environment; AWS identity must be supplied by the runtime.

## 3. Spring Boot profiles and externalized configuration

Spring Boot supports `application.properties` or `application.yaml` as default configuration and `application-{profile}.properties`/`application-{profile}.yaml` files for profile-specific overrides. Profiles can be enabled via environment variable, system property, or command line.

### 3.1. Recommended file layout

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

`application.yml` holds shared configuration:

~~~yaml
spring:
  application:
    name: orders-api

app:
  aws:
    region: ap-southeast-1
    catalog:
      bucket: orders-catalog-local
    orders:
      queue-url: http://localhost:4566/000000000000/orders-local
  features:
    enable-new-checkout: false

logging:
  level:
    root: INFO
~~~

`application-dev.yml` records only the necessary differences:

~~~yaml
app:
  aws:
    catalog:
      bucket: orders-catalog-dev
    orders:
      queue-url: https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-dev
  features:
    enable-new-checkout: true

logging:
  level:
    com.example.orders: DEBUG
~~~

`application-prod.yml` points to production resources:

~~~yaml
app:
  aws:
    catalog:
      bucket: orders-catalog-prod
    orders:
      queue-url: https://sqs.ap-southeast-1.amazonaws.com/444455556666/orders-prod
  features:
    enable-new-checkout: true

logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

The bucket/queue names in these examples are illustrative. **Never place database passwords, AWS access keys, private keys, or tokens inside profile files**, even in an `application-prod.yml` file with restricted Git access.

### 3.2. Activating profiles from the runtime

You can choose a profile without modifying source code:

~~~bash
# Linux/macOS shell
export SPRING_PROFILES_ACTIVE=dev
java -jar orders-api.jar
~~~

~~~powershell
# Windows PowerShell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar .\orders-api.jar
~~~

Or:

~~~bash
java -jar orders-api.jar --spring.profiles.active=prod
~~~

In an ECS task definition, Kubernetes Deployment, or Lambda configuration, set `SPRING_PROFILES_ACTIVE` per environment. Avoid making `prod` the default profile inside the JAR, because the same artifact could accidentally run in another environment.

### 3.3. Property source precedence

Spring Boot defines precedence rules across property sources; higher-precedence sources override lower ones. Common sources include:

| Source | Example | Usage |
|---|---|---|
| Default properties | `SpringApplication.setDefaultProperties` | Code-level default values |
| Config data inside JAR | `application.yml`, `application-prod.yml` | Defaults and profile configuration |
| Config data outside JAR | `./config/application-prod.yml` | Environment-mounted configuration |
| OS environment variables | `APP_AWS_REGION`, `SPRING_PROFILES_ACTIVE` | Container/task/pod runtime config |
| Java system properties | `-Dapp.aws.region=...` | JVM startup |
| Command-line arguments | `--app.aws.region=...` | Launch-time overrides |

The full order also includes sources such as `@PropertySource`, test properties, DevTools, and config data imports. Consult **Spring Boot Externalized Configuration** for your exact version when a value is unexpectedly overridden.

### 3.4. Important rule for spring.profiles.active

`spring.profiles.active` and `spring.profiles.default` may only be declared in **non-profile-specific documents**. Do not place `spring.profiles.active: prod` inside `application-prod.yml` or a YAML document that only activates once `prod` is already active. Select the profile from the deployment environment or command line.

### 3.5. Environment variable mapping

Spring Boot can bind the property:

~~~text
app.aws.catalog.bucket
~~~

from the environment variable:

~~~text
APP_AWS_CATALOG_BUCKET
~~~

Example overriding the bucket without modifying the JAR:

~~~bash
APP_AWS_CATALOG_BUCKET=orders-catalog-prod java -jar orders-api.jar
~~~

Environment variable names are typically uppercase with dots/hyphens replaced by underscores. When binding Map properties, conversion rules may lowercase keys; avoid case-sensitive Map keys when configuration comes from environment variables.

## 4. Binding configuration with @ConfigurationProperties

Avoid scattering dozens of `@Value` expressions across controllers and services. **@ConfigurationProperties** groups related properties into a strongly typed object that is easy to validate, test, and document.

### 4.1. Declaring a configuration record

~~~java
package com.example.orders.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.aws")
public record AwsApplicationProperties(
        @NotBlank String region,
        @NotNull @Valid Catalog catalog,
        @NotNull @Valid Orders orders) {

    public record Catalog(@NotBlank String bucket) {}

    public record Orders(@NotBlank String queueUrl) {}
}
~~~

Enable configuration properties scanning on the application:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Add the appropriate validation dependency for your Spring Boot version, such as **spring-boot-starter-validation**. When a required bucket or queue URL is missing, the application fails at startup rather than waiting until the first request errors out.

### 4.2. Injecting properties into services

~~~java
package com.example.orders.storage;

import com.example.orders.config.AwsApplicationProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AwsApplicationProperties properties;

    public CatalogService(AwsApplicationProperties properties) {
        this.properties = properties;
    }

    public String catalogBucket() {
        return properties.catalog().bucket();
    }
}
~~~

The application can inject these properties into AWS configuration beans to build clients, or let Spring Cloud AWS auto-configure service clients. Do not read environment variables directly in every business class; centralize them at the configuration boundary.

### 4.3. Validating endpoints and Regions

Some values require stricter checks than `@NotBlank`:

- The Region must be a valid AWS Region where the target service is supported.
- The queue URL must belong to the account/Region matching the environment.
- The bucket name must belong to the current environment, not a production bucket when running the `dev` profile.
- Endpoint overrides must only be enabled in `local`/`test` and must belong to a configured allowlist.
- Timeouts must be positive and within defined bounds.

You can write a **custom validator** or validate at startup. Avoid calling every AWS API just to validate config if doing so increases startup time and IAM permissions; choose checks aligned with your SLO and readiness model.

## 5. Secrets and configuration from AWS Systems Manager/Secrets Manager

Profile YAML is well-suited for non-secret values that change infrequently. For configuration requiring centralized governance, auditing, independent updates, and fine-grained access control, you can use:

- **AWS Systems Manager Parameter Store:** configuration such as queue paths, feature settings, non-secret endpoints, and `SecureString` values as needed.
- **AWS Secrets Manager:** DB passwords, third-party credentials, API tokens, and secrets requiring rotation.
- **Spring Cloud AWS Config Data integration:** loads values into the Spring Environment at bootstrap via `spring.config.import`.

### 5.1. Choosing the right storage type

| Value | Recommended storage | Example |
|---|---|---|
| Default retry count | `application.yml` / Parameter Store | `/config/orders-api/retry/max-attempts` |
| Environment-specific bucket name | Parameter Store or deployment env | `/config/orders-api/storage/catalog-bucket` |
| DB username/password | Secrets Manager or RDS-managed secret | `orders/prod/database` |
| External payment API token | Secrets Manager | `orders/prod/payment-provider` |
| AWS role permissions | IAM policy, not Parameter Store | `s3:GetObject` on bucket ARN |
| Region/runtime role | Runtime deployment configuration and IAM | `AWS_REGION`, ECS task role |

Do not put **AWS access keys/secret keys** into Secrets Manager just for the application to assume a role that the runtime already provides. Secrets Manager is for application or service secrets; IAM roles are the mechanism for granting AWS API permissions.

### 5.2. Spring Cloud AWS: selecting a compatible version

Spring Cloud AWS provides starters for core AWS integration, S3, SQS, Parameter Store, Secrets Manager, and other services. Use the **Spring Cloud AWS BOM** to keep modules aligned. Pick the branch compatible with your project's Spring Boot/Spring Cloud release train; for example, **Spring Cloud AWS 3.4.x** targets the **Spring Boot 3.5.x** line, while the **4.x** line targets the corresponding Spring Boot 4.x line. Check the official release matrix before upgrading.

Example Maven dependencies for Spring Cloud AWS 3.4.x:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>io.awspring.cloud</groupId>
      <artifactId>spring-cloud-aws-dependencies</artifactId>
      <version>3.4.x</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter</artifactId>
  </dependency>
  <dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-parameter-store</artifactId>
  </dependency>
  <dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
  </dependency>
</dependencies>
~~~

These are example coordinates; replace the version with a specific compatible release rather than using the literal string `3.4.x` as a Maven version. Add only the starters the application actually uses.

### 5.3. Importing Parameter Store into the Spring Environment

With Spring Cloud AWS 3.x, you can declare:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: "aws-parameterstore:/config/orders-api/"
~~~

Parameters under `/config/orders-api/` are loaded into the Spring Environment. **The trailing slash matters** when you want property names derived along the path hierarchy. If you need both shared config and app-specific config, multiple paths can be imported using the syntax supported by your Spring Cloud AWS version.

Example parameters:

~~~text
/config/orders-api/app/aws/catalog/bucket = orders-catalog-prod
/config/orders-api/app/aws/orders/queue-url = https://sqs.ap-southeast-1.amazonaws.com/444455556666/orders-prod
~~~

Once loaded, the values can bind into `AwsApplicationProperties`. The application's IAM role needs read permissions on the exact Parameter Store paths; if `SecureString` uses a customer-managed KMS key, corresponding decrypt permissions are required per policy.

### 5.4. Importing Secrets Manager

Example for a secret named `orders/prod/database`:

~~~yaml
spring:
  config:
    import: "aws-secretsmanager:orders/prod/database"
~~~

A JSON secret may contain:

~~~json
{
  "username": "orders_app",
  "password": "REPLACE_WITH_SECRET_VALUE",
  "host": "orders-db.example.ap-southeast-1.rds.amazonaws.com",
  "port": 5432
}
~~~

Spring Cloud AWS can expose secret properties in the Spring Environment for binding via `@Value` or `@ConfigurationProperties`, depending on the version's schema/loader. Secrets must never be printed to logs during binding or debugging.

### 5.5. Required vs. optional when a secret does not exist

By default, importing a missing secret can prevent the application from **starting up**. If a secret is genuinely optional, you can use the **optional:** prefix:

~~~yaml
spring:
  config:
    import: "optional:aws-secretsmanager:orders/dev/optional-integration"
~~~

Do not use `optional:` for DB passwords, encryption keys, or mandatory production credentials. If the application starts without a required secret, failing fast is far safer than serving traffic with misconfiguration.

### 5.6. Bootstrap dependency and IAM permissions

Config Data imports are processed during bootstrap. Therefore, the application must have **Region and AWS credentials early enough** to access Parameter Store/Secrets Manager before the context finishes initializing. In ECS/EKS/Lambda, attach the proper IAM role at runtime; do not wait for a bean created later to supply credentials to the config loader.

Typical minimum permissions needed:

- Parameter Store: `ssm:GetParameter`/`ssm:GetParameters` or `ssm:GetParametersByPath` on the exact ARN/path.
- `SecureString` with a customer-managed key: `kms:Decrypt` on the appropriate key, along with the key policy.
- Secrets Manager: `secretsmanager:GetSecretValue` on the specific secret ARN.
- Secret using a customer-managed key: `kms:Decrypt` on the corresponding key if needed.

**Do not grant `ssm:*`, `secretsmanager:*`, or `kms:*` account-wide** just to let Spring Boot start. Scope resource ARNs, path prefixes, and KMS keys explicitly.

## 6. AWS credentials provider: let the runtime supply identity

The AWS SDK requires credentials to sign API requests with SigV4. With AWS SDK for Java 2.x, **DefaultCredentialsProvider** looks up credentials through a chain of providers. If no provider is specified on a service client, the SDK uses the default chain.

### 6.1. Default credentials provider chain

Common sources in the search order of SDK for Java 2.x:

1. **Java system properties:** `aws.accessKeyId`, `aws.secretAccessKey`, `aws.sessionToken`.
2. **Environment variables:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`.
3. **Web identity token:** `AWS_WEB_IDENTITY_TOKEN_FILE` and `AWS_ROLE_ARN`, commonly used with EKS IRSA.
4. **Shared AWS profiles/config files:** IAM Identity Center SSO, role profiles, and other profile configurations.
5. **ECS container credentials:** credentials endpoint provided by the ECS agent for the task role.
6. **EC2 instance profile:** credentials via the EC2 Instance Metadata Service.

The chain stops at the first provider that yields valid credentials. This order matters: **a stale `AWS_ACCESS_KEY_ID` in the environment can take precedence over web identity/ECS/EC2 roles**, causing the application to use the wrong identity even when the correct IAM role is attached.

~~~mermaid
flowchart TD
    APP["AWS SDK client needs to sign request"] --> CHAIN["DefaultCredentialsProvider"]
    CHAIN --> SYS["1. JVM system properties"]
    SYS --> ENV["2. Environment variables"]
    ENV --> WEB["3. Web identity token"]
    WEB --> PROFILE["4. Shared profile / SSO"]
    PROFILE --> ECS["5. ECS task credentials"]
    ECS --> EC2["6. EC2 instance profile"]
    SYS --> FOUND["Valid credentials"]
    ENV --> FOUND
    WEB --> FOUND
    PROFILE --> FOUND
    ECS --> FOUND
    EC2 --> FOUND
    FOUND --> SIGN["SigV4 request signing"]
~~~

The diagram illustrates the lookup chain: when the current provider has no valid credentials, the SDK tries the next provider. If an unintended credential source sits earlier in the chain, it can shadow the role credentials operators intended to use.

### 6.2. Creating service clients without hardcoding credentials

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3 = S3Client.builder()
    .region(Region.AP_SOUTHEAST_1)
    // Do not pass access key/secret key.
    // The SDK uses DefaultCredentialsProvider.
    .build();
~~~

This is generally the right setup for workloads running on AWS. If Spring Cloud AWS starters are used, the starter can auto-configure Region and credentials providers for integrations; avoid creating a second credentials chain without a clear requirement.

### 6.3. Explicit DefaultCredentialsProvider to make intent clear

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

SqsClient sqs = SqsClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .credentialsProvider(DefaultCredentialsProvider.create())
    .build();
~~~

Specifying the provider explicitly does not change the default credential source; it clarifies the intent to use the chain. If the application creates providers or HTTP clients with independent lifecycles, manage/close them under a clear owner per the SDK version guidance.

## 7. Local development: using AWS IAM Identity Center/SSO profiles

Developer machines should not use production role access keys. Use **AWS IAM Identity Center** or a profile granted development permissions by the organization.

### 7.1. Profile in AWS config

Example configuration in the shared config file:

~~~ini
[profile orders-dev]
sso_session = company
sso_account_id = 111122223333
sso_role_name = Developer
region = ap-southeast-1
output = json

[sso-session company]
sso_start_url = https://example.awsapps.com/start
sso_region = ap-southeast-1
sso_registration_scopes = sso:account:access
~~~

Account, role, and URL values are placeholders. The organization must grant corresponding Identity Center access. Log in and run the application:

~~~bash
aws sso login --profile orders-dev
export AWS_PROFILE=orders-dev
export AWS_REGION=ap-southeast-1
export SPRING_PROFILES_ACTIVE=dev
java -jar orders-api.jar
~~~

AWS SDK for Java 2.x `ProfileCredentialsProvider` supports IAM Identity Center configuration in the shared config file per SDK version. When the SSO session expires, log in again via the CLI; never copy SSO cache tokens into application configuration files.

For AWS SDK for Java 2.x using an IAM Identity Center profile, add the corresponding SSO modules to your build if not already pulled in by another starter:

~~~xml
<dependency>
  <groupId>software.amazon.awssdk</groupId>
  <artifactId>sso</artifactId>
</dependency>
<dependency>
  <groupId>software.amazon.awssdk</groupId>
  <artifactId>ssooidc</artifactId>
</dependency>
~~~

Manage versions with the AWS SDK BOM. If the required modules are missing, `ProfileCredentialsProvider` may fail to resolve SSO profiles even when the shared config file is valid.

### 7.2. Precedence issues that cause local confusion

If a developer's machine has both `AWS_PROFILE=orders-dev` and `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, the default chain can pick environment credentials before the shared profile. When seeing the wrong account:

1. Check AWS caller identity with the AWS CLI and from the process/app itself if possible.
2. Check Java system properties `aws.accessKeyId`/`aws.secretAccessKey`.
3. Check environment variables `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN`.
4. Check `AWS_PROFILE` and the SSO session.
5. Verify the granted account/role and Region.

Do not work around this by pasting new access keys into `application-dev.yml`. Remove unwanted credential environment variables and use the proper profile/SSO.

### 7.3. Checking identity with STS

~~~bash
aws sts get-caller-identity --profile orders-dev
~~~

Output includes `Account`, `Arn`, and `UserId`. Verify the right account/role before running integration tests or write operations. This command is **read-only** and does not expose secret access keys.

## 8. Production IAM roles by compute runtime

In production, IAM roles are bound to the **runtime identity**. The application simply uses a compatible credentials provider chain; the platform supplies temporary credentials and the SDK refreshes them per the provider mechanism.

### 8.1. ECS: task role and task execution role

These are two distinct roles:

| Role | Who uses it? | Example permissions |
|---|---|---|
| **Task execution role** | ECS/Fargate agent to prepare/run the task | Pull images from ECR, send logs to CloudWatch, fetch secrets referenced in the task definition |
| **Task role** | Application code inside the container | `s3:GetObject`, `sqs:SendMessage`, `dynamodb:GetItem` on required resources |

**The Java application needs the task role** when calling the AWS SDK. Do not attach business S3/SQS permissions to the task execution role and expect the container to inherit them. The task execution role authorizes the agent for infrastructure actions; the task role supplies credentials to the application.

Example ECS task definition (fragment):

~~~json
{
  "family": "orders-api",
  "taskRoleArn": "arn:aws:iam::444455556666:role/orders-api-task-role",
  "executionRoleArn": "arn:aws:iam::444455556666:role/orders-api-execution-role",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:1.0.0",
      "essential": true,
      "environment": [
        {"name": "SPRING_PROFILES_ACTIVE", "value": "prod"},
        {"name": "AWS_REGION", "value": "ap-southeast-1"}
      ]
    }
  ]
}
~~~

This is an illustrative fragment; an actual task definition also needs CPU/memory, network mode, ports, logging, health checks, and secret configuration if applicable. The task role is provided by ECS via the container credentials endpoint; the SDK default chain finds credentials automatically. Never read the credential endpoint and write temporary keys to logs.

### 8.2. EKS: Pod Identity or IRSA

**EKS Pod Identity** and **IAM Roles for Service Accounts (IRSA)** both allow binding an IAM role to a Kubernetes service account so each workload gets dedicated permissions.

| Criterion | EKS Pod Identity | IRSA |
|---|---|---|
| Mechanism | EKS association + Pod Identity Agent | IAM OIDC provider + service account annotation/token |
| Trust principal | `pods.eks.amazonaws.com` | Cluster's OIDC federated principal |
| Credentials delivery | Agent provides credentials to the Pod | Web identity token file and STS `AssumeRoleWithWebIdentity` |
| Scope | Service account bound via association to role | Service account annotated with role ARN |
| SDK | Supported by default provider chain per version | `WebIdentityTokenFileCredentialsProvider` in the chain |

With **Pod Identity**, install the Pod Identity Agent and create an association between the cluster/namespace/service account and the IAM role. With **IRSA**, an OIDC provider is needed for the cluster and the trust policy must restrict the exact service account subject and audience. Standardize on one mechanism per cluster; do not grant broad permissions to the node role in place of a workload role.

Web identity/`AssumeRole` flows require the AWS SDK STS module on the classpath. When using the SDK directly, add `software.amazon.awssdk:sts` with the same BOM version; Spring Cloud AWS starters may already manage this dependency depending on integration/version.

Example Kubernetes service account using IRSA:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: production
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::444455556666:role/orders-api-irsa-role
~~~

With EKS Pod Identity, the association is created in EKS; do not use this IRSA annotation in place of an association. In both cases, the Java application uses the default credentials provider chain and does not hardcode the role ARN in source code.

### 8.3. Lambda execution role

A Lambda function has an **execution role** assumed by Lambda. That role holds the permissions required by the handler code, such as reading an S3 prefix or sending messages to an SQS queue. The AWS SDK obtains temporary credentials within the execution environment.

- Do not call STS `AssumeRole` to re-assume the execution role itself unless cross-account/role chaining is required.
- Use a separate role for each function group with distinct permissions.
- Configure appropriate timeout/memory/concurrency and network access.
- If the function is in private VPC subnets, ensure paths to AWS APIs via NAT or required VPC endpoints.

### 8.4. EC2 instance profile

Java applications on EC2 receive credentials from an IAM role attached via an **instance profile**. The SDK queries the EC2 Instance Metadata Service when earlier providers lack credentials. Enable **IMDSv2**, limit hop/metadata access, and prevent untrusted containers from accessing the instance role. For ECS on EC2, prefer a dedicated task role for container applications.

### 8.5. Do not use one IAM role across all environments

| Environment | Recommended identity | Typical permissions |
|---|---|---|
| Local developer | IAM Identity Center SSO profile | Dev buckets/queues/test resources |
| CI pipeline | OIDC federation/assume role for pipeline | Build/deploy artifacts; no business runtime permissions needed |
| Test | Dedicated ECS task role/EKS service account role | Test tables, queues, buckets |
| Staging | Dedicated role for staging account/resources | Production-like yet isolated data |
| Production | Production task/pod/Lambda/instance role | Only required business permissions |

Separating roles limits blast radius and clearly audits which workload calls AWS APIs. Never share an IAM user's access key across developers, CI, and production.

## 9. IAM policies: granting the exact permissions needed

An IAM role has two distinct parts:

- **Trust policy** defines who/which service can assume the role.
- **Permissions policy** defines what the role can do on AWS resources once assumed.

An ECS task role has a trust policy for `ecs-tasks.amazonaws.com`, while its permissions policy might allow only reading objects in one S3 bucket and sending messages to a specific SQS queue.

### 9.1. Example trust policy for an ECS task role

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowEcsTasks",
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

This trust policy only illustrates the ECS tasks service principal. In real deployments, apply role trust conditions and guardrails suited to your account/organization; never reuse a Lambda/EKS trust policy for ECS.

### 9.2. Permissions policy for a Spring Boot service

Suppose `orders-api` needs to read catalog objects and send orders to a queue:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadCatalogOnly",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::orders-catalog-prod/*"
    },
    {
      "Sid": "SendOrdersOnly",
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:444455556666:orders-prod"
    }
  ]
}
~~~

The policy above is an example identity policy for the **task role**; add only the actions the code actually invokes. If the app lists buckets, reads KMS-encrypted objects, or uses SSE-KMS, additional corresponding permissions may be required; grant them only when truly needed. Resource ARNs must point to the exact environment's resources.

### 9.3. Do not confuse runtime permissions with deployment permissions

| Principal | Responsibility | Example permissions |
|---|---|---|
| **Application task/pod role** | Business logic execution | `s3:GetObject`, `sqs:SendMessage`, `dynamodb:UpdateItem` |
| **CI/CD deploy role** | Updating ECS/EKS/Lambda resources | Update service/deployment, pass the right task/execution role |
| **ECS task execution role** | Agent pulls images/writes logs/reads task definition secrets | ECR pull, CloudWatch Logs, secret injection |
| **Platform administrator** | Creating roles, trust policies, networking, service resources | Scoped IAM/ECS/EKS/VPC administration |

Do not include `CreateRole`, `AttachRolePolicy`, or broad `iam:PassRole` in an application task role. The application runtime does not need permissions to alter its own IAM role.

### 9.4. EKS Pod Identity trust policy

EKS Pod Identity uses the service principal **pods.eks.amazonaws.com** and the actions **sts:AssumeRole** and **sts:TagSession**. Associations can be restricted using request tags for cluster/namespace/service account per EKS guidance. For IRSA, the trust policy uses an OIDC provider and subject/audience conditions. The two trust models are not identical; copying the wrong one will prevent Pods from receiving credentials.

## 10. Region selection and configuring AWS clients

Region affects endpoints, resource ARNs, service availability, data residency, and latency. A standard SDK client is configured with a Region at build time; do not take a Region from user requests and mutate it arbitrarily per call.

### 10.1. Region provider in AWS SDK for Java 2.x

The default region provider chain typically checks:

1. Java system property **aws.region**.
2. Environment variable **AWS_REGION**.
3. Shared AWS config/profile.
4. EC2 instance metadata when running on EC2.

With Spring Cloud AWS, a static Region can be set via **spring.cloud.aws.region.static**; otherwise, the starter uses the region provider chain per version. Do not let an app property and `AWS_REGION` point to two different Regions unintentionally.

Example Spring Cloud AWS configuration:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

If using the SDK directly, bind Region from application properties:

~~~java
import com.example.orders.config.AwsApplicationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class AwsClientConfiguration {
    @Bean
    S3Client s3Client(AwsApplicationProperties properties) {
        return S3Client.builder()
            .region(Region.of(properties.region()))
            .build();
    }
}
~~~

The SDK automatically uses the default credentials chain since no access key is passed. If using Spring Cloud AWS auto-configuration for `S3Client`, do not declare a second conflicting `S3Client` bean; only customize a bean when intentionally overriding.

### 10.2. When multiple Regions are required

For example, an application serving data in `ap-southeast-1` and `ap-northeast-1`:

- Create a **separate client per Region** with the matching endpoint/signing Region.
- Store bucket/table/queue ARNs in config per Region instead of arbitrarily concatenating ARN strings.
- Verify IAM permissions on resources in both Regions.
- Design retry/failover and data consistency; changing Region does not automatically replicate data.
- For cross-Region S3 access, check data transfer, KMS key Region, and bucket policies.

Do not change the Region on the same client per request by mutating the builder or overriding endpoints arbitrarily.

### 10.3. Cross-account access with AssumeRole

If a production service in Account A needs to read a resource in Account B, the typical pattern includes:

1. The runtime role in Account A has `sts:AssumeRole` on the target role ARN.
2. The target role in Account B has a trust policy allowing the source role from Account A.
3. The target role has a permissions policy granting access only to the target resource.
4. The Java SDK uses an STS AssumeRole credentials provider to automatically refresh temporary credentials.

Do not grant `sts:AssumeRole` on a wildcard if only one target role is needed. If the target account's resource policy also needs to allow the source principal, configure both sides per service requirements.

## 11. VPC connectivity for Spring Boot applications

An IAM policy allowing API calls does not mean the application has a network path to the AWS service endpoint. In private subnets, routing, DNS, security groups, and VPC endpoints must be designed.

~~~mermaid
flowchart TD
    APP["Spring Boot ECS task / EKS Pod<br/>Private subnet"] --> DNS["VPC DNS resolution"]
    DNS --> VPCE["VPC endpoint"]
    DNS --> NAT["NAT Gateway / egress path"]
    VPCE --> S3["S3 Gateway endpoint"]
    VPCE --> API["Interface endpoints<br/>SQS / STS / SSM / Secrets Manager"]
    NAT --> PUBLIC["AWS public service endpoints<br/>HTTPS"]
    S3 --> IAM["IAM + bucket/resource policies"]
    API --> IAM
    PUBLIC --> IAM
~~~

### 11.1. Verifying each layer

| Layer | What to verify |
|---|---|
| **Subnet/route** | Private subnet has a route to NAT or the appropriate VPC endpoint |
| **Security group** | Egress TCP 443 and DNS are allowed per policy |
| **NACL** | Inbound/outbound ephemeral ports are not blocked |
| **DNS** | VPC DNS support/hostnames, private DNS for interface endpoints |
| **VPC endpoint policy** | Allows the actions/resources the application needs |
| **IAM** | Runtime role has the appropriate identity policy |
| **Resource policy** | S3 bucket/SQS queue/secret policy has no explicit Deny |
| **KMS** | Key policy/grants allow decrypt when the service/resource needs it |

### 11.2. Interface endpoints and gateway endpoints

S3 typically uses a **Gateway VPC endpoint**; services like SQS, STS, Systems Manager, and Secrets Manager can use **Interface VPC endpoints** depending on availability/Region. When using Spring Cloud AWS Parameter Store/Secrets Manager at bootstrap, private subnets need network reachability to those endpoints before the application context completes initialization.

A VPC endpoint keeps service traffic on a private network path, but **does not replace IAM** and does not automatically allow all actions. Endpoint policies can restrict resources; bucket/queue/secret policies can also deny requests.

### 11.3. When an app in a private subnet cannot call Secrets Manager

Check in order: correct Region/endpoint, DNS resolving the interface endpoint, endpoint SG allowing TCP 443 from the app SG, route/NACL, endpoint policy, task/pod role having `GetSecretValue`, secret resource policy, and KMS key permissions. Never assign public IPs or open security groups to the entire Internet just to fix the error.

## 12. Spring Cloud AWS auto-configuration vs. direct AWS SDK

There are two ways to integrate AWS APIs into Spring Boot:

1. **Spring Cloud AWS starters** auto-configure certain AWS SDK clients and Spring integrations.
2. **AWS SDK for Java 2.x directly** when the application wants explicit control over client beans, HTTP transport, retries, or does not need Spring Cloud AWS.

Do not mix both approaches for the same client if it creates duplicate configuration.

### 12.1. Spring Cloud AWS core

The Spring Cloud AWS core starter can auto-configure **AwsCredentialsProvider** and **AwsRegionProvider** for the application context. By default, the credentials provider uses the AWS SDK default chain. Region can come from the provider chain or be explicitly set via:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Starters such as S3/SQS/DynamoDB can supply service integrations and auto-configured clients. Property names, behaviors, and dependencies vary across Spring Cloud AWS versions; check the reference docs for your exact release.

### 12.2. Avoiding static credentials properties in production

Spring Cloud AWS includes properties to configure static access keys/secret keys for special use cases. Do not use them in ECS/EKS/Lambda/EC2 production when a runtime IAM role can supply temporary credentials. Never declare:

~~~yaml
spring:
  cloud:
    aws:
      credentials:
        access-key: "..."
        secret-key: "..."
~~~

in `application-prod.yml` or deployment manifests. If local development needs SSO, use `AWS_PROFILE`/shared config; if production needs a role, use a runtime role.

### 12.3. Using the AWS SDK directly for custom clients

If not using a Spring Cloud AWS auto-configured client, create a client bean:

~~~java
import com.example.orders.config.AwsApplicationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

@Configuration
public class SqsConfiguration {
    @Bean
    SqsClient sqsClient(AwsApplicationProperties properties) {
        return SqsClient.builder()
            .region(Region.of(properties.region()))
            .build();
    }
}
~~~

Omit credentials so the SDK uses the provider chain. Clients should be shared beans tied to the application lifecycle; never build a client per message or HTTP request. When customizing HTTP transport, timeouts, or retries, configure the bean under a clear single owner.

### 12.4. Checking the version matrix

Spring Cloud AWS 2.x used legacy package/property names and targeted Spring Boot 2.x; Spring Cloud AWS 3.x moved to AWS SDK v2 and Spring Boot 3.x; the 4.x branch targets Spring Boot 4.x per the release matrix. Do not mix 2.x property prefixes with 3.x/4.x.

Example property prefix migration:

| Spring Cloud AWS 2.x | Spring Cloud AWS 3.x |
|---|---|
| `cloud.aws.credentials.access-key` | `spring.cloud.aws.credentials.access-key` |
| `cloud.aws.credentials.secret-key` | `spring.cloud.aws.credentials.secret-key` |
| `aws.paramstore.region` | `spring.cloud.aws.parameterstore.region` |
| `aws.secretsmanager.region` | `spring.cloud.aws.secretsmanager.region` |

These are a few examples of changed properties; review the full migration guide before upgrading.

## 13. Deployment configuration for ECS, EKS, and Lambda

Profiles and environment variables should be passed by the **deployment platform**, not baked back into the image. Runtime roles are attached independently of profiles.

### 13.1. ECS/Fargate: environment and task role

A task definition fragment might set:

~~~json
{
  "family": "orders-api",
  "taskRoleArn": "arn:aws:iam::444455556666:role/orders-api-task-role",
  "executionRoleArn": "arn:aws:iam::444455556666:role/orders-api-execution-role",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:1.0.0",
      "environment": [
        {"name": "SPRING_PROFILES_ACTIVE", "value": "prod"},
        {"name": "AWS_REGION", "value": "ap-southeast-1"},
        {"name": "APP_AWS_CATALOG_BUCKET", "value": "orders-catalog-prod"}
      ]
    }
  ]
}
~~~

`taskRoleArn` is the Java application's identity; `executionRoleArn` is the ECS agent's identity. If the task definition injects secrets into the environment, permission to fetch secrets belongs to the execution role as handled by the ECS agent; if Java calls Secrets Manager itself, the application task role needs `GetSecretValue`. Keep these two paths distinct when granting IAM.

### 13.2. EKS: profile and service account

Example deployment referencing a service account linked to an IAM role:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: example/orders-api:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: AWS_REGION
              value: ap-southeast-1
            - name: APP_AWS_CATALOG_BUCKET
              value: orders-catalog-prod
~~~

The service account must have an IRSA annotation or EKS Pod Identity association configured before the Pod starts. Setting `serviceAccountName` alone does not grant IAM permissions. During rollout, verify that new Pods receive credentials from the intended workload role.

### 13.3. Lambda: environment variables and execution role

In Lambda configuration:

- Set **SPRING_PROFILES_ACTIVE=prod** and non-secret settings.
- Attach a least-privilege execution role.
- Choose memory/timeout/concurrency suited to Spring startup and workload.
- Instantiate AWS SDK clients outside the handler when the runtime reuses execution environments.
- When using Spring Cloud Function/AWS adapters, check how the adapter manages the application context and cold starts for your version.

Never embed production credentials in Lambda environment variables. If Lambda needs secrets, use Secrets Manager/Parameter Store or an appropriate secret integration; restrict permissions and never log secret values.

### 13.4. Do not bake profiles into the Docker image

A production-ready Docker image should be environment-agnostic:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/orders-api.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The platform supplies `SPRING_PROFILES_ACTIVE`, `AWS_REGION`, non-secret application settings, and the IAM role when running the container. The image tag/digest is promoted across environments after testing; never rebuild the image just to change a bucket or queue.

## 14. CI/CD identity and application runtime identity

The CI pipeline needs **build/deploy** permissions, whereas the Spring Boot process needs **business runtime** permissions. These two identities should not be merged.

~~~mermaid
flowchart TD
    DEV["Developer / Git repository"] --> CI["CI pipeline"]
    CI --> OIDC["OIDC federation / deploy role"]
    OIDC --> DEPLOY["Deploy ECS/EKS/Lambda"]
    DEPLOY --> RUNTIME["Application runtime"]
    RUNTIME --> ROLE["Task / Pod / Lambda IAM role"]
    ROLE --> AWS["S3 / SQS / DynamoDB / Secrets Manager"]
~~~

### 14.1. The CI role only holds deployment permissions

The CI role may need to read the artifact registry, update ECS services/task definitions, or update Kubernetes manifests. It does not need permissions to submit orders or read production customer data just because the application has them.

### 14.2. Use OIDC federation instead of long-lived access keys

CI platforms can issue OIDC tokens to assume an AWS role, with trust policies scoped to repository, branch, tag, or environment. Once deployed, the runtime assumes its own role from ECS/EKS/Lambda. Never copy temporary credentials from CI into Docker images or application config files.

### 14.3. iam:PassRole must be scoped

The deploy role may need `iam:PassRole` to attach task/execution roles or Lambda execution roles to resources. Allow passing only the specific approved role ARNs with service-appropriate conditions. Do not grant `iam:PassRole` on a wildcard if the pipeline only deploys one application.

### 14.4. Promoting across environments

1. Build the JAR/image once and produce an immutable version/digest.
2. Run unit/integration tests.
3. Deploy to test with a test IAM role and test resources.
4. Promote the same artifact to staging and run smoke/load/security tests.
5. Production approval/deployment uses the deploy role; the deployed app receives the production task/pod/Lambda role.
6. Monitor health/metrics and roll back the version on failure.

**Same artifact, different configuration and IAM roles.** Never promote an `application-prod.yml` containing credentials from staging.

## 15. Secret rotation and updating configuration while running

Secrets Manager can rotate credentials, yet **rotating a secret does not mean every Spring bean holding the old value updates automatically**.

### 15.1. Imported configuration is typically loaded at bootstrap

When the Spring Cloud AWS Config Data loader imports Parameter Store/Secrets Manager, values are added to the Spring Environment during application configuration. If a password changes after the context has started, beans that already bound the old value may keep holding it until a refresh/reload mechanism or application restart occurs.

Do not assume `spring.config.import` automatically syncs every secret rotation into every running object. Read the reload documentation for your exact Spring Cloud AWS version and test the lifecycle of connection pools and secret consumers.

### 15.2. Three secret update strategies

| Strategy | How it works | When suitable |
|---|---|---|
| **Restart/redeploy** | Rotate the secret, then roll out new task/pod/function instances | Stateless apps with a controlled deployment pipeline |
| **Explicit refresh/reload** | Configured reload mechanism updates Environment/beans per framework support | Apps needing runtime config changes with tested bean refresh |
| **Fetch secret at use/connection time** | Dedicated secret provider/cache fetches the current value when opening a new connection | DB credentials or integrations needing independent rotation |

For database passwords, the connection pool can continue using existing connections while **new connections** require the updated password. During rotation, test pool eviction, connection lifetime, retries, and transitions between old/new credentials.

### 15.3. Secrets in ECS task definitions

If an ECS task definition injects secrets into the environment, the secret value is resolved when the task launches. When the secret changes, running tasks do not automatically receive the new environment value; you must **start/redeploy new tasks** per procedure. If the application calls Secrets Manager itself, the task role needs `GetSecretValue` and the app must implement a caching/refresh strategy.

### 15.4. Rotation must not leak secrets

- Never log the full Environment, `ConfigurationProperties`, or `SecretString`.
- Do not enable public Actuator `env`/`configprops` endpoints.
- Never pass passwords via command-line arguments, Docker build args, or Git.
- Use Secrets Manager version stages and audit API calls.
- Only refresh when the secret is valid; if a refresh fails, never overwrite the active value with empty data.
- Alert on rotation failures, expiring secrets, or applications holding an old version too long.

## 16. Fail-fast, health checks, and readiness

Applications should catch misconfigurations before serving traffic, without turning every transient dependency issue into an uncontrolled startup failure.

### 16.1. Distinguishing required config from dependency readiness

| Check | Appropriate timing | Example |
|---|---|---|
| **Config binding/validation** | Startup | Bucket name, queue URL, Region, positive timeout |
| **Credential source exists** | Startup or first call | Runtime has role/profile credentials |
| **IAM permission** | Smoke test or API call | Role is permitted to send SQS messages |
| **Network connectivity** | Readiness/monitoring per design | VPC endpoint DNS/route |
| **Downstream availability** | Readiness/health with timeouts and proper semantics | S3/SQS/DB temporarily unavailable |
| **Business invariants** | Request/job execution | Order state, tenant permissions |

Do not call numerous AWS APIs synchronously on every health check; that generates load and couples the health endpoint to non-critical services. Use short timeouts, cache health status, and separate liveness from readiness.

### 16.2. Spring Boot Actuator

Health endpoints can be enabled for orchestrator process checks:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

Expose only necessary endpoints; protect the management port/path and never expose `env`/`configprops`/`beans`/`heapdump` to the Internet. Liveness indicates the process is alive; readiness indicates the instance can receive traffic per application criteria.

### 16.3. Do not log sensitive configuration at startup

A safe startup log might record:

~~~text
Application started
profile=prod
region=ap-southeast-1
awsAccount=444455556666
runtimeRole=orders-api-task-role
~~~

Log only approved account/role metadata; never log access keys, session tokens, `SecretString`, passwords, the full environment, or config file contents. If IAM identity verification is needed, call STS `GetCallerIdentity` in a controlled manner and log redacted ARN/account fields.

### 16.4. Readiness does not replace retries

If SQS briefly throttles, the service might still handle HTTP read operations. Marking the entire application's readiness DOWN when only a secondary dependency fails is not always warranted. Classify critical dependencies per endpoint/feature; use circuit breakers, bounded retries, and degraded modes where appropriate.

## 17. Multi-account, cross-Region, and environment isolation

An organization may maintain separate accounts for development, staging, production, and security/logging. Spring Boot config should express **which environment's resources** to use, while IAM determines which roles may access that account/resource.

### 17.1. Config path structure

A Parameter Store path convention could be:

~~~text
/orders-api/dev/app/aws/catalog/bucket
/orders-api/dev/app/aws/orders/queue-url
/orders-api/staging/app/aws/catalog/bucket
/orders-api/staging/app/aws/orders/queue-url
/orders-api/prod/app/aws/catalog/bucket
/orders-api/prod/app/aws/orders/queue-url
~~~

Each environment's IAM role may read only its corresponding path. Do not grant `GetParametersByPath` across all of `/orders-api/` to every runtime role.

### 17.2. Account separation reduces blast radius

| Account | Example resources | Runtime role |
|---|---|---|
| Dev | Dev S3 buckets, test queues, sandbox DB | `orders-api-dev-task-role` |
| Staging | Staging buckets/queues/snapshot DB data | `orders-api-staging-task-role` |
| Production | Production data stores and event queues | `orders-api-prod-task-role` |
| Shared security | Audit/log archive, central KMS/logging | Approved roles/automation only |

Do not just switch to the `prod` profile; you must switch **account, resource ARNs, task/pod role, KMS keys, secret ARNs, and network paths**.

### 17.3. Cross-account AssumeRole

~~~mermaid
flowchart LR
    APP["Orders API<br/>Account A runtime role"] --> STS["AWS STS AssumeRole"]
    STS --> TARGET["Read-only role<br/>Account B"]
    TARGET --> RESOURCE["S3 / DynamoDB<br/>Account B resources"]
    APP --> BASE["Account A resources"]
~~~

The target role in Account B must trust the source role; the source role needs `sts:AssumeRole`; the target role's permissions cover only required resources. The SDK uses **StsAssumeRoleCredentialsProvider** to cache/refresh temporary credentials. Never call `AssumeRole` manually on every API request.

### 17.4. Cross-Region does not automatically create DR

Changing `AWS_REGION` from `ap-southeast-1` to `ap-northeast-1` does not replicate data, queues, or secrets. You must design replication/backups, per-Region KMS keys, endpoints, DNS, IAM resource ARNs, and application configuration. Test actual failover to prove RTO/RPO.

## 18. Verifying configuration and IAM identity with the AWS CLI

The commands below primarily read metadata and do not alter resources. Run them with the profile/role for the target environment; never print secret values or credentials to terminal logs.

### 18.1. Checking caller identity and Region

~~~bash
aws sts get-caller-identity
aws configure list-profiles
aws configure get region --profile orders-dev
~~~

**get-caller-identity** reveals the actual `Account`, `Arn`, and `UserId`. **configure list-profiles** only lists profile names; it does not print access keys. Checking Region from a CLI profile does not prove the Spring Boot application uses the same Region if another property source overrides it.

### 18.2. Checking ECS task definition roles

~~~bash
aws ecs describe-task-definition \
  --task-definition orders-api \
  --query 'taskDefinition.{TaskRole:taskRoleArn,ExecutionRole:executionRoleArn,Family:family,Revision:revision}' \
  --output json
~~~

Cross-check `TaskRoleArn` and `ExecutionRoleArn` against reviewed policies. If tasks are running on ECS, also inspect which revision the service/tasks are running; registering a new task definition without updating the service leaves workloads on the old revision.

### 18.3. Checking EKS Pod Identity associations

~~~bash
aws eks list-pod-identity-associations \
  --cluster-name orders-prod \
  --region ap-southeast-1 \
  --output json
~~~

For IRSA, check the service account annotation, OIDC provider, and role trust policy. Listing Pod Identity associations does not prove a Pod uses the right service account; verify the Kubernetes Pod spec and runtime caller identity.

### 18.4. Checking secret metadata without reading secret values

~~~bash
aws secretsmanager describe-secret \
  --region ap-southeast-1 \
  --secret-id orders/prod/database \
  --query '{Name:Name,Arn:ARN,KmsKey:KmsKeyId,RotationEnabled:RotationEnabled,LastRotated:LastRotatedDate}' \
  --output json
~~~

Do not run `get-secret-value` during routine audits when you do not need to read the password. If permission testing is required, run it in a controlled environment and never send `SecretString` to terminal recordings, CI output, or tickets.

### 18.5. Checking Parameter Store paths

~~~bash
aws ssm describe-parameters \
  --region ap-southeast-1 \
  --parameter-filters Key=Path,Option=Recursive,Values=/orders-api/prod/ \
  --query 'Parameters[].{Name:Name,Type:Type,Version:Version,LastModified:LastModifiedDate}' \
  --output table
~~~

This command only lists metadata. For `SecureString`, values remain protected; do not use `GetParameter --with-decryption` to dump sensitive values into output if the goal is solely checking paths and permissions.

### 18.6. Simulating IAM policies when authorized

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::444455556666:role/orders-api-task-role \
  --action-names s3:GetObject sqs:SendMessage \
  --resource-arns arn:aws:s3:::orders-catalog-prod/sample.json arn:aws:sqs:ap-southeast-1:444455556666:orders-prod \
  --output json
~~~

The policy simulator helps verify certain identity policy outcomes and IAM conditions. It does not replace real-world testing; resource policies, SCPs, VPC endpoint policies, KMS key policies, networking, and service-specific behaviors must still be evaluated.

## 19. Testing configuration and IAM per environment

Do not wait until production to discover the app is using the wrong account or role. Each environment needs a test suite verifying **profile, Region, resource names, and caller identity**.

### 19.1. Unit testing ConfigurationProperties

Test validation using a test context:

~~~java
import com.example.orders.config.AwsApplicationProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AwsApplicationPropertiesTest {
    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void bindsRequiredProperties() {
        contextRunner
            .withPropertyValues(
                "app.aws.region=ap-southeast-1",
                "app.aws.catalog.bucket=orders-catalog-test",
                "app.aws.orders.queue-url=https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-test"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                AwsApplicationProperties properties =
                    context.getBean(AwsApplicationProperties.class);
                assertThat(properties.catalog().bucket())
                    .isEqualTo("orders-catalog-test");
            });
    }

    @EnableConfigurationProperties(AwsApplicationProperties.class)
    static class TestConfig {}
}
~~~

This test verifies binding and validation of non-secret properties. No live AWS connection is needed for unit tests.

### 19.2. Testing property precedence

Write tests for cases such as:

- `application.yml` provides the default bucket.
- `application-dev.yml` overrides the bucket for dev.
- `APP_AWS_CATALOG_BUCKET` overrides the config file via property source precedence.
- `SPRING_PROFILES_ACTIVE` selects the right profile.
- Missing a required queue URL causes startup failure.
- Missing a required secret import causes startup failure; an optional secret may be omitted only when business logic allows it.

Do not test only the happy path; verify that a wrong profile or Region cannot silently point to production resources.

### 19.3. Integration testing with LocalStack

LocalStack can emulate certain AWS services for local integration tests. Use a dedicated local profile, dedicated endpoint overrides, and dummy test credentials:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: us-east-1
      s3:
        endpoint: http://localhost:4566
~~~

~~~bash
SPRING_PROFILES_ACTIVE=local \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
AWS_REGION=us-east-1 \
java -jar orders-api.jar
~~~

These credentials and endpoints are strictly for LocalStack/testing. Never use them in ECS/EKS/Lambda production. Not all IAM, STS, KMS, or service-specific semantics are emulated identically to AWS; validate critical flows against an AWS test account.

### 19.4. IAM identity smoke test in staging

A smoke test can call STS `GetCallerIdentity` using the same credentials provider the application uses and assert:

- Account ID matches the staging account.
- ARN matches the expected role.
- Region matches the environment.
- Reading a test object or sending a message to a test queue succeeds.
- Accessing production resources fails when not authorized.

Never write temporary credentials to logs. Log only necessary account/role ARNs and redact sensitive telemetry.

## 20. Troubleshooting configuration and IAM roles

An AWS SDK failure often spans multiple layers: Spring profile, property precedence, credentials provider, IAM authorization, Region, VPC networking, or resource policies. Layer-by-layer investigation prevents granting unnecessary permissions.

### 20.1. Symptom and root-cause table

| Symptom | Possible cause | Check first |
|---|---|---|
| **Unable to load credentials from any provider** | Missing role/profile credentials, invalid web identity token, metadata unreachable | Default chain, runtime role, `AWS_PROFILE`, ECS/EKS/EC2 credentials endpoint |
| **App uses the wrong AWS account** | `AWS_ACCESS_KEY_ID` or JVM system properties overriding role/profile | `GetCallerIdentity` from the exact process, environment/system properties |
| **AccessDenied despite attached role** | Policy missing action/resource, explicit Deny, SCP, boundary, resource policy | Caller ARN, action/resource, IAM evaluation, and service policy |
| **ECS app lacks S3 access** | Policy attached to task execution role instead of task role | `taskRoleArn` and `executionRoleArn` |
| **EKS Pod receives node role** | Service account association/IRSA misconfigured, Pod uses wrong service account | Pod spec, annotation/association, OIDC/Pod Identity Agent |
| **Lambda works locally but fails in production** | Local SSO profile has broader permissions than execution role | Caller identity and execution role policy |
| **Parameter Store import fails at startup** | Region/credentials unavailable at bootstrap, wrong path, missing `ssm:GetParametersByPath` | `spring.config.import`, `AWS_REGION`, task/pod role, VPC endpoint |
| **Secrets Manager import AccessDenied** | Role missing `GetSecretValue` or blocked by secret/KMS policy | Secret ARN, runtime role, KMS key policy |
| **KMS AccessDenied** | `SecureString`/secret uses customer-managed key but role lacks decrypt | KMS key ARN, `kms:Decrypt`, key policy/grants |
| **prod profile is not active** | Wrong `SPRING_PROFILES_ACTIVE` or overridden by another property source | Redacted startup logs, environment, and command line |
| **Bucket/queue points to wrong environment** | Environment variable overriding profile YAML or stale mounted config file | Property source precedence and redacted effective config |
| **Invalid region / signing error** | `app.aws.region`, `AWS_REGION`, and client Region inconsistent | Region provider, service endpoint, ARN Region |
| **Timeout calling AWS API** | VPC route, DNS, SG, NACL, NAT/VPC endpoint | Network path and endpoint DNS before altering IAM |
| **Secret rotated yet app uses old password** | Bean/connection pool retains startup-bound value | Secret version, refresh/redeploy strategy, connection lifecycle |
| **Kubernetes Pod fails to assume role** | Wrong IRSA trust subject/audience or missing Pod Identity association/agent | Service account, namespace, role trust policy, agent |
| **Cross-account AssumeRole denied** | Source role lacks `sts:AssumeRole` or target trust policy disallows it | Both trust/permissions sides and target role ARN |
| **Works on LocalStack, fails on real AWS** | IAM, endpoint policy, KMS, service behavior differ from local emulator | AWS staging integration tests and CloudTrail |

### 20.2. Quick investigation workflow

~~~mermaid
flowchart TD
    ERR["Spring Boot AWS call fails"] --> PROFILE{"Correct profile/config?"}
    PROFILE -->|"No"| CONFIG["Check SPRING_PROFILES_ACTIVE,<br/>property precedence, and config import"]
    PROFILE -->|"Yes"| ID{"Correct caller identity?"}
    ID -->|"No"| CREDS["Check default chain,<br/>runtime role, SSO, env keys"]
    ID -->|"Yes"| REGION{"Correct Region/endpoint?"}
    REGION -->|"No"| REG["Check AWS_REGION,<br/>spring.cloud.aws.region.static"]
    REGION -->|"Yes"| NET{"Network path exists?"}
    NET -->|"No"| VPC["DNS, route, SG/NACL,<br/>NAT/VPC endpoint"]
    NET -->|"Yes"| AUTH["IAM/resource/KMS policy<br/>and service error"]
    CONFIG --> FIX["Fix root cause<br/>and run smoke test"]
    CREDS --> FIX
    REG --> FIX
    VPC --> FIX
    AUTH --> FIX
~~~

### 20.3. Practical investigation order

1. Confirm the active profile and application config, logging only non-sensitive values.
2. Check AWS caller identity from the runtime process itself or the same credentials provider.
3. Confirm Region and endpoint, cross-checking against resource ARNs.
4. Check the network path to the service endpoint.
5. Check IAM identity policies, trust policies, permissions boundaries, SCPs, resource policies, and VPC endpoint policies.
6. If the resource is encrypted, check KMS key policies/grants.
7. Check service-specific conditions, tags, encryption context, and data-plane permissions.
8. Fix in staging, re-run smoke tests, and verify permissions were not over-broadened.

**Never respond to AccessDenied by attaching `AdministratorAccess`.** Identify the exact denied action/resource/condition, find the policy layer causing the deny, and grant least privilege.

## 21. Logging, metrics, and auditing

### 21.1. Signals to observe

| Signal | Goal |
|---|---|
| Active Spring profile | Detect app running with wrong dev/staging/prod config |
| AWS Region | Detect wrong endpoint/signing Region |
| Caller account/role ARN | Verify runtime identity |
| AWS request ID/error code | Correlate errors with AWS services |
| Secrets/Parameter import status | Detect bootstrap failures and rotation |
| Application startup/readiness | Detect config validation failures |
| Retry/throttling/latency | Detect quota/network/dependency issues |
| Deployment revision/image digest | Correlate config/role changes with releases |

### 21.2. CloudTrail and application logs

CloudTrail records many control-plane/data events depending on service and configuration. Use CloudTrail to audit changes to IAM roles/policies, secret metadata, ECS/EKS resources, and enabled API events. Application logs should record the service operation, error code, request ID, approved account/role metadata, and correlation ID.

Do not assume every credentials provider refresh, every Spring environment variable read, or every SQL query is logged by CloudTrail. Use database/service-specific auditing when data-plane tracking is needed.

### 21.3. Do not expose sensitive Actuator endpoints

Endpoints such as **env, configprops, heapdump, beans, mappings** can leak configuration, bean graphs, or sensitive data. Expose them only over a controlled management network with authentication/authorization enabled and secret values masked. Never open Actuator management endpoints publicly just for debugging convenience.

## 22. Scenario exercises

### Scenario A — Profile prod yet AWS account is dev

An ECS service has `SPRING_PROFILES_ACTIVE=prod`, yet caller identity logs show the dev account. The container image contains no access keys, but the task definition still carries a leftover `AWS_ACCESS_KEY_ID` variable.

**Question:** why wasn't the production task role used?

**Hint:** environment credentials precede ECS container credentials in the default chain. Remove the unnecessary credential variables, verify `taskRoleArn`, and check `GetCallerIdentity` from inside the container after redeploying.

### Scenario B — S3 AccessDenied on ECS

A developer attached `s3:GetObject` to `orders-api-execution-role`. The ECS task pulls the image and writes CloudWatch logs successfully, but Java code reading the object still gets `AccessDenied`.

**Question:** which role needs the S3 read policy?

**Hint:** application code needs permissions on the **task role**. The execution role serves the ECS agent. Check `taskRoleArn`, the policy resource ARN, bucket policy, KMS key if the object uses SSE-KMS, and VPC endpoint policy.

### Scenario C — Spring Cloud AWS cannot read secrets at startup

The application imports `aws-secretsmanager:orders/prod/database`, but the task in a private subnet lacks a NAT/Secrets Manager VPC endpoint. The context fails before the app is ready.

**Question:** why won't adding a `SecretsManagerClient` bean after startup fix this?

**Hint:** Config Data imports load during bootstrap, before regular application beans are created. Region/credentials/networking must be available upfront, including the interface endpoint and task role `GetSecretValue`/KMS permissions.

### Scenario D — EKS Pod uses node role instead of workload role

Pod `orders-api` needs to read a bucket. The team created an IAM role with permissions, yet the deployment omitted `serviceAccountName`, so the Pod runs under the `default` service account.

**Question:** what needs to be verified?

**Hint:** service account and namespace, IRSA annotation/OIDC trust or EKS Pod Identity association/agent, role ARN, and SDK version. Do not grant bucket permissions to the node role as a quick workaround.

### Scenario E — application-prod.yml contains a password

A developer committed a database password into `application-prod.yml` in a private repository. The repo is member-restricted, yet CI logs and the artifact registry already exist.

**Question:** how should this be handled?

**Hint:** assess everywhere the credential was exposed, rotate the password/secret per incident procedure, purge it from source history/artifacts per organizational policy, store the current secret in Secrets Manager, and restrict `GetSecretValue`/KMS. A private repository is not a secret store.

### Scenario F — Staging property accidentally overrides production bucket

A production deployment has `SPRING_PROFILES_ACTIVE=prod`, yet a leftover `APP_AWS_CATALOG_BUCKET` variable holds `orders-catalog-staging`. The app starts up fine and writes data to the wrong bucket.

**Question:** how to prevent this mistake?

**Hint:** validate bucket/account/Region per environment, enforce allowlists/expected resource identifiers, log effective non-secret config, run smoke tests before traffic, and check property source precedence. Never rely solely on profile names.

### Scenario G — IAM role looks right yet Parameter Store returns AccessDenied

The task role has `ssm:GetParameter`, yet the app imports `/orders-api/prod/` using `GetParametersByPath`. `SecureString` uses a customer-managed KMS key.

**Question:** which permissions might be missing?

**Hint:** the API may require `ssm:GetParametersByPath` on the matching parameter ARNs/path, plus `kms:Decrypt` on the key along with its key policy. Inspect the exact action called by the config loader; do not add `ssm:*`.

### Scenario H — Secret rotated yet application keeps using old password

Secrets Manager rotated the DB password, but the Spring `DataSource` bean bound the password at startup and the connection pool keeps opening new connections with the old value.

**Question:** how should refresh be designed?

**Hint:** pick a controlled redeploy/restart, configured framework reload, or a secret provider refreshing when creating physical connections. Verify pool eviction/connection lifetime and rotation stages; do not assume Environment updates beans automatically.

### Scenario I — CI pipeline has production database permissions

The CI role is shared with the ECS task role. The build pipeline can read production database secrets even though it only needs to deploy containers.

**Question:** how should identities be separated?

**Hint:** CI should use an OIDC deploy role with ECR/ECS/EKS/Lambda permissions and scoped `iam:PassRole`; the runtime should use a task/pod/Lambda role with business permissions. Never expose production secrets to the build pipeline.

### Scenario J — Works locally, AccessDenied on Lambda

A developer uses a broad SSO profile; the Lambda execution role only permits S3 reads on one prefix, yet the code also calls `s3:ListBucket` and KMS decrypt.

**Question:** why didn't local unit/integration tests catch this?

**Hint:** local identity differs from production identity. Add staging tests using a production-equivalent role, and grant scoped `ListBucket` conditions/prefixes and KMS permissions if the use case requires them; never widen permissions to match a developer profile.

### Scenario K — Cross-account AssumeRole fails

Orders API in account A has `sts:AssumeRole` on the target role ARN in account B, yet the target role's trust policy only allows a different CI role.

**Question:** where should the fix be made?

**Hint:** both source permissions and the target trust policy must allow the source runtime role. Verify session tags/external ID/conditions if used; after `AssumeRole`, the target role still needs permissions on the destination resource.

### Scenario L — Optional secret import hides a production error

The DB password was marked `optional:` so the app still starts if Secrets Manager fails. The service reports healthy, yet every database request returns 500.

**Question:** where is `optional:` appropriate?

**Hint:** `optional:` is only for genuinely non-mandatory integrations. Production DB credentials are mandatory configuration; fail-fast or controlled degraded readiness is better than accepting traffic when unable to serve.

## 23. Production checklist

- [ ] A single artifact runs in dev, test, staging, and prod; profiles are chosen by the deployment environment.
- [ ] `application.yml` holds only defaults and non-sensitive configuration.
- [ ] Profile files contain only necessary deltas; no AWS access keys, DB passwords, or API tokens.
- [ ] Property precedence is tested; environment variables/command-line overrides cannot inadvertently point to another environment's resources.
- [ ] `spring.profiles.active` is not declared inside profile-specific documents.
- [ ] Configuration is bound using `@ConfigurationProperties` and validated at startup.
- [ ] Required values such as Region, bucket, queue URL, and endpoints are validated per environment.
- [ ] A compatible Spring Cloud AWS BOM/version matching Spring Boot and the AWS SDK is selected.
- [ ] Only the Spring Cloud AWS starters actually used by the app are included.
- [ ] Config Data imports have Region, credentials, and network paths ready at bootstrap.
- [ ] Mandatory secrets are not marked `optional:`; secrets never appear in logs or public Actuator endpoints.
- [ ] Local development uses an IAM Identity Center/SSO profile or approved mechanism; never production access keys.
- [ ] Production uses IAM roles/temporary credentials via the runtime credential provider chain.
- [ ] No unintended `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` or JVM static credentials exist in production containers.
- [ ] The ECS task role grants permissions to the application; the task execution role serves only the ECS agent.
- [ ] EKS workloads have a service account/Pod Identity association or IRSA trust policy matching the exact namespace and account.
- [ ] Lambda execution roles and EC2 instance profiles follow least privilege; EC2 IMDSv2 is enabled.
- [ ] CI/CD deploy roles are separated from runtime roles; OIDC federation and `iam:PassRole` are scoped.
- [ ] Trust policies and permissions policies are reviewed separately; resource ARNs and conditions are explicit.
- [ ] `AWS_REGION`, Spring Cloud AWS Region, and `app.aws.region` do not conflict.
- [ ] Multi-Region/multi-account clients have explicit endpoints, signing Regions, resource ARNs, and KMS plans.
- [ ] VPC routes, DNS, SG/NACLs, NAT/VPC endpoints, and endpoint policies are tested from the private runtime.
- [ ] Secret rotation has a refresh/redeploy plan for beans, `DataSource`, and connection pools.
- [ ] Health/readiness distinguishes mandatory configuration, liveness, and dependency availability.
- [ ] Logs record approved profile/Region/caller identity metadata, never credentials/tokens/`SecretString`.
- [ ] CloudTrail, application metrics, and alarms suffice to audit IAM/secret/config changes and detect `AccessDenied`.
- [ ] Staging smoke tests confirm caller account/role, Region, S3/SQS/DynamoDB permissions, and no unintended production access.
- [ ] Rollback, secret rotation, task/pod replacement, failover, and cross-account access have been tested.
- [ ] Runbooks exist for wrong profiles, credentials chain issues, `AccessDenied`, KMS, VPC endpoints, and config import failures.

## 24. Key takeaways

**Spring profiles select application configuration; IAM roles define the AWS identity of the process.** The two concepts are independent. A single JAR should be deployed across multiple environments using application defaults, profile-specific non-secret settings, and externalized configuration. Secrets belong in Secrets Manager or an appropriate secret store; AWS API permissions belong in IAM policies.

In local development, use an IAM Identity Center/SSO profile. In production, let the runtime issue temporary credentials: **ECS task role** for application containers, **EKS Pod Identity/IRSA** for Kubernetes service accounts, **Lambda execution role** for functions, and **EC2 instance profile** for EC2 workloads. Remember to distinguish ECS task roles from task execution roles and verify the default credentials provider chain order, because environment credentials can shadow the runtime role.

With Spring Boot, use **@ConfigurationProperties + validation**, select profiles from the deployment environment, keep Regions consistent, and use Spring Cloud AWS Parameter Store/Secrets Manager Config Data imports when appropriate. Imports occur at bootstrap; secret rotation does not automatically guarantee every running bean refreshes. Finally, verify **IAM, resource policies, KMS, VPC endpoints, health checks, logs, CI/CD identities, and rollback** in staging before production receives traffic.

### Official documentation for reference

- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — property sources, environment variables, and config locations.
- [Spring Boot Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html) — active profiles and profile-specific configuration.
- [AWS SDK for Java 2.x Default Credentials Provider Chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — credentials provider search order.
- [AWS SDK for Java 2.x Credentials Providers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html) — profile, SSO, web identity, and role credentials.
- [AWS SDK for Java 2.x IAM Identity Center setup](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-temporary.html) — SSO profile setup and `sso`/`ssooidc` modules.
- [AWS SDK for Java 2.x Troubleshooting](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/troubleshooting.html) — credentials chain, STS module, and network errors.
- [Amazon ECS Task IAM Role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) — application credentials in containers.
- [Amazon ECS Task Execution IAM Role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) — ECS/Fargate agent permissions.
- [Best Practices for IAM Roles in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html) — role separation and least privilege.
- [IAM Roles for Service Accounts (IRSA)](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) — OIDC and workload identity on EKS.
- [EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html) — associations, agent, and credentials.
- [Spring Cloud AWS 3.4.2 Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html) — starters, Region/credentials auto-configuration, and integrations.
- [Spring Cloud AWS Version Compatibility](https://github.com/awspring/spring-cloud-aws) — Spring Boot/Spring Cloud release matrix.
- [Spring Cloud AWS Parameter Store Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html#parameter-store-integration) — Config Data import.
- [Spring Cloud AWS Secrets Manager Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html#secrets-manager-integration) — secrets as Spring properties.
- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html) — parameters, `SecureString`, and IAM.
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html) — secret lifecycle and rotation.
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html) — roles, temporary credentials, and least privilege.
- [AWS STS GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html) — verifying caller account/ARN.
