# Loading Configuration and Rotating Secrets Without Hardcoding Keys

Spring Boot applications typically need database passwords, API tokens, signing keys, certificates, or connection credentials to call managed services. Placing these values in source code, committed application.yml files, Docker images, or pipeline logs risks exposing credentials whenever code is shared or artifacts are published. The secure approach is to store secrets in a cloud secret management service, grant read access via a workload identity, load values into the Spring Environment at startup, and design a verified rotation workflow.

This lab uses a document-service running on AWS, Azure, or Google Cloud. The same application needs to read a database username/password and a partner API key, while endpoints, regions, project IDs, and feature flags remain regular configuration. Depending on the cloud, the application uses AWS Secrets Manager/Systems Manager Parameter Store, Azure Key Vault, or Google Cloud Secret Manager through the corresponding Spring integration.

The goal is not merely replacing a password string in application.yml with a secret reference. A rotation must also update the credential at the target service, deliver the new secret version to every instance, refresh clients or connection pools, verify business flows, preserve rollback capability, and revoke the old credential only after all workloads have transitioned.

## 1. Objectives and Hands-On Architecture

After this lesson, you will be able to:

1. Distinguish regular configuration from secrets and determine what data belongs in a secret manager.
2. Use the Spring Boot Config Data API and PropertySource to load external configuration.
3. Configure Spring Cloud AWS to read Secrets Manager and Parameter Store.
4. Configure Spring Cloud Azure to read Azure Key Vault Secrets.
5. Configure Spring Framework on Google Cloud to read Google Cloud Secret Manager.
6. Authenticate workloads using IAM roles, managed identities, or Application Default Credentials.
7. Grant least-privilege secret read permissions.
8. Distinguish secret versions, current versions, pending versions, and previous versions.
9. Design a rotation workflow with an overlap window for database passwords or API tokens.
10. Refresh Spring beans, HTTP clients, and JDBC connection pools after a secret changes.
11. Test missing secrets, denied permissions, wrong versions, expired credentials, and rollbacks.
12. Build an operational runbook with owners, rotation schedules, monitoring, and verification evidence.

~~~mermaid
flowchart TD
    A["CI/CD or operator"] --> B["Create new credential at target service"]
    B --> C["Write new secret version"]
    C --> D["Test new secret with canary"]
    D --> E["Roll out config/version to workload"]
    E --> F["Spring Boot loads new secret"]
    F --> G["Recreate client or connection pool"]
    G --> H["Verify requests and metrics"]
    H --> I["Revoke old credential"]
    C -. "Keep old version for rollback" .-> J["Secret history"]
    D -. "If failed" .-> K["Rollback to known-good version"]
    K --> F
~~~

**The secret manager stores and controls credential lifecycle. Spring Cloud integrates the secret manager with the Spring Environment. The application must still handle refreshing beans and existing connections.**

## 2. Distinguishing Configuration and Secrets

### 2.1. Regular configuration

Configuration describes how the application behaves in a given environment:

- Service name, profiles, and feature flags.
- Base URLs of internal services.
- Regions, project IDs, resource IDs, and bucket names.
- Timeouts, retry counts, batch sizes, and concurrency limits.
- Log levels and sampling rates.
- Queue names, topic names, database schemas, or secret resource names.

These values can live in secret-free application.yml files, environment variables, cloud parameter stores, configuration services, or Kubernetes ConfigMaps. They still require environment-scoped management and controlled changes, but do not necessarily require password-grade protection.

### 2.2. Secrets

A secret is any value that an unauthorized party could use to gain access, impersonate an identity, or bypass controls:

- Database passwords.
- API keys, OAuth client secrets, or refresh tokens.
- Private keys, signing keys, and certificates with private keys.
- SMTP credentials.
- Access keys or connection strings containing credentials.
- Encryption keys or tokens used to sign requests.

Secrets must never appear in:

- Git repositories or pull requests.
- Dockerfiles, build arguments, or image layers.
- application-prod.yml files packaged inside a JAR.
- CI/CD logs, command history, or build artifacts.
- Exception messages, stack traces, metric labels, or distributed traces.
- Unsecured Actuator endpoints.
- Tickets, chats, or public runbook documentation.

### 2.3. Separating configuration by sensitivity

| Value | Appropriate storage | Example |
| --- | --- | --- |
| Region, project ID, endpoint | application.yml or config store | ap-southeast-1 |
| Feature flag, timeout, retry | Config store/Parameter Store/App Configuration | app.retry.max-attempts |
| Database username/password | Secret Manager/Key Vault | document-db-credential |
| Partner API token | Secret Manager/Key Vault | partner-api-token |
| Private key/certificate | Secret Manager or certificate/key service | document-signing-key |
| Secret version ID | Deployment configuration/metadata | version 17 |
| Secret resource name | Application configuration | secret path or secret ID |

Never embed secret values inside secret names, tags, or descriptions. Metadata identifies purpose and owner and must never contain passwords or tokens.

### 2.4. A secret manager is not a configuration database

Secret managers are optimized for storing, accessing, and managing the lifecycle of sensitive data. Using one for every feature flag or non-sensitive parameter increases API calls, cost, and unnecessary access privileges.

AWS provides Parameter Store for configuration and SecureString; Azure provides App Configuration for application settings and Key Vault for secrets; Google Cloud provides dedicated configuration sources and Secret Manager for secret payloads. This lesson focuses on secrets and uses parameter store only where needed to illustrate non-sensitive configuration.

## 3. Loading External Configuration in Spring Boot

### 3.1. Spring Environment and PropertySource

Spring Boot aggregates values from multiple sources into the Environment. Beans can read values via:

- @Value for a few simple properties.
- Environment when querying properties dynamically.
- @ConfigurationProperties for structured property groups, validation, and type-safe binding.

PropertySource precedence determines the final value when the same key appears in multiple places. Environment variables, system properties, and command-line arguments can override config data values. Consequently, a stale environment variable can inadvertently shadow a newly loaded cloud secret.

In production, explicitly define which sources are allowed to override secrets. Never use default values for mandatory database passwords or API tokens. If a secret is missing, the application should fail startup or readiness so the deployment never serves traffic with empty credentials.

### 3.2. Spring Boot Config Data API

Spring Boot supports loading external configuration sources via the spring.config.import property. Cloud starters can register their own resolvers so Spring Boot reads data from a secret manager during the Config Data phase.

General example:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Config trees are useful when the platform mounts secrets as files. File or directory names map to property keys. This works with Kubernetes Secret volumes, Docker secrets, or platform-mounted secret volumes.

When integrating directly with a cloud secret manager, each starter uses its own import syntax. Never use an AWS prefix for Azure or Google Cloud.

