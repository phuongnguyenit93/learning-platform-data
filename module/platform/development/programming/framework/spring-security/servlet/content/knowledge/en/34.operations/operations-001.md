# Protecting Credentials, Signing Keys, Client Secrets, and Environment-Specific Configuration

> **Context:** Java 17+, Spring Boot 3.x, Spring Security 6.x on the Servlet stack. This is an operations guide: what secrets are, protecting passwords and credentials, managing JWT signing keys and OAuth2/OIDC client secrets, environment-specific application configuration, rotation, testing, and responding when secrets are exposed. The credentials in the examples are mock local/test data only and cannot be used in production.

## 1. Security Goals and Boundaries

An application with a correct `SecurityFilterChain` can still be compromised if a client secret is committed, a private key is inside the image, a production password is logged, or staging shares the same signing key with production. Authentication security requires both **correct code** and a **controlled secret lifecycle**.

```text
User / client application
           |
       HTTPS/TLS
           |
     Spring Security Servlet
       +-- Form/Basic login: verify password hash
       +-- OAuth2 Login: confidential client uses client secret
       +-- JWT resource server: uses public key of trusted issuer
       +-- Authorization: applies roles/scopes/claims after authentication
           |
           v
     Business data

Operations layer:
  Vault/Secret Manager + IAM workload
  KMS/HSM/PKI + key lifecycle
  Separate config for dev/test/staging/prod
  CI/CD + secret scanning + logging policy + audit
```

Distinguish three questions: **which secret must be kept confidential?**; **which party is actually allowed to use it?**; **when and how can it be revoked/rotated?** Do not equate any value containing the word "key" with a private key that has signing privileges or with a public verification key.

| Object | Role | Must keep secret? | Who should hold it? |
|---|---|---|---|
| User password | Login proof | Yes | User; backend only stores salted adaptive hash, never raw |
| Service password / API key | Machine, DB, LDAP bind, partner credential | Yes | Least-privileged workload via secret store |
| OAuth2 `client_id` | Identifies the client | Usually no | Client registration and application configuration |
| OAuth2 `client_secret` | Authenticates a **confidential client** | Yes | Backend server, never sent to the browser |
| JWT private signing key | Signs issuer tokens | **Highly sensitive** | Authorization Server/IdP or KMS/HSM with signing permissions |
| JWT public verification key | Verifies asymmetrically signed tokens | Does not need to be hidden | Resource server fetched from trusted JWKS/issuer |
| HMAC signing secret | Both signs and verifies HMAC JWTs | Yes | Only parties trusted as an issuer |
| TLS private key | Proves TLS endpoint identity | Yes | TLS terminator/keystore/operational PKI |
| OIDC issuer/JWKS URL | Defines the trust source | Not necessarily secret | Approved configuration, never taken arbitrarily from a token |

**A signed JWT is not an encrypted JWT.** A standard JWT payload can be decoded and read; do not include passwords, access keys, secrets, or unnecessary PII in claims. Verifying the signature is also insufficient if you skip checking issuer, audience, expiration, and authorities.

## 2. Threat Model: Where Can Secrets Be Exposed?

| Surface | Common mistake | Required control |
|---|---|---|
| Git and pull requests | Committing `.env` or `application-prod.yml` containing passwords or private keys | Do not store raw secrets, secret scanning, revoke upon detection |
| CI/CD | `echo $TOKEN`, debug shell tracing, or artifacts with resolved config | Secret scoping and masking, never print credentials |
| Docker image | `COPY private-key.pem` or `ENV PASSWORD=...` | Runtime injection/secret mount, do not bake into layers |
| Kubernetes | Secrets are only Base64-encoded; overly broad service account read access | RBAC, encryption at rest as configured, audit, strict mount permissions |
| Runtime memory | Heap dumps, thread dumps, actuator `env`/`configprops` | Restrict diagnostics, retention, dump read permissions |
| Access log | `Authorization`, `Cookie` headers, login body, query containing tokens | Redaction at proxy/app/tracing/client |
| Developer laptop | Shell history, command args, backup config files | Local secret manager, do not use production credentials |
| Staging/test | Copying production DB, IdP registration, or signing keys | Separate secrets, issuers, keys, data, and accounts |
| Network | HTTP Basic without TLS, plaintext LDAP simple bind | Verified TLS and restricted trust boundaries |
| SPA/mobile | Client secret embedded in JavaScript or binary | Public OAuth client + Authorization Code/PKCE, no embedded secret |

