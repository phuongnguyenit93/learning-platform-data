# Hands-On: Standardizing Java Configuration Across Multiple GCP Environments

A Java/Spring Boot service normally runs across multiple environments: local workstations, development, staging, and production. Each environment has its own Google Cloud project, endpoints, Pub/Sub topics, databases, resource limits, and security policies. If developers edit Java code directly or build a separate JAR for each environment, the team struggles to prove production runs the exact artifact tested in staging, while increasing the risk of shipping wrong resource targets or secrets.

**Standardizing configuration** means maintaining a single codebase and a single artifact while supplying environment-appropriate configuration values at deployment time. Spring Boot supports externalized configuration through YAML/properties, environment variables, command-line arguments, and other sources. On Google Cloud, you can pair this with Cloud Run, Google Kubernetes Engine (GKE), Secret Manager, IAM, Artifact Registry, and CI/CD pipelines to govern configuration reliably.

This hands-on lesson builds a simple checkout service and deploys it across multiple GCP environments following **build once, deploy many**, separating sensitive data from ordinary configuration, and validating correctness as soon as the application boots.

## Learning Objectives

After this lesson, you will be able to:

- Classify configuration by sensitivity level and environment scope.
- Design a cohesive set of `application.yml`, profile-specific YAML, and environment variables.
- Use `@ConfigurationProperties` to bind configuration to typed Java models with validation.
- Apply Application Default Credentials (ADC), IAM, and Secret Manager to eliminate static keys.
- Configure Cloud Run or GKE with dedicated values for dev/staging/prod.
- Build a single container image and promote the exact same digest across environments.
- Validate configuration without leaking secrets into logs.
- Establish procedures for reviewing, rolling back, detecting drift, and operating configuration safely.

## 1. Problems of Inconsistent Configuration

Common anti-patterns:

- Source code hardcodes a development `PROJECT_ID` or topic name.
- Production database connection strings are written into `application-prod.yml` and committed to Git.
- Environments run different JAR builds despite coming from the same commit.
- Staging lacks production-like concurrency limits, making load tests unrepresentative.
- Timeouts are edited in the Console without updating the repository or deployment pipeline.
- An environment runs the `prod` profile yet still references `dev` resources.
- During an application rollback, nobody knows when configuration changed.

A solid configuration system must guarantee:

1. Values have clear names and semantics.
2. Values are scoped and controlled per environment.
3. Sensitive data is protected by a dedicated mechanism.
4. The application fails fast if mandatory settings are missing.
5. Running artifact and configuration versions are traceable.
6. The exact same artifact deploys across environments without code edits.

## 2. Classifying Configuration Before Writing Code

Not every setting belongs in the same YAML file.

| Configuration group | Examples | Recommended management place |
|---|---|---|
| Shared, non-sensitive values | Service name, default timeouts, feature behavior | `application.yml` or code defaults |
| Environment-specific values | Project ID, topic ID, endpoints, concurrency | Environment variables or deployment config |
| Secrets | API keys, passwords, certificates, tokens | Secret Manager and IAM permissions |
| Infrastructure | CPU, memory, min/max instances, service accounts | IaC and Cloud Run/GKE config |
| Access permissions | Pub/Sub Publisher, Secret Manager Accessor | IAM policies per service account |
| Feature rollouts | Enabling features for small cohorts, canaries | Feature flag service or controlled configuration |

Separate **configuration** from **secrets**. A project ID is usually not secret; a password or API token is secret. Never place secrets in Git, Dockerfiles, build arguments, shared CI variables, or diagnostic logs.

### Configuration Is Part of the Operational Contract

For every field, document:

- Name and data type.
- Default value, if any.
- Whether it is mandatory in production.
- Environment scope.
- Who is authorized to change it.
- Blast radius if misconfigured.
- Whether changing it requires a restart or redeploy.

For example, `CHECKOUT_TIMEOUT=2s` bounds dependency calls, whereas `CHECKOUT_PROJECT_ID` identifies the project hosting the Pub/Sub topic. Setting the wrong project can route data to another environment's resources. This field must be strictly validated even though the value itself is not a secret.

## 3. Multi-Environment Configuration Architecture

One clean structure looks like:

~~~text
Git repository
  |
  +-- src/main/resources/application.yml
  +-- src/main/resources/application-local.yml
  +-- src/main/resources/application-staging.yml
  +-- src/main/resources/application-prod.yml
  |
  +-- Spring Boot source code
  |
  v
CI/CD: build + test + image digest
  |
  +--------> Dev Cloud Run / GKE
  |             + env dev + service account dev + secrets dev
  |
  +--------> Staging Cloud Run / GKE
  |             + env staging + service account staging + secrets staging
  |
  +--------> Production Cloud Run / GKE
                + env prod + service account prod + secrets prod
~~~

In this model, the image digest stays identical across environments. What varies belongs to deployment: profile, environment variables, secret references, IAM, and infrastructure sizing.

**Never treat a profile name as a security boundary.** Real isolation comes from IAM, project boundaries, network policies, and service account permissions. A profile only selects which configuration group Spring loads.

## 4. Structuring Spring Boot Configuration

Our example checkout project uses Java 21 and Spring Boot 3.x. A clean layout:

~~~text
checkout-service/
  src/main/java/com/example/checkout/
    CheckoutApplication.java
    config/CheckoutProperties.java
    service/CheckoutService.java
  src/main/resources/
    application.yml
    application-local.yml
    application-staging.yml
    application-prod.yml
  pom.xml
  Dockerfile
~~~

### `application.yml`: Shared Configuration

~~~yaml
spring:
  application:
    name: checkout-service

checkout:
  project-id: "${CHECKOUT_PROJECT_ID}"
  topic-id: "${CHECKOUT_TOPIC_ID}"
  payment-api-base-url: "${PAYMENT_API_BASE_URL}"
  request-timeout: "${CHECKOUT_TIMEOUT:2s}"
  max-in-flight: "${CHECKOUT_MAX_IN_FLIGHT:16}"

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Placeholders without defaults mark required configuration. If `CHECKOUT_PROJECT_ID`, `CHECKOUT_TOPIC_ID`, or `PAYMENT_API_BASE_URL` is omitted, the app must fail at startup rather than silently using the wrong project or endpoint.

Defaults for timeouts and concurrency are merely starting baselines; production deployments should specify tested values explicitly.

### `application-local.yml`: Running on a Developer Machine

~~~yaml
checkout:
  project-id: local-project
  topic-id: orders-local
  payment-api-base-url: http://localhost:8089
  request-timeout: 3s
  max-in-flight: 4

logging:
  level:
    com.example.checkout: DEBUG
~~~

The `local` profile can point to stubs or emulators for dependencies. Never point local defaults at production. When using the Pub/Sub emulator, configure emulator endpoints and credentials per your client/framework rather than assuming renaming the topic suffices.

### `application-staging.yml`: Pre-Production Environment

~~~yaml
checkout:
  request-timeout: 2s
  max-in-flight: 16

logging:
  level:
    root: INFO
~~~

Staging should mirror production closely in dependency types and key policies. Project ID, topic ID, and endpoint continue to be injected by deployment settings.

### `application-prod.yml`: Production Configuration

~~~yaml
checkout:
  request-timeout: 1500ms
  max-in-flight: 32

logging:
  level:
    root: WARN
~~~

Production must have no implicit fallbacks to dev data. Never commit endpoints embedding credentials or private IPs violating organizational security rules.

### Activating Profiles

On a developer machine:

~~~bash
export SPRING_PROFILES_ACTIVE=local
./mvnw spring-boot:run
~~~

On Cloud Run/GKE, set `SPRING_PROFILES_ACTIVE` to `staging` or `prod` in deployment configuration. If no profile is active, Spring loads only unprofiled config and the framework default profile; required fields must still be enforced by validation.

## 5. Understanding Configuration Source Precedence

Spring Boot resolves properties from multiple sources in a defined precedence order. In general, values from higher-precedence sources override lower ones.

Common sources:

- `application.yml` packaged inside the JAR.
- `application-{profile}.yml` for active profiles.
- External config files outside the JAR.
- Environment variables.
- Java system properties.
- Command-line arguments.

Exact ordering depends on source types, file locations, and launch mechanism. When unsure about an override, check the externalized configuration docs for your exact Spring Boot version.

Example:

~~~yaml
# application.yml
checkout:
  max-in-flight: 16
~~~

