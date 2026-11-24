# Decoupling Audit Tasks from Processing Paths That Cause Latency or Data Leaks

## 1. Why must authentication auditing be decoupled from login processing?

In a Spring Security application, when a user enters a valid or invalid password, uses an OTP, accesses an endpoint with a Bearer token, or re-authenticates, the system typically wants to record an **audit event**: who attempted it, when, which method was used, the outcome, a safe failure reason, and correlation data for investigations.

A common mistake is performing all of that directly on the request-handling path:

```text
POST /login
  → UsernamePasswordAuthenticationFilter
  → AuthenticationManager verifies password
  → AuthenticationSuccessEvent / AuthenticationFailureEvent
  → @EventListener
  → call database, call Kafka/HTTP, lookup GeoIP, send email, log full Authentication
  → respond to user
```

Under Spring Application Events' default configuration, listeners normally run **synchronously on the exact thread that published the event**. A 1-second DB write, a 3-second audit HTTP timeout, or a log-writing failure increases login latency; an exception from a synchronous listener can even disrupt the authentication flow. If the listener logs `Authentication.toString()` or `getCredentials()`, the system risks **leaking passwords, tokens, session data, or personal information**.

This lesson explains how to:

- Understand **who publishes** and **who receives** authentication events in Spring Security.
- Distinguish **mandatory synchronous security checks** from **auditing/telemetry that can move to post-processing**.
- Capture only a **minimal, sanitized snapshot**, never passing the raw `Authentication` object to a queue.
- Isolate I/O work behind a **bounded queue**, backpressure, overflow policies, and monitoring.
- Choose a **durable message/outbox** solution when audits cannot be lost, rather than mistaking `@Async` for durable persistence.
- Implement an illustrative demo in Java 17+, Spring Boot 3.x / Spring Security 6.x, and test correctness, latency, and data privacy.

**Distinguish from the outset:** auditing for observation/investigation can usually happen after authentication; however, **rate limiting, account lockouts, MFA, token signature checks, risk checks used to reject requests, and authorization** can be mandatory synchronous preconditions. Never "push to async" a security control that a request must pass before being allowed.

## 2. Authentication event publishing mechanism in Spring Security

Spring Security provides `AuthenticationEventPublisher`. With `DefaultAuthenticationEventPublisher`, authentication managers such as `ProviderManager` can emit:

| Event | Meaning | Typical source |
| --- | --- | --- |
| `AuthenticationSuccessEvent` | An authentication via the manager succeeded | ProviderManager/password or supporting providers |
| `AbstractAuthenticationFailureEvent` | Base class for failure events | Bad credentials, locked, disabled, expired… |
| `AuthenticationFailureBadCredentialsEvent` | Invalid credentials | Wrong password, mapped bearer failures |
| `AuthenticationFailureLockedEvent` | Account is locked | Provider throws `LockedException` |
| `AuthenticationFailureDisabledEvent` | Account is disabled | Provider throws `DisabledException` |
| `InteractiveAuthenticationSuccessEvent` | Filter notification of successful interactive login | Web/form/interactive login flows |
| `LogoutSuccessEvent` | Logout outcome where supported | Logout processing |

Do not assume that **each request** produces exactly one event, or that every authentication mechanism emits the same types. A system can emit both the manager's success event and the filter's interactive success event for the same login. HTTP Bearer tokens may be verified per request, producing far higher event volumes than form logins. Publishing events manually inside a custom provider, configuring parent managers, or tracking both filters and managers can cause **double counting**.

### 2.1. Processing layers diagram

```text
Request /login
      │
      ▼
Authentication filter
      │
      ▼
AuthenticationManager / ProviderManager
      │
      ├─ Verify password, account policy, MFA...
      │
      ├─ success / failure
      │
      └─ AuthenticationEventPublisher
               │
               ▼
        Spring ApplicationEvent
               │
               ▼
        @EventListener (default synchronous)
               │    Take minimal snapshot only
               ▼
        SafeAuditEvent containing no credentials
               │
        ┌──────┴────────┐
        ▼               ▼
   Bounded queue     Durable outbox / broker
   best effort       for mandatory auditing
        │               │
        ▼               ▼
   Audit consumer   Outbox relay/consumer
        │               │
        └──────┬────────┘
               ▼
      Storage/analytics/SIEM
```

**A synchronous listener can still be very lightweight** if it only normalizes and enqueues a small record. Decoupling from the request path means decoupling **heavy or slow I/O**, not running all authentication logic on another thread.

### 2.2. Registering the publisher