Note that a secret can exist simultaneously in Git history, CI caches, image layers, logs, and copies on developer machines. **Deleting a secret from the current file does not revoke it.** If exposed, you must revoke/rotate it at the issuing source and check all copies.

## 3. Secret Lifecycle and Operator Responsibilities

```text
Create using a cryptographically secure source
         |
Assign owner + purpose + environment + expiration
         |
Store in vault/KMS/HSM or a controlled mechanism
         |
Provision to workload by identity and least privilege
         |
Use in memory, never log/echo
         |
Audit and detect drift
         |
Rotate with rollback/overlap when permitted
         |
Revoke old key and verify remaining client usage
         |
End lifecycle, delete copies, and update inventory
```

A minimal inventory needs secret name/reference, type, scope, environment, owner, issuer, consuming applications, access mechanism, expiration/rotation, revocation procedure, and incident contact. **Do not store secret values in the inventory.**

Principles:

1. **Least privilege.** The application's DB account must not have DBA privileges; an LDAP lookup account must not be allowed to change other users' passwords; a CI job only receives secrets for its specific environment.
2. **Do not share across trust boundaries.** Staging must not use the same production signing private key, OAuth client secret, or DB password.
3. **Fail closed.** A missing secret or unreachable vault must cause a safe startup/connect/authentication failure, never falling back to `demo123` or `admin/admin`.
4. **Prefer short-lived identity.** Use workload identity/OIDC federation or managed identity for KMS/DB when supported by the platform; reduce static long-lived keys.
5. **Rehearse rotation.** Having a new secret without a reload/cache/restart process and revoking the old secret is not complete.
6. **Separation of duties.** Code configures the mechanism, platform provisions the secret, owner approves scope, operations manages audit/incidents.
7. **Do not treat env vars as a vault.** Env vars are convenient but can leak via process/container inspection, crash dumps, and debug tools.

## 4. Protecting User Passwords

### 4.1. Slow Salted Hash, Never Store Recoverably

Login passwords usually only need to be **verified**, not decrypted. Use a salted password hashing algorithm with a cost factor such as Argon2id, scrypt, bcrypt, or PBKDF2 according to policy/resources; choose cost with performance measurement, check input length, and define a migration process.

Do not use plain `SHA-256(password)`, MD5, Base64, or reversible AES as the default password storage method. Salt reduces the effectiveness of precomputed hash tables; password hashing algorithms increase offline brute-force cost.