If the deployment sets `CHECKOUT_MAX_IN_FLIGHT=40`, Spring Boot relaxed binding maps that environment variable onto `checkout.max-in-flight`.

Adopt one consistent naming convention: kebab-case in Java/YAML properties, and uppercase with underscores for environment variables. Avoid defining multiple aliases for the same setting.

### Why Avoid Overusing `@Value`?

`@Value` works fine for a handful of settings, yet once a service has dozens of properties, string keys scatter across the codebase without centralized validation.

`@ConfigurationProperties` groups properties by domain, provides strong typing, and validates at application startup.

## 6. Binding Configuration into Java with `@ConfigurationProperties`

Example using a Java record and Jakarta Bean Validation:

~~~java
package com.example.checkout.config;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @NotBlank String projectId,
        @NotBlank String topicId,
        @NotNull URI paymentApiBaseUrl,
        @NotNull Duration requestTimeout,
        @Min(1) int maxInFlight
) {}
~~~

Spring Boot binds `Duration` automatically from strings such as `2s` or `1500ms`. To enable validation, include the Spring Boot validation starter (`spring-boot-starter-validation`).

Enable configuration properties scanning:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Consume it inside services:

~~~java
package com.example.checkout.service;

import com.example.checkout.config.CheckoutProperties;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final CheckoutProperties properties;

    public CheckoutService(CheckoutProperties properties) {
        this.properties = properties;
    }

    public String topicPath() {
        return "projects/" + properties.projectId()
                + "/topics/" + properties.topicId();
    }
}
~~~

The properties object is an immutable record, ideal for injection and reading across components. If runtime updates without restarts are required, build a dedicated config-refresh mechanism; a record bound at startup does not auto-refresh when environment variables or secrets change.

### Environment-Specific Validation Rules

Bean Validation catches nulls, blanks, and numeric bounds. However, a syntactically valid project ID can still point to the wrong project.

Add startup or admission/deploy pipeline checks:

- The `prod` profile must not use topics ending in `-dev`.
- Production project IDs must appear on an allowlist.
- Production payment endpoints must use `HTTPS`.
- `max-in-flight` must remain below the approved concurrency budget.
- Request timeouts must not exceed the system's HTTP request timeout.

Write tests for these rules and verify them before serving traffic. Never print full configuration values in validation errors if they could contain sensitive data.

## 7. Projects, Identities, and Credentials per Environment

Each environment should have its own service account or workload identity. The same Java image runs in both dev and prod projects, while the identity calling GCP APIs comes from the runtime.

### Application Default Credentials

Google Cloud Java client libraries support ADC. On Cloud Run, a service account attaches to the service; on GKE, use Workload Identity Federation for GKE. Locally, developers configure ADC using organization-approved login workflows.

In code:

~~~java
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;

try (SecretManagerServiceClient client =
         SecretManagerServiceClient.create()) {
    // Client uses the environment's default credentials.
}
~~~

This snippet suits short-lived utilities. In long-running Spring Boot services, manage clients as singleton beans and close them when the application context shuts down.

Never put service account JSON keys into images, source code, or `application-prod.yml`. If a service accesses multiple projects, grant properly scoped IAM to its runtime service account—never share one all-powerful key across environments.

### Environment Matrix

| Property | Development | Staging | Production |
|---|---|---|---|
| Project ID | `checkout-dev` | `checkout-staging` | `checkout-prod` |
| Spring profile | `dev` | `staging` | `prod` |
| Runtime identity | `checkout-dev` SA | `checkout-staging` SA | `checkout-prod` SA |
| Pub/Sub topic | `orders-dev` | `orders-staging` | `orders-prod` |
| Secret Manager | Dev secret | Staging secret | Prod secret |
| Database | Dev instance | Staging instance | Prod instance |
| Logging | Controlled `DEBUG` | `INFO` | `INFO`/`WARN` |
| IAM permissions | Per dev needs | Production-like | Strict least privilege |

Names in this table are examples. Real project IDs must come from organizational allocation, never inferred from profile strings.

## 8. Secret Manager: Managing Sensitive Data

Secret Manager stores API keys, tokens, passwords, and certificates. Applications should receive read access only to the secrets they need.

On Cloud Run, secrets enter containers in two ways:

- **Environment variable:** value resolves at instance startup. Fits apps reading configuration once; pin explicit versions for reproducible deployments.
- **Mounted volume:** secret appears as a file. When read, Cloud Run pulls from Secret Manager, supporting dynamic reload on rotation per configuration.

Example binding a pinned version to an environment variable during deploy:

~~~bash
gcloud run deploy checkout \
  --image IMAGE_DIGEST \
  --project CHECKOUT_PROD_PROJECT \
  --region asia-southeast1 \
  --service-account checkout-runtime@CHECKOUT_PROD_PROJECT.iam.gserviceaccount.com \
  --update-secrets PAYMENT_API_KEY=payment-api-key:5
~~~

Here, `IMAGE_DIGEST` is a full digest reference like `registry/repository/image@sha256:digest`. The `payment-api-key` secret exists in the project, and the runtime service account holds `Secret Manager Secret Accessor` on it.

### Never Store Secrets in Environment Files

`production.env.yaml` should contain only non-sensitive settings. Declare secrets separately via secret references or controlled volume mounts. Keep secrets out of `terraform plan` output, CI logs, debug endpoints, and container snapshots.

Never leave Actuator `env` or `configprops` exposed to external callers by default. When operational endpoints are needed, enforce authentication, access control, and sensitive-value masking.

### Secret Rotation

With environment-variable secrets, running instances do not automatically pick up values when a new secret version is created. Perform a controlled rollout so new instances adopt the chosen version. With volume mounts, reading updates can be more dynamic, though the app must decide when to reload file contents.

Do not rely on `latest` as a complete rotation strategy. Test new versions, pin versions where appropriate, roll out progressively, keep rollback paths, and revoke old credentials/versions safely.

## 9. Hands-On: Deploying to Cloud Run Across Environments

The goal is building one tested container image and promoting the exact same digest across dev, staging, and production.

### Step 1: Build the Image Once

Example building with Cloud Build:

~~~bash
gcloud builds submit \
  --tag asia-southeast1-docker.pkg.dev/BUILD_PROJECT/java-services/checkout:COMMIT_SHA \
  --project BUILD_PROJECT
~~~

After pushing, record the exact digest from Artifact Registry. Log the commit, build ID, digest, and test/scan results before promoting.

### Step 2: Staging Environment Variables File

Contents of `staging.env.yaml` in the deployment repository:

~~~yaml
SPRING_PROFILES_ACTIVE: staging
CHECKOUT_PROJECT_ID: checkout-staging
CHECKOUT_TOPIC_ID: orders-staging
PAYMENT_API_BASE_URL: https://payments-staging.example.com
CHECKOUT_TIMEOUT: 2s
CHECKOUT_MAX_IN_FLIGHT: "16"
~~~

Because this file contains only non-secret settings, it can be reviewed in Git. Replace illustrative endpoints with real ones. Never commit tokens or passwords here.

### Step 3: Deploy Staging

~~~bash
gcloud run deploy checkout \
  --image IMAGE_DIGEST \
  --project CHECKOUT_STAGING_PROJECT \
  --region asia-southeast1 \
  --service-account checkout-runtime@CHECKOUT_STAGING_PROJECT.iam.gserviceaccount.com \
  --env-vars-file staging.env.yaml \
  --update-secrets PAYMENT_API_KEY=payment-api-key:3
~~~

The runtime service account requires appropriate IAM for Pub/Sub, Secret Manager, and other dependencies. When the image resides in a separate build project from the deployment project, the image-pulling identity needs `Artifact Registry Reader`—separate from the runtime service account's API permissions.

### Step 4: Production Environment Variables File

~~~yaml
SPRING_PROFILES_ACTIVE: prod
CHECKOUT_PROJECT_ID: checkout-prod
CHECKOUT_TOPIC_ID: orders-prod
PAYMENT_API_BASE_URL: https://payments.example.com
CHECKOUT_TIMEOUT: 1500ms
CHECKOUT_MAX_IN_FLIGHT: "32"
~~~

Production has its own settings and secrets, while running the exact image digest already verified in staging.

### Step 5: Controlled Production Deployment

