# Reading Secrets and Spring Configuration from Secret Manager

A Spring Boot application often needs to connect to databases, call third-party APIs, or authenticate with other systems. Service addresses, ports, and timeouts can live in ordinary configuration; however, passwords, API tokens, OAuth client secrets, and private keys must be protected. If a secret value appears in `application.yml`, a `Dockerfile`, Java source code, or Git history, anyone with access to the repository or artifacts can extract it.

Google Cloud **Secret Manager** provides versioned secret storage with IAM-controlled access. **Spring Framework on Google Cloud** (formerly commonly called Spring Cloud GCP) provides integrations so Spring Boot applications can reference secrets like ordinary configuration properties. Alternatively, applications can use the Java client library directly or platform-level secret integrations. This lesson explains how to choose an approach, configure the right library version, and rotate secrets without putting payloads in source code.

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module, in the **Java and Spring on GCP** chapter. The module explores Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases; through deployment scenarios, learners select services, secure resources, automate releases, and monitor reliability and cost. Here, we apply those principles to Spring Boot and Secret Manager.

## Learning Objectives

After this lesson, you will be able to:

- Classify ordinary configuration versus sensitive secret data in Spring applications.
- Explain the relationship among Secret Manager, IAM, Application Default Credentials (ADC), and the Spring `Environment`.
- Create secrets, add versions, and grant secret-level read access to a runtime service account.
- Configure the Spring Cloud GCP Secret Manager starter and read secrets using version-appropriate syntax.
- Bind secrets to Spring datasources, `@Value`, and `@ConfigurationProperties`.
- Distinguish startup secret loading, active reads via the Java SDK, and Cloud Run/GKE secret integrations.
- Handle errors, secret rotation, testing, and preventing secret leaks via logs or Actuator.

## 1. Distinguishing Configuration from Secrets

Spring Boot reads configuration from `application.properties`, `application.yml`, environment variables, command-line arguments, and other sources. These sources are convenient, yet not all of them offer protections suited to credentials.

| Property | Example | Appropriate place to manage |
|---|---|---|
| Application name | `orders-api` | Spring config |
| Region or project ID | `asia-southeast1`, `example-project` | Spring config or environment variables |
| Timeout, concurrency | 3 seconds, 50 requests | Spring config |
| JDBC URL without password | `jdbc:postgresql://db.internal:5432/orders` | Spring config |
| Database username | `orders_app` | Spring config or secret per policy |
| Database password | Value used to log in | Secret Manager |
| API token or client secret | Partner authentication credential | Secret Manager |
| Private key | Signing or authentication key | Appropriate key management or secret service |
| Long-lived encryption key for cryptographic operations | Data protection key | Cloud KMS |

Secret Manager fits application data that **must be retrieved in plaintext** to connect or call services. Cloud KMS primarily manages cryptographic keys and performs cryptographic operations; do not treat Cloud KMS as a password vault replacing Secret Manager.

### Insecure Configuration

The example below illustrates a common mistake:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: super-secret-value-in-git
payments:
  api-token: static-token-in-source-control
~~~

Renaming the file to `application-prod.yml` or adding it to `.gitignore` after committing does not remove copies already stored in Git history. Base64 encoding does not protect a secret either. If a real credential has been committed, rotate or revoke it immediately at the target system.

## 2. How Spring Boot Reads Secrets on Google Cloud

When using the Spring Cloud GCP Secret Manager starter, Spring initializes a property source, resolves secret references, and uses ADC to call the Secret Manager API. Cloud IAM decides whether the runtime identity has permission to read the secret version.

~~~mermaid
flowchart LR
    A["Spring Boot config<br/>application.yml"]
    B["Spring Cloud GCP<br/>Secret Manager integration"]
    C["Application Default<br/>Credentials"]
    D["IAM: secretAccessor<br/>on target secret"]
    E["Secret Manager API"]
    F["Secret version"]
    G["Spring Environment<br/>DataSource / Bean"]
    A --> B
    B --> C
    C --> D
    B --> E
    D --> E
    E --> F
    F --> G
~~~

Components carry distinct responsibilities:

1. **Secret name and version** are configuration references. They are not the secret payload itself.
2. **Workload identity** is the service account or federated identity supplied to the running application.
3. **IAM** authorizes payload reads. Grant permissions on the exact secret rather than broadening casually across the whole project.
4. **Secret Manager** stores payloads in versions that can be enabled, disabled, or destroyed.
5. **Spring Environment** supplies resolved values to properties such as `spring.datasource.password` or `payments.api-token`.

The application needs read access only. Creating versions, altering policies, or deleting secrets are separate administrative operations outside the runtime responsibility of most applications.

## 3. Preparing the Project and Secret Manager

