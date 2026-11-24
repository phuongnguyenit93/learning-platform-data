# Enabling Controlled DEBUG or TRACE Logging in the Right Environment — Spring Security

> **Topic:** Spring Security - fundamentals → **Observability and Debugging**. The goal is to use `DEBUG`/`TRACE` logs **at the right time, for the right component, in the right environment** to diagnose 401/403 responses, security filter chains, authentication, authorization, and dependent components without **exposing sensitive information, causing overload, or leaving verbose logging permanently enabled**. Practical examples use Java 17, Spring Boot 3.3.5, Spring Security 6.x, Spring MVC/Servlet, SLF4J/Logback, and JUnit 5/MockMvc. WebFlux and other Spring Security versions must be verified against actual loggers and behavior.

## 1. Security Logging: More Is Not Necessarily Better

A **401 Unauthorized** or **403 Forbidden** access error is rarely explained in full in the response sent to the client: returning too many details can help an attacker probe the system. Yet operations need to know where the request stopped—which filter, matcher, provider, or decision—to fix configuration or resolve an incident.

Spring Security provides detailed logging at `DEBUG` and `TRACE` levels. This is an effective investigative tool, but logs can contain data related to accounts, URLs, authorization info, internal errors, or details written by custom extensions. Raising log levels system-wide can cause each request to emit many lines, increasing CPU/I/O load, storage cost, and time spent hunting for clues.

**Practical rule:** prefer keeping `INFO` during normal operations; raise to `DEBUG` only with a specific hypothesis, and raise to `TRACE` narrowly and briefly when `DEBUG` is insufficient; afterward, **restore the previous level** and verify no sensitive data remains exposed in logs.

### Three Questions Before Enabling DEBUG or TRACE

1. **What needs to be diagnosed?** Request not matching a filter chain, rejected credentials, missing authority, invalid CSRF token, invalid Bearer token, or a gateway returning 403?
2. **Where and for how long?** Local/test/staging, a canary instance, a single pod, or an approved, time-boxed production incident window.
3. **Who can view the logs and what could the logs contain?** Secrets, Authorization headers, cookies, query tokens, usernames/emails/tenants, internal paths, stack traces, PII data. Controlling the log pipeline, retention, and access is a prerequisite before increasing verbosity.

Do not turn on system-wide TRACE just because you "cannot find the bug": doing so usually drowns the signal you need in noise and can introduce new risks.

## 2. Understanding Log Levels and Logger Inheritance

| Level | Purpose | When Appropriate |
| --- | --- | --- |
| `ERROR` | Serious failures requiring attention | Tracking operational failures; insufficient to explain every 401/403 |
| `WARN` | Unusual conditions needing attention | Dependency/configuration warnings; avoid treating every failed login as a system error |
| `INFO` | High-level operational events | Default for most environments; favors just-enough information |
| `DEBUG` | Information for analyzing flow and decisions | First step when investigating a specific security issue |
| `TRACE` | Very detailed processing steps, e.g., filters invoked in order | Only when DEBUG is not enough; keep scope and duration very narrow |
| `OFF` | Disables logging for a specified logger | Use very cautiously; can lose investigative signals |

Loggers are typically **named by package or class**. With Spring Boot + Logback, child loggers inherit the level from their parent logger when no explicit level is set.

Example:

```properties
# Logging in normal state
logging.level.root=INFO
logging.level.org.springframework.security=INFO
```

Setting a specific child logger:

```properties
# Only trace SecurityFilterChain selection for requests
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG

# When you need to see filter invocation order at TRACE level
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

These are **two mutually exclusive choices**; do not keep both lines with the same key in one file and expect ordering to carry security meaning. When a class logger is set to `TRACE`, it emits more detail while other Spring Security loggers continue inheriting `INFO` unless individually configured.

### How DEBUG Differs from TRACE in Practice

In Servlet mode, `FilterChainProxy` can log lines such as "Securing GET /private" at DEBUG. At TRACE, logs can add "Invoking [filter name] (i/n)". `DefaultSecurityFilterChain` can print the filter list at startup under DEBUG. Exact messages vary by version and filter; **do not** write a parser around the exact wording of an internal log line and treat it as a stable API.

Illustrative log format example (not fixed output):

```text
DEBUG ... FilterChainProxy : Securing GET /admin
TRACE ... FilterChainProxy : Invoking SecurityContextHolderFilter (...)
TRACE ... FilterChainProxy : Invoking BasicAuthenticationFilter (...)
TRACE ... FilterChainProxy : Invoking AuthorizationFilter (...)
DEBUG ... AccessDeniedHandlerImpl : Responding with 403 status code
```

**Distinguish framework loggers from application loggers:** `logging.level.org.springframework.security=TRACE` increases Spring Security logs, **not automatically** a logger you wrote under `com.example.auth`. If custom code uses `LoggerFactory.getLogger(MyAuthorizationService.class)`, you must configure that application logger—and verify whether it logs secrets before enabling it.

## 3. Knowing Where to Look in Servlet Spring Security

An HTTP request enters `FilterChainProxy`, then goes into one matching `SecurityFilterChain` and its configured security filters. Chain selection, authentication, and authorization are useful points to diagnose.

```text
Client request
    |
    v