~~~bash
gcloud run deploy checkout \
  --image IMAGE_DIGEST \
  --project CHECKOUT_PROD_PROJECT \
  --region asia-southeast1 \
  --service-account checkout-runtime@CHECKOUT_PROD_PROJECT.iam.gserviceaccount.com \
  --env-vars-file prod.env.yaml \
  --update-secrets PAYMENT_API_KEY=payment-api-key:5
~~~

This shows command syntax; real production commands must be reviewed, substitute real values, target the verified project, and obey organizational approval and canary policies. Updating environment variables or secret references on Cloud Run creates a new revision. Record the revision and diff before/after settings to verify nothing mandatory was dropped.

**Note:** `gcloud --set-env-vars` replaces the entire environment variable list, whereas `--update-env-vars` updates only named keys. With `--env-vars-file`, review the full set of values applied by the deployment. Use versioned manifests in Git or IaC as the source of truth.

## 10. Deploying on GKE with ConfigMaps and Workload Identity

On GKE, non-sensitive values can live in a `ConfigMap`, while secrets come from Secret Manager via supported integrations. Runtime identity should use Workload Identity Federation for GKE rather than static keys in Pods.

### Example ConfigMap

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-config
  namespace: production
data:
  SPRING_PROFILES_ACTIVE: "prod"
  CHECKOUT_PROJECT_ID: "checkout-prod"
  CHECKOUT_TOPIC_ID: "orders-prod"
  PAYMENT_API_BASE_URL: "https://payments.example.com"
  CHECKOUT_TIMEOUT: "1500ms"
  CHECKOUT_MAX_IN_FLIGHT: "32"
~~~

### Deployment Consuming the ConfigMap

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: production
spec:
  replicas: 2
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      serviceAccountName: checkout
      containers:
        - name: checkout
          image: asia-southeast1-docker.pkg.dev/BUILD_PROJECT/java-services/checkout@sha256:IMAGE_DIGEST
          envFrom:
            - configMapRef:
                name: checkout-config
          ports:
            - containerPort: 8080
~~~

This example omits probes, resource requests/limits, secret mounts, and Workload Identity configuration. In production, add those and ensure the Kubernetes ServiceAccount holds only least-privilege GCP permissions.

When a `ConfigMap` is injected as environment variables, running Pods do not pick up updates automatically when the `ConfigMap` changes. Perform a rollout/restart so Pods adopt new settings. When mounted as a volume, files update via Kubernetes sync, yet Spring Boot does not auto-reload `@ConfigurationProperties` simply because a file changed.

### Multi-Environment Considerations on GKE

- Enforce namespace, cluster, or project isolation per security policy.
- Restrict Kubernetes RBAC and GCP IAM permissions.
- Never share a single Kubernetes `Secret` across dev and prod.
- Use GitOps/IaC to manage manifests, ConfigMaps, and rollouts.
- Promote only verified image digests.
- Configure liveness/readiness/startup probes matching startup times and dependencies.

## 11. One Artifact, Multiple Configurations: Versioning and Rollback

The build-once, deploy-many principle eliminates drift between staging and production artifacts. Yet sharing an image alone is insufficient; you must also record the **deployed configuration**.

A deployment record should capture:

| Field | Example |
|---|---|
| Source commit | `8f3a2c1` |
| Image digest | `sha256:...` |
| Environment | `production` |
| Spring profile | `prod` |
| Config revision | Commit or version of the deployment repo |
| Secret references | `payment-api-key` version 5 |
| Runtime service account | `checkout-runtime` in the production project |
| Deployment timestamp | Release timestamp |
| Approver | Person/group approving per change policy |

Rolling back may require reverting both image and configuration. If an update changed endpoint, secret version, and timeout together, reverting only the image while leaving new config in place can still break.

### Promotion Pipeline

~~~text
Commit code
   |
   v
Build -> Unit tests -> Integration tests -> Scan
   |
   v
Artifact Registry image digest D
   |
   v
Deploy dev with config C-dev
   |
   v
Deploy staging with config C-staging
   |
   v
Verify SLI / smoke tests / business checks
   |
   v
Deploy production with config C-prod
   |
   v
Canary / monitor / rollback if needed
~~~

All three environments run digest `D`. Configurations `C-dev`, `C-staging`, and `C-prod` differ by environment yet remain versioned and peer-reviewed.

## 12. Validating Configuration Before Accepting Traffic

