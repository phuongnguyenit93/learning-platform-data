# Externalizing Environment Configuration to Properties and Type-Safe Configuration in Spring Security WebFlux

## Learning Objectives

After this lesson, you will be able to:

- Separate **security rules**, **environment-varying configuration**, and **secrets** into layers with clear responsibilities.
- Use `application.yml`, `application-dev.yml`, `application-prod.yml`, and environment variables to configure Spring Boot without editing Java code on every deployment.
- Bind security settings groups into a Java `record` with `@ConfigurationProperties`, validating values with `@Validated` and Jakarta Bean Validation to **fail fast** when values are missing or invalid.
- Use the validated data to configure `SecurityWebFilterChain`, HTTP Basic, HTTPS, CORS, and publicly permitted routes in Spring WebFlux.
- Keep protective defaults, manage password hashes via external secret sources, verify 200/401/403 with tests, and recognize dangerous misconfigurations.

> Scope: Spring Boot 3.x, Java 17+, **reactive Spring Security with WebFlux**. The security APIs in this lesson are `ServerHttpSecurity` and `SecurityWebFilterChain`; `HttpSecurity` and `SecurityFilterChain` belong to the separate Servlet/MVC stack.

## 1. Why externalize security configuration?

An application may run in local dev, test, staging, and production. Environments differ in domains, frontend origins, HTTPS ports, secret storage, and whether experimental documentation endpoints are accessible. Hardcoding these values in code forces recompiling the same application version or risks accidentally running dev settings in production.

Distinguish the following:

| Category | Example | Appropriate source |
| --- | --- | --- |
| **Core policy** | `/admin/**` always requires the ADMIN role; remaining routes require login | Code/configuration reviewed and tested as security policy |
| **Environment parameters** | Allowed CORS domains, enabling HTTPS redirect, exposing demo doc endpoints | `application-{profile}.yml`, deployment configuration |
| **Secrets** | Passwords, password hashes, private keys, OAuth client secrets, signing keys | Secret manager, config tree, or protected environment |
| **Per-user permissions** | Who is allowed to view a specific report | Identity provider/DB/service authorization, not bulk-listed in YAML |

Password hashes are not plaintext, yet they still need protection: leaked hashes enable offline password-guessing attacks. Never commit real secret values to Git, and never print configuration objects containing hashes to logs.

### Typed configuration and "secure" are two related goals

**Type safety** catches errors such as assigning the string `maybe` to a boolean or omitting a username. **Security safety** avoids defaulting to `permitAll()` when a value is absent. Both are necessary: a properly typed boolean such as `allow-all=true` can still be an extremely dangerous security decision.

Pattern to avoid:

```java
// Anti-pattern illustration; do not use in a real application:
String env = System.getenv("APP_ENV");
if ("dev".equals(env)) {
    http.authorizeExchange(a -> a.anyExchange().permitAll());
}
```

If production is mistakenly set to `APP_ENV=dev`, every endpoint becomes open. A better approach is to configure **exactly which routes** are public, with a final rule protecting all remaining requests.

## 2. Profiles and Spring Boot configuration source precedence

Spring Boot supports configuration sources from YAML/properties files, profile-specific files, environment variables, system properties, command-line arguments, and external locations outside the JAR. Higher-precedence sources can override earlier ones; profile-specific files in the same group normally override the base file.

Example directory:

```text
src/main/resources/
    application.yml
    application-dev.yml
    application-prod.yml
```

- `application.yml` holds shared values and defensive defaults.
- `application-dev.yml` overrides only what is needed locally, such as origin `http://localhost:5173` and disabling HTTP-to-HTTPS redirect on localhost.
- `application-prod.yml` specifies HTTPS and the production frontend origin; it contains no real passwords or keys.
- `SPRING_PROFILES_ACTIVE=dev` or `--spring.profiles.active=dev` activates the dev profile. Never deploy to production with the dev profile.
- Environment variables or launch arguments can override files. Always verify **effective values** in the deployed environment rather than assuming having `application-prod.yml` guarantees safety.

