# Managing Passwords, Client Secrets, and Keys with Externalized Secret Configuration

> **Context:** Spring Security — fundamentals / Deployment. This guide covers protecting **passwords, OAuth2 client secrets, API keys, JWT signing keys, and encryption keys** when building and deploying Java 17+, Spring Boot 3.x/Spring Security 6.x applications. The focus is on separating secrets from source code, distributing them via configuration or a secret manager, limiting who can read them, preventing leakage through logs/CI, and **rotating/revoking without downtime**. The main example uses Spring Boot **3.5.0**, Java 17, and Maven.

## 1. The problem: putting secrets into Git turns a small mistake into a long-lived incident

Dangerous example:

~~~java
// WRONG: passwords and keys are embedded in source code.
String databasePassword = "HardcodedDatabasePassword";
String clientSecret = "HardcodedOAuthClientSecret";
byte[] signingKey = "HardcodedShortSigningKey".getBytes();
~~~

Or configuration committed alongside the repository:

~~~properties
# WRONG: storing real secret values in a version-controlled file.
spring.datasource.password=real-database-password
spring.security.oauth2.client.registration.billing.client-secret=real-client-secret
app.jwt.signing-key=real-signing-key
~~~

Any developer, CI runner, or third-party service with read access to the code or artifacts can see the credentials. Once a secret is in Git, deleting it in a new commit **does not automatically remove it from history, forks, clones, caches, logs, and old build artifacts**. At that point, the credential must be treated as compromised and **rotated/revoked**, not merely removed from the file.

**Design principle:** source code only describes *configuration names, schema, and usage*. **Actual secret values** come from a governed deployment channel — controlled environment injection, permissioned file mounts, a secrets manager, or workload identity. Do not use Base64 or obfuscation as a form of security encryption.

Protecting secrets also covers **while they are in transit, in RAM, inside processes/containers, and during rotation**. "Not in Git" is a necessary condition, not a sufficient one.

### Common scenarios

- Developers run the application with test accounts and must keep passwords out of the repository.
- CI/CD deploys to staging/production, with each environment having its own credentials.
- Spring Security OAuth2 Client uses `client_credentials` to call a partner with `client_id` and `client_secret`.
- A Resource Server verifies JWTs using a **public key/JWKS**; the issuer signs with a **private key** or HMAC secret.
- An application needs an AES/GCM key to encrypt sensitive data, with requirements for rotation and recovery.
- Multiple pods or instances read secrets from a secrets management system without printing secrets to logs.

## 2. Accurate classification: passwords, password hashes, client secrets, and keys

| Data type | Purpose | Recommended handling |
|---|---|---|
| **User raw password** | User proves identity | Process only during login, transmit over HTTPS, never log; store a **salted password hash using an appropriate algorithm** in the user store, never store plaintext |
| **Password hash (verifier)** | Verify password at login, e.g., `{bcrypt}$2b$...` | Usually stored in the user database; for a **bootstrap account** it can be provided via secret configuration; still restrict access and support rotation |
| **DB / service account password** | App connects to other services | Prefer workload identity/short-lived credentials; if static passwords are needed, manage them in a secret manager |
| **OAuth2 client secret** | Authenticate a *confidential client* with an authorization server | Keep only on the backend/secure runtime, **never embed in SPA/mobile public clients** |
| **API key** | Call APIs or identify a client, depending on design | Grant narrow permissions, set expiration, rotate, never place in source/URL/logs |
| **JWT HMAC key (HS256/HS512)** | Shared secret to sign and verify JWTs | Random key with sufficient entropy, minimal distribution; any party holding the key **can also sign** tokens |
| **Asymmetric private key (RSA/EC)** | Sign JWTs/digital signatures | Only the issuer/signing service may hold it; use KMS/HSM when appropriate |
| **Asymmetric public key/JWKS** | Verify signatures | Not inherently secret; still must be fetched from a trusted source, with issuer/audience/algorithm verification and change management |
| **Encryption key (AES-GCM)** | Encrypt/decrypt data | Key must not sit alongside ciphertext in the database within the same access boundary; use KMS/envelope encryption, key versioning, and random/unique nonces |
| **TLS private key** | Prove TLS endpoint identity | Manage at ingress/server/KMS with restricted read permissions; the public certificate is not secret, but the private key is secret |

**Do not confuse "hash" with "encryption":** a password hash is a one-way verifier, so the application never needs to decrypt the original password. An encryption key is needed to recover plaintext, so its lifecycle, backup, and access control differ from a password hash. An **OAuth2 client secret** is also not an end-user access token; it is an application credential.

**Do not use memorable passwords as HMAC/AES keys.** Such keys require entropy from a CSPRNG and a length appropriate for the algorithm. For example, HMAC-SHA-256 should use a random secret of **at least 32 bytes** in this pattern; AES-256 uses an exact 32-byte key with properly managed nonces/IVs.

## 3. Architecture for separating code from secret values

~~~mermaid
flowchart LR
    A["Git / source code<br/>property names and schema only"] --> B["Build artifact<br/>JAR / container image"]
    C["Secret manager / KMS / Vault<br/>permissions, audit, rotation"] --> D["Runtime injection<br/>env / secret file / configtree / SDK"]
    B --> E["Spring Boot application"]
    D --> E
    E --> F["PasswordEncoder / OAuth2 client / JWT signer / DB"]
    E --> G["Logs and responses<br/>NO secrets"]
~~~

Trust boundary: only a workload granted the proper identity and permissions can retrieve the secrets it needs. The build artifact is packaged **once** and runs across dev/staging/prod with environment-specific secret configuration.

Common distribution channels:

1. **Environment variables:** simple, well-supported by Spring Boot; suitable for demos and protected environments. However, the environment can be exposed via process inspection, debugging, crash reports, container inspect, CI jobs, and telemetry.
2. **Runtime-mounted secret files:** Kubernetes Secret volumes, Docker secret mounts, CSI drivers, or Vault agents. Reduces exposure in the environment; requires managing file owner/mode/ACLs, lifecycle, and synchronization after rotation.
3. **Secret manager via workload identity:** AWS Secrets Manager, Azure Key Vault, Google Secret Manager, HashiCorp Vault, or equivalent platforms. Provides auditing, roles, versioning, and rotation; requires checking caching, retries, availability, quotas, and startup failures.
4. **Dynamic/short-lived credentials:** database IAM authentication, cloud managed identity, OIDC federation, mTLS identity, Vault dynamic secrets. Usually preferable to long-lived credentials when supported by the system.
5. **KMS/HSM:** allows signing/decryption via API without the application necessarily receiving the raw private key; reduces key leakage surface. Still requires protecting KMS invocation permissions and logs.

**Trade-off:** environment variables are easy to use but not inherently safer than secret files; mounted files are also unsafe if every process in a pod can read them or if files are copied into the image. Security comes from **access control, execution environment, rotation policy, and monitoring**, not from the channel name.

## 4. Spring Boot Externalized Configuration: specify secret names, never values

Spring Boot can be configured via `application.yml`, environment variables, command-line arguments, ConfigData imports, and property sources added by integrations. For a runtime secret, version-controlled files should contain only the **property name and placeholder**, with no secret value.

Example:

~~~yaml
# src/main/resources/application.yml — safe to commit because it contains no secrets.
spring:
  application:
    name: external-secrets-demo

app:
  auth:
    operator-username: ${APP_OPERATOR_USERNAME}
    operator-password-hash: ${APP_OPERATOR_PASSWORD_HASH}
~~~

The value of `APP_OPERATOR_PASSWORD_HASH` is supplied **at runtime**. Do not declare a fallback such as `${APP_OPERATOR_PASSWORD_HASH:changeme}` for production, because the app could accidentally start with a hardcoded credential. Do not log resolved configuration values.

Spring Boot supports relaxed binding, but when using an explicit placeholder as above, the env var name must match exactly. When relying on direct env mapping rules, for example a property `app.auth.operator-password-hash` typically maps to `APP_AUTH_OPERATORPASSWORDHASH` according to Spring Boot's naming rules; verify the rules for the Boot version in use. To minimize discrepancies, the demo in this guide uses **explicit env placeholders**.

### Fail fast when configuration is missing

A production application should refuse to start if a required credential is missing or has an invalid format, rather than running "anonymous", using a hardcoded default, or silently skipping authentication.

A config file with only property names is not enough if code still ignores a null secret. Use `@ConfigurationProperties` with validation and format checks to catch issues early. **Do not include the full property value in exception messages**, as startup logs are also an easy place to leak secrets.

### Secret value vs. secret name/path

- `APP_OPERATOR_PASSWORD_HASH`: may be a secret or sensitive data; do not print or log.
- `SIGNING_KEY_FILE=/run/secrets/private-key.pem`: the **path** is not necessarily secret; it may be configured.
- `billing-client-secret`: the **key name** in a secret manager is not the secret value; still, avoid exposing infrastructure metadata unnecessarily.
- A `Secret Version ID` or fingerprint does not replace authentication; it may be used in telemetry after evaluating metadata leakage risks.

## 5. Runnable Spring Security example: supplying password hashes outside source code

In many systems, user password hashes live in an identity management database. However, a **least-privilege bootstrap/operator account** is a great example for illustrating external secret configuration. The following example **stores no raw password**, only receives a password hash at runtime, and embeds no real hash, username, or secret into the JAR.

**Requirements:** JDK 17+, Maven 3.9+, Spring Boot 3.5.0, and Spring Security 6.x. The hash has the form `{bcrypt}$2a$...` or `{bcrypt}$2b$...` per `DelegatingPasswordEncoder`. Bcrypt in this demo does not replace production requirements for an identity provider, auditing, MFA, and authorization.

Structure:

~~~text
external-secrets-demo/
├── pom.xml
├── src/main/resources/application.yml
├── src/main/java/com/example/secrets/
│   ├── ExternalSecretsApplication.java
│   ├── OperatorSecrets.java
│   ├── SecurityConfig.java
│   └── AccountController.java
└── src/test/java/com/example/secrets/
    └── ExternalSecretsSecurityTest.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>external-secrets-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. application.yml

~~~yaml
spring:
  application:
    name: external-secrets-demo

app:
  auth:
    operator-username: ${APP_OPERATOR_USERNAME}
    operator-password-hash: ${APP_OPERATOR_PASSWORD_HASH}
~~~

This YAML file **can be stored in the repository**, because it contains variable names, not values. Do not pass secrets via command-line flags like `--app.auth.operator-password-hash=...`, because command arguments can be read from process listings, shell history, or logs.

### 5.3. ExternalSecretsApplication.java