A service must never wait until handling a live request to discover a missing project ID or endpoint.

### Fail Fast

- Apply `@Validated` and `@ConfigurationProperties` to mandatory configuration.
- Validate URIs, timeouts, and concurrency bounds before constructing clients or accepting traffic.
- Never allow production to default to local values.
- Validate resource mappings (project, topic, secret reference) inside the deployment pipeline.
- Emit clear startup errors without logging plaintext secrets.

### Health Checks

Spring Boot Actuator provides health endpoints when configured. Liveness checks whether the process is healthy; readiness determines whether the application can accept traffic.

Never configure a liveness probe to call an external dependency repeatedly and restart the app whenever that dependency slows down. Readiness can reflect conditions needed to serve traffic, while avoiding turning dependency glitches into Pod restart loops.

On Cloud Run/GKE, tune startup delays and probes for JVM boot time, warm-up, database connections, and client initialization.

### Never Let Logs Reveal Secrets

Logs may record:

~~~text
Service=checkout
Environment=production
ConfigVersion=cfg-2026-11-19
Project=checkout-prod
Topic=orders-prod
Timeout=1500ms
SecretReference=payment-api-key:5
~~~

Never log `PAYMENT_API_KEY` values, passwords, access tokens, or certificate private keys. Even resource names and secret references should only appear in logs with appropriate access controls.

## 13. Testing Multi-Environment Configuration

A practical strategy tests at multiple layers.

### Unit Tests for Property Binding

Verify:

- Default values apply correctly.
- Missing project/topic/endpoint fails startup.
- `Duration` strings parse properly.
- Zero or negative `max-in-flight` is rejected.
- Production settings reject dev endpoints.

### Profile-Based Tests

Example running tests with a Spring profile:

~~~bash
./mvnw -B -ntp test -Dspring.profiles.active=local
~~~

Use `@ActiveProfiles` in Spring tests to select profiles. Use stubs/mocks or emulators for dependencies; never let unit tests accidentally call production Secret Manager or Pub/Sub.

### Integration Tests in Staging

- Runtime service account accesses the intended secret and topic.
- Configured endpoints reach the right dependencies.
- Pub/Sub publishes or database queries succeed.
- Timeouts/retries align with SLOs.
- Readiness/liveness and request paths work properly.
- Zero secrets leak into logs or error responses.

### Deployment and Rollback Tests

Deploy the same image digest with staging config and then production config, verifying only runtime configuration changes. Simulate rolling back a broken secret reference or env var in a test environment to validate recovery procedures.

## 14. Detecting Configuration Drift

Configuration drift occurs when the live environment diverges from the source of truth: someone edits environment variables in the Console, swaps a service account, changes a secret reference, or edits a ConfigMap in-cluster without updating Git.

To detect drift:

1. Store deployment manifests/IaC in a peer-reviewed repository.
2. Periodically compare live resource state against declared configuration.
3. Use audit logs to identify changes and the acting principal.
4. Alert on out-of-band changes outside authorized pipelines.
5. Decide whether to accept, revert, or codify the change in IaC per policy.

On Cloud Run, every config change spawns a new revision, aiding per-revision audits and rollbacks. On GKE, GitOps controllers detect and reconcile differences between Git manifests and cluster resources. Take care that an automated controller does not overwrite an urgent incident mitigation before responders agree on a permanent fix.

## 15. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Hardcoding project ID in Java | Deploys to wrong environment | Externalize and validate project ID |
| Committing secrets in `application-prod.yml` | Credential leaks in Git/artifacts | Use Secret Manager and IAM |
| Sharing one service account across all environments | Wide blast radius | Separate identities and roles per environment |
| Building a separate JAR for prod | Artifact differs from staging; poor traceability | Build once, promote by digest |
| Running `prod` profile with `dev` topic | Data leaks across environments | Validate mappings and enforce policies at startup/CI |
| Unversioned environment variables | Hard rollbacks and drift | Track deployment config in Git/IaC |
| Uncontrolled `latest` secret env vars | Instances silently drift onto different versions | Pin versions and roll out intentionally |
| Expecting ConfigMap env vars to auto-refresh | Pods keep running stale values | Roll out or restart Pods on changes |
| Dumping all configuration to logs | Risks leaking secrets | Mask values and log via allowlists |
| Allowing local defaults in production | Masks missing configuration bugs | Fail fast on required properties |
| Not promoting by image digest across envs | Cannot prove tested artifact matches prod | Promote a single immutable digest |
| Rolling back only the image | New config may still break old code | Roll back paired configuration too |

