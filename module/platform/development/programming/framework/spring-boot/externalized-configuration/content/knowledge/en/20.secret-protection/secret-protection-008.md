# Rotating Secrets, Process Lifecycle, and Restart Planning

> **Topic:** Spring Boot Externalized Configuration  
> **Category:** Secret Protection

## 1. Why rotating a secret is not just changing a configuration value

A Spring Boot application often needs **secrets** to connect to protected resources: database passwords, API tokens, JWT signing keys, OAuth2 client secrets, TLS private keys, or message broker credentials. These values can be supplied via environment variables, mounted files, Kubernetes Secrets, secret managers, or Config Data mechanisms.

Example:

~~~yaml
partner:
  api:
    base-url: "https://partner.example.test"
    # Do not place real tokens here.
~~~

In a container, the token may come from an environment variable:

~~~text
PARTNER_API_TOKEN=<securely injected value>
~~~

Or from a mounted file:

~~~text
/run/secrets/partner.api.token
~~~

Suppose the token is rotated at 10:00. A critical question is: **will the running Java process automatically start using the new token?** The answer depends on how the secret is supplied and how the application reads it. There are three completely separate layers:

1. **The external secret source changes:** the secret management system, Kubernetes Secret, or mounted file is updated.
2. **The process sees the new value:** do environment variables, filesystem views, or secret clients reflect the change?
3. **Application components actually use the new value:** do `Environment`, `@ConfigurationProperties` beans, HTTP clients, connection pools, or authentication layers re-read/rebind/rebuild?

Succeeding at layer 1 **does not guarantee** success at layers 2 and 3. Therefore, a **rotation** plan must account for **process lifecycle**, **binding timing**, **simultaneous acceptance of old/new secrets**, and **restart strategy**.

### Lesson objectives

After this lesson, you will be able to:

- Distinguish secrets injected via environment from secrets mounted as files.
- Explain why `@ConfigurationProperties` is usually a snapshot of configuration at the time the bean was bound.
- Identify cases where mounted files can update while Java clients still hold old credentials.
- Design rotation workflows that avoid disrupting existing instances.
- Understand rolling restarts, graceful shutdown, and readiness in Kubernetes.
- Sequence provisioning new secrets, deploying updated apps, and revoking old secrets.
- Choose between controlled restarts and dynamic refresh when genuinely needed.
- Protect secrets in logs, diagnostic endpoints, manifests, shells, and pipelines.
- Write tests and runbooks to verify new secrets are used after restarts.

## 2. Where do secrets differ from ordinary configuration?

A property like `server.port` or `client.timeout` can be treated as non-sensitive configuration information. Secrets demand separate policies because **exposure** can directly grant access or allow identity impersonation.

Examples:

| Data group | Examples | Management approach |
| --- | --- | --- |
| Public configuration | timeouts, retry limits, non-sensitive hostnames | Config Data, env, files |
| Access secrets | database passwords, API tokens, OAuth client secrets | Secret manager, secure Secrets/volumes |
| Cryptographic keys | JWT signing keys, TLS private keys | KMS/HSM or appropriate key store |
| Expiring credentials | short-lived access tokens, expiring certificates | Automated issuance/renewal and lifecycle |
| Stateful data | refreshed tokens, authenticated connections | Dedicated runtime mechanisms, not just `@ConfigurationProperties` |

A secret often carries additional operational attributes:

- **Expiration date or validity window.**
- **Key version/identifier** for transitions.
- **Permission scope** (read, write, single service).
- **Provisioning source and rotation owner.**
- **Whether the server accepts multiple credentials concurrently.**
- **Impact of revoking the old credential.**

Thus, changing a password is not just editing a string in YAML. You must know which processes are using the old password, how to transition to the new one, and when it is safe to revoke the old value.

## 3. Configuration lifecycle inside a Spring Boot process

A generalized lifecycle:

~~~text
Container/VM receives configuration and secrets
                   |
                   v
             JVM starts running
                   |
                   v
    Spring prepares Environment
      - OS environment
      - system properties
      - Config Data, imports
      - mounted files, config tree if declared
                   |
                   v
      Bind @ConfigurationProperties
      + type conversion + validation
                   |
                   v
     Create beans and resource clients
      - DataSource / Hikari pool
      - HTTP client / authorization header
      - Kafka/Redis/MQ client
      - JWT signer / validator
                   |
                   v
        Application serves traffic
                   |
          Source secret changes?
                   |
       No default rebinding or
       rebuilding of clients
~~~

Some values may be looked up on every use, yet applications commonly store them in **singleton beans** or initialize a client/pool once. When that happens, the secret is copied into runtime structures.

Example:

~~~java
@ConfigurationProperties(prefix = "partner.api")
public record PartnerApiProperties(
        String token,
        String baseUrl
) {}
~~~

Once this bean is bound, `token()` holds the value in the object at that point in time. If an external file changes, the record **does not update its component automatically**. Even if another object reads the new file, the existing record bean still holds the old string.

**Safe operational principle:** for secret configuration bound at startup, assume you must **restart the process or have an explicitly designed refresh/reconstruction mechanism** to use the new secret.

### 3.1. Source configuration differs from secrets already used by clients

An HTTP client may build an interceptor:

~~~java
String header = "Bearer " + properties.token();
~~~

