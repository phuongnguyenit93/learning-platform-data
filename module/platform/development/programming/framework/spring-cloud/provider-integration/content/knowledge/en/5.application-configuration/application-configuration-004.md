# Distinguishing Configuration Parameters, Secrets, and Resource Identifiers

When integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud**, an application typically needs at least three kinds of information: how the application should operate, the address or name of a cloud resource, and data enabling authentication. All three can appear as strings in YAML or environment variables, yet **their meaning, storage, access permissions, and lifecycle differ**.

For example, a cloud document-upload feature might use `operation-timeout: 8s`, a bucket name `documents-prod`, and a credential for writing files. The timeout is a **configuration parameter**; the bucket name is a **resource identifier**; and the credential is an **authentication secret** if it contains a token, password, or private key. Putting all three into the same Git file, or treating a bucket name like a password, makes the design difficult to manage and secure.

This lesson belongs to the **Application Configuration** section of the `SPRING_CLOUD_PROVIDER_INTEGRATION` module, focusing on how to classify information before connecting storage, messaging, and data across multiple cloud providers.

## 1. The Three Information Categories and Their Functions

| Category | Answers the Question | Examples | Typical Management Approach |
| --- | --- | --- | --- |
| **Configuration parameter** | **How should** the application operate? | Timeout, retry count, batch size, profile name, feature toggle mode | Environment-specific config files, environment variables, configuration management services |
| **Resource identifier** | **Which resource** must the application operate on? | S3 bucket, Azure Blob container, GCS bucket, SQS queue URL, Pub/Sub topic name, database host | Per-deployment configuration; restrict visibility when revealing infrastructure details |
| **Secret** | What **proves access rights or must stay confidential to prevent abuse**? | Password, API token, client secret, private key, SAS token, signed URL granting access | Secret manager, workload identity, secure storage; restrict logging and distribution |

A resource identifier **does not grant permissions by itself**. Knowing an S3 bucket name does not automatically grant write access to that bucket. Likewise, knowing an Azure Blob endpoint still requires authorization via Microsoft Entra ID, SAS, or another authentication mechanism.

Conversely, a secret can look like a resource address: a URL containing an access token, a connection string containing a shared key, or a presigned URL conferring time-bounded access. You must evaluate **content and capability** rather than relying solely on field names.

### Quick Classification Rule

```mermaid
flowchart TD
    A["Reviewing a configuration value"] --> B{"Can the value authenticate, sign requests, or grant access like a bearer token?"}
    B -->|Yes| S["SECRET: protect as a credential"]
    B -->|No| C{"Does the value select or point to a specific cloud resource?"}
    C -->|Yes| R["RESOURCE IDENTIFIER"]
    C -->|No| P["CONFIGURATION PARAMETER or metadata"]
    R --> D["Control topology disclosure if needed"]
    P --> V["Validate type and business constraints"]
    S --> K["Secret manager / workload identity / rotation policy"]
```

The diagram above is a practical rule of thumb, not a legal classification matrix. Some values are **not secrets yet remain sensitive**: cloud account IDs, internal hostnames, project names, production addresses, or architecture-revealing metadata. They do not need to be treated like passwords, but access to them should still be restricted according to organizational policy.

## 2. Classification Examples Across AWS, Azure, and Google Cloud

Providers use different resource naming and identity models. The following table helps separate these categories upfront when designing Spring Boot configuration files.