### 3.3. Required vs. optional imports

There are two cases:

- Mandatory secrets for opening database connections or calling APIs: the import must be required. Missing or unreadable secrets must fail startup.
- Optional configuration such as experimental feature flags: may use optional imports if the application has safe defaults.

Never use optional to mask permission errors or missing production credentials. If a secret import fails yet the application starts with an empty/default password, failures appear later and are harder to diagnose.

### 3.4. Profile-based configuration

Keep application.yml limited to shared configuration with no secrets. Use dedicated profiles to enable the resolver matching the environment:

~~~text
application.yml
application-aws.yml
application-azure.yml
application-gcp.yml
~~~

Example selecting a profile at runtime:

~~~bash
SPRING_PROFILES_ACTIVE=aws
~~~

Each profile only declares the configuration source and secret resource names for its respective cloud. The same business service can bind to shared property keys such as spring.datasource.username, spring.datasource.password, and partner.api.key.

### 3.5. Validated binding

Example partner client configuration:

Add the validation starter so Jakarta Validation annotations are enforced when binding configuration:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.validation.annotation.Validated;

@Validated
@RefreshScope
@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiProperties {

    @NotBlank
    private String key;

    public String getKey() {
        return key;
    }

    public void setKey(String key) {
        this.key = key;
    }

    @Override
    public String toString() {
        return "PartnerApiProperties{key=[REDACTED]}";
    }
}
~~~

Enable configuration properties scanning in the application:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DocumentServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentServiceApplication.class, args);
    }
}
~~~

Do not use a Java record with secret fields if the generated toString() could print the full secret value. If using a record, control serialization/logging and never log the object. Never expose PartnerProperties in JSON responses or actuator endpoints.

### 3.6. Property refresh does not mean clients updated credentials

When a secret manager detects a new version, a PropertySource may reload or Spring may refresh certain beans. However, a previously created singleton JDBC DataSource or HTTP client may still hold the old credentials.

For example, HikariCP creates its connection pool at startup. Changing spring.datasource.password in the Environment does not automatically guarantee that the existing pool closes old connections, opens new connections with the new password, or terminates old sessions.

For connection pool credentials, the safer approach is typically a rolling restart or a pool replacement mechanism with explicit drain/close. Only use in-place refresh after testing precisely which beans are recreated and how old connections are retired.

## 4. Preparing the Sample Application

### 4.1. Common configuration

application.yml without credentials:

~~~yaml
spring:
  application:
    name: document-service
  datasource:
    url: jdbc:postgresql://db.internal.example:5432/documents
    hikari:
      pool-name: document-service-pool
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 30000

partner:
  base-url: https://partner.example/api
~~~

The URL, pool size, and partner endpoint are regular configuration in this example. Username/password and the API key come from the secret manager. If a database URL contains a password in its query string, the URL itself must be treated as a secret.

### 4.2. Shared secret contract

To switch providers without modifying business code, standardize on the same property keys:

| Property | Meaning | Kind |
| --- | --- | --- |
| spring.datasource.username | Database login | Secret |
| spring.datasource.password | Database password | Secret |
| partner.api.key | Partner API token | Secret |
| spring.datasource.url | Database endpoint | Configuration |
| partner.base-url | Partner endpoint | Configuration |
| app.rotation.expected-version | Expected secret version in deployment | Metadata/configuration |

Each provider can name secret resources differently. What matters is that the final values bind to the same property keys in the Spring Environment.

### 4.3. Runtime identity

Each workload must use its own runtime identity:

- AWS: IAM role attached to an EC2 instance profile, ECS task role, or EKS workload identity/IRSA.
- Azure: system-assigned or user-assigned managed identity; local development can use DefaultAzureCredential.
- Google Cloud: service account attached to Cloud Run/GCE or Workload Identity Federation for GKE.

Never store access keys, client secrets, or service-account JSON keys in images when the platform supports workload identity. Grant read access to the exact secret resources rather than account-, project-, or subscription-wide admin permissions.

### 4.4. Spring version compatibility

Each starter has its own release train. Select the BOM matching your application's Spring Boot/Spring Cloud version instead of mixing dependencies randomly:

| Ecosystem | Current reference line | Compatible Spring Boot |
| --- | --- | --- |
| Spring Cloud AWS | 4.1.x | Spring Boot 4.x; 3.4.x line targets Boot 3.5.x |
| Spring Cloud Azure | 7.5.x | Spring Boot 4.0.x/4.1.x; 6.x or 5.x lines target Boot 3.5.x per mapping |
| Spring Framework on Google Cloud | 8.2.x | Spring Boot 4.0.x/4.1.x; 7.5.x line targets Boot 3.5.x |

This table is a reference baseline based on current releases at the time of writing. Always check compatibility matrices and release notes before upgrading. Use BOMs to align Spring, cloud SDKs, and transitive dependencies.

## 5. AWS: Secrets Manager and Parameter Store

### 5.1. Choosing the service

AWS offers two common options:

- **Secrets Manager:** stores database credentials, API tokens, and secrets requiring lifecycle/rotation. Supports versions and staging labels such as AWSCURRENT, AWSPREVIOUS, and AWSPENDING, plus rotation workflows via Lambda.
- **Systems Manager Parameter Store:** stores hierarchical configuration supporting String, StringList, and SecureString. SecureString is encrypted with AWS KMS. Parameter Store fits configuration and simple secrets; it does not replace Secrets Manager's rotation workflow.

If you need automated rotation for database passwords or API credentials, prefer Secrets Manager. With Parameter Store SecureString, applications/automation must build their own process to update both the stored value and the target service credential.

### 5.2. Dependencies

Use the Spring Cloud AWS BOM and the two required starters:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>4.1.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
    </dependency>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-parameter-store</artifactId>
    </dependency>
</dependencies>
~~~

If the application only uses Secrets Manager, omit the Parameter Store starter. If your project uses Spring Boot 3.5.x, select the Spring Cloud AWS line compatible with Boot 3.5.x instead of the 4.x BOM.

### 5.3. Creating JSON secrets

Create a secret resource for document-service, for example:

~~~json
{
  "username": "DOCUMENT_SERVICE_DB_USER",
  "password": "VALUE_PROVIDED_BY_SECRET_ROTATION_WORKFLOW"
}
~~~

This is an illustrative data structure. Real values are generated by a credential provisioning workflow and written directly to Secrets Manager through secured Console/API/automation. Never place real values in source code, shell history, or tickets.

Example secret name:

~~~text
/prod/document-service/database
~~~

Top-level JSON keys become property keys in the Spring Environment. You can apply a prefix to avoid collisions with properties of other modules.