Examples use a Spring Boot application named `orders-api` connecting to PostgreSQL. Replace the project ID, addresses, and service account with values provisioned in your test environment.

### Step 1: Select the Project and Enable the API

~~~bash
export PROJECT_ID="example-project"
export SECRET_ID="orders-db-password"
export RUNTIME_SA="orders-runtime@example-project.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable secretmanager.googleapis.com \
  --project="$PROJECT_ID"
~~~

Permissions to enable APIs, create secrets, or modify IAM typically belong to project administrators; do not grant those administrative permissions to an application that only needs to read secrets.

### Step 2: Create the Secret

~~~bash
gcloud secrets create "$SECRET_ID" \
  --replication-policy=automatic \
  --project="$PROJECT_ID"
~~~

Automatic replication is a common choice. If your organization enforces data residency constraints, design replication/locations according to policy and Secret Manager support before provisioning resources. The following examples use global secrets to focus on Spring integration.

### Step 3: Add a Version

~~~bash
gcloud secrets versions add "$SECRET_ID" \
  --data-file="/secure/path/orders-db-password.txt" \
  --project="$PROJECT_ID"
~~~

The input file holds a test password generated via your team's security workflow. Avoid passing secrets directly on the command line, saving them inside the repository directory, or printing them to logs. Secure file permissions and delete temporary copies per policy once done.

Secret Manager does not automatically create or change passwords on the database itself. The password in the secret must match the actual credential configured for the database user. During rotation, coordinate both sides.

### Step 4: Grant Least-Privilege Read Access

~~~bash
gcloud secrets add-iam-policy-binding "$SECRET_ID" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor"
~~~

The `roles/secretmanager.secretAccessor` role allows reading secret payloads. Granting it at the secret level narrows scope compared to project-level bindings. If an app uses three secrets, grant access on those exact three secrets rather than letting the app read every secret in the project.

On Cloud Run, attach this service account as the service's runtime service account. On GKE, use Workload Identity Federation for GKE and bind permissions to the matching principal. On Compute Engine, attach the workload service account to the VM and verify related access controls.

## 4. Spring Cloud GCP Version Determines Syntax

**Important point:** Secret Manager property source syntax changed across major lines of Spring Framework on Google Cloud. Older online guides commonly use `sm://`, whereas documentation for newer lines recommends `sm@`.

| Integration line | Enabling Config Data | Secret reference | Notes |
|---|---|---|---|
| Spring Cloud GCP 4.x or 5.x | `spring.config.import=sm://` | `${sm://orders-db-password}` | Syntax documented for these lines |
| Spring Framework on Google Cloud 6.x onward | `spring.config.import=sm@` | `${sm@orders-db-password}` | New syntax introduced in 6.0.0; recommended for 7.x |
| Spring Cloud Config Server with Secret Manager backend | Separate config mechanism | Per Config Server backend | Not identical to direct Secret Manager starter integration |

The main examples below use **`sm@`** per Spring Framework on Google Cloud 7.x documentation. If your project uses an older line, adjust imports and placeholders to match your exact version's docs. Never mix syntaxes from both lines in the same configuration. Before upgrading Spring Boot or Spring Cloud, check the compatibility matrix and release notes—especially across major versions.

### Ways to Reference Secrets in the New Syntax

| Syntax | Meaning |
|---|---|
| `sm@orders-db-password` | Secret in the default project, latest version |
| `sm@orders-db-password/5` | Secret in the default project, version 5 |
| `sm@example-project/orders-db-password/5` | Specifies project, secret, and version |
| `sm@projects/example-project/secrets/orders-db-password/versions/5` | Full resource name |
| `sm@projects/example-project/secrets/orders-db-password` | Full resource name without version; uses latest version |

Newer Spring Framework on Google Cloud releases also support **regional secrets** via paths containing `locations/LOCATION_ID`. On older library lines, verify regional secret support before adopting it. When strict version pinning is required, specify a concrete version instead of `latest`; `latest` fits rotation workflows paired with an intentional refresh strategy.

## 5. Adding the Starter to a Maven Application

Spring Boot projects must pick a Spring Framework on Google Cloud version compatible with their Spring Boot version. With Maven, import the Spring Framework on Google Cloud BOM in `dependencyManagement` and declare the starter:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-secretmanager</artifactId>
</dependency>
~~~

This dependency snippet assumes the project has already imported the corresponding BOM, so no version is repeated on individual starters. If no BOM is present yet, add `spring-cloud-gcp-dependencies` at your chosen version and check the Spring Boot/Spring Cloud compatibility matrix. Avoid copying an arbitrary version from an old tutorial onto a modern Spring Boot project.