~~~java
package com.example.secrets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ExternalSecretsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExternalSecretsApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` discovers the config record in the next section. There is no need to scatter manual `System.getenv(...)` calls across controllers.

### 5.4. OperatorSecrets.java

~~~java
package com.example.secrets;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.auth")
public record OperatorSecrets(
    @NotBlank String operatorUsername,
    @NotBlank String operatorPasswordHash
) {}
~~~

**Explanation:** Spring Boot binds `operator-username` to `operatorUsername` and `operator-password-hash` to `operatorPasswordHash`. `@NotBlank` prevents null/blank values at startup. The app never substitutes missing values with a default password.

`String` in the JVM is immutable and cannot be wiped with `Arrays.fill`; therefore, minimize copying/logging secrets, limit their lifetime, and control heap dumps and process diagnostics. Password hashes should also be treated as restricted-access data.

### 5.5. SecurityConfig.java

~~~java
package com.example.secrets;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(OperatorSecrets properties) {
        String storedHash = properties.operatorPasswordHash();

        // Accept only bcrypt format per this example's policy.
        if (!storedHash.startsWith("{bcrypt}$2")) {
            throw new IllegalStateException(
                "Operator password hash must use bcrypt encoding");
        }

        return new InMemoryUserDetailsManager(
            User.withUsername(properties.operatorUsername())
                .password(storedHash)
                .roles("OPS")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/ops/status")
                    .hasRole("OPS")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        return http.build();
    }
}
~~~

Here:

1. **There is no real password or hardcoded hash** in Java. The hash is passed via `OperatorSecrets` from Spring configuration at runtime.
2. `DelegatingPasswordEncoder` understands the `{bcrypt}` prefix; never use `NoOpPasswordEncoder` or `{noop}` for real accounts.
3. The `UserDetailsService` in this example has only one OPS account with narrow scope. For regular users, use a database/identity provider to manage hashes, MFA policies, and user lifecycles.
4. Spring Security authenticates HTTP Basic on every request without storing login state in a session. This is independent of keeping the hash in a secret store.
5. `/api/me` and `/api/ops/status` do not return the hash/secret value. All other endpoints are rejected by `denyAll`. Method rules allow only GET as contracted.
6. The example has only `GET` requests; keep default CSRF protection enabled. When adding POST/PUT/PATCH/DELETE for browsers, choose an explicit CSRF strategy rather than disabling it just because Basic/STATELESS is used.
7. The fail-fast message only states that the format is invalid; it **never** concatenates the actual value into the exception.
8. For production, also validate bcrypt strength/cost against policy, enforce account/rate limits, and manage rotation. Do not treat `startsWith` as a full validator for all hashes; it catches simple misconfigurations in this demo.

### 5.6. AccountController.java

~~~java
package com.example.secrets;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/api/me")
    public Me me(Authentication authentication) {
        List<String> roles = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
        return new Me(authentication.getName(), roles);
    }

    @GetMapping("/api/ops/status")
    public Status status() {
        return new Status("ready");
    }

    public record Me(String username, List<String> roles) {}
    public record Status(String status) {}
}
~~~

DTOs return only the principal name, authorities, and harmless status. **Never** write an `/api/debug/config` endpoint that returns `OperatorSecrets` — that record holds a sensitive verifier. When a health check is needed, return only a boolean/status, never secret names, key lengths, credentials, or arbitrary fingerprints.

### 5.7. ExternalSecretsSecurityTest.java

The test provides a **runtime-generated password hash for a test account**, never uses staging/production secrets, and never commits hashes to the repo:

~~~java
package com.example.secrets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ExternalSecretsSecurityTest {

    private static final String TEST_PASSWORD =
        "local-test-only-password-123";

    private static final String TEST_HASH = "{bcrypt}" +
        new BCryptPasswordEncoder(10).encode(TEST_PASSWORD);

    @DynamicPropertySource
    static void testSecrets(DynamicPropertyRegistry registry) {
        registry.add("app.auth.operator-username",
            () -> "operator-test");
        registry.add("app.auth.operator-password-hash",
            () -> TEST_HASH);
    }

    @Autowired
    MockMvc mvc;

    @Test
    void correctExternalHashAuthenticates() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("operator-test", TEST_PASSWORD)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("operator-test"))
            .andExpect(jsonPath("$.roles[0]").value("ROLE_OPS"));
    }

    @Test
    void badPasswordIs401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("operator-test", "not-the-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousIs401() throws Exception {
        mvc.perform(get("/api/ops/status"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizedStatusContainsNoPasswordHash() throws Exception {
        mvc.perform(get("/api/ops/status")
                .with(httpBasic("operator-test", TEST_PASSWORD)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ready"));
    }
}
~~~

The tests use `@DynamicPropertySource` to set property values **for tests only**; they do not need and must not access a production secret manager. The password `local-test-only-password-123` is a public test string with no privileges in any other environment. In real deployments, the deployment username/password are provisioned separately.

**Limitation:** The test proves Spring Boot binds the properties and Spring Security authenticates using a hash supplied outside the configuration class; it **does not prove** Vault/Kubernetes/CI permissions or the production rotation lifecycle. Those require deployment/infrastructure tests.

### 5.8. Running the example

In the project directory:

~~~bash
mvn test
~~~

With compatible Maven/JDK and dependencies, the tests are expected to pass; this guide **does not claim to have executed Maven**. Running the app with `mvn spring-boot:run` requires provisioning **both** `APP_OPERATOR_USERNAME` and `APP_OPERATOR_PASSWORD_HASH` beforehand; if either is missing, startup must fail rather than falling back to a weak password.

Bash example to enter configuration **without writing the hash directly into shell command history**:

~~~bash
export APP_OPERATOR_USERNAME=operator
read -r -s -p "Enter provisioned {bcrypt} hash: " APP_OPERATOR_PASSWORD_HASH
echo
export APP_OPERATOR_PASSWORD_HASH
mvn spring-boot:run
~~~

The hash value must be generated/supplied through a trusted provisioning process. If using bash locally, do not copy the hash value into shell history and avoid capturing screenshots of logs. Even when entered via `read -s`, environment variables **can still be exposed via process inspection**; this is a simple example, and production should use a secret manager or mounted file per policy.

A successful request must include the **raw password matching the hash** entered by the operator when creating the credential:

~~~bash
curl -i -u operator http://localhost:8080/api/me
~~~

With `curl -u operator` (without `:password` on the command line), curl **prompts for the password interactively**, reducing the risk of exposing the password in shell history or process arguments. `GET /api/ops/status` also succeeds only with valid credentials. Without credentials, HTTP Basic on a protected API typically returns `401`; with valid credentials, `/api/me` returns the username and `OPS` role.

After testing:

~~~bash
unset APP_OPERATOR_PASSWORD_HASH
unset APP_OPERATOR_USERNAME
~~~

`unset` removes the variables from the current shell; it **does not revoke** the credential used—revoke/rotate if exposure is suspected.

## 6. Password hashing: raw secrets do not belong in source, verifiers must not leak

Spring Security recommends using a `PasswordEncoder` suited to your compute budget and system requirements. With `DelegatingPasswordEncoder`, a hash prefixed with `{bcrypt}` is delegated to `BCryptPasswordEncoder`. Each bcrypt encoding generates a random salt inside the hash; two hashes of the same password **usually differ**, yet both match.

API usage example (illustrative snippet, not a standalone class):

~~~java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String storedHash = encoder.encode(rawPasswordFromSafeInput);
boolean match = encoder.matches(candidatePassword, storedHash);

// NEVER write storedHash or rawPassword to logs or HTTP responses.
~~~

This snippet requires importing `PasswordEncoder` and `PasswordEncoderFactories`; in a real system, the raw password comes from a TLS-protected request, not a hardcoded constant. `encode` is not used when **comparing** a password against an existing hash; use `matches`, because the random salt causes `encode(candidate)` to produce a different result.

**Bcrypt cost** must be tuned to your infrastructure and login latency target—neither set so low that password guessing becomes cheap, nor so high that it enables denial-of-service. New applications may also consider Argon2id/PBKDF2/scrypt depending on environment and policy. Never build a custom hashing scheme using a single pass of `MessageDigest.getInstance("SHA-256")` and store it as a password verifier.

**Scope of secret managers for passwords:**

- Password hashes for millions of end users: store in an **identity/user database** with appropriate access control and backups.
- A least-privilege bootstrap credential: the hash may be injected via a secret manager, though avoiding fixed accounts altogether is better.
- Database passwords, partner client secrets, API keys: these are the real secrets that belong in deployment/secret manager distribution.
- Do not pass passwords via config to "create a default admin" on every replica without a rotation/revocation process.

## 7. OAuth2 confidential clients: client secrets belong only on the backend

Spring Security OAuth2 Client uses `client_id` and `client_secret` when a backend acts as a **confidential client**, such as obtaining a token via `client_credentials` to call a partner API. `client_id` is usually a non-secret identifier; `client_secret` is a credential.

**This is an additional configuration example, not part of the runnable application in section 5.** When implementing OAuth2 Client in another project, add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          billing:
            provider: billing
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: invoices.read
        provider:
          billing:
            token-uri: https://auth.example.test/oauth2/token
~~~

`https://auth.example.test/oauth2/token` is an **illustrative** URL and must be replaced with the real token endpoint confirmed by the provider. This document does not require and does not perform connections to a live provider.

