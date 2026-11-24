# AuthorizationGrantedEvent and Controlling Successful Event Volume

> **Topic:** Spring Security – authorization. **Knowledge group:** Events and Auditing. This lesson focuses on `AuthorizationGrantedEvent`, why you should not publish every successful authorization event, how to select important events, and how to test event volume. The main examples use **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Servlet API**; API notes for newer versions appear at the end of the lesson.

## 1. Why Do You Need to Know About Successful Authorization Events?

A request to `GET /api/admin/report` can pass through multiple steps: authenticating the caller, checking roles, checking method permissions, querying data, and building the HTTP response. At the permission check step, Spring Security can arrive at a **decision**: allowed (`granted`), denied (`denied`), or the evaluation mechanism does not produce a definite decision (`null` in some APIs).

`AuthorizationGrantedEvent` represents **an authorization check that yielded an allowed result**. It does **not** confirm that the entire business operation completed, does not confirm that a DB transaction committed, and is not a "login succeeded" event.

You will learn how to:

1. Distinguish `AuthorizationGrantedEvent`, `AuthorizationDeniedEvent`, `AuthenticationSuccessEvent`, and business auditing.
2. Know when Spring Security can publish events, what object is inside the event, and why **successes are not published by default**.
3. Design a **purposeful** collection policy: keep important grant events, suppress ordinary grants, and maintain visibility into denial events.
4. Implement a selective `AuthorizationEventPublisher`, listen with `@EventListener`, and test with `MockMvc`/`ApplicationEvents`.
5. Manage event volume, cardinality, processing overhead, data security, and audit boundaries.

## 2. Event Types and Scope of Meaning

| Event | When is it meaningful? | Can it replace other events? |
|---|---|---|
| `AuthenticationSuccessEvent` | Credentials were successfully authenticated by the corresponding authentication mechanism | Does not state that the user is allowed to access a specific resource |
| `AuthenticationFailure...Event` | Authentication failed, depending on mechanism and publisher | Does not necessarily generate an `AuthorizationDeniedEvent` |
| `AuthorizationGrantedEvent<T>` | An authorization evaluation produced a **granted** result, when the publisher **chooses to publish** | Does not prove the business operation succeeded |
| `AuthorizationDeniedEvent<T>` | An authorization evaluation produced a **denied** result, when the publisher publishes | Not every HTTP 401/403 generates exactly one event |
| **Business audit** defined by the application | For example, a transfer order was recorded/committed, or a document was shared | Must be emitted at the appropriate business boundary, potentially after commit |

Example: an employee with `ROLE_ADMIN` accesses `/api/admin/report`. `AuthorizationGrantedEvent` records that the authorization rule allowed the request to proceed. The controller can still return 500 if a DB connection fails. Treating the grant as "report was successfully read" makes the audit history inaccurate.

### Servlet Request Flow

```text
HTTP request
    │
    ▼
Authentication filter / SecurityContext
    │
    ▼
AuthorizationFilter
    │  └─ AuthorizationManager evaluates:
    │       ├─ DENIED  → AuthorizationEventPublisher
    │       │             → AuthorizationDeniedEvent (if published)
    │       │             → AccessDeniedException → handle denial
    │       └─ GRANTED → AuthorizationEventPublisher
    │                     → AuthorizationGrantedEvent
    │                       ONLY WHEN the publisher explicitly allows it
    ▼
Controller → Service → Database
    │
    └─ business outcome and separate business audit
```

`AuthorizationFilter` uses `Supplier<Authentication>` and `HttpServletRequest` to evaluate rules in `authorizeHttpRequests`. With method security such as `@PreAuthorize`, the checked object may be a `MethodInvocation`, not an `HttpServletRequest`. Therefore, code reading `event.getObject()` must check the type rather than casting blindly.

**One HTTP request can lead to multiple permission evaluations:** at the URL, at a service method, during forward/error dispatches, or when code calls a protected method multiple times. The number of authorization events does not necessarily equal the number of requests or user actions.

## 3. Default Behavior: Why Don't You See AuthorizationGrantedEvent?

To receive authorization events via Spring Application Events, the application needs a configured `AuthorizationEventPublisher`. Spring Security provides `SpringAuthorizationEventPublisher` to forward authorization results to Spring events.

An important fact in version 6.x: **`SpringAuthorizationEventPublisher` publishes denied events and ignores granted events by default.** It does not automatically enable collecting every success, because a normal application can check permissions on nearly every request and many methods.