Spring Boot uses *relaxed binding*: YAML key `app.security.require-https` binds to Java `requireHttps`. When overriding the property directly via environment variable under Boot's rules, the name is `APP_SECURITY_REQUIREHTTPS`: replace dots with underscores, drop hyphens, and uppercase. Variable names used inside placeholders like `APP_ADMIN_PASSWORD_HASH` below are **chosen by you** and do not have to match relaxed-binding rules because they are resolved via placeholder.

### Watch out for lists

In multi-profile configuration, a `List` is normally **replaced** by the list from the higher-precedence source rather than merged element by element. For example, a dev localhost list will not automatically keep production origins; this behavior helps prevent accidentally widening CORS scope. Verify real origins upon deployment.

## 3. Designing typed security settings with a record

The complete example uses Java 17+, Spring Boot 3.x, Spring WebFlux, and Spring Security. The validation starter is included so constraint annotations are actually enforced.

**`build.gradle`** — dependencies in a Gradle project that already has the Spring Boot plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Do not add `spring-boot-starter-web` to a WebFlux demo because when both MVC and WebFlux are present, Spring Boot normally selects a Servlet application unless the app type is forced.

**`src/main/java/example/secureconfig/SecuritySettings.java`**:

```java
package example.secureconfig;

import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.security")
public record SecuritySettings(
        @NotNull Boolean requireHttps,
        @NotNull Boolean publicDocs,
        @NotBlank String adminUsername,
        @NotBlank
        @Pattern(
            regexp = "\\{bcrypt\\}.+",
            message = "must use an encoded {bcrypt} password"
        )
        String adminPasswordHash,
        @NotNull List<@NotBlank String> corsAllowedOrigins
) {}
```

Specific meaning:

1. `@ConfigurationProperties` binds keys under `app.security.*` into one object, avoiding scattering `@Value` magic key strings across security config.
2. `record` fits configuration bound via constructor without setters. For a record with a single constructor, Spring Boot 3.x does not require `@ConstructorBinding`. The values reflect the **configuration at bean creation time**, and do not auto-reload if you later edit an environment variable.
3. Wrapper `Boolean` combined with `@NotNull` catches a missing required key; using primitive `boolean` can silently turn a missing value into `false`.
4. `@NotBlank` and `@Pattern` reject empty hashes or plaintext missing the `{bcrypt}` prefix. The regex only checks **shape**; it does not prove the full hash is verifiable or that the password is strong enough.
5. `@NotNull List<@NotBlank String>` requires a list to be present; an empty list `[]` is valid to **allow zero cross-site origins**. Elements inside the list must not be blank.
6. `@Validated` uses Bean Validation (via the validation starter). When data is invalid, the app fails at startup instead of silently picking a risky configuration.

Do not turn a properties record into a `@Component` bean expecting constructor binding to behave like `@ConfigurationProperties`. This lesson registers it properly via `@EnableConfigurationProperties` on the `SecurityConfiguration` class.

### Why shouldn't every field have a default?

Two flags have safe defaults in `application.yml`. By contrast, username and hash have no defaults because *a missing secret is a deployment error*. Never write `${APP_ADMIN_PASSWORD_HASH:password}` or `{noop}123456` just to "make the app start". If the environment does not supply valid credentials, startup must fail.

## 4. Declaring environment-specific configuration files

**`src/main/resources/application.yml`**:

```yaml
spring:
  application:
    name: reactive-secure-config

app:
  security:
    require-https: true
    public-docs: false
    admin-username: ${APP_ADMIN_USERNAME}
    admin-password-hash: ${APP_ADMIN_PASSWORD_HASH}
    cors-allowed-origins: []
```

Explanation:

- `require-https: true`: HTTPS redirection enabled by default.
- `public-docs: false`: demo docs are not public by default.
- `admin-username` and `admin-password-hash` must come from the runtime environment or a secret source supplying those exact keys.
- `cors-allowed-origins: []`: do not open CORS carelessly.

