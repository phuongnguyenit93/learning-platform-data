# Environment-Based Configuration Separation and Secrets Management in Spring Security Federation

## 1. Objectives and Scope

A Spring Boot application acting as an OpenID Connect (OIDC) **Relying Party (RP)** or a SAML 2.0 **Service Provider (SP)** must know how to connect to the right identity server, receive callbacks at the right public address, verify messages with the right trusted keys, and keep secret any credentials capable of granting access or impersonating identities. These values usually differ across `local`, `dev`, `staging`, and `prod`.

Copying a single configuration across all environments leads to failures: localhost redirecting to production clients, test apps trusting the production IdP, client secrets committed to Git, SPs signing SAML with a private key shared across environments, or rotated keys not reloaded by the JVM.

**Goal:** build a repeatable, secure, and testable configuration layout; clearly distinguish environment config, secrets, and trust material; properly use Spring Profiles, externalized configuration, Secret Manager/Kubernetes Secrets, and OIDC/SAML registrations; operate and rotate keys without weakening authentication.

This lesson uses Spring Boot 3.x / Spring Security 6.x as the baseline example (property names must be cross-checked against your project's actual version). URLs, domain names, and IDs in examples are **hypothetical**, not live services.

## 2. Distinguishing Regular Configuration, Sensitive Info, and Trust Material

Not every SSO-related value is a secret:

| Category | Examples in Federation | Safe to Store in Git? | Critical Protection |
| --- | --- | --- | --- |
| Non-sensitive, environment-specific config | Public base URL, issuer URI, redirect URI, SAML ACS URL, timeouts, registration names | Usually yes, per internal policy | Right domain, right tenant, aligned with IdP/OP |
| Public identifiers | OAuth2/OIDC `client_id`, SAML SP `entityID`, public X.509 certificate, JWKS public key | Yes, if it contains no restricted internal info | Accuracy and trusted provenance |
| **Application secrets** | OIDC `client_secret`, SAML signing/decryption private keys, `private_key_jwt` private key, keystore passwords | **No** | Read access control, encrypted storage, rotation, avoid logging |
| Per-session login data | Authorization code, ID/Access/Refresh Tokens, SAML Response/Assertion, session cookies | **No** | Shortest practical lifetime, restrict logs/caching, replay and audience checks |
| Trust configuration | OIDC `issuer-uri`, IdP verification keys, SAML metadata, allowed algorithms | Public parts may be | **Config integrity and provenance**: tampering can shift trust to a rogue IdP |

**A non-secret value can still be security-critical.** For example, `issuer-uri` is public, yet changing it from the enterprise IdP to an attacker-controlled IdP makes the application trust the wrong token issuer. Likewise, `client_id` is usually public; only `client_secret` must remain secret, though a wrong-environment `client_id` can break authentication or mix login flows.

### Partitioning Trust by Environment

Register **separate OIDC clients and SAML SPs per environment** in the IdP/OP, with redirect/ACS/entityID matching that environment's host. Specifically:

- `dev` uses dev IdP client ID/credentials and issuer, with zero authority to authenticate on behalf of production.
- `staging` has its own registration, ideally against a sandbox IdP with test users. Only connect staging to the production IdP with an explicit decision and proper safeguards.
- `prod` accepts only approved IdP/OP configurations and trust anchors.
- `test` prefers a mock OIDC provider/test certificates or a test-only IdP; never let automated tests read production secrets.

A **Spring profile** is merely a mechanism to select configuration and beans; it **does not create a security boundary by itself**. Secret store permissions, workload identity, networking, IdP environments, and deployment permissions determine the blast radius if an environment is compromised.

## 3. Spring Boot's Externalized Configuration Mechanism

Spring Boot resolves properties through the Spring `Environment` from many sources: `application.yml`/`application.properties`, profile-specific files, external config, environment variables, system properties, command-line arguments, and additional config imports. Higher-precedence sources override lower-precedence ones per Spring Boot's precedence rules.

Key practical rules:

1. `application.yml` holds **shared defaults and config structure**, never real secrets.
2. `application-dev.yml` and `application-prod.yml` hold **environment-specific, non-sensitive values**; active profiles control which files load.
3. Secrets are injected externally at runtime: environment variables, read-only mounted secret files, or a Secret Manager provider integrated via a supported mechanism.
4. Command-line flags/environment variables can override config files; protect deployment and CI/CD edit permissions because altering a trust property like `issuer-uri` is equally dangerous.
5. Set `spring.profiles.active` in **environment variables, launch arguments, or non-profile-specific config**. Do not place it inside `application-prod.yml` itself or a YAML document gated by `spring.config.activate.on-profile`.
6. When no profile is activated, Spring Boot uses the `default` profile. Never treat that state implicitly as dev/prod; require explicit profiles in deployment manifests.

You can launch with:

```bash
# POSIX shell example; credentials are supplied separately by the deployment system.
SPRING_PROFILES_ACTIVE=dev ./gradlew bootRun

# Built artifact example, on a production host.
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
```

The second command only illustrates profile selection; a real application also needs OIDC/SAML credentials supplied via a secure source. Never pass `--spring.security.oauth2.client.registration.corp.client-secret=...` on the command line: arguments can appear in logs, shell history, or process listings.

### 3.1. Choosing Between Profiles and Property Overrides

- Use **profiles** when a clear group of settings belongs to an environment (dev/prod issuer, public callback host, logging policy, proxy settings).
- Use **environment variables** when each deployment supplies a varying value or secret (client ID, client secret, credential location).
- Use **Secret Manager / mounted secrets** for private keys, client secrets, and mTLS credentials with independent lifecycles and access controls.
- Use `@Profile` to select bean implementations **only when behavior truly differs**; do not create separate `SecurityFilterChain` beans for dev/prod if the same login mechanism only differs by properties.

Never scatter `if (profile.equals("prod"))` logic through code to pick secrets or issuers. Loading config upfront, binding via stable rules, validating, and running one shared implementation is simpler and easier to audit.

## 4. Environment-Based OIDC Configuration Layout

Suppose a Spring Boot backend acts as an OIDC RP with registration ID `corp`, using authorization code and server-side sessions. You can organize files as:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-staging.yml
  application-prod.yml

# Must not exist in source control:
# OIDC_CLIENT_SECRET, SAML private keys, refresh tokens, secret store dumps
```

### 4.1. Shared Configuration – `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
```

Explanation:

- `corp` is the consistent `registrationId` across login initiation and callback routes.
- `client-id` is normally non-secret, yet injected from deployment so each environment receives its own value.
- `client-secret` is resolved via Spring placeholder from the environment variable **named exactly** `OIDC_CLIENT_SECRET`; never store real values in YAML.
- `redirect-uri` uses template variables supported by Spring Security. The public base URL must be resolved accurately when running behind a reverse proxy.
- Include `openid` whenever OIDC login is the goal; add minimal extra scopes needed by the application. Do not request excess scopes or refresh tokens if unneeded.

**Never set dummy defaults for secrets**, such as `${OIDC_CLIENT_SECRET:change-me}`: the system could boot with a wrong/unmanaged credential without operators noticing. Fail on missing secrets before opening production traffic.

### 4.2. Development Configuration – `application-dev.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corp:
            issuer-uri: "https://idp.dev.example.test/realms/team"

server:
  port: 8080
```

`issuer-uri` must match the `iss` value in ID Tokens issued by the dev OP and the OP's discovery metadata. `.test` URLs only illustrate configuration; replace with a real provider in your environment.

In the dev IdP console, register the matching redirect URI, such as `http://localhost:8080/login/oauth2/code/corp` if OP policy permits localhost in development. **Never** add localhost redirects to production registrations. Even though client IDs are non-secret, provision dedicated `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` for dev.

### 4.3. Production Configuration – `application-prod.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corp:
            issuer-uri: "https://login.example.com/realms/company"

server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
```

In this example, ingress/reverse proxy terminates HTTPS on the public domain and forwards requests to Spring Boot. `forward-headers-strategy: framework` lets the app read original scheme/host when proxies send standard headers, **which is safe only when ingress strips/overwrites client-supplied `Forwarded`/`X-Forwarded-*` headers from the Internet** and the backend is unreachable outside the trust boundary.

The production OP needs a dedicated registration:

- Production client ID/secret, distributed solely to the production RP workload.
- Exact public redirect URI, e.g. `https://app.example.com/login/oauth2/code/corp`.
- Production OP issuer and HTTPS certificates for the right tenant, never dev OP URLs.
- Appropriate session cookie, CSRF, timeout, and HTTPS policies, not relying solely on the two cookie properties above.

When running multiple replicas, every instance must receive the same client credentials and session strategy; if sharing sessions, protect the session store itself. Never generate new client secrets per pod when the OP registers a single credential.

### 4.4. Staging Environment

`application-staging.yml` mirrors production structure while pointing to staging's issuer/callback and registration. Avoid duplicating large blocks of `application.yml`. Override only differing properties: issuer, public host, session cookies, or timeouts if specifically required.

**QA checkpoint:** For every environment, verify the 4-tuple: `registrationId`, `clientId`, `issuerUri`, `redirectUri`. Login only works cleanly when RP configuration and OP registration match, and all endpoints loaded by the RP belong to the trusted OP.

## 5. How Are Secrets Supplied at Runtime?

### 5.1. Environment Variables

With `${OIDC_CLIENT_SECRET}`, an environment variable named `OIDC_CLIENT_SECRET` is passed into the process by the deployment platform. Spring Boot reads it from `Environment` when binding OAuth2 client registrations. No manual `System.getenv` code is needed to populate builders.

However, environment variables **are not an absolute vault**: depending on OS, container permissions, diagnostic tools, or operational logging, values can leak via crash dumps, diagnostic endpoints, environment inspection commands, or process-read permissions. Therefore:

- Never put secrets in `Dockerfile ENV`, build `ARG`s, image layers, committed `.env` files, or pipeline logs.
- Never run `printenv`, `env`, `set`, or `echo $OIDC_CLIENT_SECRET` in CI logs to "check" secrets.
- Never dump raw `Environment`, `ClientRegistration` objects, auth headers, or token endpoint requests into logs.
- Restrict who can modify deployment secret values and who can inspect processes/containers.
- Prefer controlled secret injection over plaintext in repositories or public manifests.

A **safe check** verifies whether a variable **is present** and endpoints bind cleanly without printing the value. For example, operational status might report `OIDC_CLIENT_SECRET configured: yes`, and even that should stay in secure internal logs.

### 5.2. Mounted Secret Files and `configtree:`

Spring Boot can load a directory where **filenames become property keys** and file contents become property values. This fits Docker/Kubernetes volumes or secret agents mounting read-only files.

When using **configtree directly**, `application-prod.yml` can declare:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/oidc/"
```

The directory must exist in production since `optional:` is omitted. If the app must run without mounts in dev, declare this import only in the prod profile or use another approach in dev. On the example host, two files exist:

```text
/run/secrets/oidc/
  spring.security.oauth2.client.registration.corp.client-id
  spring.security.oauth2.client.registration.corp.client-secret
```

Each file holds **exactly one value**; for instance, the second file holds the client secret from the secret store. Spring Boot maps dotted filenames to the corresponding properties. With **this option**, `client-id` and `client-secret` can be omitted from `application.yml` so secret files supply the standard properties directly. Avoid maintaining two competing value sources with unclear precedence.

*Abridged* Kubernetes Deployment mount example; Secret `rp-oidc-prod` must be provisioned and access-controlled by secret infrastructure beforehand:

```yaml
spec:
  template:
    spec:
      containers:
        - name: rp
          image: registry.example.test/federation-rp:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
          volumeMounts:
            - name: oidc-credentials
              mountPath: /run/secrets/oidc
              readOnly: true
      volumes:
        - name: oidc-credentials
          secret:
            secretName: rp-oidc-prod
```

This is the `spec` portion of a Deployment manifest, not a complete Deployment (missing `apiVersion`, `kind`, `metadata`, `selector`, etc.). Both keys in the Kubernetes Secret must match the desired filenames. Kubernetes Secrets can appear as Base64 in manifests: **Base64 is encoding, not secure encryption**. Enforce RBAC, restrict `get/list/watch` permissions, enable etcd encryption-at-rest, and lock down volume read permissions.

File mounts work well for long credentials and PEM private keys while keeping secrets out of process environments, yet **files remain readable inside the container by privileged processes**. Filesystem permissions, service accounts, container isolation, and secret-provider auditing remain critical.

### 5.3. External Secret Managers

Systems like HashiCorp Vault or cloud provider secret managers supply credentials through one of these patterns:

1. **Pre-startup secret injection:** an init container/agent or orchestrator authenticates via workload identity and provides mounts/env vars.
2. **Spring ConfigData integration or official extension:** the application fetches secrets during `Environment` initialization using a version-compatible integration library.
3. **Runtime API client:** the application makes authenticated calls to the secret manager with caching/proactive refresh if dynamic rotation is truly required.

Designate **one primary source of truth** per secret, documenting who updates it, when the app picks it up, and how rotation is verified. Never add integration libraries just because they say "secret manager" when dynamic refresh is unneeded; transport, permissions, workload tokens, and failure fallbacks must be explicitly designed.

**Never store credentials used to log into the Secret Manager in Git.** Use workload identity, service accounts, or a platform-managed short-lived credential issuer.

## 6. SAML 2.0: Separating Metadata, Signing Keys, and Decryption Keys per Environment

SAML involves multiple trust-related values. In Spring Security Servlet, `RelyingPartyRegistration` combines SP and IdP details:

- **IdP metadata / entity ID / SingleSignOnService URL:** identifies the IdP trusted by the SP and where to send AuthnRequests. This is trust config; public URLs/certificates are not secrets, yet must come from trusted sources.
- **IdP verification certificate:** public key used by the SP to verify `SAMLResponse`/`Assertion` signatures; must support certificate rotation.
- **SP signing private key + certificate:** SP signs `AuthnRequest`/logout messages when required by profile and partner; the private key is a secret.
- **SP decryption private key + certificate:** SP decrypts `EncryptedAssertion` when encrypted by the IdP for the SP; the private key is a secret.
- **SP entity ID + Assertion Consumer Service (ACS) URL:** normally differs between dev/prod and must be accurately registered at the IdP.

**Illustrative** configuration example under `application-prod.yml` if credentials are mounted via filesystem:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp-saml:
            entity-id: "https://app.example.com/saml2/service-provider-metadata/corp-saml"
            acs:
              location: "https://app.example.com/login/saml2/sso/corp-saml"
            assertingparty:
              metadata-uri: "https://idp.example.com/metadata"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-signing.key"
                  certificate-location: "file:/etc/saml/sp-signing.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-decryption.key"
                  certificate-location: "file:/etc/saml/sp-decryption.crt"
```

This configuration only works if the SAML partner is set up accordingly, the IdP exposes trusted metadata, and the files actually exist. When the IdP does **not** require signed AuthnRequests or send EncryptedAssertions, those credentials can be omitted; avoid adding private keys without a real requirement. Across Spring Security/Spring Boot releases, verify property names and `acs` syntax against your exact dependency version; an alternative is building `RelyingPartyRegistration` in Java config and binding paths from external configuration.

**Never rotate an SP private key solely by swapping the public certificate.** The IdP must receive the new public certificate at the right time; production SP instances must hold the matching private key, and both parties should coordinate an overlap window if supported. Signing and decryption keys can follow separate rotation schedules; private keys must never live on the `classpath` of distributed JARs.

### Why Shouldn't Environments Share SAML Keys?

If dev is compromised, a dev SP signing private key could be used to sign requests within the dev IdP's trust scope. If that same key is also trusted in production, the blast radius expands. Likewise, a shared decryption private key exposes assertions across multiple environments. Therefore separate keypairs, IdP trust metadata, SP entity IDs, and ACS URLs per environment; never copy a production `.p12` onto a laptop for "quick testing".

An IdP verification certificate may be public, yet **the process for updating that certificate** must be controlled because trusting the wrong key causes the SP to accept signatures from an unauthorized party.

## 7. Fail-Fast Configuration Checks Without Exposing Secrets

Errors to catch **before serving traffic**:

- Invalid active profile, such as a production workload running under the dev profile.
- Missing client ID/secret or issuer URI, malformed URL, wrong protocol, or discovery metadata mismatch.
- Unreachable token endpoint/JWKS endpoint; DNS/TLS/truststore errors.
- OAuth2 redirect URI/registration rejected by the IdP.
- Unreadable SAML IdP metadata, SP entity ID/ACS mismatch at IdP, missing PEM keys/certificates, or mismatched key/cert pairs.
- Decryption enabled without decryption credentials, or untrusted IdP verification certificate.
- Local test configuration allowing authentication bypass still present in production.

For custom properties, Spring Boot provides `@ConfigurationProperties` and Bean Validation to enforce `@NotBlank`, `@NotNull`, URL formats, etc. Example class **for use inside a Spring Boot application**, not a standalone Java SE program:

```java
package demo.federation.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.sso")
public record SsoProperties(
        @NotBlank String expectedIssuer,
        @NotBlank String publicBaseUrl
) { }
```

Register the record with `@ConfigurationPropertiesScan` on the `@SpringBootApplication` class or `@EnableConfigurationProperties(SsoProperties.class)` in configuration; add `spring-boot-starter-validation` in Boot 3.x environments. If `app.sso.expected-issuer` or `app.sso.public-base-url` is missing or invalid, binding validation fails startup naming the offending property.

**Important distinction:** `SsoProperties` is an example of **custom configuration** and does not automatically replace `spring.security.oauth2.client...`. Without Java code consuming it to validate registrations, it is merely validated data. Avoid creating a "second source of truth" for the issuer; ideally bind a single config source to build registrations or enforce cross-property consistency.

When adding startup checks, error messages should look like: `Missing required secret for OIDC registration 'corp'` or `Unexpected OIDC issuer for profile 'prod'`; never embed secrets/tokens/PEMs or full request bodies into exceptions. Validating tokens against the right issuer/audience/signature remains the authentication library's job; config validation does not replace protocol checks.

## 8. Precedence Order and Override Surprises

Suppose `application-prod.yml` declares:

```yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corp:
            issuer-uri: "https://login.example.com/realms/company"
```

If the deployment simultaneously sets the environment variable:

```text
SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_CORP_ISSUERURI=https://other.example.test
```

Depending on Boot's relaxed binding rules, the environment variable can bind and override the issuer property. A common env naming pattern strips hyphens within segments and replaces dots with underscores. This underscores a critical point: **anyone permitted to edit deployment variables can alter trust config, even if the production YAML in Git never changed**.

Never rely on assuming "the prod file always wins". Command-line, environment, or config import sources can alter the outcome per Boot precedence rules. To verify:

1. List property sources that can supply values (without printing secret values).
2. Confirm the active profile and verify `application-{profile}.yml` actually loaded.
3. Verify the final resolved values of **non-sensitive properties** such as issuer, public base URL, redirect URI, and SAML entity ID via access-controlled startup validation/health checks.
4. Never expose `/actuator/env` or `/actuator/configprops` publicly; if required internally, enforce authentication/authorization, sanitization, and network protection. Never set `show-values=ALWAYS` to debug secrets.

A property can look right in a file yet be wrong at runtime due to deployment overrides. Diagnostics should start from **protected runtime effective configuration**, not just committed YAML.

## 9. Secret Lifecycle Management and Rotation

Credentials rotate periodically or after incidents. "Just updating the secret in the vault" is rarely enough because many applications load secrets into `ClientRegistration`, `RelyingPartyRegistration`, or `Environment` **once at startup**.

### OIDC Client Secret

A safe secret rotation process typically involves:

1. Check whether the OP supports multiple active secrets per client, or whether a new client registration is needed.
2. Create the new secret at the OP and save a new version in the secret store, without exposing it in logs/tickets.
3. Grant the target environment's workload access to the new secret.
4. Roll out/restart so **every replica** loads the new value; verify backend token exchange succeeds.
5. Revoke the old secret only after no instances still use it and normal login flows are confirmed.
6. If secret compromise is suspected, switch to an incident rotation workflow with a shortened overlap, investigation, and impact containment.

If the OP can only hold **one active secret**, rotating it may cause a brief disruption; prepare a synchronized rollout, maintenance window, or parallel registration strategy depending on IdP capabilities. Never assume secrets automatically refresh in Spring Boot.

### OIDC ID Token Signing Key / JWKS

This is the **OP's signing key**, not the RP's client secret. When the OP rotates signing keys, the RP normally fetches new keys from the trusted issuer's JWKS endpoint and handles caching per library settings. Never accept arbitrary JWKS URLs or `kid` values from unverified tokens; issuer, algorithms, and audience must still be validated. Test JWKS reload/caching behavior in staging first.

### SAML Certificates / Private Keys

- **IdP rotates signing certificate:** update SP trust config from verified metadata/certificate; if supported, keep both old + new certificates during the overlap window.
- **SP rotates signing private key:** upload the matching new public certificate to the IdP, deploy the new secret to the SP, and handle the window where the IdP accepts both keys if supported.
- **SP rotates decryption key:** coordinate the IdP encrypting with the new certificate while the SP can still decrypt valid assertions encrypted for the old certificate.
- Signing and decryption keys can be separated to limit usage scope and lifecycle.

A successful rotation must prove valid SSO logins, logout (if enabled), callbacks, signature validation, and related sessions work smoothly during the transition window.

## 10. Preventing Secret Leaks in Logs, Git, and CI/CD

### Repository and Developer Workstations

- Commit only example templates with **variable names**, never real values; add `.env.local`/`secrets/` containing real data to ignore rules and configure secret scanning.
- Enable secret scanning in pre-commit hooks and CI; if a secret is detected in Git, **revoke/rotate the actual secret**. Deleting a commit or rewriting history does not guarantee the secret wasn't copied.
- Never store SAML private keys, keystore passwords, or client secrets in `src/main/resources`, as files there can be packaged into JARs and widely distributed.
- Never place real credentials in unit test snapshots, golden files, issue trackers, or documentation.

### CI/CD and Runtime

- CI artifact builds **do not need production secrets** when applications read secrets at runtime; separate build identity from deployment identity.
- Gate prod deploy jobs with proper permissions/approvals; mask secrets in logs, recognizing **masking fails against transformed data or stack traces**.
- Never run builds/tests under service accounts holding production secret read access unless truly required.
- Separate "deploy artifact" permissions from "read all secrets". A workload should only read secrets for its own environment and application.
- Audit request/response logging on proxies and backends; Authorization headers, cookies, codes, ID/Access/Refresh Tokens, and SAMLResponses can be highly sensitive.
- For mounted files, grant minimal process read permissions and set up auditing/alerts on unusual secret changes.

**Operational fields safe to log:** environment name, registration name, configured issuer (if policy allows), network/token error category, PII-free request correlation IDs, public certificate validity dates, and "secret present" status. Never print secret values, raw tokens, assertions, or private keys.

## 11. Deployment and Pre-Production QA Matrix

| Check | Dev / Staging | Production |
| --- | --- | --- |
| Profile | Proper `dev`/`staging` | `prod` only; block default/dev per policy |
| OIDC client | Dedicated client on test IdP | Production client, secret from controlled store |
| Issuer/JWKS | Test environment URL and token `iss` | Pinned issuer/metadata from approved prod OP |
| Redirect URI | Dev/staging host; localhost only in dev if permitted | HTTPS public host, matching registration |
| SAML SP/IdP | Separate entity ID/ACS/certificate | Prod entity ID/ACS/certificate; private keys never packaged |
| Secret exposure | Repo/pipeline scanning; mock secrets for tests | RBAC, filesystem/workload identity, audit, and rotation |
| Proxy/cookie | Measure generated scheme and callbacks | Trusted forwarded headers, TLS, Secure/HttpOnly/SameSite per flow |
| Logging | Controlled diagnostics only | Redact tokens/codes/assertions, lock down Actuator and logs |
| Startup | Catch wrong profile/missing config | Fail-fast on bad trust/secrets; clear rollback |
| Rotation | Rehearse changing secrets, IdP certs, SAML keys | Runbook ready, overlap if supported, verified across all replicas |

### Three Especially Valuable Integration Tests

**Test A – Wrong issuer.** Use the dev IdP to issue an ID Token with a dev `iss`, while the RP is configured to trust the prod issuer. Expected result: login is rejected because the token fails issuer/verification policy; never "fix" by disabling signature or audience checks.

**Test B – Missing client secret.** Start production without supplying the secret (or with a required mount path missing). Expected result: startup/deployment health checks refuse to bring the app into service; logs state only the missing property/registration name without printing sensitive values. Design explicit fail-fast checks because not every empty config is caught at the same time across releases.

**Test C – Rotating secrets across multiple replicas.** Perform rotation at the OP/secret store, roll out replicas, verify continuous logins, and confirm no instance still uses the old secret before revoking it. Expected result: zero `invalid_client` errors after rollout, no code changes required, and alerts distinguish configuration errors from network errors.

## 12. Common Failures and How to Investigate

| Symptom | Possible Cause | Proper Resolution |
| --- | --- | --- |
| OIDC returns `invalid_client` at Token Endpoint | Wrong client ID/secret, rotated secret, wrong auth method, or wrong tenant | Verify registration and secret version with OP; check all replicas; never print secrets |
| `redirect_uri_mismatch` or wrong HTTP/HTTPS callback | Misconfigured URL, ingress fails to handle trusted forwarded headers | Inspect actual redirect, public base URL, proxy headers, and OP callback list |
| Works locally yet prod points to dev IdP | Wrong profile or environment override on `issuer-uri` | Check active profile and effective property source; fix permissions/deployment |
| Cannot load discovery/JWKS | DNS/TLS/truststore, outbound proxy, wrong metadata URL | Verify backend connectivity to OP and truststore; never disable TLS verification |
| SAML `Invalid Signature` | Wrong IdP verify cert or unrotated metadata | Fetch metadata/cert from trusted channel, verify trust and validity period |
| SAML decrypt failed | Missing/wrong private decryption key, IdP using another certificate | Check public certificate + private key pair and rollout order |
| Wrong SAML `Recipient`/`Destination` | Wrong ACS/entity ID due to deploy host, reverse proxy, or profile | Align host, route, IdP registration, and forwarded headers |
| Secret updated in vault yet app still uses old value | App reads at startup with no runtime refresh | Controlled rollout/restart or implement proper designed refresh |
| Secret appears in CI logs | Environment debug script/command or plugin printing properties | Stop printing, restrict log access, revoke/rotate secret, scan related history |

When debugging, separate **configuration layer**, **TLS connectivity**, **SSO protocol**, and **application session**. A token endpoint TLS certificate error is never solved by disabling ID Token signature validation. A SAML assertion with the wrong audience is never solved by accepting every audience.

## 13. Practical Workflow from Local to Prod

1. **Define trust boundaries.** List RPs/SPs, OPs/IdPs, proxies, issuers, callbacks/ACS, and user groups for `dev`, `staging`, and `prod`. Create matching registrations at the IdP for each environment.
2. **Design file layout.** Create `application.yml` with shared settings and placeholders, and `application-{profile}.yml` with non-secret issuers/hosts. If using configtree, place imports in the right profile.
3. **Separate secrets from source.** Client secrets and private keys reside in a secret manager or read-only mounts, provisioned via least-privilege workload identity.
4. **Design startup validation.** Check profiles, required properties, URI/key formats, and environment issuer boundaries; errors must be clear without exposing secrets.
5. **Register callbacks and metadata.** OIDC redirect URIs and SAML entity IDs/ACS/certificates must match the real public host, especially behind reverse proxies.
6. **Run negative tests.** Test missing secrets, wrong issuers, unrotated certs, wrong ACS, and network blocks; ensure the system **fails closed** with sufficient diagnostic info.
7. **Deploy staging then prod.** Verify multiple replicas, zero secret leaks in logs, health, tracing, and Actuator; monitor `invalid_client` and JWKS/SAML verification failures.
8. **Document lifecycle.** Who owns each secret, rotation schedule, overlap capabilities, consuming services, rollback steps, and incident response if a key is compromised.

For new environments, avoid "copy YAML and swap a few strings": verify **identity provider registrations, trust anchors, and workload identities** alongside config files.

## 14. Self-Assessment Questions

**1. Do Spring Profiles protect production secrets from development environments?**  
No. Profiles select configuration. Security boundaries must come from secret store permissions, workload identities, infrastructure isolation, and separate IdP registrations.

**2. Should `client_id` and `client_secret` both be committed into `application-prod.yml`?**  
`client_id` is usually non-secret and can live in managed config if policy allows. `client_secret` is a real credential and must be supplied outside source code via a protected mechanism.

**3. Why must the issuer URI be controlled even though it is not a secret?**  
Because the issuer is part of the trust boundary: pointing the issuer to an unintended system can cause the RP to trust the wrong party.

**4. Does mounting a Kubernetes Secret as a file and editing the Secret automatically update a running Spring Boot `ClientRegistration`?**  
Do not assume it does. The mounted file may update while bound objects and properties were loaded at startup; verify refresh mechanisms or perform a rollout/restart.

**5. Can we bundle a SAML private key into the JAR so dev and prod share it for convenience?**  
No. A private key inside an artifact spreads everywhere the artifact is distributed and destroys environment isolation. Supply separate private keys via a properly permissioned secret manager/mount.

**6. Once Spring Boot no longer reports `invalid_client`, is federation proven secure?**  
No. You must still verify TLS, issuer/audience, state/nonce/PKCE, SAML signatures/certificates, replay, callbacks, and protocol-specific session policies.

## 15. Standard References

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): source precedence, property placeholders, `configtree:`, and external files.
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): `spring.profiles.active`, profile-specific files, and declaration constraints.
- [Spring Security – OAuth 2.0 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `ClientRegistration`, `client-id`, `client-secret`, issuer, and redirect URI.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, metadata, verification, and decryption credentials.
- [Spring Security – SAML 2.0 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): signing credential property examples and IdP configuration.
- [Kubernetes – Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): secret delivery methods, encoding limitations, RBAC, and volumes.
- [OWASP – Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): storage, auditing, rotation, and least-privilege access.