and retain `header` in memory. Even if `Environment` changes later, that interceptor keeps the old header unless the code is designed to update.

A database pool may have been initialized with the old password; already-established connections continue using authenticated sessions. Changing the password on the database does not automatically recreate all connections or supply the new password to the pool.

### 3.2. Refreshing Environment differs from rebuilding the whole system

Libraries/frameworks may exist to support refreshing beans or re-reading secrets. Yet **refreshing properties does not mean every client received the new value**:

- Constructors may run only once.
- Client builders may copy values into internal configuration.
- Connection pools may keep live connections and startup credentials.
- A token may be cached in another service.
- In-flight request threads may still be using old details.

Therefore, if dynamic refresh is desired, specify exactly which resources are updated and whether connections/clients must be recreated or thread access synchronized.

## 4. Secrets supplied via environment variables

A common approach is injecting environment variables into the process:

~~~bash
# Illustrative variable name example; contains no real secret.
PARTNER_API_TOKEN=<secret-value>
~~~

In Spring Boot:

~~~java
@ConfigurationProperties(prefix = "partner.api")
public record PartnerApiProperties(String token) {}
~~~

Per relaxed binding, `partner.api.token` can come from `PARTNER_API_TOKEN`.

### 4.1. A running process's environment does not update automatically when external Secrets change

If Kubernetes creates a container with environment variables populated from a Secret, values are supplied to the process when the container is created. **Updating the Kubernetes Secret afterward does not automatically change environment variables inside running containers.**

This is the most important point to avoid failed deployments: updating a Secret object in the cluster and observing that an old Pod still sends the old credential is not a Spring Boot Binder bug; that is how environment variable provisioning works.

With this model, **new Pods/containers** usually must be created to receive the new value. Restarting the process inside an environment whose env vars were not re-injected may also not be enough; ensure the orchestrator/container is recreated or the environment source is updated.

### 4.2. Limitations of environment variables for secrets

Advantages:

- Easy to integrate with `@ConfigurationProperties` and many libraries.
- No custom file-reading logic needed.
- Fits immutable-process deployments that restart on configuration changes.

Things to watch:

- Each running process retains its own environment snapshot.
- Diagnostic/process inspection tools can expose environment variables if permissions are misconfigured.
- May be accidentally printed in logs, crash dumps, support bundles, or debug endpoints.
- Short-lived secrets requiring continuous refresh may not suit static provisioning via environment.
- Editing a deployment's env source does not guarantee current Pods are replaced unless the template/rollout triggers properly.

Do not treat env vars as "secret encryption." They are **a value-transport mechanism**, and still require access control and lifecycle management.

## 5. Secrets supplied via mounted files

Instead of environment variables, secrets can be mounted as files:

~~~text
/run/secrets/partner.api.token
/run/secrets/database.password
~~~

Spring Boot supports Config Data imports in configuration-tree style:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Then filenames beneath the configuration root become property names, while **file contents** become values. For instance, if `partner.api.token` contains the token, a `@ConfigurationProperties(prefix="partner.api")` bean can bind the corresponding value.

### 5.1. Why are mounted files used?

- Secrets can be supplied via volumes instead of entering the environment.
- File read permissions can be restricted by user/group and workload settings.
- With standard Kubernetes Secret volumes, mounted contents can update after the Secret object changes.
- Suitable for certificate chains, private keys, or data unsuitable for cramming into a plain environment variable.

However, "the file updated" **does not equal** "the Java bean updated."

### 5.2. Kubernetes Secret volumes can update, though not instantaneously

When a Secret is mounted as a regular volume, Kubernetes has a mechanism to update volume contents after the Secret changes. Propagation is **eventual**; do not expect millisecond timing or simultaneous updates across all Pods.

Two important exceptions:

- If a Secret is supplied via **environment variables**, running containers do not receive updates automatically.
- If mounted using **`subPath`**, Kubernetes does not automatically propagate Secret updates via the regular volume mechanism.

In addition, whether the application picks up the change still depends on actually re-reading the file and reloading the resource.

### 5.3. Config Tree configuration is not an automatic file watcher

Example:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Only declares the **Config Data loading mechanism at startup**. It does not mean Spring Boot watches all files and rebinds every `@ConfigurationProperties` bean whenever a file is modified.

Even after Kubernetes updates volume contents, the application still requires a restart or an intentional reload/refresh mechanism.

### 5.4. Do not treat secret files like log files or temp data

Secret volumes need restricted permissions and must not be copied into public directories, image layers, or logs. If code reads files using `Files.readString`, consider:

- Read permissions at runtime.
- Whether trailing newlines are significant to the credential.
- Encoding of text-based secrets.
- Timing of file updates.
- Handling files being modified or atomically replaced.
- Which clients must be recreated after reading the new value.

Do not blindly call `trim()` on secrets: stripping whitespace or newlines can alter valid tokens. Secret formats must be explicitly defined.

## 6. Comparison table of three secret-supply approaches