Spring Security provides `PasswordEncoder` and `DelegatingPasswordEncoder`. Example bean suitable when you want to store an algorithm prefix like `{bcrypt}` to support migration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
class PasswordHashConfig {
    @Bean
    PasswordEncoder encoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
```

This is a **Spring configuration snippet**, not a standalone program. In a real application, `UserDetailsService`/data access returns the **stored hash**; the authentication provider uses `encoder.matches(raw, stored)` to verify.

Example check with a fixture:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
String saved = encoder.encode("local-test-password-only");

boolean correct = encoder.matches("local-test-password-only", saved);
boolean incorrect = encoder.matches("wrong-password", saved);

// correct == true; incorrect == false
// Do not assert that the hash is a fixed string because the salt changes each time.
```

Bcrypt has a byte-length limit that must be considered with long-password policies and Unicode; do not silently truncate, pre-hash, or change encoding without an explicit design. For password hash migration, retain verification of old hashes during the transition period, then safely upgrade the hash when the user authenticates validly.

### 4.2. Caring for Credentials at Login

- Only accept passwords over HTTPS; never place passwords in URLs/queries, redirects, audits, or exceptions.
- HTTP Basic uses Base64, **not password encryption**; use it only over a trusted TLS connection.
- Do not log `Authorization`, `Cookie`, `Set-Cookie`, form passwords, authorization codes, refresh/access tokens, or session IDs.
- Rate-limit login attempts, defend against credential stuffing, and handle account lockout and resets securely. `PasswordEncoder` does not do these automatically.
- MFA and step-up must be policy-driven; a user with a valid password is not automatically authorized for sensitive transactions.
- Do not have production admin accounts with generated/demo passwords or hardcoded fallback passwords.

If using LDAP bind, user credentials must traverse LDAPS/StartTLS properly and the service bind account must have minimal privileges. If using SSO, the backend usually does not need to receive the IdP password; use OIDC/SAML and keep the credential boundary at the IdP.

## 5. OAuth2/OIDC Client Secret: Server-Side Only

`client_id` is the client identifier; `client_secret` is the **confidential client** credential when the protocol and IdP use this client authentication method. It is **not** a user password, access token, or JWT signing key.

| Application type | Can hold a secret? | Integration approach |
|---|---|---|
| Spring MVC server-side web app | Yes, if the secret stays on the backend | OIDC Authorization Code and client authentication per IdP |
| Backend service-to-service | Possibly, depending on workload platform | Client credentials or workload identity/mTLS/private_key_jwt when appropriate |
| JavaScript SPA in the browser | No | Public client Authorization Code + PKCE |
| Native/mobile client | Embedded secret cannot be treated as confidential | Public client + PKCE, protected redirect URI |

Any secret embedded in a JS bundle, source map, or mobile binary can be extracted. Minification/obfuscation does not change this boundary.

### 5.1. Spring Boot OIDC Configuration Reading Secret from Runtime

With `spring-boot-starter-oauth2-client`, a server-side confidential client can be configured in `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          corp:
            issuer-uri: ${OIDC_ISSUER_URI}
```

This is an **illustrative** configuration requiring an OIDC IdP with a real issuer, client registration/redirect URI, and secret. Login cannot run without an IdP. Each environment uses its own registration; do not put real secrets into YAML and commit them.

`OIDC_CLIENT_ID` and the issuer URI are not necessarily secrets, but they must still be **trusted, governed values**. `OIDC_CLIENT_SECRET` must only be provisioned to the backend server; never return it via REST responses, templates, or static resources. When configuration requires a secret, do not set a fake default in production.

### 5.2. Do Not Mix Up Token Types

- `client_secret`: authenticates a confidential client at the token endpoint when configured.
- `authorization_code`: short-lived proof in the callback; do not log callback queries containing the code.
- `access_token`: bearer credential granting API access; do not log or send it to the wrong audience.
- `refresh_token`: used to obtain new tokens; requires secure storage, rotation/revocation, and tight scoping.
- `id_token`: OIDC identity assertion; do not substitute it for an access token to call arbitrary APIs.

Exposing a client secret may allow client impersonation under certain flows and conditions; impact depends on grants, scopes, redirect URIs, and client authentication. Rotation must be performed **on the IdP/authorization server** as well as in app config, not just by changing an env var.

## 6. JWT Signing Keys and Separating Issuer from Verifier

### 6.1. Asymmetric Key Pair

`RS256`/`ES256` and asymmetric signing algorithms allow the issuer to keep the private signing key while the resource server only needs the public verification key:

```text
Authorization Server / IdP:
  PRIVATE SIGNING KEY
  +-- sign JWT with kid/alg
            |
            v
       Signed JWT
            |
            v
Spring Security Resource Server:
  Trusted issuer + JWKS public keys
  +-- verify signature
  +-- validate iss/exp/nbf/aud and token contract
  +-- map scope/roles -> authorities
            |
            v
       API authorization
```

**A resource server that only verifies tokens does not need the IdP's private key.** Do not copy the private signing key into every microservice. If an application is also an authorization server, it needs a key ownership model, key usage permissions, HSM/KMS where appropriate, auditing, and rotation.

With HMAC (e.g., HS256), the same symmetric secret is used for both signing and verifying; every party sharing the secret can issue valid signatures. Choose based on the threat model, not merely convenience.

### 6.2. JWKS, kid, alg, and Claims

- `kid` is used to select a key from a trusted JWKS; `kid` itself is **not proof of trust**.
- Do not arbitrarily take a JWKS/`jku` address from a client-sent token and download keys from the Internet.
- Only accept `alg` values in a server-side allowlist; do not trust `alg` in the header as dynamic policy.
- `iss` must match the trusted issuer; `aud` must contain the audience intended for the API; `exp`/`nbf` must check validity windows with bounded clock skew.
- Mapping scopes/claims to `GrantedAuthority` must follow an explicit policy; a valid token signature does not automatically grant admin privileges.
- Signed JWT payloads can be read; do not put secrets inside claims.

Example `application.yml` for a resource server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${JWT_ISSUER_URI}
```

This configuration requires `spring-boot-starter-oauth2-resource-server` and a valid issuer with JWKS/metadata. Spring Security can validate the signature and default claims, but **configuring `issuer-uri` alone does not prove that the API's audience is validated per contract**. Configure an audience validator appropriate for your version/deployment.

### 6.3. JWT Signing Key Rotation

Typical planned rotation:

1. Generate a new key pair in KMS/HSM or a cryptographically secure key generation mechanism and assign a new `kid`.
2. Publish the new public key in JWKS while keeping the old public key.
3. Start signing new JWTs with the new private key; verify that resource servers validate them.
4. Keep the old public key for the period required by token TTL, clock skew, and JWKS caching to avoid breaking valid tokens.
5. After old tokens expire/are no longer accepted, remove the old key and revoke the old private key properly.
6. Audit signing uses, errors, key versions, and the rollback plan.

This is a **planned rotation**. If the old private key is **suspected of compromise**, prioritize emergency revocation/invalidating tokens per incident policy, even if it forces re-login or brief disruption; never prolong an exposed key solely for zero-downtime.

TLS private keys and JWT signing keys serve different purposes; do not reuse a single private key across multiple purposes without dedicated design and review.

## 7. Environment-Specific Spring Boot Configuration

### 7.1. What Belongs in Git

Keep in the repository:

- Property names and `application.yml` structure, without real secrets.
- `application-dev.yml`/`application-staging.yml`/`application-prod.yml` containing only non-secret settings, approved endpoints, or **references** to runtime secrets.
- Documentation of required secrets, owners, and permissions, without secret values.
- Test fixtures using fake passwords/keys, clearly marked local/test only.
- Tests ensuring that a missing secret causes deployment to fail.

Do not commit raw `.env` files, production `.p12`/PEM private keys, client secrets, DB/LDAP passwords, access/refresh tokens, backup keys, resolved `Environment` outputs, or dumps containing credentials. `.gitignore` helps prevent mistakes but does not erase Git history. If a secret has been pushed to a remote, **revoke/rotate** it and audit clones/artifacts.

### 7.2. Property Placeholders and Fail Closed

Integration service configuration template:

```yaml
app:
  outbound:
    base-url: ${PARTNER_API_BASE_URL}
    api-key: ${PARTNER_API_KEY}

spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

This is a **template**, not a standalone runnable Spring Boot application without a matching datasource/client. Variables are supplied from runtime/Vault. Do not add fallbacks like `${DB_PASSWORD:admin}` to "help production avoid startup errors". A missing secret must fail in a controlled way, never silently downgrade security.

Spring profiles are not a security boundary: naming a file `application-prod.yml` does not guarantee the file is confidential. Properties follow Boot precedence across files, profiles, env vars, command-line arguments, config imports, and test properties; verify **effective values and sources** using authorized tooling that does not print secrets.

### 7.3. Secret Manager, Env Vars, and configtree

Common provisioning sources: cloud secret managers, Vault, KMS/HSM, platform workload identity, runtime-mounted files, and environment variables. Env vars are convenient but are not a vault by themselves; they can leak via process inspection, crash dumps, CI output, or diagnostics.

Spring Boot supports `configtree` to read filenames in a directory as property keys:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

If the orchestrator mounts `/run/secrets/app.security.client-secret`, the application can bind the property `app.security.client-secret`. Mounted files must have restricted read permissions; configtree **does not encrypt** file contents. Locally, `optional:configtree:/run/secrets/` may fit when the directory is absent; in production, require mandatory secrets and fail closed when absent.

In Kubernetes, `Secret.data` is Base64-encoded, **not encrypted**. RBAC, namespace boundaries, encryption-at-rest, auditing, and mount permissions determine the protection level. Do not grant every service account read access to every secret.

**A Java `String` containing a secret cannot be reliably erased from memory.** Do not claim `char[]` is sufficient protection if the secret has already been copied into Strings, logs, or libraries. Minimize copies, limit lifetime, avoid dumps, and control permissions.

## 8. Spring Boot 3.3.5 + Java 17 Example: Runtime Credentials, No Hardcoding

This learning example uses Spring Security Servlet + HTTP Basic, one in-memory user with a password supplied via **runtime property**, BCrypt hashing in memory, and one private endpoint. It is **not a production account management pattern**; production uses a user store/IdP, credential rotation, MFA, and appropriate rate limiting.

There is no default password in source code; missing properties prevent Spring from resolving them and **prevent startup**. Never use test accounts/passwords in real environments.

### 8.1. Gradle

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Files:

```text
src/main/java/demo/runtime/
  RuntimeSecretsApplication.java
  SecurityConfig.java
  DemoController.java

src/test/java/demo/runtime/
  RuntimeSecretsTest.java
```

### 8.2. Spring Boot Application

`src/main/java/demo/runtime/RuntimeSecretsApplication.java`:

```java
package demo.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeSecretsApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeSecretsApplication.class, args);
    }
}
```

### 8.3. SecurityConfig: BCrypt, Externalized Password, and Deny by Default

`src/main/java/demo/runtime/SecurityConfig.java`:

```java
package demo.runtime;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${DEMO_USERNAME}") String username,
            @Value("${DEMO_PASSWORD}") String password) {
        if (username.isBlank() || password.length() < 12) {
            throw new IllegalStateException(
                "Required local demo identity configuration is invalid");
        }
        UserDetails user = User.withUsername(username)
            .password(encoder.encode(password))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .requestMatchers("/private").hasRole("USER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Do not log the username/password or the entire `UserDetails` object in configuration. The raw password from the environment is only used to generate a hash **for the local demo**; in production, store hashes in a database and authenticate via a provider/IdP, rather than loading all user passwords into environment variables.

### 8.4. Controller Not Returning Secrets

`src/main/java/demo/runtime/DemoController.java`:

```java
package demo.runtime;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public")
    public String publicResource() {
        return "public";
    }