If the app uses JDBC and PostgreSQL, you also need matching dependencies such as the Spring Boot JDBC starter and PostgreSQL JDBC driver. The Secret Manager starter provides only a configuration source; it does not create databases, provision network connectivity, or replace JDBC drivers.

## 6. Putting the Datasource Password in Spring Config

In `application.yml`, declare the secret reference instead of the password value:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: "sm@"
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
    password: "${sm@orders-db-password}"
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
~~~

In newer lines, importing `sm@` enables the Spring Boot Config Data API for Secret Manager. When Spring resolves `spring.datasource.password`, the starter calls Secret Manager to retrieve the payload of `orders-db-password` in the default project at the latest version. Spring Boot JDBC auto-configuration then uses that password to initialize the `DataSource`.

`DB_JDBC_URL` and `DB_USERNAME` come from the environment or another config source. If usernames are sensitive under organizational policy, they can also live in Secret Manager.

To reference a specific version:

~~~yaml
spring:
  config:
    import: "sm@"
  datasource:
    password: "${sm@orders-db-password/5}"
~~~

To access a secret in another project, use the full resource name:

~~~yaml
spring:
  config:
    import: "sm@"
  datasource:
    password: "${sm@projects/central-secrets/secrets/orders-db-password/versions/5}"
~~~

The runtime service account must still have permission to read the secret in the target project. Passing a project ID in the reference string does not grant access automatically.

### Equivalent application.properties

~~~properties
spring.application.name=orders-api
spring.config.import=sm@
spring.datasource.url=${DB_JDBC_URL}
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${sm@orders-db-password}
~~~

Never put secret payloads in YAML, properties files, or default placeholders like `secret-value`. For mandatory secrets, let the application fail fast when a secret is missing or denied rather than silently falling back to a hardcoded password.

## 7. Injecting Secrets via @Value and @ConfigurationProperties

Spring can read a secret directly with `@Value` or bind it to a clearly named configuration property.

### Using @Value for Single Properties

Example referencing a partner API token:

~~~yaml
spring:
  config:
    import: "sm@"
payments:
  endpoint: "https://payments.example.invalid/api"
  api-token: "${sm@payments-api-token}"
~~~

In Java:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class PaymentCredentialProvider {
    private final String apiToken;

    public PaymentCredentialProvider(
            @Value("${payments.api-token}") String apiToken) {
        this.apiToken = apiToken;
    }

    public String tokenForOutboundRequest() {
        return apiToken;
    }
}
~~~

This class merely illustrates injection. In production, consume the token inside the HTTP client when constructing the `Authorization` header, and never log the returned value or expose it in API responses. Never create a public endpoint that displays secrets.

You can reference the secret directly:

~~~java
@Value("${sm@payments-api-token}")
private String paymentApiToken;
~~~

However, mapping through a domain property like `payments.api-token` is usually easier to review, as most application code does not need to know which secret backend stores the value.

### Using @ConfigurationProperties for Structured Configuration

When a client needs multiple settings, `@ConfigurationProperties` is cleaner than scattered `@Value` fields.

~~~yaml
spring:
  config:
    import: "sm@"
payments:
  endpoint: "https://payments.example.invalid/api"
  timeout: 3s
  api-token: "${sm@payments-api-token}"
~~~

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payments")
public record PaymentSettings(
        URI endpoint,
        Duration timeout,
        String apiToken) {
}
~~~

Register the configuration properties bean:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(PaymentSettings.class)
public class PaymentSettingsConfiguration {
}
~~~

When Spring binds `payments.api-token`, the placeholder resolves from Secret Manager. The bean receives the token as a `String` just like any other Spring property.

**Caution:** Java records auto-generate a `toString()` containing all fields. Never log `PaymentSettings` directly, include the bean in error messages or responses, or allow Actuator to display sensitive values. To guard against accidental `toString()` calls, you can use a regular class with a custom `toString()` that prints only non-sensitive fields.

## 8. Profiles and Environment-Specific Configuration

Applications typically run in local, staging, and production environments. A clean design stores shared settings in `application.yml` and environment-specific Secret Manager references in matching profile files.

**application.yml** holds only shared configuration:

~~~yaml
spring:
  application:
    name: orders-api
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
~~~

**application-staging.yml:**

~~~yaml
spring:
  config:
    import: "sm@"
  datasource:
    password: "${sm@orders-db-password-staging}"
~~~

**application-prod.yml:**

~~~yaml
spring:
  config:
    import: "sm@"
  datasource:
    password: "${sm@projects/prod-secrets/secrets/orders-db-password/versions/7}"
~~~

**application-local.yml** can use a local environment variable for testing:

~~~yaml
spring:
  datasource:
    password: "${LOCAL_DB_PASSWORD}"
