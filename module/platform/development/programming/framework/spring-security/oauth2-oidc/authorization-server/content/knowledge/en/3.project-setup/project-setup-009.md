# Managing Sensitive Configuration with Environment Variables and Secret Stores

> **Chapter: Project Setup.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module: designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application. The goal is removing secrets from source code and artifacts, granting least-privilege access to the running process, controlling lifecycle, and testing secret changes.

## 1. Why Does an Authorization Server Need Strict Secret Management?

An Authorization Server issues authorization codes, access tokens, and (when OIDC is enabled) ID Tokens to clients. If a signing key or a high-privilege secret leaks, an attacker can forge tokens, impersonate clients, or access sensitive data. Right from project setup, you must separate **standard configuration** from **sensitive configuration** and define who is allowed to view, update, and rotate each type.

| Value | Is It a Secret? | Where Used | Notes |
|---|---|---|---|
| `issuer` (`https://login.example.vn`) | No | Authorization Server, Client, Resource Server | Must be stable, public, and match the `iss` claim; changes must be planned |
| `client_id`, registered redirect URI | No | RegisteredClient and OAuth2 Client | Never treat `client_id` as a password |
| **Client secret** of a confidential client | **Yes** | Client when authenticating to `/oauth2/token`; hashed copy on Authorization Server | Protect plaintext on the client side; on the Authorization Server side prefer storing a **one-way hash** |
| **Private signing key** used to sign JWT/ID Tokens | **Yes, very high** | Authorization Server or KMS/HSM | The private key must remain secret; the corresponding public key may be published via JWKS |
| PKCS#12/keystore password | **Yes** | Process loading signing/TLS keys | Protect both the key file and the unlocking password |
| Database password, Redis password, integration API key | **Yes** | Infrastructure and supporting services | Restrict permissions and lifecycle per environment |
| `jwks_uri`, public JWK | No | Metadata and Resource Server | Publishes public keys; never publishes private keys |
| Active access tokens, refresh tokens, authorization codes | **Sensitive** | Runtime protocol data | Not static configuration; strictly avoid logging them in full |

Running example throughout: the Authorization Server uses issuer `https://login.example.vn`; the web client has `client_id=portal-web` and callback `https://app.example.vn/login/oauth2/code/portal`. This document illustrates two ways to provide the client secret: **environment variables** and a **secret store supplying values at runtime**. Secrets in code snippets are represented by variable names or placeholders, containing no real values.

Security goals of a production system:

1. No secrets in Git, committed `application.yml`, Docker images, JARs, manifests, or documentation.
2. Only authorized workloads can retrieve secrets; each environment uses a distinct set of secrets.
3. Startup fails clearly when required secrets are missing, without falling back to weak defaults.
4. Minimize the risk of secrets leaking via logs, runtime configuration, debug tools, and backups.
5. Maintain the ability to revoke and replace secrets and signing keys while preserving compatibility during the required transition window.

## 2. Distinguishing Environment Variables, Secret Stores, and How Apps Receive Values

An **environment variable** is a **mechanism for passing configuration into a process**. It is simple, available on most platforms, fits 12-factor configuration, and can carry secrets in controlled environments. However, it **does not encrypt or manage secret lifecycles by itself**: variables can be exposed through debug tools, crash dumps, OS-level process inspection, CI/CD configuration, or child processes inheriting the environment.

A **secret store** is a system for storing/managing secrets and access policies, such as HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, or Google Cloud Secret Manager. Some platforms also use Kubernetes Secrets to deliver values to Pods; Kubernetes Secrets have their own management model, but **base64 values in manifests are not cryptographic security**.

~~~mermaid
flowchart LR
    Dev["Source code + application.yml<br/>property names only"] --> Build["Build JAR / image<br/>no embedded secrets"]
    Store["Secret store<br/>IAM, audit, rotation"] --> Agent["Workload identity / CSI / operator<br/>permission check"]
    Agent --> Runtime["Runtime:<br/>environment or file mount"]
    Build --> App["Spring Boot Authorization Server"]
    Runtime --> App
    App --> Registered["RegisteredClientRepository<br/>hashed client secret"]
    App --> Signer["Signing service/JWKSource<br/>protected private key"]
    Signer --> Public["JWKS: public key only"]
~~~

There are three main delivery patterns:

| Delivery Method | Strengths | Limitations to Control |
|---|---|---|
| Runtime-injected environment variables | Simple with Spring Boot, containers, and CI/CD | Can show up in env dumps, process snapshots, and deployment specs; changes usually require a restart |
| Read-only secret file mounted into container/VM | Keeps contents out of environment variables; file permissions can be enforced | Must block unauthorized reads, manage mounts, avoid baking files into images; updating the file does not mean Spring beans auto-reload |
| Calling the secret store directly or via operator/agent | Centralized IAM, auditing, versioning, and rotation | Increases dependence on permissions, network, API/quotas, caching, and store-unavailable fallback strategy |

A **secret store** and the **mechanism delivering secrets into a process** are two decisions that can be combined: for instance, secrets live in Vault, an agent mounts them as a volume, and Spring Boot reads the volume via `configtree:`. Your deployment choice must fit your infrastructure and risk profile; no single mechanism is inherently secure enough for every environment.

## 3. Configuring Spring Boot with Environment Variables

### 3.1. Commit Only Placeholders into `application.yml`

Example base configuration for the **Authorization Server**:

~~~yaml
# src/main/resources/application.yml
app:
  authorization-server:
    issuer: ${AUTH_SERVER_ISSUER}
    client:
      id: ${PORTAL_CLIENT_ID:portal-web}
      secret: ${PORTAL_CLIENT_SECRET}
      redirect-uri: ${PORTAL_REDIRECT_URI}

# Need to import separate security config for environments with a secret volume?
# See Section 4 to add spring.config.import.
~~~

`issuer`, `client.id`, and `redirect-uri` are standard deployment configuration; `client.secret` is sensitive. Although all four can be passed via environment variables so they vary across local/staging/production, only `PORTAL_CLIENT_SECRET` must be provisioned and governed as a secret. Never put a default like `dev-secret` on `PORTAL_CLIENT_SECRET` in a file that could run in production: missing variables must fail early.

Mapping table for the example:

| Runtime Variable | Spring Boot Property | Example Value |
|---|---|---|
| `AUTH_SERVER_ISSUER` | `app.authorization-server.issuer` via placeholder | `https://login.example.vn` |
| `PORTAL_CLIENT_ID` | `app.authorization-server.client.id` | `portal-web` |
| `PORTAL_REDIRECT_URI` | `app.authorization-server.client.redirect-uri` | `https://app.example.vn/login/oauth2/code/portal` |
| `PORTAL_CLIENT_SECRET` | `app.authorization-server.client.secret` | **Never place real values in docs, logs, or Git** |

Here `PORTAL_CLIENT_SECRET` is an **explicitly referenced placeholder**, so it does not rely on guessing environment variable names via relaxed binding. Spring Boot also maps properties to environment variables by its own rules; when combining multiple configuration sources, pick one convention and verify the bound values in tests.

### 3.2. Binding into a Configuration Object and Validating at Startup

Java 17+ example using `@ConfigurationProperties` and Bean Validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.authorization-server")
public record AuthorizationProperties(
        @NotBlank String issuer,
        @Valid @NotNull Client client) {

    public record Client(
            @NotBlank String id,
            @NotBlank String secret,
            @NotBlank String redirectUri) {
    }
}
~~~

Enable binding in a configuration class and consume the validated values:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

@Configuration
@EnableConfigurationProperties(AuthorizationProperties.class)
class AuthorizationSettingsConfig {