    @GetMapping("/private")
    public Map<String, String> privateResource(Principal principal) {
        return Map.of(
            "user", principal.getName(),
            "message", "private fixture"
        );
    }
}
```

The `/private` endpoint only illustrates the security context. A username can be personal data in a real application; proper authorization and a valid purpose are required when returning this information.

### 8.5. Running with Mock Local Data

In Bash:

```bash
export DEMO_USERNAME=learner
export DEMO_PASSWORD='local-fixture-password'
./gradlew bootRun
```

On PowerShell, use PowerShell's environment variable syntax. Do not use production credentials on a developer machine or leave them in shell history. Access:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
```

The body of the first request is `public`; the second request without credentials receives an HTTP Basic challenge (401). To enter the password interactively **without placing the password in process arguments**:

```bash
curl --user learner http://localhost:8080/private
```

`curl` may prompt you to enter the password. With the correct demo credentials, the application returns JSON containing `"user":"learner"`; JSON field order is not fixed. Plain HTTP is only for `localhost` testing; any real network connection receiving HTTP Basic credentials requires TLS.

## 9. Testing Credentials Through the Real Filter, Not Just Mock Users

`src/test/java/demo/runtime/RuntimeSecretsTest.java`:

```java
package demo.runtime;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "DEMO_USERNAME=learner",
    "DEMO_PASSWORD=test-only-long-password"
})
@AutoConfigureMockMvc
class RuntimeSecretsTest {
    @Autowired MockMvc mvc;
    @Autowired UserDetailsService users;
    @Autowired PasswordEncoder encoder;

    @Test
    void publicEndpointWorks() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validCredentialUsesAuthenticationProvider() throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("learner", "test-only-long-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    void invalidPasswordIsRejected() throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("learner", "invalid-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userStoreContainsHashInsteadOfRawPassword() {
        String stored = users.loadUserByUsername("learner").getPassword();
        assertFalse(stored.equals("test-only-long-password"));
        assertTrue(encoder.matches("test-only-long-password", stored));
    }
}
```