Example of configuring the default publisher to track denials:

```java
// Short configuration example in @Configuration, Spring Security 6.x.
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher applicationEventPublisher) {
    return new SpringAuthorizationEventPublisher(applicationEventPublisher);
}
```

This bean **does not yet** cause `@EventListener(AuthorizationGrantedEvent)` to receive successful checks. You must actively build a publisher that knows when to publish grants, or use the event-filtering API corresponding to the exact version you are running.

### Do Not Confuse Three Layers

- **Authorization decision:** for example, `hasRole("ADMIN")` returns granted. This decision happens whether auditing is enabled or not.
- **Authorization event publication:** the publisher decides whether to create an event or skip it. Skipping **does not** turn an allowed request into a denied one.
- **Event consumption:** `@EventListener`, metrics, or an audit sink consumes published events. Listeners should not be used to re-decide permissions.

You cannot "turn on `@EventListener`" to catch an event the publisher never created. Conversely, creating every event and filtering only in the listener still incurs object allocation, dispatch overhead, and invocation of other listeners.

## 4. Data Inside an AuthorizationGrantedEvent

In Spring Security 6.3, `AuthorizationGrantedEvent<T>` resides in package `org.springframework.security.authorization.event`. Its constructor takes:

```java
new AuthorizationGrantedEvent<>(
    Supplier<Authentication> authentication,
    T securedObject,
    AuthorizationDecision decision
);
```

Components to understand:

| Component | Meaning | Logging precautions |
|---|---|---|
| `getAuthentication()` | `Supplier<Authentication>` bound to the principal during the check | Extract only needed fields; do not serialize Authentication/token/credentials |
| `getObject()` | The object being checked: request or method invocation, depending on mechanism | May contain URIs with IDs, bodies, headers, or sensitive parameters |
| `getAuthorizationDecision()` | Authorization result in the 6.3 API; `isGranted()` must be `true` for a grant | Do not infer HTTP outcome or DB commit |
| Publication timing | At the authorization evaluation boundary | May occur before the controller executes |

`T` is the protected object type, not an ID or user type. You should not store `event.toString()`, dump the entire request, or send the raw event over a message broker. Some objects may hold references to the request and security context; extract a small audit DTO with a clear schema before handing off to asynchronous processing.

## 5. The Volume Problem: Even a "Cheap" Success Event Can Be Very Expensive

Suppose an API handles **2,000 requests/second**, averaging **two authorization checks/request**, and **99%** of results are allowed. If every success is published:

```text
2,000 × 2 × 0.99 = 3,960 grant events / second
3,960 × 86,400 = 342,144,000 grant events / day
```

This is an illustrative example to estimate scale, not a default Spring Security number. If each stored record takes about 1 KB after serialization, successes alone can generate **hundreds of GB/day** before replication, indexing, retention, and network traffic.

The impact is not just storage size:

- **CPU and allocation:** event instantiation, record construction, JSON serialization, and listener logic.
- **Request latency:** Spring `@EventListener` normally runs synchronously on the publishing thread; a slow listener can slow down the API.
- **Cardinality:** metrics tagged with `userId`, document IDs, or URLs with dynamic parameters can create a massive number of time series.
- **Queues and downstream:** bursts can fill queues, increase retries, and congest the logging pipeline.
- **Signal-to-noise ratio:** millions of "ordinary GET allowed" lines can bury the few privileged events that truly need investigation.

**The right measure is an event's value relative to its cost and risk**, not maximizing event counts.

## 6. Practical Collection Policy

A policy can be divided into three groups:

| Group | Example | Strategy |
|---|---|---|
| **Security-relevant denials** | Rules blocking access to documents/endpoints | Typically retain all `AuthorizationDeniedEvent`s if the system needs monitoring; handle repeats/bursts in the pipeline without losing signal |
| **Privileged/sensitive grants** | Accessing admin reports, approving permissions, financial operations | **Allowlist**, selectively record in full with a retention policy |
| **High-frequency ordinary grants** | Viewing profile pages, reading catalogs, routine read requests | Skip, collect aggregated metrics, or use small **sampling** if visibility is needed |

Decide upfront whether an event is **mandatory audit evidence**, **monitoring telemetry**, or a **debug signal**. For mandatory audits, sampling or silent dropping is inappropriate. For telemetry, 1% sampling may suffice to observe trends; sampled output cannot serve as a complete list of everyone who accessed a resource.

### Five Publisher Design Principles