| Supply method | Does running process automatically see source changes? | Do beans/clients automatically use new values? | Safe default measure |
| --- | --- | --- | --- |
| Environment variable from Secret | **Does not** auto-change in running container | **No** | Create new Pod/container |
| Regular Secret volume mount | File may update after a delay | **Not by default** | Designed restart or reload |
| Secret volume via `subPath` | No automatic updates like regular mounts | **Not by default** | Recreate Pod/mount |
| Externalized file edited by operator | Filesystem can change | **Not by default** | Controlled restart or refresh |
| Secret manager SDK queried on demand | Can fetch new version per SDK/cache policy | Depends on client and integration | Design TTL, caching, retries, and rotation |
| Short-lived token refreshed by client | Client can renew per protocol | If client supports it properly | Monitor expiry, refresh, and errors |

This table describes **default behavior and common patterns**, without claiming every Spring library or integration behaves identically. If an application has a custom hot-reload mechanism, inspect that exact implementation.

## 7. Rotation planning: four basic phases

A resilient rotation process usually has four phases:

~~~text
1. PREPARE
   Create new secret and establish transition support
                   |
                   v
2. DISTRIBUTE
   Provision new secret to deploy source / secret manager
                   |
                   v
3. ACTIVATE
   Restart/rollout or refresh instances;
   verify traffic actually uses new credential
                   |
                   v
4. REVOKE
   Revoke old secret once no consumers remain
                   |
                   v
             MONITOR & CLOSE
~~~

### 7.1. PREPARE: understand both client and server sides

Before rotating a secret, answer:

- Does the service provider allow **two credentials to coexist**?
- Does the old secret have a specific final deadline?
- How many deployments, jobs, cron jobs, workers, and instances use the secret?
- Are clients receiving tokens via env, volumes, custom files, or SDK?
- Is rolling restart available, or is downtime required?
- How long does it take to replace one instance?
- Are there long-lived connections or in-flight transactions?
- Can we roll back from the new version to the old one if needed?
- Are there logs/metrics confirming the new credential works without disclosing its value?

You cannot choose the right rotation sequence without knowing **both ends of authentication**. For example, a server allowing two parallel API keys makes transition much easier than a database allowing only instant password replacement on the same account.

### 7.2. DISTRIBUTE: provision the new secret without putting it in public places

Issue secrets using approved infrastructure, such as a secret manager or Kubernetes Secret. Avoid:

- Committing secrets to Git.
- Putting real values in example docs or tickets.
- Pasting secrets into public chat channels.
- Using command lines where secrets appear in process arguments and shell history.
- Putting secrets into Dockerfile `ENV` or build args that leak into image layers/history.
- Printing secret values to logs to "be sure it changed."

Assign clear ownership for issuance, clear permission scopes, and a **non-sensitive** version ID for correlation.

### 7.3. ACTIVATE: make processes use the new version

If the application binds secrets at startup, **recreate instances**. In Kubernetes, that is usually a rolling rollout based on an updated Pod template or a controlled restart operation.

Do not declare success simply because the Kubernetes Secret object updated. Verify new Pods were created, became ready, and connected successfully with the new credential.

### 7.4. REVOKE: revoke the old version only when no consumers remain

Revoking too early can cause un-restarted Pods or running batch jobs to lose access. Revoking too late widens the window in which an old credential remains valid.

A transition window should be sized by: concurrent old/new secret support, rollout duration, job/connection lifetimes, and maximum transaction or token duration.

Only after all consumers have switched and operational evidence confirms it should the old secret be revoked per plan. Keeping old secrets active indefinitely "to make rollback easy" is not complete rotation.

## 8. Two-phase rotation: accepting old and new before removing old

To avoid downtime, use an **overlap** model (if supported by the authentication system):

~~~text
T0: Server accepts only OLD
T1: Server accepts OLD + NEW
T2: Provision NEW to applications
T3: Rolling restart instances
T4: Verify all instances use NEW
T5: Server accepts only NEW, revoke OLD
~~~

### 8.1. API keys may support concurrent validity

An API provider may issue multiple active keys simultaneously. In that situation:

1. Issue a new key from the provider system.
2. Put the new key into the secret store.
3. Roll out the application to use the new key.
4. Monitor request success/authentication failures.
5. Verify no consumers remain on the old key.
6. Revoke the old key.

This is usually the simplest rotation path because **old and new clients both work during the transition window**.

### 8.2. When the provider allows only one password at a time

If changing the password invalidates the old password immediately, a rolling restart can create an interval where:

- Old instances use the old credential and get rejected.
- New instances have the new credential and work.
- Existing connections stay open, yet reconnects can fail.

Different approaches are needed depending on the system: creating parallel accounts with least privilege, migrating consumers one by one, using a credential manager supporting multiple versions, or accepting a scheduled maintenance window.

**There is no single zero-downtime recipe for every authentication mechanism.** Server-side overlap support is the foundational prerequisite.

### 8.3. JWT signing keys differ from API tokens

With JWTs, a system can **sign new tokens with a new key** while continuing to **verify older tokens with the old key** until they expire. You can use `kid` in token headers and a key set to select the right verification key.

The typical sequence is:

1. Publish the new public verification key or inform validators of the new key.
2. Switch signers to sign with the new private key.
3. Retain the old public/verification key for the valid lifetime of old tokens plus allowed clock skew.
4. Retire the old key from the verification set after the transition period.

Do not blindly apply a "change one secret string and restart everything" model to live tokens or key pairs. Key distribution and verification semantics must be designed carefully.

## 9. Spring Boot `@ConfigurationProperties` and secret validation