## 16. Comprehensive Practice Exercise

Deploy `checkout-service` from a single Java image into staging and production on Cloud Run.

### Requirements

- Identical image digest across both environments.
- Matching `staging` or `prod` Spring profile.
- Separate project, Pub/Sub topic, and endpoint per environment.
- `payment-api-key` secret fetched from Secret Manager.
- Least-privilege runtime service account.
- Validated timeout and `max-in-flight` settings.
- Ability to inspect deployment revisions and roll back configuration.

### Steps

1. Define `CheckoutProperties` with validation.
2. Create `application.yml` with shared properties and mandatory placeholders.
3. Create profile-specific YAML only for legitimate behavioral differences.
4. Create `staging.env.yaml` and `prod.env.yaml` without secrets.
5. Build the image once and record its digest.
6. Deploy staging with that digest and staging config.
7. Run smoke tests, inspect logs, and verify IAM permissions.
8. Deploy production with the exact same digest and prod config.
9. Verify live project, topic, and secret references.
10. Update timeout on staging via the pipeline; verify the new revision and rollback procedure.

### Completion Criteria

| Criterion | Expected outcome |
|---|---|
| Image | Identical digest between staging and production |
| Config | Environment-accurate profiles and environment variables |
| Secrets | Zero plaintext secrets in Git, images, or logs |
| IAM | Service accounts hold only required permissions |
| Validation | Missing/invalid properties fail startup with safe messages |
| Traceability | Recorded image digest, config revision, and secret version |
| Rollback | Can revert cleanly to a stable config/revision |
| Observability | Dashboards/logs distinguish service, environment, and revision |

## 17. Production Configuration Standardization Checklist

- [ ] Configuration is classified into non-sensitive, sensitive, and infrastructure settings.
- [ ] `application.yml` contains safe defaults and explicit placeholders.
- [ ] `application-{profile}.yml` contains zero credentials.
- [ ] `@ConfigurationProperties` enforces strong typing and validation.
- [ ] No silent fallback exists from production to local/dev.
- [ ] Project IDs, topics, endpoints, and secret references match each environment.
- [ ] ADC/Workload Identity and runtime service accounts are properly configured.
- [ ] Least-privilege IAM is granted per service and environment.
- [ ] Secret Manager versions and env/volume delivery modes are chosen deliberately.
- [ ] Build once, deploy to multiple environments using the exact same image digest.
- [ ] Deployment configuration is reviewed and versioned in Git/IaC.
- [ ] Smoke tests, health probes, and startup validation are in place.
- [ ] Zero plaintext secrets exist in source, images, logs, Actuator, or CI output.
- [ ] Rotation and config/secret rollback plans are documented.
- [ ] Drift detection catches out-of-band changes outside pipelines.
- [ ] Live running config can be verified against deployment records.

## Conclusion

Standardizing Java configuration across GCP environments lets teams ship one tested artifact while isolating each environment's projects, identities, endpoints, quotas, and secrets. Spring Boot externalized configuration and `@ConfigurationProperties` provide a typed, validated, testable configuration layer. Cloud Run and GKE supply environment variables and runtime identities, while Secret Manager keeps secrets out of source code. By versioning deployment configurations, promoting by digest, validating at startup, and governing rollbacks and audits, organizations cut configuration mistakes and strengthen CI/CD reliability.

## References

- [Spring Boot: Externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot: Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot: Type-safe configuration properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Google Cloud: Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Cloud Run: Environment variables](https://docs.cloud.google.com/run/docs/configuring/services/environment-variables)
- [Cloud Run: Configure secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Cloud Run: Service identity](https://docs.cloud.google.com/run/docs/securing/service-identity)
- [Secret Manager: Best practices](https://docs.cloud.google.com/secret-manager/docs/best-practices)
- [GKE: Workload Identity Federation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Kubernetes: ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes: Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Artifact Registry documentation](https://docs.cloud.google.com/artifact-registry/docs)
- [Cloud Run: Traffic splitting and revisions](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