| Service | Configuration Parameter | Resource Identifier | Secret or Credential to Protect |
| --- | --- | --- | --- |
| **AWS S3** | Upload timeout, retry count, encryption strategy | Bucket name, object key, bucket ARN, AWS region | AWS secret access key, session token, unexpired presigned URL |
| **AWS SQS/SNS** | Batch size, visibility timeout, retry | Queue URL, queue ARN, topic ARN | Authentication token/key if the app uses static credentials |
| **Azure Blob Storage** | Block size, timeout, retry | Storage account name, container name, blob name, endpoint | Account key, SAS token, connection string containing a shared key |
| **Azure Service Bus** | Prefetch count, concurrency level | Namespace, queue, topic, subscription name | Shared access key, connection string containing a SAS key |
| **Google Cloud Storage** | Client timeout and retry configuration | Project ID, bucket name, object name | Private key in service account JSON, access token |
| **Google Cloud Pub/Sub** | Flow control, ack deadline, batch settings | Resource name `projects/{project}/topics/{topic}`, subscription ID | Service account private key or access token |
| **Managed database** | Pool size, timeout, migration mode | Host, port, database name, instance/cluster ID | Password, client certificate private key, DSN containing a password |

Cases requiring closer attention:

- **AWS access key ID** is an *identifier for an access key*, distinct from the **secret access key**. However, the pair together with a session token (if present) forms a credential; in operations, treat the whole set as sensitive authentication data and do not log it carelessly.
- **Azure tenant ID** and **client ID** are generally identifiers; the **client secret** is the secret. `subscriptionId` and resource group identify resource scope, not passwords.
- **Google Cloud service account email** is a principal identifier; the `private_key` field inside the JSON key file is the secret. `GOOGLE_CLOUD_PROJECT` is a project ID, not a credential.
- **Secret ARN, Key Vault secret URI, and Secret Manager resource name** are usually *references to a secret*, not **secret values**. Even so, references can reveal internal environments or resources and still require appropriate access control.
- **Presigned URLs / SAS URLs** allow whoever holds the URL to access the resource during its validity window. Classify the **entire URL as a secret**, even though its prefix looks like an ordinary URL.

### Example Document Upload Transaction

```mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Config as App config
    participant Identity as Workload identity / credential provider
    participant Storage as Cloud Storage
    App->>Config: Read timeout, provider, target
    Config-->>App: 8s, AWS, documents-prod
    App->>Identity: Request appropriately provisioned credential
    Identity-->>App: Credential handled securely
    App->>Storage: Upload object to documents-prod
    Storage-->>App: Result or IAM/network/resource error
```

Here, the **bucket name** is used to construct the request; the **credential** is used by the SDK to sign or authenticate the request; the **timeout** controls how long the client waits. Three values have three distinct responsibilities.

## 3. Resource Identifiers, Workload Identities, and Credentials Are Not the Same

The word *identity* appears frequently when working with the cloud. Distinguish three concepts:

1. **Resource identifier:** name, path, URI, or ID of the target object to act upon. For example, `documents-prod` is a bucket name; `projects/example-prod/topics/events` is a Pub/Sub resource name.
2. **Workload identity / principal:** the identity assigned to the running application. For example, AWS IAM Role, Azure Managed Identity, or GCP service account via Workload Identity.
3. **Credential:** proof of authentication accepted by the system, such as a time-limited token, secret key, client certificate private key, or access key.

An **IAM Role ARN**, **Managed Identity client ID**, or **service account email** can identify a principal, yet **knowing an identifier is not equivalent to possessing a credential**. Authentication relies on runtime mechanisms (AWS credential provider chain, Azure Identity, Google Application Default Credentials, etc.).

Cloud deployments generally prefer:

| Cloud | Recommended Identity for Applications | Example Permission Needed for Storage Writes |
| --- | --- | --- |
| AWS | IAM Role attached to the runtime environment (EC2/ECS/EKS or workload federation) | `s3:PutObject` on the exact bucket/prefix |
| Azure | Managed Identity or workload identity via Microsoft Entra ID | Appropriate data role, such as **Storage Blob Data Contributor** when writes are required |
| Google Cloud | Service account via Workload Identity or Application Default Credentials | `storage.objects.create` permission on the target bucket, via an appropriate role |

An application can use short-lived credentials automatically obtained by the SDK **without declaring access keys, passwords, or private keys in `application.yml`**. Permissions must be granted to the principal on the IAM/RBAC side; changing `app.storage.target` to another bucket name does not automatically grant access to the new bucket.