Store the partner API key in a separate secret so it has an independent owner, version, and rotation schedule:

~~~json
{
  "key": "VALUE_PROVIDED_BY_PARTNER_CREDENTIAL_WORKFLOW"
}
~~~

Name the resource /prod/document-service/partner-api and import with prefix partner.api. to produce the partner.api.key property.

### 5.4. Importing Secrets Manager and Parameter Store

application-aws.yml:

~~~yaml
spring:
  config:
    import: "aws-secretsmanager:/prod/document-service/database?prefix=spring.datasource.,aws-secretsmanager:/prod/document-service/partner-api?prefix=partner.api.,aws-parameterstore:/prod/document-service/"
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

The JSON secrets provide username/password under the spring.datasource. prefix. Parameter Store can provide non-sensitive properties such as app.retry.max-attempts or app.feature.new-workflow.

If the database secret is mandatory, keep its import required. Only use optional for genuinely optional configuration sources. Spring Cloud AWS also supports importing multiple secrets/paths with prefixes to prevent property collisions.

### 5.5. Using Parameter Store for configuration

Example parameter tree:

~~~text
/prod/document-service/app/retry/max-attempts
/prod/document-service/app/feature/new-workflow
/prod/document-service/app/partner/timeout
~~~

When importing path /prod/document-service/, Spring Cloud AWS adds child keys to the Environment. For sensitive configuration requiring encryption, use SecureString and KMS. The IAM policy may require ssm:GetParametersByPath; if SecureString uses a customer-managed KMS key, the workload also needs kms:Decrypt on that key.

Parameter Store standard parameters have a smaller payload limit than advanced parameters. Do not bundle a large config blob into one parameter if it exceeds the limit. For many keys, use path hierarchies and prefixes.

### 5.6. IAM policy for the workload

The workload only reads the designated secrets:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:ACCOUNT_ID:secret:/prod/document-service/database-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParametersByPath"
      ],
      "Resource": "arn:aws:ssm:ap-southeast-1:ACCOUNT_ID:parameter/prod/document-service/*"
    }
  ]
}
~~~

If the secret is encrypted with a customer-managed KMS key, add kms:Decrypt for the exact key ARN and restrict via encryption context where appropriate. Never grant secretsmanager:* or ssm:* to runtime workloads just to fetch a single secret.

Separate roles:

- Application role: GetSecretValue and Parameter Store read permissions.
- Rotation Lambda role: read/write versions, change credentials at the database/service, and test the new credential.
- Secret administrator: create secrets, configure rotation, policies, and tags.
- Auditor: read metadata/audit logs without accessing secret payloads.

### 5.7. AWS Default Credentials Provider Chain

Spring Cloud AWS uses the AWS SDK credential provider chain. In production, prefer IAM roles over access keys:

- EC2 uses an instance profile.
- ECS uses a task role.
- EKS uses IRSA or EKS Pod Identity per cluster architecture.
- Local development uses an AWS CLI/SSO profile.
- CI/CD uses OIDC federation/assume role if supported by the platform.

Never add aws.access-key-id and aws.secret-access-key to application.yml. Never use personal user accounts as production runtime identities.

### 5.8. Secrets Manager version labels

Secrets Manager attaches staging labels to secret versions:

| Label | Meaning |
| --- | --- |
| AWSCURRENT | Version retrieved by the application by default |
| AWSPREVIOUS | Previous version, typically the rollback candidate |
| AWSPENDING | Version currently undergoing rotation |

A standard Rotation Lambda has four steps:

1. createSecret: creates a new secret version and attaches AWSPENDING.
2. setSecret: updates the credential in the database or target service.
3. testSecret: attempts to log in or call the API using the new credential.
4. finishSecret: moves AWSCURRENT to the new version; the prior version becomes AWSPREVIOUS.

The rotation function must be idempotent. If the workflow stops mid-way, the next run must recognize the AWSPENDING version and resume/recover cleanly. Never write old or new passwords to CloudWatch Logs.

### 5.9. Enabling reload in Spring Cloud AWS

PropertySource reloading for Secrets Manager/Parameter Store is disabled by default. To use refresh or restart strategies, add the required dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-commons</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
~~~

Example Secrets Manager reload configuration:

~~~yaml
spring:
  cloud:
    aws:
      secretsmanager:
        reload:
          strategy: restart_context
          period: 30s
          max-wait-time-for-restart: 10s
~~~

Strategies:

- refresh: refreshes supported beans, such as configuration beans using @ConfigurationProperties or @RefreshScope.
- restart_context: restarts the Spring ApplicationContext to recreate beans from the new configuration. Requires enabling and securing the restart actuator endpoint per Spring Cloud AWS documentation.

If choosing restart_context, configure the endpoint per starter documentation and expose it only over an authenticated management network:

~~~yaml
management:
  endpoint:
    restart:
      enabled: true
  endpoints:
    web:
      exposure:
        include: restart
~~~

For database passwords, a controlled rolling restart is usually easier to verify. Do not assume changing a secret automatically swaps the password across all open HikariCP connections.

### 5.10. Verifying AWS

- Inspect VersionIdsToStages via DescribeSecret without printing SecretString.
- Confirm AWSCURRENT points to the tested version.
- Confirm the application role only reads the required secrets.
- Test missing ssm:GetParametersByPath or secretsmanager:GetSecretValue to verify 403 failures.
- Verify refresh/restart created a new DataSource.
- Check CloudTrail and rotation Lambda logs to ensure no credentials appear.

## 6. Azure: Key Vault Secrets and Spring Cloud Azure

### 6.1. Key Vault stores secrets by version

Azure Key Vault stores each secret update as a new version. Older versions remain available according to the vault's retention/soft-delete policy. Applications typically read the current version via SecretClient/PropertySource.

Key Vault manages secrets, keys, and certificates. For non-sensitive settings such as feature flags, endpoints, or timeouts, Azure App Configuration is the better service. Do not turn Key Vault into a store for all application configuration.

### 6.2. Dependencies

Use the Spring Cloud Azure BOM and Key Vault Secrets starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>7.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
    </dependency>
</dependencies>
~~~

Spring Cloud Azure 7.x targets Spring Boot 4.x. If the application uses Spring Boot 3.5.x, choose the compatible Spring Cloud Azure 5.x/6.x line per the compatibility mapping and release notes.

### 6.3. Secret names and property mapping

Key Vault secret names only support letters, digits, and hyphens. Dots in property keys are invalid in secret names.

Example mapping:

| Secret name in Key Vault | Spring property |
| --- | --- |
| spring-datasource-username | spring.datasource.username |
| spring-datasource-password | spring.datasource.password |
| partner-api-key | partner.api.key |