1. **Do not alter permission decisions.** The publisher only observes; it does not grant or manage user permissions.
2. **Filter before publishing.** Only construct `AuthorizationGrantedEvent` when an observed rule matches.
3. **Preserve the denial path.** When writing a custom publisher, continue delegating denials to `SpringAuthorizationEventPublisher` or a tested equivalent implementation.
4. **Choose stable keys.** Classify by policy/route template (e.g., `admin-report`), avoiding live URLs containing IDs.
5. **Distinguish event sources.** The publisher should only filter request-level checks when the object is `HttpServletRequest`. If method-security monitoring is needed, build a separate policy for `MethodInvocation`.

## 7. Runnable Example: Publishing Grants Only for Admin Endpoints

The following example sets up a small web app with two endpoints. Every authenticated request is evaluated by Spring Security, but **only granted decisions on `GET /api/admin/report`** are published as `AuthorizationGrantedEvent`. Denied decisions continue to be delegated for handling.

### 7.1. Source Structure

```text
settings.gradle
build.gradle
src/main/java/demo/AuthorizationEventDemoApplication.java
src/main/java/demo/SecurityConfiguration.java
src/main/java/demo/SelectiveAuthorizationEventPublisher.java
src/main/java/demo/DemoController.java
src/main/java/demo/GrantLogListener.java
src/test/java/demo/AuthorizationEventDemoTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'authorization-event-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Versions are pinned to demonstrate a specific API in this example; real projects should update to supported patches and check Spring Boot/Spring Security compatibility.

`src/main/java/demo/AuthorizationEventDemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationEventDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationEventDemoApplication.class, args);
    }
}
```

`src/main/java/demo/SecurityConfiguration.java`:

```java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/admin/report").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET,
                    "/api/profile").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher springEvents) {
        return new SelectiveAuthorizationEventPublisher(springEvents);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("admin")
                .password("{noop}adminpass")
                .roles("ADMIN")
                .build(),
            User.withUsername("reader")
                .password("{noop}readerpass")
                .roles("USER")
                .build()
        );
    }
}
```

`{noop}` is only suitable for in-memory demos: never store plaintext passwords in real applications. HTTP Basic in production systems must use HTTPS.

`src/main/java/demo/SelectiveAuthorizationEventPublisher.java`:

```java
package demo;

import java.util.function.Supplier;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.authorization.event.AuthorizationGrantedEvent;
import org.springframework.security.core.Authentication;

public final class SelectiveAuthorizationEventPublisher
        implements AuthorizationEventPublisher {

    private final ApplicationEventPublisher events;
    private final AuthorizationEventPublisher deniedDelegate;

    public SelectiveAuthorizationEventPublisher(
            ApplicationEventPublisher events) {
        this.events = events;
        this.deniedDelegate = new SpringAuthorizationEventPublisher(events);
    }

    @Override
    public <T> void publishAuthorizationEvent(
            Supplier<Authentication> authentication,
            T securedObject,
            AuthorizationDecision decision) {

        // Some AuthorizationManagers may not return a decision.
        if (decision == null) {
            return;
        }

        if (!decision.isGranted()) {
            // Never drop the denied publishing path when customizing.
            deniedDelegate.publishAuthorizationEvent(
                authentication, securedObject, decision);
            return;
        }

        // This example tracks Servlet request-level checks only.
        if (!(securedObject instanceof HttpServletRequest request)) {
            return;
        }

        // Do not emit extra events for forward/error dispatches.
        if (request.getDispatcherType() != DispatcherType.REQUEST) {
            return;
        }

        boolean criticalGrant = "GET".equals(request.getMethod())
            && "/api/admin/report".equals(request.getServletPath());

        if (criticalGrant) {
            events.publishEvent(new AuthorizationGrantedEvent<>(
                authentication, securedObject, decision));
        }
    }
}
```

Explanation of decisions:

- **Denied:** delegates handling to Spring Security's default behavior. Does not force denied to granted, and does not change HTTP 403.
- **Granted for ordinary routes:** returns immediately inside the publisher without creating `AuthorizationGrantedEvent`.
- **Granted for admin routes:** publishes a Spring event for listeners to process.
- **Dispatcher type:** cares only about `REQUEST`, avoiding duplicate records due to re-dispatching.
- **Object type:** in method security, the object is typically not `HttpServletRequest`; this sample intentionally does not publish method-level grants. A successful decision on a route does not guarantee that downstream methods are allowed.

The `getServletPath()` condition fits the two fixed routes in the demo. Real applications with context paths, special servlet mappings, versioned APIs, or dynamic routes should identify a **normalized policy ID/template** in the authorization layer rather than comparing raw URIs or logging sensitive IDs.

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/admin/report")
    String report() {
        return "report-ok";
    }

    @GetMapping("/api/profile")
    String profile() {
        return "profile-ok";
    }
}
```

