# Secrets Manager and Application Secret Storage

A Spring Boot application needs to connect to Amazon RDS, call a partner API, and sign requests to an internal service. If usernames/passwords, API keys, or tokens are written directly into source code, configuration files, Docker images, or long-lived environment variables, secrets can leak through Git, CI logs, image registries, process inspection, or backups.

**AWS Secrets Manager** is a centralized secret management service. Applications can retrieve secrets while running with an IAM role; Secrets Manager encrypts values using AWS KMS, manages secret versions, and supports automatic rotation. Secrets can be shared in a controlled manner across services, accounts, and Regions.

For Java, integration typically uses the AWS SDK for Java 2.x or the Secrets Manager Java caching client. You should not call the API to fetch a secret on every request; in-process caching reduces latency and API costs. However, caching must be designed alongside the rotation schedule so the application does not keep using old credentials for too long.

This lesson belongs to the **Encryption, Secrets, and Certificates** chapter of the **CLOUD_PROVIDERS_AWS** module. It focuses on secret lifecycle, version/staging labels, IAM/KMS, rotation, Java integration, caching, private connectivity, cross-account access, multi-Region replication, and secure operational workflows.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish secrets from ordinary configuration.
2. Describe the components of a secret and how Secrets Manager stores versions.
3. Explain the roles of `AWSCURRENT`, `AWSPREVIOUS`, and `AWSPENDING`.
4. Create JSON or binary secrets and manage versions.
5. Retrieve secrets using the AWS Console, CLI, and AWS SDK for Java 2.x.
6. Integrate Secrets Manager with Spring Boot using an IAM role.
7. Use the Java caching client and choose an appropriate TTL.
8. Explain envelope encryption with AWS KMS.
9. Grant `GetSecretValue` and `kms:Decrypt` following least privilege.
10. Distinguish an AWS managed key from a customer managed KMS key.
11. Set up automatic rotation and understand the four steps of a rotation Lambda.
12. Compare single-user rotation with alternating-users rotation.
13. Design applications resilient to credential rotation.
14. Configure a VPC interface endpoint for Secrets Manager.
15. Grant secret access across AWS accounts.
16. Replicate secrets across multiple AWS Regions and monitor replication status.
17. Use CloudTrail for auditing without logging secret values.
18. Manage the deletion recovery window, version quotas, and cost.
19. Troubleshoot IAM, KMS, rotation, cache, and network errors.
20. Build a production secret protection checklist.

## 2. What Is a Secret and When Should You Use It?

A secret is sensitive data that an application or operator needs to authenticate, authorize, or access a resource. Examples:

- Database usernames/passwords.
- Partner API keys.
- OAuth client secrets.
- Private tokens used for service-to-service authentication.
- Credentials for systems outside AWS.
- Authentication credentials for a workload or automation.

Not every configuration value is a secret. Non-sensitive values like Region, log level, or feature flags typically belong in AWS Systems Manager Parameter Store or AppConfig. Credentials and keys requiring access control, encryption, rotation, and auditing typically belong in Secrets Manager.

| Need | Common choice |
|---|---|
| Database password needing rotation | Secrets Manager |
| API key needing version management and rotation | Secrets Manager |
| Feature flags or non-sensitive configuration | AWS AppConfig |
| Hierarchical config values, optionally `SecureString` | Systems Manager Parameter Store |
| Dedicated private key/certificate lifecycle | AWS Certificate Manager or an appropriate PKI solution |
| Temporary AWS workload credentials | IAM role/STS; do not create long-lived access keys to store in a secret |

Secrets Manager does not replace IAM roles. If an application only needs to call AWS APIs, use temporary credentials from a task role, instance profile, or workload identity. Never create IAM user access keys and store them in Secrets Manager if a role can meet the need.

## 3. Storage and Retrieval Architecture

An application running on an ECS task needs database credentials:

    Spring Boot application
            |
            | IAM task role
            v
      AWS Secrets Manager
            |
            | KMS envelope encryption
            v
       Encrypted secret value

When the application retrieves a secret:

1. The AWS SDK obtains temporary credentials from the task role.
2. The SDK calls `GetSecretValue` on Secrets Manager.
3. Secrets Manager evaluates IAM/resource policies.
4. Secrets Manager requests AWS KMS to decrypt the data key.
5. Secrets Manager decrypts the secret value and returns it over TLS.
6. The application parses the secret and uses it to connect to the database.

The application needs permission to read the specific secret. It does not need permission to create, modify, delete, or configure rotation for the secret if its only responsibility is runtime retrieval.

### 3.1. Secret Value and Metadata

A secret consists of these parts:

| Component | Example | Encrypted like the secret value? |
|---|---|---|
| Secret value | JSON username/password | Yes |
| Secret name | `prod/orders/database` | No |
| Description | Credential for orders database | No |
| Tags | `Environment=prod` | No |
| Rotation configuration | Lambda ARN/schedule | No |
| KMS key reference | Key ARN | No |

Do not place passwords, tokens, or sensitive information in names, descriptions, or tags. Those metadata fields can appear in inventories, API responses, or audit logs.

### 3.2. SecretString and SecretBinary

Secrets Manager supports:

- `SecretString`: a UTF-8 string, typically JSON or plain text.
- `SecretBinary`: binary data, such as a credential blob or application-encrypted material.

For database credentials, JSON lets you store username, password, host, port, engine, and database name in one secret. For binary values, the application must handle formatting and decoding at the appropriate layer.

Illustrative JSON example:

~~~json
{
  "engine": "mysql",
  "host": "orders-db.example.ap-southeast-1.rds.amazonaws.com",
  "port": 3306,
  "dbname": "orders",
  "username": "orders_app",
  "password": "REPLACE_WITH_SECRET_VALUE"
}
~~~

This is an illustrative structure. Never store real values in source code or documentation. Secrets Manager protects only the secret value; metadata must still be named safely.

## 4. Secret Versions and Staging Labels

When a secret value changes, Secrets Manager creates a new version. Each version has a `VersionId` and can carry staging labels indicating its role in the lifecycle.

| Staging label | Meaning |
|---|---|
| `AWSCURRENT` | The version applications should use by default |
| `AWSPREVIOUS` | The version that was previously current |
| `AWSPENDING` | A new version being prepared during rotation |

Secrets Manager does not maintain history as a linear list with fixed states. Labels move between versions. Every secret always has an `AWSCURRENT` version; calling `GetSecretValue` without specifying a version returns the current version.

Example:

    Version A: AWSPREVIOUS
    Version B: AWSCURRENT
    Version C: AWSPENDING