**`src/main/resources/application-dev.yml`**:

```yaml
app:
  security:
    require-https: false
    public-docs: true
    cors-allowed-origins:
      - "http://localhost:5173"
```

**`src/main/resources/application-prod.yml`**:

```yaml
app:
  security:
    require-https: true
    public-docs: false
    cors-allowed-origins:
      - "https://console.example.com"
```

`https://console.example.com` is an **illustrative** hostname: replace it with the exact approved origin of your real frontend. The intentional differences between dev and prod are docs accessibility, the CORS allowlist, and TLS redirect—not the entire authentication/authorization policy.

Note that a dev file packaged inside a JAR artifact can still be activated if an operator sets the wrong profile. Deployment controls and tests must prevent the dev profile from running in production; profiles are a configuration mechanism, not an impenetrable security boundary.

## 5. Applying settings in Spring Security WebFlux

The code below wires together record registration, user source, password encoder, CORS, and `SecurityWebFilterChain`. HTTP Basic is used solely to demonstrate wiring the configuration; real systems may choose OIDC/OAuth2 resource server depending on the authentication model.

**`src/main/java/example/secureconfig/SecureConfigApplication.java`**:

```java
package example.secureconfig;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecureConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecureConfigApplication.class, args);
    }
}
```

**`src/main/java/example/secureconfig/ReactiveSecurityConfiguration.java`**:

```java
package example.secureconfig;

import java.util.List;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableConfigurationProperties(SecuritySettings.class)
class ReactiveSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(SecuritySettings settings) {
        UserDetails admin = User.withUsername(settings.adminUsername())
                .password(settings.adminPasswordHash())
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users, PasswordEncoder encoder) {
        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource(SecuritySettings settings) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(settings.corsAllowedOrigins());
        cors.setAllowedMethods(List.of("GET", "HEAD", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(false);

        var source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            SecuritySettings settings,
            ReactiveAuthenticationManager authManager,
            CorsConfigurationSource corsSource) {

        http
            .authorizeExchange(exchanges -> {
                exchanges.pathMatchers(HttpMethod.GET, "/public/ping")
                        .permitAll();

                if (settings.publicDocs()) {
                    exchanges.pathMatchers(HttpMethod.GET, "/docs/info")
                            .permitAll();
                } else {
                    exchanges.pathMatchers("/docs/**")
                            .denyAll();
                }

                exchanges.pathMatchers("/admin/**")
                        .hasRole("ADMIN");
                exchanges.anyExchange().authenticated();
            })
            .httpBasic(basic -> basic.authenticationManager(authManager))
            .formLogin(form -> form.disable())
            .cors(cors -> cors.configurationSource(corsSource));

        if (settings.requireHttps()) {
            http.redirectToHttps(Customizer.withDefaults());
        }

        return http.build();
    }
}
```

**`src/main/java/example/secureconfig/DemoController.java`**:

```java
package example.secureconfig;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class DemoController {
    @GetMapping("/public/ping")
    Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/docs/info")
    Mono<String> docs() {
        return Mono.just("demo docs");
    }

    @GetMapping("/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "hello " + ctx.getAuthentication().getName());
    }

    @GetMapping("/admin/report")
    Mono<String> report() {
        return Mono.just("admin report");
    }
}
```

### Why does this code enforce type-safe configuration?