Security points:

1. Do not place a real `client-secret` in `application.yml` in Git, Maven POM, JAR, Dockerfile `ENV`, or frontend bundles.
2. Each environment/partner should have its own credential, minimal scope, expiration, and clear owner.
3. `client_secret_basic` sends credentials using HTTP Basic over HTTPS to the token endpoint; never log `Authorization` or the `client_secret` form parameter.
4. For **SPAs, mobile/native apps, or desktop public clients**, never assume `client_secret` can be kept safe inside a binary or frontend. They should use a public client design such as Authorization Code + PKCE and follow the authorization server's policies.
5. Received access tokens are also sensitive data: never log or put them in URLs, protect caches/token stores, and refresh according to expiration and scope.
6. Where supported, consider `private_key_jwt`, mTLS, managed identity, or workload federation to avoid shared static secrets; private keys and identity permissions must still be managed.
7. OAuth2 client secret rotation requires coordination with the provider and may need an overlap window between old and new secrets if the provider supports it.

### Why not put secrets in the frontend?

~~~javascript
// WRONG: anyone downloading the web bundle can read the secret.
const oauthClientSecret = "NOT_A_SECRET_IF_IN_BROWSER";
~~~

Even with minification or obfuscation, the string is still delivered to the browser. If the frontend needs OAuth2 login, use an appropriate public-client flow instead of turning the frontend into a confidential client by embedding a `client_secret`.

## 8. Signing keys and encryption keys: a higher privilege boundary than a password

### JWT/JWS with asymmetric signing

A common architecture:

~~~text
Token issuer / authorization server:
  - Holds the RSA/EC private key or signing permission via KMS/HSM
  - Signs JWTs, attaches the appropriate key ID (kid)

Resource servers:
  - Only receive the public key/JWKS from a trusted source
  - Verify signature + issuer + audience + expiry + algorithm policy
  - Do NOT need the private signing key
~~~

**The private key is a secret**; the public key does not need to be kept secret, but must be fetched from a trusted issuer/JWKS URI over a verified channel. Never distribute the private key to every microservice just for verification, because any compromised service could then forge tokens.

In Spring Security Resource Server, you typically configure a trusted issuer URI or JWK Set URI per your identity system's guidance:

~~~yaml
# Resource server example; NOT part of the HTTP Basic demo in section 5.
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
~~~

This requires the `spring-boot-starter-oauth2-resource-server` dependency and audience validation configuration when required by the application. This URI is an illustrative address. Setting `issuer-uri` alone does not automatically configure every audience restriction in all systems; verify your token contract. Do not accept arbitrary algorithms/issuers from token headers without checking against server policy.

### Symmetric HMAC signing

With HS256, the issuer and verifier share **one** HMAC key; every verifier holding the key can produce valid MACs, so wide distribution increases risk. Use a random key with sufficient entropy and rotate by `kid`/version when supported by the system.

Generate a test secret **without printing it into Git** (bash with OpenSSL):

