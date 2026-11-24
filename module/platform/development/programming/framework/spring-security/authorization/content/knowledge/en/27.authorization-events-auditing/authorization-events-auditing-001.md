# AuthorizationEventPublisher and SpringAuthorizationEventPublisher

> Topic: **Spring Security – authorization**, group **Events and Auditing**. This lesson focuses on the API for publishing **authorization events** when `AuthorizationManager` makes a decision, how to enable `SpringAuthorizationEventPublisher`, how to listen to, test, and use event data within its proper boundaries. Examples run with **Java 17, Spring Boot 3.5.6, and Spring Security 6.5.x** (Servlet/Spring MVC). API differences in Spring Security 7.x are noted separately at the end of the lesson.

## 1. Why Are Authorization Events Needed?

The system has an endpoint `GET /api/management/report` that requires the `MANAGER` role. User `analyst` is logged in but only has `ROLE_ANALYST`: the request is denied. The HTTP client needs to receive **403 Forbidden**; the operations team also needs to know that **an authorization denial decision** occurred for monitoring or auditing. Those are two distinct responsibilities:

- **AuthorizationManager** checks permissions and produces an allow/deny result.
- **AuthorizationEventPublisher** is the contract that sends authorization results to the event mechanism. It does not grant permissions itself, does not check passwords, and does not decide the HTTP status.
- **SpringAuthorizationEventPublisher** is the built-in implementation that uses **Spring's `ApplicationEventPublisher`** to publish events to listeners such as `@EventListener`.
- **ExceptionTranslationFilter / AccessDeniedHandler / AuthenticationEntryPoint** handle the security error path and turn it into an appropriate HTTP response. Authorization events do not replace them.

When denial decisions are observable, the application can measure denials on a group of resources, detect misconfigured roles, attach a trace ID to a request, or send sanitized audit records to an external system.

**Note:** An `AuthorizationDeniedEvent` only states that *an authorization check* was denied. It **does not guarantee** that the client will see HTTP 403: an unauthenticated caller might receive a 401/redirect to a login page; conversely, an HTTP 403 caused by CSRF or another component might not emit a corresponding `AuthorizationDeniedEvent`.

## 2. Distinguishing the Two Core APIs

### 2.1. `AuthorizationEventPublisher` — Event Publishing Contract

Package: `org.springframework.security.authorization`. The meaning of the event publishing method in the modern API:

```java
// Conceptual signature of the AuthorizationResult API.
// In Spring Security 6.5, this is the default overload; the older API
// taking AuthorizationDecision still exists but is deprecated.
<T> void publishAuthorizationEvent(
    Supplier<Authentication> authentication,
    T object,
    AuthorizationResult result
);
```

Three inputs:

| Input | Practical meaning | Points to note |
|---|---|---|
| `Supplier<Authentication> authentication` | How to obtain caller information when needed | The supplier can defer retrieving the SecurityContext. Do not retain the supplier for use after the request or on another thread |
| `T object` | The object being protected | In request authorization this is usually `HttpServletRequest`; in method security it can be a method invocation. Do not assume every event is HTTP |
| `AuthorizationResult result` | Check result, has `isGranted()` | `true`: granted; `false`: denied. If there is no decision (`null`/abstain in a supporting branch), a denial event must not be published by default |

`AuthorizationEventPublisher` is an **extension point** to change *how events are published or filtered*, while the policy remains in `AuthorizationManager`. The contract does not promise durable event delivery, global ordering, or exactly-once delivery to an external system.

**Version note:** Spring Security **6.5** still has the legacy abstract signature accepting `AuthorizationDecision` and a default overload accepting `AuthorizationResult`; the legacy signature is marked deprecated. Spring Security **7.x** centers on the signature accepting `AuthorizationResult`. When implementing the interface yourself, you must check the exact signature on the classpath version; do not copy a 7.x implementation verbatim into 6.5.

### 2.2. `SpringAuthorizationEventPublisher` — Adapter to Spring Events

This is a `final` implementation that receives Spring's `ApplicationEventPublisher` through its constructor. By default, it publishes **`AuthorizationDeniedEvent`** when a result is denied, while **not publishing `AuthorizationGrantedEvent` for every success**, because the volume of successful events can be very high. This is intentional behavior to avoid flooding logs or audit systems.

