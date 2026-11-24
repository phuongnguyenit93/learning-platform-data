# Reading Login, Failed Login, and Access Denied Events

## 1. Three distinct questions in security auditing

In the HTTP and auditing chapter of Spring Boot Actuator, audit events help answer: which identity was just authenticated, which authentication attempt failed, and who was blocked when requesting a resource. These are security decision points; they add context that a single HTTP status code cannot express.

**Authentication** checks "who are you?". **Authorization** checks "are you allowed to do this?". Because these two checks serve different purposes, someone can authenticate successfully and still be denied access.

| Situation | Default audit type to look for | Accurate interpretation |
| --- | --- | --- |
| Credentials accepted | `AUTHENTICATION_SUCCESS` | Authentication step succeeded; does not prove the business request succeeded |
| Credentials rejected | `AUTHENTICATION_FAILURE` | An authentication attempt failed; read the reason further |
| Authorization decision denies access | `AUTHORIZATION_FAILURE` | Request did not meet access permissions; not synonymous with a wrong password |

For example: Alice enters the right password and requests an admin-only resource. Both `AUTHENTICATION_SUCCESS` and `AUTHORIZATION_FAILURE` may appear for Alice. These two records describe two phases of the same situation and do not contradict each other.

Spring Boot provides listeners that translate Spring Security events into audit events. The audit framework requires an `AuditEventRepository` bean; do not assume merely adding the Actuator starter gives you a security history store. [Spring Boot 3.3 Auditing Documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

## 2. How do events flow from Spring Security to Actuator?

```text
HTTP request
  -> Spring Security checks authentication / authorization
  -> Publishes corresponding security event
  -> AuthenticationAuditListener / AuthorizationAuditListener
  -> AuditApplicationEvent containing AuditEvent
  -> AuditListener stores into AuditEventRepository
  -> GET /actuator/auditevents reads records matching filters
```

You can read over HTTP via the endpoint, query the repository directly in Java, or observe `AuditApplicationEvent` as it is published. These three approaches serve different moments: the endpoint and repository query stored data, whereas a listener observes events in flight.

In Spring Boot 3.3, `AuthenticationAuditListener` translates authentication success and failure events into the two corresponding audit types. `AuthorizationAuditListener` handles `AuthorizationDeniedEvent` to produce `AUTHORIZATION_FAILURE`; there is no rule that every HTTP 403 automatically turns into this audit event. [AuthorizationAuditListener 3.3.0 source](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/security/AuthorizationAuditListener.java).

With Spring Security 6.3's `authorizeHttpRequests`, the configurer wires a publisher for `AuthorizationFilter`: using an `AuthorizationEventPublisher` bean if present, or creating `SpringAuthorizationEventPublisher`. Thus you must not conclude that this standard configuration always lacks events unless a separate publisher bean is declared. When building custom filters, managers, or authentication flows, verify the actual publisher wiring. [AuthorizeHttpRequestsConfigurer 6.3.0 source](https://github.com/spring-projects/spring-security/blob/6.3.0/config/src/main/java/org/springframework/security/config/annotation/web/configurers/AuthorizeHttpRequestsConfigurer.java).

`SpringAuthorizationEventPublisher` 6.3 publishes only denial decisions by default; not seeing an "authorization success" record matches this mechanism. Do not invent or infer an `AUTHORIZATION_SUCCESS` type from `AUTHENTICATION_SUCCESS`. [SpringAuthorizationEventPublisher 6.3.0 source](https://github.com/spring-projects/spring-security/blob/6.3.0/core/src/main/java/org/springframework/security/authorization/SpringAuthorizationEventPublisher.java).

## 3. Reading the fields of a record

The response contains an `events` array. The example below is **illustrative data with omitted fields**, not mandatory verbatim output for every run:

```json
{
  "events": [
    {
      "timestamp": "2026-01-01T10:00:00Z",
      "principal": "alice",
      "type": "AUTHENTICATION_SUCCESS"
    },
    {
      "timestamp": "2026-01-01T10:00:10Z",
      "principal": "alice",
      "type": "AUTHENTICATION_FAILURE",
      "data": {
        "type": "org.springframework.security.authentication.BadCredentialsException",
        "message": "Bad credentials"
      }
    },
    {
      "timestamp": "2026-01-01T10:00:20Z",
      "principal": "alice",
      "type": "AUTHORIZATION_FAILURE"
    }
  ]
}
```

| Field | Meaning | Point to check |
| --- | --- | --- |
| `timestamp` | Event timestamp | Read with time zone; `Z` is UTC, not local time |
| `principal` | Actor name attached to the check | For authentication failure, may be an unverified caller-claimed name |
| `type` at event level | Audit type | Used to classify auth success, auth failure, or authorization failure |
| `data` | Supplementary data depending on listener and context | May contain `type`, `message`, `details`; do not assume every record has the same structure |

**Distinguish two fields with the same name:** `events[i].type` may be `AUTHENTICATION_FAILURE`, whereas `events[i].data.type` may be an exception class name such as `BadCredentialsException`. The query parameter `type=AUTHENTICATION_FAILURE` filters the outer audit type, not the inner exception name.

In Boot 3.3's default authentication listener, failures include exception type and message; `details` is included when the authentication object holds that data. `BadCredentialsException` indicates credentials were not accepted, which is not enough to conclude whether the account name exists. A locked account, expired account, or authentication service error should also not be lumped into "wrong password".

`data.details` from a web flow may contain remote address and session ID. This is not a contract that every event includes IP, URL, HTTP status, or session ID. In particular, default access-denied audit events do not guarantee containing the blocked resource; correlate with HTTP data or an intentionally added context mechanism.

For anonymous access, the principal may be `anonymousUser`; in some cases where authentication info cannot be obtained, it may be `<unknown>`. Do not treat these values as logged-in user identities.

## 4. Local experiment with Spring Boot 3.3 and Java 17+

The following example is a standalone Spring MVC application to observe all three scenarios. The code uses Spring Boot **3.3.0** and Spring Security **6.3.0** via Boot dependency management; this is an example reproducibility baseline, not a patch-level recommendation for deployment. It can run on JDK 17 or JDK 21.

Create a Gradle Java project with a wrapper compatible with Boot 3.3. Arrange files as:

```text
audit-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat and gradle/wrapper/
  src/main/java/example/audit/AuditDemoApplication.java
  src/main/resources/application.yml
```

`settings.gradle`:

```groovy
rootProject.name = 'audit-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

`src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  auditevents:
    enabled: true
  endpoint:
    auditevents:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,auditevents
```

The three switches have distinct roles: `management.auditevents.enabled` controls the audit framework configuration; `management.endpoint.auditevents.enabled` controls the endpoint; `management.endpoints.web.exposure.include` determines whether the endpoint is exposed over HTTP. Collecting events and exposing the endpoint are two separate concerns. The `auditevents` endpoint also requires a repository. [AuditAutoConfiguration 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/audit/AuditAutoConfiguration.html), [Boot 3.3 endpoint configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

`src/main/java/example/audit/AuditDemoApplication.java`:

```java
package example.audit;

import java.security.Principal;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.AuditEventsEndpoint;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@RestController
public class AuditDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuditDemoApplication.class, args);
    }

    @Bean
    AuditEventRepository auditEventRepository() {
        return new InMemoryAuditEventRepository(1000);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-demo"))
                .roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-demo"))
                .roles("USER", "ADMIN").build(),
            User.withUsername("auditor")
                .password(encoder.encode("audit-demo"))
                .roles("AUDIT").build()
        );
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new DefaultAuthenticationEventPublisher(publisher);
    }

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new SpringAuthorizationEventPublisher(publisher);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(EndpointRequest.to(AuditEventsEndpoint.class))
                    .hasRole("AUDIT")
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/admin/report").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @GetMapping("/profile")
    String profile(Principal principal) {
        return "profile:" + principal.getName();
    }

    @GetMapping("/admin/report")
    String report() {
        return "admin-report";
    }
}
```

Choices in the example:

- `alice` has `USER` role; `bob` also has `ADMIN`; `auditor` has only `AUDIT` to read history. Having business admin privileges does not automatically grant audit read permissions.
- `InMemoryAuditEventRepository(1000)` stores up to 1,000 events in process memory. It suits experiments; restarts clear data and exceeding capacity replaces old events.
- Both publisher beans are explicitly declared so the wiring to the event system is visible. In an application with standard configuration already in place, check existing beans before adding; do not create a duplicate publish/store path.
- `STATELESS` configuration ensures the experiment's Basic requests do not rely on a prior login session. A new request with valid credentials can emit a new authentication success event.
- Only internal dispatches of type `ERROR` bypass authorization re-checking in the example; this avoids error-page handling masking the initial observation. Authorization for the original HTTP request is still checked.
- All tests use GET, so disabling CSRF is unnecessary. Do not copy disabling CSRF just to fix an unexplained HTTP 403.

The application listens only on `127.0.0.1`. The passwords in the code are sample data for a personal machine. When using Basic over a real network, HTTPS and proper credential management are required.

Start from the project directory:

```bash
./gradlew bootRun
```

On Windows PowerShell use `.\gradlew.bat bootRun`. The HTTP commands below use curl; on PowerShell where `curl` is an alias, invoke `curl.exe`. This application requires Spring dependencies, so it cannot be run standalone with `javac AuditDemoApplication.java`.

## 5. Generating and verifying the three event types

Keep the application running and use another terminal window. Do not send session cookies from other tests.

### 5.1. Authentication success

```bash
curl -i -u alice:alice-demo http://127.0.0.1:8080/profile
```

Expect HTTP 200 with exact body `profile:alice`. The request authenticated and was permitted to call `/profile`; querying Alice's audit events shows `AUTHENTICATION_SUCCESS`. Do not treat this event type as proof that every API Alice calls afterward is permitted.

### 5.2. Authentication failure

```bash
curl -i -u alice:wrong-demo http://127.0.0.1:8080/profile
```

Expect HTTP 401 and `AUTHENTICATION_FAILURE` for name `alice`. Inspect `data.type` and `data.message` as well; in this wrong-password example it is typically `BadCredentialsException` with message `Bad credentials`. Error language/messages can vary when customized.

### 5.3. Valid authentication but insufficient permissions

```bash
curl -i -u alice:alice-demo http://127.0.0.1:8080/admin/report
```

Expect HTTP 403. Alice may have an `AUTHENTICATION_SUCCESS` because the password was right, followed by `AUTHORIZATION_FAILURE` due to lacking `ROLE_ADMIN`. Cross-check with an authorized account:

```bash
curl -i -u bob:bob-demo http://127.0.0.1:8080/admin/report
```

Expect HTTP 200 with exact body `admin-report`. `AUTHORIZATION_SUCCESS` is not required to appear to validate this result.

| Test | Expected HTTP in sample config | Primary audit signal |
| --- | --- | --- |
| Alice calls `/profile`, right password | 200 | `AUTHENTICATION_SUCCESS` |
| Alice calls `/profile`, wrong password | 401 | `AUTHENTICATION_FAILURE` |
| Alice calls `/admin/report`, right password | 403 | `AUTHENTICATION_SUCCESS` and `AUTHORIZATION_FAILURE` |
| Bob calls `/admin/report`, right password | 200 | `AUTHENTICATION_SUCCESS` |

These are results of the sample configuration, not a universal lookup table between HTTP and audit events. Form login can use 302 redirects; an intermediate gateway can return errors before the request reaches the application; CSRF can block requests; application code can return 403 directly without a corresponding authorization decision.

A request carrying no credentials also differs from a request carrying a wrong password. For instance, an anonymous caller accessing a protected resource may be denied authorization and receive 401 from the authentication-entry mechanism even though no password check failed.

## 6. Reading via the endpoint and using filters

Read all events currently retained by the repository:

```bash
curl -s -u auditor:audit-demo http://127.0.0.1:8080/actuator/auditevents
```

To focus on Alice, filter by `principal`:

```bash
curl -s -u auditor:audit-demo -G http://127.0.0.1:8080/actuator/auditevents --data-urlencode "principal=alice"
```

Filter specifically for Alice's authentication failures after a timestamp:

```bash
curl -s -u auditor:audit-demo -G http://127.0.0.1:8080/actuator/auditevents --data-urlencode "principal=alice" --data-urlencode "type=AUTHENTICATION_FAILURE" --data-urlencode "after=1970-01-01T00:00:00Z"
```

The 1970 timestamp in the command ensures the example does not miss data from the current run. During real investigations, use a timestamp close to the target time window to narrow results. Change type to `AUTHENTICATION_SUCCESS` or `AUTHORIZATION_FAILURE` to verify the other two groups.

| Parameter | Usage |
| --- | --- |
| `principal` | Actor name; with the example's in-memory store, this is an exact match, not substring matching |
| `type` | A specific audit type; case-sensitive in the example |
| `after` | ISO-8601 timestamp with time zone; the in-memory store selects events **strictly after**, excluding events at the exact boundary |

Parameters are optional and narrow the result set together when combined. The endpoint does not provide built-in `before` filters, page numbers, or total historical record counts across the whole system. Do not add `page`/`size` assuming the data is paginated. [`auditevents` HTTP Contract](https://docs.spring.io/spring-boot/api/rest/actuator/auditevents.html).

`after` can use `Z` or a valid time zone offset. Using `--data-urlencode` is especially helpful with offsets like `+07:00`, because `+` in a query string can be interpreted as a space if the URL is concatenated manually.

**The reader itself also creates a trace:** under stateless Basic configuration, `auditor`'s request can generate another `AUTHENTICATION_SUCCESS` before the endpoint returns data. Therefore, do not assert the array will have exactly four or five elements. Filtering `principal=alice` separates test calls from the auditor's own query activity.

You can test the read-permission boundary with the following command:

```bash
curl -i -u alice:alice-demo http://127.0.0.1:8080/actuator/auditevents
```

Expect 403 because Alice lacks `AUDIT`. This test itself generates more events for Alice; if a clean experimental dataset is needed, restart the application and execute only the chosen request sequence.

## 7. Reading in Java and observing new events

When writing an internal component that needs to query audit events, inject `AuditEventRepository` and call `find(principal, after, type)`. The example below is a Spring component supplementing the application above, not a separate program with `main`:

```java
package example.audit;