- `@EnableConfigurationProperties(SecuritySettings.class)` lets Spring Boot create the bean via the Binder and validate it; every other bean receives a **strongly typed configuration object**.
- The credential in `MapReactiveUserDetailsService` is an illustrative user with a **password hash** from a secret source. `UserDetailsRepositoryReactiveAuthenticationManager` takes `PasswordEncoder` and is explicitly wired into HTTP Basic to verify passwords.
- `pathMatchers(GET, "/public/ping").permitAll()` opens exactly one route publicly. `/docs/info` is open to anonymous users only when `publicDocs=true`; when false, `/docs/**` hits `denyAll()`. `/admin/**` always requires the ADMIN role and all remaining requests require authentication.
- `roles("ADMIN")` generates the `ROLE_ADMIN` authority. `hasRole("ADMIN")` automatically prepends `ROLE_`, so do not write `hasRole("ROLE_ADMIN")`.
- CORS is configured via a **reactive** `CorsConfigurationSource`. It handles browser origins/preflights; it does not replace authentication, authorization, or CSRF.
- `formLogin` is disabled because this demo has no form login UI/cookie session; `httpBasic` is enabled explicitly. The example does not disable default CSRF (the controller only has `GET` endpoints). For POST/PUT/DELETE or cookie-using browsers, evaluate CSRF against the actual threat model.
- `redirectToHttps` is enabled only according to the bound flag. Sending HTTP Basic over an unencrypted public connection leaks passwords; production setups need real TLS from client to a trusted termination point.
- The controller uses `ReactiveSecurityContextHolder` to read the identity from the Reactor Context, avoiding Servlet-style ThreadLocal APIs.

**Be careful about permissions:** `permitAll()` on a public route does not mean security filters, CORS, or other defenses are skipped. `anyExchange().authenticated()` is also insufficient to protect resources per owner; services/repositories still need object-level authorization for sensitive data.

## 6. Secrets and password hashes must be provisioned outside source code

The two placeholders in the base file accept:

- `APP_ADMIN_USERNAME`: the demo account name.
- `APP_ADMIN_PASSWORD_HASH`: a BCrypt hash with the `{bcrypt}` prefix understood by `DelegatingPasswordEncoder`, e.g., structure `{bcrypt}$2a$...` (the ellipsis is not a valid hash).

**Never** store a real password hash in public repositories or documentation. Use a secret manager, config tree, or access-controlled process environment. Never use `{noop}` to store production passwords.

To generate a hash in an internal Java utility with Spring Security on the classpath, the core operation is:

```java
String encoded = "{bcrypt}" +
        new BCryptPasswordEncoder().encode(passwordFromProtectedInput);
```

This is **illustrative code**, assuming `passwordFromProtectedInput` comes from a protected input mechanism and `BCryptPasswordEncoder` is imported. This snippet is not standalone, has no `main()`, and should never print raw passwords. Provisioning must follow your organization's secret management rules.

In container environments, Spring Boot also supports importing configuration from secret mounts:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Mount exact file/key names, protect read permissions, and manage rotation. `optional:configtree:...` allows missing paths, which is inappropriate if a missing required secret must halt deployment. Environment variables can also leak via process inspection tools, debug logs, or crash dumps; they should not automatically be treated as a secret manager.

**Do not log the `SecuritySettings` object.** Default `record.toString()` prints every component, including `adminPasswordHash`. Actuator's `/env` and `/configprops` must also be secured, properly sanitized, and never exposed publicly.

## 7. Running with profiles and testing endpoints

In a project with a Gradle Wrapper, after provisioning the username/password hash into the launching process, run with the `dev` profile:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

In production, select `prod` from your deployment manifest/environment—never use `dev` to work around certificate or redirect issues. When running the built JAR:

```bash
java -jar build/libs/your-app.jar --spring.profiles.active=prod
```

`your-app.jar` is an illustrative filename; replace it with Gradle's actual output name. Ensure environment variables exist in the **Java process**, not just in a different terminal tab.