~~~bash
# Only for generating a demo key; stdout contains a SECRET, do not screenshot/log/commit.
openssl rand -base64 32
~~~

The output is a real secret for that invocation; it is **not a public sample string to copy into code**. In production, a secret manager/KMS should generate, store, distribute, and control keys. When using Base64 to transport key bytes, **Base64 is not encryption**; the content is merely encoded.

### Encryption keys vs. JWT signing keys

AES-GCM keys provide confidentiality and integrity for ciphertext. They require a **unique nonce/IV per key**, typically 12 properly generated bytes, along with AAD/metadata where applicable. Do not reuse the same key across multiple purposes (JWT signing, database encryption, CSRF, API authentication); domain separation and clear lifecycles reduce cross-impact risk.

If long-lived data is encrypted with a rotated key, you need a strategy for **key versioning, decrypting with old keys during transition, re-encrypting/rewrapping**, backups, and disaster recovery. Abruptly changing an env key value can render old data undecryptable.

### Dedicated file mount for private keys

Path configuration example:

~~~yaml
app:
  crypto:
    signing-private-key-path: ${SIGNING_KEY_PATH:/run/secrets/jwt-signing-key.pem}
~~~

`SIGNING_KEY_PATH` is a path, not the PEM contents. Only the signing service needs to read the private key; verifying resource servers should use **public keys/JWKS** rather than mounting a private key. When reading PEM/PKCS#8 files, validate algorithm, format, read permissions, and size, and prevent key logging; do not write fragile `replace`-based parsing/encoding without proper checks.

## 9. Secret file mounts and Spring Boot Config Tree

An effective option is placing each secret into a read-only file mounted at runtime instead of baking it into an image or Git. Spring Boot provides **Config Data config trees**, which read file names as property names.

Example in an environment with a `/run/secrets/` directory:

~~~text
/run/secrets/
├── app.auth.operator-username
├── app.auth.operator-password-hash
└── billing.client-secret
~~~

Each file's contents is the **property value**, not YAML. The file name `app.auth.operator-password-hash` represents the property key; its contents must be provisioned by the secret system. Filesystem permissions must allow **only the app identity or authorized agent** to read. Do not mount secrets into public/web roots or into containers that do not need them.

An alternative configuration in a file-mount environment, **replacing the env-placeholder strategy** in section 5:

~~~properties
# application-prod.properties — imports only the path, contains no secrets.
spring.config.import=configtree:/run/secrets/
~~~

`app.auth.operator-password-hash` can then be bound directly from the file of the same name. Ensure property source ordering/precedence aligns with the rest of the environment configuration; **avoid keeping a required env placeholder unset at the same time** if it causes binding/resolution errors. Choose one clear runtime source and test startup with real production-like configuration.

If you want to allow the directory to be absent locally, Spring Boot supports `optional:configtree:/run/secrets/`; production should generally **fail fast** when a required secret mount is missing rather than adding `optional:` just to avoid startup errors.

### Comparing env and mount

| Criterion | Environment variables | Secret file / configtree |
|---|---|---|
| Binding in Spring | Placeholders/relaxed binding | `spring.config.import=configtree:...` |
| Risks | Process env, debug tools, CI/export, child processes | File permissions, mount scope, backups, accidental copy |
| Rotation | Usually requires restart/rollout for process to pick up new env | File can change, but **Spring does not guarantee all beans holding the secret will reload** |
| Access control | Based on process/deployment env read access | Based on service account/volume and filesystem ACLs |
| Multi-line PEM key support | Awkward escaping | File mounts are generally much more natural |
| Operations | Easy for demos/local | Great for keys/certs and large secrets; depends on secret delivery |

**Do not equate "the file was updated" with "the client is using the new key".** Many Spring beans are created once at startup and retain a copy of the credential; you need a formal refresh mechanism or a tested application rollout. For JWT key rotation, you must also handle verifying old tokens and key IDs.

## 10. Docker and Kubernetes: runtime injection, never bake secrets into images

### Docker

**Do not** write:

~~~dockerfile
# WRONG: the secret will reside in image layers/build history.
ENV DATABASE_PASSWORD=real-secret
~~~

Nor should you put secrets into `ARG` and assume they are safe: build args can appear in metadata, history, logs, and caches depending on the build pipeline. Prefer BuildKit secret mounts for **build steps that genuinely require** a secret, and runtime secret injection for services.

At runtime, Docker secrets (when supported by the orchestration mode in use) typically appear as files; the application can read them via properties/configtree. Verify container permissions, file modes, and that secrets are not copied into the image. An image that has contained a secret must be treated as a compromised artifact, not "fixed" merely by deleting it in a subsequent layer.

### Kubernetes Secrets do not automatically mean secure encryption

A workload manifest references only the **Secret name** provisioned by the cluster operator or an external-secrets controller:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: secure-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: secure-app
  template:
    metadata:
      labels:
        app: secure-app
    spec:
      serviceAccountName: secure-app-sa
      containers:
        - name: app
          image: registry.example.test/secure-app:1.0.0
          env:
            - name: APP_OPERATOR_USERNAME
              value: "operator"
            - name: APP_OPERATOR_PASSWORD_HASH
              valueFrom:
                secretKeyRef:
                  name: secure-app-runtime
                  key: operator-password-hash
          ports:
            - containerPort: 8080
~~~

This is an **illustrative deployment manifest**: before production, it requires a proper namespace, real image, `imagePullPolicy`, probes, resources, admission policies, networking, and Service definition. The manifest contains no secret value. `APP_OPERATOR_PASSWORD_HASH` in env must be created by a secret manager/controller; pods usually need a restart/rollout to receive **updated env values**.

