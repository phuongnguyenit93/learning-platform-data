# Managing Client Secrets, Keys, and Passwords with Externalized Security Configuration (Spring Security Reactive)

> **Context:** Deploying Spring Boot WebFlux/Spring Security applications across development, CI, staging, and production environments. This lesson explains how to keep OAuth2 client secrets, service connection passwords, TLS/signing keys, and credentials out of source code, JARs, container images, and committed configuration files. The values in the examples are only variable names, paths, or dummy test data; they do not contain real operational credentials.

## 1. Objectives and Core Principles

After this lesson, you will know how to:

1. Distinguish secrets that must be **read back in plaintext** from user passwords that only need **one-way matching**; choose an appropriate storage mechanism for each type.
2. Use Spring Boot Externalized Configuration, environment variables, `spring.config.import`, and `configtree:` to load secrets into a reactive application.
3. Wire external configuration to `spring.security.oauth2.client.registration.<id>.client-secret` without hardcoding values in `application.yml`.
4. Mount secrets from Kubernetes/a secret manager into a Pod in a controlled manner; understand the limitations of Kubernetes Secrets, environment variables, and secret updates.
5. Manage private keys, TLS certificates, and keystore passwords; separate the authorization server's signing key from the public key that the resource server uses for verification.
6. Design authorization, access auditing, configuration testing, secret rotation, and revocation, reducing the risk of leaks through Git, images, logs, Actuator, and CI.

**Foundational rule:** Source code only declares *configuration key names* or *paths to the secret source*. The source providing real values resides at runtime/deployment and is provisioned separately per environment. Hiding values from Git does not mean a secret is safe: its storage location, transport path, read permissions, logs, and lifecycle must also be protected.

## 2. What Counts as a Secret and How to Handle It

| Data Type | Example in WebFlux | Proper Protection | Common Mistakes |
| --- | --- | --- | --- |
| OAuth2 confidential client secret | `spring.security.oauth2.client.registration.billing.client-secret` | Load from a controlled secret store/volume/env; authorize per application | Writing in YAML, baking into `ARG`/`ENV` in Dockerfile |
| DB/Redis/SMTP passwords, API keys | `spring.r2dbc.password`, service call keys | Provision at runtime, restrict TTL/scope, rotate | Printing to logs when debugging configuration |
| TLS private key, keystore password | `server.p12`, `server-key.pem` files, keystore password | Store separately in KMS/HSM or protected volume; restrict read permissions | Placing private keys into `src/main/resources` or images |
| JWT signing key | RSA/EC private key at the authorization server | HSM/KMS or secret store; separate signer and verifier | Copying the private key to all resource servers |
| Public key/JWKS, CA public certificate | `jwk-set-uri`, public trust certificate | Does not need secrecy, but must ensure authenticity and tamper resistance | Treating public keys like passwords or disabling TLS verification |
| User login password | User-entered password | Store a **salted adaptive hash** (bcrypt/Argon2/PBKDF2/scrypt) and match via `PasswordEncoder.matches` | Storing plaintext, rolling single-round SHA-256, or hashing client secrets that must be used verbatim |
| Access/refresh token | `OAuth2AuthorizedClient`, tokens used for WebClient | Protect at rest, in transit, and in logs; appropriate TTL/scope | Letting tokens appear in logs/traces or API responses |

**Critical distinctions:**

- User passwords for login verification: the system **does not need to recover the original password**. Use `PasswordEncoder`.
- Client secrets, DB passwords, API keys, private keys: the application usually **must present the original value** to an external system or use the value for signing. You cannot replace them with a one-way hash and expect connections to still work. Use a vault/KMS/secret store, or encryption with managed keys if they must be stored.
- `client-id` is generally an identifier that can be public in the protocol; **client-secret** is the value that requires protection. For public clients (SPA/mobile), there is no way to hide long-lived secrets in code running on a user's device; use an appropriate flow such as Authorization Code + PKCE instead of embedding a client secret.

## 3. Threat Model: Where Can Secrets Leak?

A secret can be copied before the application ever receives a request:

```text
Secret manager / KMS / Vault
          |
       (authorized by workload identity)
          |
 Deployment runtime: env / mounted volume / API provider
          |
 Spring Boot Environment + ConfigData
          |
 Config binding / OAuth2 ClientRegistration / SSL bundle
          |
 WebFlux runtime -> outbound calls via WebClient
```