In Spring Security 6.5, documentation provides this bean example:

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    return new DefaultAuthenticationEventPublisher(publisher);
}
```

Imports are `org.springframework.security.authentication.AuthenticationEventPublisher`, `DefaultAuthenticationEventPublisher`, and `org.springframework.context.ApplicationEventPublisher`. This is a **snippet inside a `@Configuration` class**, not a standalone Java file.

Spring Boot may auto-configure a publisher depending on version and setup. When an application manually constructs a `ProviderManager` or another authentication manager, ensure the publisher is properly attached rather than creating a listener and assuming every manager emits events. `DefaultAuthenticationEventPublisher` maps many authentication failures to event types; mapping custom exception classes may require extra registration, noting the documentation's exact exception class matching rule.

## 3. Why is a "write audit immediately" listener an anti-pattern?

Suppose the following code is inside an event handler class:

```java
// ANTI-PATTERN — DO NOT implement
@EventListener
void unsafe(AuthenticationFailureBadCredentialsEvent event) {
    log.warn("Failed authentication: {}", event.getAuthentication());
    remoteAuditClient.post(event);
    userRepository.findByName(event.getAuthentication().getName());
    emailService.sendAlert(event.getAuthentication());
}
```

This snippet illustrates flaws, not a standalone runnable class.

There are at least four problems:

1. **Latency:** network, DB, and external email/SIEM calls increase user login wait times, risking timeouts and servlet thread exhaustion.
2. **Availability:** an unavailable audit service can directly break authentication if an exception from the synchronous listener propagates back.
3. **Sensitive data:** the full `Authentication` may hold credentials, principal, `details`, session info, remote address, or custom attributes. `toString()` is not a redaction contract.
4. **Attack amplification:** an attacker actively generating many failed logins forces the system to open numerous HTTP connections, DB writes, emails, and GeoIP lookups—turning auditing into a self-inflicted DoS.

**Do not fix this by simply calling `new Thread(...)` per event.** That spawns unbounded threads, lacks lifecycle/rejection control, offers no durability guarantees, and still passes sensitive objects across threads.

## 4. Classification: what needs to be synchronous vs. asynchronous?

Not all "security" work shares the same data-loss tolerance:

| Task | Appropriate place | On failure |
| --- | --- | --- |
| Password, token, MFA verification | Before allowing the request | Reject authentication, never skip |
| Account lock/disabled/revocation check | On the security decision path | Fail closed per policy |
| Rate limiting / brute-force guard deciding the request | Before expensive verification | Designed fail-closed/degraded guard |
| Authorization on roles/tenants/ownership | Before returning data | Deny access |
| Recording aggregate login attempt metrics | Async/best-effort post-processing | Measured sample loss acceptable |
| Sending safe events to SIEM for investigation | Async, controlled queue/broker | Detect loss, retry, persistence policy |
| Regulatory auditing or transaction approval | Durable synchronous handoff/outbox when mandated | May have to fail closed if recording fails |
| Sending user alert emails | Async via proper queue | Retry, anti-spam, do not slow logins |
| Geolocation/IP reputation analysis for dashboards | Async if observational only | Must not affect just-completed login decisions |

**Decision rule:** if an action must finish **before** access is granted, never silently defer it to async. If the goal is solely recording, alerting, and analysis, decouple it from the processing path with explicitly defined reliability and latency targets.

For example, "admin accepted terms before receiving privileges" may require durable recording as part of the transaction, whereas "counting login successes for a dashboard" typically tolerates approximation.

## 5. Designing a minimal SafeAuditEvent

**Never enqueue `Authentication`, `HttpServletRequest`, `SecurityContext`, or exception objects directly.** Create an immutable DTO/record containing only allowlisted fields for auditing.

Example schema:

| Property | Type/meaning | Notes |
| --- | --- | --- |
| `eventId` | UUID generated once at source | Deduplicates on consumer retries |
| `occurredAt` | UTC timestamp at source | Preserve original time; consumer time is different data |
| `eventType` | Fixed enum/string `AUTH_SUCCESS`, `AUTH_FAILURE` | Never client-specified |
| `actorRef` | HMAC of canonical account identifier | Pseudonymous, not truly anonymous |
| `actorKind` | `ASSERTED` / `VERIFIED` | Failures contain attacker-supplied usernames, not verified identities |
| `mechanism` | `PASSWORD`, `BEARER`, `OIDC`… if trusted | Derived from provider/chain, not client headers |
| `reasonCategory` | Allowlisted enum, e.g., `BAD_CREDENTIALS` | Never copy raw exception messages |
| `correlationId` | Short server-generated or validated ID | Keep credentials out of traces |
| `sourceRef` | HMAC/aggregate of trusted client IP if needed | IPs are sensitive data; enforce retention policies |
| `schemaVersion` | Event format version | Supports consumer upgrades |

**Must omit:** raw passwords, OTPs, access/refresh tokens, session cookies, `Authorization` headers, full request bodies, full exception stack traces, raw `Authentication.toString()`, or raw principal objects.

If raw emails/usernames must be stored for legal investigations, place them in a separate, access-controlled, encrypted vault with read-auditing and explicit retention limits rather than letting raw data flow through every analytics pipeline. For HMAC, protect the secret/pepper separately; rotation affects cross-period event linking, so manage key versions per policy.

### 5.1. Principal on failure is not necessarily a real user

When someone submits `username=ceo@example.test` with a wrong password, the failure event may contain that submitted username string. It **does not prove** the CEO acted. Record `actorKind=ASSERTED`, and never turn login failures into verified activity of the target victim.

Conversely, after successful authentication by a trusted provider, only the verified subject can use `VERIFIED` per contract. Classify machine tokens, service principals, anonymous requests, and OIDC separately rather than assuming `getName()` is always an email.

## 6. Data boundary: small snapshot directly on the caller thread

Recommended pipeline for best-effort auditing:

```text
AuthenticationEvent (potentially sensitive)
        │
        │ synchronous listener: O(1), no network/DB
        ▼
Sanitize + allowlist + HMAC actor + UUID
        │ SafeAuditEvent immutable, small size
        ▼
Non-blocking queue.offer(record)
        │
        ├── accepted: authentication flow continues
        └── rejected: overflow counter/alert, no secret logging
                 (only suitable for telemetry where loss is acceptable)
        ▼
Scheduled consumer thread / worker pool
        │
        ├── batch + transport + retry policy
        └── audit sink / metrics / SIEM