During rotation, Lambda creates the pending version, updates the credential in the database, tests the new credential, and then moves `AWSCURRENT` to that version.

### 4.1. VersionId and Staging Labels

- `VersionId` identifies a specific version.
- A staging label identifies a version's lifecycle role.
- One version can hold multiple labels.
- One label can be attached to only one version at a time.
- Custom labels can be created for internal workflows, up to 20 labels per secret.

Production applications should generally request `AWSCURRENT` rather than hardcoding a `VersionId`. If you hardcode a `VersionId`, the application may keep using old credentials after a successful rotation.

### 4.2. Moving Staging Labels

When `AWSCURRENT` moves to a new version, Secrets Manager automatically moves `AWSPREVIOUS` to the version just replaced. This enables rolling back to the prior version if needed, provided the old credential is still valid on the target system.

Do not manually remove `AWSPENDING` in the middle of an active rotation. The rotation function relies on this label to track progress and ensure idempotency.

### 4.3. Version Limits

Secrets Manager retains up to the 100 most recent versions and does not delete versions created within the last 24 hours. Versions without staging labels are considered deprecated and can be cleaned up when exceeding the quota.

AWS recommends not calling `PutSecretValue` or `UpdateSecret` continuously more frequently than once every 10 minutes. Updating too frequently can cause new versions to accumulate faster than cleanup and hit quotas.

Do not use Secrets Manager as a database for frequent state writes. Secrets are meant for credentials and sensitive values with relatively stable lifecycles.

## 5. Creating and Naming Secrets

Name secrets by service, environment, and purpose:

    prod/orders/database
    prod/payment/provider-api
    staging/inventory/database
    shared/partner-x/oauth-client

A clear naming convention makes IAM policies, inventories, and audits easier to read. Secret names must not contain usernames/passwords or PII.

Standardize `environment`, `service`, `purpose`, `owner/team` tags, `data classification`, and `rotation owner` if your organization has a taxonomy.

### 5.1. Creating a Secret via the Console

1. Open AWS Secrets Manager in the right Region.
2. Choose **Store a new secret**.
3. Choose the appropriate secret type, such as credentials for an Amazon RDS database.
4. Enter the secret value.
5. Select the KMS key.
6. Set a safe secret name and description.
7. Add non-sensitive tags.
8. Configure rotation if supported by the secret type and target.
9. Review access permissions and create the secret.

After creation, verify the ARN, KMS key, version stage, and policy. Never share secret values via screenshots or tickets.

### 5.2. Creating a Secret with the AWS CLI

You can use `create-secret` reading the value from a protected file:

~~~bash
aws secretsmanager create-secret \
  --name "prod/orders/database" \
  --description "Database credentials for orders service" \
  --secret-string file://secret.json \
  --region ap-southeast-1
~~~

The `secret.json` file must be created with restricted filesystem permissions and never committed to Git, CI artifacts, or logs. Securely delete the file per data protection procedures once done.

Never pass real passwords directly on the command line like `--secret-string '{"password":"..."}'`. Shell history, process inspection, or CI command logging can expose arguments.

### 5.3. Updating a Secret Value

Use `PutSecretValue` to create a new version:

~~~bash
aws secretsmanager put-secret-value \
  --secret-id "prod/orders/database" \
  --secret-string file://secret-next.json \
  --region ap-southeast-1
~~~

If `VersionStages` is omitted, Secrets Manager attaches `AWSCURRENT` to the new version and moves `AWSPREVIOUS` according to version staging rules.

Do not update the same secret continuously on every deployment. If the credential has not changed, the application simply reads the existing secret; do not create a new version.

## 6. IAM: Least-Privilege Secret Read Permissions

An application that only needs to retrieve a secret typically needs:

- `secretsmanager:GetSecretValue` on the specific secret ARN.
- `kms:Decrypt` on the customer managed key if the secret uses a key you manage and the key policy requires this permission.

Minimal identity policy example for an application:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrdersDatabaseSecret",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:prod/orders/database-AbCdEf"
    }
  ]
}
~~~

If using a customer managed KMS key, add `kms:Decrypt` for the corresponding key ARN and ensure the key policy allows that principal. Do not grant `secretsmanager:PutSecretValue`, `DeleteSecret`, or `RotateSecret` to a runtime application if it only reads secrets.

### 6.1. Using IAM Roles Instead of Access Keys

| Platform | Identity to use |
|---|---|
| Amazon EC2 | Instance profile |
| Amazon ECS | Task role |
| Amazon EKS | EKS Pod Identity or IRSA depending on architecture |
| AWS Lambda | Execution role |
| On-premises | IAM Roles Anywhere or appropriate credential federation |

Never place access keys/secret keys in `application.properties`, Docker `ENV`, static Kubernetes Secrets, or AMIs. Runtime credentials should be provisioned automatically and be short-lived.

### 6.2. Secrets Manager Resource Policies

A resource policy attaches directly to a secret to specify which principals may access it. It is useful when multiple roles/accounts need to use the same secret.

When attaching a policy:

- Use `BlockPublicPolicy` when calling `PutResourcePolicy`.
- Use `ValidateResourcePolicy` or console validation.
- Avoid `Principal: "*"` unless tightly constrained by conditions.
- Do not grant `PutResourcePolicy` to an application role.
- Review identity policies, resource policies, and KMS key policies together.

A resource policy does not automatically replace an identity policy in all scenarios. Final access depends on the entire authorization model, explicit denies, SCPs/RCPs, permissions boundaries, and KMS.

## 7. Encrypting Secrets with AWS KMS

Secrets Manager uses **envelope encryption**. KMS does not directly encrypt the entire secret value; KMS generates and protects the data key used to encrypt the value.

Write flow:

1. Secrets Manager calls KMS `GenerateDataKey` to obtain a plaintext data key and an encrypted data key.
2. Secrets Manager uses AES to encrypt the secret value with the plaintext data key.
3. The plaintext data key is cleared from memory when no longer needed.
4. The encrypted data key is stored alongside the secret's metadata.

Read flow:

1. Secrets Manager retrieves the encrypted data key.
2. It calls KMS `Decrypt` to decrypt the data key.
3. It uses the data key to decrypt the secret value.
4. It returns the secret to the caller over TLS.

The secret value is encrypted at rest. Secret name, description, tags, rotation settings, and KMS key ARN are not encrypted like the secret value.

### 7.1. AWS Managed Key vs. Customer Managed Key