## 4. Designing an Application-Owned Configuration Namespace

An application integrating storage and messaging can use a namespace **defined by the application itself** as follows:

```yaml
# src/main/resources/application.yml
app:
  integration:
    storage:
      target: ${STORAGE_TARGET}
    messaging:
      destination: ${MESSAGING_DESTINATION}
    operation-timeout: 8s
    retry:
      max-attempts: 3
```

Here:

- `operation-timeout` and `retry.max-attempts` are **configuration parameters**.
- `storage.target` and `messaging.destination` are **resource identifiers**.
- No fields hold **access keys, tokens, or private keys**; the SDK is expected to use the identity mechanism configured for the runtime environment.
- `${STORAGE_TARGET}` is a **placeholder referencing an environment variable**. The placeholder itself in Git contains no secret; the runtime value of the variable must be classified separately according to its contents.

Providers can be selected via profile files:

**`application-aws.yml`**

```yaml
app:
  integration:
    provider: aws
```

**`application-azure.yml`**

```yaml
app:
  integration:
    provider: azure
```

**`application-gcp.yml`**

```yaml
app:
  integration:
    provider: gcp
```

When deploying, set `SPRING_PROFILES_ACTIVE` accordingly and supply the appropriate resource names. For example:

| Profile | `STORAGE_TARGET` | `MESSAGING_DESTINATION` | Adapter Interpretation |
| --- | --- | --- | --- |
| `aws` | `documents-prod-asia` | Production SQS queue URL | S3 bucket and SQS queue URL |
| `azure` | `uploads` | `documents-created` | Blob container and Service Bus queue/topic within a separately configured namespace |
| `gcp` | `documents-prod-asia` | `projects/example-prod/topics/documents-created` | GCS bucket and Pub/Sub topic resource name |

These values are **illustrative examples**, not pre-provisioned resource names. Do not assign identical technical semantics to every field: an SQS queue URL differs from a Service Bus entity name; each provider's adapter must convert/validate the identifier according to its SDK.

Note that `app.integration.*` is **not** an official auto-configuration namespace of Spring Cloud AWS, Azure, or GCP. When initializing clients, you must still supply the properties required by each starter, or use the appropriate SDK client configuration APIs. Actual namespaces vary by library generation, so check the documentation for the BOM/version in use.

## 5. Binding and Validation with `@ConfigurationProperties`

In Spring Boot 3.x and Java 17+, you can define a strongly typed contract instead of having adapters read raw strings from `Environment`:

```java
package example.cloud.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @NotNull Provider provider,
        @Valid @NotNull Storage storage,
        @Valid @NotNull Messaging messaging,
        @DefaultValue("8s") Duration operationTimeout,
        @Valid @DefaultValue Retry retry
) {
    public enum Provider { AWS, AZURE, GCP }

    public record Storage(@NotBlank String target) {}

    public record Messaging(@NotBlank String destination) {}

    public record Retry(
            @Min(1) @Max(10) @DefaultValue("3") int maxAttempts
    ) {}
}
```

Register the configuration using `@ConfigurationPropertiesScan` on the main class or `@EnableConfigurationProperties(IntegrationProperties.class)`. When using `jakarta.validation.*`, include the `spring-boot-starter-validation` dependency. With a Java record, Spring Boot 3 supports constructor binding for a single-constructor record.

Four important points:

1. **Classification reflected in names and types:** `operationTimeout` is a `Duration`, `maxAttempts` is a number, and `storage.target` and `messaging.destination` are identifiers with business meaning.
2. **Early validation:** `@NotBlank` rejects empty resource names, and `@Min`/`@Max` reject invalid retry counts. Adapters can add validation tailored to each cloud's naming rules.
3. **Do not share a single regex across all providers:** S3/GCS buckets and Azure containers have different naming rules; an SQS Queue URL has a different format from a Pub/Sub topic. Provider-specific semantic validation belongs in the adapter layer or conditional validators.
4. **Do not store secrets in broadly used configuration records:** Java records automatically generate `toString()`. If you place tokens, passwords, or private keys in a record and log `properties`, sensitive data can leak. If an integration must receive a secret via binding, put a dedicated protection and log-masking model in place.

