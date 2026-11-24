# Enabling Spring Security Diagnostic Logging by Environment (WebFlux / Reactive)

## 1. Objectives and Scope

In a Spring Boot application using **Spring WebFlux + Spring Security**, diagnostic logs help answer the following questions: whether a request passed through the security chain, where authentication failed, why access was denied, and which configuration is active. You need enough detail during development or incident investigation, while keeping log levels moderate in production to reduce cost, noise, and data exposure risk.

Expected outcomes after this lesson:

- Understand the difference between `INFO`, `DEBUG`, and `TRACE` levels and the scope of each logger.
- Configure log levels using `application.yml`, `application-dev.yml`, `application-staging.yml`, and `application-prod.yml`; activate the right Spring profile.
- Reproduce and read HTTP 200, 401, and 403 scenarios in the **reactive security chain**.
- Narrow down loggers when deep analysis is needed, temporarily change log levels via Actuator when permitted, and then restore safe levels.
- Recognize the impact on performance, sensitive data, and log correlation when a request switches threads in Reactor.

This is **diagnostic logging**, not a replacement for an audit trail, metrics, tracing, or security mechanisms. Enabling DEBUG does not grant permissions to a request, nor does it automatically return authentication error details to the client.

## 2. Where Do Logs Originate in a Reactive Application?

WebFlux processes requests through `WebFilter`; Spring Security applies `SecurityWebFilterChain`, typically configured with `ServerHttpSecurity`. Related components include `AuthenticationWebFilter`, `AuthorizationWebFilter`, `ExceptionTranslationWebFilter`, and the corresponding authentication/authorization managers. Depending on the login mechanism (HTTP Basic, OAuth2/JWT, OAuth2 Login...), the loggers and messages may differ.

**Distinction from Servlet:** `SecurityFilterChain`, `HttpSecurity`, `FilterChainProxy`, and `@EnableWebSecurity(debug = true)` are Servlet-specific examples/concepts. For this lesson, use `SecurityWebFilterChain`, `ServerHttpSecurity`, and loggers in the reactive branch, especially `org.springframework.security.web.server`. Do not expect Servlet-style log lines like “Invoking ...Filter (n/m)” to appear identically in WebFlux.

Spring Boot controls log levels via the `logging.level.<logger-name>` property. Loggers are hierarchical by package name: setting `org.springframework.security=DEBUG` affects child loggers unless they have a more specific configuration. `logging.level.root` is the baseline level for the entire application; you should not lower the entire root to TRACE just to find an authorization error.

| Level | Diagnostic Meaning | Usage |
| --- | --- | --- |
| `ERROR` / `WARN` | Serious issues, warnings; does not guarantee logging every security decision | Continuous monitoring |
| `INFO` | Informational events actually emitted by components | Practical default for many environments |
| `DEBUG` | Details for tracking execution flow and decisions | Dev, test, or time-bounded enabling during investigation |
| `TRACE` | More detailed than DEBUG, more messages | Enable only on narrow loggers, for short periods |
| `OFF` | Disables the selected logger | Use only when fully understanding the observability impact |

There is no guarantee that every request generates a specific message at every log level; this depends on the version, execution branch, and logging class.

## 3. Choosing the Right Logger for the Problem

| Logger/Package | When to Use | Notes |
| --- | --- | --- |
| `org.springframework.security` | Need a broad overview of authentication/authorization | Broad DEBUG/TRACE; may generate a lot of logs |
| `org.springframework.security.web.server` | Trace WebFlux security WebFilters | Correct reactive branch |
| `org.springframework.security.authentication` | Investigate authentication/credential verification logic | Do not expect identical logs across all authentication providers |
| `org.springframework.security.authorization` | Investigate grant/deny decisions | Cross-check against `authorizeExchange` rules |
| `org.springframework.security.oauth2.server.resource` | App acts as a Resource Server, validating Bearer/JWT | Only useful when actually using OAuth2 Resource Server |
| `org.springframework.web.server` | Need additional WebFlux request processing context | WebFlux log, not Spring Security-specific |
| `reactor.netty.http.server` | Diagnose HTTP/Netty layer when communication issues occur | Do not infer network logs as authorization decisions |

Start with `org.springframework.security=DEBUG` on dev. When there are too many logs, reduce it back to INFO and enable DEBUG/TRACE for **a smaller package**. For JWT-related errors, also check the decoder, issuer, audience, timestamps, and authorities configuration; loggers do not replace configuration inspection.

## 4. Environment-Specific Configuration with Spring Profiles

Assume the project already has Spring Boot 3.x, `spring-boot-starter-webflux`, and `spring-boot-starter-security`. Place the following files in `src/main/resources/`. The values below are **intentional examples** and should be adjusted according to your team's logging policy.

**`application.yml` — shared baseline level:**

```yaml
spring:
  application:
    name: reactive-security-demo

logging:
  level:
    root: INFO
    org.springframework.security: INFO
    org.springframework.web: INFO
```