Event objects belong to the package `org.springframework.security.authorization.event`:

- `AuthorizationDeniedEvent<T>`: a denied decision.
- `AuthorizationGrantedEvent<T>`: an allowed decision, only seen if an appropriate publisher/configuration publishes it.
- Both expose details via `getAuthentication()` (returns a supplier), `getObject()`, and `getAuthorizationResult()`. With an `AuthorizationResult`, `isGranted()` represents the decision.

**Easily confused class names:** `AuthenticationEventPublisher` and `DefaultAuthenticationEventPublisher` relate to **login/authentication success or failure**. They are completely different from `AuthorizationEventPublisher` and `SpringAuthorizationEventPublisher`, which relate to **access permissions**.

## 3. Event Flow in Spring Security Servlet

```text
Request GET /api/management/report
       |
       v
SecurityFilterChain
       |
       +--> Authentication filter: sets up the appropriate Authentication
       |
       +--> ExceptionTranslationFilter
                 |
                 v
            AuthorizationFilter
                 |
                 +--> AuthorizationManager checks ROLE_MANAGER
                 |         |
                 |         +--> AuthorizationResult (granted=false)
                 |
                 +--> AuthorizationEventPublisher
                 |         |
                 |         +--> SpringAuthorizationEventPublisher
                 |                   |
                 |                   +--> ApplicationEventPublisher
                 |                            |
                 |                            +--> @EventListener receives AuthorizationDeniedEvent
                 |
                 +--> throws AccessDeniedException
                               |
                               v
                         ExceptionTranslationFilter
                               |
                               +--> AccessDeniedHandler (authenticated) --> 403
                               +--> AuthenticationEntryPoint (authentication required) --> 401/redirect
```

There are several important details:

1. `AuthorizationFilter` uses the `AuthorizationManager` from `authorizeHttpRequests`. When denied, it can **publish the event and then throw an exception**, so a listener receiving the event does not mean the request has finished.
2. `ExceptionTranslationFilter` responds over HTTP based on authentication state; **the event publisher does not choose 401 or 403**.
3. Events are usually delivered to listeners on the same thread when using the default synchronous `ApplicationEventMulticaster`. If the application configures asynchronous multicasting, timing and SecurityContext may differ.
4. A single request can trigger **multiple checks** (request, method, `ERROR`/`FORWARD` dispatches), so the number of events does not necessarily equal the number of HTTP requests.
5. Not every security mechanism or custom code publishes through `AuthorizationEventPublisher`. For example, if a custom filter calls `sendError(403)` directly, the publisher's listener will not automatically know about it.

## 4. Runnable Example: Receiving an Event When ROLE_MANAGER Is Missing

We will build a small API with two in-memory accounts for easy testing. HTTP Basic and `{noop}` in this example are for learning only; real systems must use encoded password storage, proper identity management, and transport over HTTPS.

### 4.1. Project Structure