Servlet container / proxy / gateway
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy
    |  Selects SecurityFilterChain by RequestMatcher
    |
    +--> Filters protecting request / session / CSRF / CORS ...
    |
    +--> Authentication filter (Basic, form login, Bearer ...)
    |       |
    |       +--> AuthenticationManager / AuthenticationProvider
    |               |
    |               +--> UserDetailsService / IdP / token decoder
    |
    +--> AuthorizationFilter / AuthorizationManager
    |       |
    |       +--> Does Authentication have the required authority?
    |
    +--> Controller / method security
    |
    +--> ExceptionTranslationFilter / entry point / denied handler
              (depending on position and exception type)
```

**Keep in mind:** CORS may be handled early or by a filter at different configured positions; CSRF can return 403 immediately when a state-changing request lacks a token; an API gateway can reject a request **before Spring Security ever sees it**. Do not substitute a theoretical diagram for verifying the actual running chain.

### Useful Loggers

| Investigation Goal | Logger/Package to Try | Starting Level |
| --- | --- | --- |
| Is the request entering the security chain? | `org.springframework.security.web.FilterChainProxy` | DEBUG |
| See each filter invoked in order | `org.springframework.security.web.FilterChainProxy` | Brief TRACE |
| Inspect URL authorization decisions | `org.springframework.security.web.access.intercept.AuthorizationFilter` | TRACE when needed |
| `AuthorizationManager` rules | `org.springframework.security.authorization` | DEBUG, then selective TRACE |
| HTTP Basic/form authentication | `org.springframework.security.authentication` and `org.springframework.security.web.authentication` | DEBUG |
| CSRF 403 | `org.springframework.security.web.csrf` | DEBUG |
| Access denied/entry point handling | `org.springframework.security.web.access` | DEBUG |
| JWT Resource Server | `org.springframework.security.oauth2.server.resource` | DEBUG after reviewing log contents |
| OAuth2 client/login | `org.springframework.security.oauth2.client` | Scoped DEBUG |
| Custom app filter/controller | Application package, e.g. `com.example.security` | DEBUG, with controlled format |

Logger names and log output can vary across Spring Security versions; verify the actual dependencies and classes present in your project. Do not enable all packages at once if you can narrow the scope.

### Reading 401 and 403 as an Event Sequence

- **401**: the request lacks authentication, has invalid credentials, or has an invalid token; inspect the entry point, authentication filter, provider, and exception. Do not conclude 401 always means "the user typed the wrong password": the identity store or configuration might be failing.
- **403**: authenticated but missing authority, invalid CSRF, or another protection mechanism; inspect the exception type and failing filter rather than guessing from status alone.
- **404 or no Security logs**: the URL may not be reaching the app, `securityMatcher` may not match, a reverse proxy may be responding, the endpoint may not exist, or traffic may be hitting another instance.

**Diagnostic order:** identify request ID, where the request arrived, which chain handled it, which filter decided, authentication/authority/CSRF, and finally the HTTP response. Record conclusions with evidence, not just a screenshot of a single log line.

## 4. Safe Per-Environment Configuration with Spring Boot Profiles

Instead of editing the default production log level and forgetting to revert it, use a separate profile **that is only activated intentionally**:

```text
src/main/resources/
├── application.properties
└── application-diagnostics.properties
```

`application.properties` — normal level:

```properties
# Do not emit detailed TRACE for the whole framework by default
logging.level.root=INFO
logging.level.org.springframework.security=INFO
```

`application-diagnostics.properties` — a scoped debugging configuration:

```properties
# Enabled only when intentionally activating the diagnostics profile
logging.level.root=INFO

# Entry flow and filter selection
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG

# Authorization decisions requiring closer observation
logging.level.org.springframework.security.web.access.intercept.AuthorizationFilter=TRACE
logging.level.org.springframework.security.authorization=DEBUG

# Authentication/CSRF analysis when relevant to the issue
logging.level.org.springframework.security.authentication=DEBUG
logging.level.org.springframework.security.web.csrf.CsrfFilter=DEBUG

# Custom service logs only if the service does not log secrets
# logging.level.com.example.myapp.security=DEBUG
```

Here `root` stays at INFO; TRACE applies only to a single class logger. If you need to see every filter invocation, **temporarily** switch `FilterChainProxy` to TRACE, then return it to DEBUG/INFO. Do not assume `application-diagnostics.properties` is unconditionally safe: extensions and framework log messages still need evaluation against real application data.

### Activating the Profile

From a shell with Maven and Java 17:

```bash
# Normal run (INFO)
mvn spring-boot:run

# Run in controlled diagnostics mode:
mvn spring-boot:run -Dspring-boot.run.profiles=diagnostics
```

For an application packaged as a JAR:

```bash
java -jar target/security-logging-demo-1.0.0.jar --spring.profiles.active=diagnostics
```

**Do not treat profiles as access control:** anyone who can alter how the app starts, the command line, environment variables, or config files can change log levels. Govern those permissions through deployment/ops processes.

### Setting Loggers via Startup Arguments

When you need one very specific class without adding a permanent profile:

```bash
java -jar target/security-logging-demo-1.0.0.jar \
  --logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

This is a **startup-time configuration**, not a command that modifies logging on an already-running process. To change at runtime, use Actuator/management controls or logging framework features per security policy. When used in containers/CI, check who can read command lines and deployment manifests.

### Do Not Confuse Spring Boot's "Debug Mode"

Spring Boot's `--debug` or `debug=true` mainly raises a specific set of loggers and prints Boot's auto-configuration report; **it is not equivalent** to `logging.level.org.springframework.security=TRACE`. Similarly, `@EnableWebSecurity(debug=true)` enables web security's debug mode and can produce special logging with potentially sensitive details; it is not a default choice for production. To trace filters and authorization, generally start with **specific loggers**.

## 5. A Runnable Java 17 Project to Investigate 401/403

This example builds a small Servlet application with a public URL, an authentication-required URL, and an ADMIN-role URL. Tests verify security behavior independently of log verbosity. When running with the `diagnostics` profile, you can inspect the configured loggers and match them against 401/403/200 responses.

### 5.1 Structure

```text
security-logging-demo/
├── pom.xml
└── src/
    ├── main/resources/
    │   ├── application.properties
    │   └── application-diagnostics.properties
    ├── main/java/com/example/securitylogging/
    │   └── SecurityLoggingDemoApplication.java
    └── test/java/com/example/securitylogging/
        └── SecurityLoggingDemoApplicationTest.java
```

### 5.2 Maven

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-logging-demo</artifactId>
    <version>1.0.0</version>
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
```

Create the exact two properties files from section 4. They keep normal operation at INFO while providing a separate diagnostics mode.

### 5.3 Java Application

Create `src/main/java/com/example/securitylogging/SecurityLoggingDemoApplication.java`:

```java
package com.example.securitylogging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityLoggingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLoggingDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo456"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @RestController
    static class Controller {

        @GetMapping("/public")
        String publicEndpoint() {
            return "public ok";
        }

        @GetMapping("/me")
        String whoAmI(Authentication authentication) {
            return "hello " + authentication.getName();
        }

        @GetMapping("/admin")
        String adminEndpoint() {
            return "admin ok";
        }
    }
}
```

**Explanation:** `/public` is public; `/me` requires authentication; `/admin` requires default `ROLE_ADMIN`. HTTP Basic ensures anonymous responses return 401 rather than redirecting to form login. `InMemoryUserDetailsManager` defines two demo users (for learning environments only). BCrypt stores hashes; do not log passwords or return them in responses. `@EnableWebSecurity(debug=true)` is omitted because this exercise selects loggers through properties.

**Limitation:** the demo only uses GET, so it does not fully exercise CSRF for POST. When investigating a CSRF-caused 403 in a real application, test state-changing requests separately; do not disable CSRF to "make logs clearer" because doing so removes the very cause under investigation.

### 5.4 JUnit 5 / MockMvc Verifying Security Behavior

Create `src/test/java/com/example/securitylogging/SecurityLoggingDemoApplicationTest.java`:

```java
package com.example.securitylogging;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityLoggingDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResourceIsAvailableWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public ok"));
    }

    @Test
    void anonymousAdminRequestRequiresAuthentication() throws Exception {
        mvc.perform(get("/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotBecomeAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validAdminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo456")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin ok"));
    }

    @Test
    void wrongPasswordIsNotAccepted() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedPrincipalIsAvailable() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello reader"));
    }
}
```

These are **six test cases**: public 200, anonymous 401, unauthorized user 403, authorized admin 200, wrong password 401, and valid principal. The statuses reflect this application's HTTP Basic configuration, not a mandatory rule for all form login or OAuth2 systems.

**Do not write tests that depend on exact internal log wording.** The text of a DEBUG/TRACE line may change across Spring Security upgrades. For functional tests, assert security behavior via responses/side effects; for logging configuration, check effective levels via logging APIs or controlled checks in a diagnostic environment rather than asserting on a fixed log sentence.

### 5.5 Running and Observing

Inside `security-logging-demo` with JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run -Dspring-boot.run.profiles=diagnostics
```

