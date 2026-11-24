# Removing Demo Accounts, Passwords, and Sample Configurations Before Deploying Spring Security

> **Context:** Spring Security on Spring Boot 3.x / Servlet MVC, Java 17+. Part of the **Deployment** group. This lesson focuses on turning a learning app or proof of concept into a deployment with **real identity mechanisms**, **zero sample accounts/passwords/keys**, **zero demo-only security rules**, and verification layers across source code, configuration, CI/CD, and runtime environments.

## 1. Why is this a separate deployment step?

During learning, the following configuration snippets often help test functionality quickly:

- `InMemoryUserDetailsManager` containing `admin`, `demo`, or `test` users with fixed passwords.
- `spring.security.user.name=admin`, `spring.security.user.password=123456` in `application.properties`.
- `User.withDefaultPasswordEncoder()`, `NoOpPasswordEncoder`, or `{noop}password` passwords.
- `http.csrf(csrf -> csrf.disable())`, `requestMatchers("/**").permitAll()`, or `anyRequest().permitAll()` for "debugging".
- Sample HMAC/RSA keys, JWTs, API keys, client secrets, database passwords, and connection strings in source code.
- Publicly exposed H2 console, actuator endpoints, Swagger UI, test controllers, `/debug/**`, `/dev-login`, or test data.
- `@Profile("dev")` or `app.demo.enabled=true` flags that can still be enabled in production.
- Spring Security DEBUG/TRACE logging and filters printing `Authorization`, `Cookie`, passwords, or tokens.

These pieces are **not just dead code**. They can become an **unmanaged second authentication path**, a public secret already exposed in Git history, or an endpoint that bypasses all authorization checks.

**The real goal is not just changing `password=demo` to a harder-to-guess string.** You must audit all other access paths, credential sources, permissions, keys/tokens, preloaded data, and startup behavior when configuration is missing.

### Outcomes required before go-live

1. No demo accounts or sample passwords able to log in exist in the production artifact or environment.
2. No sample signing secrets, private keys, API keys, refresh tokens, database passwords, or client secrets used for real services remain.
3. No demo security bypasses remain: overly broad `permitAll`, bypassed filters, CSRF/CORS disabled under the wrong model, or public debug/H2 endpoints.
4. The production authentication path is chosen **explicitly**: IdP/OIDC/OAuth2 Resource Server, LDAP, or a managed production user store.
5. If a required configuration is missing or a dangerous demo flag is detected, the system **must not silently open access**.
6. CI/CD verifies **source code, merged configuration, Docker image/JAR, and deployment environment**, not just passing tests.
7. A **rotation/revocation** plan exists for any secret or demo account ever placed in repositories, docs, logs, or environments accessible to others.

## 2. Inventorying by attack surface

Do not search only inside `SecurityConfig.java`. Inventory **every place that can create credentials or alter policy**:

| Location | Indicators to review | Risk if left behind |
| --- | --- | --- |
| `src/main/java` | `User.withUsername("admin")`, `InMemoryUserDetailsManager`, sample `AuthenticationProvider`, custom login controllers | Secret/hardcoded account exists in build |
| `src/main/resources` | `spring.security.user.*`, fake issuer, CORS `*`, `spring.h2.console.enabled=true`, `local` profile | Dev config gets packaged and activated |
| `src/test/**` | Test fixtures, fake keys, `@WithMockUser` | Usually allowed in **test scope**; verify they are never packaged or copied into main |
| `Dockerfile` / Helm / manifests | `ENV ADMIN_PASSWORD=...`, default secrets, build args, init containers creating users | Secrets embedded in image layers or deploy manifests |
| CI/CD | Variables, pipeline echoes, build args, artifacts, release notes | Credentials logged or replicated across environments |
| Database | Seed migrations creating `admin/admin`, demo user tables, sample PII data | Users can still log in even after Java code is deleted |
| Identity provider | Test realms, OAuth2 clients, admin users, client credentials, sample redirect URIs | External authentication path left open |
| Reverse proxy / gateway | `/debug` routes, auth bypasses, trusting client-supplied `X-User` or `X-Roles` | Bypassing Spring Security checks at the edge |
| Observability | DEBUG/TRACE, exception dumps, HAR files, request body/header logging | Passwords, JWTs, session IDs end up in logs |
| Documentation / support | READMEs containing working passwords, token screenshots, runbooks | Secrets shared outside control |
| Object storage / backups | Old config files, DB dumps, exports containing secrets | Deleting at HEAD does not mean data disappeared elsewhere |

**Rule:** mark each item's status: **removed from runtime**, **present in tests only**, **rotated/revoked if previously exposed**, **verified in artifacts and environments**. Deleting a line of code without checking the DB/IdP/image is incomplete.

## 3. Distinguishing default accounts, sample accounts, and production accounts

### 3.1. Spring Boot's default account

When Spring Security is on the classpath and the application has not provided its own appropriate authentication mechanism, Spring Boot may auto-configure a default user named `user` with a random password printed in startup logs (suitable for development, **not a production identity**). `spring.security.user.name`/`spring.security.user.password` override that default.

Common points of confusion:

- Adding a `SecurityFilterChain` bean may replace **default web security** without necessarily removing the `UserDetailsService` created by auto-configuration.
- A `UserDetailsService`, `AuthenticationProvider`, or `AuthenticationManager` bean can prevent the default user from being created. Modules such as OAuth2 Resource Server/OAuth2 Client also affect auto-configuration conditions. Inspect **actual beans and mechanisms** for your dependency/version rather than guessing from logs.
- "Randomly generated password" does not mean the app has a user store with proper identity governance, authorization, MFA, offboarding, or auditing.
- If production unexpectedly prints "Using generated security password", that is a **signal to investigate authentication configuration**; do not use that password for operations.

Do not treat `spring.security.user.password=RANDOM_SECRET_FROM_ENV` as a complete solution for a multi-user product. It still creates a shared account lacking lifecycle or proper permission governance if misused.