Test from a separate terminal:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/docs/info
curl -i http://localhost:8080/admin/report
curl -i -u ADMIN_USER http://localhost:8080/me
curl -i -u ADMIN_USER http://localhost:8080/admin/report
```

Replace `ADMIN_USER` with the provisioned demo account. With `curl -u username` without a password, curl can prompt for the password interactively. Avoid passing passwords directly on the command line where they may be recorded in shell history or process lists.

| Request when running dev | Expected result | Explanation |
| --- | --- | --- |
| `GET /public/ping` anonymous | 200, body `pong` | Explicit `permitAll` |
| `GET /docs/info` anonymous | 200, body `demo docs` | Dev sets `public-docs=true` |
| `GET /admin/report` anonymous | 401, Basic challenge | Missing authentication |
| `GET /me` with valid credentials | 200, `hello <username>` | Principal read from reactive security context |
| `GET /admin/report` with valid admin | 200, body `admin report` | Has `ROLE_ADMIN` |

In the `prod` profile, once the request arrives over valid HTTPS, `/docs/info` is denied. For authenticated callers, denial usually yields **403**; anonymous callers may receive **401** when the security entry point challenges for login. Therefore, do not assume every denial returns 403 for all clients.

### HTTPS and reverse proxies

If TLS terminates at a reverse proxy/load balancer and the proxy forwards HTTP to WebFlux, the framework may need trusted forwarded-header configuration to know the original client used HTTPS. Misconfiguration can cause redirect loops or wrong URLs. Inspect `server.forward-headers-strategy` per infrastructure, set a clear trust boundary, and ensure the proxy strips external spoofed `Forwarded`/`X-Forwarded-*` headers. Never turn off HTTPS just to hide infrastructure problems.

### CORS is not authentication

The CORS allowed-origins list is a policy for **browsers**. It does not mean a backend client or `curl` from another origin is automatically blocked from connecting. A cross-origin request carrying an `Authorization` header typically triggers a preflight; test preflight with the exact method, headers, and origin on the frontend. When using cross-origin cookies/sessions, configure credentials, SameSite, and CSRF consistently instead of opening wildcards indiscriminately.

## 8. Automated testing with WebTestClient

The test below supplies a BCrypt hash for the account **only within the test**, without needing production secrets. It forces HTTPS redirect off for local HTTP testing and sets docs to false to verify fail-closed behavior.

**`src/test/java/example/secureconfig/SecurityHttpTest.java`**:

```java
package example.secureconfig;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "app.security.require-https=false",
        "app.security.public-docs=false"
    }
)
@AutoConfigureWebTestClient
class SecurityHttpTest {

    @Autowired WebTestClient client;

    @DynamicPropertySource
    static void credentials(DynamicPropertyRegistry registry) {
        registry.add("app.security.admin-username", () -> "admin");
        registry.add(
            "app.security.admin-password-hash",
            () -> "{bcrypt}" + new BCryptPasswordEncoder(4)
                    .encode("test-only-password")
        );
    }