Run:

```bash
./gradlew test
```

`httpBasic(...)` only sends the HTTP Basic header; Spring Security's `BasicAuthenticationFilter` actually invokes the `AuthenticationManager`/provider. Unlike `@WithMockUser`, this test can catch wrong passwords. Test fixtures in code are **not** production secrets; never use real secrets to test CI.

### 9.1. What This Test Does Not Prove

- Does not test TLS/reverse proxy or HTTP headers over a real network.
- Does not test OIDC client secret/IdP/JWKS, because the demo uses Basic instead of OAuth2.
- Does not prove full secret manager permissions, container mounts, backups, and rotation.
- Does not test MFA, account recovery, brute-force protection, or database persistence.
- Does not guarantee env vars are safe from process inspection; that is a deployment concern.

An additional pipeline test should intentionally start the app without `DEMO_PASSWORD` to verify **startup failure**. If secrets are supplied via vault/configtree, test invalid/revoked secrets and the reload/restart plan in staging. When logging errors, only print the **missing/config invalid** status, never the secret.

## 10. Separating dev, CI, staging, and production

| Factor | Local/Dev | CI | Staging | Production |
|---|---|---|---|---|
| Secret source | Local manager or fake fixture | Job-scoped secret or fixture | Staging vault | Production vault/KMS/HSM |
| OIDC client | Dev registration | Test registration | Staging registration | Prod registration |
| JWT signing keys | Dev-only/ephemeral | Test keys | Staging key pair | Production key pair |
| Database/LDAP | Local/test only | Isolated fixtures | Staging services | Production services |
| Identity/data | Fake users | Test users | QA users + scrubbed data | Real data, real privileges |
| Logs/debug | Debug with redaction | Do not echo secrets | Production-like redaction | Minimize diagnostics, audit access |
| Access control | Developer only | Scoped CI identity | QA/Ops least privilege | Prod approvals and break-glass audit |