Example configuration record for a partner integration:

~~~java
package com.example.partner.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "partner.api")
@Validated
public record PartnerApiProperties(
        @NotNull URI baseUrl,
        @NotBlank String token,
        @NotNull Duration timeout
) {}
~~~

Bean registration:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PartnerApplication {}
~~~

With Maven, add the validation dependency when needed:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

### 9.1. Validation checks secret existence, not whether it is still valid

`@NotBlank` catches missing or whitespace-only tokens at startup. However, it cannot confirm the provider will accept the token, that the token is unexpired, or that its permissions are right.

Separate:

- **Syntax and presence**: binding/Bean Validation.
- **Actual authentication capability**: a safe call, connectivity check, or metric.
- **Rotation lifecycle**: issuance, distribution, activation, revocation.
- **Permissions and security**: least privilege, no value disclosure.

### 9.2. Do not log records containing secrets

Records automatically have `toString()` and can print `token`. Do not do:

~~~java
logger.info("Partner config: {}", properties); // Unsafe.
~~~

With a **non-sensitive** version code or key identifier, you can log:

~~~java
logger.info("Partner credential configuration loaded");
~~~

If you need to identify which secret version is active, use a **dedicated non-authenticating secret version ID** issued by the system, or an observable indicator permitted by security policy. Never arbitrarily print tokens or hashes into logs; hashes of short/guessable credentials can also pose risks.

### 9.3. Do not create secret defaults

Do not write:

~~~java
@DefaultValue("test-secret")
String token
~~~

and share it across all environments. A public or guessable secret default weakens security. For required secrets, require a secure source to supply them and fail fast if missing.

## 10. Kubernetes: Secrets via environment variables

Example Deployment using values from an existing Secret named `partner-api-credentials`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: partner-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: partner-service
  template:
    metadata:
      labels:
        app: partner-service
    spec:
      containers:
        - name: app
          image: example/partner-service:1.0
          env:
            - name: PARTNER_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: partner-api-credentials
                  key: token
~~~

Newly created containers receive the value of the `token` key via secret injection.

### 10.1. What happens after the Secret object changes

Suppose the Secret in the cluster is updated through an approved governance workflow. The Deployment spec still references the same Secret name. **Running** containers continue holding the old environment variable.

Without a change causing the Pod template to trigger a new rollout, updating only the Secret may not cause the Deployment to create new Pods. A **controlled rollout/restart trigger** or Pod template change is needed per your deployment tooling.

### 10.2. Rolling restart example

In an authorized operational environment:

~~~bash
kubectl rollout restart deployment/partner-service \
  --namespace production
~~~

Then monitor:

~~~bash
kubectl rollout status deployment/partner-service \
  --namespace production
~~~

These are operational examples **to be run only with proper authority and an approved change plan**. Never test this command on production just to learn. It replaces Pods according to the Deployment strategy; rollout status must be verified.

### 10.3. What does restart mean here?

`kubectl rollout restart` tells the Deployment to initiate a new rollout by modifying a Pod template annotation. New Pods are created and their environments are re-injected from the current Secret.

It does **not** mean all old Pods vanish at once, nor does it guarantee zero downtime if replicas, readiness probes, cluster resources, or rolling strategies are poorly designed.

## 11. Kubernetes: Secrets via volumes and `configtree`

Example Secret mounted at `/run/secrets`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: partner-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: partner-service
  template:
    metadata:
      labels:
        app: partner-service
    spec:
      containers:
        - name: app
          image: example/partner-service:1.0
          volumeMounts:
            - name: partner-secrets
              mountPath: /run/secrets
              readOnly: true
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "optional:configtree:/run/secrets/"
      volumes:
        - name: partner-secrets
          secret:
            secretName: partner-config-files
~~~

For Spring Boot to bind `partner.api.token` via Config Tree, filenames under the mount must match the key to load (for example, Secret data key `partner.api.token` creates a file of the same name). This differs from `secretKeyRef` environment variables, where you actively map key `token` into `PARTNER_API_TOKEN`.

### 11.1. Files on the volume can change

When `partner-config-files` changes, Kubernetes can update the Secret volume contents after a delay. A process re-reading the file at the right moment can receive the new value.

Yet code using `PartnerApiProperties.token()` bound at startup usually **keeps the old token**. That means:

~~~text
New Kubernetes Secret       : YES
Mount file in new Pod       : YES
Mount file in old Pod       : MAYBE, after a delay
Record bound at startup     : DOES NOT AUTO-CHANGE
Already-initialized client  : DOES NOT AUTO-CHANGE
~~~

### 11.2. `SubPath` and update limitations

If mounting a Secret via `subPath`, Kubernetes does not update Secret contents automatically like regular mounts. In rotation workflows, do not rely on a `subPath` file for hot reload without a mechanism replacing the Pod/mount.

### 11.3. Avoid mounting unnecessary sensitive files

If a single Secret contains many keys, mounting the whole volume can give a container more files than it needs. Apply least privilege across Secret objects, namespaces, ServiceAccounts, and granted keys. Kubernetes Secret objects also require RBAC, at-rest encryption, and appropriate governance policies.

## 12. Designing rolling restarts to minimize downtime

Suppose a Deployment has multiple replicas serving traffic. The rotation goal is replacing Pods one by one without losing availability.