`src/main/java/demo/GrantLogListener.java`:

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.event.AuthorizationGrantedEvent;
import org.springframework.stereotype.Component;

@Component
public class GrantLogListener {

    private static final Logger log =
        LoggerFactory.getLogger(GrantLogListener.class);

    @EventListener
    public void onGranted(AuthorizationGrantedEvent<?> event) {
        // Publisher has already restricted this to a sensitive route.
        // Do not serialize Authentication or HttpServletRequest.
        log.info("authorization_granted policy=admin-report");
    }
}
```

This listener only illustrates a safe, low-cost log entry. When writing real audits, add correlation IDs and timestamps according to your application's standard mechanism, but **never** log passwords, bearer tokens, cookies, request bodies, or the entire `event.getObject()`.

### 7.2. Running and Observing

In the directory with the Gradle wrapper (or using an appropriate Gradle installation), run:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. With Bash/curl:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:adminpass http://localhost:8080/api/admin/report

curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:readerpass http://localhost:8080/api/profile

curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:readerpass http://localhost:8080/api/admin/report

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/admin/report
```

**Expected** HTTP results, in exact order: `200`, `200`, `403`, `401`. After the first request, the logger is **expected** to contain `authorization_granted policy=admin-report`. The successful profile request produces no grant event due to the allowlist policy. Denied requests produce no grant event; the publisher continues forwarding the denied path to Spring.

These results are expectations for the example, not logs captured from a live run in this article.

### 7.3. Automated Tests with MockMvc and ApplicationEvents

`src/test/java/demo/AuthorizationEventDemoTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.authorization.event.AuthorizationGrantedEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
class AuthorizationEventDemoTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationEvents events;

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void privilegedGrantIsPublished() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isOk());

        assertThat(events.stream(AuthorizationGrantedEvent.class).count())
            .isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void ordinaryGrantIsFilteredBeforePublishing() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isOk());

        assertThat(events.stream(AuthorizationGrantedEvent.class).count())
            .isZero();
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void denialStillProducesDeniedEvent() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());

        assertThat(events.stream(AuthorizationDeniedEvent.class).count())
            .isGreaterThanOrEqualTo(1);
    }

    @Test
    void anonymousAdminRequestIsRejected() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isUnauthorized());
    }
}
```

Run `./gradlew test`. `@WithMockUser` creates a security context for the test and does not verify a real password; the event/status tests verify authorization and the publisher. If you need to test real authentication, add tests with `httpBasic(...)` or requests against a live server.

**Assumptions of the example:** there is only one `SecurityFilterChain`; there are no additional `@PreAuthorize`, custom filters, or unusual dispatches emitting multiple decisions; the handler and publisher share the same Spring ApplicationContext. In real applications, filter events by secured object/policy type and verify counts when multiple chains or method security exist.

## 8. If You Want to Observe 1% of Ordinary Grants

A system may need a sample of ordinary decisions. In that case, extend the **granted branch** of the publisher before `publishEvent`:

```java
// Illustrative snippet inside publishAuthorizationEvent,
// after checking object is HttpServletRequest and DispatcherType.REQUEST.
boolean important = "GET".equals(request.getMethod())
    && "/api/admin/report".equals(request.getServletPath());

boolean sampledOrdinary = "GET".equals(request.getMethod())
    && "/api/profile".equals(request.getServletPath())
    && java.util.concurrent.ThreadLocalRandom.current()
        .nextInt(100) == 0; // Approximately 1% of decisions.

if (important || sampledOrdinary) {
    events.publishEvent(new AuthorizationGrantedEvent<>(
        authentication, securedObject, decision));
}
```

This snippet **replaces** the `criticalGrant` condition in the full example and does not run standalone. A 1% outcome is an expected probability, not a guarantee of exactly one event per 100 decisions. Tests for sampling should inject a selector controllable via seed/fake to avoid flaky tests; still keep separate tests proving critical grants are always published and denials are not filtered out.

### Sampling vs. Rate Limiting