**Kubernetes Secret `data:` uses Base64 encoding, not encryption.** Actual security depends on RBAC, etcd encryption at rest, secret distribution, auditing, service account permissions, admission controls, and container isolation. Do not commit Secret manifests containing real `data:` or `stringData:` to public or broadly shared internal Git repositories.

For private signing keys, mount a read-only Secret/CSI volume with restricted file permissions rather than injecting PEM into env. Do not mount the entire secret store into every pod. Restrict `get/list/watch secrets` permissions for service accounts; an application usually only needs to read its mounted secret and **does not need** permission to list every Secret in the namespace.

### Why can a secret volume be better than env for private keys?

- Multi-line PEMs do not need to be escaped into an env string.
- You can set file mode/owner/readOnly and reference the path.
- It is easier to separate the issuer's key from resource servers.
- It can integrate with CSI drivers/KMS under existing workflows.

However, a mounted private key still exists on the pod's filesystem and can be read by a compromised process; a KMS/HSM signing API can reduce risk without exporting the raw private key.

## 11. CI/CD: secrets must not appear in build/test logs

### Division of responsibilities across the pipeline

| Stage | Should have | Should not have |
|---|---|---|
| Source review | Property names, schema, fake test fixtures | Raw credentials, real `.env`, private PEMs |
| Compile/unit test | Fake/generated test secrets inside the test process | Production DB passwords, partner client secrets |
| Package | Image/JAR containing no secrets | `COPY .env`, PEMs, secret files in image |
| Deploy | Deployer identity authorized to write/reference secrets for the right environment | Echoing secrets, passing via CLI arguments, sharing credential artifacts |
| Runtime | Pod/app identity reading only its assigned secrets | One superuser key shared across all services |
| Observability | Anonymized status/metrics and correlation IDs | `Authorization`, `Cookie`, tokens, passwords, private keys |

Prefer **OIDC workload federation** from CI to cloud providers where supported to obtain short-lived credentials instead of storing long-lived cloud access keys in CI secrets. GitHub Actions, GitLab CI, and Azure Pipelines all offer secret management mechanisms, each with its own limits and caveats; check masking policies and script output before printing logs.

**Do not assume log masking is infallible.** Secret values can be transformed (Base64, URL encoding, JSON escaping, string slicing) in ways that bypass filters. Scripts with `set -x`, shell traces, debug logs, `env`, `printenv`, `docker inspect`, `kubectl describe`, or test failure dumps can all cause data leaks.

A helpful `.gitignore` file:

~~~gitignore
# Local file containing secrets only; use a template with no values.
.env
.env.*
!.env.example
secrets/
*.key
*.p12
*.pfx
*.pem
~~~

**Note:** `.gitignore` does not remove files that were already tracked by Git, nor does it replace rotating a leaked secret. The `*.pem` rule can also block public certificates that need to be stored—adjust intentionally; private keys must always be protected.

An `.env.example` can contain:

~~~dotenv
# Variable NAMES / example syntax, no secret values.
APP_OPERATOR_USERNAME=
APP_OPERATOR_PASSWORD_HASH=
BILLING_CLIENT_ID=
BILLING_CLIENT_SECRET=
SIGNING_KEY_PATH=/run/secrets/jwt-signing-key.pem
~~~

Do not put "real-looking" values into `.env.example` and hope they are harmless. If local mock credentials are needed, make clear they are unprivileged accounts restricted to test environments.

## 12. Preventing secret leakage via Actuator, errors, logs, and debug endpoints

Common leak locations:

- Printing an entire `@ConfigurationProperties` object with `toString()` (Java records generate a `toString` containing all fields by default).
- Logging `Environment`, HTTP headers, login request bodies, `OAuth2ClientCredentialsGrantRequest`, token responses, or internal exceptions containing credentials.
- Exposing sensitive properties in `/actuator/env`, `/actuator/configprops`, thread dumps, heap dumps, build reports, or diagnostics.
- Returning a "debug config" response from a controller; automatically serializing beans/configs.
- Embedding credentials in URL query parameters, redirects, exception messages, or client-side monitoring.
- Placing secrets in Docker images, layers, OCI labels, CI caches, artifacts, source maps, or Sentry breadcrumbs.

**Spring Boot sanitizes certain keys in Actuator**, but do not rely on that as your sole defense: custom property names, transformations, and custom endpoints can still leak data. Restrict Actuator access, never expose sensitive endpoints publicly, and test actual responses in your running environment.

Avoid:

~~~java
// WRONG: the OperatorSecrets record contains the password hash.
log.info("Loaded config: {}", operatorSecrets);
~~~

Replace with telemetry containing no secret data:

~~~java
// Illustration: log only status, not secrets/fingerprints.
log.info("Required authentication configuration loaded successfully");
~~~

When failing fast, messages should name the **property name**/configuration type needed, without appending values. When tracing is needed, use correlation IDs and `present/absent` flags evaluated so they do not leak sensitive metadata.

**Restrict access to heap dumps, debuggers, profilers, and `/proc`** at the same level as secret read access. Anyone allowed to attach a debugger or dump process memory can usually inspect credentials even when secrets are delivered via Vault.

## 13. Proper rotation and revocation

"Separating secrets from source" only pays off long term when paired with a **rotation/revocation** schedule and procedure. Design a process with an owner, expiration, rollback plan, and post-rotation evidence.

### General procedure

1. **Inventory:** which secrets exist, which workloads use them, their source, permission scope, expiration date, owner, and revocation impact.
2. **Generate a new version** via CSPRNG/KMS/provider; never reuse a secret from another environment.
3. **Provision** the new secret into the managed store, verify ACLs/authorization, expiration, and auditing.
4. **Roll out** workloads gradually; if the provider allows old and new secrets simultaneously, use a bounded overlap window.
5. **Smoke/integration test** with the new workload and monitor auth error/5xx/latency metrics on canary; avoid logging secrets in telemetry.
6. **Switch all clients**, confirming no requests still use the old secret.
7. **Revoke/disable** the old secret at the provider, not just by deleting a file/env on one instance.
8. **Monitor and record**: deployed version, overlap end time, verification results, and approver.
9. **Deliberate rollback**: never re-enable a secret confirmed to be compromised. If a credential is leaked, an emergency procedure without keeping the old overlap is required.