| Criterion | `aws/secretsmanager` | Customer managed KMS key |
|---|---|---|
| Key policy management | Managed by AWS | Managed by the customer |
| Key cost | No key fee | KMS key/API charges per pricing |
| Cross-account access | Not suitable | Can be configured |
| Key rotation policy | Managed by AWS | Can enable automatic rotation |
| KMS condition control | Limited | Customizable key policies/grants |

For most secrets within a single account, AWS recommends `aws/secretsmanager`. Use a customer managed key when you need cross-account access, a custom key policy, or specific key governance requirements.

### 7.2. Restricting KMS Access with ViaService and Encryption Context

You can restrict a key to be used only through Secrets Manager using the `kms:ViaService` condition with the Regional service hostname:

    secretsmanager.ap-southeast-1.amazonaws.com

You can combine encryption context, such as `SecretARN`, to scope key operations to a specific secret. This reduces the risk of key usage outside its intended purpose.

Do not write overly broad key policies just to fix `AccessDenied`. Identify the principal, KMS action, `ViaService`, encryption context, and explicit denies before modifying anything.

## 8. Retrieving Secrets with AWS SDK for Java 2.x

AWS SDK for Java 2.x provides `SecretsManagerClient` and `GetSecretValueRequest`.

Maven dependency:

~~~xml
<dependency>
  <groupId>software.amazon.awssdk</groupId>
  <artifactId>secretsmanager</artifactId>
  <version>AWS_SDK_VERSION</version>
</dependency>
~~~

`AWS_SDK_VERSION` should be managed centrally using the AWS SDK BOM so modules use compatible versions.

Java example:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueRequest;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueResponse;

public final class DatabaseSecretLoader {
    private final SecretsManagerClient client;
    private final ObjectMapper mapper = new ObjectMapper();

    public DatabaseSecretLoader(Region region) {
        this.client = SecretsManagerClient.builder()
                .region(region)
                .build();
    }

    public DatabaseCredentials load(String secretId) throws Exception {
        GetSecretValueRequest request = GetSecretValueRequest.builder()
                .secretId(secretId)
                .versionStage("AWSCURRENT")
                .build();

        GetSecretValueResponse response = client.getSecretValue(request);
        JsonNode json = mapper.readTree(response.secretString());

        return new DatabaseCredentials(
                json.path("host").asText(),
                json.path("port").asInt(),
                json.path("dbname").asText(),
                json.path("username").asText(),
                json.path("password").asText()
        );
    }

    public void close() {
        client.close();
    }
}
~~~

`DatabaseCredentials` is an application-defined DTO. This example omits validation and error mapping to focus on the API. In production, validate required fields, data types, port ranges, and handle malformed secret formats.

### 8.1. Reusing the Client and Credentials Provider

Do not instantiate a new `SecretsManagerClient` on every HTTP request. AWS SDK clients are thread-safe and should be reused across the application lifecycle.

When running on AWS, the SDK default credentials provider chain obtains credentials from the task role, instance profile, or Lambda execution role. Never pass access keys directly in source code.

Spring configuration example:

~~~java
@Configuration
public class SecretsConfiguration {
    @Bean(destroyMethod = "close")
    SecretsManagerClient secretsManagerClient() {
        return SecretsManagerClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

In larger applications, inject the client/secret provider into services rather than invoking the builder in multiple places.

### 8.2. Retrieving Binary Secrets

If a secret uses `SecretBinary`, read `response.secretBinary()` and process the byte buffer according to the agreed format. Do not assume every secret populates `secretString()`.

### 8.3. BatchGetSecretValue

If an application needs multiple secrets, the `BatchGetSecretValue` API can reduce individual calls. Verify quotas, filters, and permissions for each secret; batching does not mean every secret is permitted to be read. For typical applications, caching individual secrets by lifecycle is often easier to control.

## 9. Java Client-Side Caching

AWS recommends caching secrets on the client side to reduce latency and API call costs. Calling `GetSecretValue` on every HTTP request directly ties the application to Secrets Manager's latency/availability and generates unnecessary requests.

The Java caching client holds secrets in process memory, using an LRU cache and refreshing based on TTL.

Maven dependency for the AWS Secrets Manager Java caching client:

~~~xml
<dependency>
  <groupId>com.amazonaws.secretsmanager</groupId>
  <artifactId>aws-secretsmanager-caching-java</artifactId>
  <version>2.2.0</version>
</dependency>
~~~

Check the current release in the official repository before pinning a version. The v2 line of the library uses AWS SDK for Java 2.x.

Example:

~~~java
import com.amazonaws.secretsmanager.caching.SecretCache;
import com.amazonaws.secretsmanager.caching.SecretCacheConfiguration;
import java.util.concurrent.TimeUnit;

public final class CachedSecretProvider implements AutoCloseable {
    private final SecretCache cache;

    public CachedSecretProvider() {
        SecretCacheConfiguration config =
                new SecretCacheConfiguration()
                        .withCacheItemTTL(TimeUnit.MINUTES.toMillis(5));

        this.cache = new SecretCache(config);
    }

    public String getSecretJson(String secretId) {
        return cache.getSecretString(secretId);
    }

    @Override
    public void close() {
        cache.close();
    }
}
~~~

Initialize the cache once per application process and close it on shutdown. Never create a new cache inside each controller request.

### 9.1. TTL and Rotation

By default, the Java caching client refreshes secrets roughly every hour. You can configure a shorter TTL. The shorter the TTL:

- The faster the application picks up new credentials after rotation.
- The higher the number of API calls to Secrets Manager.
- The greater the dependency on network/service availability.
- Cache refreshes can create simultaneous load bursts if many instances refresh at once.

Choose TTL based on rotation interval, how long old credentials remain acceptable, the number of application instances, and risk tolerance. The 5-minute TTL in the example is illustrative, not a mandatory default.

### 9.2. Cache Is Not an Absolutely Secure Vault

AWS documentation notes that the Java caching client is not designed as a specialized security cache:

- Secrets reside in process memory in usable form for the application.
- The cache does not force garbage collection when references are released.
- The implementation lacks a general cache invalidation API.
- If synchronous refresh fails, the cache may return an older secret.
- The default cache focuses on LRU/TTL and does not encrypt data inside the heap.

Protect heap dumps, core dumps, debug endpoints, memory inspection, and host access. If stronger cache protection is needed, use a custom hook/interface or dedicated cache with appropriate encryption and lifecycle controls.

### 9.3. Designing Caching Alongside Connection Pools

When a database password rotates, a connection pool may hold connections already authenticated with the old credential. Rotation does not automatically close all existing database sessions.

A practical strategy:

1. Cache secrets with a defined TTL.
2. On cache refresh, detect the new version/credential via the application's mechanism.
3. Create or update the datasource/pool with the new credential.
4. Activate new connections and verify health.
5. Drain the old pool and close connections.
6. Maintain bounded retries for authentication failures during the transition window.

Do not recreate the pool on every request. Perform refreshes through a synchronized mechanism so multiple threads do not rebuild the pool simultaneously.

## 10. What Is Rotation?

Rotation is the process of changing credentials on the target system and updating the corresponding secret. For example, changing a database password and storing the new password in Secrets Manager.

Rotation limits the window during which a compromised credential remains usable. However, rotation is safe only when the application, database, and rotation function coordinate properly.

Secrets Manager supports managed rotation for certain AWS services, Lambda-based rotation for many databases/services, single-user rotation, alternating-users rotation, and `rate()` or `cron()` schedules.

Not every secret can be rotated automatically. For third-party API keys or vendor-managed credentials, you need dedicated APIs/automation or a key change procedure matching the provider's capabilities.

## 11. Lambda-Based Rotation: Four Steps

With Lambda-based rotation, Secrets Manager invokes the rotation function in four steps:

    createSecret
        |
        v
    setSecret
        |
        v
    testSecret
        |
        v
    finishSecret
        |
        v
    AWSCURRENT moves to new version

| Step | Task |
|---|---|
| `createSecret` | Create a new version and attach `AWSPENDING` |
| `setSecret` | Update the credential in the database/service |
| `testSecret` | Test access using the new credential |
| `finishSecret` | Move `AWSCURRENT` to the new version |

### 11.1. createSecret

The rotation function checks whether the version token already exists. If not, it generates a new secret value and stores it with `AWSPENDING`.

Using `ClientRequestToken`/version ID makes rotation idempotent. If Lambda is retried, the function must not create an unbounded number of different versions for the same rotation request.

### 11.2. setSecret

The function uses the `AWSCURRENT` credential to authenticate to the database/service, then updates the target credential with the `AWSPENDING` value.

This step holds powerful permissions. The function must verify that the current and pending secrets point to the exact same resource. For example, username and database host must match the intended resource. Otherwise, the function could act as a confused deputy and modify credentials on an unintended resource.

Use query parameterization when sending statements to the database. Never log passwords to CloudWatch Logs.

### 11.3. testSecret

The function uses the `AWSPENDING` credential to connect and verify access permissions. Rotation completes only when the new credential actually works.

Testing should be sufficient to confirm authentication and minimal required privileges without performing unnecessary business mutations.

### 11.4. finishSecret

The function moves `AWSCURRENT` to the new version. Secrets Manager moves `AWSPREVIOUS` to the version just replaced.

Do not remove `AWSPENDING` before completing this step. If rotation fails, inspect staging labels and CloudWatch Logs to identify the failing step; do not manually move labels without understanding the current state.

## 12. Single-User vs. Alternating-Users Rotation

### 12.1. Single-User Rotation

The single-user strategy changes the password of a single database user. This is simple and works well for many scenarios.

Caveat: there is a brief window where the credential in the database and the secret may not be fully synchronized. Applications may encounter authentication failures during cutover. Design appropriate retries and connection pool refresh logic.

### 12.2. Alternating-Users Rotation

The alternating-users strategy uses two database users. The rotation function creates or maintains a cloned user and alternates credentials between the two users.

    Rotation 1:
      orders_app       -> active
      orders_app_clone -> prepared

    Rotation 2:
      orders_app       -> prepared
      orders_app_clone -> active

One user continues operating while the other user is updated. This improves availability if the application can tolerate two equivalent users.

This requires a secret holding admin credentials to clone users and change passwords. Admin credentials must be protected even more tightly than application credentials. Some services/architectures have limitations; for example, RDS Proxy does not support the alternating-users strategy per AWS documentation.

| Criterion | Single user | Alternating users |
|---|---|---|
| Number of database users | One | Two |
| Complexity | Low | Higher |
| Credential availability | Has a transition window to handle | The other user remains active to serve |
| Permissions needed for rotation | Change user password | Clone/manage users |
| Best fit | Simple credentials, retries acceptable | Workloads needing minimized disruption |

## 13. Managed Rotation for AWS Services

Some AWS services manage rotation directly or integrate natively with Secrets Manager. For example, certain services support managing passwords for RDS/Aurora, Redshift, or DocumentDB depending on engine and configuration.

Managed rotation eliminates the Lambda code customers would otherwise maintain. Still, applications must fetch the latest secret by version stage, cache with an appropriate TTL, refresh connection pools, retry transient authentication errors, use least-privilege database users, and verify rotation schedules.

For secret types without managed rotation, use Lambda rotation templates or custom rotation functions following AWS guidance.

## 14. Rotation Schedules and Rotation Windows

Secrets Manager supports `rate()` and `cron()` expressions. Schedules use UTC.

Example:

~~~text
rate(7 days)
~~~

Rotates every 7 days.

Example cron running at 10:00 UTC daily:

~~~text
cron(0 10 * * ? *)
~~~

Rotation can be scheduled as frequently as every 4 hours. The rotation window starts on the hour; default window duration depends on schedule type and can be configured.

When choosing a schedule, consider whether the credential is used continuously, maintenance windows, database load, Lambda timeout/concurrency, replica propagation, and on-call readiness if rotation fails.

Do not choose a rotation schedule solely based on "as frequently as possible." Balance risk, operational load, and the application's ability to refresh credentials.

## 15. Java Applications and Rotation: Avoiding Stale Credentials

A common failure mode is rotation succeeding while the application still connects with the old password due to caching or connection pooling.

Design should include:

1. Reading the secret via `AWSCURRENT`.
2. Cache TTL shorter than the tolerance for stale credentials.
3. A connection factory capable of creating a new datasource/pool.
4. Bounded retries and safe secret refresh on authentication failures.
5. Draining the old connection pool once the new pool is healthy.
6. Metrics/logs recording only secret version ID or stage, never secret values.

Do not retry indefinitely with the old password. Do not refresh the secret for every database error; distinguish authentication errors from network timeouts, SQL errors, or database unavailability.

### 15.1. Race Conditions During Rotation

If many application instances refresh simultaneously, they can trigger a burst of `GetSecretValue` calls and simultaneous database reconnects. Use jitter, backoff, single-flight refresh, or staggered refresh to avoid stampedes.

If the database does not accept two credentials concurrently, coordinate the rotation window and connection pool rollout to avoid outages.

## 16. Rotation Lambda in a VPC

A rotation Lambda needs connectivity to both Secrets Manager and the target database/service. If the database resides in a private subnet, Lambda must have a network path to the database. If Lambda has no Internet egress, a VPC interface endpoint for Secrets Manager is required so API calls do not rely on a public endpoint/NAT.

Verify:

- Lambda security group outbound to the database port.
- Database security group inbound from the Lambda security group.
- Secrets Manager VPC endpoint and private DNS.
- Lambda role permissions to read/write secrets, call rotation APIs, and use KMS if needed.
- Appropriate timeout/concurrency.
- CloudWatch Logs do not record secret values.

Never place a rotation Lambda in a subnet with a route to the database but no endpoint/NAT to Secrets Manager; rotation will time out on the very first step.

## 17. Accessing Secrets Manager via a VPC Endpoint

Applications in private subnets can use an interface VPC endpoint:

    com.amazonaws.<region>.secretsmanager

The endpoint is deployed via AWS PrivateLink. With Private DNS enabled, applications continue using the standard Regional Secrets Manager hostname while DNS resolves to the endpoint ENI.

Verify VPC DNS resolution/hostnames, endpoint subnets/AZs, endpoint security group inbound TCP 443 from the application security group, application egress TCP 443, endpoint policy, resolver, and TLS. A NAT Gateway is not needed solely for calling Secrets Manager once the interface endpoint is working; applications may still need NAT or other endpoints for services outside Secrets Manager.

## 18. Cross-Account Access to Secrets

For an application role in Account B to read a secret in Account A, coordinate:

1. Identity policy on the Account B role allowing `secretsmanager:GetSecretValue` on the Account A secret ARN.
2. Resource policy on the Account A secret allowing the Account B role.
3. KMS key policy/permissions allowing the Account B principal to decrypt.
4. The secret must use a customer managed KMS key; the AWS managed key `aws/secretsmanager` cannot be used for cross-account access.
5. No SCP/RCP, permissions boundary, or explicit deny blocks the request.

Abbreviated resource policy example:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOrdersRuntimeRead",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::444455556666:role/orders-runtime"
      },
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Because a resource policy attaches directly to a single secret, `Resource: "*"` in this statement remains scoped to the secret carrying the policy. In the caller's identity policy, specify the full secret ARN.

Never grant `secretsmanager:PutResourcePolicy` to an application role. Permission to alter resource policies could allow expanding secret access.

### 18.1. BlockPublicPolicy and Access Analyzer

When calling `PutResourcePolicy`, enable `BlockPublicPolicy` so Secrets Manager blocks overly broad/public policies. You can use IAM Access Analyzer to review cross-account access.

Do not inspect only the resource policy. Related identity policies and KMS key policies can also create unintended access paths.

## 19. Replicating Secrets Across Multiple Regions

Multi-Region replication creates replica secrets in other Regions so workloads elsewhere can read a local endpoint, lowering latency and supporting DR.