    @Bean
    AuthorizationServerSettings authorizationServerSettings(AuthorizationProperties properties) {
        return AuthorizationServerSettings.builder()
                .issuer(properties.issuer())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(
            AuthorizationProperties properties,
            PasswordEncoder encoder) {

        AuthorizationProperties.Client client = properties.client();

        RegisteredClient portal = RegisteredClient.withId("portal-web-registration")
                .clientId(client.id())
                // Hash with encoder; the repository only stores strings like {bcrypt}...
                .clientSecret(encoder.encode(client.secret()))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(client.redirectUri())
                .scope(OidcScopes.OPENID)
                .clientSettings(ClientSettings.builder().requireProofKey(true).build())
                .build();

        return new InMemoryRegisteredClientRepository(portal);
    }
}
~~~

**Boundary of the example:** these beans focus on configuration management. A working Authorization Server still needs `SecurityFilterChain`, login configuration, authorization persistence, and an appropriate `JWKSource<SecurityContext>`; enable OIDC if issuing ID Tokens. `InMemoryRegisteredClientRepository` is only suitable for illustration/testing, not as a durable client store for production. Include a validation starter such as `spring-boot-starter-validation` so `@NotBlank` and `@NotNull` are enforced.

**Key points to understand about client secrets:**

- A confidential client sends its **plaintext secret** to the token endpoint using the registered authentication method over a TLS connection.
- The Authorization Server compares it against the **hashed** string stored in `RegisteredClient`. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` produces an encoded value with an algorithm prefix such as `{bcrypt}`.
- In production, clients should be onboarded via a provisioning workflow storing **hashes** in `JdbcRegisteredClientRepository` or an equivalent durable repository. Then the Authorization Server does not even need the client's plaintext secret in its startup environment; only the client needs the plaintext.
- A confidential client's secret is **not** a private signing key; never use a client secret as a signing key for ID Tokens/JWTs with asymmetric algorithms like RS256.
- If you change `PORTAL_CLIENT_SECRET` and restart the in-memory bean above, the client must switch to the corresponding secret. Updating an environment variable on a running Pod usually does **not** cause the repository to reload the new secret automatically.

### 3.3. Running Locally Without Recording Secrets in Shell History

Bash example for local testing:

~~~bash
export AUTH_SERVER_ISSUER='http://127.0.0.1:9000'
export PORTAL_REDIRECT_URI='http://127.0.0.1:8080/login/oauth2/code/portal'
export PORTAL_CLIENT_ID='portal-web'

# Type the secret directly in the terminal; do not put it in a command saved in history.
read -r -s -p 'PORTAL_CLIENT_SECRET: ' PORTAL_CLIENT_SECRET
printf '\n'
export PORTAL_CLIENT_SECRET

# Start using your Spring Boot project's build/run mechanism.
java -jar authorization-server.jar
~~~

The HTTP loopback addresses in the example are **strictly for local development**; real deployments must use valid HTTPS and exact registered redirect URIs. After testing, close the shell/session or clean up environment variables appropriately, though do not treat `unset` as clearing copies already held in a running process's memory.

Regarding `.env` files: Spring Boot **does not automatically** load `.env` files the way some JavaScript tools do. Docker Compose or a process launcher can read the file to inject environment variables. If using `.env` locally, add it to `.gitignore`, provide a `.env.example` containing only **variable names/placeholders**, restrict file permissions, and never commit real secrets. Never treat `.gitignore` as a cure for secrets that were already committed.

## 4. Supplying Secrets from a Secret Store via File Mount and `configtree:`

### 4.1. A Deployment Pattern

An operations team can store `PORTAL_CLIENT_SECRET` in Vault/a cloud secret manager; an operator, CSI driver, or agent authenticated via **workload identity** fetches the value and mounts it as a read-only file inside the container:

~~~text
/run/secrets/
└── PORTAL_CLIENT_SECRET    # file content = secret value, without the variable name
~~~

Spring Boot supports *configuration tree* imports, where the **filename is the key** and the **file content is the value**. Add to `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"

app:
  authorization-server:
    issuer: ${AUTH_SERVER_ISSUER}
    client:
      id: ${PORTAL_CLIENT_ID:portal-web}
      secret: ${PORTAL_CLIENT_SECRET}
      redirect-uri: ${PORTAL_REDIRECT_URI}
~~~

With `/run/secrets/PORTAL_CLIENT_SECRET`, the `${PORTAL_CLIENT_SECRET}` placeholder resolves from the configuration tree. Locally, when the mount directory does not exist, the `optional:` prefix allows skipping the file source; in that case, the `PORTAL_CLIENT_SECRET` environment variable is still needed. If neither provides the secret, the application must **fail to start**.

For deployments that **only accept mounted secret files**, use `configtree:/run/secrets/` (omitting `optional:`) so a missing mount fails immediately, combined with non-empty validation. When the same key appears in multiple sources, property source precedence can cause another value to win; test the actual configuration and avoid letting higher-precedence sources unintentionally override secrets.

### 4.2. Kubernetes Secret Volume Illustration

This example only shows **how to mount a Secret created outside Git** into a Pod:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-server
spec:
  replicas: 2
  selector:
    matchLabels:
      app: auth-server
  template:
    metadata:
      labels:
        app: auth-server
    spec:
      serviceAccountName: auth-server
      containers:
        - name: auth-server
          image: registry.example.vn/auth-server:REPLACE_WITH_PINNED_TAG
          volumeMounts:
            - name: runtime-secrets
              mountPath: /run/secrets
              readOnly: true
          env:
            - name: AUTH_SERVER_ISSUER
              value: "https://login.example.vn"
            - name: PORTAL_REDIRECT_URI
              value: "https://app.example.vn/login/oauth2/code/portal"
      volumes:
        - name: runtime-secrets
          secret:
            secretName: auth-server-runtime
~~~

The `auth-server-runtime` Secret must contain the **key** `PORTAL_CLIENT_SECRET` so the volume creates the matching filename. The YAML above is illustrative; a real deployment must add the image, ports, readiness/liveness probes, resource limits, RBAC/network policies, and infrastructure-appropriate Secret provisioning. Never commit a `Secret` manifest with base64-encoded `data` and treat it as secure: base64 is trivially decoded. Use encryption at rest, least-privilege RBAC, etcd access controls, and an appropriate pipeline/secret operator.

Practical note: updating a Kubernetes Secret can update **volume** contents after a short delay, yet Spring Boot beans with already-bound configuration and secrets converted into `RegisteredClient` records **do not update automatically**. Env vars sourced from Secrets do not update at all inside a running container. You need an explicit restart/rollout strategy or a cleanly designed and tested reload mechanism. With `subPath` mounts, Secret content updates have additional limitations.

### 4.3. Accessing a Secret Store Directly

Beyond volumes, an application can use an SDK or appropriate Spring integration to read from a secret store at startup or on a secure schedule. There is no universal Spring Boot property that automatically connects to every Vault/KMS.

Required lifecycle:

1. The workload authenticates using a **platform-issued identity** (service account, IAM role, managed identity); avoid using a static access key just to fetch another secret.
2. The secret store enforces policies by environment, application, and secret name, recording audit logs per policy.
3. The application receives the current secret over TLS, validates its format, and initializes beans/connections.
4. During rotation, the runtime retrieves the new version and transitions in a controlled manner; do not mutate individual beans haphazardly.
5. When the store is unavailable, the application follows a defined strategy: startup needing secrets must **fail closed**; for running instances, use cached values or stop serving depending on expiration, risk, and operational requirements.

Never grant every Pod access to the entire vault. Partition namespaces/paths and policies by application, environment, and action (read/write/rotate), enforcing change control and auditing. Even with TLS, secret values must still be minimized in application memory and kept out of logs.

## 5. A Special Authorization Server Secret: JWT/ID Token Signing Keys

An Authorization Server issuing JWT/ID Tokens signed with an asymmetric algorithm needs a **private key** to sign and a **public key** to publish. A private signing key has broader blast radius than a client secret: if compromised, an attacker can forge tokens with your system's `iss` until relying parties stop trusting that key.

~~~mermaid
flowchart TB
    KeyStore["Secret store / HSM / encrypted keystore<br/>PRIVATE KEY"] --> Sign["Authorization Server signs JWT/ID Token"]
    Sign --> Token["JWT header: kid=key-v2"]
    KeyStore --> Public["Export corresponding public JWK"]
    Public --> JWKS["JWKS endpoint: /oauth2/jwks"]
    Token --> Verify["Client / Resource Server"]
    JWKS --> Verify
    Verify --> Decision{"Signature, iss, aud,<br/>exp, nbf, scope valid?"}
    Decision -->|Yes| Accept["Accept per policy"]
    Decision -->|No| Reject["Reject"]
~~~

**Signing key configuration notes:**

- Never generate a new RSA/EC key pair **on every process startup** in production. If pods hold different private keys without coordinated public JWKS, newly issued tokens can fail verification on the next request.
- Keys can live in an HSM/KMS with remote signing operations, or be delivered as keystore/PEM files via a secret store mounted with minimal read permissions. Actual KMS/HSM usage must match the signing/JWK mechanisms supported by your chosen stack.
- If using PKCS#12, keep both the **keystore file** and **password** in secure storage; only place paths or property names such as `JWT_KEYSTORE_PATH`, `JWT_KEYSTORE_PASSWORD`, and `JWT_KEY_ALIAS` in application configuration.
- `JWKSource<SecurityContext>` in Spring Authorization Server must provide the active signing key and public JWKs so the `jwks_uri` endpoint returns the right public keys. Never include RSA private fields such as `d`, `p`, or `q` in the public JWKS.
- Each key should have a stable `kid` unique within the JWKS; key transitions must be coordinated with token lifetimes and JWKS caching.
- A password used to **decrypt/unlock** a private key cannot be replaced with a one-way hash: the application needs the actual key or access to the signing device. This is an important difference from client secrets, where the Authorization Server only needs to **verify a hash**.

Indicative configuration example for a system storing keys in a mounted file:

~~~yaml
app:
  signing:
    keystore-path: ${JWT_KEYSTORE_PATH:/run/keys/signing.p12}
    keystore-password: ${JWT_KEYSTORE_PASSWORD}
    key-alias: ${JWT_KEY_ALIAS:key-v1}
    key-password: ${JWT_KEY_PASSWORD}
~~~

The `app.signing.*` properties above are **application-defined conventions**, not built-in Spring Authorization Server properties that automatically enable JWT signing. Implementers must bind them, load the key, build `JWKSource<SecurityContext>`, verify algorithm/`kid`, and configure rotation. Never load private keys directly from literal strings in `application.yml`, and never print PEM data into stack traces or responses.

## 6. Rotating and Revoking Secrets by Type

Do not apply the exact same rotation pattern to every secret. The table below outlines handling suited to each role:

| Type | How to Change | Notes on Retiring the Old Value |
|---|---|---|
| Client secret of a confidential client | Issue a new secret over a secure channel, update the client and the hash on the Authorization Server | Default `RegisteredClient` holds only one `clientSecret`; if an overlap window is needed, design explicit support (e.g., client registration migration) rather than assuming two secrets work automatically |
| Database/Redis credentials | Provision new credentials, update the secret source, test connection pools, and roll out | Prefer overlapping credentials during transition; revoke the old credential once all instances have rolled over |
| Private JWT/ID Token signing key | Publish the new public key, start signing with the new private key and new `kid`, retain the old public key temporarily | Remove the old public key only after valid token lifetimes plus required clock skew/cache TTLs expire; on key compromise, follow incident response and revoke sooner |
| Keystore password | Rotate the password/keystore and update the runtime source in sync | Verify keystore opening and signing before shifting traffic |
| Secret store access credentials | Prefer short-lived/managed identities; rotate through the platform | Never store long-lived credentials in repos or images; catch identity/permission failures immediately on deploy |

### 6.1. Example Signing Key Rotation Sequence

~~~mermaid
sequenceDiagram
    autonumber
    participant Ops as Operator / Key manager
    participant AS as Authorization Server
    participant JWKS as JWKS
    participant RS as Resource Server