Example of an AWS layer receiving application configuration and an `S3Client` configured with the appropriate credential mechanism:

```java
package example.cloud.storage;

import example.cloud.config.IntegrationProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
@ConditionalOnProperty(
        prefix = "app.integration",
        name = "provider",
        havingValue = "aws"
)
public class AwsDocumentStorage {
    private final S3Client s3Client;
    private final IntegrationProperties properties;

    public AwsDocumentStorage(S3Client s3Client,
                              IntegrationProperties properties) {
        this.s3Client = s3Client;
        this.properties = properties;
    }

    public void upload(String objectKey, byte[] payload) {
        var request = PutObjectRequest.builder()
                .bucket(properties.storage().target()) // Resource identifier
                .key(objectKey)
                .build();
        s3Client.putObject(request, RequestBody.fromBytes(payload));
    }
}
```

This example assumes the compatible AWS S3 integration dependency already provides an `S3Client` bean. The adapter **does not read secrets from `IntegrationProperties`**: the SDK/client is responsible for resolving credentials via its configured mechanism. Likewise, `operationTimeout` and `retry.maxAttempts` **do not automatically control the AWS SDK**; to apply them, configure timeouts/retries on the client or API call layer while avoiding layered retries.

## 6. Placing Each Category in the Right Configuration Source

| Data Type | Suitable Source | Examples | What to Avoid |
| --- | --- | --- | --- |
| Shared, non-sensitive parameters | `application.yml` in the repository | Default timeouts, non-sensitive feature flags | Hardcoding production values in Java code |
| Environment-varying parameters | Profiles, external Config Data, Config Server/App Configuration | Per-environment retries, regional endpoints | Mistaking dev defaults for production settings |
| Per-deployment resource identifiers | Environment variables, files outside JAR, config services | S3 bucket name, Azure Service Bus namespace, GCP project ID | Mixing staging and production resources |
| Secret references | Runtime configuration with restricted read access | Secret ARN, Key Vault URI, Secret Manager resource name | Confusing a reference path with the secret content |
| Secret values | Secret manager or protected credential provider | Database password, API token, client private key | Committing plaintext to Git, images, logs, or build artifacts |
| Application identity | Role/identity attached by deployment infrastructure | AWS IAM Role, Azure Managed Identity, GCP Workload Identity | Creating static keys solely for SDK login when runtime identity exists |

Common solutions:

- **AWS:** IAM Roles for workloads; Secrets Manager or Systems Manager Parameter Store for secrets/parameters as appropriate.
- **Azure:** Managed Identity; Azure Key Vault for secrets, Azure App Configuration for key/value settings.
- **Google Cloud:** Workload Identity or Application Default Credentials; Secret Manager for secrets, runtime-appropriate config sources for ordinary parameters.

Depending on the version, Spring Cloud starters can load data from remote stores into a Spring `PropertySource`, support `spring.config.import`, or only offer an SDK for runtime queries. Do not guess import syntax: verify what your exact starter/version supports.

### Secret References Differ from Secret Values

Example configuration holding only a reference name:

```yaml
app:
  integration:
    third-party-api:
      credential-secret-ref: ${API_CREDENTIAL_SECRET_REF}
```

`credential-secret-ref` can be the name/URI of a secret entry in a secret store. This is an **identifier of a secret resource**; it is not the actual token. Integration code or a dedicated library uses that reference along with the workload identity to fetch the value at runtime.

```mermaid
flowchart LR
    A["Config: secret name/URI"] --> C["Secret client"]
    B["Workload identity"] --> C
    C --> D["Secret manager"]
    D --> E["Secret value returned over a secured channel"]
    E --> F["SDK / partner requiring authentication"]
```