**Staging must never use production client secrets, private signing keys, or DB passwords**. A staging config mistakenly pointing to the production `issuer-uri` could allow tokens from an untrusted environment to be accepted by production or accidentally affect real data.

Deployment guards are needed to verify: expected issuer/hostname/redirect URI, active Spring profile, DB endpoint, secret reference, role/namespace, audience, TLS trust store, and rollback capability. Never use `spring.profiles.active=dev` in production even if the application has strong passwords.

Both config trees and environment variables follow Spring Boot's **property source precedence**. When diagnosing overrides, inspect configuration sources with authorized tooling, **never dump the entire effective config containing secrets** into logs/tickets.

## 11. Docker, Kubernetes, CI/CD, and Observability

### 11.1. Do Not Bake Secrets into Docker Images

**Unsafe** example:

```dockerfile
# Do not use this pattern with real secrets:
ARG CLIENT_SECRET
ENV CLIENT_SECRET=$CLIENT_SECRET
COPY production-private-key.pem /app/private-key.pem
```

Reason: image layers, metadata, build caches/registries/artifacts can retain secrets even if the file is deleted in a later build step. Provision secrets **at runtime** via workload identity, external vault, scoped secret volume, or appropriate mounts; the container image should only contain code and non-secret configuration.

### 11.2. Kubernetes Secrets and Read Permissions

Kubernetes `Secret.data` stores a Base64 representation, not encryption. Protection also depends on encryption-at-rest, RBAC, pod/service account permissions, network policies, auditing, how CI/GitOps manages manifests, and host/cluster permissions.

Do not allow every service account to read every secret. Do not run `kubectl get secret -o yaml` and paste the output into a ticket, or print `env` in build logs. When a secret volume is updated, the application may need a reload or restart depending on the library, connection pool, and caching mechanism; test this rather than assuming automatic updates.

### 11.3. Logs, Tracing, and Actuator

**Should log**: request ID, timestamp, non-sensitive route, authentication mechanism type, result code, issuer ID or `kid` if needed for rotation, duration. **Do not log**: `Authorization`, `Cookie`, `Set-Cookie`, passwords, full JWTs, client secrets, private keys, ID/access/refresh tokens, or auth codes.

Verify redaction across proxies, servlet filters, exception handlers, HTTP clients, tracing/observability agents, and log aggregators. Do not rely solely on default masking of `/actuator/env` or `/actuator/configprops`; restrict exposure, verify against your actual version, and protect networks/roles.

Heap dumps, thread dumps, memory diagnostics, HAR files, and screenshots can also contain secrets. Access permissions and retention for debug artifacts must be strict; never post them to open chats/tickets.

### 11.4. CI/CD