### 3.2. When is `InMemoryUserDetailsManager` appropriate?

Common example:

```java
// ILLUSTRATION — MUST NOT BE DEPLOYED TO PRODUCTION:
@Bean
UserDetailsService demoUsers() {
    UserDetails user = User.withUsername("admin")
        .password("{noop}admin123")
        .roles("ADMIN")
        .build();
    return new InMemoryUserDetailsManager(user);
}
```

The snippet above is strictly an illustration of an **unsafe configuration to identify**, not a file used in the production example later.

Drawbacks:

- Username/password are visible to anyone reading the code or artifact.
- `{noop}` compares unhashed passwords; anyone reading the source immediately knows the credential.
- No workflow for creating/locking/revoking accounts, MFA, password resets, or per-user auditing.
- Can coexist alongside an IdP if the app adds an uncontrolled provider; this is a **backdoor created by configuration itself**.

In tests, use `@WithMockUser`, `with(user(...))`, security test fixtures, or a test user store **strictly separated from the production build**. If local users are needed to demo UI, prefer a dedicated environment/scope and never package that config into release artifacts.

### 3.3. Never use `User.withDefaultPasswordEncoder()` or `NoOpPasswordEncoder` to store real passwords

Snippets using simple encoders help demonstrate concepts but do not meet production password management requirements. For a self-managed user/password system, use a standard `PasswordEncoder` with an algorithm upgrade policy—such as `DelegatingPasswordEncoder` with `bcrypt`/`argon2` per supported configuration—along with migration handling and brute-force/credential-stuffing controls.

```java
// ILLUSTRATION of a component usable in a self-managed user store:
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

Required imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
```

**Having the right encoder is not enough.** You still need user provisioning, unique usernames/identities, password policies, MFA where needed, account locking/rate limiting, reset flows, auditing, role lifecycles, and data-level authorization checks. If your organization already has OIDC/SSO, do not build your own password store merely because a Spring Security demo used form login.

## 4. A 5-layer process to eliminate sample configurations

### Layer 1 — Remove disallowed mechanisms

- Remove `InMemoryUserDetailsManager` in `src/main` and any provider accepting demo credentials.
- Remove `/test-login`, `/generate-token`, `/debug-auth`, and controllers/filters used to bypass authentication.
- Review `@Profile`: merely having `@Profile("dev")` is **not sufficient proof**, because profiles can be misconfigured in production. Ideally, do not package demo classes into production artifacts at all.
- Remove account seeds in migrations or ensure production migrations never execute demo-account creation steps.
- On the IdP side, disable/delete demo users and demo client credentials outside the application.

### Layer 2 — Replace authentication with an official source

Depending on the system:

- **API**: OAuth2 Resource Server verifying access tokens from a trusted issuer with `iss`/`aud`/`exp`/signature/scope checks.
- **Web**: `oauth2Login` via an IdP with managed session cookies, or a real user store with an appropriate `PasswordEncoder`.
- **Machine-to-machine**: client credentials/workload identity, explicit scopes/audiences, and secret/certificate/key rotation.
- **Hybrid**: multiple `SecurityFilterChain` beans separating session-based web from Bearer APIs, or a BFF.

Never replace one demo account with a single org-wide shared "admin" account. Each user or service principal must be identifiable, follow least privilege, and be offboardable.

### Layer 3 — Move secrets out of source code and manage their lifecycle

- Use a secret manager, appropriately permissioned secret mounts, or an organization-approved configuration mechanism.
- Provision secrets per environment and workload identity; never share the same secret across local, staging, and production.
- Track an **owner**, purpose, access scope, rotation schedule, access audit trail, and expiry/revocation policy.
- Never print secrets in application logs, command-line arguments, shell history, stack traces, test reports, metric labels, or error responses.
- Never allow CI/CD to echo full environment variables or secret files.
- If a secret was ever committed to Git, treat it as **potentially compromised**; rotate/revoke it rather than merely deleting the line and force-pushing.

### Layer 4 — Remove bypasses and debug exposures

- Audit `authorizeHttpRequests` for every HTTP method and route; prefer **deny by default** for undeclared endpoints.
- Audit `web.ignoring()`/`permitAll()`, matcher ordering, and all `SecurityFilterChain` beans; inspect routes like `/api/admin`, `/actuator/**`, `/h2-console`, `/swagger-ui/**`, `/v3/api-docs`, `/error`, and file exports/attachments.
- Re-evaluate `csrf.disable()` against your credential model. Header-only token APIs may omit CSRF; cookie-based web/BFF apps usually cannot.
- Never use CORS `*` with credentials, and never treat CORS as authorization.
- Disable the H2 console, debug actuator exposure, test controllers, profiler endpoints, and test data in deployed environments.
- Lower Spring Security DEBUG/TRACE logging to an appropriate production level with redaction and correlation IDs.

### Layer 5 — Gate mistakes with tests and release checks

- Unit/integration tests verify anonymous callers cannot access private endpoints and under-privileged users cannot access admin routes.
- Include tests for invalid/expired/wrong-audience tokens, CSRF, session logout, or user-store behavior matching the model.
- Run **static/secret scans** on source and commit history, **artifact scans** post-build, and verify deploy manifests, secret references, and live smoke tests.
- Block deployment whenever demo flags, hardcoded secrets, missing required env vars, active sample principals, or public debug endpoints are detected.
- Maintain change review, recorded evidence, rollback plans, and rotation playbooks.

## 5. Before/after: from learning config to deployment config

### 5.1. Risky pattern before cleanup

```java
// UNSAFE EXAMPLE — shown only to point out mistakes to remove.
@Configuration
public class DemoSecurityConfig {

    @Bean
    UserDetailsService users() {
        var admin = User.withUsername("admin")
            .password("{noop}admin")
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(admin);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/debug/**").permitAll()
                .anyRequest().permitAll()
            );
        return http.build();
    }
}
```