Example:

~~~yaml
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
~~~

Meaning:

- `replicas: 4`: desired replica count.
- `maxUnavailable: 0`: aims not to reduce ready Pods below the required level during rollout.
- `maxSurge: 1`: can create at most one extra Pod above the desired count during replacement.

This is a **policy supporting** availability maintenance, not an absolute guarantee. If the cluster lacks resources to schedule a new Pod, the rollout can stall. If readiness turns green too early or the application handles shutdown poorly, users can still see errors.

### 12.1. Readiness probe

An application should be marked ready only when qualified to receive traffic. For example, Spring Boot Actuator can provide a readiness health group when properly configured:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Illustrative manifest:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

Use this path and port only when the application actually includes Actuator, the health endpoint is ready, and network routing matches. Never assume every Boot app opens the exact same endpoint.

A good readiness probe reflects essential serving capability without causing excessive network connections or indirect restart loops.

### 12.2. Graceful shutdown

When an old Pod is asked to stop, give in-flight requests/transactions a chance to finish.

In Spring Boot on supported web servers, configure:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

At the same time, configure the Pod's `terminationGracePeriodSeconds` to cover the time the application needs to finish shutting down:

~~~yaml
spec:
  terminationGracePeriodSeconds: 45
~~~

Values are illustrative only. Actual grace periods must account for latency, long requests, batch processing, how the server stops accepting new connections, any `preStop` hooks, and queue workers' ability to stop safely.

### 12.3. Do not disable old credentials immediately while old Pods remain

During a rolling update, there is a period when both old and new Pods run concurrently. If the old credential is revoked at the start of the rollout while old Pods still receive traffic, requests hitting old Pods can fail.

Therefore, for near-zero-downtime rotation, **the server-side authentication service must permit an overlap period**, or the system must plan for a brief disruption.

## 13. Database password rotation and connection pools

Databases add the issue of long-lived connections. For example, an application using Spring DataSource and HikariCP, where the password is configured for the pool at startup.

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://db.internal:5432/orders"
    username: "orders_app"
    # Password supplied by a secure secret source.
~~~

If the password of account `orders_app` is changed in the database:

- Already-authenticated connections may keep working depending on DB/protocol and server policy.
- When the pool opens new connections, the old password may be rejected.
- Changing only the Pod's environment variables or Secret volume does not automatically update all pool parameters.
- Some pools/clients have APIs to update credentials, yet recreating/recycling connections must be explicitly designed.

### 13.1. Simple approach: restart instances once the new credential is valid

If multiple accounts/credentials with identical permissions and overlap are supported:

1. Create a new user/credential with least-privilege permissions needed.
2. Verify the new credential connects to the right database and scope.
3. Supply the new credential to the Secret.
4. Rolling restart the service.
5. Check new connection success rate, pool metrics, and main read/write flows.
6. Revoke the old credential after no consumers remain.

### 13.2. If only one active password is allowed

If the DB does not allow old/new secrets for the same identity simultaneously, options may include:

- A scheduled maintenance window.
- Using parallel users during migration.
- Credential rotation integration supported by the DB/provider.
- Bounded reconnect/retry policies and communicating downtime if any.

Never promise zero downtime for every database via `kubectl rollout restart` alone.

### 13.3. Background jobs and cron jobs are easily overlooked

A web Deployment may have switched to the new credential, yet there remain:

- Scheduled CronJobs.
- Queue consumers in another Deployment.
- Long-running batch jobs.
- Admin/migration tools.
- Reporting or audit services sharing the same account.

If the old secret is revoked too early, those components can fail on their next connection. A complete consumer inventory is an essential part of a rotation runbook.

## 14. Secret managers and dynamic refresh

Some organizations use an external secret manager to issue credentials and rotate by version. There may be direct SDKs or integration with Spring Boot Config Data/`PropertySource`.

Distinguish two designs:

### 14.1. Load-on-startup

The application loads secrets at startup and holds them in beans. If the secret manager gets a new version, the application normally must restart or use a rebind mechanism to receive the new version.

This model is easy to control, especially with immutable processes in containers.

### 14.2. Fetch-on-demand or auto-refresh

Clients call the secret manager on demand or maintain a TTL cache. Issues to solve:

- Cache lifetime and rate limits to the secret manager.
- Refresh-before-expiry rules.
- Network connectivity and secret manager outages.
- Backoff when refresh fails.
- Concurrent version switching across threads.
- Recreating clients/connections using the old secret.
- Fallback behavior during transition windows.
- Logging/metrics levels that do not disclose credentials.

Example interface design:

~~~java
public interface CredentialSupplier {
    String currentToken();
}
~~~

An HTTP interceptor can call `currentToken()` per request instead of keeping the token in a field initialized once. However, this is only an **API pattern**, not a complete rotation implementation. Caching, synchronization, authentication, timeouts, secret zeroization where feasible, and error conditions are still needed.

### 14.3. Skip hot reload if restart is safer

Dynamic refresh increases complexity: multiple beans may see different secret versions, connection pools may hold old credentials, and concurrent refreshes can cause race conditions. If the application already runs multiple replicas, a rolling restart with readiness/graceful shutdown is usually **easier to verify** for secrets with sufficiently long lifetimes.