Spring Cloud Azure KeyVaultPropertySource maps secret names to property keys. When keys require special characters or a different structure, use property placeholders in application configuration.

### 6.4. Configuring PropertySource

Example application-azure.yml:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: document-service-secrets
              endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              secret-keys:
                - spring-datasource-username
                - spring-datasource-password
                - partner-api-key
              refresh-interval: 5m
~~~

The endpoint is substituted with the actual vault URI via environment configuration. The secret-keys list restricts which secrets the property source reads; omitting this field can cause the integration to pull all secrets in the vault according to configuration.

The default refresh interval of KeyVaultPropertySource is 30 minutes. The example lowers it to 5 minutes for illustration; shorter intervals increase Key Vault API calls and do not replace a rotation workflow.

### 6.5. Managed Identity and DefaultAzureCredential

On Azure App Service, VM, Container Apps, or AKS, prefer managed identity or workload identity. System-assigned managed identity example:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
~~~

With a user-assigned managed identity:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        client-id: AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID
~~~

In local development, DefaultAzureCredential can use the identity signed in via Azure CLI/IDE. When running on Azure, the credential chain can use managed identity. Never store a service principal client secret in application.yml when workload identity satisfies the use case.

### 6.6. Azure RBAC for Key Vault

Under the Azure RBAC model, the runtime principal needs the Key Vault Secrets User role to read secret payloads. The Key Vault Reader role only reads metadata, not secret values. Key Vault Contributor manages control-plane resources and does not implicitly grant data-plane read permissions.

Separate roles:

- Application managed identity: Key Vault Secrets User scoped to the vault or required secrets.
- Rotation Function identity: permission to read/write secrets and update credentials at the target service.
- Secret operator: Key Vault Secrets Officer to create/update secrets.
- Vault administrator: manages the vault and role assignments per responsibility.

Never grant Key Vault Administrator or Owner to a runtime application. Prefer RBAC over legacy access policies when provisioning new vaults under current standards.

### 6.7. Refreshing PropertySource

KeyVaultPropertySource automatically refreshes secrets according to refresh-interval. The default is 30 minutes; set 0 to disable auto-refresh.

Distinguish four separate actions:

- PropertySource refresh: reloads the secret value from Key Vault.
- Spring bean refresh: updates objects bound to properties.
- Client refresh: recreates HTTP clients or DataSources holding credentials.
- Credential revoke: revokes the old password/key at the target system.

These four actions do not happen simultaneously by default. For database passwords, use a rolling restart or a tested custom pool replacement. For partner clients, you can use @RefreshScope on configuration beans and recreate clients with an appropriate lifecycle.

### 6.8. Rotating secrets with Event Grid

Key Vault can emit events when a new secret version is created or a secret nears expiration. An automated workflow typically follows:

1. Key Vault emits SecretNearExpiry or SecretNewVersionCreated.
2. Event Grid delivers the event to an Azure Function/worker.
3. The rotation worker identifies the secret and target credential.
4. The worker creates a new credential at the target service or generates a new key.
5. The worker writes a new secret version to Key Vault.
6. The worker verifies the new credential.
7. The application picks up the new version via PropertySource refresh or rolling restart.
8. Once all instances use the new version, the worker revokes the old credential.

For databases/services that only allow a single password, there can be a gap between updating Key Vault and updating the target system. Prefer dual credentials/overlap when supported. If unsupported, use a coordinated password-change procedure with health checks and a concrete rollback plan.

### 6.9. Verifying Azure

- Verify the managed identity matches the expected principal.
- Verify Key Vault Secrets User has the right scope.
- Attempt to access an ungranted secret to confirm 403.
- Check secret names for dots or invalid characters.
- Confirm refresh interval and secret-keys are accurate.
- Verify DataSource/HTTP clients are recreated after rotation.
- Verify Event Grid delivery and Function execution logs redact secrets.

## 7. Google Cloud: Secret Manager and Spring Framework on Google Cloud

### 7.1. Secret versions are immutable

Google Cloud Secret Manager separates the secret resource from secret versions. Payloads live inside versions and cannot be edited in place. To change a value, create a new version. A secret can have multiple enabled/disabled/destroyed versions.

Current documentation recommends pinning version numbers for production deployments rather than always referencing latest. latest is convenient, but a faulty version can roll out simultaneously to every instance during restarts or scale-outs.

### 7.2. Dependencies and BOM

Use the Spring Framework on Google Cloud BOM and Secret Manager starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>8.2.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-secretmanager</artifactId>
    </dependency>
</dependencies>
~~~

Spring Framework on Google Cloud 8.x targets Spring Boot 4.x. For Spring Boot 3.5.x, use the 7.x line and its corresponding BOM. Do not mix Spring Cloud GCP 7.x with Boot 4.x.

### 7.3. Application Default Credentials

Spring Cloud GCP defaults to Application Default Credentials (ADC). At runtime, ADC can obtain credentials from a service account attached to the workload or Workload Identity Federation. On GKE, prefer Workload Identity for Kubernetes service accounts; on Cloud Run/GCE, use the corresponding service identity.

Local development can use gcloud application-default login. Never commit service-account JSON keys to repositories or Docker images. If using GCE/GKE, verify the cloud-platform OAuth scope per platform requirements and assign IAM roles to the right service account.

### 7.4. IAM roles

Runtime workloads only need to read payloads of designated secrets:

~~~text
roles/secretmanager.secretAccessor
~~~

Grant the role at the secret level if the application only reads a few secrets. Do not grant at the project scope if access to every secret in the project is unnecessary.

Separate identities:

- Application service account: Secret Accessor on specific secrets.
- Rotation worker: Secret Version Adder to create new versions.
- Rotation operator: Secret Version Manager when enabling/disabling/destroying versions.
- Secret administrator: Secret Manager Admin to manage secrets and IAM.

Granting permission to read a secret does not imply permission to create or destroy versions.

### 7.5. Secret Manager Config Data Resource

The starter uses the Spring Boot Config Data API. Since Spring Framework on Google Cloud 6.0, the new sm@ syntax is recommended; the older sm:// syntax emits deprecation warnings.

Example application.properties:

~~~properties
spring.config.import=sm@
spring.cloud.gcp.project-id=YOUR_GCP_PROJECT_ID

spring.datasource.username=${sm@projects/YOUR_GCP_PROJECT_ID/secrets/document-db-username/versions/7}
spring.datasource.password=${sm@projects/YOUR_GCP_PROJECT_ID/secrets/document-db-password/versions/12}
partner.api.key=${sm@projects/YOUR_GCP_PROJECT_ID/secrets/partner-api-key/versions/4}
~~~