```

Taking a quick snapshot inside the listener avoids passing `Authentication` or `HttpServletRequest` references to other threads, avoids reading thread-local `SecurityContextHolder` after the request ends, and prevents loggers from accidentally serializing credentials.

Only use **non-blocking** `queue.offer(...)` on the best-effort path; `put(...)` or a long-timeout `offer(...)` can still block authentication when the queue is full. Bounded queues require an explicit overflow policy: drop low-priority events, sample, degrade, or reject requests if mandated by audit requirements. **Never silently lose data.**

## 7. Standalone Java 17 example: bounded non-blocking queue

The following program uses only the Java standard library to illustrate immediate enqueuing followed by separate consumption, with no Spring or database dependencies.

**`BoundedAuditDemo.java`**

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;

public class BoundedAuditDemo {
    record AuditRecord(String kind, String actorRef) {}

    static final class AuditBuffer {
        private final ArrayBlockingQueue<AuditRecord> queue =
                new ArrayBlockingQueue<>(2);
        private final AtomicLong overflow = new AtomicLong();

        boolean offer(AuditRecord record) {
            if (queue.offer(record)) {
                return true;
            }
            overflow.incrementAndGet();
            return false;
        }

        AuditRecord poll() {
            return queue.poll();
        }

        long overflowCount() {
            return overflow.get();
        }
    }

    public static void main(String[] args) {
        AuditBuffer queue = new AuditBuffer();

        System.out.println("first = " + queue.offer(
                new AuditRecord("AUTH_SUCCESS", "actor-1")));
        System.out.println("second = " + queue.offer(
                new AuditRecord("AUTH_FAILURE", "actor-2")));
        System.out.println("third = " + queue.offer(
                new AuditRecord("AUTH_SUCCESS", "actor-3")));

        AuditRecord item;
        while ((item = queue.poll()) != null) {
            System.out.println("write = " + item.kind()
                    + ":" + item.actorRef());
        }
        System.out.println("overflow = " + queue.overflowCount());
    }
}
```

Compile/run on Java 17+:

```bash
javac BoundedAuditDemo.java
java BoundedAuditDemo
```

**Exact stdout:**

```text
first = true
second = true
third = false
write = AUTH_SUCCESS:actor-1
write = AUTH_FAILURE:actor-2
overflow = 1
```

The first two elements fill the capacity-2 queue; the third is rejected immediately without blocking. Afterwards, the simulated consumer drains it. In production, the consumer runs on a separate thread/process with a retry policy; here the consumer runs after the enqueue calls to produce deterministic stdout.

**This is not durable auditing:** a process crash while items remain in the queue loses events; a full queue drops additional items; a consumer polling and crashing before persisting also loses data. This exercise clarifies **latency** and **overflow policies**, not durability or audit completeness.

## 8. Spring Boot 3.x project: safe listener and separate worker

The integration sample below uses:

- Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet.
- Spring Security events for form login via `DefaultAuthenticationEventPublisher`.
- A **short synchronous** `@EventListener` that only builds a pseudonymized `SafeAuditRecord` and enqueues it.
- A `@Scheduled` worker draining the queue on a separate thread, keeping I/O out of authentication callbacks.
- A small bounded queue for **illustrative telemetry**. For mandatory zero-loss audits, apply the durable outbox pattern in section 13.

Classes are separate files in package `com.example.auditdemo` under `src/main/java/com/example/auditdemo/`.

### 8.1. Gradle dependencies and configuration

In a Spring Boot project with the matching Gradle plugin and dependency management, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create `src/main/resources/application.yml`:

```yaml
audit:
  hmac-secret: ${AUDIT_HMAC_SECRET}
  drain-millis: 500
demo:
  password: ${DEMO_USER_PASSWORD}
```

These are **example** properties, not complete secret management. `AUDIT_HMAC_SECRET` must be a strong random secret supplied by a secret manager—never hardcoded in the repository. `DEMO_USER_PASSWORD` is a local lab password; never use a shared demo password in production.

Run in a development Bash shell:

```bash
export AUDIT_HMAC_SECRET="$(openssl rand -base64 48)"
export DEMO_USER_PASSWORD='local-lab-only-not-for-production'
./gradlew bootRun
```

Use this environment-variable approach only in labs. Production should use a secret manager, strict permissions, rotation, and keep secrets out of command history and CI logs. This Boot sample uses username `local-demo` for web form login.

### 8.2. Application, SecurityConfig, controller

**`AuthAuditApplication.java`**

```java
package com.example.auditdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class AuthAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthAuditApplication.class, args);
    }
}
```

**`SecurityConfig.java`**

```java
package com.example.auditdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationPublisher) {
        return new DefaultAuthenticationEventPublisher(applicationPublisher);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${demo.password}") String demoPassword) {
        return new InMemoryUserDetailsManager(
                User.withUsername("local-demo")
                        .password(encoder.encode(demoPassword))
                        .roles("USER")
                        .build());
    }
}
```

**`DemoController.java`**

```java
package com.example.auditdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Home: public";
    }

    @GetMapping("/private")
    public String privateResource() {
        return "Private: authenticated";
    }
}
```

These Java files assume a standard Spring Boot 3.x project with the dependencies above. `formLogin()` creates the default login page and uses sessions/cookies, so CSRF protection for POST login must remain enabled (this example does **not** disable CSRF). The in-memory user store is for demo purposes only.

### 8.3. SafeAuditRecord: allowlist only safe fields

**`SafeAuditRecord.java`**

```java
package com.example.auditdemo;

import java.time.Instant;

public record SafeAuditRecord(
        String id,
        Instant occurredAt,
        String kind,
        String actorRef) {
}
```

This is an immutable Java 17 record containing String/Instant fields. It holds no `Authentication`, password, credentials, `HttpServletRequest`, raw IP, or exception message, so even if accidentally serialized/logged, leak impact is drastically reduced. **Pseudonymous `actorRef` is still data that requires protection**; do not treat it as completely anonymous.

### 8.4. AuditPrivacy: converting usernames to HMAC is safer than raw identifiers

**`AuditPrivacy.java`**

```java
package com.example.auditdemo;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class AuditPrivacy {

    private final SecretKeySpec secret;

    public AuditPrivacy(@Value("${audit.hmac-secret}") String rawSecret) {
        byte[] bytes = rawSecret.getBytes(StandardCharsets.UTF_8);
        if (bytes.length < 32) {
            throw new IllegalArgumentException(
                    "Audit HMAC secret needs at least 32 bytes");
        }
        this.secret = new SecretKeySpec(bytes, "HmacSHA256");
    }

    public String actorRef(String name) {
        if (name == null || name.isBlank() || name.length() > 256) {
            return "invalid-identifier";
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(secret);
            byte[] digest = mac.doFinal(
                    name.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException(
                    "Cannot calculate audit actor reference", exception);
        }
    }
}
```