Add hot reload only when business goals demand it or when a secret type has such a short lifetime that restarting each time makes no sense.

## 15. Why `@RefreshScope` does not solve everything

Ecosystems such as Spring Cloud provide context/bean refresh mechanisms. However, `@RefreshScope` **is not** a default feature of plain Spring Boot, and its presence does not guarantee every client gets updated.

For example, if a singleton HTTP client sits outside refresh scope, it may still keep an authorization header built with the old token. Or a database pool may keep old connections even after the properties bean rebound.

When designing refresh:

1. Identify which components must be updated.
2. Identify where secrets are cached.
3. Ensure refreshes occur safely between requests.
4. Define closing/recreating connections or clients.
5. Never leave refresh endpoints unprotected.
6. Test against your exact secret/provider type and framework version.

Avoid exposing secrets via Actuator `env`, `configprops`, or custom endpoints. If management features are enabled, apply authentication, authorization, network restrictions, and redaction.

## 16. Secret governance: permissions and versions

Rotation is a security workflow, so controls outside code are also required.

### 16.1. Least privilege

Each service should read only the secrets it genuinely needs. Never grant broad permissions to read all secrets in a namespace/project just for deployment convenience. Secret manager policies and Kubernetes RBAC must match workload scope.

### 16.2. Encryption and data transmission

Secrets should be encrypted at rest per platform capabilities, transmitted over protected channels, and kept out of logs/monitoring in raw form. Kubernetes Secrets use base64 representation in the API; **base64 is not encryption** and does not replace encryption at rest or access controls.

### 16.3. Secret versions and audit trails

Know which version is provisioned to each environment, who approved changes, and when revocation occurs. You can use a non-sensitive metadata/version ID for correlation in deployments. Avoid printing raw values or easily reversible hashes of secrets into deployment annotations or logs.

### 16.4. Avoid coupling secret lifecycles to build artifacts

A good model avoids embedding real credentials inside JARs or Docker images. An image should be deployable across multiple environments, with secrets coming from infrastructure at runtime.

This allows rotating passwords without rebuilding code and reduces the risk of credential exposure in artifact registries.

## 17. Restart planning when an application has only one instance

Not every service runs multiple replicas. If there is only a single instance:

- Restarting may create a brief outage.
- An announced maintenance window may be required.
- Confirm in-flight jobs and data are not lost.
- Save checkpoint state or support retries/idempotency.
- Have a safe rollback plan if the new credential fails.

For queue-processing services, stop accepting new messages, wait for in-flight messages to finish or return them to the queue per broker semantics, then restart and resume.

For a single-replica HTTP application, blue-green deployment or staging a parallel instance can be used if infrastructure allows, yet do not claim zero downtime without readiness, routing, and concurrent old/new secret support.

## 18. Sample runbook for rotating an API token on Kubernetes

**Scope:** a multi-replica Spring Boot Deployment, token supplied via `secretKeyRef` environment variable and bound at startup.

### 18.1. Before starting

- [ ] Identify owner and rotation deadline.
- [ ] List all consumers of the token.
- [ ] Confirm the provider supports two tokens simultaneously.
- [ ] Confirm replica count, rolling strategy, readiness, and graceful shutdown.
- [ ] Confirm authority to update the Secret/Deployment per change management process.
- [ ] Prepare success criteria and rollback plan.
- [ ] Verify no raw secret values appear in logs/dashboards.
- [ ] Ensure visibility into request success, 401/403, latency, and errors.

### 18.2. Issue the new token

Issue the new token via the provider. Do not revoke the old token at this step. Test the new token with a safe call in an approved environment or tool without exposing the token to terminal history.

### 18.3. Update the Secret store

Use an approved governance/CI mechanism to update `partner-api-credentials`. Never put real tokens in docs or example manifests.

If using GitOps with an external-secrets controller, distinguish updating the secret in the backend, the controller syncing the Kubernetes Secret, and triggering the new rollout. Each step has its own status and delay.

### 18.4. Trigger rollout

Once data has been distributed to the right Secret:

~~~bash
kubectl rollout restart deployment/partner-service \
  --namespace production
~~~

Then:

~~~bash
kubectl rollout status deployment/partner-service \
  --namespace production
~~~

Commands are illustrative operational steps for authorized personnel in the right environment. Monitor new Pods, readiness, and ready replica counts.

### 18.5. Confirm the application uses the new token

Never log raw tokens. Confirm by:

- HTTP 2xx/401/403 rates on the application side.
- Provider audit logs for credential version or key ID (if supported).
- Readiness status and remaining old Pod count.
- Running a safe business check request through the new service.
- Zero authentication errors across a defined observation window.

**Seeing rollout status succeed is not enough**, if new clients could still be using an old token fetched from the wrong Secret, wrong namespace, or cached in another source.

### 18.6. Revoke the old token

Once certain all consumers have transitioned and no batch jobs use the old token, revoke the old token per the agreed window. Monitor 401/403 rates and late-running jobs after revocation.

### 18.7. Handling rollback

Rollback is not always just `kubectl rollout undo`. If the old token has already been revoked, restoring the old image/Pod template may restore code yet **not restore authentication**. Rollback runbooks must include provider-side secret status and the ability to re-issue a valid version.

When possible, keep the old token active throughout the rollout and rollback confirmation window before revoking.