**`application-dev.yml` — detailed diagnostics during development:**

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.server: TRACE
    org.springframework.web.server: DEBUG
```

**`application-staging.yml` — normally quieter than dev:**

```yaml
logging:
  level:
    org.springframework.security: INFO
    org.springframework.security.web.server: DEBUG
```

**`application-prod.yml` — conservative level:**

```yaml
logging:
  level:
    org.springframework.security: WARN
    org.springframework.security.web.server: WARN
    org.springframework.web.server: INFO
```

Explanation: on dev, the overall security package is at DEBUG while `security.web.server` is at TRACE; on staging, only the WebFlux security branch is at DEBUG; on prod, WARN is preferred. `application-{profile}.yml` overrides the corresponding baseline values when the profile is activated. A child logger with a specific level will not be replaced simply because a parent logger changes its level.

**Activating the right profile:**

```bash
# Run JAR in dev
java -jar app.jar --spring.profiles.active=dev

# Run JAR in staging via environment variable (Linux/macOS)
SPRING_PROFILES_ACTIVE=staging java -jar app.jar

# Run JAR in prod
java -jar app.jar --spring.profiles.active=prod

# Override a single logger at startup for controlled investigation
java -jar app.jar --spring.profiles.active=staging --logging.level.org.springframework.security.web.server=TRACE
```

You can set package-level environment variables, such as `LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_SECURITY=DEBUG`, to control general levels. For **class-specific** logger names, use file configuration, `--logging.level...` arguments, or `SPRING_APPLICATION_JSON` because environment variable mapping rules do not work well with every uppercase class name. Command-line values generally take precedence over configuration files; multiple simultaneously active profiles can also alter the final value. Verify the actual configuration source being loaded.

**Do not confuse Spring Boot's `--debug` with enabling all Spring Security logs:** this option makes Spring Boot log additional startup information and auto-configuration reports, and is not a deterministic way to set all security loggers to DEBUG. To diagnose security, explicitly set `logging.level.org.springframework.security`.

## 5. WebFlux Example Reproducing 200 / 401 / 403

The example below is for **learning environments only**; `{noop}` passwords are plaintext passwords for demonstration and must never be used for real accounts. In a Spring Boot 3.x project using Java 17+, you need these dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create the file `src/main/java/demo/SecurityLogDemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SecurityLogDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLogDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}learn-only")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @RestController
    static class DemoEndpoints {
        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("public ok");
        }

        @GetMapping("/me")
        Mono<String> me() {
            return Mono.just("authenticated ok");
        }

        @GetMapping("/admin")
        Mono<String> admin() {
            return Mono.just("admin ok");
        }
    }
}
```

`SecurityWebFilterChain` is the **reactive** chain. The `/public` rule allows everyone; `/me` requires authentication; `/admin` requires the `ADMIN` role. The demo account only has the `USER` role, so accessing `/admin` is still denied even after successful login. HTTP Basic is used for easy testing; form login is disabled to avoid redirecting to a login page when observing results.

Run the application with the dev configuration, for example when the project has the Gradle wrapper and Spring Boot Gradle plugin:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

In another terminal, run the following standalone commands. Use `-s -o /dev/null -w` to print only the HTTP status code, avoiding unnecessary body/header output:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
curl -s -o /dev/null -w '%{http_code}\n' -u learner:learn-only http://localhost:8080/me
curl -s -o /dev/null -w '%{http_code}\n' -u learner:learn-only http://localhost:8080/admin
```

With the **exact demo configuration above**, stdout from the four commands is respectively:

```text
200
401
200
403
```

Meaning: the first `200` is the public endpoint; `401` is missing authentication credentials for `/me`; the third `200` is valid Basic auth; the last `403` is authenticated but lacking the `ADMIN` role. In a real application, entry points, access-denied handlers, proxies/gateways, and other rules may produce different responses than this example.

**How to read logs during testing:**

1. Enable DEBUG/TRACE in the dev profile and send **a controlled request**.
2. Filter by request timestamp, `org.springframework.security.*` loggers, path, and response status code.
3. For 401, trace the credential extraction, authentication manager, and authentication entry point steps; verify whether credentials exist/are valid.
4. For 403, check the authenticated principal, authorities/roles in the Authentication, `authorizeExchange` rules, CSRF (for state-changing requests), and the access-denied handler.
5. Compare configuration and logs after switching profiles; if log volume is too high, keep DEBUG/TRACE only on the valuable package.

Do not copy a “standard” log sequence from a Servlet application to verify WebFlux. Logger names, message order, and detailed content vary by Spring Security version and authentication method. Use the response + configuration policy + observed logs to draw conclusions.

## 6. Changing Log Levels at Runtime via Actuator (Optional)

When `spring-boot-starter-actuator` is present and operational policy allows it, the **loggers** endpoint lets you read current levels or adjust log levels without restarting the process. Only configure this endpoint in an administrative environment with authentication/authorization and restricted network access.