Flaws: the demo account has a plaintext password with no provisioning lifecycle, CSRF is disabled without a threat model, `/debug/**` is public, and `anyRequest().permitAll()` opens every URL. Changing the password alone does not fix the authorization bypass.

### 5.2. Illustrative production baseline design

This lesson chooses a **Bearer access-token-only API**; the resource server uses an OAuth2 issuer managed by the organization. This is **one specific illustrative choice**, not a one-size-fits-all solution for browser sessions. If your app is a cookie-based web app, configure a separate web chain/session/CSRF policy instead of blindly copying `STATELESS` or `csrf.disable()`.

Baseline goals:

- No `InMemoryUserDetailsManager`, `admin` user, or passwords in main source code.
- The app never mints its own JWTs and uses no sample HMAC secret.
- JWTs must match environment-configured issuer/audience and carry `SCOPE_items.read`/`SCOPE_items.write` authorities.
- Unlisted routes are rejected with `denyAll()`; only health checks are public if deployment policy allows.
- A startup guard catches several **known demo flags**; static scanning/reviews are still required to catch bypasses unknown to the guard.
- Security tests use `spring-security-test` in **test scope** without creating runtime credentials.

## 6. Spring Boot 3.x / Java 17+ project layout

Structure:

```text
production-security-baseline/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── resources/application.yml
    │   └── java/com/example/deploysecure/
    │       ├── SecureApplication.java
    │       ├── SecurityConfig.java
    │       ├── DeploymentGuard.java
    │       ├── ItemService.java
    │       └── ItemController.java
    └── test/java/com/example/deploysecure/
        ├── SecurityBoundaryTest.java
        └── DeploymentGuardTest.java
```

**Runnable scope:** the Java files can compile in a Spring Boot Gradle project once dependencies and configuration are supplied. Real startup requires a **valid OAuth2 issuer**, official audience, and appropriate network/environment; tests mock `JwtDecoder` to avoid depending on an external IdP. This is not an out-of-the-box template for creating user accounts or issuing tokens in production.

### 6.1. `settings.gradle`

```groovy
rootProject.name = 'production-security-baseline'
```

### 6.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The version in this guide is a **lab baseline for the Boot 3.3/Security 6 API**, not a permanently recommended production version. When deploying for real, upgrade to a currently supported release, patch CVEs in your chosen branch, and run dependency/SBOM/vulnerability scans.

### 6.3. `application.yml` — keeping only safe references

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OIDC_ISSUER_URI}
          audiences:
            - ${API_AUDIENCE}

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never

logging:
  level:
    org.springframework.security: INFO