- Scope secrets by environment/branch and authorized jobs; untrusted PRs must never receive production secrets.
- Use CI OIDC workload federation if supported by the platform to reduce static long-lived deployment credentials.
- Do not enable `set -x`/echo secrets, dump env, or run tests with real private keys.
- Run secret scanning on commits, Git history where appropriate, and container artifacts; upon detection, **revoke/rotate** rather than just deleting the line.
- Separate deployment permissions, secret read permissions, and signing key rotation permissions; production requires audit/approval per policy.
- Do not save `.p12` files, PEM private keys, OAuth client secrets, or production tokens in test reports or code coverage artifacts.

## 12. Rotation and Plans for Changing Secrets Without Outage

### 12.1. Passwords/API Keys/DB Credentials

A typical planned rotation process includes:

1. Inventory clients/connection pools using the old credential.
2. Create the new credential with a scope no broader than needed.
3. If supported by the system, allow both credentials to stay active temporarily with a revocation deadline.
4. Update the secret manager and deploy/reload the service; test **new connections**.
5. Once all clients are confirmed on the new credential, revoke the old credential and monitor attempted uses.
6. Clean up unused caches/backups/pipeline variables; update the inventory.

If two credentials cannot coexist simultaneously, plan a scheduled cutover; do not promise zero-downtime when upstream does not support it. With DB pools, existing open connections may persist after the password changes, so test reconnects/new connections.

### 12.2. OAuth Client Secrets

Rotate the secret at the IdP/authorization server, update the vault, reload/redeploy the app, test authorization code exchange/client authentication, and then revoke the old secret. Some IdPs allow **two active secrets** during an overlap window, while others only replace immediately; confirm capability.

Changing an env var on the server without revoking the old secret at the IdP **does not complete rotation**. Assess issued tokens/sessions and blast radius if the secret was previously exposed.

### 12.3. Signing Private Keys

Keep overlapping **public verification keys** in JWKS according to token lifetime/cache during planned rotation. However, when a key is compromised, prioritize emergency revocation and token invalidation per the threat model, even if re-login is required. Never keep a compromised private key active indefinitely out of fear of disruption.

## 13. Incident Response: When Secret Exposure Is Suspected

Scenario: a CI log accidentally printed an OIDC client secret. Minimum steps:

1. **Identify secret type and scope**: environment, issuing system, granted permissions, people and systems able to access the log/artifact.
2. **Containment**: restrict access, revoke/rotate the credential **at the issuing source**, not just by deleting the log.
3. **Find copies**: Git, CI caches, container layers, backups, dashboards, tickets, chat, developer machines, and log retention.
4. **Assess tokens/sessions**: an exposed client secret may affect tokens; an exposed signing private key allows forged tokens; an exposed DB credential requires query auditing.
5. **Deploy safe version**: new secret, proper workload permissions, correct environment config, validate keys/issuer/audience.
6. **Monitor and respond**: anomalous logins, token failures, API activity, old credential usage, key signing events.
7. **Improve**: secret scanning, reduce TTL/permissions, avoid static secret copies, rehearse rotation, and update runbooks.

| Incident | Priority action | Additional considerations |
|---|---|---|
| User password exposed | Reset password, revoke sessions if needed, MFA/monitoring | Credential reuse and account takeover |
| OAuth client secret exposed | Revoke and reissue at IdP, update backend | Issued tokens, abuse, and scope |
| JWT private key exposed | Revoke/rotate key, update trust and token policy | Forged JWTs, cached keys, and active tokens |
| TLS private key exposed | Replace key/certificate and evaluate revocation | Copies at proxy/CDN/backups |
| DB/API key exposed | Rotate account/key and audit access | Connection pools, permissions, logs |

Do not attach the **secret value** to incident tickets. Use a non-sensitive secret reference, timestamps, and status details. Do not output a hash/fingerprint of the secret merely to prove rotation unless required and risk-assessed.

## 14. Common Mistakes

**Mistake 1.** Putting `client-secret` into `application-prod.yml` and committing it. Filenames do not create a security boundary; use a runtime secret store and rotate if exposed.

**Mistake 2.** Letting staging use the production signing private key. A weak environment exposes production issuer authority; keep keys/issuers separate.

**Mistake 3.** Putting secrets in Docker `ARG`/`ENV` or copying PEM files into the build image. Caches and layers can retain secrets. Only inject at runtime when needed.