Send requests from another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/admin
curl -i -u reader:demo123 http://localhost:8080/admin
curl -i -u admin:demo456 http://localhost:8080/admin
curl -i -u admin:wrong http://localhost:8080/admin
```

| Request | Expected HTTP | What to Look For in Logs (Independent of Exact Wording) |
| --- | --- | --- |
| GET /public anonymous | 200 | Request enters chain; permitAll matcher |
| GET /admin anonymous | 401 | No valid authentication; entry point requests credentials |
| GET /admin with reader | 403 | Authenticated, but missing `ROLE_ADMIN` |
| GET /admin with admin | 200 | Authentication succeeds, sufficient role |
| GET /admin with wrong password | 401 | Authentication fails; no sensitive reason leaked to client |

Exact log output depends on logger level, version, and formatter. If the expected message does not appear at DEBUG, inspect which logger emits the event and **raise only that class** to TRACE when needed. Do not reflexively raise the root logger to TRACE.

**After testing:** stop the diagnostics process and restart without that profile, or restore log levels via management controls; verify the effective configuration has returned to defaults.

## 6. Changing Log Levels at Runtime with Spring Boot Actuator

Not every incident allows a restart. Spring Boot Actuator provides the **loggers endpoint** to view and change logger levels at runtime. This is a **sensitive administrative capability**: anyone authorized to change loggers can enable TRACE, increasing log cost and causing more detailed data to be written.

**Deployment principle:** this endpoint should generally not be exposed to the public Internet. Use a dedicated management network/localhost, mTLS/VPN/operator identity, operational authorization and auditing, and a time-limit policy. Enable Actuator loggers only when needed; do not turn log-level mutation APIs into endpoints accessible to every logged-in user.

### 6.1 Dependencies and Exposure

Add this dependency **to `pom.xml` only if you actually use Actuator**:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

In a **separate protected management configuration**, you can enable:

```properties
management.endpoints.web.exposure.include=health,loggers
```

This is an **optional configuration fragment**, not a default snippet to drop into the demo app. Exposing the endpoint alone is not enough: **you must add a security policy protecting Actuator**. If the app defines a custom `SecurityFilterChain`, do not assume auto-configuration will protect endpoints the way you expect. Dedicated matchers for management endpoints and management networks are needed, not just `anyRequest().authenticated()`.

In systems with CSRF enabled and endpoints mutating state via HTTP POST, CSRF requirements can still apply. If using automated clients without cookies/browser sessions, design authentication and CSRF for the management flow according to your threat model; **do not disable CSRF application-wide** just to make POST loggers work.

### 6.2 Viewing, Enabling, and Restoring a Logger

Actuator uses the logger name as the path, for example:

```text
GET /actuator/loggers/org.springframework.security.web.FilterChainProxy
```

The logger response may report `configuredLevel` and `effectiveLevel`. These two values differ: `configuredLevel = null` means the logger has no direct override and inherits from its parent; `effectiveLevel` is the active level after inheritance.

To change the level, send an HTTP POST with a JSON body:

```http
POST /actuator/loggers/org.springframework.security.web.FilterChainProxy
Content-Type: application/json

{"configuredLevel":"DEBUG"}
```

For finer detail during a short window:

```http
POST /actuator/loggers/org.springframework.security.web.FilterChainProxy
Content-Type: application/json