If the cloud library already supplies credentials to the SDK via a role/managed identity, **do not create a secret just to store a key that the SDK can obtain securely and automatically**.

### When Passwords Must Still Be Passed via Configuration

Some systems do not yet support identity-based authentication, such as databases or third-party APIs that accept only passwords. In such cases, design a clear secret delivery path. Example placeholders:

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

The file above contains no real password, yet **the runtime value of `DB_PASSWORD` is still a secret**. Environment variables can be visible through container inspection tools, crash dumps, or deployment manifests. When possible, prefer secret stores, permission-restricted file mounts, and identity mechanisms to reduce leakage risk; avoid passing real passwords via command-line arguments since they can appear in process lists or shell history.

## 7. Cases Commonly Misclassified

### 7.1. A "Connection String" Can Be a Secret

Two strings that look similar:

```text
# Only the endpoint and database name
jdbc:postgresql://db.internal.example:5432/inventory

# Password embedded in URL: must protect the entire string
postgresql://inventory_user:super-secret@example.internal:5432/inventory
```

The second line is only an **illustration of a sensitive structure**, not a real credential. Proper classification depends on **string contents**, not whether a field is named `connection-string` or `url`. An Azure Storage connection string containing `AccountKey=...` or a Service Bus connection string containing `SharedAccessKey=...` is a credential and must be handled as a secret.

### 7.2. URIs That Are Both an Address and an Access Grant

- A public URL without tokens is typically an identifier/endpoint.
- A URL with query parameters like `sig`, `token`, `X-Amz-Signature`, or other signed access parameters must be treated as a **secret during its validity period**, because anyone holding the URL can exercise the granted permissions.
- Never write full presigned URLs into access logs, error messages, tracing spans, dashboards, or customer support emails.

### 7.3. Encrypted Secrets Still Require Protection

Encrypted ciphertext is **not automatically safe to make public**. Consider decryption capability, key location, reader scope, and organizational policy. Even when storing ciphertext in Git, the application still needs a secure decryption key delivery mechanism; never place ciphertext and its decryption key side by side.

A **password hash** is likewise not an innocuous parameter: it can be exploited if the algorithm or storage policy is weak. Classify based on risk, not merely on whether a value "looks like a password."

### 7.4. Resource Names Are Not Access Permissions

Setting `STORAGE_TARGET=prod-financial-documents` merely points the adapter at that bucket/container. If the application's principal lacks write permissions, the API returns an authorization error. Conversely, an application with overly broad permissions could accidentally write to the wrong resource if misconfigured.

Therefore, you need **both identifier validation and IAM/RBAC scoping**: names/resources must match the intended environment, and workload identities must be permitted to act only within the required scope.

## 8. Lifecycle and Ownership for Each Category

| Activity | Configuration Parameter | Resource Identifier | Secret |
| --- | --- | --- | --- |
| Creation | Developers/ops define values and defaults | IaC/infra provisions resource and outputs name/ID | Identity or secret manager issues credential |
| Storage | Git, config repo, external config | Deployment config, IaC outputs | Secret manager, secure mount, credential provider |
| Validation | Type conversion, range, business rules | Resource name/URI format, environment, existence | Read permission, validity, expiration, scope |
| Change | Config rollout/refresh if supported | Update deployment and access permissions | Rotation, revocation, re-issuance, and client refresh |
| Logging | Log only non-sensitive values when needed | Redacted/shortened IDs may be logged per policy | Never log plaintext, tokens, or private keys |
| Common incident | Timeout too short | Wrong bucket/topic/project/namespace | Expired token, wrong credential, revoked access |

A change to a **resource identifier** can entail a change in **permissions**. For instance, switching a destination to another SQS queue may require `sqs:SendMessage` on the new queue ARN; changing a Pub/Sub topic may require `roles/pubsub.publisher` on the new topic. These are two separate operational changes even when occurring in the same deployment.