```text
authorization-events-demo/
├── pom.xml
├── src/main/java/com/example/authzevents/
│   ├── AuthorizationEventsApplication.java
│   ├── SecurityConfig.java
│   ├── ReportController.java
│   └── AuthorizationAuditListener.java
└── src/test/java/com/example/authzevents/
    └── AuthorizationEventsTest.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>authorization-events-demo</artifactId>
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

Starter Web provides Spring MVC and logging; Starter Security provides Spring Security; the two `test` dependencies provide JUnit/MockMvc and Spring Security test support.

### 4.2. Entry Point

`src/main/java/com/example/authzevents/AuthorizationEventsApplication.java`:

```java
package com.example.authzevents;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationEventsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationEventsApplication.class, args);
    }
}
```

### 4.3. Event Publisher Bean and Access Rules

`src/main/java/com/example/authzevents/SecurityConfig.java`:

```java
package com.example.authzevents;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher springEvents) {
        return new SpringAuthorizationEventPublisher(springEvents);
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/management/**").hasRole("MANAGER")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        var analyst = User.withUsername("analyst")
            .password("{noop}analyst123")
            .roles("ANALYST")
            .build();
        var manager = User.withUsername("manager")
            .password("{noop}manager123")
            .roles("MANAGER")
            .build();
        return new InMemoryUserDetailsManager(analyst, manager);
    }
}
```

**Why is only an `AuthorizationEventPublisher` bean needed?** In modern Spring Security configurations using `AuthorizationManager`, Spring Security can pick up the publisher bean from the application context and wire it into the corresponding authorization components. When a decision is denied and that component publishes events, `SpringAuthorizationEventPublisher` forwards it to the Spring event infrastructure. There is no need to invoke the publisher manually from a controller.

- `hasRole("MANAGER")` looks for `ROLE_MANAGER` using the default prefix.
- `User.roles("MANAGER")` creates the matching authority; `analyst` only has `ROLE_ANALYST`.
- `.anyRequest().authenticated()` requires authentication for other paths.
- The default HTTP 403 handler still operates. Publishing an event does not change the response status code.

### 4.4. Controller with Protected Resources

`src/main/java/com/example/authzevents/ReportController.java`:

```java
package com.example.authzevents;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    @GetMapping("/api/management/report")
    public Map<String, String> managementReport() {
        return Map.of("report", "ready");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile() {
        return Map.of("profile", "visible");
    }
}
```

### 4.5. Listener Receiving Denied Decisions

`src/main/java/com/example/authzevents/AuthorizationAuditListener.java`:

```java
package com.example.authzevents;

import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class AuthorizationAuditListener {
    private static final Logger log =
            LoggerFactory.getLogger(AuthorizationAuditListener.class);

    @EventListener
    public void onAuthorizationDenied(AuthorizationDeniedEvent<?> event) {
        Object securedObject = event.getObject();
        String target;

        if (securedObject instanceof HttpServletRequest request) {
            target = request.getMethod() + " " + request.getRequestURI();
        } else if (securedObject != null) {
            target = securedObject.getClass().getSimpleName();
        } else {
            target = "unknown";
        }

        Authentication current =
                SecurityContextHolder.getContext().getAuthentication();
        String actor = current == null ? "unknown" : current.getName();

        log.warn("authorization_denied actor={} target={} granted={}",
                actor, target, event.getAuthorizationResult().isGranted());
    }
}
```

In a regular request branch, the listener sees that the protected object can be an `HttpServletRequest`; in method security or another extension, the type of `event.getObject()` can differ. Therefore, the code **checks the type before using it**. Using `SecurityContextHolder` inside a synchronous listener to obtain the actor from the current context is a choice for this example, not a guarantee that the SecurityContext will be present in every type of asynchronous listener.

A log line may have a message portion similar to the following (timestamp, thread, and logger prefix depend on logging configuration):

```text
authorization_denied actor=analyst target=GET /api/management/report granted=false
```

Note that `granted=false` is read from `AuthorizationResult`. That field could be omitted since the event is already an `AuthorizationDeniedEvent`, but keeping it in the example helps learners recognize the relationship between the event type and the result. In production, replace the demo log with an audit event that has a clear schema and strip sensitive data.

**Do not use `event.getObject().toString()` to log the entire object**: payloads, paths, and context may contain personal information, internal IDs, or tokens. Even `getRequestURI()` needs rules to mask/hash identifier parameters according to your system's security requirements. Do not put `Authentication.getCredentials()`, the `Authorization` header, or stack traces into audit logs.

## 5. Running the Application and Observing Behavior

In the project directory, JDK 17+ and Maven are required:

```bash
mvn spring-boot:run
```

Test from another terminal:

```bash
# A. Authenticated, missing ROLE_MANAGER
curl -i -u analyst:analyst123 http://localhost:8080/api/management/report

# B. Authenticated, has ROLE_MANAGER
curl -i -u manager:manager123 http://localhost:8080/api/management/report

# C. Unauthenticated
curl -i http://localhost:8080/api/management/report

# D. Analyst can still read profile
curl -i -u analyst:analyst123 http://localhost:8080/api/profile
```

On Windows PowerShell, you can use `curl.exe` to invoke the real curl binary. Expected statuses:

| Case | HTTP status | Event expectation |
|---|---|---|
| A: `analyst` accesses report | **403** | `AuthorizationDeniedEvent` for the denied permission decision |
| B: `manager` accesses report | **200** | `SpringAuthorizationEventPublisher` by default does **not** publish `AuthorizationGrantedEvent` |
| C: No authentication credentials | **401** with HTTP Basic | Do not equate 401 with an `AuthorizationDeniedEvent`. Depending on the evaluation branch, missing authentication may throw an error before an authorization result is published |
| D: `analyst` accesses profile | **200** | No denial event from this rule |

The HTTP `200` in case B has a JSON body shaped like `{"report":"ready"}`. Each HTTP Basic request can involve additional authentication components. Observe **authorization events separately**, without assuming every security log comes from this publisher.

## 6. Testing: Events Are Actually Published

A unit test that manually calls `ApplicationEventPublisher.publishEvent(new AuthorizationDeniedEvent(...))` **only tests the listener**; it does not prove that Spring Security itself publishes an event when a rule denies access. Integration testing is more appropriate: use `MockMvc` going through the security filters, and Spring Test's `@RecordApplicationEvents` to inspect the events emitted during each test.

`src/test/java/com/example/authzevents/AuthorizationEventsTest.java`:

```java
package com.example.authzevents;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
class AuthorizationEventsTest {
    @Autowired
    MockMvc mvc;

    @Test
    void deniedRequestProducesAuthorizationEvent(ApplicationEvents events)
            throws Exception {
        mvc.perform(get("/api/management/report")
                .with(user("analyst").roles("ANALYST")))
            .andExpect(status().isForbidden());

        assertThat(events.stream(AuthorizationDeniedEvent.class)
                .anyMatch(event ->
                    !event.getAuthorizationResult().isGranted()))
            .isTrue();
    }

    @Test
    void allowedRequestDoesNotProduceDeniedEvent(ApplicationEvents events)
            throws Exception {
        mvc.perform(get("/api/management/report")
                .with(user("manager").roles("MANAGER")))
            .andExpect(status().isOk());

        assertThat(events.stream(AuthorizationDeniedEvent.class).count())
            .isZero();
    }

    @Test
    void unauthenticatedRequestIsChallenged() throws Exception {
        mvc.perform(get("/api/management/report"))
            .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
mvn test
```

Three test cases:

1. For analyst, the request gets 403 **and** there is at least one denial event. Avoid asserting strictly "exactly 1 event" because additional interceptors or dispatchers can trigger multiple checks as configuration grows.
2. For manager, the request is allowed and emits no **denial** event in this simple test. This is different from asserting that a **granted** event is always emitted.
3. For anonymous, HTTP Basic challenges for authentication and returns 401; the test intentionally does not assert an event count because the details depend on the authentication/authorization path.

`with(user(...))` creates a mock authentication for the test request and does not verify a real password. The `curl -u` command in the previous section tests the HTTP Basic path through `UserDetailsService`. `@RecordApplicationEvents` records events per test method; there is no need to store events in a static list that can easily leak state between test cases.

## 7. Choosing the Right Hook for Auditing

Three mechanisms are often mentioned together, but they are not interchangeable:

| Need | Hook to consider | Limitation |
|---|---|---|
| Record authorization rule denials at `AuthorizationManager` | `AuthorizationEventPublisher` + `AuthorizationDeniedEvent` | Only covers decision sources that actually go through the publisher |
| Return JSON/HTML 403 to the client | `AccessDeniedHandler` | Part of **response handling**, not the authorization channel or a general-purpose audit source |
| Track login successes/failures | `AuthenticationEventPublisher` + authentication events | Relates to authentication, not whether the caller has permission for specific resources |
| Record completed business actions (e.g. approving an order) | Business/domain event or transactional outbox | Does not replace the permission decision before executing the action |

For example, with `@EnableMethodSecurity` and `@PreAuthorize`, a service call can also produce an `AuthorizationDeniedEvent` when the interceptor is configured with the publisher. The event object may be a method invocation, **not `HttpServletRequest`**. Do not apply HTTP assumptions to every `event.getObject()`; verify each real authorization control point in the application individually.

In systems with multiple `SecurityFilterChain` beans, endpoints may use different chains. A recorded event must be tied to the **actual rule/check source**, rather than inferred solely from the URL when multiple protection layers exist. For authorization handled by custom business code outside Spring Security, you must emit an appropriate domain audit explicitly; publishing `AuthorizationDeniedEvent` arbitrarily can make audit data misleading.

## 8. When Should `AuthorizationGrantedEvent` Be Published?

Every allowed request or method call can generate a huge number of successes. For that reason, `SpringAuthorizationEventPublisher` **only publishes denial events by default**. In high-traffic systems, enabling event publishing for every success can:

- increase CPU, I/O, memory, and storage overhead;
- flood the monitoring pipeline, making risky events hard to distinguish;
- expose metadata of successful accesses if logging is not tightly controlled.

Only select allowed decisions that **need a dedicated trail** (such as accessing sensitive administrative features), or perform controlled sampling. You still need to determine which audits must be durable and provide an appropriate delivery mechanism.

### 8.1. Differences Between Spring Security 6.5 and 7.x

- In **6.5.x**, `SpringAuthorizationEventPublisher` does not provide the `setShouldPublishResult(...)` setter. If selective granted events are needed, you need a custom publisher compatible with the 6.5 API or separate instrumentation, and you must thoroughly test the `AuthorizationDecision`/`AuthorizationResult` overloads.
- In **7.x**, `SpringAuthorizationEventPublisher` provides `setShouldPublishResult(Predicate<AuthorizationResult>)`. You can supply a predicate to choose which results to publish. Do not copy this setter into source code targeting Spring Security 6.5.

Example **for Spring Security 7.x only**, placed in a `@Configuration` class and replacing the default publisher bean from section 4.3 (method-only snippet to avoid mixing into the 6.5 project):

```java
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher springEvents) {
    var publisher = new SpringAuthorizationEventPublisher(springEvents);
    publisher.setShouldPublishResult(result -> {
        if (!result.isGranted()) {
            return true; // Keep all denied results
        }
        if (result instanceof AuthorityAuthorizationDecision authorityResult) {
            return authorityResult.getAuthorities().stream()
                    .anyMatch(a -> "ROLE_MANAGER".equals(a.getAuthority()));
        }
        return false; // Do not publish other granted results
    });
    return publisher;
}
```

The types used in the 7.x snippet reside in `org.springframework.security.authorization`: `AuthorizationEventPublisher`, `SpringAuthorizationEventPublisher`, and `AuthorityAuthorizationDecision`; `ApplicationEventPublisher` is in `org.springframework.context`, and `@Bean` is in `org.springframework.context.annotation`. The snippet above is intentionally just a method fragment to illustrate the 7.x difference; add the corresponding imports and verify the classpath version when implementing.

Meaning of the predicate: always keep denials, and additionally publish certain grants whose result object is an `AuthorityAuthorizationDecision` with the observed authority. Depending on the actual configuration, an `AuthorizationManager` may return a different `AuthorizationResult` type, so the predicate does not guarantee capturing every access to "administrative" features if it relies solely on the result/authority type. Write tests proving the exact decision type produced by critical endpoints and measure event volume before enabling in production.

## 9. Designing Safe and Operable Auditing

### 9.1. Recommended Schema

If forwarding data to a dedicated audit system, an event can be transformed into a minimal record:

```json
{
  "eventType": "AUTHORIZATION_DENIED",
  "occurredAt": "2026-11-05T11:00:00Z",
  "actorId": "user-42",
  "resourceType": "MANAGEMENT_REPORT",
  "action": "READ",
  "result": "DENIED",
  "requestId": "req-abc123",
  "source": "SPRING_SECURITY_AUTHORIZATION"
}
```

This is an **illustrative schema**, not JSON emitted by Spring Security itself and not the exact output of the example in section 4. In production, `actorId`, `resourceType`, `action`, and `requestId` values must come from verified context; do not infer permissions from unchecked URL strings.

### 9.2. Key Design Decisions to Finalize

1. **Define event types:** distinguish authentication, authorization, CSRF, and business audits. Counting `AuthorizationDeniedEvent` is not equivalent to counting every HTTP 403.
2. **Minimize data:** store only permitted account identifiers, resource/operation codes, outcome, timestamp, and trace/correlation ID. Do not record credentials, cookies, access tokens, response bodies, or the raw protected object.
3. **Reliability:** an in-process Spring application event is not a durable audit trail. If persistence is required before confirming a business operation, design appropriate durable storage (such as a guaranteed queue or transactional outbox depending on requirements).
4. **Performance impact:** slow synchronous listeners can slow down requests. A listener that throws a runtime exception can also fail the request. Establish clear failure-handling boundaries, batch/queue/timeout limits, and backpressure policies.
5. **Asynchrony:** `Supplier<Authentication>` and `HttpServletRequest` depend on call-time context. When sending audits through a queue, **capture sanitized primitive values on the original processing thread**; do not pass the raw supplier, request, or SecurityContext to another thread.
6. **Ordering and duplicates:** multiple authorization layers or multiple dispatches can emit multiple events. Use correlation keys and check types to distinguish them; do not assume exactly-once semantics.
7. **Audit access control:** logs/events contain security information; restrict read permissions, retention periods, data classification, and export controls.

## 10. Common Troubleshooting

| Symptom | Common cause | How to verify |
|---|---|---|
| Client receives 403 but listener does not run | Publisher bean not created, endpoint hits a different chain, CSRF blocked the request, or a component returned 403 directly | Check `AuthorizationEventPublisher` bean; test GET without role using `@RecordApplicationEvents`; distinguish the 403 source |
| Client receives 401 and there is no event | Authentication failed or the authentication entry point was invoked before an authorization decision | Test with a user who **is logged in** but lacks permission |
| No `AuthorizationGrantedEvent` seen | `SpringAuthorizationEventPublisher` ignores grants by default | This is the default; consider selective grants according to version |
| Compile error on `setShouldPublishResult` | Using Spring Security 6.5 or earlier | The setter exists in 7.x; use a version-appropriate implementation |
| Wrong/null actor read in async listener | SecurityContext/request changed or cleared after the request | Extract actor and metadata safely in a synchronous listener before queueing |
| More events than requests | Multiple permission checks, method security, or `ERROR/FORWARD` dispatches | Attach request ID, check type, and compare each branch |
| Only `@ControllerAdvice` used and HTTP filter errors missed | Exceptions from security filters do not necessarily pass through MVC exception resolvers | Use `ExceptionTranslationFilter`/`AccessDeniedHandler` for HTTP; listeners for auditing |
| Auditing slows down API or causes 500s | Synchronous listener is slow or throws an exception | Limit listener work, test sink failures, use queues and fallbacks |
| Events published manually even without a real check | Creating synthetic audits by publishing events untied from `AuthorizationManager` | Emit a separate domain event or publish from the real permission control point |

## 11. Practice Checklist

- [ ] Can explain the roles of `AuthorizationManager`, `AuthorizationEventPublisher`, and `SpringAuthorizationEventPublisher`.
- [ ] Confirmed the `AuthorizationEventPublisher` bean is properly registered in the application context.
- [ ] With analyst lacking `ROLE_MANAGER`, verified HTTP **403** *and* `AuthorizationDeniedEvent`.
- [ ] With manager having permission, verified HTTP **200**; understood why grants are not published by default.
- [ ] Do not confuse `AuthorizationDeniedEvent` with `AuthenticationFailureEvent` and `AccessDeniedHandler`.
- [ ] Extract audit metadata safely; do not store `HttpServletRequest` or `Supplier<Authentication>` directly for async processing.
- [ ] Check 6.5/7.x API differences before writing a custom publisher or enabling grants.
- [ ] Have tests covering the event source, data protection, and listener impact on failures.

## Official References

- [Spring Security – Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html) – how to create `SpringAuthorizationEventPublisher` and listen for events.
- [Spring Security 6.5 – `AuthorizationEventPublisher` API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationEventPublisher.html) – legacy signature and `AuthorizationResult` overload.
- [Spring Security 6.5 – `SpringAuthorizationEventPublisher` API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/SpringAuthorizationEventPublisher.html) – default implementation publishing denials only.
- [Spring Security 7.x – `SpringAuthorizationEventPublisher` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/SpringAuthorizationEventPublisher.html) – `setShouldPublishResult(...)` setter.
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) – `AuthorizationFilter`, `AuthorizationManager`, and error flow.
- [Spring Framework – Application Events in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html) – `@RecordApplicationEvents` and `ApplicationEvents`.