    Primary secret
    ap-southeast-1
          |
          | Replication
          +-------------------+
          |                   |
          v                   v
    Replica secret       Replica secret
    ap-southeast-2       ap-northeast-1

When the primary secret value changes, Secrets Manager propagates the new version to replicas. Replication is asynchronous and eventually consistent; do not assume replicas receive the new value instantaneously when rotation completes.

### 19.1. KMS Keys in Replica Regions

Each replica is encrypted with a KMS key in the target Region. You can select an AWS managed key or a customer managed key per requirements. If using a customer managed key, configure required permissions for replication and decryption.

### 19.2. Rotation and Replication

If rotation is enabled on the primary, Secrets Manager rotates in the primary Region and propagates the new secret value to replicas. You do not enable rotation independently on each replica of the same multi-Region secret.

Applications in each Region should use the local replica's secret ARN to reduce cross-Region dependencies. Check replication status and design fallbacks if a replica is not yet `InSync`.

### 19.3. Replication Status

| Status | Meaning |
|---|---|
| `Pending` | Replica relationship created but copy has not started |
| `InProgress` | Copying data |
| `InSync` | Replica currently holds the same secret value as the primary |
| `Failed` | Replication failed |
| `Detached` | Replication relationship has been stopped |

When `Failed`, inspect the status message, KMS permissions, enabled Regions, secret name collisions, and CloudTrail events.

## 20. Cross-Account Replication vs. Cross-Account Access

These two mechanisms solve different goals:

| Mechanism | Purpose |
|---|---|
| Cross-account access | An application in another account calls `GetSecretValue` on the original secret |
| Cross-account replication | Creates an independent replica secret in another account and synchronizes values |

Cross-account access requires resource policies, identity policies, and KMS authorization on the source secret. Cross-account replication requires coordination between both accounts and a customer managed KMS key for the replica.

A cross-account replica has its own lifecycle, resource policy, tags, and KMS key. Replication is asynchronous. Do not assume the replica account has full control identical to the primary account.

## 21. Auditing with AWS CloudTrail

Secrets Manager emits CloudTrail events for API operations such as:

- `GetSecretValue`
- `CreateSecret`
- `PutSecretValue`
- `UpdateSecret`
- `RotateSecret`
- `PutResourcePolicy`
- `ReplicateSecretToRegions`
- `DeleteSecret`
- `RestoreSecret`

CloudTrail helps answer which principal called the API, when, in which Region, and on which secret resource. Secret values must never be logged by the application or rotation function.

### 21.1. Never Log Secret Values

Never do the following:

- `System.out.println(secretJson)`.
- Log the full `GetSecretValueResponse`.
- Log the password while parsing JSON.
- Log rotation events including the `AWSPENDING` value.
- Include secrets in exception messages.
- Put secrets into metric dimensions, tracing attributes, or CI output.

You may log a sanitized secret ARN/name, version ID, stage, operation result, and correlation ID if policy allows. Metadata can still be sensitive, so review carefully.

### 21.2. Detecting Anomalous Access

Use CloudTrail Lake/EventBridge/SIEM to detect unusual roles calling `GetSecretValue`, secrets accessed from unexpected Regions/accounts, sudden spikes in API calls, resource policy changes, secrets scheduled for deletion, repeated rotation failures, or cross-Region replication switching to `Failed`.

Never include secret values in alert payloads. Alerts only need ARN, principal, operation, and timestamp.

## 22. Updating, Restoring, and Deleting Secrets

### 22.1. Restoring Secrets

When a secret is scheduled for deletion, it cannot be read until restored. Use `RestoreSecret` before applications try to fetch the secret value again.

### 22.2. Deletion Recovery Window

Secrets Manager does not delete secrets immediately by default. Recovery window:

- Minimum 7 days.
- Default 30 days.
- Maximum 30 days.

During the recovery window, the secret cannot be retrieved but can be restored. After the window expires, the service permanently deletes it in the background.

### 22.3. Force Delete

`ForceDeleteWithoutRecovery` bypasses the recovery window and cannot be undone. Use it only with explicit approval and confirmation that no consumers or replicas depend on it.

A primary secret that is actively replicating cannot be deleted before handling its replicas. For cross-account replication, stop/disassociate replication using the corresponding API.

### 22.4. Deleting Versions

You do not delete a secret version directly. Remove all staging labels using `UpdateSecretVersionStage` to mark the version deprecated; Secrets Manager cleans up deprecated versions per lifecycle rules.

## 23. Cost and Quotas

Secrets Manager cost depends on the number of stored secrets, API calls, replica secrets, and ancillary resources such as KMS customer managed keys, rotation Lambdas, and network endpoints.

Optimization practices:

- Use caching to reduce `GetSecretValue` calls.
- Do not create separate secrets per request/user unless necessary.
- Use naming/ownership metadata to clean up unused secrets.
- Set rotation schedules commensurate with risk.
- Replicate only to Regions with real workload/DR requirements.
- Choose KMS keys based on governance needs rather than creating a CMK for every secret by default.
- Monitor API call volume and secret count.
- Use a recovery window when deleting to prevent outages from accidental deletion.

Regarding version quotas, AWS recommends avoiding calling `PutSecretValue` or `UpdateSecret` continuously more often than once every 10 minutes. Secrets Manager keeps the 100 most recent versions and does not delete versions newer than 24 hours. This is why secrets should not store continuously changing state.

Check AWS Secrets Manager pricing per Region to calculate actual cost; never hardcode static pricing figures in long-lived operational docs.

## 24. Comparing Secrets Manager with Parameter Store

| Criterion | Secrets Manager | Parameter Store |
|---|---|---|
| Primary goal | Secret lifecycle and credential management | Configuration and parameter hierarchy |
| Built-in rotation | Yes, including Lambda/managed rotation by type | No equivalent secret rotation workflow |
| Versions/staging labels | Yes | Has parameter versions, but different semantics |
| Caching client | Java/Python/.NET/Go/Rust components | AWS Parameters and Secrets Lambda Extension/Powertools integration |
| Cross-Region replication | Secret replication | Sharing/replication capabilities depending on tier and config |
| Pricing | Per secret/API/replication pricing | Standard/Advanced parameter pricing |
| Best fit | Database passwords, API keys, tokens | App config, feature values, `SecureString` |

Choose the service based on data lifecycle and usage pattern. Do not move every configuration into Secrets Manager just because data can be encrypted; that increases cost and operational complexity.

## 25. Common Troubleshooting

### 25.1. AccessDenied on GetSecretValue

Check whether the application role has `secretsmanager:GetSecretValue` on the right ARN, whether the secret resource policy has an explicit deny, whether an SCP/RCP or permissions boundary blocks it, whether the secret uses a customer managed KMS key, whether the KMS key policy allows the principal to decrypt, and whether the Region/secret ARN are correct.

Never resolve by granting `secretsmanager:*` on `*`.

### 25.2. KMS DecryptionFailure

Check whether the KMS key is enabled, key policy, IAM permissions, grants, encryption context, and `ViaService` conditions. If the key was disabled/deleted, versions encrypted with that key cannot be decrypted.

### 25.3. Rotation Timeout

Check whether Lambda has network connectivity to the database, whether Lambda can reach the Secrets Manager endpoint, whether timeout/concurrency are sufficient, whether security groups/NACLs allow the database port, whether CloudWatch Logs indicate a failure in `createSecret`/`setSecret`/`testSecret`/`finishSecret`, and whether `AWSPENDING` was left behind from a prior rotation.

### 25.4. Rotation Succeeds but Application Login Fails

The application may be using a stale cache or a connection pool holding old connections. Check TTL, secret stage, pool refresh logic, and propagation time. Ensure the application does not hardcode `VersionId`.

### 25.5. Lambda Cannot Call Secrets Manager in a VPC

If Lambda is in a private subnet without Internet egress, create a Secrets Manager interface endpoint or configure appropriate NAT/egress. Check private DNS and endpoint security group inbound TCP 443.

### 25.6. Secret Replica Not InSync

Check enabled Regions, KMS key permissions in primary/replica, name collisions, replication status messages, and CloudTrail. Replication is asynchronous, so allow synchronization time; do not assume instantaneous updates.

### 25.7. Too Many Versions

Check whether automation is calling `PutSecretValue` too frequently. Use idempotency tokens for retries and write new versions only when the value actually changes.

### 25.8. Secret Scheduled for Deletion

Applications cannot read a secret pending deletion. If deleted by mistake and still within the recovery window, call `RestoreSecret`; then verify version stages and application access.

## 26. Runbook: Moving a Database Password into Secrets Manager

1. Create a JSON secret containing `host`, `port`, `dbname`, `username`, and `password`.
2. Select the appropriate KMS key.
3. Attach `owner`/`environment`/`data classification` tags.
4. Create an IAM role for the application with only `GetSecretValue` on the secret ARN.
5. Configure Spring Boot to use SDK v2 and the exact Region.
6. Use the Java cache with a TTL aligned to the rotation policy.
7. Parse JSON and validate the schema.
8. Build the datasource/connection pool using the retrieved credentials.
9. Test read-only connectivity to the database.
10. Enable rotation if supported by the database/strategy.
11. Verify Lambda/managed rotation networking and IAM.
12. Test rotation in staging.
13. Verify the application refreshes its pool and continues serving requests.
14. Enable CloudTrail monitoring and safe session/application logging.
15. Remove old credentials from source code, CI variables, images, and config files after confirming no consumers remain.

Do not remove old credentials from the database or legacy secret store until the new rollout is verified. Roll out in batches with a rollback plan.

## 27. Practical Scenarios

### Scenario A — Password Hardcoded in application.properties

A Spring Boot application has `spring.datasource.password` hardcoded in Git.

**Handling:** Move the value into Secrets Manager, grant the task/instance role read-only access to the secret, fetch at runtime via SDK, and remove the credential from the repository following your exposed-secret incident procedure. If the credential was ever committed, rotate it; rewriting Git history does not make the old credential safe again.

### Scenario B — Rotation Completed but Application Still Uses Old Password

Secrets Manager moved `AWSCURRENT`, yet HikariCP still holds the old connection pool.

**Handling:** Lower TTL appropriately, refresh the secret and create a new pool, health-check the new pool, and drain the old pool. Avoid simply restarting the entire fleet when controlled rollout is possible.

### Scenario C — Application Throttled When Reading Secrets

Every HTTP request calls `GetSecretValue`.

**Handling:** Reuse the SDK client, add in-process caching, pick an appropriate TTL, use jitter, and monitor API call volume.

### Scenario D — AccessDenied Even Though IAM Role Has GetSecretValue

The secret uses a customer managed KMS key, but the key policy does not allow decrypt.

**Handling:** Inspect both identity policy and KMS key policy; grant minimal `kms:Decrypt` with appropriate `ViaService`/encryption context conditions.

### Scenario E — Rotation Lambda Times Out

The database is in a private subnet; Lambda lacks a route to the DB or Secrets Manager.

**Handling:** Fix security groups, routes, and the Secrets Manager VPC endpoint/NAT. Check both connections, not just the Lambda execution role.

### Scenario F — Cross-Account Role Cannot Read Secret

Account B has an identity policy, but Account A's resource policy does not allow that role; the secret also uses an AWS managed key.

**Handling:** Add a principal-scoped resource policy, switch to a customer managed KMS key, and configure key policy/identity permissions.

### Scenario G — Replica Region Has Not Received New Credential

The primary rotated, but the replica still holds the old version.

**Handling:** Check replication status; allow for eventual consistency or resolve `Failed` status/KMS permissions. Applications should use local replicas and have a strategy for handling credential versions during propagation.

### Scenario H — Secret Scheduled for Deletion

An automation script mistakenly deletes a production secret with a 7-day recovery window.

**Handling:** Restore the secret before applications need access, verify IAM/versions/rotation, and investigate CloudTrail events. Never use force-delete in routine production cleanup.

### Scenario I — CloudWatch Logs Contain Passwords

A rotation Lambda logs the entire secret JSON for debugging.

**Handling:** Remove payload logging from the function, handle logs per your data incident policy, rotate the credential if exposure is possible, and add code review checks to block secret logging.

### Scenario J — Secret Version Quota Growing Rapidly

A CI pipeline calls `PutSecretValue` on every build even though the value has not changed.

**Handling:** Switch build pipelines to read secrets at runtime, write new versions only when credentials change, and avoid continuous updates more frequent than once every 10 minutes.

## 28. Scenario Exercises

### Exercise A — Service Selection

An application needs to store a database password and rotate it automatically every week.

**Answer:** Secrets Manager with appropriate rotation; Parameter Store lacks an equivalent secret rotation workflow.

### Exercise B — Minimal IAM Role

Spring Boot only needs to read one secret.

**Answer:** Grant `secretsmanager:GetSecretValue` on the secret ARN; add `kms:Decrypt` if a customer managed key requires it. Do not grant secret management permissions.

### Exercise C — KMS Key

A secret is used only within one account and needs no custom key policy.

**Answer:** `aws/secretsmanager` is usually appropriate; use a customer managed key when cross-account access or custom key policy control is required.

### Exercise D — Version Stage

Rotation is running and a new version has `AWSPENDING`.

**Answer:** Do not use pending in production before testing; applications continue using `AWSCURRENT` until `finishSecret` moves the label.

### Exercise E — Stale Cache

Java cache TTL is one hour, rotation runs every 15 minutes.

**Answer:** Reduce TTL or add a refresh mechanism matching rotation; evaluate API costs and connection pool refresh.

### Exercise F — Rotation Lambda

Rotation fails at `setSecret`.

**Answer:** Check permissions and network reachability to the database, validity of the current credential, resource matching, and rotation function logs.

### Exercise G — High Availability

Database password rotation causes brief disruption when a single user changes password.

**Answer:** Consider alternating users if supported by the database/service and an admin secret is available to clone users.

### Exercise H — Private Subnet

A private application without NAT needs to call Secrets Manager.

**Answer:** Create an interface VPC endpoint `com.amazonaws.<region>.secretsmanager`, enable private DNS, and allow inbound TCP 443 on the endpoint SG.

### Exercise I — Cross-Account Access

An Account B role reads an Account A secret.

**Answer:** Requires both identity policy and resource policy, plus a customer managed KMS key and cross-account key policy/permissions.

### Exercise J — Multi-Region DR

An application running in two Regions needs the same secret.

**Answer:** Replicate the primary secret to the second Region, use the local replica, monitor status, and account for eventual consistency.

### Exercise K — Deleting Secrets

A secret is no longer used and needs safe deletion.

**Answer:** Use a 7–30 day recovery window (default 30 days); restore if deleted by mistake. Force delete cannot be recovered.

### Exercise L — Version Quota

Automation creates a version every minute.

**Answer:** Stop continuous updates; write only when values change and use idempotency tokens. AWS recommends not sustaining `PutSecretValue`/`UpdateSecret` more often than once every 10 minutes.

## 29. Review Questions

1. How does a secret differ from ordinary configuration?
2. When should you use Secrets Manager instead of Parameter Store?
3. How do `SecretString` and `SecretBinary` differ?
4. Which secret metadata is not encrypted like the secret value?
5. How do `VersionId` and staging labels differ?
6. What does `AWSCURRENT` mean?
7. When is `AWSPREVIOUS` used?
8. In which step is `AWSPENDING` used?
9. Why should applications read `AWSCURRENT`?
10. How many recent versions does Secrets Manager retain?
11. Why should you not call `PutSecretValue` continuously?
12. Which IAM action is required at runtime to retrieve a secret?
13. When is `kms:Decrypt` also required?
14. How does envelope encryption work?
15. How does an AWS managed key differ from a customer managed key?
16. What does `kms:ViaService` restrict?
17. Which Java SDK v2 client is used to retrieve secrets?
18. Why should `SecretsManagerClient` be reused?
19. Roughly how often does the Java cache refresh by default?
20. How does cache TTL affect freshness and cost?
21. Why might the cache return an older secret?
22. What are the four steps of a rotation Lambda?
23. What must `setSecret` verify to prevent confused deputy issues?
24. How do single-user and alternating-users rotation differ?
25. Why must an application refresh its connection pool after rotation?
26. Which timezone do rotation schedules use?
27. What is the service name format for a Secrets Manager VPC endpoint?
28. Which policies are needed for cross-account access?
29. Why do cross-account secrets require a customer managed KMS key?
30. Is multi-Region replication instantaneous?
31. What does `InSync` indicate?
32. What activity does CloudTrail record?
33. Should CloudTrail contain secret values?
34. What is the default recovery window when deleting a secret?
35. Can `ForceDeleteWithoutRecovery` be restored?

**Quick Answers:** (1) secrets are authentication/sensitive data; (2) when secret lifecycle/rotation is needed; (3) text vs. binary; (4) name, description, tags, rotation settings, and key ARN; (5) ID identifies a version, label describes lifecycle role; (6) current active version; (7) last known previous version; (8) new version undergoing rotation; (9) automatically tracks the new version; (10) 100 most recent; (11) creates too many versions and hits quota; (12) `GetSecretValue`; (13) when using a customer managed key and required by policy; (14) KMS protects the data key, the data key encrypts the secret; (15) AWS-managed vs. customer-managed policy/key; (16) restricts KMS usage to calls via the Secrets Manager service; (17) `SecretsManagerClient`; (18) reduces overhead and reuses connections; (19) roughly one hour; (20) shorter TTL increases freshness and API calls; (21) refresh failed or TTL has not expired; (22) `createSecret`, `setSecret`, `testSecret`, `finishSecret`; (23) current/pending point to the same resource and right destination; (24) one user vs. two alternating users; (25) pools may keep old connections/credentials; (26) UTC; (27) `com.amazonaws.<region>.secretsmanager`; (28) identity policy, resource policy, and KMS key policy/permissions; (29) AWS managed keys do not support cross-account access; (30) no, eventual consistency; (31) replica is synchronized with primary; (32) API activity; (33) no; (34) 30 days; (35) no.

## 30. Production Checklist

- [ ] Secrets are named by service/environment/purpose without sensitive data.
- [ ] Secret values have a clear schema and are validated when read.
- [ ] No credentials stored in source code, AMIs, container images, or CI logs.
- [ ] Applications use IAM roles/temporary credentials.
- [ ] Runtime roles have only `GetSecretValue` on required secrets.
- [ ] KMS key policies and `kms:Decrypt` are properly scoped.
- [ ] Secrets read `AWSCURRENT`, without hardcoded `VersionId`s.
- [ ] `PutSecretValue` is not called repeatedly when values have not changed.
- [ ] Java SDK clients are reused across the application lifecycle.
- [ ] Java cache TTL aligns with rotation intervals and freshness requirements.
- [ ] Caches, heap dumps, and debug endpoints are protected.
- [ ] Database connection pools have a refresh procedure after rotation.
- [ ] Rotation Lambdas are idempotent and verify current/pending target the same resource.
- [ ] Rotation functions have network paths to both the database and Secrets Manager.
- [ ] Rotation schedules use UTC with defined owners/on-call.
- [ ] Single-user/alternating-users strategy is chosen based on availability needs.
- [ ] Secret values, passwords, and tokens are never logged.
- [ ] CloudTrail monitoring is configured for secret API activity.
- [ ] Resource policies use `BlockPublicPolicy` and are reviewed.
- [ ] Cross-account access has matching identity/resource/KMS policies.
- [ ] Cross-Region replicas have KMS keys and replication status monitoring.
- [ ] VPC endpoints, private DNS, and security groups are verified.
- [ ] Secret deletion uses a recovery window; force delete requires approval.
- [ ] Version count, API calls, rotation failures, and costs are monitored.
- [ ] Runbooks exist for `AccessDenied`, KMS failures, rotation timeouts, and stale caches.

## 31. Summary

AWS Secrets Manager enables centralized secret management, KMS encryption, version tracking, and rotation for applications:

- Secret values can be text/JSON or binary; metadata such as names, descriptions, and tags are not encrypted like secret values.
- Version labels `AWSCURRENT`, `AWSPREVIOUS`, and `AWSPENDING` drive lifecycle; applications should read the current stage.
- KMS uses envelope encryption; an AWS managed key suits most single-account cases, while a customer managed key is required for cross-account access or custom key policies.
- Runtime applications use IAM roles with `GetSecretValue`; avoid static access keys and secret administration permissions.
- AWS SDK for Java 2.x integrates via `SecretsManagerClient`; the Java caching client cuts latency/API calls, but TTL must align with rotation.
- Lambda rotation comprises `createSecret`, `setSecret`, `testSecret`, and `finishSecret`; custom functions must be idempotent and verify target resources.
- Single-user rotation is simple; alternating users can improve availability where supported.
- VPC interface endpoints enable private-subnet access to Secrets Manager over PrivateLink.
- Cross-account access requires identity policies, resource policies, and KMS authorization; multi-Region replication is asynchronous.
- CloudTrail supports auditing API activity, while application and rotation logs must never record secret values.
- Recovery windows allow restoring accidentally deleted secrets; force delete cannot be undone.
- Caching, IAM, KMS, networking, rotation, connection pools, and auditing must be designed together.

A secure secret is more than an encrypted value. Applications must fetch the right version using a minimal identity, cache within acceptable bounds, swap credentials without disrupting connections, and keep secrets out of logs and artifacts.

### Official AWS and Java Documentation

1. AWS Secrets Manager best practices: https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html
2. What's in a secret and secret versions: https://docs.aws.amazon.com/secretsmanager/latest/userguide/whats-in-a-secret.html
3. Get a secret using Java AWS SDK: https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets-java-sdk.html
4. Get a secret using Java with client-side caching: https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_cache-java.html
5. AWS Secrets Manager Java caching client: https://github.com/aws/aws-secretsmanager-caching-java
6. AWS SDK for Java 2.x Secrets Manager examples: https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_secrets-manager_code_examples.html
7. Secret encryption and decryption: https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html
8. Authentication and access control: https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access.html
9. Resource-based policies: https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_resource-policies.html
10. Lambda rotation functions: https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda-functions.html
11. Managed rotation: https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_managed.html
12. Rotation schedules: https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_schedule.html
13. Rotation strategy: alternating users: https://docs.aws.amazon.com/secretsmanager/latest/userguide/tutorials_rotation-alternating.html
14. Troubleshoot rotation: https://docs.aws.amazon.com/secretsmanager/latest/userguide/troubleshoot_rotation.html
15. Using a Secrets Manager VPC endpoint: https://docs.aws.amazon.com/secretsmanager/latest/userguide/vpc-endpoint-overview.html
16. Replicate secrets across Regions: https://docs.aws.amazon.com/secretsmanager/latest/userguide/replicate-secrets.html
17. Cross-account access: https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_examples_cross.html
18. Cross-account replication: https://docs.aws.amazon.com/secretsmanager/latest/userguide/cross-account-replicate-secrets.html
19. Monitor replication status: https://docs.aws.amazon.com/secretsmanager/latest/userguide/cross-account-replicate-status.html
20. Delete and restore a secret: https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html
21. Secrets Manager quotas: https://docs.aws.amazon.com/secretsmanager/latest/userguide/reference_limits.html
22. AWS Secrets Manager pricing: https://aws.amazon.com/secrets-manager/pricing/