{"configuredLevel":"TRACE"}
```

**Revert** the explicit override you set:

```http
POST /actuator/loggers/org.springframework.security.web.FilterChainProxy
Content-Type: application/json

{"configuredLevel":null}
```

This is an **administrative request format example**, not a suggestion to send it directly to an unprotected public endpoint. A real operational request requires operator authentication, proper CSRF policy, network restrictions, auditing, and approval. If the logger's previous level was explicitly `WARN`/`DEBUG`, restore **the original level** rather than blindly setting `null` and altering production policy.

**Runtime behavior:** log-level changes via Actuator generally apply to the current process and do not necessarily persist across restarts/deployments. Each instance in a cluster holds its own runtime state; track which instances are emitting logs and ensure rollback across every instance that was changed.

### 6.3 Controlled Runtime Change Procedure

1. Record the previous level via `GET /actuator/loggers/...` and note **configured vs effective**.
2. Target a specific logger and a specific instance; obtain approval/ticket if production change control requires it.
3. Set DEBUG and observe requests with a correlation ID. Raise to TRACE only if DEBUG is insufficient.
4. Bound duration and log volume; monitor CPU, I/O, queues, storage, and sensitive data.
5. Restore the exact original level, read it back to verify, close the ticket, and record the rollback timestamp.
6. Review generated logs and restrict access/retention if sensitive data may have been captured.

Runtime log mutation should be monitored as an **audited administrative action**; never hand Actuator control tokens to regular frontends or browsers.

## 7. A Hypothesis-Driven Playbook for Observing 401/403

### 7.1 A 401 Request Even Though the Client Believes Credentials Are Valid

**Hypothesis:** the request hit the wrong SecurityFilterChain, the Authorization header was not received, the provider does not support the token, or the identity store/IdP failed.

Steps:

1. Attach a **non-PII request ID/trace ID**, and verify the same ID across the gateway and application.
2. Enable `FilterChainProxy=DEBUG` to confirm whether Spring Security processed the request.
3. If needed, enable `org.springframework.security.authentication=DEBUG` or the relevant filter logger, after ensuring the test area uses dummy credentials.
4. Check the `AuthenticationException` type, provider, upstream HTTP status, timeouts, and internal failure reason. Never log raw passwords, Authorization headers, or JWTs.
5. Turn the logger back down and record the conclusion; do not tell users to reset passwords if the root cause is a database/IdP outage.

**Avoid wrong inferences:** Spring Security may intentionally avoid distinguishing "user not found" from "bad password" in public messages to prevent account enumeration. DEBUG/TRACE is for internal diagnostics and must not be forwarded verbatim into API responses.

### 7.2 A 403 Request Even Though the User Is Authenticated

**Hypothesis:** missing authority, wrong role prefix, missing CSRF token, method security differing from URL rules, or tenant-based policy.

Steps:

1. Check the **HTTP method**. For POST/PUT/DELETE, check CSRF before changing roles.
2. Read `FilterChainProxy=DEBUG` and `AuthorizationFilter` at an appropriate level.
3. Verify `hasRole("ADMIN")` compares against authority `ROLE_ADMIN` per prefix configuration; `hasAuthority("SCOPE_read")` must match the exact string.
4. If `@PreAuthorize` sits on a service, the URL check can pass while method security denies it. Inspect method-security logs in the authorization package and relevant proxies.
5. Do not print `Authentication.toString()` unconditionally; principals/claims may contain PII or sensitive metadata.
6. Restore log levels and write a regression test covering 403/200 for the right permissions.

### 7.3 403 Appearing Only in Browsers

**Hypothesis:** CORS preflight rejected, CSRF token/cookie not sent, or SameSite/Secure/proxy settings affecting session state.

Separate:

- **Preflight OPTIONS**: check `Origin`, `Access-Control-Request-Method`, requested headers, and CORS filter/gateway config. Browsers do not necessarily send credentials on preflight.
- **Actual POST**: check CSRF token, cookies, Authentication, and authorization.
- **Response headers**: is `Access-Control-Allow-Origin` accurate or overwritten by a gateway?
- **Network/proxy**: did the request actually reach the app, or did the browser block it before reaching the backend?

CORS does not replace authentication or CSRF. Do not apply quick fixes like `allowedOrigins("*")` or `csrf.disable()` just to make the 403 go away.

### 7.4 403/401 with No Spring Security Logs

The absence of logs **proves neither that the request is secure nor insecure**. You may have enabled the wrong logger, checked the wrong instance, traffic hit a different gateway, logs were filtered, `securityMatcher` did not match, or a filter did not emit an event at the active level. Verify proxy/ingress access logs, trace ID, filter chain config, effective logger level, and routing before escalating root to TRACE.

## 8. Reducing the Risk of Exposing Sensitive Data in DEBUG/TRACE

### 8.1 Information You Must Never Intentionally Log

- Passwords/PINs/OTPs, raw Basic Authorization headers, raw JWT access/refresh tokens, API keys, session cookies, CSRF tokens, OAuth authorization codes, client secrets.
- Private keys, secret signing keys, connection strings containing credentials, or environment secrets.
- Query parameters containing tokens, reset links, or sensitive identifiers; request/response bodies with personal, payment, or medical data.
- Full `Authentication`, `SecurityContext`, `Principal`, `UserDetails`, or claim objects without reviewing their `toString()`/serialization and fields.

Framework loggers may not intentionally print passwords, but **extensions, custom filters, HTTP client wire logs, access logs, and third-party libraries** can still emit other details. Selecting only the `org.springframework.security` category does not guarantee clean logs.

### 8.2 How to Write Custom Logs Properly

Anti-pattern:

```java
// WRONG — credentials or entire request objects may be exposed.
log.debug("Login request: {}", loginRequest);
log.trace("Authorization: {}", request.getHeader("Authorization"));
log.debug("Principal: {}", authentication.getPrincipal());
```

These snippets are **fragments** where `loginRequest`, `request`, and `authentication` are application-defined variables; never implement logging like this.

Replace with structured, minimal-data events:

```java
// Fragment using SLF4J; requestId is generated, validated, and format-bounded.
log.debug("auth outcome={} requestId={} route={}",
    "DENIED", requestId, "/api/reports");