    Ops->>AS: Provision key-v2, keep key-v1
    AS->>JWKS: Publish public key-v1 + key-v2
    RS->>JWKS: Fetch/refresh public key set
    JWKS-->>RS: keys v1, v2
    Ops->>AS: Switch new token signing to kid=key-v2
    AS-->>RS: New JWT with kid=key-v2
    RS->>RS: Verify using public key-v2
    Note over AS,RS: Wait for key-v1 tokens and related caches to expire
    Ops->>JWKS: Remove public key-v1 once safe
    Ops->>AS: Disable/revoke private key-v1
~~~

Wait times depend on `exp`, token type, allowed clock skew, JWKS cache behavior, and revocation requirements. Emergency action may be necessary if a private key leaks; in that case, do not merely wait for tokens to expire naturally.

### 6.2. Rotation Principles for Client Secrets

With the in-memory `RegisteredClientRepository` example, updating `PORTAL_CLIENT_SECRET` and rolling out causes updated instances to accept the new secret while older instances still expect the old secret. This easily produces intermittent failures on `/oauth2/token`. Rollout design must coordinate client/server ordering and overlap windows; if simultaneous acceptance of two secrets is required, use a registration/authentication mechanism that formally supports it or perform a controlled cutover.

In production systems storing `RegisteredClient` in a DB, issuing a new secret should update the **hash** in the repository, distribute the plaintext to the rightful client over a secure channel, and record the version/timestamp. Never write plaintext secrets into change requests, issue trackers, or migration histories. Rotating a client secret does not require rotating JWT signing keys.

## 7. Preventing Leaks Across Development and Operations Lifecycles

### 7.1. Before Running the Application

- **Git and source code:** never commit `.env` files containing secrets, `application-prod.yml` with passwords, PEM private keys, real `.p12` files, live sample tokens, or exports from a secret manager. Add ignore rules for sensitive artifacts and enforce secret scanning in CI. If a secret was committed, revoke/rotate it and clean history per policy; merely deleting the line in a newer commit is not enough.
- **Build pipeline:** never put secrets in Dockerfile `ARG`s, build commands echoed to logs, test reports, or image layers. Runtime receives secrets from a dedicated distribution mechanism. Restrict who and what systems can view CI/CD configuration.
- **Developer machines:** use dedicated local secrets with least privilege and short lifetimes; never copy production secrets onto a laptop for convenience.
- **Environments:** create distinct secrets for local, staging, and production. Never share private signing keys or client secrets across environments.

### 7.2. At Runtime

- **Application:** never log the full `Environment`, `@ConfigurationProperties`, `HttpServletRequest`, `Authorization` headers, token request bodies, token responses, keystore bytes, or exceptions containing secrets. Mask values in error messages and observability tools, but do not rely solely on key-name masking.
- **Spring Boot Actuator:** restrict access to sensitive endpoints like `/actuator/env`, `/actuator/configprops`, heap dumps, and loggers; expose only genuinely needed endpoints with strict authentication/authorization. Showing unmasked values should be restricted to authorized roles under security policy.
- **OS/container:** protect volumes and file read permissions, process inspection, `/proc`, debug shells, crash dumps, and Pod exec privileges. Never pass secrets as command-line arguments, as command lines are easily observable.
- **Network:** connect to secret stores, databases, and token endpoints over TLS; verify certificates and peer identities. Never disable TLS validation in production.
- **Backups:** protect, restrict access to, and enforce retention limits matching the sensitivity of backed-up data; verify recovery procedures when secrets are lost or revoked.

### 7.3. When a Secret Leak Occurs

1. Identify the secret type, access scope, version, and potentially affected systems.
2. Cut off the leaking path: disable exposed tokens/credentials, update store permissions, and isolate the leak source per your incident response plan.
3. Issue new secrets, update consumers, roll out, and verify authentication.
4. If a private signing key leaked, treat forged token issuance as a critical incident; rotate keys, assess circulating tokens, and consider revoking/blocking tokens per your architecture.
5. Inspect logs, image registries, Git history, CI artifacts, backups, and tickets for copies; document the incident without copying the secret value.

## 8. Testing Configuration Before Production

Every test should run in an isolated environment with **synthetic secrets**, never real production secrets. A practical test matrix:

| Scenario | Expected Observable Result |
|---|---|
| `PORTAL_CLIENT_SECRET` missing from both env and volume | Startup fails with a missing-config message, **without printing other secrets** |
| `PORTAL_CLIENT_SECRET` is blank | Binding/validation rejects it or a clear fail-fast check triggers |
| Valid env variable provided | Config beans initialize; the client authenticates at the token endpoint with the test secret |
| `/run/secrets/PORTAL_CLIENT_SECRET` file present | Spring Boot reads the value via `configtree:` without baking secrets into the image |
| Required mount missing when using `configtree:` without `optional:` | Startup fails fast instead of falling back to a default secret |
| Client supplies wrong secret | Token endpoint rejects client authentication; no token issued |
| Client secret rotated | Old secret is rejected after cutoff/revocation; rollout completes without unexpected errors |
| New private signing key | JWTs with the new `kid` verify; still-valid tokens signed by the old key work during the planned overlap |
| Startup behind reverse proxy | Public `issuer` matches `https://login.example.vn` in metadata and the `iss` claim |
| Secret store fetch error or file permission error | System refuses to start with default credentials; alerts contain no secrets |
| Inspecting logs/Actuator/dumps | No client secrets, tokens, private keys, or passwords appear |

### 8.1. Checking Configuration Without Printing Values

You can verify a key's **presence** in a shell without printing its value:

~~~bash
if [ -n "${PORTAL_CLIENT_SECRET:-}" ]; then
  printf 'PORTAL_CLIENT_SECRET: present\n'
else
  printf 'PORTAL_CLIENT_SECRET: missing/empty\n'
fi
~~~

This check applies only to **env-based delivery**. For secret files, verify existence, read permissions, and non-empty length at the application or startup-script level without **printing contents**. Never run `env`, `printenv`, `set`, or `cat /run/secrets/...` to paste configs into tickets or logs. Having a properly provisioned secret does not automatically mean the system is secure: you must still test actual OAuth2 flows and authorization controls.

### 8.2. OAuth2 Flow Tests to Combine

- Run Authorization Code + PKCE with a real test-environment confidential client; verify `redirect_uri` is strictly registered, `state` matches, and the token endpoint enforces client authentication.
- Change one character in the client secret and confirm an `invalid_client`-style error with no access token/ID Token issued. Never log HTTP Basic headers or request bodies containing secrets.
- Check `issuer` at `/.well-known/openid-configuration` (if OIDC is enabled) and `/.well-known/oauth-authorization-server`, then compare against the `iss` claim and Resource Server configuration.
- Read the public JWKS from `jwks_uri` and confirm **no** private key parameters appear; valid tokens verify with the right `kid`, algorithm, and key.
- Simulate secret store permission loss, expired workload identity, or temporary endpoint unavailability to verify planned fail-fast/alert/retry behavior.
- Rehearse rotation in staging: publishing the new key, switching signing, refreshing JWKS, retiring the old key, and cutting over client secrets.

## 9. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
| Committing `client-secret: supersecret` in YAML | Secret spreads into repos, caches, images, and forks | Use placeholders, secret stores, and secret scanning; rotate immediately if leaked |
| Using `{noop}` with plaintext secrets in production `RegisteredClient` | Stores secrets in readable form and weakens data-at-rest protection | Encode with a supported `PasswordEncoder` and store hashes in a durable repository |
| Assuming `.env` files are always auto-loaded by Spring Boot | Startup misses configuration or boots with wrong settings | Inject real env vars via the launcher, or use explicit import/integration config |
| Treating Base64 Kubernetes Secrets as encryption | Anyone reading the manifest can decode them directly | Provision Secrets securely; enable encryption at rest, RBAC, and access controls |
| Generating random private signing keys on every restart | Issued tokens fail consistent verification | Persist keys durably, share consistently across the cluster, and plan rotation |
| Disabling TLS because secrets live in Vault | Secrets or tokens can leak in transit | Use TLS and peer verification across all transport links |
| Updating a Secret and assuming Spring beans picked up the new value | Running instances keep using old credentials/keys | Design rollout/reload properly; verify behavior with pools, repositories, and `JWKSource` |
| Exposing `/actuator/env` publicly for debugging | High risk of config exposure and system reconnaissance | Restrict Actuator, mask sensitive values, and audit access |
| Rotating JWT signing keys while deleting the old public key immediately | Live valid JWTs get rejected | Maintain JWKS overlap and retire per token/cache lifetimes, unless doing emergency revocation |

## 10. Deployment Checklist for a New Authorization Server

- [ ] Clearly classify issuer/client ID/redirect URI, client secrets, infrastructure credentials, keystores, and private signing keys.
- [ ] `application.yml` holds only non-sensitive configuration or placeholders; no real credentials in Git or build artifacts.
- [ ] Each environment has its own secrets and a workload identity permitted to **read only the secrets it needs**.
- [ ] Confidential client secrets are distributed over secure channels; the Authorization Server stores **hashes** in a durable `RegisteredClient` repository.
- [ ] Private signing keys are durably managed in a secret store/keystore/HSM; public JWKS serves the right keys and `kid`s.
- [ ] Missing secrets cause fail-fast startup without leaking sensitive values in errors/logs.
- [ ] Connections to secret stores/DB/token endpoints use TLS; Actuator, shells, volumes, and observability are locked down.
- [ ] Rotation runbooks and drills exist for client secrets, database credentials, and JWT signing keys.
- [ ] OAuth2/OIDC tests cover valid/invalid secrets, issuer, metadata, JWKS, and startup with missing permissions.
- [ ] An incident runbook exists for secret revocation and leak response, including auditing and purging copies in repos/logs/backups.

**Self-Check Questions**

1. Why can `PORTAL_CLIENT_SECRET` be passed via an environment variable, yet an environment variable by itself is not a secret store?
2. Why can the Authorization Server store a hash of a client secret, whereas a JWT private signing key must be protected while still usable for signing?
3. What happens when a Kubernetes Secret changes if the application's `RegisteredClientRepository` was constructed once at startup?
4. Why does rotating a JWT private signing key require planning public JWKS overlap and `kid` transitions?
5. What checks ensure secrets do not leak through CI/CD, images, Actuator, logs, or debug output?

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), covering `@ConfigurationProperties`, environment variables, and configuration trees.
- [Spring Authorization Server — Core Model/Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html), especially `RegisteredClient` and `RegisteredClientRepository`.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html), especially `AuthorizationServerSettings` and JWK Sets.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
- [The Twelve-Factor App — Config](https://12factor.net/config).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517) and [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