**Note:** this computes the HMAC of the name returned by `Authentication.getName()`. On a **failed login**, this name is an *asserted username*, not proof a corresponding user exists. Real systems need canonicalization matching the identity store (Unicode/case/email alias rules) before hashing; never call `toLowerCase()` blindly if account names are case-sensitive.

HMAC reduces the chance of deducing usernames from records when an adversary only holds the audit data **without the secret**. If the secret leaks, anyone with a username list can still test matches. Protect, rotate, and key-version the secret; never log the full identifier list or the secret.

### 8.5. AuditBuffer: non-blocking enqueue, bounded memory

**`AuditBuffer.java`**

```java
package com.example.auditdemo;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

@Component
public final class AuditBuffer {

    private final ArrayBlockingQueue<SafeAuditRecord> queue =
            new ArrayBlockingQueue<>(512);

    private final AtomicLong overflow = new AtomicLong();
    private final AtomicLong captureError = new AtomicLong();
    private final AtomicLong writeError = new AtomicLong();

    public void offer(SafeAuditRecord record) {
        if (!queue.offer(record)) {
            overflow.incrementAndGet();
        }
    }

    public SafeAuditRecord poll() {
        return queue.poll();
    }

    public void markCaptureError() {
        captureError.incrementAndGet();
    }

    public void markWriteError() {
        writeError.incrementAndGet();
    }

    public long overflowCount() {
        return overflow.get();
    }

    public long captureErrorCount() {
        return captureError.get();
    }

    public long writeErrorCount() {
        return writeError.get();
    }

    public int queuedCount() {
        return queue.size();
    }
}
```

Uses `ArrayBlockingQueue` to prevent unbounded queue growth when the sink slows down. `offer` never waits on audit service connections; overflows are counted so they can be measured/alerted. This is an **intentional best-effort policy for the demo**, not the default choice for regulatory auditing; if an event must never be lost, use a durable path before returning success.

### 8.6. Listener only takes a snapshot; no DB/HTTP writes in the event callback

**`AuthAuditCapture.java`**

```java
package com.example.auditdemo;

import java.time.Instant;
import java.util.UUID;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public final class AuthAuditCapture {

    private final AuditBuffer buffer;
    private final AuditPrivacy privacy;

    public AuthAuditCapture(AuditBuffer buffer, AuditPrivacy privacy) {
        this.buffer = buffer;
        this.privacy = privacy;
    }

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        capture("AUTH_SUCCESS", event.getAuthentication());
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        capture("AUTH_FAILURE", event.getAuthentication());
    }

    private void capture(String kind, Authentication authentication) {
        try {
            String name = authentication == null
                    ? null : authentication.getName();

            SafeAuditRecord snapshot = new SafeAuditRecord(
                    UUID.randomUUID().toString(),
                    Instant.now(),
                    kind,
                    privacy.actorRef(name));

            buffer.offer(snapshot);
        } catch (RuntimeException unexpected) {
            // Telemetry demo: do not break login on instrumentation error.
            // Do not log unexpected.getMessage() or authentication.
            buffer.markCaptureError();
        }
    }
}
```

**Safety highlights:**

- The listener receives an event containing `Authentication`, yet **never puts that object into the queue**.
- It never reads `getCredentials()`, `getDetails()`, exception messages, full principals, or HTTP requests.
- The actor identifier is processed inside the short callback so it does not rely on request thread-locals after the request ends.
- It makes no database/HTTP/SIEM calls and does not format/write large logs on the auth thread.
- If HMAC/instrumentation fails, the telemetry sample counts the error without changing the login outcome. **For mandatory audits**, policy must differ: never silently ignore.
- The illustrative record includes `kind`/`actorRef` without `actorKind`; consumers must understand `AUTH_FAILURE` reflects an *asserted* user, not necessarily a verified one.
- The manager's `AuthenticationSuccessEvent` does not necessarily mean "the user completed a web session." If you only want to audit interactive session logins, distinguish `InteractiveAuthenticationSuccessEvent`, avoid double-recording, and document event semantics.

### 8.7. Background consumer, keeping failures off the auth thread

**`AuditDrain.java`**

```java
package com.example.auditdemo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class AuditDrain {

    private static final Logger log =
            LoggerFactory.getLogger(AuditDrain.class);

    private final AuditBuffer buffer;

    public AuditDrain(AuditBuffer buffer) {
        this.buffer = buffer;
    }

    @Scheduled(fixedDelayString = "${audit.drain-millis:500}")
    public void drain() {
        for (int i = 0; i < 100; i++) {
            SafeAuditRecord record = buffer.poll();
            if (record == null) {
                return;
            }
            try {
                log.info(
                        "audit id={} occurredAt={} kind={} actorRef={}",
                        record.id(), record.occurredAt(),
                        record.kind(), record.actorRef());
            } catch (RuntimeException failure) {
                buffer.markWriteError();
            }
        }
    }
}
```

In the demo, the consumer writes a **structured/sanitized log** as its sink. This write runs on the scheduler, **not on the login request thread**. `@EnableScheduling` on the main class activates `@Scheduled`.

**Explicit limitations:** once the consumer calls `poll()` and logging/DB fails, the record can be lost. Scheduler crashes, process restarts, full queues, JVM kills, or non-durable log targets can also lose events. This sample suffices to demonstrate decoupling latency from web logins—it **does not** prove 100% audit accuracy, provides no retry/idempotency, and is unsuitable as mandatory audit evidence.

## 9. Should you put @Async directly on @EventListener?

Spring Framework supports combining `@Async` with `@EventListener` when `@EnableAsync` is enabled, for example:

```java
// API illustration; passing raw Authentication to async is not recommended.
@Async("auditExecutor")
@EventListener
public void slowAudit(AuthenticationSuccessEvent event) {
    // I/O will run in the executor, NOT on the request thread.
}
```