~~~

When the `prod` profile is active, `application-prod.yml` loads and Spring queries Secret Manager. When running unit tests under a `test` or `local` profile without `sm@` import, you can supply test credentials without calling Google Cloud APIs.

Do not let the `test` profile accidentally inherit `sm@` from shared config if offline testing is intended. Enable the Secret Manager source only in profiles and environments that genuinely need it; the same artifact can run across profiles without baking secrets inside.

### Default Project

The starter can resolve the project from shared configuration or ADC. To specify the project explicitly for Secret Manager, set:

~~~properties
spring.cloud.gcp.secretmanager.project-id=example-project
~~~

When accessing another project, full resource names make the target unmistakable. Verify the resolved project at startup so an application never runs cleanly while reading secrets from the wrong environment.

## 9. Authenticating with Application Default Credentials

**Application Default Credentials (ADC)** is the mechanism Google Cloud libraries use to discover credentials from the running environment. Applications need no custom credential-selection logic when moving from a laptop to Cloud Run or GKE.

Locally, create ADC for a developer account:

~~~bash
gcloud auth application-default login
gcloud auth application-default set-quota-project "$PROJECT_ID"
~~~

The second command sets the quota project for ADC if needed and permitted for the account. **`gcloud auth login`** authenticates the Google Cloud CLI; it does not provision ADC for Java client libraries. Always run the `application-default` command when testing directly from a workstation.

Run the application with the desired profile:

~~~bash
export DB_JDBC_URL="jdbc:postgresql://127.0.0.1:5432/orders"
export DB_USERNAME="orders_app"

./mvnw spring-boot:run \
  -Dspring-boot.run.profiles=staging
~~~

This requires the database or connection tunnel to be established, the ADC principal to hold read access on the staging secret, and the project configured properly. If database connectivity is missing, Spring may still read the secret while `DataSource` initialization or health checks fail on network errors; separate those two root causes when investigating.

Never download service account JSON keys onto a laptop just to test locally. JSON keys are long-lived credentials that can be copied or committed. For external automation outside Google Cloud, prefer Workload Identity Federation over static keys.

### Distinguishing Identities Across Environments

| Environment | Where ADC usually comes from | What to control |
|---|---|---|
| Developer machine | `gcloud auth application-default login` | User permissions on dev secrets |
| Cloud Run | Service's runtime service account | IAM on the exact secret |
| Compute Engine | Service account attached to the VM | IAM and related VM/Google API access settings |
| GKE | Workload Identity Federation for GKE | Kubernetes workload identity, IAM, namespace, and networking |
| External CI/CD | Workload Identity Federation | Trust between external identity provider and Google Cloud |

An application can run anywhere with the exact same Java code, yet the target project and secret references must be explicitly scoped per environment. Never assume a default identity automatically has permission to read all secrets.

## 10. Deploying Spring Boot on Cloud Run

Cloud Run supplies a runtime identity to the container and lets the application call the Secret Manager API. If the app already uses the starter with `sm@` import, it only needs an authorized service account, the right project, and network access to the API.

### Attaching a Runtime Service Account

Example updating the service's identity:

~~~bash
gcloud run services update orders-api \
  --region=asia-southeast1 \
  --project="$PROJECT_ID" \
  --service-account="$RUNTIME_SA"
~~~

This command updates the Cloud Run service configuration; it is illustrative of the workflow and unnecessary if the service already uses the intended identity. Deployers need permission to update the service and `actAs` permission on the specified service account. Once attached, the runtime identity needs only read access to the app's secrets.

### Two Ways to Supply Secrets to Spring on Cloud Run

**Option A — Spring starter reads directly from Secret Manager.** Keep configuration:

~~~yaml
spring:
  config:
    import: "sm@"
  datasource:
    password: "${sm@orders-db-password/7}"
~~~

Cloud Run only needs to supply the identity and non-sensitive config variables. The starter calls Secret Manager when resolving placeholders.

**Option B — Cloud Run injects secrets via environment variables.** Cloud Run integrates with Secret Manager and can map a secret version into an environment variable such as `SPRING_DATASOURCE_PASSWORD`:

~~~bash
gcloud run deploy orders-api \
  --image="asia-southeast1-docker.pkg.dev/example-project/app-images/orders-api:release-7" \
  --region=asia-southeast1 \
  --project="$PROJECT_ID" \
  --service-account="$RUNTIME_SA" \
  --set-secrets="SPRING_DATASOURCE_PASSWORD=orders-db-password:7"
~~~

Spring Boot reads `SPRING_DATASOURCE_PASSWORD` as `spring.datasource.password` via relaxed binding. With this option, the application does not strictly need the Secret Manager starter, as the platform injects the value into the process. Remove any `sm@` placeholder on the same property.