import java.time.Instant;
import java.util.List;

import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.stereotype.Service;

@Service
public class AuditReader {
    private final AuditEventRepository repository;

    public AuditReader(AuditEventRepository repository) {
        this.repository = repository;
    }

    public List<AuditEvent> failedAuthentications(String principal, Instant after) {
        return repository.find(principal, after, "AUTHENTICATION_FAILURE");
    }
}
```

`after` in the repository API is an `Instant`; the HTTP endpoint parses a zoned timestamp and converts it to the corresponding instant. Do not mix up parameter order as `find(type, after, principal)`. `null` for a criterion in the in-memory store means omitting that filter criterion.

To observe immediately when an audit event is published, you can add the following component. It logs only timestamp and event type, avoiding printing all user data:

```java
package example.audit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.listener.AuditApplicationEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AuditObserver {
    private static final Logger log = LoggerFactory.getLogger(AuditObserver.class);

    @EventListener
    public void onAudit(AuditApplicationEvent applicationEvent) {
        AuditEvent event = applicationEvent.getAuditEvent();
        if ("AUTHENTICATION_FAILURE".equals(event.getType())
                || "AUTHORIZATION_FAILURE".equals(event.getType())) {
            log.info("Security audit at={} type={}",
                event.getTimestamp(), event.getType());
        }
    }
}
```

This listener does not replay events that occurred before it became active and does not replace the repository. Do not call `repository.add(event)` inside this listener when Boot's default storage listener is running: that could store the same event twice. Also do not perform network calls or heavy synchronous work inside the login path just to inspect one record.

## 8. Investigating from evidence rather than guesswork

A systematic reading approach is to pick a time window, filter actor/event type, inspect the cause, and then correlate with HTTP data and permission rules in effect at that time:

1. **Establish time and configuration version.** Convert UTC/local time before correlating events; do not compare hour numbers alone.
2. **Distinguish authenticated identity from claimed name.** For authentication failures, `principal=alice` does not prove Alice herself sent the request.
3. **Read the authentication failure cause.** Wrong credentials, locked accounts, and authentication service failures require different remediation steps.
4. **Check permissions on denial.** Inspect actual granted authorities, path-matching rules, and method security if present. Do not treat every `AUTHORIZATION_FAILURE` by resetting passwords.
5. **Correlate additional context.** Default audit events do not guarantee URL/HTTP status/request ID; use HTTP data or added context to confirm the specific resource. Do not assign two records to the same request merely because they share a username and close timestamps.
6. **State conclusions proportionally.** "There are multiple authentication failures for the name Alice" is evidence; "Alice is under a password-guessing attack" also requires context, rate, and further verification.

Concurrent requests can interleave events. Do not assume two adjacent elements in the array are an authentication/authorization pair for the same request, and do not assume all repositories return results in the same order.

## 9. When expected events are missing

| Symptom | What to check first |
| --- | --- |
| Endpoint unreachable / 404 | Does a repository bean exist; are endpoint and exposure enabled; right port, base path, context path, and instance |
| Endpoint returns 401/403 | Permissions of the **audit reader**; do not immediately conclude the audit store is broken |
| `events` is empty | Are time/type/principal filters right; was an event actually generated; did the process just restart |
| HTTP 401 but no `AUTHENTICATION_FAILURE` | Did the request send credentials; did the error come from the app or a gateway; is the publisher used in the actual auth flow |
| HTTP 403 but no `AUTHORIZATION_FAILURE` | Was the denial made by an authorization mechanism that publishes events; or did CSRF, business code, proxy, or another mechanism return the error |
| Older records missing | In-memory capacity limit, restart, or reading the wrong instance |
| One action creates multiple records | Stateless Basic, multiple browser requests, error dispatch, multiple authorization layers, or duplicate storage listeners |
| No URL or reason in denial record | Not every field is supplied by default listeners; verify the data contract rather than guessing |

Do not fix issues by exposing all of Actuator or allowing everyone to read audits. First separate the three steps: **was the event published → was it stored → is the reader querying accurately with sufficient permissions**.

## 10. Limits when applying beyond the experiment

`InMemoryAuditEventRepository` is a local, bounded-capacity, non-durable store. With multiple instances, each instance holds its own slice of history; one query through a load balancer does not represent the entire system. Choose an appropriate centralized repository/storage if investigations require data across restarts and across multiple instances.

Audit read access should follow least privilege. Account names, remote addresses, session IDs, and error messages can be sensitive; do not dump all of `data` indiscriminately, do not store passwords or tokens in custom events, and do not assume the endpoint automatically masks all such details. For IPs behind a proxy, trust forwarded headers only when the proxy chain and trust policy are properly configured.

Counting failures for alerting or account lockout requires additional policy, time windows, and concurrency handling. An in-memory repository plus three event types do not form a complete brute-force protection mechanism. Locking by unverified username can also be abused to lock out legitimate users.

## 11. Self-check

1. Alice calls `/admin/report` with the right password and gets 403. Explain why both `AUTHENTICATION_SUCCESS` and `AUTHORIZATION_FAILURE` can appear together.
2. Reading one `AUTHENTICATION_FAILURE` for Alice: which field is the audit type, and which field can be the exception name? Why can you not yet say Alice actually sent the request?
3. Query Alice's access denials separately, then query authentication failures separately. Do not lump both groups into "bad login".
4. Read the audit endpoint twice as `auditor`. Explain why the success record count can rise even without calling business APIs.
5. Restart the application and query again. State why the old dataset disappeared and the consequence when investigating multi-day incidents.
6. Encountering HTTP 403 with no corresponding audit event: check the error source and event-publishing path before changing passwords or loosening permissions.

The tests succeed when the learner distinguishes **authentication outcome**, **authorization decision**, and **HTTP result**, and queries the right records within their data limits.