## 19. When to revoke immediately without waiting for a clean rollout?

When a secret is suspected of **having leaked or been exploited**, security priority can override planned rotation workflows. It may be necessary to revoke credentials immediately to block unauthorized access even if that causes temporary disruption.

In an incident situation:

1. Activate incident response per organizational policy.
2. Limit credential blast radius and contain scope.
3. Safely issue/rotate credentials.
4. Revoke or disable compromised secrets per risk level.
5. Restart/reconfigure consumers as quickly as possible.
6. Inspect audit logs, permissions, signs of abuse, and related resources.
7. Fix the root cause of the leak, not just swap the string.
8. Record timestamps, decisions, and post-incident review.

Never keep a **compromised** credential active too long just for zero downtime. Planned rotation and emergency revocation have different priorities.

## 20. Testing: verifying behavior instead of assuming

A testing strategy should cover both configuration and deployment lifecycle.

### 20.1. Testing startup validation

With `PartnerApiProperties` having `@NotBlank token`:

- When `token` has a value and other fields are valid, the bean binds.
- When `token` is completely missing, the context must fail if validation is properly configured.
- When `token` is empty or whitespace-only, validation must reject it.

This checks **configuration presence**, not whether the remote provider accepts the token.

### 20.2. Testing that the application retains initial values

In a controlled integration test:

1. Supply a test token A through configuration.
2. Initialize the context and read the property from the bean.
3. Update the source file to test token B.
4. Observe the bound bean normally still holds A when no refresh mechanism exists.
5. Restart the context with source B and confirm the new bean receives B.

Tests should use fake tokens and mock/stub systems, never production credentials.

### 20.3. Testing Kubernetes env injection

In a sandbox environment:

1. Create a fake Secret with key `token=A`.
2. Create a sample Pod receiving env from the Secret.
3. Change the Secret to `token=B`.
4. Verify the existing Pod still has the initially injected env value (no need to print the token; have the app check a separate version ID).
5. Create a new Pod and verify it receives the updated value.

The takeaway is distinguishing the **Secret object source** from the **process environment**.

### 20.4. Testing volume mounts and Config Tree

With a file-mounted Secret, test across two layers:

- Expect the filesystem volume to update eventually under matching Kubernetes conditions.
- Expect already-bound `@ConfigurationProperties` **not to change automatically** without refresh.
- When using `subPath`, do not expect automatic updates like regular mounts.
- After restart, beans rebind from current file contents.

Use non-sensitive version IDs or fake tokens to verify, avoiding logging real secrets.

### 20.5. Testing rolling restarts and rollbacks

Set up a small multi-replica model with readiness configured. During rollout with a new secret:

- New Pods become ready only after passing required checks.
- Old Pods have drain time.
- Ensure zero authentication errors during old/new overlap.
- Test the case where a replica fails binding and stalls the rollout.
- Rehearse rolling back both code and secret provider state.

## 21. Common mistakes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Secret object changes yet Spring still uses old value | Bean/HTTP client bound at startup | Restart or design refresh/reconstruction |
| Env var inside Pod does not change | Env injection does not update running processes | Create new Pod/container |
| Mounted file changes yet client sends old token | Client caches token/connection | Rebuild client or restart |
| File mounted via `subPath` does not update | Secret mount update limitation | Recreate Pod or change mount style |
| Restarted Pod yet token is still old | Secret not synced, wrong name/namespace/key, other higher-precedence source | Check mapping/precedence and version |
| Rollout reports success yet 401s occur | New client uses wrong secret, provider rejects, or old consumers remain | Check auth metrics and provider audit |
| Database pool errors after password change | Pool opens new connections with old credential | Recreate/update pool or controlled restart |
| Revoking old key breaks batch jobs | Job/cron worker had not switched | Inventory all consumers, allow overlap |
| Rollout stalls | New Pod fails readiness or cluster lacks resources | Check readiness, quotas, image, startup errors |
| Code rollback fails to recover | Old credential was already revoked | Rollback plan must include credentials |
| Secret leaks in logs | Printed record/Environment or debug headers | Remove raw value logs, control Actuator |
| GitOps updates yet Pods do not restart | Secret sync does not change Pod template | Trigger rollout per approved strategy |
| Keeping both keys indefinitely | No revocation step/clear owner | Set deadlines and verify consumers |
| Hot reload causes random errors | Unsynchronized rebind, old client not recreated | Test concurrency or switch to restart |

## 22. A decision flowchart for your next secret rotation

~~~text
New secret created
         |
         v
Can old and new secrets both be valid?
    |                       |
   Yes                     No
    |                       |
    v                       v
Enable overlap          Is parallel migration or
and schedule rollout    maintenance possible?
    |                       |
    v                       v
Does app read secret at startup?
    |                       |
   Yes                     No
    |                       |
    v                       v
Rolling restart         Is refresh mechanism
or create new Pods      thoroughly tested?
    |                       |
    v                       v
Check readiness,        Reload/rebuild clients,
auth, and jobs          verify consistency
         \                  /
          \                /
           v              v
       Have all consumers switched?
                   |
          No ------+------ Yes
           |                |
           v                v
      Continue          Revoke old secret
      monitoring        and monitor post-cutover
~~~