Both approaches require the runtime identity to have read permission on the secret. Option A standardizes access via Spring property sources and is portable across environments; Option B is simpler for apps running exclusively on Cloud Run. Choose based on architecture and operational fit, then stay consistent so configuration sources remain clear.

Cloud Run also supports supplying secrets via mounted volumes. File mounts and environment variables differ in update behavior. Secrets passed via environment variables are resolved at instance startup; running instances do not automatically pick up values just because a new secret version is created. Plan revision rollouts or restarts so every instance adopts the new credential after rotation.

### Post-Deploy Verification

After updating the service:

1. Confirm the new revision reaches `Ready`.
2. Verify the health endpoint and a database operation using a test account.
3. Monitor error rates, latency, instance restarts, and startup logs.
4. Confirm logs contain no passwords or tokens.
5. Confirm the runtime service account cannot read secrets outside its granted scope.

Never create debug endpoints that return `Environment`, `DataSource` configuration, or beans containing secrets. Any diagnostic check must avoid printing raw payloads.

## 11. Spring Boot on GKE and Workload Identity

On GKE, Pods run the Spring Boot application and typically use a Kubernetes ServiceAccount (KSA). If the application calls the Secret Manager API directly, Workload Identity Federation for GKE is the preferred way to give workloads a controlled Google Cloud identity without storing JSON key files.

Example Kubernetes ServiceAccount manifest:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: production
~~~

The Pod must reference the matching service account:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 2
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
          image: asia-southeast1-docker.pkg.dev/example-project/app-images/orders-api:release-7
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
~~~

This manifest illustrates attaching a KSA to a Pod, not the entire Workload Identity setup. Configure the workload identity pool/principal and IAM bindings according to your GKE Standard or Autopilot cluster mode, ensuring the principal representing the namespace and KSA holds `roles/secretmanager.secretAccessor` on required secrets. In some models, a KSA links to an IAM service account; follow the currently supported setup guide.

Once the workload has permissions and network reachability to the Secret Manager API, the starter uses ADC inside the Pod to read secrets. If your organization uses the Secret Manager add-on or CSI driver to mount secrets as files, the app can read from files/configtree instead. That is a different architecture from calling the API directly via the starter; verify permissions, version synchronization, and refresh schedules separately.

For GKE private clusters, beyond IAM, check egress paths or connectivity to Google APIs. A Pod with valid IAM that cannot reach the Secret Manager endpoint still fails to read secrets.

## 12. When to Read Secrets Using the Java SDK

The Spring starter fits secrets resolved as configuration during application startup. Sometimes an application needs to read a version actively at runtime—for instance, after a rotation event or inside a background job. In that case, use the Google Cloud Secret Manager Java client library.

Add the dependency through a version manager compatible with Google Cloud libraries:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-secretmanager</artifactId>
</dependency>
~~~

Register a Spring-managed client bean:

~~~java
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SecretManagerClientConfig {

    @Bean(destroyMethod = "close")
    SecretManagerServiceClient secretManagerClient()
            throws IOException {
        // Uses Application Default Credentials.
        return SecretManagerServiceClient.create();
    }
}
~~~

Create a service to read a specific version:

~~~java
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;
import org.springframework.stereotype.Service;

@Service
public class RuntimeSecretService {
    private final SecretManagerServiceClient client;

    public RuntimeSecretService(
            SecretManagerServiceClient client) {
        this.client = client;
    }

    public String read(
            String projectId,
            String secretId,
            String versionId) {
        SecretVersionName name = SecretVersionName.of(
                projectId, secretId, versionId);

        return client.accessSecretVersion(name)
                .getPayload()
                .getData()
                .toStringUtf8();
    }
}
~~~

This example only shows payload retrieval. Design the calling service never to log returned values, leak secrets in exception messages, or expose secrets in responses, and handle errors per business requirements. Note that a value returned as a `String` resides in JVM memory; immediate erasure of all copies from memory cannot be guaranteed.

Reuse the client and read only when necessary. Never call Secret Manager on every HTTP request or every database connection checkout. Over-frequent reads raise latency, increase API call counts, and can hit quotas; use caching or controlled refresh workflows if required by your architecture.

### Comparing Three Integration Approaches

| Approach | Best when | Limitations to watch |
|---|---|---|
| Spring Cloud GCP property source | Secrets act as startup config properties | Updating a secret does not auto-update running beans |
| Java Secret Manager SDK | Need active or event-driven version reads | Must manage client, caching, retries, and propagation to components |
| Runtime secret integration | Running on Cloud Run/GKE and preferring platform injection | Env/file behavior and refresh mechanics depend on the platform |