**Mistake 4.** Choosing HS256 so every service can easily verify. With HMAC, services holding the key can also sign; evaluate the token issuance permission model.

**Mistake 5.** Treating a valid JWT signature as sufficient. You still need issuer, audience, expiry, algorithm policy, scopes, and resource permissions.

**Mistake 6.** Trusting `kid`/`jku` in a JWT to download keys arbitrarily. The JWKS source must come from trusted configuration, not client input.

**Mistake 7.** Hashing passwords with SHA-256 only. Passwords require adaptive salted hashing, cost factors, and a migration policy.

**Mistake 8.** Using a secret in an SPA because the bundle is minified. The browser can still extract it; use a public client/PKCE.

**Mistake 9.** Setting fallback `DB_PASSWORD:admin` in production. When the vault fails, the app could use weak credentials. Fail closed.

**Mistake 10.** Only adding `.gitignore` after committing a secret. The secret remains in history/clones; revoking/rotating is the decisive step.

**Mistake 11.** Disabling Spring Security/HTTP log redaction to debug login. Tokens, cookies, or credentials can enter log retention. Use scrubbed diagnostics.

**Mistake 12.** Changing the secret store without redeploying/reloading consumers or revoking the old version. Rotation must verify the new path and ensure the old secret is no longer used.

**Mistake 13.** Granting production secrets to a CI workflow from an untrusted PR. Restrict by branch/environment, workload identity, and approvals.

**Mistake 14.** Equating a signed JWT with an encrypted payload. Signatures do not hide contents; never put secrets in claims.

## 15. Test Matrix and Release Checklist

| Goal | Test to run | PASS when |
|---|---|---|
| No secrets in source | Repo/image secret scanner | No production secrets exposed |
| Fail-fast | Missing DB/OIDC/DEMO_PASSWORD | Startup does not fall back to demo credentials |
| User hash | `PasswordEncoder.matches` | Hash differs from plaintext, right pass true, wrong pass false |
| HTTP auth | MockMvc Basic with valid/invalid credentials | Real filter returns 200/401 appropriately |
| Environment isolation | Staging tokens/DB/client | Cannot access/impersonate production |
| JWT validation | Tokens with valid/invalid signature, issuer, audience, expiry | Tokens outside trust policy are rejected |
| Client secret rotation | New key can auth with IdP | Old secret is revoked at the right time |
| Signing key | JWKS rollover/caching | New tokens verify, old tokens follow overlap policy |
| Runtime permissions | Other pod/CI/job tries reading secret | Denied by RBAC/IAM |
| Logging | Requests with dummy credentials | No raw password/token/Authorization leaked |
| Actuator/diagnostics | Check endpoints and role access | No config containing secrets exposed |
| DB credential | Rotate then reconnect | New connections succeed; old secret rejected |

Release checklist:

- [ ] Secrets have an owner, purpose, environment, scope, issuing source, rotation, and revocation plan.
- [ ] User passwords use adaptive salted hashing; no plaintext/reversible encryption stored.
- [ ] Client secrets reside only on confidential backends, never in SPA/mobile.
- [ ] JWT signing private keys reside only at the issuer/HSM/KMS; resource servers use trusted public JWKS.
- [ ] Issuer, audience, algorithm allowlist, key rotation, and claim mapping are tested.
- [ ] Dev/CI/staging/prod environments have separate secrets/issuers/DB/client registrations.
- [ ] No secrets in Git, image layers, CI artifacts, logs, metrics, or dumps.
- [ ] Secrets are injected at runtime via workload identity/least privilege; TLS protects required hops.
- [ ] Missing secrets fail closed, with no default admin password.
- [ ] Rotation/revocation, new connections, and token/key overlap have been tested.
- [ ] Actuator/config/diagnostics endpoints are restricted and verified for sanitization.
- [ ] An incident response plan exists; secrets are never sent via chat/tickets.

**Summary:** Spring Security can authenticate passwords, OAuth2 Login, and JWT resource servers, but **keeping credentials secret, protecting private signing keys/client secrets, configuring per environment, enforcing least privilege, avoiding secret logging, and rotating/revoking** are system-wide design and operations responsibilities. Prove these through real tests and runbooks, not just a property file or an enabled filter.