Control points to enforce:

- **Repository and Git history:** adding to `.gitignore` after committing does not remove secrets from history. If leaked, you must **revoke/rotate** first, then scrub history.
- **CI/CD:** secrets can appear in job logs, command lines, artifacts, test reports, caches, Docker build args, or script output. Prefer workload identity/OIDC to obtain short-lived credentials instead of static cloud keys.
- **Container images:** secrets in `Dockerfile ENV`, `ARG`, `COPY`, or a layer deleted in a later layer can still be recovered from the image.
- **Process runtime:** environment variables can be inspected by container management systems, dump/debug tools, or privileged processes; mounted files can be read by unauthorized users/containers if mount mode/UID is misconfigured.
- **Spring configuration/observability:** do not echo `Environment`, `ClientRegistration`, exceptions containing URLs with userinfo, Authorization headers, or the contents of `/actuator/env` and `/actuator/configprops`.
- **Network:** transmit secrets to IdP/DB/KMS over TLS with a proper trust chain; never disable hostname/certificate verification as a "quick fix".
- **Backups:** secrets persist in snapshots, old revisions, Git, logs, crash dumps, or backups after rotation; destruction policies must also cover copies.

A secret that is "encrypted at rest" when anyone can read the decryption key fails the security goal. **Identity + least privilege + audit + rotation** must accompany encryption.

## 4. Spring Boot Externalized Configuration Mechanism

Spring Boot aggregates configuration sources into `Environment`, then binds them to beans via `@ConfigurationProperties`, `@Value`, or auto-configuration. Sources can be:

- `application.yml`/**profiles**: define property names, endpoint addresses, runtime modes, and references to secrets.
- **Environment variables** provided by the runtime: suitable for simple deployments, but carry exposure risks via process/deployment metadata.
- **External files outside the JAR** or **config trees**: especially well suited for Kubernetes and Docker secret volumes.
- **Secret management systems** (HashiCorp Vault, cloud secret managers, KMS/HSM): provide authenticated access, versioning, revocation, auditing, and often automated rotation.
- **Command-line/system properties**: can override configuration, but **avoid passing secrets directly** because command lines/logs/process listings can be observed.

With sources of varying precedence, a later configuration source can override an earlier one. Check the official property source order for the exact Boot version running; do not guess where a secret comes from based solely on profile names.

### 4.1. Placeholders Without Secret Values

Example in `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: reactive-billing-api

  security:
    oauth2:
      client:
        registration:
          billing:
            provider: billing-idp
            client-id: reactive-billing-service
            client-secret: ${BILLING_OAUTH2_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: billing.read
        provider:
          billing-idp:
            token-uri: https://identity.example.invalid/oauth2/token

  r2dbc:
    url: r2dbc:postgresql://db.internal:5432/billing
    username: billing_app
    password: ${BILLING_DB_PASSWORD}
```

This is a **configuration snippet** for an application with OAuth2 Client and R2DBC installed; `.invalid` hostnames are illustrative and do not operate as a real service. Real secret values come from the runtime under the names `BILLING_OAUTH2_CLIENT_SECRET` and `BILLING_DB_PASSWORD`. Do not add fallbacks like `${BILLING_OAUTH2_CLIENT_SECRET:change-me}` or `:password` in production because they mask missing configuration and can become weak secrets.

Corresponding dependencies (Gradle Kotlin DSL, release versions managed by the Spring Boot BOM in use):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

If R2DBC is not used, omit the starter and the `spring.r2dbc` block; if the application is solely a **Resource Server accepting JWTs**, use `spring-boot-starter-oauth2-resource-server` and do not configure a client secret when there is no OAuth2 Client requirement. Examples in this lesson use Java 17+, Spring Boot 3+/4+, and compatible Spring Security versions provided by the BOM.

### 4.2. Supplying Values via Environment Variables

The orchestrator can set `BILLING_OAUTH2_CLIENT_SECRET` and `BILLING_DB_PASSWORD` in the process environment before Spring Boot starts. For production, **do not** copy real values into committed script files or command lines saved in shell history. When operating locally, load secrets from the team's credential management tool, use a protected terminal/session, and revoke access when finished.

Java code example checking only **presence/absence**, without logging the value:

```java
// File SecretPresenceCheck.java — Java 17+, Spring-independent
public class SecretPresenceCheck {
    public static void main(String[] args) {
        String secret = System.getenv("BILLING_OAUTH2_CLIENT_SECRET");
        if (secret == null || secret.isBlank()) {
            throw new IllegalStateException(
                    "Missing BILLING_OAUTH2_CLIENT_SECRET");
        }
        System.out.println("Required secret is available");
    }
}
```

Run `javac SecretPresenceCheck.java` then `java SecretPresenceCheck` in a process with `BILLING_OAUTH2_CLIENT_SECRET` set. When the variable is valid, stdout is **exactly**:

```text
Required secret is available
```

If the variable is missing/blank, the program throws `IllegalStateException` and exits non-zero; it does not print the value. This example only verifies that the variable is supplied; it **does not prove** the secret is valid, unleaked, unexpired, or authorized to access the IdP. This is a standalone Java program; running a Spring Boot application requires the corresponding project/dependencies and configuration.

### 4.3. Fail-Fast with Custom Configuration

For custom credentials, use validated binding to detect blank values at startup. Create `src/main/java/com/example/security/RemoteCredentials.java`:

```java
package com.example.security;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.remote")
public record RemoteCredentials(@NotBlank String apiKey) {
    // Default record toString() exposes field values; replace with a redacted version.
    @Override
    public String toString() {
        return "RemoteCredentials[apiKey=<redacted>]";
    }
}
```

Register the bean via `src/main/java/com/example/security/SecretsConfiguration.java`:

```java
package com.example.security;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RemoteCredentials.class)
public class SecretsConfiguration {
}
```

And add the property to the environment configuration:

```yaml
app:
  remote:
    api-key: ${REMOTE_API_KEY}
```

`@NotBlank` requires a Bean Validation provider (`spring-boot-starter-validation`). Missing configuration can fail during placeholder resolution or binding/validation; test the actual missing-secret case in the runtime environment to confirm the system **does not start** when a required secret is absent. Do not print exceptions containing secret values; validation messages should name the **missing key**, not dump all properties.

**Note:** Overriding `toString()` only reduces risk on one logging path and cannot replace logging policies, heap dump controls, and access management. With `String`-based credentials, the JVM does not guarantee immediate erasure of all copies in memory; access control to the process remains an essential security boundary.

## 5. Configuration Tree: Reading Secrets from a Volume Outside the Container Image

With `configtree:`, the filename (or directory path) becomes the **property key**, and the file contents become the **property value**. This setup fits when the orchestrator mounts secrets as files and Spring Boot loads them at startup.

Example production profile `src/main/resources/application-prod.yml`:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"

  security:
    oauth2:
      client:
        registration:
          billing:
            provider: billing-idp
            client-id: reactive-billing-service
            authorization-grant-type: client_credentials
            scope: billing.read
        provider:
          billing-idp:
            token-uri: https://identity.example.invalid/oauth2/token
```

At runtime, the file exists at:

```text
/run/secrets/
└── spring.security.oauth2.client.registration.billing.client-secret
```

The contents of that file are the platform-supplied secret, **not** stored in the repo/JAR/image. Spring Boot receives the property `spring.security.oauth2.client.registration.billing.client-secret` from the config tree. Using dot-separated filenames as shown above is valid in a config tree; there is no need to create nested directories for each dot.

The `configtree:/run/secrets/` option means "this location **must exist**." `optional:configtree:/run/secrets/` allows the directory to be absent and is usually more suitable for local/test environments; for production where secrets are required, consider omitting `optional:` and adding validation to reject cases where the directory exists but the value file is empty/missing.

Do not simultaneously declare an unintended placeholder in a higher-precedence property source that overrides the value from the config tree. Choose **one canonical source mechanism** for the same secret per environment; if combining env + configtree, test precedence.

### 5.1. Mounting a Kubernetes Secret in a Deployment

The following manifest **contains no secret values**; it assumes the cluster already has a Secret named `billing-oauth2` with key `client-secret` created by a separate provisioning workflow:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: reactive-billing-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: reactive-billing-api
  template:
    metadata:
      labels:
        app: reactive-billing-api
    spec:
      containers:
        - name: app
          image: registry.example.invalid/billing/reactive-api:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
          volumeMounts:
            - name: oauth2-secrets
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: oauth2-secrets
          secret:
            secretName: billing-oauth2
            items:
              - key: client-secret
                path: spring.security.oauth2.client.registration.billing.client-secret
```

**Operational prerequisites:** The `billing-oauth2` Secret must exist in the **same namespace** as the Pod and have the `client-secret` key. Kubernetes provides the file via the mount; Spring Boot reads the file from `configtree:/run/secrets/`. Provisioning owners can use External Secrets Operator, Secrets Store CSI Driver, Vault, or corresponding cloud tools to sync secrets from a central store into the cluster. Specifics depend on the platform, policy, and driver version.

In production, additionally enforce: RBAC permissions restricted to required controllers/identities; Secret encryption at rest in etcd when supported; restrictions on who can `get/list/watch` Secrets and `exec`/`attach` into Pods; mounting only into containers that need them; running Pods as least-privilege users; and restricting access to nodes/snapshots.

**Do not mistake `Secret` for automatic secure encryption:** the `data` field in a Kubernetes Secret is **Base64 encoding**, not encryption; by default, Secrets may be stored unencrypted in the datastore if the cluster does not have encryption at rest enabled. Mounting as a volume does not automatically eliminate risks from file permissions, backups, or compromised nodes.

### 5.2. File Mount vs. Env in Kubernetes

| Criterion | `secretKeyRef` as env | Secret volume + `configtree:` |
| --- | --- | --- |
| Form | Process environment | File in container filesystem |
| Spring Boot app | Binds via env/property placeholder | Binds property keys via config tree |
| When Secret updates | Running process env **does not auto-update**; requires new process/Pod | Mounted file is usually updated by kubelet after a delay; **whether the app reloads** is a separate matter |
| Exposure surface | Env inspection, process dump, deployment metadata | File permissions, container/node access, backups |
| Notes | Do not log env, do not dump full process | Avoid `subPath` mounts if automatic updates are needed; check file owner/mode |

**Key takeaway:** Even when the file in the volume changes, Spring Boot `Environment`, `@ConfigurationProperties`, OAuth2 `ClientRegistration`, or already-instantiated beans usually **do not update automatically**. For new credentials to take effect, you need a supported reload strategy, controlled refresh/rebind, or a rolling restart. Do not claim "Kubernetes automatically rotates all OAuth2 client secrets inside the app" merely because the mount updates.

## 6. Secret Manager, Vault, KMS, and Workload Identity

Externalized configuration separates code and secret data; a secret manager adds controlled distribution and governance.

**Common options:**

- **HashiCorp Vault/Spring Cloud Vault:** Spring Cloud Vault supports `spring.config.import: vault://` when compatible starters/extensions, Vault URI, TLS, and authentication mechanisms are configured. Workloads are granted policies to read only their own paths; prefer Kubernetes auth/AppRole/OIDC over embedding a root token in `application.yml`.
- **AWS Secrets Manager / Systems Manager Parameter Store, Azure Key Vault, Google Secret Manager:** use the appropriate integration/SDK/CSI/sidecar and IAM workload identity. Spring Boot **does not natively understand every provider import prefix** unless the corresponding connector/dependency is installed.
- **KMS/HSM:** keeps key material non-exportable (when supported by the API/provider) and performs signing/decryption via authorized APIs. Useful for signing keys, envelope encryption, and strict security boundaries. KMS does not completely replace tools for secret storage/password rotation.

Conceptual **Spring Cloud Vault** example (requires installing dependencies and configuring a real auth method per deployment):

```yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: https://vault.internal.example.invalid:8200
```

This is only an integration point. It will not run without a Vault server, CA trust, policies/paths/secret backend, and proper authentication. **Do not put a static `spring.cloud.vault.token`, root token, or cloud access key into Git** just to make the application start. In containers, prefer an identity bound to a service account/workload with a TTL and least privilege.

Sample secure flow:

```text
Pod ServiceAccount / Cloud Workload Identity
    -> authenticate to Secret Manager (TLS)
    -> policy: read exactly billing/prod/client-secret
    -> receive current secret version (or mount it)
    -> Spring Boot binds OAuth2 ClientRegistration
    -> WebClient uses authorized access token for downstream
    -> audit retrieval + rotate/revoke on schedule
```

**Do not make blocking secret-manager SDK calls on the WebFlux event loop.** Secrets can be loaded at startup via ConfigData/integrations; if runtime reads are strictly required, use a non-blocking SDK or offload blocking operations to `Schedulers.boundedElastic()` after accounting for caching, timeouts, concurrency, and error handling. Calling `block()` inside a `SecurityWebFilterChain`/handler/`WebClient` callback can stall the Reactor Netty event loop.

## 7. Managing Keys, Certificates, and Keystore Passwords

Not every "key" is a string bound to `@Value`.

### 7.1. WebFlux Inbound HTTPS (Reactor Netty)

For a PKCS#12 keystore generated/provisioned from a secret system outside the JAR, Spring Boot supports SSL bundles. Example `application-prod.yml` (supplementary snippet):

```yaml
spring:
  ssl:
    bundle:
      jks:
        web:
          keystore:
            location: "file:/run/keys/server.p12"
            type: PKCS12
            password: ${SERVER_KEYSTORE_PASSWORD}

server:
  port: 8443
  ssl:
    bundle: web
```

`/run/keys/server.p12` is a mounted file with read permissions for the required process; `SERVER_KEYSTORE_PASSWORD` is supplied at runtime. Do not copy `.p12` files, private keys, or passwords into the build context/image. The keystore password decrypts/opens the keystore; it **does not replace** protecting file and private key read permissions.

For PEM certificates + private keys, `spring.ssl.bundle.pem.<name>.keystore.certificate` and `...private-key` can point to `file:/run/keys/...` paths. SSL bundles offer conditional reload options in recent Spring Boot versions for supported consumers (including the Netty server); **do not assume every WebClient, driver, keystore, or Boot version automatically hot-reloads**. Check documentation for the running version and test certificate rotation in staging.

### 7.2. JWT Signing Keys: Signer Differs from Verifier

- **Authorization Server** signs JWTs with a **private key**. Keep the private key in an HSM/KMS or appropriately protected store; only authorized endpoints may sign according to policy.
- **Reactive Resource Server** typically **verifies** JWTs with the issuer's public key/JWKS via `jwk-set-uri` or `issuer-uri` configuration (including appropriate discovery mechanisms). A resource server normally **does not need** the private signing key or an OAuth2 client secret to verify tokens.
- Use HTTPS, validate issuer, audience per business requirements, allowed algorithms, and `kid`; never trust a JWKS URI controlled by arbitrary user input.
- JWT signing key rotation: publish the new key with a new `kid`, keep the old public key in JWKS long enough for still-valid tokens, switch signing to the new key, wait for old tokens to expire, then remove the old key. If a private key is compromised, trigger a dedicated incident response plan, which may require early revocation.

Example resource server using a trusted issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.invalid/
```

This is a **Resource Server** configuration verifying inbound JWTs; it stores no client secret and requires the `spring-boot-starter-oauth2-resource-server` dependency. The issuer must support the corresponding metadata/JWKS in a real environment.

## 8. User Passwords: `PasswordEncoder` Instead of Config Secrets

When a WebFlux application provides form login or username/password authentication, the database should store an adaptive password hash, not the raw password. Spring Security provides `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, supporting prefixes such as `{bcrypt}` to select the appropriate algorithm during verification.

Complete JUnit 5 example in a project that already includes Spring Security Crypto and the test starter. File `src/test/java/com/example/security/PasswordHashTest.java`:

```java
package com.example.security;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordHashTest {
    @Test
    void usesAdaptiveOneWayPasswordHash() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String raw = "test-only-user-password";
        String stored = encoder.encode(raw);

        assertNotEquals(raw, stored);
        assertTrue(stored.startsWith("{bcrypt}"));
        assertTrue(encoder.matches(raw, stored));
        assertFalse(encoder.matches("incorrect", stored));
    }
}
```

Run `./gradlew test --tests com.example.security.PasswordHashTest` (Windows: `gradlew.bat test --tests com.example.security.PasswordHashTest`). **Expected result:** test passes, no application stdout. Bcrypt hashes are salted so encoded values differ across runs; do not assert a fixed hash string. Tune the work factor to target hardware/latency; apply brute-force and failed-login protections in addition to hashing.

**Do not use `PasswordEncoder` for DB passwords, OAuth2 client secrets, or API keys that must be presented again**. One-way hashing destroys the original value needed to authenticate against external systems; those credentials require a secret store and protected retrieval mechanisms.

## 9. Testing OAuth2 Client Configuration Without Leaking Secrets

For OAuth2 Client, tests must prove **the right registration ID is bound**, values come from test configuration, and no requests are sent to a real authorization server. Example in a Spring Boot WebFlux project with `spring-boot-starter-oauth2-client`, create `src/test/java/com/example/security/OAuth2SecretBindingTest.java`:

```java
package com.example.security;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(properties = {
        "spring.security.oauth2.client.registration.billing.client-id=test-client",
        "spring.security.oauth2.client.registration.billing.client-secret=test-only-secret",
        "spring.security.oauth2.client.registration.billing.authorization-grant-type=client_credentials",
        "spring.security.oauth2.client.provider.billing.token-uri=https://identity.example.invalid/token"
})
class OAuth2SecretBindingTest {
    @Autowired
    ReactiveClientRegistrationRepository registrations;

    @Test
    void bindsExternalizedOAuth2Registration() {
        ClientRegistration registration = registrations
                .findByRegistrationId("billing")
                .block(Duration.ofSeconds(2)); // Only block in synchronous tests.

        assertNotNull(registration);
        assertEquals("billing", registration.getRegistrationId());
        assertEquals("test-client", registration.getClientId());
        assertEquals("test-only-secret", registration.getClientSecret());
    }
}
```

The `test-only-secret` value is a **dummy fixture**, not a real credential, and does not need to be stored in a secret manager. Expected result: the test passes when Spring Boot auto-configuration creates `ReactiveClientRegistrationRepository`; the test **does not** send HTTP/token requests to the `.invalid` URL. These classes assume the test package is scanned by the Boot application and no custom bean/repository overrides it; if there is, adjust the test context accordingly.

Run `./gradlew test --tests com.example.security.OAuth2SecretBindingTest` (Windows: `gradlew.bat test --tests com.example.security.OAuth2SecretBindingTest`). JUnit does not print the secret; avoid adding `System.out.println(registration)` or logging `ClientRegistration`.

**Testing boundaries:**

- The test above verifies **property binding**. It does not verify Kubernetes Secret files, Vault policies, Pod permissions, TLS to the IdP, or real token grants.
- Staging environment tests must prove startup retrieves secrets using a real workload identity, without printing values. Log only registration names, non-sensitive version/metadata, or a "configuration ready" indicator.
- Missing-secret tests: run in a clean environment with required configuration and validation, verify startup reports the **missing key** and fails without printing key contents.
- Rotated client-secret tests: confirm Pods/beans use the new version and the IdP issues tokens successfully; verify old versions are revoked on schedule.
- OAuth2 client-to-service flow tests: use `MockWebServer`/WireMock for downstream, and a mock OAuth2 client/manager if needed; assert the Bearer header at the mock server without logging real access tokens.

## 10. Rotation: From Old Version to New Version Without Downtime

Secret rotation comprises **creation, distribution, traffic cutover, verification, and revocation**. Changing a file's contents alone is not enough.

1. **Inventory:** identify the secret owner, usage sites, `registrationId`, permission scope, expiration, version storage, dependent Pods/workloads, and rollback procedure.
2. **Create a new version:** at the IdP/DB/secret manager/KMS using an appropriate algorithm and entropy. If the provider supports two concurrent credentials, prefer a bounded overlap window.
3. **Distribute:** update the version in the secret store or volume; check Kubernetes/CSI/sidecar sync schedules and related caches.
4. **Ensure the application uses the new version:** rolling restart Pods (common, easy to verify), or a reload mechanism supported and tested for each component. Process env does not auto-update; `@ConfigurationProperties` or OAuth2 `ClientRegistration` beans also do not automatically rebind just because a file changed.
5. **Verify:** check readiness, successful token requests with the new credential, latency/5xx/401/`invalid_client`, downstream reachability, and zero traffic sending the old credential.
6. **Revoke the old secret:** only after verifying all consumers have migrated; record audit/operational events, notify owners, and purge copies in pipelines/temporary stores per retention policy.
7. **Rollback plan:** rolling back application/config versions may require an overlap window where the old credential remains valid. When a credential is compromised, **never** restore the compromised secret; issue a new safe secret.

### Specific Scenarios

- **OAuth2 client secret:** update the credential at the authorization server and Spring `ClientRegistration`; new token requests may return `invalid_client` if both sides have mismatched versions. Previously issued access tokens may remain valid until their TTL expires, depending on IdP policy.
- **DB password:** may require provisioning parallel users/credentials for gradual cutover; a connection pool holding old connections does not prove new connections work with the new password.
- **TLS certificate/private key:** SSL bundle reload can be used if the Boot version and Netty consumer support it; verify handshake and chain with a real client after rotation.
- **JWT signing key:** coordinate `kid`, JWKS caching, and token TTL; do not remove old public keys too early and break verification of still-valid tokens.
- **Refresh tokens:** do not share the client secret lifecycle; store securely and be prepared to invalidate sessions/tokens during incident response.

### When Secret Exposure Is Suspected

Prioritize stopping abuse: revoke/rotate credentials at the provider; restrict related permissions and sessions/tokens; inspect audit/usage logs to determine scope; update config and roll out; clean Git history/logs/artifacts/backups per investigation procedures. **Simply deleting the secret from the repo or amending commits does not invalidate an exposed credential.**

## 11. Protecting Logs, Actuator, HTTP Traces, and CI

### Spring Boot Actuator

`/actuator/env` and `/actuator/configprops` sanitize values by default in many Boot versions; however, masking should not be treated as the sole barrier. Restrict exposure and require authentication/authorization for management endpoints. Example production configuration:

```yaml
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
```

Do not enable `show-values: always` in production. `/actuator/heapdump`, thread dumps, debug endpoints, and trace/httpexchanges also require access review. Debug logging of security/OAuth2/HTTP clients can leak payloads or Authorization headers via custom loggers/filters; **do not log raw Bearer tokens or request headers**.

### WebClient in Reactive Systems

- `WebClient` attaches `Authorization` via a filter when an authorized client is selected; send credentials only to the intended host/registration. Do not attach a default bearer mechanism to every request toward arbitrary domains.
- Do not write `Authorization`, `Cookie`, `Set-Cookie`, or `client_secret` into structured logs, traces, exception messages, or audit events.
- If writing a custom `ExchangeFilterFunction` to log requests, build a safe **header allowlist** (method, sanitized path, status, duration) rather than logging raw `request.headers()`.
- Set reasonable timeouts and retries toward KMS/Vault; do not retry indefinitely and never fall back to static hardcoded values when a secret provider fails.
- When keys/secrets are retrieved via a blocking API, do not execute blocking calls on the Reactor Netty event loop; prepare configuration at startup or use an appropriate asynchronous API.

### CI/CD and Development Workflow

- Use **secret scanning** (pre-commit + repository/CI), restrict job runner privileges, manage masking, and review artifacts/logs; inspect for false negatives.
- Do not pass real secrets into `docker build --build-arg`, control Docker layers/cache; runtime mounts/secret providers are the appropriate boundary for service credentials.
- Do not print env with `printenv`, `env`, or `set` in CI jobs that hold secrets; restrict shell debug `set -x`.
- Use only **non-real fixtures** in `src/test/resources`; real secrets do not belong in test fixtures, screenshots, tickets, or PRs.
- Enforce permissions by **service + environment**: `billing-dev` cannot read `billing-prod`; one service cannot read another service's secrets.
- Fields such as `client-secret`, `password`, `api-key`, `private-key` are checked by property name, but scanners must also cover unnamed values, logs, artifacts, and history.

## 12. Common Deployment Pitfalls

| Symptom | Possible Cause | Safe Verification Approach |
| --- | --- | --- |
| Startup fails with missing secret | Env not provisioned, wrong mount path, wrong key in configtree, or missing read permissions | Check key/mount **existence and name**, service account, file permissions; do not print values |
| OAuth2 token endpoint returns `invalid_client` | Wrong client-id/client-secret, IdP not rotated, trailing newline in value, or app using old version | Check registration ID, property source order, version; verify with IdP via a controlled test flow |
| Works locally, Pod fails | Local has env; Pod uses volume without enabling the right profile or `spring.config.import` | Check profile, mount path, namespace, import, and bean binding |
| File in Pod changed but requests still fail | Bean/OAuth2 registration bound at startup, not refreshed | Rolling restart or deploy verified reload mechanism |
| K8s Secret is base64-encoded yet still leaked | Mistaking base64 for encryption, overly broad RBAC, secret lingering in image/logs/backups | Enable encryption at rest, tighten RBAC, rotate, and audit access trails |
| WebFlux slows down during Vault outage | Blocking SDK called on event loop, infinite retries | Move I/O to startup/non-blocking path, apply timeouts/circuit breaker and fail-closed |
| Authorization token appears in logs | Misconfigured HTTP filter/request logging/tracing | Disable body/header logging, scrub sensitive data, rotate exposed tokens |
| Resource Server lacks private key | Mistakenly trying to copy signing key to verifier | Configure only appropriate public issuer/JWKS; keep private key on signer |
| Password check fails after deploy | Hash missing prefix/incompatible algorithm or `NoOpPasswordEncoder` used | Use `DelegatingPasswordEncoder`, plan migration, and test real hashes |
| New certificate mounted but TLS still serves old cert | SSL consumer not reloading or wrong path configured | Check Boot/Netty version and reload support; restart if needed |

## 13. Pre-Release Checklist

- [ ] No real secrets in source code, active Git history, JARs, images, committed Helm values/manifests, logs, test fixtures, or CI artifacts.
- [ ] Application configuration contains **property names** and **secret references**; production obtains values from an organization-approved mechanism.
- [ ] Proper classification: **user password hashes** via `PasswordEncoder`, **service credentials and private keys** read from secret store/KMS/mount.
- [ ] Identity/service account has least-privilege access to the exact secret of the exact environment; reads and version changes are audited.
- [ ] OAuth2 client registration ID/client-id, grant type, scopes, and token endpoint are correct; client-secret is never logged.
- [ ] `configtree:`/env/Vault/CSI is tested in a production-like container, verifying missing secrets cause a clear startup failure without leaking values.
- [ ] File/volume permissions, network TLS, CA trust, certificate expiry, and KMS/secret manager policies are verified.
- [ ] Mount updates are distinguished from runtime bean updates; restart/reload strategy and rotation tests are in place.
- [ ] Actuator/management endpoints expose only necessary features; logs/traces/heap dumps are controlled.
- [ ] Owner, rotation schedule, revocation plan, overlap window, failover test, and leak response procedure exist.

## 14. Self-Study Questions

1. Why can you store a user's password hash, yet **cannot** use bcrypt in place of an OAuth2 client secret?
2. Write the property name that `/run/secrets/spring.security.oauth2.client.registration.billing.client-secret` provides to `configtree:/run/secrets/`.
3. Are secrets in a Kubernetes Secret automatically encrypted just because the data is Base64-encoded? Which permissions should be restricted?
4. When a secret volume updates but `ReactiveClientRegistrationRepository` still uses the old secret, how would you implement and verify rotation?
5. Why does a typical resource server only need a public key/JWKS to verify JWTs, while the private signing key should stay on the authorization server?
6. What could a `WebClient` filter that logs all request headers for debugging expose? What is a safer way to log?
7. When a Vault/KMS API is blocking, why can calling it directly inside a WebFlux request handler stall the service?
8. In an incident where a client secret was committed to Git, why is "deleting the secret line from the file" insufficient?

## Official References

- Spring Boot – Externalized Configuration and Configuration Trees: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot – SSL Bundles and reload mechanism: https://docs.spring.io/spring-boot/reference/features/ssl.html
- Spring Boot – Actuator Endpoints and value sanitization: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Security – Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security – Reactive OAuth2 Client core classes: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security – Password Storage / PasswordEncoder: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Kubernetes – Secrets good practices: https://kubernetes.io/docs/concepts/security/secrets-good-practices/
- Spring Cloud Vault – Quick Start / ConfigData: https://docs.spring.io/spring-cloud-vault/reference/quickstart.html

> Cross-check reload details, Spring Boot/Cloud versions, and each secret provider against your BOM and real deployment environment. Illustrative examples use `.invalid` domains and dummy data, containing no operational credentials.