```

Never take the route straight from a URL containing query tokens. If a user identifier is needed for investigation, use an internal/hashed identifier per policy rather than logging raw emails/usernames by default. When logging exceptions, keep only the error type and correlation ID sufficient for operations; detailed stack traces belong only in properly protected storage.

### 8.3 Do Not Log Payloads Arbitrarily in Auth Filters

A custom `OncePerRequestFilter` receives `HttpServletRequest`. Using `ContentCachingRequestWrapper` and printing the full body at TRACE can log passwords, tokens, and sensitive payloads. If you need the route, log a **route template** or a normalized path allowlist; avoid logging full URL queries.

**Allowlist-based** redaction is safer than blocklisting: only log fields verified to be safe rather than dumping all fields and trying to strip keys like `password`. Secrets can also hide inside nested JSON, custom headers, or URL tokens.

### 8.4 Log Access Permissions and Retention

Security system logs are a sensitive data source. When enabling TRACE, verify:

| Control | Action Required |
| --- | --- |
| Viewers | RBAC/mTLS/VPN; separate log-viewing rights from logger-level mutation rights |
| Environment | Prefer local/staging with synthetic or anonymized data |
| Scope | Specific logger, instance, request path, and incident window |
| Duration | Record enable/disable timestamps; auto-rollback if infrastructure supports it |
| Volume | Cap volume; avoid overloading sinks or dropping critical audit logs |
| Retention | Policy-based TTL/deletion; encryption at rest and in transit |
| Secondary tools | Reverse proxies, APM, distributed tracing, and body capture must also apply redaction |
| Evidence | Save conclusions and request IDs; never attach tokens/passwords to tickets or chats |

If a secret is discovered in logs: restrict access, assess exposure, trigger incident response, rotate/revoke credentials as needed, and purge per retention policy. **Turning off TRACE alone does not delete data already shipped to centralized logging.**

## 9. Performance Cost, Reliability, and Overload Signals

Adding logs to every filter and every request can cause event count and size to spike:

- **CPU**: string formatting, stack traces, JSON serialization, regex redaction.
- **I/O and networking**: console/file appenders, log shippers, queues, and backpressure.
- **Storage**: higher indexing, storage, and search costs.
- **Latency**: synchronous appenders or slow sinks can lengthen request processing times.
- **Availability**: full disks or congested logging pipelines can affect the app; increasing logs during peak traffic can worsen an outage.

Do not rely on rules of thumb like "TRACE adds x% CPU" without measuring on your specific architecture. Watch p95/p99 latency, log events/s, shipper backlog, disk utilization, JVM CPU, network egress, error rates, and sensitive-data volume.

**Important tip:** logger level differs from log sampling. Pipeline sampling can reduce volume, but never blindly sample mandatory audit events or rare events needed for investigation. When using async appenders, you still have to manage queue capacity/drop policies and sensitive data; do not treat async as infinite capacity.

## 10. Differences Across Servlet, WebFlux, and Other Observability Layers

| Component | Servlet/Spring MVC | WebFlux/Reactive |
| --- | --- | --- |
| Security chain | `SecurityFilterChain`, `FilterChainProxy` | `SecurityWebFilterChain`, reactive web filters |
| Security context | Typically `SecurityContextHolder`/ThreadLocal | `ReactiveSecurityContextHolder`/Reactor Context |
| Error tracing | Filters, `ExceptionTranslationFilter`, entry point/denied handler | Reactive authentication/authorization and error handlers |
| Per-request tracing | Servlet request/MDC with proper propagation | Reactor Context, context propagation |
| Risk when enabling TRACE | Volume, PII, log I/O | All of the above **plus** risk of stalling event loops if appenders/formatting block |

Do not copy the Servlet logger class list directly to WebFlux and conclude TRACE does not work. WebFlux uses packages under `org.springframework.security.web.server` and reactive components. Also, MDC does not automatically follow a subscriber across Reactor thread switches without proper context propagation configured.

**With distributed tracing**, trace/span IDs let you locate events without enabling framework-wide logging. However, trace attributes/baggage can also leak sensitive data if poorly designed; never put tokens or personal info into spans.

## 11. A Repeatable, Time-Bounded Debugging Process

A standard workflow for development and operations teams:

1. **Describe the incident:** endpoint, method, timestamp, environment, HTTP status, correlation ID, frequency, impact. Do not write passwords/tokens into the ticket.
2. **Form a hypothesis:** CSRF, permissions, provider, matcher, gateway/IdP, or session. Pick the corresponding logger.
3. **Check defaults first:** existing metrics/audit/access logs before turning on DEBUG.
4. **Pick the smallest scope:** local/staging first; production only with justification and authorization, on a single instance or isolated scope.
5. **Record baseline levels:** profile/Actuator `configuredLevel`/`effectiveLevel`, inherited level, timestamp, and approver.
6. **Enable DEBUG and reproduce:** use demo users, synthetic data, or sanitized requests; verify traffic hits the targeted instance.
7. **Escalate to TRACE only if insufficient:** enable a very narrow class/package, monitor volume and risk, and set an expiration time.
8. **Analyze:** correlate via correlation ID, security decisions, exceptions, responses, and upstream events; prove root cause.
9. **Roll back immediately:** restore the **original level**, verify effective level, disable the profile/redeploy or POST Actuator per process.
10. **Verify post-change:** log volume, CPU, and latency return to normal; confirm no secret leakage; write a regression test for the bug found.
11. **Close the incident:** document conclusion, timeline, and prevention steps without storing raw token/password dumps in shared docs.

**Clear stopping point:** once you have enough evidence to pinpoint the issue, turn off TRACE. Do not keep elevated levels "just in case for next time."

## 12. Common Mistakes When Enabling DEBUG/TRACE

### Mistake 1 — Setting `logging.level.root=TRACE`

Every library/SDK can dump massive logs, including HTTP clients, ORMs, networking, and application-printed objects. **Fix:** start from a specific Spring Security logger and expand step by step with evidence.

### Mistake 2 — Thinking `--debug` Equals Security TRACE

Spring Boot's debug flag and Spring Security loggers are separate mechanisms. **Fix:** inspect effective logger levels and specify the exact category.

### Mistake 3 — Enabling `@EnableWebSecurity(debug=true)` in Production

This special debug mode can emit extensive request/security details unsuitable for production. **Fix:** prefer narrow DEBUG/TRACE loggers in safe environments and turn them off afterward.

### Mistake 4 — Seeing 403, Turning On TRACE, Then Disabling CSRF

A POST without a CSRF token returning 403 is expected behavior. **Fix:** classify the cause using `CsrfFilter` and regression tests rather than relaxing policy just to make a request succeed.

### Mistake 5 — Printing Entire Authentication/Authorization Headers

Principals and tokens can contain sensitive data, and `toString()` may reveal unintended fields. **Fix:** use allowlist-based structured logging, never log credentials, and hash/mask when required by policy.

### Mistake 6 — Raising the Logger on the Wrong Instance

In microservices/clusters, requests may land on a different pod. **Fix:** use trace IDs, pod/instance IDs, gateway access logs, and routing checks; apply and roll back on the exact instances modified.

### Mistake 7 — Forgetting to Revert Runtime Overrides

`configuredLevel=TRACE` persists in the process until changed back or restarted depending on setup. **Fix:** save the original level, set expiration alerts, roll back, and re-read effective levels.

### Mistake 8 — Exposing `/actuator/loggers` as a Public Endpoint

Anyone able to mutate loggers can trigger log floods and information disclosure. **Fix:** expose only on management networks with operator authentication, strict authorization, and auditing.

### Mistake 9 — Writing Tests That Assert on Verbatim TRACE Messages

Spring Security does not guarantee identical log strings across upgrades. **Fix:** test security behavior in JUnit; logs are observability data, not an application API contract.

### Mistake 10 — Assuming DEBUG/TRACE Is Always Harmless to Performance

Even with asynchronous appenders, log formatting and queues consume resources. **Fix:** monitor log rate, CPU, disk, and latency; bound TTL, logger scope, and traffic.

### Mistake 11 — Using Environment Variables for Every Class Name

Spring Boot supports `LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_SECURITY=DEBUG` for packages, yet uppercase environment variable binding can fail to preserve mixed-case class names accurately. **Fix:** use `application.properties`, command-line properties, `SPRING_APPLICATION_JSON`, or Actuator for specific class loggers, and always check the effective level.

### Mistake 12 — Pasting Raw Logs into Issues or AI Tools

DEBUG/TRACE lines can contain IDs, tokens, sensitive URLs, and organizational data. **Fix:** review and sanitize before sharing, following data governance and access policies. Never share secrets simply because you are troubleshooting.

## 13. Checklist for Choosing Which Log Level to Enable

| Scenario | Starting Step | When DEBUG Is Insufficient | What Must Be Verified |
| --- | --- | --- | --- |
| Unknown which security chain matches a URL | `FilterChainProxy=DEBUG` | `FilterChainProxy=TRACE` | Exact instance/RequestMatcher/filter |
| User has role yet gets 403 | `AuthorizationFilter=DEBUG` or authorization package | Narrow TRACE | Actual authorities, role prefix, method security |
| POST gets 403 | `CsrfFilter=DEBUG` | Time-boxed TRACE | Missing/invalid token, CSRF matcher, session/cookie |
| HTTP Basic returns 401 | Authentication package DEBUG | Specific provider/filter logger | Never log passwords or Basic headers |
| Bearer JWT rejected | Resource-server package DEBUG | TRACE relevant class if safe | Issuer, audience, expiry, decoder/IdP |
| OAuth login fails | OAuth2 client package DEBUG | TRACE only in synthetic-data environment | Redirect, state, error code, IdP response |
| Logs missing | Check effective logger level + instance | Check proxy/trace ID | Whether the request reached Spring Security |
| Production root cause still unclear | Existing metrics and INFO logs | Time-windowed DEBUG, TRACE as last resort | Approval, TTL, rollback, log redaction |

**Level selection rule:** one narrow question → one narrow logger → one explicit time limit → verified rollback.

## 14. Conclusion

- `DEBUG`/`TRACE` are very useful for understanding filter chains, authentication, authorization, CSRF, and 401/403 paths, but **should not be enabled broadly or permanently**.
- Start at `INFO` in normal operation, raise to `DEBUG` for the relevant package/class, and use `TRACE` only when finer detail is required in a controlled environment and time window.
- Use profiles or temporary startup overrides; if modifying at runtime via the **Actuator loggers endpoint**, protect the endpoint, record the old level, verify rollback, and audit.
- Diagnose using **correlation IDs, root causes, and security behavior**, not HTTP statuses or verbatim log lines alone.
- Never log passwords, tokens, Authorization headers, cookies, or entire principals/requests; prevent logging from overloading CPU, I/O, or storage.
- Once you reach a conclusion, **revert log levels and add a regression test** so you do not need TRACE for the same bug next time.

## Official Reference Documentation

- Spring Security — Servlet Architecture, Security Filters/Logging section: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authorization for Servlet: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Testing MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Boot — Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot — Actuator Loggers endpoint: https://docs.spring.io/spring-boot/reference/actuator/loggers.html
- Spring Boot — Actuator Endpoint Security: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- OWASP Cheat Sheet — Logging: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html