Not every application needs both the starter and the direct SDK. Pick the simplest option meeting version control, refresh, latency, and access control needs.

## 13. Rotating Secret Versions

Secret Manager tracks multiple versions of the same secret. However, changing a secret in Secret Manager **does not automatically change credentials in databases or third-party services**, nor does it guarantee already-constructed Spring beans pick up the new value.

### `latest` vs Explicit Versions

- **`latest`:** convenient when new instances should read the newest enabled version. Running instances caching values in beans or connection pools typically keep using what they read at startup.
- **Explicit version:** gives each release reproducible configuration. Teams can deliberately bump from version 7 to 8 and deploy a new revision so every instance runs the same version.

For a PostgreSQL password, changing the database password before instances switch to the new secret can cause older instances to fail when pools open new connections. If the database cannot accept two simultaneous credentials for one user, introduce a second credential/user during transition or schedule an appropriate cutover window.

### Recommended Rotation Workflow

1. Create a new credential on the target system, allowing overlap with the old credential where possible.
2. Add a new version in Secret Manager without editing source code.
3. Test reading the new version with an authorized identity in a test environment.
4. Update the version reference or deploy a new revision so instances start with the new credential.
5. Verify connectivity, health checks, and real business flows succeed.
6. Shift all traffic to the new application version or restart instances still holding the old credential.
7. Revoke the old credential on the target system and disable or destroy the old secret version per policy.
8. Monitor logs, metrics, and audit events to detect any workload still using the old credential.

Never destroy the old version before verifying the rollout and recovery path. Application rollbacks may rely on the old version briefly, though keeping old credentials active too long also raises risk. Define clear retention windows and revocation criteria.

### Can Secrets Auto-Refresh?

Some Spring Cloud GCP lines support refresh mechanisms via Spring Cloud Context and `@RefreshScope`. However, invoking refresh only affects supported beans and config styles; it does not automatically rebuild a `DataSource`, connection pool, or already-open connections. Never build a rotation workflow assuming every bean refreshes instantaneously.

The most controllable pattern on Cloud Run or GKE is releasing a new revision/rollout with an explicit version, running smoke tests, and shifting traffic after verification. For systems requiring hot updates, explicitly design secret reloading, client/pool replacement, draining old connections, and testing in staging.

## 14. Common Errors and Investigation

| Symptom | Possible cause | How to check |
|---|---|---|
| Secret not found | Wrong project, secret ID, or version | Verify resource name, project, and existing version |
| `PERMISSION_DENIED` | Runtime identity lacks read permission on the secret | Check service account and IAM binding on the exact secret |
| `NOT_FOUND` | Secret/version does not exist or was destroyed | Check resource path and version lifecycle |
| `FAILED_PRECONDITION` | Version is disabled or state blocks access | Check secret version status |
| `UNAVAILABLE` or timeout | Connectivity, Google API, or transient issue | Check network, DNS, egress, and bounded retries |
| `RESOURCE_EXHAUSTED` | Quota exceeded or excessive request rate | Reduce read frequency, cache values, and check quotas |
| Placeholder remains unresolved | Wrong syntax for library line or import not enabled | Check BOM, starter, and `spring.config.import` |
| Works locally, fails on Cloud Run | Runtime service account or project differs from local | Compare local ADC against Cloud Run service identity |
| App starts, DB returns `401`/`28P01` | Secret does not match database credential | Check rotation steps and exact database user |
| Added version, app still uses old value | Bean or pool loaded secret only at startup | Plan rollout/restart or controlled refresh |

Never troubleshoot by printing the entire Spring `Environment` or password values for comparison. Log error codes, secret names, projects, versions, and correlation IDs as appropriate; keep payloads out of logs, traces, metric labels, and exception messages.

### Verify Exact Library Versions

If `sm@` import is not recognized, first check the Spring Framework on Google Cloud version. Lines 4.x/5.x use `sm://`; `sm@` syntax was introduced in 6.0.0. Also verify the starter appears in the dependency tree and matches your Spring Boot version. Never copy a property from a guide for another major version and blame the Secret Manager API.

If using Spring Cloud Config Server's Secret Manager backend, configuration workflows and app/profile mappings differ from the starter reading directly via Config Data API. Distinguish the two architectures before choosing settings.

## 15. Securing Data in Spring and Pipelines

Secret Manager mitigates the risk of secrets leaking in Git, yet applications still handle plaintext payloads at runtime. Security therefore depends on how values move through memory, logs, networks, and diagnostic tools.

Key principles:

- Never write tokens, passwords, or private keys in Java source, Dockerfiles, `application.yml`, or build substitutions.
- Never put secrets in URLs/query strings, exception messages, metrics, traces, or structured logs.
- Never pass secrets as system properties or command-line arguments if they could appear in logs or process listings.
- Enforce least-privilege IAM and separate service accounts per workload and environment.
- Never expose production secrets to pull-request builds or test environments.
- Avoid long-lived JSON credentials; prefer ADC and Workload Identity Federation.
- Protect Spring Actuator—especially `env`, `configprops`, `heapdump`, or endpoints exposing configuration data.
- Never log whole `@ConfigurationProperties` beans containing tokens; record `toString()` can expose sensitive fields.
- Review audit logs and configure logging properly to investigate anomalous access.
- Rotate exposed credentials immediately, even if the offending commit was removed.

With Spring Boot Actuator, restrict exposed endpoints and prevent displaying sensitive values:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

This example reduces configuration exposure surface. Endpoint access must still be protected with network controls and Spring Security or equivalent; never treat value masking as a substitute for authentication.

In CI/CD pipelines, build service accounts usually only need to build artifacts and deploy. Never grant them runtime secret read access unless the build itself strictly needs it. Conversely, runtime service accounts need secret read access, not permission to alter pipelines or push images.

## 16. Testing Applications That Depend on Secret Manager

Split testing into layers:

| Test level | Approach | Goal |
|---|---|---|
| Unit test | Mock clients or supply test properties | Test business logic without network calls |
| Spring context test | Activate test profile without Secret Manager import | Test config binding and bean wiring |
| Integration test | Use dedicated test secrets and least-privilege test principal | Verify real API and connectivity |
| Deployment smoke test | Run under the real runtime service account | Confirm revision/Pod reads granted secrets |
| Rotation test | Add a test version and roll out again | Verify safe credential cutover |
| Failure test | Revoke permission in test env or reference bad version | Verify app fails clearly without static fallback secrets |

Example `application-test.yml` without Secret Manager import:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:orders_test
    username: sa
    password: ""
~~~

This example assumes the project includes the H2 test dependency or an appropriate test datasource. Never leave `sm@` imported in shared config files if tests must run offline. If your project must validate production-like configuration, run a separate integration test suite with dedicated test secrets and permissions.

### Testing Missing Permissions

In a test environment, revoke `secretAccessor` from the test principal or point to an unauthorized secret. Verify the application fails to read the secret and reports the expected error category without exposing any payload.

Never revoke permissions directly on a live production secret used by active workloads as a "quick test" without proper planning and isolated test scope.

## 17. Observability and Cost Optimization

Accessing Secret Manager generates API requests. If an application fetches secrets on every HTTP request, latency, quota usage, and costs rise. Most passwords and tokens only need loading at startup or on controlled refresh events.

Track:

- Application startup failure rates caused by unreadable secrets.
- Unusual secret read spikes following deploys or rotations.
- Latency of secret read operations when instrumented.
- IAM changes and secret access events via Cloud Audit Logs.
- Secret version states and old-credential revocation milestones.
- Secret Manager usage against quotas, budgets, and retention policies.

Never put secret payloads or high-cardinality user IDs in metric labels. Use resource names or non-sensitive error codes for troubleshooting. With multi-replica apps, pair version changes with phased rollouts and connection monitoring rather than letting every replica refresh simultaneously unchecked.

## 18. Hands-On Exercise: Spring Boot Reading a Password and API Token

Suppose the `orders-api` service connects to PostgreSQL and calls a payment partner. Previously `application-prod.yml` held the database password and API token. You need to migrate both secrets into Secret Manager and verify the application reads them via its runtime identity.

Steps in a test Google Cloud project:

1. Create two secrets `orders-db-password` and `payments-api-token`, adding versions containing **test** credentials.
2. Create a runtime service account for `orders-api` and grant `roles/secretmanager.secretAccessor` on those exact two secrets.
3. Check the Spring Framework on Google Cloud major version in use and select `sm@` or `sm://` accordingly.
4. Add `spring-cloud-gcp-starter-secretmanager` and a compatible BOM to `pom.xml`.
5. In `application-staging.yml`, declare `spring.config.import` and reference the password via a Secret Manager placeholder.
6. Define `payments.api-token` and inject it into `PaymentCredentialProvider` or `PaymentSettings`.
7. Use ADC with a test principal to run the app locally or in staging. Verify database connectivity and the HTTP client work.
8. Deploy to Cloud Run with the authorized runtime service account. Verify revision readiness and run smoke tests.
9. Test updating the version of `payments-api-token` and verify restarting/deploying the revision reads the new version.
10. Inspect logs, Actuator exposure, and build artifacts to confirm no payloads appear.
11. Revoke read access on one secret in the test environment and verify the app fails clearly without falling back to hardcoded values.
12. Restore test permissions, complete the rotation workflow, and verify the old credential is revoked on schedule.