Running on an executor isolates threads, yet introduces other risks:

1. **The event still carries sensitive objects.** `Authentication`/credentials/principals can linger in the task queue until the executor processes them, and risk getting serialized/logged.
2. **The executor might be unbounded.** Queued tasks pile up, causing memory growth or OOM under login-failure attacks.
3. **Rejection and overload:** if the executor uses `CallerRunsPolicy`, tasks run on the request thread when full; if it throws `TaskRejectedException`, throwing at submission time impacts the caller.
4. **Async exceptions:** errors in a `void @Async` method are not thrown back to the request; an `AsyncUncaughtExceptionHandler` and monitoring are required.
5. **Thread-local context:** `SecurityContextHolder`, MDC, and tracing contexts are not automatically guaranteed to propagate across threads; never assume post-request context still exists.
6. **Not durable:** `@Async` does not durably persist events and offers no acknowledgements, replay, or dead-letter queues.

**A better pattern to minimize leaks:** have the synchronous listener snapshot an allowlisted DTO and **pass only the DTO** to the executor/queue. You can publish a safe event and apply `@Async` to its handler, though you still need bounded queues, rejection policies, and durability if required.

### 9.1. Bounded executors and rejection handling

When using `ThreadPoolTaskExecutor`, explicitly set `corePoolSize`, `maxPoolSize`, `queueCapacity`, thread naming, shutdown timeouts, and `RejectedExecutionHandler`. Every policy must be load-tested under overload. `CallerRunsPolicy` throttles producers but can **push audit I/O back onto the request thread**; `DiscardPolicy` preserves low latency but **drops events**. There is no universal "best" default: it depends on whether audits are allowed to drop.

For systems demanding low p99 login latency alongside mandatory auditing, consider the **smallest possible durable handoff** before returning the response, then offload all long I/O (SIEM/email/analytics). You cannot simultaneously demand "never wait on any storage" and "never lose an event on crash" without another durability guarantee.

## 10. Do not blindly make all Spring events asynchronous

Spring lets you configure a global `ApplicationEventMulticaster` backed by an executor, yet changing it globally impacts more than just audit listeners. Other listeners may depend on:

- Running on the same transaction/request thread.
- Execution ordering and state-update timing.
- Error propagation when a synchronous listener fails.
- SecurityContext/MDC/request context and cleanup.
- Spring listeners carrying business logic that must run before the response.

**Never solve auditing latency by switching the global event multicaster without checking every subscriber.** Decouple only the specific **audit listener/pipeline**, preferring safe DTOs; account for transaction-bound event semantics and context propagation when using async.

With `@TransactionalEventListener`, events published outside a transaction may not execute as expected (unless fallback execution is enabled); firing after commit also does not provide durability if the process crashes right after commit before publishing. Never treat that annotation as an outbox. To keep events and DB transactions strictly consistent, write an **outbox row in the same transaction** as the business change.

## 11. How does a durable audit differ from an in-memory queue?

| Solution | Request latency | Lost on process crash? | Retry/replay | Use case |
| --- | --- | --- | --- | --- |
| Synchronous listener writing HTTP/SIEM | Potentially very high | Depends on remote ack | Custom-built, blocks easily | Generally avoid |
| `@Async` + executor | Low until full | Can lose events | Not built in | Best-effort only when queue is bounded |
| Internal `ArrayBlockingQueue` | Low and bounded | **Yes** | Not built in | Loss-tolerant metrics/telemetry |
| Kafka/RabbitMQ with durable broker + ack | Handoff/ack step when durability is required | Reduced if broker is properly configured | Supports retry/DLQ | Large-scale log pipelines |
| Database transactional outbox | Brief DB write inside transaction | Tied to DB transaction | Relay can retry | Audits needing consistency with DB changes |
| Protected synchronous append-only audit store | Durable storage cost | Depends on HA/replication | System-dependent | Strict regulatory/compliance audits |

**"Async" and "durable" are two orthogonal axes.** You can be async without durability, durable with request cost, or combine a durable handoff with async downstream delivery. Never use an in-memory queue and claim exactly-once processing.

Most real-world brokers/consumers provide **at-least-once delivery**, because a record can be sent/written while the ack is lost. Design an **idempotent consumer** keyed by a unique event ID. If an audit store appends blindly without deduplication, retries create duplicate entries for the same event.

## 12. Audit schema design, privacy, and data minimization

### 12.1. Versioned durable audit event

Example JSON record **after sanitization**, containing no credentials:

```json
{
  "schemaVersion": 1,
  "eventId": "fdc799ec-a5cd-40d1-8105-34648bcd1252",
  "occurredAt": "2026-10-21T09:00:00Z",
  "kind": "AUTH_FAILURE",
  "actorKind": "ASSERTED",
  "actorRef": "hmac:rotation-v1:...",
  "mechanism": "PASSWORD",
  "reasonCategory": "BAD_CREDENTIALS",
  "sourceRef": "hmac:source-v1:...",
  "correlationId": "rq-19a8b2"
}
```

This is **illustrative data**; the `...` placeholders are not real HMACs. Beyond the demo code above, production `actorRef` values should carry `keyVersion` and subject classification.

### 12.2. Rules for extracting data from Authentication

Never do this:

```java
// ANTI-PATTERN — unsafe
String raw = authentication.toString();
String secret = String.valueOf(authentication.getCredentials());
String details = String.valueOf(authentication.getDetails());
auditClient.send(raw + secret + details);
```

On an unauthenticated `UsernamePasswordAuthenticationToken`, `credentials` may still hold the password or a secret string. On a `BearerTokenAuthenticationToken`, `credentials` is the **access token**. On an `OAuth2AuthenticationToken` and OIDC, the principal may carry claims/emails. Custom authentication objects can hold extra metadata unknown to the logging system. Never rely on one current implementation "appearing to mask passwords in `toString()`" to declare an entire pipeline safe.