Replace the project ID and version IDs with real resources. Use pinned version numbers so deployments are reproducible and reversible. Never place secret payloads directly in properties files.

For regional secrets, use resource paths containing locations and location IDs per Secret Manager documentation. Verify the secret's replication/location policy against data residency requirements.

### 7.6. SecretManagerTemplate

Spring Framework on Google Cloud provides SecretManagerTemplate to read, create, and update secrets programmatically in Java. Use the template when applications/automation need imperative operations, such as a worker creating a new version. Do not grant version creation permissions to application runtimes that only need to read secrets.

When using the template, handle response metadata/version IDs and never log payloads. Version operations require the corresponding IAM permissions.

### 7.7. Refreshing secrets via Actuator

The GCP integration supports refreshing secrets without restarting for compatible beans:

1. Add Spring Boot Actuator.
2. Expose the refresh endpoint securely.
3. Configure beans with @ConfigurationProperties and @RefreshScope.
4. Update the secret version in Secret Manager.
5. Call POST /actuator/refresh over an authenticated management network.
6. Verify the bean receives the new value.

Example:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.validation.annotation.Validated;

@Validated
@RefreshScope
@ConfigurationProperties(prefix = "partner.api")
public class PartnerConfiguration {

    @NotBlank
    private String key;

    public String getKey() {
        return key;
    }

    public void setKey(String key) {
        this.key = key;
    }

    @Override
    public String toString() {
        return "PartnerConfiguration{key=[REDACTED]}";
    }
}
~~~

Actuator refresh does not automatically recreate DataSource, HikariCP, or every singleton. For database credentials, perform a rolling restart or custom DataSource replacement with connection draining and dedicated testing. Never expose the refresh endpoint publicly.

### 7.8. Rotation notifications via Pub/Sub

Secret Manager can publish SECRET_ROTATE messages to a Pub/Sub topic on a rotation schedule. Secret Manager only emits the notification; the subscriber/worker must create the new credential, add the secret version, and update the target system.

Key points to remember:

- Minimum rotation period is one hour.
- next_rotation_time must be set appropriately and cannot be less than five minutes in the future.
- The Pub/Sub topic and subscriber must be configured.
- Workers must be idempotent and handle retries.
- Secret Manager does not change passwords at databases or API providers by itself.
- Avoid running multiple concurrent rotation workflows on the same secret.

### 7.9. Verifying Google Cloud

- Verify ADC is using the intended service account.
- Verify Secret Accessor is granted only on the required secrets.
- Check version IDs and enabled state.
- Attempt reading a disabled version to confirm error handling.
- Verify Pub/Sub receives SECRET_ROTATE.
- Verify the worker creates a new version and records the version ID.
- Verify rolling restarts or bean refresh work as expected.
- Verify old versions remain available for rollback during the control window.

## 8. Comparing the Three Cloud Providers

| Capability | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Secret service | Secrets Manager | Key Vault Secrets | Secret Manager |
| Non-sensitive config | Parameter Store/AppConfig | App Configuration | Config service/ConfigMap |
| Spring integration | Spring Cloud AWS | Spring Cloud Azure | Spring Framework on Google Cloud |
| Config loading | spring.config.import with aws-secretsmanager | KeyVaultPropertySource | Config Data resource sm@ |
| Workload identity | IAM role/STS web identity | Managed Identity/Workload Identity | ADC/Workload Identity Federation |
| Read permission | secretsmanager:GetSecretValue | Key Vault Secrets User | roles/secretmanager.secretAccessor |
| Versioning | Secret versions + staging labels | Secret versions | Secret versions |
| Rotation trigger | Lambda rotation workflow | Event Grid + Function/worker | Pub/Sub rotation notification |
| Default refresh | Reload integration off by default | PropertySource refresh every 30 minutes | Not continuous; Actuator refresh supported |
| Rollback | AWSPREVIOUS or version stage | Select previous version | Pin previous version ID |
| Notable quirk | Secrets Manager has a 4-step rotation workflow | Secret names cannot contain dots | latest can distribute faulty versions fleet-wide |

### 8.1. Differences in rotation

AWS Secrets Manager provides built-in rotation via Lambda and staging labels. Azure Key Vault creates new versions while Event Grid/Functions or workers coordinate target credential updates. Google Cloud Secret Manager emits rotation notifications via Pub/Sub; subscribers perform credential changes and add new versions.

No provider automatically knows how every external service changes passwords. Rotation workflows must understand the target system's protocol.

### 8.2. Differences in refresh

- AWS: reload must be enabled with supporting dependencies; refresh and restart_context behave differently.
- Azure: KeyVaultPropertySource refreshes periodically; verify whether beans/clients pick up new values.
- Google Cloud: Config Data loads secrets; Actuator refresh supports @ConfigurationProperties/@RefreshScope beans per documentation.

For DataSources, pooled clients, TLS contexts, or SDK clients holding credentials, treat rolling restarts as the default choice until tests prove in-place refresh is safe.

### 8.3. Avoid forcing providers into a fake unified API

Business services can share the same property keys, while provider adapters, identities, rotation triggers, and version semantics remain distinct. Separate configuration by profile and keep business code dependent on domain interfaces rather than AWS SecretsManagerClient, Azure SecretClient, or Google SecretManagerTemplate.

## 9. Safe Secret Rotation Workflow

### 9.1. Preparing before rotation

Every secret needs governance metadata:

- Business owner and technical owner.
- Applications, environments, and resources using it.
- Credential type and target system.
- Creation date, last rotation date, and expiration if applicable.
- Secret resource ID and version ID.
- Replica/consumer count.
- Rotation, testing, rollback, and revocation procedures.
- On-call contact when rotation fails.

Maintain an inventory for database passwords, partner API keys, SMTP credentials, certificates, and signing keys. Never store secret payloads in the inventory.

### 9.2. Prefer overlap or dual credentials

If the target system allows two active credentials simultaneously, use this workflow:

1. Create the new credential.
2. Keep the old credential active.
3. Store the new credential as a new secret version.
4. Deploy a canary or a single replica reading the new version.
5. Verify connectivity and permissions.
6. Rolling restart remaining replicas.
7. Monitor authentication errors, connection pools, and request latency.
8. Confirm no consumers remain on the old credential.
9. Revoke the old credential.

Overlap provides a window to roll back if the new credential is faulty or not yet received by all instances.

### 9.3. When the target system only supports one password

Some databases or services allow only one active password at a time. Tight coordination is required:

1. Put the application into maintenance/controlled rollout if needed.
2. Take a backup or verify a fallback administrative access path.
3. Change the password at the target system.
4. Update the secret manager immediately afterward.
5. Restart/refresh workloads per plan.
6. Verify connections from every zone/replica.
7. On failure, use the administrative account to reset the password and resync the secret version.
8. Record downtime duration and verification evidence.

For systems supporting credential rollover, A/B users, or token overlap, migrate to those patterns to minimize downtime.

### 9.4. Canary and rolling deployment

Do not swap secrets across all instances simultaneously without good reason. A rollout flow can be:

- Canary: one instance or a small slice of traffic uses the new version.
- Verify: health checks, database connectivity, API success rates, and authorization.
- Expand: roll forward to remaining replicas.
- Stabilize: observe during a defined soak window.
- Revoke: revoke the old credential once confirmed.

Each deployment should record the active version ID. Never log payloads—only log version identifiers or non-sensitive metadata.

### 9.5. Rollback

Rollback is not just pointing the secret manager back to an older version. The old credential must still be valid at the target system. If the old credential has already been revoked, rolling back to the old secret version will not restore connectivity.

Before revoking the old credential:

- Confirm all instances use the new version.
- Confirm jobs, scheduled tasks, batch workers, and disaster recovery environments have switched.
- Confirm connection pools have been recreated.
- Check audit/access logs to confirm zero remaining usage of the old credential if supported.
- Maintain a clear rollback path with a time window and owner.

## 10. Refreshing Spring Beans and Connection Pools

### 10.1. Why property refresh may be insufficient

Suppose Spring Boot binds a password into a DataSource at startup. The secret manager updates the value in the Environment, but the DataSource/HikariCP pool was created earlier. The pool may continue opening connections using the old password.

Similarly:

- HTTP clients may cache Authorization headers.
- SDK clients may retain tokens/certificates.
- TLS contexts may retain old certificates.
- Background workers may hold stale configuration objects.
- Singleton beans may not re-read the Environment on every call.

### 10.2. Choosing a strategy by secret type

| Secret type | Recommended rollout approach |
| --- | --- |
| API key read per request from refresh-scoped config | Refresh bean and test request |
| HTTP client holding API key in an interceptor | Recreate client after refresh |
| Database username/password in HikariCP | Rolling restart or pool replacement with drain |
| TLS client certificate | Reload SSL context/client or restart |
| Signing key with key ID/version | Support multiple keys and overlapping key rotation |
| Short-lived token from identity provider | Refresh token via credential provider; do not rotate manually |

### 10.3. Using @RefreshScope appropriately

@RefreshScope fits configuration beans that can be recreated upon refresh. Do not blindly wrap entire services or DataSources without checking proxies, lifecycle, and connection closure. For pools, ensure:

- In-use connections are not returned to an already closed pool.
- Active transactions are not aborted mid-flight.
- The new pool uses the new secret version.
- The old pool is drained and closed.
- If the new pool fails to initialize, the application maintains a safe readiness state or rolls back.

### 10.4. Securing Actuator

If using /actuator/refresh or /actuator/restart:

- Expose only the necessary endpoints.
- Allow access only from the management network.
- Enforce authentication and authorization.
- Never expose env, configprops, heapdump, or sensitive endpoints publicly.
- Audit callers of the endpoint.
- Prevent refresh endpoints from becoming public triggers for restart storms.

### 10.5. Readiness and startup

If a mandatory secret cannot be read, the application must not serve traffic. Use readiness checks to wait until DataSources/clients initialize successfully. Liveness checks should only verify the process is alive; do not trigger continuous restarts simply because the secret manager is temporarily slow.

Configure bounded startup retries with backoff. If the secret manager is unavailable, deciding whether to fail startup or continue with a cached version must be a deliberate decision weighed against risk and availability requirements.

## 11. Secret Security and Operations

### 11.1. Least privilege

- Applications only read secrets needed for the service.
- Rotation workers have permission to create versions and update target credentials.
- Operators manage lifecycle and policies.
- Auditors view metadata/logs without reading payloads.
- Isolate secrets by app, environment, and purpose.
- Avoid sharing the same database password across multiple services.

### 11.2. Encryption and networking

Secret managers encrypt data at rest and protect connections with TLS. For network isolation requirements, use private endpoints/VPC endpoints/service endpoints per cloud provider. Network restrictions do not replace IAM; workloads still need valid identities and permissions.

### 11.3. Logging and observability

Helpful metadata to log:

- Secret resource name or opaque identifier.
- Version ID.
- Rotation event ID.
- Actor/rotation worker identity.
- Start/end timestamps.
- Outcome and failure code.
- Application deployment ID.

Never log secret payloads, passwords, tokens, private keys, certificate private material, or request headers containing credentials.

### 11.4. Rotation metrics

Monitor:

- Secret age and last rotation timestamp.
- Secrets approaching expiration.
- Rotation success/failure counts.
- Number of instances still on old versions.
- Secret access denied/timeout errors.
- Authentication failures after rotation.
- Connection pool creation failures.
- Rollback counts.
- Old credentials still in use after the transition window.

Alert when a secret is overdue for rotation, a rotation fails, or applications fail to switch versions before the deadline.

### 11.5. Auditing and incident response

When secret exposure is suspected:

1. Identify affected secrets and consumers.
2. Issue new credentials or revoke old credentials depending on urgency.
3. Update the secret manager and roll out the application.
4. Inspect secret manager access logs/audit events.
5. Inspect target systems for anomalous requests.
6. Revoke the exposed credential once applications are confirmed on the new credential.
7. Consider rotating related secrets sharing the same trust boundary.
8. Document timeline, owners, and evidence.

Never merely delete a secret from Git. If a secret was ever committed, treat the credential as compromised and rotate it at the target system.

## 12. End-to-End Lab

### 12.1. Scenario

document-service runs on a cloud provider and needs to:

- Connect to PostgreSQL with username/password.
- Call a partner API using an API key.
- Read timeouts and retry counts from non-sensitive configuration.
- Rotate the database password every operational cycle.
- Rotate the partner API key when exposure is suspected.
- Roll back if a new version causes health checks to fail.

### 12.2. Preparing resources

Choose one of the three environments:

**AWS**

- Create a Secrets Manager secret for database credentials.
- Create a Parameter Store path for retry/timeout/feature flags.
- Attach an IAM role to the workload.
- Create a rotation Lambda or database-appropriate rotation workflow.
- Enable CloudTrail and CloudWatch monitoring.

**Azure**

- Create a Key Vault for the target environment.
- Enable the Azure RBAC permission model.
- Attach a managed identity to the workload.
- Assign Key Vault Secrets User to the application identity.
- Create an Event Grid subscription and Function/worker if automated rotation is needed.
- Enable diagnostic logs.