A change to a **secret** may require reinitializing connection pools, HTTP clients, or SDK clients holding cached credentials. Updating Secret Manager does not guarantee every Spring Boot bean refreshes instantaneously. Choose refresh, restart, or rollout strategies according to library capabilities and service requirements.

## 9. Logging, Actuator, and Error Handling Without Leaking Secrets

In Spring Boot, configuration can be exposed unintentionally through:

- Logging the entire `Environment`, `@ConfigurationProperties` beans, or objects with auto-generated `toString()`.
- Actuator endpoints such as `/actuator/env` and `/actuator/configprops` when access control and value masking are not strictly configured.
- Exceptions containing full connection strings, presigned URLs, or request headers.
- Metric tags, trace attributes, message payloads, health check responses, or crash dumps.
- CI/CD logs, build artifacts, container metadata, and cloud deployment configurations.

Safe practices:

1. **Never log secrets or values that can act as credentials.** For authentication errors, log the error code, provider type, operation, and correlation ID instead of tokens.
2. **Separate metadata from secrets in error messages.** You can log `provider=aws` and `operation=PutObject`; log bucket names/ARNs only if observability policies permit.
3. **Mask values at both the application and infrastructure layers.** Do not rely on a single regex masking `password`, because secrets can be named `token`, `authorization`, `sas`, `sig`, or appear inside URLs.
4. **Secure Actuator** using authentication, authorization, internal networking, and proper display settings. Never enable unmasked full-value output in production.
5. **Restrict workload secret-read permissions** and secret visibility in CI/CD. An application's permission to read a secret does not mean every engineer or pipeline should be able to view its contents.

A helpful error message that does not leak credentials:

```text
Storage upload failed:
  provider=aws
  operation=PutObject
  resourceAlias=document-archive
  reason=AccessDenied
  requestId=<provider-request-id>
```

Here `resourceAlias` is an operational label permitted in logs, not necessarily the real bucket name. During investigation, correlate the request ID with cloud audit logs to identify the principal and target resource scope.

## 10. Testing Configuration, Identifiers, and Secrets by Responsibility

The three data categories lead to three different kinds of tests:

| Goal | How to Test | What Cannot Be Concluded from This Alone |
| --- | --- | --- |
| Parameters have valid types and ranges | Binding + Bean Validation unit tests with `ApplicationContextRunner` | That the cloud SDK actually uses those timeout/retry settings |
| Identifiers have valid syntax | Adapter validation, bucket/container/topic name mapping tests | That the resource exists or permissions are granted |
| Resources match the environment | Integration tests in a test environment, comparing IaC-provisioned IDs | That credentials will remain valid after rotation |
| Appropriate identity and permissions | Integration tests with a least-privilege test workload identity | That secrets do not leak through logs or telemetry |
| Secrets are retrieved safely | Test secret store/mount with dummy data, test refresh/rotation | That production secrets can be used in unit tests |
| No data leakage | Test log redaction and inspect operational endpoints in a controlled environment | That all external monitoring systems are safe |

### Example Test Scenarios

**Scenario A — parameter error:** `app.integration.retry.max-attempts=0`. Spring Boot should catch the Bean Validation failure at startup without needing cloud connectivity.

**Scenario B — identifier error:** `STORAGE_TARGET` is a bucket name containing characters invalid for the chosen provider. The adapter should reject it before issuing a request if possible; the SDK/provider may also return a validation error.

**Scenario C — permission error:** the bucket/container exists, but the workload identity lacks write permission. Even though property binding succeeds, the upload operation must fail with a clear authorization error.

**Scenario D — inaccessible secret:** the secret reference is syntactically valid, but the runtime lacks read permission. The application must not fall back to fake placeholders or default credentials to continue calling secured services.

**Scenario E — rotation:** update a credential in the secret store. Verify when the application reads the new version, whether the SDK/client caches it, and whether a restart/rollout is required.

### Classification Exercise

Classify the following values, then compare with the answers:

| Value | Primary Category | Explanation |
| --- | --- | --- |
| `app.storage.operation-timeout=5s` | Parameter | Controls the application's wait behavior |
| `AWS_REGION=ap-southeast-1` | Parameter / deployment scope | Selects the execution or connection region; does not prove permissions |
| `STORAGE_TARGET=documents-prod` | Resource identifier | Bucket/container name |
| `AZURE_STORAGE_ACCOUNT=storageprod` | Resource identifier | Storage account name |
| `GOOGLE_CLOUD_PROJECT=example-prod` | Resource identifier / scope | Project ID |
| `projects/example-prod/topics/orders` | Resource identifier | Pub/Sub topic name |
| `AZURE_CLIENT_ID` (UUID value) | Principal identifier | Not a client secret |
| `AZURE_CLIENT_SECRET` | Secret | Used to prove the client's identity |
| Service account JSON containing `private_key` | Secret | Contains a private key |
| URI of an item in Key Vault | Resource reference | Only the secret's address, unless the URI includes a privileged token |
| Unexpired S3 presigned URL | Secret | Anyone holding the URL can use the signed permissions |

These examples underscore that a value may technically be a **non-secret parameter or metadata**, yet still carry sensitivity depending on the organization. Whenever unsure whether a URL/connection string contains a credential, **treat it as a secret until you have inspected its components**.

## 11. Three-Cloud Integration Practice Exercise

A development team deploys the same "store invoice and emit event" feature on AWS, Azure, and GCP. Build a configuration contract for the Spring Boot application following these steps:

1. **Identify data categories.** Put `provider`, `operation-timeout`, and `retry.max-attempts` in parameters; put `storage.target` and `messaging.destination` in resource identifiers; exclude real credentials from both.
2. **Separate files and sources by environment.** Use `application.yml` for non-sensitive defaults; profiles to select the provider; environment variables or external configs to receive per-deployment bucket/container/topic names.
3. **Configure workload identity.** Use an IAM Role on AWS, Managed Identity/Workload Identity on Azure, and Workload Identity or appropriate ADC on GCP. Confirm the runtime requires no hardcoded long-lived credentials.
4. **Create dedicated adapters.** The S3 adapter reads the bucket name; the Azure Blob adapter reads the container name; the GCS adapter reads the bucket name. Messaging adapters map `destination` to the SDK-appropriate queue/topic identifier.
5. **Test misconfigurations.** Test missing `STORAGE_TARGET`, invalid resource names, non-existent resources, missing write permissions, and an unreachable secret store. Record whether each error is caught during binding or when calling the provider.
6. **Audit sensitive data.** Inspect logs, error messages, Actuator, CI/CD, and tracing; confirm no tokens, passwords, private keys, or signed URLs appear.
7. **Run operational tests.** Switch the test environment's bucket/topic to verify both adapter and IAM/RBAC updates; rotate a third-party service credential to test refresh/restart behavior.

**Expected outcome:** for any configuration key, learners can explain **whether it is an operational policy, resource name, identity, or secret**, who supplies the value, where it should be stored, and what kind of test is required. When switching cloud providers, business logic can keep the shared configuration contract while adapters, resource identifiers, and authentication mechanisms adapt to the platform.

## 12. Key Takeaways

- **Configuration parameters** tune behavior; **resource identifiers** point to where the application operates; **secrets** carry proof of authorization or access. Similar variable names do not guarantee the same classification.
- **Identifiers are not credentials.** Bucket names, project IDs, tenant IDs, and service account emails are typically identifiers; private keys, client secrets, tokens, and privileged presigned URLs must be protected.
- Leverage **workload identities and least-privilege permissions** instead of static keys whenever possible. Resource existence and valid syntax do not prove the workload has access permissions.
- Use `@ConfigurationProperties` and validation to verify parameters and identifiers; let secret managers or credential providers handle secrets, keeping sensitive values out of Git and logs.
- Whenever changing environments, resources, or secrets, verify **effective configuration, IAM/RBAC permissions, refresh/rotation behavior, and sensitive-data traces** in operational systems.