### Passwords / bootstrap operators

If a password or hash is suspected of compromise, change the raw password, generate a new hash, provision the new hash, invalidate active sessions if policy requires, and verify operation. Simply changing the `{bcrypt}` prefix is not rotation. If the bootstrap user is no longer needed, remove it and disable the credential.

### OAuth2 client secrets

A provider may allow creating a second secret during a transition period. Swap the secret in runtime, test fetching a new token, monitor client authentication errors, then revoke the old secret. **Do not** assume all providers support multiple simultaneous secrets: check provider documentation and coordinate a maintenance window/downtime if needed.

### JWT signing keys

With asymmetric signing, publish the **new public key** in JWKS (with `kid`), switch the issuer to sign with the new private key, keep the old public key long enough for unexpired old tokens (unless emergency revocation is required), then remove the old key. Clients must validate issuer, audience, algorithm, expiry, and cache/refresh JWKS properly. A suspected compromise of the old private key may force immediate revocation, accepting token invalidation.

With a shared HMAC key, signers and verifiers must be coordinated together; keep both old and new versions under control if existing tokens remain valid. Do not assume updating an env var on one node rotates all nodes.

### Encryption keys

Rotating encryption keys requires a plan for **decrypting legacy data** and rewrapping/re-encrypting. With envelope encryption, rotating the KEK (key encryption key) can be done by rewrapping the DEK (data encryption key) without decrypting all data, depending on design. Never delete the old key before verifying that data/backups have been migrated or a recovery strategy exists.

## 14. When a secret is suspected of being committed or sent by mistake

Incident response must not stop at "deleting the file":

1. **Identify** the secret type, exposure vector (Git, CI logs, artifacts, chat, tickets, images, crash dumps), timeframe, and access scope.
2. **Restrict access immediately**, prioritizing credential revocation/rotation first; for exposed signing keys, consider revoking tokens and investigating forged tokens.
3. **Audit** logins, token issuance, DB access, KMS operations, and signs of abuse.
4. **Fix the leak source** in build/logs/config; remove it from current source and from artifacts/logs permitted to be purged.
5. **Clean history** (where organizational policy allows) to reduce ongoing exposure, but do not rely on rewriting Git history to invalidate a secret that may already have been copied.
6. **Expand investigation** to forks/clones/caches/mirrors and resources sharing the credential.
7. **Add controls**: pre-commit/CI secret scanning, config reviews, least privilege, TTLs, and rotation automation.

Do not run `git filter-repo` or arbitrary history-rewriting commands on a shared multi-user repository without coordination; rewriting history can break collaborators' sync. **Rotation/revocation is mandatory whenever a secret is exposed**, even after scrubbing history.

## 15. Testing secret configuration and deployment

A good test suite needs no knowledge of production credentials. You can use **fake/test-only secrets** and mock secret managers, then run smoke tests with workload identity upon deployment.

| Case | How to test | Expected |
|---|---|---|
| App lacks `APP_OPERATOR_PASSWORD_HASH` | Run runtime profile without env/mount | Startup fails clearly, no default password used |
| Malformed hash | Provide a string without `{bcrypt}` | Fail fast, value not written to logs |
| Valid password | MockMvc HTTP Basic with runtime test hash | 200 and `ROLE_OPS`, hash not returned |
| Wrong password / anonymous | Call protected APIs | 401, no secret exposed |
| Secret file permission denied | Simulate mount lacking read permission | Startup fails, alert metric; no hardcoded fallback |
| Env and secret file conflict | Provide both configs in a test | Clear priority determined, rejected or actively selected per policy |
| CI log/artifact scan | Scan variables/credential markers in artifacts | No secret values; false positives reviewed |
| Container image scan | Inspect layers/build history | No `.env`, `*.key`, raw secrets, or credentials in history |
| OAuth client rotation | Issue new version, test token endpoint, revoke old | Workload uses new secret, old secret no longer used |
| JWT key rollover | Issuer signs with new key, verifier uses JWKS with `kid` | Valid tokens verify, wrong key rejected, no private key on verifier |
| Multi-instance rollout | Pod A/B run different versions as planned | No unapproved downtime; overlap ends cleanly |
| Emergency revocation | Suspected leaked credential is disabled | Requests with old credential fail; audit logs record event without leaking secret |

The Spring Boot test suite in section 5 covers part of this table: it proves the app binds the hash from a test property and authenticates valid/invalid credentials. Infrastructure cases require chaos/smoke tests in authorized environments; **never intentionally revoke a production key as a test** without a change plan.

### QA rules for secret hygiene

- Scan source, test fixtures, and Git history per organizational policy; also check source maps, Docker build layers, and CI artifacts.
- Never place production secrets into snapshot tests or golden files.
- Generate secrets randomly via CSPRNG and provision per environment; demos may use public values **only if they do not collide with any real system**.
- Verify the app refuses to start when required secrets are missing; failure messages must not leak raw secrets.
- Verify logs and error bodies contain no password hashes, OAuth2 client secrets, private keys, JWT/Bearer tokens, or API keys.
- Verify session/expiry policies, auditing, scopes, and rotation; do not evaluate secret hygiene only at build time.

## 16. Common deployment issues and diagnostics

### App reports unresolved placeholder