**Google Cloud**

- Create a Secret Manager secret and version.
- Attach a service account or Workload Identity to the workload.
- Grant Secret Accessor at the secret level.
- Create a Pub/Sub topic/subscriber if using a rotation schedule.
- Enable audit logs and monitoring.

### 12.3. Configuring Spring profiles

Select the profile for the environment:

~~~bash
SPRING_PROFILES_ACTIVE=aws
~~~

Or:

~~~bash
SPRING_PROFILES_ACTIVE=azure
~~~

Or:

~~~bash
SPRING_PROFILES_ACTIVE=gcp
~~~

Only the corresponding profile is used for a deployment. Do not enable all three secret manager profiles simultaneously in production unless the application legitimately needs multi-cloud reading.

### 12.4. Verifying startup

After the application starts:

1. Confirm the profile is active.
2. Confirm secret resources are read using workload identity.
3. Confirm the DataSource connects successfully.
4. Confirm the partner client calls the test endpoint successfully.
5. Confirm non-sensitive properties bind properly.
6. Check logs to verify no secrets appear.
7. Verify read permissions are restricted to required resources only.

Never build a debug endpoint returning Environment or full configuration to verify secrets.

### 12.5. Rotating the database password

Run in staging first:

1. Create a new database credential using dual credentials/overlap if supported.
2. Write the new credential as a new secret version.
3. Select the new version for a canary or create a new deployment.
4. Restart the canary so DataSource/HikariCP loads the new password.
5. Run smoke test queries and transaction rollback tests.
6. Open traffic to the canary and monitor connection errors.
7. Rolling restart remaining replicas.
8. Confirm no replicas remain on the old version.
9. Revoke the old credential.
10. Record the version ID, deployment ID, and test results.

### 12.6. Rotating the partner API key

1. Request a second key from the partner if they support overlap.
2. Save the new key in the secret manager.
3. Refresh PartnerProperties or rolling restart.
4. Send canary requests and inspect responses.
5. Gradually shift traffic.
6. Confirm the old key is no longer used.
7. Revoke the old key with the partner.
8. Check application logs and partner audit logs.

If the partner only allows a single active key, coordinate the key swap and rollout timing to minimize disruption.

### 12.7. Testing rollback

Create an invalid test secret version in staging:

- The canary must detect authentication failure.
- Do not expand the rollout.
- The application logs failure codes and version metadata without payloads.
- Restore the known-good version or recreate the credential.
- Recreate clients/pools.
- Verify health and readiness.
- Keep the old credential valid until rollback completes.

Never test bad secrets in production or against shared credentials.

## 13. Testing

### 13.1. Unit tests

Verify:

- Configuration properties fail validation when required keys are missing.
- toString() and logs do not reveal secrets.
- Client builders pick up new properties after refresh.
- Retries do not loop indefinitely.
- Secret version metadata is stored alongside deployment state.
- Rollback selects a previously verified version.

### 13.2. Integration tests

In an isolated test account/project/subscription:

1. Application reads the right secret.
2. Workload identity works without static credentials.
3. Missing required secrets fail startup.
4. Principals without permission receive authorization errors.
5. New secret versions are read properly.
6. New DataSources use the new credential.
7. New partner clients use the new API key.
8. Old credentials are revoked after rollout completes.
9. Refresh endpoints are unreachable from public networks.
10. Secret payloads never appear in logs, traces, or metrics.

### 13.3. Negative tests

- Revoke secret read permission.
- Configure an incorrect secret resource name.
- Disable the referenced secret version.
- Set a secret as expired or not-yet-valid if supported by the provider.
- Use a new credential before updating the target system.
- Revoke the old credential prematurely in staging.
- Emit duplicate rotation events.
- Trigger concurrent refreshes across multiple replicas.
- Make the secret manager temporarily unavailable.

The application must fail safely with metrics/correlation IDs and without leaking secrets in error messages.

## 14. Troubleshooting

| Symptom | Possible cause | Resolution direction |
| --- | --- | --- |
| Spring startup cannot find config import | Missing starter, wrong prefix, or profile inactive | Check dependencies, profile, and provider syntax |
| AWS AccessDeniedException | Missing GetSecretValue/GetParametersByPath or KMS Decrypt | Check IAM role, ARN, region, and KMS key policy |
| AWS new secret created but app still uses old one | Reload disabled or bean not refreshed | Enable reload, use restart_context, or rolling restart |
| Azure 403 Forbidden | Managed identity lacks Key Vault Secrets User | Check principal and RBAC scope |
| Azure secret fails to bind to property | Secret name uses dots or wrong mapping | Use hyphens and check key mapping |
| Azure version updated but app has not picked it up | Refresh interval not reached or singleton not recreated | Wait for controlled refresh or restart workload |
| GCP PermissionDenied | Missing Secret Accessor or ADC using wrong service account | Check workload identity and role on secret |
| GCP Config Data resolver not working | Missing starter or wrong sm@ syntax | Check BOM, dependencies, and updated syntax |
| GCP new version unused | Application pinned to older version | Update deployment version and roll out |
| Database still rejects after secret change | HikariCP retains old connection/credential or DB password unchanged | Recreate pool, inspect target system, and check credential overlap |
| Partner API returns 401/403 | New key not yet activated or client not reloaded | Check key state and recreate client |
| Rotation worker runs twice | Event redelivery or retry | Use idempotency keys and persist rotation state |
| Rollback to old version fails to connect | Old credential already revoked | Create recovery credential or update DB before rollback |
| Actuator refresh exposed | Endpoint exposed publicly | Restrict management network and enable authentication |
| Secret appears in logs | Debug serialization, exceptions, or actuator | Redact, fix logging, and rotate the exposed credential |

## 15. Operational Runbook

### 15.1. Before every rotation

- Identify owner and rotation window.
- Identify all workloads/replicas/workers using the secret.
- Verify overlap and rollback capability.
- Confirm the secret manager and target system are healthy.
- Verify rotation worker permissions.
- Announce maintenance window if necessary.

### 15.2. During rotation

- Create the new credential at the target system.
- Write the new version to the secret manager.
- Run a canary.
- Verify database/API authentication.
- Roll out across replica groups.
- Monitor metrics and logs.
- Keep the old credential active.

### 15.3. After rotation

- Confirm all instances run on the new version.
- Confirm connection pools are recreated.
- Revoke the old credential.
- Close the rotation event.
- Record the version ID and deployment ID.
- Inspect audit logs.
- Update the next rotation date.

### 15.4. When rotation fails