- **Probability sampling (1%)**: reduces the average rate, but a massive burst can still overwhelm sink capacity.
- **Rate limit/quota**: caps events/second for telemetry, which can drop information under load; overload behavior must be defined.
- **Bounded queue + backpressure**: controls memory and prevents blowups, with clear drop/flush/retry policies.
- **Aggregation**: replaces millions of detailed rows with counters grouped by policy/decision and time window.
- **Allowlist**: selects important decision types first, typically most useful for sensitive audits.

For events with mandatory retention requirements, you must have durable infrastructure and operational runbooks when the sink is unavailable; do not apply sampling just to cut costs and still claim complete auditing. Conversely, never force the API to wait on an optional analytics system on every request.

## 9. Counting Accurately: Metrics, Tracing, and Audits Are Not the Same

If you only have filtered grant events, a chart of "number of `AuthorizationGrantedEvent`s received" is **the number of events published**, not necessarily the true total of grants.

A sound observability design:

1. At the decision point, increment an **aggregated counter** with a bounded label set: `decision=granted|denied`, `policy=admin-report|profile|other`, `surface=request|method`. If a metric truly needs complete totals, count **before sampling** and know the scope of the checkpoints.
2. Emit **detailed grant events** only for selected policies. If sampling is used, attach `sample_rate` in metadata so the pipeline knows how to interpret it; do not extrapolate into per-user audits.
3. Attach trace/correlation IDs to link events to requests, while controlling retention and read permissions. Do not use trace IDs or user IDs as high-cardinality Prometheus/Micrometer labels.
4. Record a separate **business audit** for completed actions (e.g., changing document permissions after commit), using a transactional outbox or appropriate delivery guarantee; a filter-level grant event is not enough.
5. Track metrics for **filtered** events, **sent** events, events **dropped due to a full queue**, queue depth, and downstream errors. Use these metrics to tell whether "no events" means low traffic or a broken pipeline.

Example metric names with stable labels:

```text
security_authorization_decisions_total{surface="request",policy="admin-report",decision="granted"}
security_authorization_events_published_total{kind="granted",policy="admin-report"}
security_authorization_event_queue_dropped_total{kind="granted"}
```

These are **suggested metric schemas** for learning, not metric names automatically created by Spring Security. Declare actual metrics in your project's Micrometer/observability pipeline; in particular, never create metric series keyed by raw document ID, email, or URLs containing tokens.

## 10. Performance and Security Concerns in Listeners

### Synchronous or Asynchronous?

By default, Spring application events are usually dispatched synchronously. If a listener writes to a DB or makes HTTP calls to a SIEM directly inside `@EventListener`, successful requests can slow down or even fail if the listener throws an exception.

Do not treat `@Async` as a complete solution: using it requires enabling async processing, providing an executor with bounded threads/queues, understanding security context propagation, and designing failure handling. Forwarding the raw `AuthorizationGrantedEvent` to another thread is especially dangerous because the object may retain `HttpServletRequest` and `Supplier<Authentication>` tied to the request context.

A safer approach is to **extract a small DTO while the context is valid**—for example `timestamp, policyId, decision, correlationId, pseudonymized principalRef`—and put the DTO onto a bounded queue; heavy work runs outside the request path. Do not serialize security contexts or entities containing private data.

### When Is Full Recording Mandatory?

Actions such as granting admin roles, modifying ACLs, signing approvals, or exporting sensitive data usually require detailed **business** audits. In those cases:

- Define the **business milestone** that marks success: command accepted, transaction committed, or external side effect completed.
- Have clear delivery semantics: at-most-once, at-least-once, retry, deduplication.
- Satisfy retention, audit access control, encryption, and system compliance policies.
- `AuthorizationGrantedEvent` can serve as a secondary signal at the security layer, but **must not be treated as proof that a transaction completed**.

### Do Not Let Listeners Break the Authorization Flow

Publishers and observation listeners must be lightweight and resilient. If the log collector disconnects, failure policies must be decided ahead of time: optional telemetry can drop with metrics; mandatory audits require specific data durability designs. Do not silently swallow business errors, and never silently flip a request between allowed and denied because a secondary reporting system failed.

## 11. Grant Events Can "Multiply" Through Several Mechanisms