```

**Key points:**

- `OIDC_ISSUER_URI` and `API_AUDIENCE` are injected from the environment/governed configuration system. Never hardcode a fake IdP URL into production "just to let it start".
- No `spring.security.user.name/password`, `app.demo.user`, or sample tokens/passwords.
- `management.endpoints.web.exposure.include` limits **exposed endpoints**; securing them still depends on `SecurityFilterChain` and deployment networking. Only `health` is public in this example; `info` remains blocked by authorization.
- Do not enable `spring.h2.console.enabled`, debug logging, or actuator wildcards.
- Do not store `spring.profiles.active=dev` in the artifact, and do not include `application-dev.yml` files with credentials in the production image.
- If issuer/audience are absent, required configuration will fail to resolve/initialize properly. In real systems, add **pre-traffic config validation** and separate health/readiness probes.

**Version note:** `spring.security.oauth2.resourceserver.jwt.audiences` is a Boot property for validating `aud` in Boot versions that support it. On other versions or with a custom `JwtDecoder`, verify that an audience validator is **actually wired in**, rather than setting YAML and assuming it works. Test with a validly signed JWT carrying the wrong audience in integration tests.

### 6.4. `SecureApplication.java`

```java
package com.example.deploysecure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecureApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecureApplication.class, args);
    }
}
```

### 6.5. `SecurityConfig.java` — no sample accounts, no authentication bypass

```java
package com.example.deploysecure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/items")
                    .hasAuthority("SCOPE_items.read")
                .requestMatchers(HttpMethod.POST, "/api/items")
                    .hasAuthority("SCOPE_items.write")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // Valid ONLY for a Bearer-only API without auto-sent cookies.
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
```

Clarifying commonly misunderstood points:

- `@EnableMethodSecurity` enables `@PreAuthorize` on Spring-managed beans invoked through proxies; service rules complement URL authorization rather than replacing it.
- `requestMatchers("/actuator/health").permitAll()` is an **intentional decision for health probes**. If organizational policy forbids public health endpoints, place it behind network policy/gateway or adjust the rule accordingly. Never use `/actuator/**.permitAll()`.
- `GET` requires `SCOPE_items.read`, `POST` requires `SCOPE_items.write`. There is no default `hasRole("ADMIN")` or blanket `permitAll`.
- `anyRequest().denyAll()` fails closed for undeclared endpoints. Depending on error-handling requirements, check the `ERROR` dispatcher separately to avoid breaking error rendering; **never open all routes** just to see nicer errors.
- `STATELESS` and `csrf.disable()` in this example are **specific to a Bearer-header-only API**. If the app adds session cookies or a BFF to the same chain, re-evaluate instead of copying blindly.
- `oauth2ResourceServer().jwt()` obtains the Boot-configured decoder from issuer/audience rather than reading a hardcoded HMAC secret from source.
- Because the OAuth2 Resource Server dependency is present, Spring Boot applies auto-configuration conditions around the default `UserDetailsService`; **you must still inspect runtime beans and filter chains** rather than assuming "no generated password logged" is sufficient proof.
- Production security still requires HTTPS, token issuance policies, JWKS key rotation, logging, rate limiting, data authorization, and gateway controls.

### 6.6. `DeploymentGuard.java` — rejecting dangerous flags at startup

Deleting sample accounts is not enough if the deploy pipeline could still inject `spring.security.user.password` or enable consoles/debug flags. A small guard catches **known** misconfigurations, though it does not replace static scans or penetration tests:

```java
package com.example.deploysecure;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public final class DeploymentGuard implements InitializingBean {

    private final Environment environment;

    public DeploymentGuard(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void afterPropertiesSet() {
        // Disallow sample single-user authentication configuration in all environments.
        rejectIfSet("spring.security.user.name");
        rejectIfSet("spring.security.user.password");

        // app.demo.* properties are project example conventions,
        // NOT default Spring Security properties.
        rejectIfTrue("app.demo.enabled");
        rejectIfTrue("app.auth.bypass.enabled");

        // Never expose the H2 console in any deployment environment
        // using this production artifact.
        rejectIfTrue("spring.h2.console.enabled");
    }

    private void rejectIfSet(String name) {
        if (environment.containsProperty(name)) {
            throw new IllegalStateException(
                "Disallowed legacy account configuration: " + name
            );
        }
    }

    private void rejectIfTrue(String name) {
        if (Boolean.parseBoolean(
                environment.getProperty(name, "false"))) {
            throw new IllegalStateException(
                "Unsafe demo configuration is enabled: " + name
            );
        }
    }
}
```

**Why is this guard useful?**

- Enforces the "no sample accounts" policy directly at runtime instead of relying solely on humans remembering to delete a property.
- Rejects misconfiguration instead of silently serving requests with a bypass.
- Logs only the **property name**, never printing password values or secrets in exceptions/logs.
- `InitializingBean.afterPropertiesSet()` runs during bean initialization; failures prevent the `ApplicationContext` from starting normally.

**Mandatory limitation:** this guard knows only the listed properties. It **does not** detect a hardcoded `/debug/login` controller, manual `permitAll()`, seeded DB accounts, or tokens in Docker layers. Nor does it replace startup environment controls from the deployment platform. Guard tests and static scans are both required.

If a project also has a local environment that legitimately uses `spring.security.user.*`, **do not disable the guard with a `prod` profile** and call it done; use a separate lab/test artifact that does not ship demo configs to production. Production apps should enforce the baseline unconditionally rather than relying on an easily omitted `prod` flag.

### 6.7. `ItemService.java` — use-case authorization

```java
package com.example.deploysecure;

import java.util.List;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ItemService {

    @PreAuthorize("hasAuthority('SCOPE_items.read')")
    public List<ItemView> list() {
        return List.of(new ItemView("sample-1", "Non-sensitive example"));
    }

    @PreAuthorize("hasAuthority('SCOPE_items.write')")
    public ItemView create(String title) {
        return new ItemView("preview-only", title);
    }

    public record ItemView(String id, String title) {
    }
}
```

This is a **simulated in-memory use case without DB persistence** to test authorization. Do not treat the `preview-only` ID or this lesson's response as real persisted data. In a real product, the service must enforce tenant, owner, record state, transaction, and field limits before persisting via an appropriate repository.

### 6.8. `ItemController.java` — input DTO instead of entity

```java
package com.example.deploysecure;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping
    public List<ItemService.ItemView> list() {
        return service.list();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ItemService.ItemView create(
            @Valid @RequestBody CreateItemRequest request) {
        return service.create(request.title());
    }

    public record CreateItemRequest(
        @NotBlank @Size(max = 120) String title
    ) {
    }
}
```

The controller does not accept arbitrary `ownerId` or `tenantId` fields from the client and treat them as authorization. That is a separate object-level authorization requirement that cannot be "solved" merely by removing demo accounts. Valid JSON request tests require `Content-Type: application/json`.

## 7. Testing the baseline before release

You must prove both that it **works when configured properly** and **fails when misconfigured**. Below are tests for the lab code in section 6; they use `spring-security-test` to verify permissions without requiring a live issuer during unit/integration tests.

### 7.1. `SecurityBoundaryTest.java`

```java
package com.example.deploysecure;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "OIDC_ISSUER_URI=https://idp.example.invalid/issuer",
    "API_AUDIENCE=business-api"
})
@AutoConfigureMockMvc
class SecurityBoundaryTest {

    // Boot 3.3 uses @MockBean; newer Boot versions provide @MockitoBean.
    // Mock JwtDecoder so tests do not call an external IdP.
    @MockBean
    JwtDecoder decoder;

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadPrivateItems() throws Exception {
        mvc.perform(get("/api/items"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readScopeCanRead() throws Exception {
        mvc.perform(get("/api/items")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_items.read")
                )))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value("sample-1"));
    }

    @Test
    void wrongScopeCannotRead() throws Exception {
        mvc.perform(get("/api/items")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_items.write")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerCanPost() throws Exception {
        mvc.perform(post("/api/items")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_items.write")
                ))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Example\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Example"));
    }

    @Test
    void readerCannotPost() throws Exception {
        mvc.perform(post("/api/items")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_items.read")
                ))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Denied\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownEndpointIsNotPublic() throws Exception {
        // Do not bind strictly to 403/404 if error dispatch changes,
        // but the API must not return a successful business response.
        mvc.perform(get("/api/debug").with(jwt()))
            .andExpect(result -> {
                int status = result.getResponse().getStatus();
                org.junit.jupiter.api.Assertions.assertTrue(
                    status == 403 || status == 404
                );
            });
    }
}
```

Explaining the results: `@SpringBootTest` + `@AutoConfigureMockMvc` wires Servlet/Spring Security filters; `jwt()` creates a test security principal. `@MockBean JwtDecoder` keeps tests from contacting a real IdP/JWKS, so **this test does not prove signature, issuer, and audience validation**. You must have separate tests exercising `BearerTokenAuthenticationFilter` with genuinely signed JWTs and a mock JWKS or staging IdP.

For an `oauth2ResourceServer` API, anonymous requests typically return 401; a valid token missing `SCOPE_items.read` typically returns 403. Tests following this sample only evaluate app and service rules—do not call them a full pentest or production audit.

### 7.2. `DeploymentGuardTest.java`

```java
package com.example.deploysecure;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DeploymentGuardTest {

    @Test
    void cleanPropertiesPass() {
        DeploymentGuard guard = new DeploymentGuard(new MockEnvironment());
        assertDoesNotThrow(guard::afterPropertiesSet);
    }

    @Test
    void legacyPasswordPropertyFails() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("spring.security.user.password", "dummy-for-test");

        DeploymentGuard guard = new DeploymentGuard(environment);
        assertThrows(IllegalStateException.class,
            guard::afterPropertiesSet);
    }

    @Test
    void demoEnabledFails() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("app.demo.enabled", "true");

        assertThrows(IllegalStateException.class,
            () -> new DeploymentGuard(environment).afterPropertiesSet());
    }

    @Test
    void h2ConsoleEnabledFails() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("spring.h2.console.enabled", "true");

        assertThrows(IllegalStateException.class,
            () -> new DeploymentGuard(environment).afterPropertiesSet());
    }
}
```

The value `dummy-for-test` is strictly a test string in `src/test`, **not an active account**, and is never shipped. This test verifies fail-closed behavior for known properties; it does not scan the whole codebase.

### 7.3. Run commands

```bash
# When the project has an appropriate Gradle wrapper:
./gradlew clean test

# Inspect runtime dependencies and build the release artifact.
./gradlew dependencies --configuration runtimeClasspath
./gradlew bootJar
```

For a new project without a Gradle wrapper, run with a compatible Gradle installation or generate the wrapper per your organization's standard process. There is no fixed stdout; JUnit/Gradle determines pass/fail. **You cannot consider the app ready to deploy just because `test` passes**: scanners, artifact inspection, and live IdP/HTTPS testing are still required.

### 7.4. Negative tests that must not be skipped

In addition to the tests above, release-level integration tests should cover:

- JWTs with invalid signatures, untrusted algorithms, wrong `iss`, wrong `aud`, expired tokens, and missing scopes.
- `Authorization: Basic ...` and session cookies must be rejected on a token-only API.
- No default `user`/`demo`/`admin` account can log in through any route, except properly provisioned real identities.
- `/h2-console`, `/debug/**`, `/internal/**`, Swagger, and actuator endpoints all follow deployment policy.
- No overly broad `permitAll()` or filter bypasses.
- CORS/CSRF match the client model; never disable CSRF in web session tests.
- Tenant/owner queries never leak cross-tenant data even with a valid token.
- After disabling an account or revoking a token, subsequent requests follow the published expiration and revocation policy.
- Missing issuer/secret/required configuration never causes the app to fall back to a demo user or `permitAll`.
- Actual Docker/JAR images and deploy manifests contain no sample credentials.

## 8. Secret management: moving secrets does not automatically make them safe

### 8.1. Where should secrets live?

Each environment needs a controlled secret provider:

```text
Source code + build artifact
   |
   | Contains ONLY configuration NAMES / secret references
   v
Deployment configuration / workload identity
   |
   v
Secret manager or ACL-protected secret mount
   |
   v
Process receives credentials at runtime
   |
   +-- Used via JDBC/IdP/SMTP/third-party API
   +-- Never printed to logs, crash reports, or HTTP errors
```

Each option has different characteristics:

- **Secret manager** with IAM, auditing, versioning, rotation, and per-workload permissions is generally better than passwords in YAML.
- **Environment variables** are convenient but can show up in process inspection, debug dumps, or ops tooling; restrict read access and never echo them.
- **Mounted secret files** allow file permission/rotation management, but require protecting paths, caches, backups, and application reload behavior.
- **Kubernetes Secrets** are secret-holding objects; Base64 encoding **is not encryption**. Protect etcd, RBAC, encryption-at-rest, and cluster admission policies.
- **CI/CD variables** must not be echoed or baked into artifacts. Build-time secrets differ from runtime secrets; never use Docker `ARG`/`ENV` to bake credentials into image layers.

For JWT resource servers using asymmetric signing, **public keys/JWKS are not private signing keys**; resource servers usually need only the public verification key/issuer config. Never copy the authorization server's private signing key into every API.

### 8.2. What to do if a secret was ever committed?

Response procedure:

1. Classify the secret: DB credential, OAuth client secret, JWT signing key, access token, API key, user password, session secret.
2. **Rotate/revoke at the provider** or disable the account/token. Deleting from Git does not revoke usability of the old secret.
3. Identify any logs, artifacts, CI backups, registries, or documentation that may have captured the secret.
4. Update the secret manager/workloads with the new version and verify services run with the new secret.
5. Watch for anomalous access before and after rotation; coordinate with security/incident response if exposure poses real risk.
6. Only after invalidating the secret, handle scrubbing branches/history/screenshots/docs per policy—never arbitrarily force-push and break team history.
7. Add detection rules to prevent recurrence.

**When a JWT signing key is exposed, key rotation must account for tokens already in circulation.** You may need to revoke sessions/tokens, update `kid`/JWKS, coordinate transition windows, and protect legacy keys. Do not assume key rotation is merely "swapping a variable" with no user impact.

### 8.3. Keeping sensitive data out of logs

Specifically audit:

```text
Authorization
Cookie / Set-Cookie / JSESSIONID
access_token / refresh_token / id_token
password / client_secret / api_key
Authorization Code, OTP, reset-password token
JWT signing key, database password
CSRF token
```

Log request IDs, route templates, minimized user IDs, and standardized error codes, **never raw headers/bodies**. Spring Security DEBUG/TRACE can aid debugging in staging but should not be left enabled casually in production; set logger levels appropriately and enforce redaction policies.

## 9. Pre-release CI/CD checks

### 9.1. Static scans can be automated — but never replace review

Use a script to search for demo **markers** in resources/config. The example below scans only paths tracked in Git; it prints **file names**, not lines containing passwords:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Run at the repository root containing src/main/resources.
# Checks only a set of patterns in resource text;
# separate secret scanners/SAST must inspect Java, IaC, history, and artifacts.
if git grep -I -l -E \
  'spring\.security\.user\.(name|password)|\{noop\}|app\.demo\.enabled[=: ]+true' \
  -- src/main/resources; then
  echo "BLOCKED: demo credential/config marker in main resources" >&2
  exit 1
fi

echo "No simple demo markers found in main resources"
```

**Limitations:** the script matches only specific patterns (and may produce false positives), does not understand multi-line YAML, does not scan Java/Helm/DB, and does not catch every password/key. Run **secrets scanning**, SAST, dependency/IaC scans, and code review in separate steps. Define explicit allowlists for `src/test/**` fixtures, without letting allowlists mask a copy step into release artifacts.

Secret scanners like Gitleaks/TruffleHog can be used per organizational standards. Run them on the **working tree, relevant commits, and history where needed** with maintained detection rules—not just `HEAD`. Do not disable CI when a scanner hits a false positive; create an exception with an owner, justification, and expiration date.

### 9.2. Scanning risky Java patterns

Patterns to *review* (not every occurrence is automatically a bug):

```text
InMemoryUserDetailsManager
User.withUsername(...)
withDefaultPasswordEncoder()
NoOpPasswordEncoder
{noop}
spring.security.user.name
spring.security.user.password
anyRequest().permitAll()
web.ignoring()
csrf.disable()
cors.configurationSource(...)
spring.h2.console.enabled
management.endpoints.web.exposure.include=*
/debug/**
/test-login
/issue-token
@Profile("dev")
System.out.println(...token...)
```

**Do not automatically conclude every `csrf.disable()` is wrong.** A stateless Bearer-header-only API with a clear threat model may legitimately use it. Conversely, global `csrf.disable()` for cookie-based web sessions can be a severe vulnerability. `permitAll()` on `/login` or public health may be valid; `anyRequest().permitAll()` in a production chain usually warrants blocking.

CI policies should include *context*: which files are production, which routes are allowed to be public, which security exceptions are reviewed, and which secrets are scoped to tests. Automated tests verifying the route inventory and permissions are highly valuable.

### 9.3. Inspecting binary artifacts, not just the repository

A release build may accidentally carry:

- `application-dev.yml`, `application-local.properties`, `data.sql`, H2 databases, or test data due to misconfigured copy tasks.
- `DemoAuthenticationProvider`, `DevSecurityConfig`, or `/debug/**` endpoints still inside the JAR despite `@Profile("dev")`.
- PEM/private key files, JSON credentials, cert bundles containing private keys, or seed credentials.
- Docker image layers that once contained secrets, even if a later command ran `rm`.
- Java agents/debug ports or Docker entrypoints enabling debug mode.

**`@Profile("dev")` only controls whether a bean is loaded into the Spring context; it does not remove the class or resource from the JAR.** If a production artifact can have that profile activated via deployment config, the risk remains. Exclude demo code/fixtures from production builds or enforce verifiable packaging policies; never rely on profile names alone.

A sensible QA pipeline:

```text
git commit
   -> secret scan + SAST + dependency / IaC scan
   -> compile + unit/integration security tests
   -> package release JAR
   -> inspect packaged resources/classes
   -> build container image (no secret build args)
   -> image/SBOM/vulnerability scan
   -> deploy to staging with prod-like config
   -> smoke tests auth, permission, health, debug denial
   -> approval / progressive rollout / monitoring
```

### 9.4. Do not trust insufficient "proof"

- **`git grep` finds no `admin123`:** seeded accounts may still exist in the database or IdP.
- **`/api/private` returns 401:** a `/debug/admin` route might still allow unauthenticated access.
- **No generated password in startup logs:** WARN logging might be suppressed, or the app might use a different misconfigured user store.
- **`@WithMockUser` tests pass:** does not prove real passwords/JWTs are validated.
- **YAML deleted from Git:** an earlier release image/JAR still contains the secret.
- **`@Profile("dev")` is inactive locally:** does not prove it cannot be activated in production.
- **JWT signature verifies:** does not prove issuer, audience, scopes, and object-level permissions are enforced.

## 10. Post-deploy runtime smoke tests

After deploying the final artifact to staging/pre-production, test along a **production-like HTTP path**: TLS, ingress, DNS, proxies, cookies, and the corresponding auth provider.

| Action | Expectation in Bearer-only API | Evidence |
| --- | --- | --- |
| Anonymous `GET /api/items` | 401, appropriate Bearer challenge | Response status/header, request ID |
| Valid token with `items.read` | 200 | No out-of-scope data leaked |
| Valid token missing `items.read` | 403 | Scope rule enforced |
| JWT with bad signature/`iss`/`aud`/expired | 401 | Decoder rejects |
| Session cookie or Basic credentials alone | No API access granted | No fallback account |
| `POST /api/items` with READ scope | 403 | READ permission cannot perform WRITE |
| `GET /actuator/health` | Follows approved health check policy | No details/secrets leaked |
| `/h2-console`/`/debug/**` | No access to debug features | No public debug endpoints |
| Demo property enabled in staging startup | App refuses to start or deployment gate blocks | Message shows **property name**, no value leaked |
| Missing issuer/audience config | No permissive login fallback | Fail closed / readiness fails |
| New deployed image carries no fixtures | No demo files/users/keys | Artifact scan + runtime checks |

Smoke tests must verify **body/data side effects**, not just status codes. On unauthorized updates/deletes, the DB must remain unchanged. On exports, files must contain no cross-tenant data. Store redacted evidence in the release ticket.

### Curl examples carrying no real secrets

```bash
# No Authorization -> typically 401 Bearer.
curl -i https://api.example.org/api/items

# Token issued by the official IdP; never record real tokens in tickets.
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.org/api/items

# Debug endpoint must not return debug features or test credentials.
curl -i https://api.example.org/debug/login
```

These URLs are **examples**, not live service addresses. Avoid using `curl -v` with real credentials because verbose output can print the `Authorization` header. Run tests in authorized environments and mask tokens in logs.

## 11. Migration plan without disrupting the system

### Phase 1 — Inventory and dependency mapping

Find demo users, security filters, dev endpoints, secrets, and IdP accounts. Identify who **actually depends** on those credentials (automation, batch jobs, support tools). Never rush to delete them only to discover a production integration was using a demo user.

### Phase 2 — Provision real identities

- Provision official user/service principals via the IdP or managed store.
- Assign minimal scopes/roles; review owner/tenant policies.
- Migrate clients to the proper flow, such as OAuth2 client credentials for machine-to-machine instead of a shared admin password.
- Rotate deployment secrets so no exposed keys/passwords remain in use.

### Phase 3 — Prevent new occurrences

- Code review rules blocking new `InMemoryUserDetailsManager`/`{noop}` in `src/main`.
- Static/secrets scans on branches and IaC.
- CI checks for permission boundaries, JWT validation, and no public debug endpoints.
- Fail-closed guards for project-specific demo toggles.
- Record exceptions with owner, reason, and expiration if a lab environment legitimately needs a fixture.

### Phase 4 — Remove/disable old paths

- Delete demo accounts from the app user store and IdP.
- Revoke tokens, refresh tokens, client secrets, and keys if ever used or potentially exposed.
- Remove seed scripts and endpoints; verify old accounts **cannot log in** over real HTTP paths.
- If immediate disabling is impossible due to a dependency, establish a timeline and compensating controls under an approved risk decision; never silently leave old accounts active.

### Phase 5 — Release gate and monitoring

- Test staging with the final artifact and inspect platform-merged configuration.
- Verify the active `SecurityFilterChain`, auth providers, endpoint mappings, and scope permissions.
- Roll out progressively; monitor 401/403 errors, login counts, and hits to old demo endpoints.
- Track rotation schedules and close temporary exceptions.
- Confirm a safe rollback **never restores revoked secrets or demo accounts**.

## 12. Risks of relying on Spring Profiles

Spring Profiles separate per-environment configuration, **not security boundaries**:

```java
@Configuration
@Profile("dev")
class LocalOnlyUsers {

    @Bean
    UserDetailsService users() {
        // Demo user if this class is present in the JAR.
        return new InMemoryUserDetailsManager();
    }
}
```

This snippet is a **warning example**, not part of the baseline. Even when the bean is not created outside the `dev` profile, its bytecode still lives in the JAR, and mistakenly activating `dev` during deployment brings it back. Moreover, another `SecurityFilterChain` could override rules depending on `@Order` and matchers.

Safer alternatives:

- Keep test data and mock authentication in `src/test`.
- Keep local fake IdPs or dev-only modules **separated from the production artifact**.
- Production baselines reject demo toggles and provide no "fallback to demo" when config is missing.
- Release pipelines verify active profiles, property sources, and artifact contents.
- Deploy scripts never auto-enable `dev`/`local` when env vars are missing; use explicit validated configuration.

If an organization **must** keep a dev-only class in the artifact, enforce a threat review, independent activation guard, scanners, artifact checks, deploy permissions, and monitoring; `@Profile("dev")` alone is insufficient.

## 13. Web session configurations need different checks from Bearer APIs

The sample in section 6 **has no web session**. If a real project uses browser logins, separate checks are required:

- Users log in via IdP/OIDC or a managed store, not `admin/admin`.
- `formLogin`/`oauth2Login` and success/failure/logout handlers point to the right URLs.
- Session cookies have `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`, and appropriate timeouts.
- `CsrfFilter` protects state-changing HTTP methods. If an SPA uses cookies, ensure CSRF tokens are issued and refreshed after login/logout.
- Logout clears session, security context, remember-me, and CSRF; for SSO, distinguish local logout from IdP logout.
- Never apply `SessionCreationPolicy.STATELESS` across an entire web app while expecting login state to persist.
- Do not open `/login` with `web.ignoring()` when `permitAll()` is appropriate; preserve security headers and filter behavior.
- Write integration tests for valid/invalid POST login, session persistence, CSRF, logout, disabled users, redirects, and roles.

**Moving from a Basic/in-memory demo to OIDC is not just adding a dependency.** You must configure redirect URIs, cookies during cross-site flows, issuer/client ID, client secrets in a secret manager, scope mapping, logout, and real browser/proxy tests.

## 14. Reviewing each commonly missed sample configuration

### 14.1. Overly broad `permitAll`

Wrong:

```java
.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll()
)
```

Safer with an explicit route list:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/actuator/health").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/items")
        .hasAuthority("SCOPE_items.read")
    .anyRequest().denyAll()
)
```

**Not every `permitAll` is wrong**; login pages, public assets, and health checks may need it. However, list the exact purpose and verify another filter chain does not accidentally match or redirect unexpectedly.

### 14.2. `web.ignoring` and multiple SecurityFilterChains

`web.ignoring()` bypasses Spring Security filters for that path. For many public URLs, `permitAll()` inside the right chain preserves security headers. With multiple `SecurityFilterChain` beans, verify the first chain's `securityMatcher` and `@Order`; a "correct" rule in an unmatched chain has no effect.

### 14.3. CSRF/CORS copied from demos

- Never disable CSRF system-wide just because a Postman demo did not send a token. With cookie sessions, this creates CSRF risk.
- Never use CORS wildcards with credentialed requests.
- Bearer APIs are not automatically CSRF-safe if tokens live in cookies auto-sent by browsers.
- CORS is neither authentication nor data authorization; server-to-server clients are not restricted like browser JavaScript.

### 14.4. Debug endpoints and actuator

Never leave `/h2-console`, `/debug/**`, `/dev/**`, `/test-login`, or `/mint-token` open in production. Actuator health/metrics/env/heapdump/loggers have varying sensitivity; control both exposure and authorization/networking. Never configure `management.endpoints.web.exposure.include=*` on an internet-facing service without an approved security design.

### 14.5. HTTP Basic, form login, and password storage

Do not keep a fixed HTTP Basic account as an "emergency fallback" without a tightly controlled break-glass policy (MFA where feasible, secret management, approval, and auditing). Shared break-glass accounts require their own threat review and **must never originate from a demo user**.

### 14.6. Sample JWT signing keys

A `jwt.secret=secret123` string or sample RSA private key in resources is a serious credential, not mere configuration. Production requires an official issuer/AS, JWT validation, and rotation. Pay attention to Spring Security version differences in JWT decoder builders; advisories have noted cases where **issuer validation was not automatic with certain builders/versions**. Use appropriate auto-configuration/validators, test wrong-issuer cases, and stay patched.

### 14.7. Fake PasswordEncoder

`NoOpPasswordEncoder`, `{noop}`, and `withDefaultPasswordEncoder()` do not belong in production paths. However, do not delete test fixtures in a way that leaves unit tests unable to verify login flows; keep them **strictly in test scope** and ensure they cannot reach real artifacts or environments.

## 15. Release reviewer sign-off template

| Item | Expected evidence | Owner |
| --- | --- | --- |
| Demo users | Absent from runtime app, DB/IdP, secret store | Backend + Identity |
| Seed passwords/keys | Removed from artifacts; rotated/revoked if ever used | Security/Platform |
| Auth mechanism | Only approved chains/providers active | Backend |
| URL authorization | Every route has rules/matchers; fallback deny | Backend |
| CSRF/CORS | Matches client type; browser-tested if needed | Backend + Frontend |
| Data scope | Tenant/owner/action-level tests | Backend/QA |
| Security configs | No dangerous demo/H2/debug/TRACE flags | Platform + Backend |
| Secrets | Secret manager/ACLs/rotation/auditing | Platform/SRE |
| Tests | CI + staging negative and positive smoke tests | QA/Backend |
| Artifact | JAR/image/IaC scanned; no fixtures packaged | DevOps |
| IdP | Official issuer/audience/scopes/client credentials | Identity |
| Incident readiness | Rotate/revoke/rollback plan | Security + Operations |

When signing off, do not simply write "Done". Record links to CI results, artifact digests, deploy manifest versions, test runs, and rotation dates (without attaching passwords or tokens).

## 16. Final pre-go-live checklist

- [ ] No usable demo accounts remain in the app, database, IdP, or integrated systems.
- [ ] No `spring.security.user.name/password` or demo `InMemoryUserDetailsManager` in production paths.
- [ ] No `{noop}`/`NoOpPasswordEncoder`/`withDefaultPasswordEncoder()` used for real passwords.
- [ ] No hardcoded or packaged JWT signing keys, client secrets, DB passwords, or tokens.
- [ ] Every credential ever exposed in Git/CI/docs has been evaluated and rotated/revoked.
- [ ] Production identity mechanism has owners, provisioning/offboarding, MFA where needed, and least privilege.
- [ ] JWT Resource Server validates issuer/audience/expiry/signature/scopes; never accepts ID tokens as access tokens.
- [ ] No unapproved `anyRequest().permitAll()`, `web.ignoring()`, or debug bypasses.
- [ ] Web/BFF session CSRF is not disabled while auto-sent credentials are used.
- [ ] H2 console, test endpoints, and sensitive actuators are not exposed to unauthorized clients.
- [ ] Logs never print passwords, `Authorization`, `Cookie`, CSRF tokens, or private keys.
- [ ] CI scans source, history, secrets, IaC, dependencies, and final artifacts.
- [ ] Staging tests login/auth/permissions with production-like issuer and gateway.
- [ ] Unknown routes and missing credentials are denied; no login fallback exists.
- [ ] Production artifacts contain no test data or reactivatable demo configs.
- [ ] Runtime config is validated; missing/invalid values never open access.
- [ ] Runbook exists for secret exposure; rollback never restores revoked secrets or demo paths.
- [ ] Reviewer verified actual evidence rather than trusting checklist checkboxes alone.

### Self-check questions

1. Why does merely deleting `password=admin` from `application.yml` not guarantee the demo account is gone?
2. When might Spring Boot create `user` with a generated password, and why is it not a production identity?
3. Does a custom `SecurityFilterChain` always remove the default `UserDetailsService`?
4. Why is `{noop}` dangerous for real passwords, and which `PasswordEncoder` is better?
5. Why is `@Profile("dev")` not proof that a dev account is absent from the production JAR?
6. If a secret was committed to Git and later deleted in a new commit, what is the mandatory next step?
7. For what kind of API can `csrf.disable()` be justified, and for which apps is it unjustified?
8. Why does `with(jwt())` not prove that JWT issuer, audience, and signature are verified?
9. Why does secret injection via env still require protecting process inspection and logs?
10. Does making actuator health public mean all actuator endpoints can be public?
11. Why does testing that `/api/private` returns 401 not prove the entire system has no backdoors?
12. What must a deploy script do when an issuer or DB secret is missing instead of enabling a demo fallback?

**Hints:** (1) Java user store, DB seeds/IdP/images may still exist; (2) development fallback user lacks production lifecycle; (3) not necessarily, depends on auto-configuration/dependencies; (4) no hashing—use an encoder with salt/work factor and proper lifecycle; (5) profiles only control bean loading; (6) revoke/rotate and trace where the secret was copied; (7) header-only Bearer vs. cookie session; (8) mock principal bypasses decoder; (9) env still has exposure surfaces; (10) no, independent exposure/auth required; (11) other bypass routes may exist; (12) fail closed, alert, never use a default password.

## References

- Spring Boot — Spring Security auto-configuration and default user: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- Spring Boot — Profiles and profile-specific configuration: https://docs.spring.io/spring-boot/reference/features/profiles.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Actuator endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Security — Authorization for Servlet Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- OWASP — Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP — Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP — CI/CD Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html