This flowchart guides decisions rather than replacing each provider's security/protocol design. For potentially compromised credentials, emergency policy may require immediate revocation instead of following the overlap path.

## 23. Practice exercises

### Exercise A — Observing the secret snapshot

Write a `@ConfigurationProperties(prefix="lesson.auth")` record containing a token and register it with `@ConfigurationPropertiesScan`. Start with fake token A. Edit the external config file to B while the app is running. Explain why the record bean can still hold A; restart to pick up B.

### Exercise B — Environment vs. volume

In a Kubernetes sandbox, create a fake Secret and supply it via both `secretKeyRef` environment and volume mount. Update the Secret. Observe the difference between env and file contents without printing real credentials.

### Exercise C — `@ConfigurationProperties` with Config Tree

Create `/run/secrets/lesson.auth.token` in a test environment, and declare:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Bind `lesson.auth.token` into a record with `@NotBlank`. Test missing file and empty file cases. Observe when validation blocks startup.

### Exercise D — Planning API key rotation

Suppose the provider allows two keys simultaneously and the service runs three Pods. Write a runbook in order: issue new key, update Secret, restart/rollout, monitor Pods and auth metrics, revoke old key. List conditions for a safe rollback.

### Exercise E — Database credentials

A service has a HikariCP pool and a batch job sharing the same DB account. Changing the password can break new connection attempts. Choose among parallel users, a maintenance window, or a DB-native rotation mechanism. Explain when to revoke the old account.

### Exercise F — JWT signing keys

Design how to rotate JWT signing keys while still verifying old tokens until they expire. Specify the order of distributing verification keys, switching the signer, and retiring the old key.

### Exercise G — Rolling restart

For a Deployment with `replicas=4`, `maxUnavailable=0`, and `maxSurge=1`, describe conditions for a safe rollout. Explain why readiness, spare cluster capacity, and graceful shutdown are still needed.

### Exercise H — Emergency revocation

Suppose a token leaked in CI logs. Identify steps that differ from planned rotation: limiting permissions, revoking, issuing new credentials, restarting workloads, and checking audits. Do not keep the old token valid just to avoid disruption while ignoring risk.

## 24. Checklist for production rotation

- [ ] Inventoried all consumers of the secret.
- [ ] Know whether the secret is supplied via env, file, Config Tree, or secret manager SDK.
- [ ] Know when existing beans/clients initialize and retain credentials.
- [ ] Verified the new secret works on the provider side before revoking the old one.
- [ ] Overlap window or maintenance plan established.
- [ ] Secret store updated through a secure procedure.
- [ ] Distinguished Secret object updates from Pod rollouts.
- [ ] Chose a controlled restart/rollout trigger.
- [ ] Readiness and graceful shutdown match workload behavior.
- [ ] Sufficient cluster capacity for rollout per `maxSurge`.
- [ ] Metrics exist for authentication failures, latency, and success rates.
- [ ] Way to verify secret version **without disclosing values**.
- [ ] Checked CronJobs, batch workers, and consumers outside the web Deployment.
- [ ] Rollback plan covers credentials and provider state.
- [ ] Scheduled timing/tooling to revoke the old secret.
- [ ] Old secret is not left active indefinitely.
- [ ] Checked logs, Actuator, and Secret access permissions.
- [ ] Distinguished planned rotation from emergency incident response.
- [ ] Recorded owner, timestamps, outcome, and post-review.

## 25. Takeaways

1. **Changing the source Secret does not mean running applications use the new Secret.** Account for three layers: secret store, process view, and runtime beans/clients.
2. With **environment variables**, running Pods/containers do not automatically receive updated Kubernetes Secret values; new Pods/containers must be created.
3. With **Secret volumes**, files may update eventually, yet bound `@ConfigurationProperties` and clients do not auto-refresh; `subPath` mounts also have separate update limitations.
4. **Rolling restarts** support safe transitions when having multiple replicas, readiness, graceful shutdown, and enough capacity, yet do not guarantee zero downtime in every situation.
5. **Overlapping old/new credentials** are key to disruption-free rotation when supported by the provider. Revoke the old secret after all consumers have transitioned.
6. **Stateful connection pools and clients** can keep using old credentials even after sources change. Controlled restarts/rebuilds or tested specialized refreshes are needed.
7. **Startup validation** verifies a secret was supplied and has basic valid shape, without proving the provider still accepts the token.
8. **Rolling back code does not necessarily roll back credentials**. Runbooks must cover secret provider state and revocation timing.
9. **Never log secret values**, embed them in images/Git, or treat base64 as encryption.
10. When a secret is compromised, **prioritize incident response and risk-based revocation**, rather than mechanically following a planned rotation schedule.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, Config Data, configtree imports, and precedence.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): record binding and validation.
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): stopping request acceptance and shutdown timeouts.
- [Spring Boot Actuator — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): readiness/liveness and caveats.
- [Kubernetes — Secret](https://kubernetes.io/docs/concepts/configuration/secret/): supplying secrets via environment and volumes, updating mounted Secrets, and `subPath`.
- [Kubernetes — Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rolling updates and rollout strategies.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): termination, graceful shutdown, and Pod lifecycle.
- [Kubernetes — Encrypting Secret Data at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/): encryption considerations when storing Kubernetes Secrets.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lifecycle-based secret management and rotation.