- Halt the rollout.
- Do not revoke the old credential.
- Isolate whether the fault lies in the secret manager, identity, target system, or application binding.
- Roll back the secret version or create a recovery version.
- Recreate clients/pools.
- Verify health and readiness.
- Resume traffic only after the canary passes.
- Document root cause and improve automation.

## 16. Self-Assessment Exercises

1. How does regular configuration differ from secrets?
2. Why should database passwords not be committed to application-prod.yml?
3. At which phase does the Spring Boot Config Data API load secrets?
4. Why should optional import not be used for mandatory database passwords?
5. How does AWS Parameter Store differ from Secrets Manager?
6. What do AWS Secrets Manager staging labels AWSCURRENT, AWSPREVIOUS, and AWSPENDING mean?
7. What are the four steps of a Lambda rotation workflow?
8. Why should AWS workloads use IAM roles instead of static access keys?
9. What character restrictions apply to Azure Key Vault secret names?
10. How does Key Vault Secrets User differ from Key Vault Contributor?
11. How are DefaultAzureCredential and Managed Identity related?
12. Why does refreshing Azure KeyVaultPropertySource not automatically change HikariCP's password?
13. Does Google Secret Manager store payloads in the secret resource or the secret version?
14. Why should production pin version IDs instead of using latest?
15. What permission does roles/secretmanager.secretAccessor grant?
16. Does Google Cloud's rotation schedule change database passwords automatically or only emit Pub/Sub notifications?
17. When should @RefreshScope be used?
18. Why does DataSource require a restart or pool replacement after password rotation?
19. Why must the old credential remain valid during rollout?
20. When is it safe to revoke the old credential?
21. If a rotation worker receives the same event twice, what safeguards are needed?
22. Why should secret version payloads never be logged during debugging?
23. How do you prove all replicas have switched to the new version?
24. If you roll back a secret version after the old credential was already revoked, how must you recover?

**Guided answers:** Configuration describes behavior while secrets authorize authentication/access; Spring Config Data loads external sources at startup; missing required secrets must fail startup; Parameter Store suits configuration and SecureString, while Secrets Manager provides version labels and rotation workflows; AWSCURRENT is active, AWSPENDING is rotating, AWSPREVIOUS is prior; Lambda rotation comprises createSecret, setSecret, testSecret, finishSecret; IAM roles supply short-lived credentials; Key Vault secret names allow only letters/digits/hyphens; Secrets User reads data plane while Contributor manages control plane; DefaultAzureCredential can use Managed Identity on Azure; refreshing PropertySource does not automatically recreate singleton DataSources; GCP payloads live in versions; pinning versions enables controlled rollouts/rollbacks; Secret Accessor permits reading payloads; Pub/Sub only notifies, and subscribers execute rotation; @RefreshScope fits recreatable beans; Hikari requires drain/recreation; overlap enables rollback; revoke old credentials only after every consumer switches; events require idempotency; logs record metadata only; verify via versions/deployments/metrics; if the old credential was revoked, provision a recovery credential and resync the secret.

## 17. Official References

### Spring Boot

- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): Config Data API, PropertySource, config imports, config trees, and property precedence.
- [Spring Cloud Context Refresh](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): RefreshScope and refresh lifecycle.

### AWS

- [Spring Cloud AWS 4.1.1 – Secrets Manager Integration](https://docs.awspring.io/spring-cloud-aws/docs/4.1.1/reference/html/index.html): starter, config import, JSON secrets, reload strategies, and IAM permissions.
- [Spring Cloud AWS 4.1.1 – Parameter Store Integration](https://docs.awspring.io/spring-cloud-aws/docs/4.1.1/reference/html/index.html): config import, prefixes, SSM client, reload, and IAM permissions.
- [AWS Secrets Manager – Secret Versions](https://docs.aws.amazon.com/secretsmanager/latest/userguide/whats-in-a-secret.html): versions and staging labels.
- [AWS Secrets Manager – Lambda Rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda-functions.html): createSecret, setSecret, testSecret, and finishSecret.
- [AWS Secrets Manager – Rotation Strategies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotation-strategy.html): single-user and alternating-user strategies.
- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html): parameter hierarchy, SecureString, and KMS.

### Azure

- [Spring Cloud Azure – Secret Management](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/secret-management): KeyVaultPropertySource, secret-keys, property mapping, and refresh intervals.
- [Spring Cloud Azure – Authentication](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/authentication): DefaultAzureCredential, Managed Identity, and Workload Identity.
- [Azure Key Vault RBAC Guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide): Key Vault Secrets User, Secrets Officer, and control/data planes.
- [Azure Key Vault Secret Rotation Tutorial](https://learn.microsoft.com/en-us/azure/key-vault/secrets/tutorial-rotation): Event Grid and Function rotation workflow.
- [Azure Key Vault Event Grid Schema](https://learn.microsoft.com/en-us/azure/event-grid/event-schema-key-vault): SecretNewVersionCreated and SecretNearExpiry events.
- [Spring Cloud Azure Version Mapping](https://github.com/Azure/azure-sdk-for-java/wiki/Spring-Versions-Mapping): Spring Boot, Spring Cloud, and Spring Cloud Azure compatibility.

### Google Cloud

- [Spring Framework on Google Cloud 8.2.4 – Secret Manager](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.4/reference/html/index.html): starter, Config Data resource, SecretManagerTemplate, and refresh.
- [Google Cloud Secret Manager – Access a Secret Version](https://docs.cloud.google.com/secret-manager/docs/access-secret-version): version IDs, latest, and Secret Accessor role.
- [Google Cloud Secret Manager – IAM Access Control](https://docs.cloud.google.com/secret-manager/docs/access-control): Secret Accessor, Secret Version Adder, and Secret Version Manager.
- [Google Cloud Secret Manager – Rotation Schedules](https://docs.cloud.google.com/secret-manager/docs/secret-rotation): Pub/Sub notifications and rotation schedules.
- [Google Cloud Secret Manager – Rotation Recommendations](https://docs.cloud.google.com/secret-manager/docs/rotation-recommendations): gradual rollouts, version pinning, rollback, and idempotency.
- [Google Cloud Secret Manager – Best Practices](https://docs.cloud.google.com/secret-manager/docs/best-practices): version pinning, disabling before destroying, and rotation.

**Key takeaway:** Secret managers protect payloads and manage versions; workload identities grant read access; Spring Config Data brings values into the Environment; refresh only updates supported beans; rotation must update both the target system and the application. For database credentials and connection-holding clients, roll out with overlap, verify with a canary, recreate pools/clients, preserve a rollback path, and revoke old credentials only after every consumer has moved to the new version.