### Completion Criteria

- Source code and committed config files contain no passwords or tokens.
- Spring Boot reads secrets using the exact syntax matching the library version.
- Runtime service account holds access only to required secrets.
- Tests never require production secrets.
- Application never exposes payloads via APIs, logs, or Actuator.
- Version update workflows include validation and old-credential revocation.

## 19. Production Readiness Checklist

- [ ] Secrets and ordinary configurations are clearly separated.
- [ ] Secret names, projects, and versions are explicitly defined per environment.
- [ ] Secret Manager API and replication follow organizational policy.
- [ ] Each runtime identity holds only the `secretAccessor` permissions it requires.
- [ ] No service account JSON keys reside in repositories or images.
- [ ] Starter and Spring Boot versions are compatible; `sm@` or `sm://` matches the major version.
- [ ] Spring config holds only secret references, never payloads.
- [ ] Config classes or beans holding secrets are never logged or serialized externally.
- [ ] Spring Actuator does not expose `env`/`configprops`/`heapdump` to unauthorized callers.
- [ ] Runtime networking can reach the Secret Manager API when using direct integration.
- [ ] Caching or refresh strategies prevent per-request secret reads.
- [ ] Missing permissions, invalid versions, and API unavailability are handled cleanly.
- [ ] Rotation plan covers both target systems and application rollouts.
- [ ] Tests cover startup, smoke checks, and missing-permission failure paths.
- [ ] Active secret version can be traced without printing payloads.
- [ ] Logs, metrics, builds, and artifacts have been audited for secret leaks.

## Self-Check Questions

**1. Why should database passwords never be stored in `application.yml`?**

Because config files can be committed, copied into images, or retained in artifacts and logs. Secret Manager stores payloads outside the repository and governs read access with IAM.

**2. How do Spring Cloud GCP 4.x/5.x and newer lines differ in syntax?**

Older lines use `sm://`; starting in 6.0.0, `sm@` was introduced and is recommended in newer lines. Check the actual library version before choosing imports and placeholders.

**3. What does ADC provide to a Spring Boot application?**

ADC lets client libraries discover an identity from the execution environment. IAM on that identity determines which secrets are accessible, removing the need to embed JSON keys in source code.

**4. Does adding a new secret version automatically change a running `DataSource`'s password?**

Not by default. A `DataSource` or connection pool keeps values loaded at startup. You need a controlled refresh mechanism or rollout/restart, coordinated with credential updates on the database.

**5. When should you use the Secret Manager Java SDK directly?**

When an application must read secrets actively upon an event or for a specific version at runtime, rather than injecting secrets solely as startup configuration properties.

**6. Why might a GKE Pod with valid IAM still fail to read a secret?**

The workload may lack properly configured Workload Identity Federation for GKE, or lack network connectivity to the API. Check identity, bindings, and network paths.

**7. If a password appeared in Git once, is removing it from the latest commit enough?**

No. Clones, branches, artifacts, or logs may still retain the old value. Revoke or rotate the password on the target system.

## References

- [Spring Framework on Google Cloud 7.x – Secret Manager Config Data](https://googlecloudplatform.github.io/spring-cloud-gcp/7.0.0/reference/html/index.html)
- [Spring Framework on Google Cloud 5.x – Secret Manager](https://googlecloudplatform.github.io/spring-cloud-gcp/5.13.2/reference/html/index.html)
- [Google Codelab: Retrieving Credentials/Secrets from Secret Manager with Spring Boot](https://codelabs.developers.google.com/codelabs/cloud-spring-cloud-gcp-secret-manager)
- [Spring Boot: Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Google Cloud: Secret Manager overview](https://docs.cloud.google.com/secret-manager/docs/overview)
- [Google Cloud: Access control for Secret Manager](https://docs.cloud.google.com/secret-manager/docs/access-control)
- [Google Cloud: Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Google Cloud: Cloud Run configure secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Google Cloud: Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Google Cloud: Secret Manager audit logging](https://docs.cloud.google.com/secret-manager/docs/audit-logging)

## Conclusion

Reading secrets in Spring Boot from Secret Manager combines configuration, identity, and credential lifecycle management. Secret Manager holds payloads and versions; IAM restricts reads; ADC supplies environment-appropriate identities; Spring Cloud GCP or the Java SDK delivers values to the right application components. Choose `sm@` or `sm://` according to your library major version, keep secrets out of source code, and establish rotation procedures verified across both applications and target systems. By managing projects, versions, runtime permissions, logging, and refresh behavior clearly, Java applications on Google Cloud stay flexibly configured while keeping credentials protected.