Example configuration for a controlled test environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,loggers
```

Once the endpoint is protected and the caller has appropriate permissions, HTTP operations look like:

```http
GET /actuator/loggers/org.springframework.security.web.server

POST /actuator/loggers/org.springframework.security.web.server
Content-Type: application/json

{"configuredLevel":"TRACE"}
```

To clear the directly configured level and revert to the inherited/default configured level, send:

```http
POST /actuator/loggers/org.springframework.security.web.server
Content-Type: application/json

{"configuredLevel":null}
```

On GET, `configuredLevel` is the level explicitly set on that logger (may be `null`), while `effectiveLevel` is the effective level after inheritance. Runtime changes are **temporary**: they may be lost after a restart or overwritten by another configuration management process. You must actively restore the logger to the desired level after finishing the investigation.

**Protecting the endpoint:** Actuator typically exposes only `health` over HTTP by default. If your app has a custom security chain configuration, protect `/actuator/loggers/**` yourself with admin permissions, internal network restrictions, and an appropriate authentication mechanism; do not assume it is automatically secured as intended. POST may return `403` due to CSRF; handle management endpoint authentication/CSRF policies according to your use case, and do not disable CSRF application-wide just to call the API. Never expose `loggers` to the public Internet.

## 7. Logging Aids Observability, But Has Costs

**Performance:** DEBUG/TRACE increases string formatting, stdout/file writes, log shipping, and storage; CPU, I/O, and disk pressure vary with load and the logging backend. In WebFlux, heavy synchronous logging on the request processing path can introduce unwanted latency; measure actual throughput, log volume, and latency, and consider appropriate appender configurations. Do not claim a fixed overhead figure without measuring.

**Sensitive data:** DEBUG/TRACE logs may contain paths, identifiers, credentials, or application data depending on how loggers are written. WebFlux masks certain sensitive headers/parameters by default, but that **does not guarantee every library or custom logger is safe**. Avoid enabling `enableLoggingRequestDetails(true)` or logging full `Authorization` headers, cookies, bearer tokens, passwords, request/response bodies, or personal data. Restrict access, and apply redaction, retention, filtering, and access control in the centralized logging system.

**Reactive characteristics:** a request may resume on different threads, so thread name/thread ID is not a reliable key for correlating logs. Spring WebFlux provides a log ID per request (via `ServerWebExchange#getLogPrefix()`); in multi-service systems, add consistently implemented correlation IDs/tracing. Reactor context is not equivalent to expecting a `ThreadLocal` to always follow the request across all schedulers.

**Recommended policy:** prod usually stays at INFO/WARN per operational needs; during an incident, restrict the duration, logger, account/request scope, and access permissions; afterward, restore previous levels and review the volume/sensitivity of generated logs. Diagnostic logs are not sufficient as an immutable audit log.

## 8. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| Set DEBUG but no security logs appear | Wrong profile; logger did not emit events during test; child logger level overridden | Check active profile, config order, `effectiveLevel`, then send a request hitting the right branch |
| Only seeing Servlet `FilterChainProxy` examples | Comparing MVC documentation with WebFlux | Use `SecurityWebFilterChain` and `org.springframework.security.web.server` |
| `401` but unclear what credential error occurred | Request missing header, wrong authentication provider, or entry point | Check the authentication mechanism in use; enable DEBUG for the relevant authentication package |
| `403` after login | Missing authority/role, rule mismatch, CSRF, or access denied | Cross-check path, HTTP method, authorities, and security configuration |
| Too many logs, high cost | Enabled `root=DEBUG/TRACE` or overly broad security logger | Lower root, target a smaller package, set a time limit then turn off |
| Log level changed but lost on restart | Actuator change is runtime-only | Update files/profiles if a long-term policy is needed; restore if temporary investigation |
| Enabling logs on staging leaks request content | Custom logger, codec config, or gateway logging sensitive data | Review redaction policies and access control, remove unnecessary details |
| Cannot correlate logs of the same request | Reactive request switches threads; missing correlation ID | Use WebFlux log ID/tracing; do not group solely by thread name |

## 9. Deployment Checklist

- [ ] Confirm the stack is **WebFlux reactive** and the right Spring profile is active per environment.
- [ ] Set the narrowest logger sufficient for diagnostics; start with DEBUG, use TRACE only when truly necessary.
- [ ] Test public, unauthenticated, authorized, and unauthorized requests; observe 200/401/403 against actual policy.
- [ ] Check `configuredLevel`/`effectiveLevel` if Actuator is present; restrict endpoint access permissions.
- [ ] Do not log secrets/PII; enforce redaction, retention, and log-enablement time limits.
- [ ] Measure log volume and latency when verbose logging is enabled; restore configuration after investigation.

## Official References

- Spring Boot 3.3 — Externalized Configuration, profile-specific files: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot — Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Boot Actuator — Loggers: https://docs.spring.io/spring-boot/reference/actuator/loggers.html
- Spring Boot Actuator — Exposing and securing endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Framework WebFlux — Logging and sensitive data: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