For example, an error on `app.auth.operator-password-hash`. Check that the variable name is exact, the deployment injected it into the **right container/process**, case sensitivity, YAML quoting, and startup timing. Do not fix it by adding a weak default credential. You can inspect `printenv` **for variable names only** via a safe mechanism; never dump values to CI logs.

### Spring Security returns 401 even though env has a value

Possible causes: the hash lacks the `{bcrypt}` prefix, the raw password does not match the verifier, the account is locked, or the wrong provider is active. Check safely at a boolean level in logs: did user lookup succeed? was the hash encoding recognized? did password `matches` succeed? Never send hashes or `PasswordEncoder` internals to clients. A bcrypt hash must be checked with `matches`, not by re-encoding the candidate and comparing strings.

### OAuth2 token endpoint returns invalid_client

Check `client-id`, client authentication method, secret version, token URI, encoding, clock/expiry policy, and network/TLS. Do not print the `Authorization` header or responses containing tokens. If the provider recently rotated the secret, check deployment sync and whether old/new credentials can coexist.

### JWT signature verification fails after rotation

Check `kid`, JWKS cache, issuer, audience, algorithm, clock skew, and token issuance time. Resource servers verify using a trusted public key/JWKS; never share the private key just to work around verification errors. If using symmetric signing, verify the right key version across all nodes.

### Secret mount exists but app still uses the old value

Environment variables do not update inside a running process when a Kubernetes Secret is updated. File mounts also do not guarantee that Spring beans automatically rebind. Determine the integration's rollout/refresh mechanism, cache TTL, bean/client lifecycle, and active version; do not try printing keys to compare.

### Old decryption key is lost

If ciphertext was created with a deleted key, the application cannot decrypt it even with a new key. Locate backups or previous key versions under KMS policy and restore through controlled procedures; do not run ad-hoc scripts guessing keys against unauthorized production data.

## 17. Pre-production checklist

1. **Inventory:** every password/client secret/API key/private key/encryption key has an owner, scope, environment, expiry, and rotation plan.
2. **No hardcoding:** repository, history, JARs, images, Dockerfiles, frontend bundles, Helm values, CI caches, and logs have been reviewed.
3. **Secret source:** application receives configuration from a runtime store/mount/identity; contains no real fallback credentials or weak defaults.
4. **Least privilege:** service accounts read only the secrets they need, without permission to list an entire vault/namespace unnecessarily.
5. **TLS/transport:** HTTPS/mTLS used appropriately; secrets are never sent in URLs/queries or over insecure channels.
6. **Storage:** secret manager encrypts at rest and audits access; private keys managed by KMS/HSM where appropriate; backup/restore controlled.
7. **Validation:** app fails fast on missing/malformed secrets, and exceptions report only property names/error types.
8. **Authentication:** raw user passwords are never stored; verifiers use `PasswordEncoder` with proper algorithm/cost; OAuth2 client secrets never reach the browser.
9. **Cryptography:** asymmetric public/private keys properly separated; HMAC/AES keys have sufficient entropy; `kid`, audience, issuer, nonces, and key versions handled.
10. **Rotation:** overlap/rollout/revoke/rollback procedures exist, canary-tested, handling legacy tokens/ciphertext and compromise incidents.
11. **Observability:** logs/Actuator/crash dumps/traces leak no secrets, error messages print no values, and debug access is restricted.
12. **CI/CD:** tests use fake secrets; deployments use workload identity or OIDC federation, never writing credentials to shell history/artifacts.
13. **Infra:** Kubernetes RBAC, encryption at rest, filesystem permissions, network policies, and secret injection verified.
14. **Testing:** tests for missing secrets/bad credentials/rotation/permissions/side effects exist and run through the actual deployment path.

## 18. Practice exercises and self-check questions

1. Why is deleting a password from a new commit without **rotating** the exposed credential insufficient?
2. Why does storing `{bcrypt}$2b$...` in a user database not mean the application needs to retain the raw password?
3. Why must the `client-secret` of an OAuth2 confidential client never be embedded in an SPA?
4. If an app runs locally but fails to start in Kubernetes because `APP_OPERATOR_PASSWORD_HASH` does not exist, which fix is more secure: provisioning the secret properly or adding a `changeme` default?
5. In Spring Boot, what are the differences between env placeholders, configtree file mounts, and a secret manager SDK? Which ones automatically update values in running beans?
6. If a resource server only needs to verify RS256 JWTs, should it hold the private or public key? Why?
7. Is Base64 encoding sufficient to protect `Kubernetes Secret.data`? What additional measures are needed?
8. In a multi-tenant app, why should each tenant/service have separate credentials and scopes?
9. When rotating a JWT signing key, why is it usually necessary to keep the old public key in JWKS for some time?
10. For an AES-GCM key used on long-lived data, why can immediately replacing it and deleting the old key cause data loss?
11. Reading a stack trace shows `invalid_client`, but the system is logging the raw token response. What parts need to be fixed simultaneously?
12. If a Secret volume is updated, why might a Spring Boot bean keep using the old secret until a rollout or refresh?
13. How do you write a test proving the app fails fast when configuration is missing without putting production secrets into CI?
14. Why does `.gitignore` not protect a credential file that was previously tracked by Git?
15. If the system has a KMS signing API, what benefit comes from the app not receiving the raw private key? How must KMS invocation permissions still be protected?

**Conclusion:** never "put secrets in a config file" and call it done. Keep **secret values out of source and artifacts**, receive them via runtime identity/secret managers or permissioned secret mounts, bind/validate through Spring Boot, prevent leakage via logs/HTTP/CI, verify credential types, and maintain rotation/revocation. Source code holds only the configuration contract; deployment decides **who gets which secret, when, and how**.

## References

- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot 3.5 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — OAuth2 Client](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/index.html)
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — Encryption at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/)
- [Spring Vault — Reference Documentation](https://docs.spring.io/spring-vault/reference/)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP — Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