| Situation | Symptom | How to handle |
|---|---|---|
| Both URL authorization and `@PreAuthorize` check | One request has multiple granted results | Tag `surface`, choose appropriate observation points and policies; do not assume one request equals one event |
| FORWARD/ERROR dispatch | Additional evaluations may occur in `AuthorizationFilter` | Consider dispatcher type, security config, and actual dispatch paths |
| Using `permitAll()` | Requests can still pass through authorization evaluation points | Do not enable global grant events just to count HTTP requests |
| Batch invoking thousands of secured methods | Method-level events grow with call count | Narrow scope, aggregate, or audit at the batch boundary |
| API running across multiple nodes/pods | Each node counts and samples independently | Aggregate via centralized metrics; keep policies consistent across versions |
| One request retried multiple times | Same user may repeat permission checks | Use correlation and idempotency keys if business reconciliation is required |

Important reality check: **"grant event count" is the number of permission decisions selected for event emission**, not "number of users", "number of HTTP 200s", or "number of completed operations".

## 12. API Compatibility Across Versions

The `SelectiveAuthorizationEventPublisher` example above uses the **Spring Security 6.3.x** interface, where the main method is:

```java
<T> void publishAuthorizationEvent(
    Supplier<Authentication> authentication,
    T securedObject,
    AuthorizationDecision decision);
```

In **Spring Security 6.4–6.5**, the `AuthorizationResult` API appears alongside `AuthorizationDecision`. Some overloads may be marked deprecated; when upgrading, check the exact Javadoc of the running version before changing signatures.

In **Spring Security 7.x**, `SpringAuthorizationEventPublisher` has an API to configure a predicate selecting which results are published (such as `setShouldPublishResult` in 7.0/7.1 releases). When using that version, you can configure the predicate instead of writing a custom publisher. Do not copy 7.x APIs into a 6.3 project because it will not compile. Likewise, method-level and request-level examples must use the exact overloads/event types of your version.

**What stays constant conceptually:** do not publish every grant by default; collect only results worth observing, preserve the denial path, bound overhead, protect sensitive data, and test the actual behavior.

## 13. Common Mistakes

1. **Assuming every 200 produces a grant event.** Wrong: HTTP response, authorization decision, and event publication are three separate layers.
2. **Creating an `@EventListener` bean and seeing no grants.** Missing an explicit publisher for successes; the default publisher only produces denials.
3. **Custom publisher handling only granted results.** Accidentally drops `AuthorizationDeniedEvent` and reduces visibility into unauthorized access.
4. **Filtering in the listener instead of the publisher.** Events are still created, wasting CPU and potentially reaching other listeners/sinks.
5. **Logging raw principals, tokens, or URLs.** Easily leaks PII and secrets, inflates cardinality, and creates risk when logs are shared.
6. **Enabling events for every `@PreAuthorize` check.** Generates far more records than HTTP requests.
7. **Using sampling for mandatory audits.** Leaves incomplete evidence; makes per-user investigations difficult.
8. **Inferring a successful business action from granted.** Controllers or transactions can still fail.
9. **Calling logging systems synchronously without bounds from a listener.** Downstream issues raise API latency.
10. **Writing tests that only check status 200/403.** Fails to catch new event policies that accidentally collect every success or drop denials.

## 14. Pre-Production Checklist

- [ ] Identify which grant types genuinely need recording (e.g., elevated privileges, reading sensitive data).
- [ ] Define stable policy IDs; do not use raw URLs, record IDs, or personal data as metric labels.
- [ ] Preserve the deny path and have tests confirming denials do not disappear.
- [ ] Test that important grants are published and ordinary grants are skipped or sampled per policy.
- [ ] Distinguish request-level, method-level, and dispatch checks; avoid double-counting from wrong assumptions.
- [ ] Verify listeners do not alter authorization outcomes, latency, or response security.
- [ ] Set throughput limits, queue bounds, retention, retries, and drop alerts for the event pipeline.
- [ ] Maintain a separate business audit if you need proof of completed/committed actions.
- [ ] Verify the Spring Security version, compile tests against the real version, and check behavior after upgrades.

## 15. Reference Documentation

- [Spring Security 6.5 – Authorization Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/events.html): publisher, denied, granted, and examples of filtering successful events.
- [Spring Security 6.3 – AuthorizationEventPublisher Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authorization/AuthorizationEventPublisher.html): contract using `AuthorizationDecision`.
- [Spring Security 6.3 – SpringAuthorizationEventPublisher Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authorization/SpringAuthorizationEventPublisher.html): publishes only denials by default.
- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, `HttpServletRequest` objects, and dispatches.
- [Spring Security 7.1 – SpringAuthorizationEventPublisher Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/SpringAuthorizationEventPublisher.html): API for selecting which results emit events in newer releases.
- [Spring Framework – Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events): `ApplicationEventPublisher` and `@EventListener`.