Better: extract reviewed fields, enforce length limits, classify data, pseudonymize where appropriate, and **build an immutable record**. Never construct an unconstrained `Map<String,Object>` that allows arbitrary objects into events without schema validation.

### 12.3. IPs, headers, and devices

Client IPs may reside in `WebAuthenticationDetails`, though behind proxies `getRemoteAddress()` often reflects the peer/proxy depending on configuration. Never trust client-supplied `X-Forwarded-For` headers unless normalized by a trusted gateway/proxy. Moreover, IPs and device fingerprints can be personal data requiring clear retention purpose, TTL, access controls, and deletion workflows.

Correlation IDs should be generated by the server or a trusted gateway with character/length validation; never log raw arbitrary `X-Request-Id` headers (log forging). Never place `Authorization`/Cookie headers into MDC/baggage; MDC can propagate unexpectedly to external tracing backends.

## 13. Transactional outbox for events that must never be lost

When audits serve critical transaction compliance or internal policies forbid loss, define the **durability point** before reporting an operation successful. A common design:

1. Inside the relevant DB transaction, write business data and an **outbox row containing `SafeAuditEvent`**.
2. Commit both atomically; if the transaction rolls back, never pretend the operation succeeded.
3. A separate relay reads unprocessed outbox rows, sends them to the broker/audit store, awaits ack, and marks them published.
4. If the relay crashes, rows remain and are retried; consumers must deduplicate by event ID.
5. Bound retention/outbox size, configure retry backoff, dead-letter handling, backlog alerts, and DB access controls.

**Illustrative PostgreSQL SQL**, not a complete migration:

```sql
CREATE TABLE audit_outbox (
    event_id UUID PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    actor_ref VARCHAR(160) NOT NULL,
    payload_json JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX audit_outbox_pending
    ON audit_outbox (occurred_at)
    WHERE published_at IS NULL;
```

Batch-fetching pattern in a PostgreSQL relay transaction:

```sql
SELECT event_id, payload_json
FROM audit_outbox
WHERE published_at IS NULL
ORDER BY occurred_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
```

This is only the **work-fetching query**, not the complete relay/locking/ack logic. Never mark a row published before receiving an ack from the sink/broker. If delivery succeeds yet the relay crashes before updating `published_at`, the event is redelivered -> consumers require **idempotency**. At high throughput, design appropriate partitioning/ordering and lock durations; avoid holding DB transactions open across slow network calls when avoidable by using claim/lease states.

### 13.1. Special considerations for login events

Web login flows do not necessarily share a DB transaction with a business mutation. If login uses an external IdP/LDAP, the application **cannot assume** writing a local outbox row and the IdP accepting login form an atomic distributed transaction.

If compliance requires recording the audit successfully before granting access, the app can append to a durable store **before returning success** and fail closed if persistence fails. That carries latency and availability costs that must be measured and evaluated. Alternatively, use an audit gateway returning a durable persistence ack; actual guarantees depend on the gateway/broker's durability contract.

**Critical point:** never silently trade away mandatory auditing for speed by using a local queue and calling it "zero data loss." Architecture documentation must explicitly state the guarantee level: best-effort, at-most-once, at-least-once, and the commit/ack boundary.

## 14. Testing Spring Security event listeners and redaction

### 14.1. Unit testing a listener that builds DTOs without retaining credentials

Create `src/test/java/com/example/auditdemo/AuthAuditCaptureTest.java`:

```java
package com.example.auditdemo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class AuthAuditCaptureTest {

    @Test
    void failureProducesOnlyPseudonymizedRecord() {
        AuditBuffer buffer = new AuditBuffer();
        AuditPrivacy privacy = new AuditPrivacy(
                "test-audit-hmac-secret-32-bytes-minimum-2026");
        AuthAuditCapture listener = new AuthAuditCapture(buffer, privacy);

        Authentication submitted =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice@example.test", "DO_NOT_LOG_PASSWORD");

        listener.onFailure(new AuthenticationFailureBadCredentialsEvent(
                submitted, new BadCredentialsException("Invalid credential")));

        SafeAuditRecord audit = buffer.poll();
        assertNotNull(audit);
        assertEquals("AUTH_FAILURE", audit.kind());
        assertFalse(audit.toString().contains("alice@example.test"));
        assertFalse(audit.toString().contains("DO_NOT_LOG_PASSWORD"));
        assertEquals(0, buffer.queuedCount());
    }

    @Test
    void successAlsoUsesSafeActorReference() {
        AuditBuffer buffer = new AuditBuffer();
        AuditPrivacy privacy = new AuditPrivacy(
                "test-audit-hmac-secret-32-bytes-minimum-2026");
        AuthAuditCapture listener = new AuthAuditCapture(buffer, privacy);

        Authentication verified =
                UsernamePasswordAuthenticationToken.authenticated(
                        "alice@example.test", "SENSITIVE",
                        List.of(new SimpleGrantedAuthority("ROLE_USER")));

        listener.onSuccess(new AuthenticationSuccessEvent(verified));

        SafeAuditRecord audit = buffer.poll();
        assertNotNull(audit);
        assertEquals("AUTH_SUCCESS", audit.kind());
        assertFalse(audit.toString().contains("alice@example.test"));
        assertFalse(audit.toString().contains("SENSITIVE"));
    }
}
```

These are unit tests of the **adapter/sanitization**, requiring no Spring context. Run `./gradlew test` with the dependencies in section 8. These two tests verify the produced record has no raw username/password in `toString`; they do not prove the entire pipeline/log/capture enforces data policies if uncontrolled fields are added later.

### 14.2. Integration tests to ensure real events are emitted

An integration suite should include:

- `@SpringBootTest` + `@AutoConfigureMockMvc`, failing login via `POST /login` with `csrf()`, verifying the failure event becomes a `SafeAuditRecord`.
- Valid login for `local-demo` using the test password from environment, verifying the success event without logging the request password.
- Verifying the app does not visibly slow down when the audit sink stalls for 5 seconds: the response path only enqueues without awaiting the sink.
- Testing very long/blank malformed usernames, HMAC errors, and listener exceptions without exposing raw input.
- Verifying events are emitted by configured providers; for OIDC/LDAP/JWT flows, verify actual events rather than assuming form-login behavior.
- Checking for duplicate events when one login emits both manager success and interactive success, or when custom publishers exist on parent/child managers.

**Watch out for `@Scheduled` in tests:** the consumer can drain the queue before assertions read it. Tests can disable scheduling via test configuration, use a spy/fake sink, or synchronize on records persisted in a fake writer using a test latch rather than arbitrary `Thread.sleep`. Unit testing the listener as above avoids this race.

## 15. Consumer correctness and resilience

With a best-effort queue, slow record writes do not slow down logins, yet consequences must be defined:

- **Queue full:** increment overflow metrics, alert on thresholds, optionally downsample low-priority events or route to a durable sink; never log each dropped event individually as that creates an I/O amplification loop.
- **Consumer errors:** retry with backoff, per-dependency circuit breakers, bounded concurrency, and no busy loops.
- **Poison events:** schema validation, dead-letter queues, and alerts; never infinitely retry one bad record and block everything behind it.
- **Process restarts:** in-memory queues lose data; graceful shutdown draining helps, though hard crashes still lose buffered items.
- **Ordering:** multiple consumers/partitions can reorder events; retain `occurredAt`, event IDs, and sequence/partition keys if ordering is required.
- **Duplicates:** durable delivery is usually at-least-once; deduplicate by `eventId`, never by timestamp or username.
- **Consumer isolation:** use dedicated connection pools, CPU/memory budgets, outbound circuit breakers, and least-privilege IAM/credentials; audit sink failures must never starve auth verifiers.
- **Event-source rate limiting:** attackers can deliberately generate thousands of authentication failures; protect both login ingress and the event pipeline.

A healthy audit pipeline monitors backlog (queue length, oldest-event age), sink successes/timeouts, retry counts, dead-letter counts, HMAC/capture failures, and drop counts. Without metrics, silent event loss misleads operators into thinking "no attack is happening."

## 16. SecurityContext, MDC, and context propagation

In Servlet apps, `SecurityContextHolder` binds context per thread in most setups. With an async executor, worker threads do not automatically inherit that context. Never pass the entire `SecurityContext`/`Authentication` across threads just to extract a username; snapshot filtered `actorRef`/tenant/correlation metadata immediately when receiving the event.

For tracing, use framework-supported context propagation **strictly for non-sensitive data**. MDC correlates logs via correlation IDs, yet can propagate to external systems; clear context cleanly per lifecycle to prevent cross-request contamination.

**Pseudocode** example, not standalone Java:

```text
ON authentication event in request thread:
    actorRef = HMAC(trustedConfiguredSecret, canonicalIdentifier)
    requestId = validatedCorrelationIdOrServerGenerated()
    dto = SafeAuditEvent(eventId, at, kind, actorRef, requestId)
    boundedSink.tryPublish(dto)

IN worker:
    set logging context { eventId, requestId }
    try:
        persist(dto)
    finally:
        clear logging context
```

Never capture `ServletRequestAttributes`, cookies, `Authorization` headers, or raw `WebAuthenticationDetails` for later processing by a worker. Holding request references after request completion can cause memory leaks and lifecycle corruption.

## 17. Data masking and log injection prevention

Audit storage holds high-sensitivity data, typically lives long-term, and is readable by multiple operators. Therefore:

- **Allowlist fields, deny by default:** persist only reviewed fields; never dump entire objects via Jackson or generic JSON converters.
- **Redact at the source:** if raw identifiers must go to a separate vault, encrypt early and restrict channels; never assume the sink will scrub later.
- **Versioned HMAC keys:** support secret rotation and compliant correlation; HMAC pseudonymization does not eliminate personal-data protection obligations.
- **Distinguish verified vs. asserted actors:** login failures can carry forged usernames; never claim the victim performed the action.
- **Prevent log forging:** strip/encode newlines and control characters, truncate correlation IDs, fix `eventType`/reason enums, and use structured logging.
- **Never serialize exceptions:** `AuthenticationException.getMessage()` and stack traces can expose provider URLs, account hints, or custom provider details.
- **Audit sink access control:** write-only for the service identity, read-only for authorized groups, immutable/tamper-evident if required, with retention/deletion per policy.
- **Never use PII as metric labels:** usernames, emails, IPs, tokens, and high-cardinality `actorRef` values are also unfit as Prometheus tags.
- **Protect backups/exports:** secure audit tables, broker topics, archives, BI exports, and traces; weaknesses often hide in downstream systems rather than the source app.

## 18. Measuring performance: is it truly decoupled from the login path?

Do not measure averages alone. Compare:

| Metric | Writing directly on request | Decoupled via queue |
| --- | --- | --- |
| Login p50/p95/p99 | Spikes when audit sink slows | Generally independent of network sink latency |
| Audit backlog | No explicit queue; requests block | Observe queue depth and event age |
| Time from login to audit visibility | Typically immediate after I/O | Controlled delay, requires SLO |
| Sink outage | Logins may time out or throw | Queue grows, overflows, or applies durable backpressure |
| Data-loss risk | Depends on transaction/ack | In-memory queues lose data on crash |
| Sensitive data exposure | Easy to dump Authentication directly | Allowlisted snapshot shrinks leak surface |
| Behavior at 1,000 failures/sec | Risks exhausting threads/connections | Queue may fill; needs limits and alerts |

Load test design:

1. Measure login baselines at normal and peak load with a healthy audit sink.
2. Intentionally inject 200 ms, 2 s, and 10 s sink delays; measure response p99 and queue growth.
3. Ramp failed logins across many accounts to evaluate attacker amplification.
4. Simulate full queues, consumer crashes, app restarts, and broker/DB outages.
5. Reconcile created/queued/persisted/dropped counts, accounting for duplicates/retries.
6. Inspect thread counts, heap, GC, connection pools, scheduler drift, tail latency, and logging errors.
7. For durable outboxes, measure the short commit cost and relay lag; verify consistency/deduplication rather than latency alone.

**Never claim "zero added latency."** Snapshotting, HMAC, and `queue.offer` still consume minor CPU/memory; fetching secrets over the network from a secret manager per listener call defeats the goal. Cache/supply secrets securely at startup rather than making network calls on every authentication event.

## 19. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Writing DB/HTTP directly in `@EventListener` | Slow logins; sink errors break auth | Snapshot + queue/broker, or brief durable handoff per policy |
| Logging `Authentication.toString()` | May leak principals, credentials/details | Allowlist DTO; HMAC/redact at source |
| `@Async` receiving raw authentication events | Sensitive objects linger in executor queue | Build `SafeAuditEvent` first; pass DTO asynchronously |
| Unbounded executor queue | Memory growth/OOM under login spam | Bounded queue, monitoring, and rejection policy |
| Using `CallerRunsPolicy` expecting always-async I/O | Runs on caller when full, spiking p99 | Choose intentional rejection contract and test overload |
| Using `DiscardPolicy` for mandatory audits | Silent event loss | Durable store + ack/alerts |
| `queue.poll()` followed by failed DB write | Record lost after leaving queue | Retry/ack/durable consumer as required |
| Treating `@Async` as durable | Process crash wipes the queue | Outbox or durable broker |
| Missing `eventId` | Retries create duplicate audits | Source UUID and idempotent consumers |
| Counting two success events for one login | Inflated audits and false alerts | Choose authoritative source event and deduplicate |
| Omitting publisher on manual `ProviderManager` | Listeners receive no events | Configure `AuthenticationEventPublisher` properly |
| Uncaught exception in listener | Can disrupt authentication/requests | Bounded, safe capture; explicit error policy |
| Passing `SecurityContext` to background threads | Lifecycle/thread-local mismatch, principal leaks | Snapshot minimal fields |
| Treating failed usernames as verified actors | Attributes attacker activity to victims | Distinguish `ASSERTED` vs. `VERIFIED` |
| Adding raw IPs/headers to every audit event | PII/credential leaks, IP spoofing | Trusted proxy, HMAC/retention, allowlist |
| Relying solely on `@TransactionalEventListener` | Not crash-durable and skipped without transaction | Write outbox row in the same transaction |
| Losing SIEM events with no metrics | Blind investigations and missing audit trails | Alert on lag/overflow/dropped/failed writes |
| Moving rate limiters/authorization to async | Requests slip through before checks run | Keep security decisions on the synchronous path |
| Sending email alerts on every failed login | Attackers cause mail floods and latency | Aggregate, queue, enforce quotas and cooldowns |
| Failing to test audit logs for secret leaks | Leaks slip in when code/providers change | Regression tests inspecting schemas and log output |

## 20. Self-practice exercises

1. Fix the anti-pattern in section 3: have the listener create only a `SafeAuditEvent` DTO with event type, account HMAC, and timestamp, then enqueue it. Explain why `Authentication` and `Exception` must not be passed along.
2. Run `BoundedAuditDemo.java` with capacity changed to 1. Predict and compare accepted counts, rejected counts, and consumer output order.
3. In the Boot 3 example, build a fake sink delaying 3 seconds. Use a load test to measure login p99 when writing directly inside `@EventListener` versus draining with `AuditDrain`; observe queue depth and overflows.
4. Write a failure unit test whose credential contains a distinctive secret string. Assert that no serialized `SafeAuditRecord` contains that string, the raw username, or the exception message.
5. Use both `AuthenticationSuccessEvent` and `InteractiveAuthenticationSuccessEvent` in the same application. Identify when both fire for one login and design a deduplication strategy.
6. Design durable auditing for payment approval: event ID, in-transaction outbox row, relay, ack, retry, deduplication, retention, and fail-closed conditions.
7. With a custom `ProviderManager`, verify the publisher is attached. Create a custom authentication exception and trace exact exception mapping.
8. Simulate HMAC secret rotation, comparing `actorRef` for the same username before and after rotation; propose key versioning and compliant historical joins.
9. Simulate the entire audit sink being unavailable for 10 minutes: how much best-effort telemetry can drop, how much capacity does a durable outbox need, and can users still log in?
10. Design security logs/metrics to detect credential stuffing without storing full usernames/IPs or leaking source tokens via MDC.

## 21. Summary

- Spring Security authentication events are a convenient audit source, yet **listeners are synchronous by default** and can carry sensitive objects.
- Keep **authentication, authorization, rate limiting, and mandatory policy checks** on the decision path; move auditing/telemetry I/O to workers after building a safe record.
- **Snapshot early, minimally, and immutably**: avoid raw `Authentication`/request/exception objects, prefer HMACs/correlation IDs/allowlisted enums, and distinguish asserted from verified principals.
- **Bounded queues + non-blocking `offer`** protect latency, yet can lose data when full or on crashes. Measure overflows and document best-effort semantics.
- **`@Async` is not durable**; it requires executor, rejection, error-handler, and context policies. Never switch the global event multicaster to async indiscriminately.
- Mandatory auditing requires **durable handoffs/outboxes/broker acks**, retries, and idempotency; failing closed may incur durable-write cost on the request path.
- Measure **p99 latency, event loss, lag, false duplicates, and schema privacy** together, and test failure modes. A fast pipeline that leaks secrets into logs or silently drops audits is still an unsafe pipeline.

**Official references:**

- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Framework 6.2 — Application Events and Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Task Execution, @Async and @Scheduled](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework — Observability and event listeners](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)