    @Test
    void publicRouteWorksWithoutLogin() {
        client.get().uri("/public/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousCannotAccessAdmin() {
        client.get().uri("/admin/report").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void adminCanAccessAdminReport() {
        client.get().uri("/admin/report")
                .headers(h -> h.setBasicAuth("admin", "test-only-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin report");
    }

    @Test
    void authenticatedAdminStillCannotReadDisabledDocs() {
        client.get().uri("/docs/info")
                .headers(h -> h.setBasicAuth("admin", "test-only-password"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Command:

```bash
./gradlew test --tests example.secureconfig.SecurityHttpTest
```

In PowerShell: `.\gradlew.bat test --tests example.secureconfig.SecurityHttpTest`. With the right code and environment, all four cases are expected to PASS. This is an **HTTP security test**; it does not yet prove TLS/proxy deployment is right, CORS is error-free, or production secrets are rotated properly. Add separate tests/checks for those conditions.

### Negative tests for typed configuration

The cases below should run in an isolated test context or startup validation check; never deliberately trigger failures in production:

| Test change | Expected outcome | Caught by |
| --- | --- | --- |
| Omit `APP_ADMIN_PASSWORD_HASH` and any equivalent override | App fails to start | Placeholder/binding/validation |
| `app.security.require-https=maybe` | App fails to start | Cannot convert to Boolean |
| `app.security.admin-username=""` | App fails to start | `@NotBlank` |
| `app.security.admin-password-hash=plaintext` | App fails to start | `@Pattern` |
| `app.security.cors-allowed-origins[0]=""` | Validation fails | `List<@NotBlank String>` |
| `app.security.public-docs=false` | Authenticated admin is denied on `/docs/info` | `denyAll` rule |
| `app.security.require-https=true`, valid HTTP request | Redirects to HTTPS | HTTPS redirect in chain |

Type-safe values only confirm the configuration has a valid shape. They do not guarantee origins are trustworthy or roles are assigned rightly; separate policy reviews and tests are required. Never enable debug logs that expose hashes/tokens just to inspect binding.

## 9. Common mistakes and how to fix them

| Mistake | Harm | How to fix |
| --- | --- | --- |
| Scattered `@Value` fields, string-comparing security flags | Hard to inventory and verify consistency | Group with `@ConfigurationProperties` |
| Primitive `boolean` without a reviewed default | Missing value silently becomes `false` | `Boolean @NotNull` or tested safe default |
| Using `security.enabled=false` / `allow-all=true` | Risk of opening all routes if toggled by mistake | Exact rules, `anyExchange().authenticated()` |
| Committing passwords, real hashes, or secrets in YAML | Exposed via Git history/artifacts | Keep placeholders only and provision from secret store |
| Having fallback `${PASSWORD:password}` | Missing secret leaves app running weakly | Remove weak fallback, fail fast |
| Activating `dev` profile in production | Can disable TLS and expose docs | Enforce profile controls in CI/CD and deployment |
| Using `@Component` on a constructor-bound record | Binder may not instantiate the right bean style | `@EnableConfigurationProperties` |
| Missing validation provider | Constraints are not guaranteed to be enforced | Add validation starter, test startup failure |
| Assuming profile list configs merge automatically | Origins may differ from expectations | Verify list replacement and effective allowlist |
| Using CORS in place of authorization | Non-browser clients can still call APIs | Check authentication/authorization independently |
| Disabling CSRF when app uses cookies/sessions | Increases cross-site request forgery risk | Base CSRF decisions on client/credential types |
| Trusting `X-Forwarded-Proto` unconditionally | Scheme spoofing, wrong redirects | Trust only managed proxies |
| Logging `SecuritySettings.toString()` | Can leak password hash | Mask/redact; never log secrets |
| Assuming editing env auto-updates running beans | Policy does not update as expected | Design verified reload/restart/rotation |

## 10. Practice exercises

1. Create a `staging` profile with a dedicated frontend origin, keeping HTTPS enabled and docs disabled. Verify the effective config and CORS preflight.
2. Try removing the password hash from the environment and running the app; compare the placeholder error against the validation error when a hash lacks its prefix.
3. Add a `security.audit-enabled` property (under `app.security`) to toggle non-sensitive audit logging using typed binding; explain why `Authorization` headers must never be logged.
4. Write two integration tests for `public-docs=true/false`; prove that only `/docs/info` changes status and `/admin/report` always requires the ADMIN role.
5. Place the app behind a TLS-terminating reverse proxy and test request scheme, redirects, and forwarded header trust. Ensure clients cannot spoof headers to bypass policy.
6. Replace the local user with a JWT or OIDC resource server: keep the idea of externalizing issuer/JWKS/audience and validated secrets, using only the authentication mechanisms supported by Spring Security.

**Conclusion:** Externalize environment-varying values, bind them into **typed and validated** configuration, keep secrets out of code, and maintain a WebFlux policy that protects every endpoint not explicitly made public. Combining fail-fast configuration, HTTP permission tests, and deployment verification produces a reliable security configuration.

## Official references

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot — Configuration Properties Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — WebFlux CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html)
- [Spring Security — Reactive HTTP/HTTPS](https://docs.spring.io/spring-security/reference/reactive/exploits/http.html)
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
