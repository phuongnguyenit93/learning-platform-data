# User Context in Logging — Safely Attaching User Context to Java Logs

## 1. What is User Context?

In **Java Core Logging**, **user context** is the minimal set of information about the **actor performing an action** that is attached to log events to answer questions such as:

- Who or **what type of actor** initiated a request or task?
- Which **request**, processing session, or job does this event belong to?
- Is the actor authenticated or **anonymous**? If it is an internal system, which **service account** is it?
- **On whose behalf** was an operation performed in a controlled delegated access or impersonation scenario?
- How can records across multiple application layers be correlated **without logging secrets or unnecessary personal data**?

**Illustrative log** example:

~~~text
INFO  requestId=req-42 actorRef=usr-7 event=profile.read outcome=success
WARN  requestId=req-42 actorRef=usr-7 event=rate_limit.approaching remaining=2
ERROR requestId=req-42 actorRef=usr-7 event=profile.write.failed errorCode=UPSTREAM_TIMEOUT
~~~

Here, **actorRef=usr-7** is an **illustrative reference identifier**, not a name or email address. **requestId** identifies a single request flow; **actorRef** represents the actor that performed the operation; **event** and **errorCode** have stable meanings for searching.

**User context in logs is not an authentication/authorization mechanism.** Logs are for observability and investigation; access-control decisions must still rely on the security context, verified tokens/sessions, authorization policies, and trusted system state.

**User context is also not the full user profile.** In most situations, a few controlled reference fields are sufficient. Logging full names, email addresses, phone numbers, physical addresses, tokens, or entire JWT claims increases security risk without necessarily aiding diagnosis.

### Lesson Objectives

After this lesson, you will be able to:

1. Choose appropriate user context fields for logs.
2. Distinguish **userId/actorRef**, **requestId**, **traceId**, **tenantRef**, and **principal**.
3. Attach and clean up context across its lifecycle using **SLF4J MDC**.
4. Understand why **MDC does not automatically propagate across thread pools** and how to copy/restore it properly.
5. Configure Logback to output context using a pattern or structured encoder.
6. Handle anonymous users, service principals, delegated actions, and multi-tenancy.
7. Avoid information leakage and verify actual log output with a runnable Java 17 example.

## 2. Why is User Context Valuable?

A log line without context:

~~~text
ERROR event=profile.write.failed errorCode=UPSTREAM_TIMEOUT
~~~

tells you the error type but does not help identify **which request** failed among thousands of concurrent requests. With additional information:

~~~text
ERROR requestId=req-42 actorRef=usr-7 event=profile.write.failed errorCode=UPSTREAM_TIMEOUT
~~~

operators can:

- Find events with the same requestId and inspect the sequence leading up to the error.
- Distinguish a failure in a specific operation from a widespread service-wide outage.
- Correlate with traces/metrics and support data that the system **has authorized** access to.
- Identify whether an action was triggered by a regular user, an admin, or a service account without exposing direct identifying information.
- Check whether a log record has the wrong context attached due to thread reuse.

However, logs **do not prove an action was validly authorized** just because the actorRef field is present. MDC data can be set mistakenly, copied incorrectly, or taken from an untrusted source. For security/audit investigations, logs must be combined with controlled **authentication events, permission checks, and audit trails**.

## 3. Distinguishing Context Types

| Field | Example | Description | Mistake to Avoid |
| --- | --- | --- | --- |
| **actorRef** | usr-7 | Reference to the actor performing the action | Logging name/email/raw token instead |
| **actorType** | user / service / anonymous | Type of actor | Assuming every request is logged in |
| **requestId** | req-42 | ID of a single request | Using it as userId or treating it as access permission |
| **traceId** | Standard tracing trace ID | Correlates a request across multiple services | Populating it with unvalidated user-supplied data |
| **spanId** | ID of a span | Links an event to a processing step | Mixing up spanId and requestId |
| **tenantRef** | tenant-3 | Tenant reference in multi-tenant applications | Exposing tenant data through uncontrolled logs |
| **subjectRef** | usr-9 | Target entity affected by the action, which may differ from the actor | Conflating actor and subject |
| **jobId** | job-78 | Background job not belonging to the current HTTP request | Trying to assign a fake requestId to every job |
| **authenticationState** | authenticated / anonymous | Verified authentication status | Logging raw headers/tokens as proof |
| **event** | profile.read | Stable event type | Embedding dynamic IDs into the event name |
| **errorCode** | ACCESS_DENIED | Stable technical/business error code | Using exception.message as the error code |

The fields above are **schema suggestions**, not a mandatory list. A small service might only need requestId, actorType, actorRef, and event; a multi-tenant system might also need tenantRef.

**actorRef may still be data related to an individual.** Using an ID instead of an email does not automatically make the data anonymous. Appropriate collection policies, access controls, retention, and data deletion rules must still apply. If pseudonymization is used, it must be designed by an authorized team; an unkeyed hash of a predictable ID generally **does not provide adequate protection** against reverse lookup.

## 4. User Context vs. Security Context

A request flow may look like this:

~~~text
HTTP request
    |
    v
Authentication: verify token/session
    |
    v
Security context: authenticated principal and permissions
    |
    +--> Authorization: is the operation allowed?
    |
    v
Create logging context (minimal field allowlist)
    |
    v
Business code -> Logger -> Appender -> Collector
~~~

**Security context** serves authentication and authorization. **Logging context** is data used to describe events and correlate logs, and it may be derived from **a subset of verified information** in the security context.

Keep in mind:

- **Do not use MDC.get("actorRef") to make access-control decisions.** MDC is auxiliary data for logging, not a secure authentication store.
- Do not trust a client-supplied header like **X-User-Id** or a request parameter to conclude who is logged in.
- If the client sends a request ID, apply validation/length-limit rules or generate a trusted internal ID.
- Only obtain actorRef from a **verified principal** or a service identity provided by a trusted system.
- Security context may not exist when a request is unauthenticated or authentication fails; in that case, **actorType=anonymous** is a cleaner choice than guessing a user.

A common security mistake is dumping all **JWT claims** into logs. A JWT can contain email, roles, groups, tenant, and other sensitive information; the raw token itself is a credential and must not be logged. Only extract the safe fields that are genuinely needed, using an allowlist.

## 5. Designing a Minimal User Context Schema

An illustrative JSON record:

~~~json
{
  "schemaVersion": 1,
  "timestamp": "2026-11-09T10:15:00.125Z",
  "level": "INFO",
  "service": "profile-api",
  "event": "profile.read",
  "requestId": "req-42",
  "actorType": "user",
  "actorRef": "usr-7",
  "outcome": "success",
  "message": "Profile read completed"
}
~~~

You can apply the following rules:

1. **actorType** belongs to a defined set of values: e.g., user, service, anonymous. Do not let one team use "human" and another use "end-user" for the same meaning.
2. **actorRef** is a string in a system-controlled format, which may be absent for anonymous requests.
3. **requestId** is a string per request; avoid values that carry access privileges or secret information.
4. **event** is stable, such as profile.read; do not use natural-language messages as query keys.
5. **timestamp** includes an explicit timezone, preferring UTC by operational convention.
6. **outcome** is a string enum with consistent meaning; do not mix success/ok/done across modules.
7. **message** is human-readable and does not contain sensitive raw data.
8. Additional fields such as tenantRef, subjectRef, or errorCode are emitted only when meaningful.

### Null, Missing Fields, and Anonymous

The following three forms have different meanings:

~~~json
{"actorType":"anonymous","event":"catalog.view"}
{"actorType":"user","actorRef":null,"event":"profile.read"}
{"actorType":"user","actorRef":"","event":"profile.read"}
~~~

The first example represents a valid anonymous request; the latter two may indicate **missing data or a contract violation** if actorRef is required when actorType=user. Do not unconditionally turn null or an empty string into actorRef="unknown", because unrelated events can be lumped together under a single fake actor.

**Do not use userRef="anonymous" and treat all unauthenticated visitors as the same user.** If anonymous behavior analysis is needed, use appropriate identification/consent mechanisms and data minimization rather than inventing a persistent tracking ID in logging.

## 6. What Should and Should Not Be Logged?

| Data | Should Log? | Condition |
| --- | --- | --- |
| Non-secret Request ID | Usually yes | Generated/validated, length-limited |
| Event code and errorCode | Yes | Stable schema |
| actorType (user/service/anonymous) | Usually useful | Do not guess authentication state |
| Minimal internal actorRef | Consider | Clear need, permitted processing, retention/ACL |
| tenantRef | Consider | Investigative value and log access control |
| Raw user roles | Restrict | Easily exposes internal permissions; only necessary summary fields |
| Email, full name, phone number | Avoid by default | Only when truly necessary and with proper basis/process |
| JWT/access token, refresh token | **No** | These are credentials |
| Password, API key, session cookie | **No** | No normal diagnostic logging reason |
| Full HTTP headers/body | **No by default** | Easily contains secrets and sensitive data |
| Direct hash of email | Do not treat as anonymous | Vulnerable to dictionary attacks |
| IP/user-agent | Consider very carefully | May be identifying data; limit purpose and retention |
| Exception message/stack trace | Selectively | Check for information leakage and size |

### A "Reference Code" Is Not Automatically Anonymous Data

An actorRef can be a join key to a users table. Anyone with permission to look up that table can still identify the individual. When linkability must be reduced, **keyed pseudonymization** with separated key access and lifecycle management can be used; however, this must be designed according to legal/security requirements rather than arbitrarily computing SHA-256(email) and calling it anonymous.

### Reduce Footprint When User Context Is Unnecessary

Not every cache DEBUG line, health check, or metric needs actorRef. Only attach user context to events that genuinely need correlation with user actions. The more widely user data is replicated across log stores, the harder it becomes to control.

## 7. What is SLF4J MDC?

**Mapped Diagnostic Context (MDC)** is an SLF4J API for storing **key-value pairs scoped to the execution context**, allowing multiple Logger calls to share the same requestId/actorRef without passing those values as parameters to every call.

Example snippet in a class that already has `LOG`:

~~~java
try (org.slf4j.MDC.MDCCloseable request =
         org.slf4j.MDC.putCloseable("requestId", "req-42");
     org.slf4j.MDC.MDCCloseable actor =
         org.slf4j.MDC.putCloseable("actorRef", "usr-7")) {

    LOG.info("event=profile.read outcome=success");
    LOG.warn("event=rate_limit.approaching remaining={}", 2);
}
~~~

This is an **illustrative snippet**, not a complete program. **MDC.putCloseable** creates a convenient scope: when exiting **try-with-resources**, the resource is closed and the corresponding key is **removed**. This prevents a previous request's context from lingering on a reused thread.

**Important:** `putCloseable` **is not a general mechanism that automatically restores previous values** of the same key across nested scopes. If a prior value already existed, you must snapshot/restore it properly or use a tested context wrapper. The standalone example in the next section creates a new scope from an empty context.

### Where Does MDC Sit in the Pipeline?

~~~text
Request handler
  |
  +--> MDC.put("requestId", "req-42")
  +--> MDC.put("actorRef", "usr-7")
  |
  v
Business code -> LOG.info("event=profile.read")
  |
  v
SLF4J API -> Logback event
  |
  v
Encoder: %X{requestId}, %X{actorRef}
  |
  v
stdout/file/collector
  |
  v
Clear/restore MDC at end of scope
~~~

A common mistake: **MDC is set, yet actorRef does not appear in the logs.** The reason is that the backend/encoder **is not configured to output that field**. MDC only holds the context data; how it is rendered is determined by the encoder/formatter.

### Is MDC ThreadLocal or Global?

With standard Logback Classic, MDC is managed per **current thread** context, not as a JVM-wide global variable. **Each thread must have the appropriate context.** A thread pool may reuse threads across multiple requests, so it must be cleaned up/restored after each task.

MDC **does not automatically propagate across every ExecutorService, CompletableFuture, reactive pipeline, or distributed processing flow**. A new worker thread may have no actorRef; a reused worker may carry stale context if the code does not clean it up.

**Do not use MDC to store critical business data.** If core logic needs actorRef/tenantRef, pass them through a **verified** request context or security context, rather than relying on how the logging backend maintains ThreadLocal state.

## 8. Runnable Example — Java 17 + SLF4J + Logback + ExecutorService

This example demonstrates four things:

1. Log statements within a request see the user context via MDC.
2. A task running on a **thread pool does not automatically receive MDC**; a snapshot must be passed if logs should share the same context.
3. Worker code must **restore the context that existed before the task** in a `finally` block.
4. After closing the scope, subsequent logs **are not attributed to the wrong user**.

### 8.1. Project Structure

~~~text
user-context-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── UserContextDemo.java
        └── resources/
            └── logback.xml
~~~

### 8.2. Create pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>user-context-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.UserContextDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The versions shown are a **specific version set for this lesson**, not a claim of being the latest. In real deployments, check version compatibility, security advisories, and dependency management, and avoid having multiple SLF4J providers on the classpath at the same time.

### 8.3. Create src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | requestId=%X{requestId} actorRef=%X{actorRef} | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

In Logback, **%X{requestId}** retrieves the `requestId` value from the logging event's MDC, and **%X{actorRef}** retrieves `actorRef`. When a key is unset, this converter outputs an **empty string** with the configuration in this example.

To keep output deterministic, the pattern intentionally **omits timestamps and thread names**. In production, include a timezone-aware timestamp, service, level, logger name, event, and correlation IDs according to your schema; do not drop timestamps just to make snapshot testing easier.

### 8.4. Create src/main/java/demo/UserContextDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class UserContextDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(UserContextDemo.class);

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            LOG.info("event=system.ready");

            try (MDC.MDCCloseable request =
                         MDC.putCloseable("requestId", "req-42");
                 MDC.MDCCloseable actor =
                         MDC.putCloseable("actorRef", "usr-7")) {

                LOG.info("event=profile.read outcome=success");

                // Capture a copy of the MDC on the thread calling submit.
                Map<String, String> context =
                        MDC.getCopyOfContextMap();

                executor.submit(() -> {
                    // Save the previous context of the worker thread.
                    Map<String, String> previous =
                            MDC.getCopyOfContextMap();
                    try {
                        // Context does not automatically propagate across thread pools.
                        if (context == null) {
                            MDC.clear();
                        } else {
                            MDC.setContextMap(context);
                        }

                        LOG.info("event=audit.enqueued outcome=success");
                    } finally {
                        // Important when this thread is reused.
                        if (previous == null) {
                            MDC.clear();
                        } else {
                            MDC.setContextMap(previous);
                        }
                    }
                }).get();
            }

            // Same worker thread, after the previous task has restored.
            executor.submit(() ->
                    LOG.info("event=worker.idle")).get();

            // Main thread has closed the request/actor MDC scope.
            LOG.info("event=request.closed");
        } finally {
            executor.shutdown();
        }
    }
}
~~~

The program uses **Java 17** and standard APIs only. **Future.get()** waits for the first task to finish before continuing, so the log line order in the example is deterministic. The `ExecutorService` is shut down in `finally`.

### 8.5. Compile and Run

Inside the **user-context-demo** directory, with JDK 17+, Maven, and dependencies downloadable or already in the Maven cache:

~~~bash
mvn -q compile exec:java
~~~

**Stdout emitted by the Java program with the exact logback.xml above** (excluding Maven or environment output):

~~~text
INFO | requestId= actorRef= | event=system.ready
INFO | requestId=req-42 actorRef=usr-7 | event=profile.read outcome=success
INFO | requestId=req-42 actorRef=usr-7 | event=audit.enqueued outcome=success
INFO | requestId= actorRef= | event=worker.idle
INFO | requestId= actorRef= | event=request.closed
~~~

There are no DEBUG, ERROR, or stack trace logs because the program does not emit those events. The blank values for `requestId`/`actorRef` represent **unset MDC keys**; production should have clear rules for missing fields, such as omitting the field rather than emitting an empty key in JSON output.

### 8.6. Output Explanation

1. **system.ready** runs before entering the MDC scope, so both fields are empty.
2. **profile.read** runs on the main thread after setting MDC, so it has `req-42` and `usr-7`.
3. **audit.enqueued** runs on the worker thread: the code **copied the context** on main, called **setContextMap(context)** in the worker, and then logged.
4. **finally** in the worker **restores previous**. With the demo's fresh executor, `previous` is typically null, so MDC is cleared.
5. **worker.idle** runs after the previous task on the single-thread executor; `actorRef`/`requestId` are gone, verifying there is no context leak.
6. **request.closed** runs after both `MDCCloseable` instances are closed on the main thread; the context has been removed.
7. **shutdown()** tells the executor to stop accepting new tasks; `Future.get` already waited for the submitted tasks to complete.

The demo keeps `actorRef` and `requestId` as **non-sensitive mock values**. Production must not blindly copy an entire MDC containing sensitive information just for convenience.

### 8.7. Limitations of This Example

- This is a **single-thread executor** to make context leak checking easier; real multi-threaded systems have many concurrent tasks and more complex error paths.
- The demo has no HTTP server, authentication, or authorization. It only demonstrates **attaching/propagating/clearing logging context**.
- **MDC.putCloseable** removes the key on close; it does not automatically restore an older value of the same key in a nested scope. Frameworks with nested scopes need a snapshot/restore strategy.
- The worker code restores the entire **previous** map so it does not affect another task that ran earlier on the same thread. Calling `MDC.clear()` alone while ignoring `previous` can break valid context in wrapping/nested executors.
- MDC does not automatically cross the network to other services. Correlation/trace context must be propagated over a trusted channel with a policy that prevents arbitrary personal data from being carried in headers.
- **Logback text patterns** do not automatically turn into structured JSON fields. If the system needs to query `actorRef`/`requestId` by field, use an appropriate JSON encoder and configure the collector.
- This code does not use MDC as a security context and does not decide whether reading a profile is permitted.
- `ConsoleAppender` only writes to a stream; it does not guarantee durable storage of audit events. Use a dedicated audit system if required.

## 9. Creating and Cleaning Up User Context at the HTTP Boundary

A web application typically attaches context **once at the request entry point**, rather than setting `actorRef` again in every service. A recommended flow:

~~~text
HTTP request
    |
    v
Authentication filter / middleware
    |
    v
Verify trusted principal
    |
    v
Generate requestId and select context fields via allowlist
    |
    v
MDC scope
    |
    v
Controller -> Service -> Repository -> Logger
    |
    v
finally: clear/restore MDC
~~~

**Pseudocode** example (not standalone Java code):

~~~java
// Pseudocode: principal is authenticated and requestId is generated/validated
// by the framework's mechanism. Do not take actorRef from an arbitrary header.
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", trustedRequestId);
    MDC.put("actorType", authenticated ? "user" : "anonymous");

    if (authenticated) {
        MDC.put("actorRef", approvedActorRef);
    } else {
        MDC.remove("actorRef");
    }

    // frameworkFilterChain.doFilter(request, response);
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

This is pseudocode to illustrate the **mechanism and lifecycle**; real variables/functions must be provided by the actual framework. In real code, you can use a servlet filter, interceptor, request scope, or the framework's observation mechanism. Principal extraction must happen **after trusted authentication**, and exception/async dispatch policies must be handled properly.

**Creating context should be a controlled action:**
- Obtain `requestId` from a trusted gateway/tracing layer, validating format and length.
- Obtain `actorRef` from a verified principal or security service.
- Do not put `displayName`, `email`, or `roles`/raw JWT directly into MDC.
- Record `actorType=anonymous` if unauthenticated, rather than assigning an arbitrary user ID.
- Clean up context when the request finishes or an exception occurs.

### Which Events Should Carry User Context?

Not every log record in the JVM needs `actorRef`. Define clear categories:

- Business requests: **requestId + actorType + actorRef when present and permitted**.
- System events: **service + event**; usually no user.
- Background jobs: **jobId + actorType=service** or an approved reference; do not attach the user from the request that triggered the job if it is no longer appropriate.
- Required auditing: `actor`/`subject`/`tenantRef` under a **separate audit contract**, not using INFO console logs as a substitute.

### Do Not Take Context from Untrusted HTTP Input

A header like **X-Actor-Id: admin** is not proof that the sender is an admin. Putting that header into MDC and treating it as an identity allows logs to be spoofed. If you must log part of an unvalidated input to investigate an attack, **explicitly mark it as untrusted**, limit its size/escaping, and avoid confusing it with an authenticated actor.

## 10. Anonymous, Service Principal, Admin, and Delegated Actions

User context is not only for directly logged-in humans.

| Scenario | Reasonable Context | What to Keep Clear |
| --- | --- | --- |
| Logged-in user | actorType=user, actorRef=... | Actor comes from a verified principal |
| Anonymous access | actorType=anonymous, no actorRef | Do not fabricate a user ID |
| Scheduler/cron | actorType=service, actorRef=job-runner | Do not assign an arbitrary end user |
| Service-to-service | actorType=service, actorRef=svc-payment | Trusted service identity, no raw credentials |
| Support staff acting for a user | actorRef=staffRef, subjectRef=customerRef | Who acts and who is affected are two different entities |
| Admin operating on another tenant | actorRef, tenantRef, subjectRef as needed | Do not mix permissions and tenants of actor/subject |
| Job started by a request | jobId, correlationId, actorRef if policy allows | Timing and actor meaning must be clear |

### Actor and Subject

**Actor** is the entity performing the operation; **subject** is the person/resource being affected. For example, a support staff member updating an account on behalf of a customer:

~~~json
{
  "event": "account.support_update",
  "actorType": "user",
  "actorRef": "staff-12",
  "subjectRef": "customer-8",
  "requestId": "req-900",
  "outcome": "success"
}
~~~

This is **illustrative data**. If only `userId=customer-8` were logged without distinguishing who performed the action, the log would misleadingly suggest that the customer performed the action themselves.

**Impersonation/delegation** is a sensitive scenario. If auditing is required, verified and durably stored audit events are needed per policy—not an MDC string that could be overwritten.

### Tenant Context and Multi-Tenancy

For multi-tenant systems:

- `tenantRef` can help identify which tenant a request belongs to.
- Do not use `tenantRef` in MDC to decide DB access permissions; security/authorization must verify that independently.
- Only use a tenant that is authenticated or reliably derived, never taken directly from an arbitrary header.
- Logs from one tenant must not leak to another tenant due to misconfigured dashboards, search, or ACLs.
- Do not attach sensitive tenant information to every event if unnecessary.

## 11. Async Tasks, Thread Pools, and CompletableFuture

MDC is typically bound to the current thread, while thread pools reuse workers. If a request submits a task and then finishes, the task may execute **after** the request scope has already closed. Therefore:

1. **Snapshot the context at submission time**, keeping only an allowlist of necessary values.
2. On the worker, **save the previous context**.
3. **Set or clear** the context appropriately for the task.
4. Run the work inside `try`.
5. **Restore previous in finally**, even if the work throws an exception.
6. Do not retain references to the request object, principal, HTTP headers, or tokens just to log a task.
7. Do not assume the context snapshot is proof that permissions are still valid when the task runs.

General wrapper snippet:

~~~java
// Illustrative snippet: snapshot contains allowlisted fields.
Runnable wrapWithMdc(Runnable task, Map<String, String> snapshot) {
    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (snapshot == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(snapshot);
            }
            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
}
~~~

The snippet above is an **illustrative method** requiring `import java.util.Map` and `org.slf4j.MDC`, placed inside a class. In real systems, prefer a library or framework that supports context propagation rather than writing inconsistent custom wrappers across modules.

**CompletableFuture.supplyAsync(...)** may run on the common pool or a specified executor. It **does not automatically carry the caller's MDC** across all runtimes. Reactor, servlet async, and message consumers have their own context mechanisms; use the framework-appropriate solution.

### Security When Propagating User Context

Copying the **entire MDC** can carry along fields placed by another library, including data that should not be sent to a worker. In production, prefer **propagating only approved keys**, such as `requestId`, `traceId`, and `actorRef` when there is a clear justification; consider omitting `actorRef` for tasks not directly tied to a user.

**Do not use an MDC snapshot to perform authorization.** By the time the task runs, the user's permissions may have changed or the login session may have expired. Security decisions must be verified using the appropriate trusted mechanism.

## 12. Are SLF4J MDC, Log4j ThreadContext, and JUL the Same?

| Logging System | Typical Context API | Notes |
| --- | --- | --- |
| **SLF4J + Logback** | org.slf4j.MDC | Used via provider; Logback typically stores context per thread |
| **Log4j 2** | org.apache.logging.log4j.ThreadContext | Has context map/stack concepts and its own configuration |
| **JUL (java.util.logging)** | No direct standard MDC equivalent | Can use LogRecord parameters/custom Formatter or a custom abstraction |

Do not confuse these APIs:

- **SLF4J Logger** is not **java.util.logging.Logger**.
- **MDC** is a context API for logging, not a database session or security principal.
- Log4j 2's **ThreadContext** has its own syntax and behavior; you cannot copy Logback XML verbatim into a Log4j 2 configuration.
- **JUL LogRecord.setParameters(...)** is not an automatic request-wide MDC. If used, you need a dedicated contract for how the `Formatter` interprets parameters.

When integrating frameworks, clarify who owns the context: the application, web filter, framework observation/tracing, task decorator, or a shared library. No single automatic configuration fits every environment.

## 13. Structured Logging: Turning User Context into Queryable Fields

A Logback text pattern:

~~~xml
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level requestId=%X{requestId} actorRef=%X{actorRef} %logger - %msg%n</pattern>
~~~

can be useful for humans, but **key=value text does not automatically become structured fields in a collector**. If a message contains newlines or equals signs, simple parsers may misinterpret it.

A JSON object is better suited for field-queryable systems:

~~~json
{"timestamp":"2026-11-09T10:15:00.125Z","level":"INFO","service":"profile-api","event":"profile.read","requestId":"req-42","actorType":"user","actorRef":"usr-7","outcome":"success"}
~~~

In production:

- Let the backend/encoder pull **level, timestamp, logger, and MDC** from the logging event rather than manually typing these fields in every log call.
- Use a JSON encoder with proper escaping; emit one event per physical line if the collector ingests JSON Lines.
- Ensure **requestId, actorRef, and actorType** are mapped with consistent names/types, avoiding duplicate keys between MDC and the event payload.
- Check **null/missing** handling: when anonymous, do not force an empty `actorRef`; the schema should allow the field to be absent.
- Maintain a **schemaVersion** or compatibility strategy when field names, types, or meanings change.
- Limit log size and control how exceptions/stack traces are formatted.
- Verify that the collector actually parses and indexes the allowed fields, rather than only storing a raw JSON string.

### SLF4J 2 Fluent API

In addition to MDC, an event can carry attributes **that apply only to that single call**:

~~~java
// Illustrative snippet in a class with LOG and an actorRef variable.
LOG.atInfo()
        .addKeyValue("event", "profile.read")
        .addKeyValue("actorRef", actorRef)
        .addKeyValue("outcome", "success")
        .log("Profile read completed");
~~~

This is **not a standalone program**. SLF4J 2.x provides the key-value API, but **does not guarantee that every backend/encoder outputs them as JSON or that collectors index them properly**. MDC is suited for context shared across many events in a scope; event key-value pairs are suited for attributes local to a single event. Design your schema to avoid duplicate or inconsistent keys.

## 14. User Context and Distributed Tracing

A request passing through an API gateway, profile service, and audit service may need `traceId`/`spanId` to correlate events. User context does not replace tracing:

~~~text
Gateway       -> traceId=trace-a, spanId=span-1
Profile API   -> traceId=trace-a, spanId=span-2
Audit worker  -> traceId=trace-a, spanId=span-3
~~~

The same `traceId` can have multiple spans; `requestId` may be an ID generated by the gateway, depending on architecture. These fields correlate the **execution flow**, while `actorRef` describes the **actor** of the operation.

If integrating OpenTelemetry or a similar system, you can use framework-supported context propagation for trace/span context. **Do not put emails, tokens, or raw userIds into trace baggage**: baggage can cross network boundaries and reach services that do not need to know the identity.

### When Should actorRef Be Propagated Across Services?

Not always. A downstream service may only need `traceId`/`requestId` for troubleshooting; logging `actorRef` in the receiving service can expand the personal data surface area. If actor identity must be shared for auditing or business logic, use a **trusted authentication/authorization mechanism**, not values from baggage or logging headers as proof.

## 15. Securing User Context and Log Access Control

User context is especially sensitive because it can link logs directly to an individual or account. Rules to apply:

- Only log fields with a **defined purpose** that are genuinely useful for investigation.
- Apply an **allowlist** instead of dumping principals, JWTs, sessions, or full HTTP headers.
- **Never log credentials** at any level, including DEBUG.
- Enforce **read access controls** on logs by service, team, tenant, environment, and data classification.
- Apply **retention**, deletion, and data-request handling processes according to policy.
- Restrict bulk querying by `actorRef` if there is a risk of data abuse.
- **Masking, pseudonymization, and tokenization** must be properly designed and verified; renaming a key is not data protection.
- Prevent log injection using encoders that handle newlines, quotes, and control characters.
- Do not log raw profile payloads, emails, or full roles/permissions, as they easily overexpose information.
- Review export configurations to collectors, SIEMs, or external monitoring platforms, since logs can leave the application environment.
- Separate **security audit events** from best-effort diagnostic logs if higher integrity, retention, or durable storage is required.

**User context can make data more sensitive even when individual fields seem harmless.** Combining timestamps, IP, `actorRef`, `tenantRef`, and `event` can reveal user behavior. Apply data minimization and least-privilege access principles.

## 16. User Context and Performance

Simple MDC usage usually has moderate overhead, but that does not mean you can store unlimited fields and log every action. Points to consider:

1. **Number of keys in MDC:** more fields increase copy/context propagation overhead and governance complexity.
2. **Event volume:** calling `LOG.info` for every item in a high-throughput loop can cause a log storm.
3. **Field size:** do not put profile JSON or full JWTs into MDC.
4. **AsyncAppender/queues:** passing events through a queue can involve context snapshots, drop policies, and lifecycle management.
5. **Field cardinality:** `actorRef` typically has very high cardinality; storing/indexing every value has a cost.
6. **Correlation with metrics:** do not use unique `actorRef`/`requestId` values as unbounded metric labels.
7. **Context creation frequency:** create one scope at the request boundary rather than repeatedly setting/removing keys in every method.

If you need request counts, error rates, or latency, **metrics** are more suitable than emitting a flood of counting logs; **tracing** is suited for paths across multiple services. Logs with user context are useful for investigating specific events, not for replacing the entire observability stack.

## 17. Common Concurrency and Cleanup Issues

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Not removing MDC after a request | Request B's logs show A's actorRef | `try`/`finally` or scope wrapper |
| Setting MDC on main and assuming executor inherits it | Worker logs are missing user context | Snapshot at submit and set in worker |
| Calling only `MDC.clear()` at end of nested wrapper | Destroys valid context of outer scope | Snapshot/restore `previous` |
| Nesting `putCloseable` on the same key expecting auto-restore | Previous value is lost on close | Manage nested scopes explicitly |
| Putting email/raw token into MDC | Sensitive data spreads across many logs | Allowlists, minimal `actorRef` |
| Taking `actorRef` directly from `X-User-Id` | Users can spoof identity in logs | Use verified principal |
| MDC is set but encoder does not print it | Cannot query `actorRef` | Configure pattern/JSON encoder |
| Propagating entire MDC to all services | Unnecessary spread of personal data | Propagate only permitted fields |
| Using MDC for authorization decisions | Risk of authorization bypass | Independent security context |
| Using `actorRef` for all anonymous requests | Multiple visitors merged into one fake ID | `actorType=anonymous`, `actorRef` absent |
| Conflating `actorRef` with `subjectRef` | Logs misattribute who performed the action | Distinguish actor and subject |
| Renaming `userId` to `actorRef` without migration | Old queries/dashboards miss results | Schema versioning and testing |
| Using `actorRef` as a metric label | Cardinality explosion | Do not use individual IDs as metric dimensions |
| Keeping user context in logs too long | Privacy/retention risk | Retention policies and ACLs |
| Not handling exceptions inside scope | MDC leaks on error paths | `finally`, guaranteed scope closure |
| Async processing after HTTP request ends | Stale or invalid context | Controlled context propagation |

## 18. Troubleshooting Workflow When User Context Is Wrong

When a log has a wrong or missing `actorRef`:

1. **Confirm where the event originated:** HTTP request, scheduler, queue consumer, or background job?
2. **Check the authentication point:** did `actorRef` come from a verified principal or an untrusted external source?
3. **Locate the MDC scope:** was the key put before the `Logger` call?
4. **Check thread boundaries:** is there an `ExecutorService`, `CompletableFuture`, virtual thread, or reactive pipeline?
5. **Check copy/restore:** did the worker carry stale context from a previous task?
6. **Inspect the encoder:** does the Logback pattern/JSON encoder actually read the key from MDC?
7. **Check appenders/filters:** was the event filtered by level, routed to another backend, or duplicated?
8. **Check `requestId`/`traceId`:** do related logs share the same correlation ID?
9. **Check actor/subject/tenant fields:** were the actor and target subject swapped?
10. **Check privacy:** did unexpected email/token/raw claim values appear in MDC or the message?
11. **Check the collector:** was the field renamed, overwritten, or parsed with the wrong type?
12. **Verify with a test:** run two requests with different `actorRef` values on the same thread pool and verify there is no cross-talk.

**The absence of `actorRef` is not enough to conclude a request was anonymous.** It could be a bug in context creation, propagation, or the encoder. When you need to distinguish, explicitly set `actorType=anonymous` at the point where the state is verified.

## 19. Testing User Context

Scenarios to include in automated tests:

- **Authenticated request:** `actorType=user` and `actorRef` matches the permitted reference.
- **Anonymous request:** `actorType=anonymous`, no fake user ID generated.
- **Service principal:** `actorType=service` and valid service ID.
- **User context cleanup:** requests A and B running sequentially on the same thread do not see each other's `actorRef`.
- **Exception path:** when a controller/service throws an error, `finally` still clears/restores MDC.
- **Executor propagation:** a task in a worker sees the permitted snapshot.
- **Executor isolation:** the next task does not inherit the previous task's context.
- **Nested scope:** `previous` is restored properly when an outer scope still exists.
- **Impersonation/delegation:** `actorRef` and `subjectRef` are distinct; no ambiguous `userId`.
- **Multi-tenant:** `tenantRef` is not mixed or leaked between tenants.
- **JSON output:** `requestId`/`actorRef` become queryable fields, not just text inside `message`.
- **Security:** test that tokens, passwords, and email/phone are not emitted when forbidden, including in `Throwable` output.
- **Cardinality and size:** key allowlist, `actorRef` length, and retention are appropriate.
- **Unknown/missing:** missing `actorRef` follows schema semantics and does not silently turn into `"anonymous"`.
- **Compatibility:** if renaming fields, verify collector queries and alerts.

### Verifying Using the Demo Output

In the Java 17 example in Section 8, observe:

- Both **profile.read** and **audit.enqueued** lines have `requestId=req-42 actorRef=usr-7`.
- The **worker.idle** line no longer has that context, even though the same executor ran the previous task.
- The **request.closed** line also has no context on the main thread.

That is **minimal evidence for one specific execution flow**, not a guarantee that the entire system is completely thread-safe or that every async framework propagates context automatically.

## 20. Self-Check Questions and Exercises

**Q1.** Is user context the entire user profile written into logs?

**Answer:** No. Only minimal, permitted, and investigation-useful fields should be logged, such as `actorType`, `actorRef`, and `requestId`.

**Q2.** Can `MDC.get("actorRef")` be used to grant database access?

**Answer:** No. MDC is a logging context, not a trusted authentication/authorization source. Permissions must be verified using the security context and dedicated policies.

**Q3.** Should an anonymous request have `actorRef="anonymous"` as a user ID?

**Answer:** It should not be treated as a single user. Use `actorType=anonymous` and omit `actorRef`.

**Q4.** When using SLF4J MDC, why doesn't a task in an `ExecutorService` automatically have the context?

**Answer:** Standard Logback MDC is bound to the thread; a pool's worker thread is different from the caller. Controlled snapshot/propagate/restore is required.

**Q5.** Why should wrapper code restore `previous` MDC in `finally` instead of just clearing everything?

**Answer:** To prevent context leaks while also avoiding wiping out a valid outer-scope context if the worker has wrapped/nested tasks.

**Q6.** Does `MDC.putCloseable` automatically restore the old value of the same key in nested scopes?

**Answer:** No. It closes the scope by removing the key; nested scopes require snapshot/restore or an appropriate abstraction.

**Q7.** Are `requestId` and `actorRef` the same thing?

**Answer:** No. `requestId` represents a single request flow; `actorRef` represents the actor. One actor can make many requests.

**Q8.** If a support staff member edits data on behalf of a customer, who are the actor and the subject?

**Answer:** The actor is the staff member performing the action; the subject is the customer/account being affected. Use separate fields when both must be recorded.

**Q9.** Does logging an internal `userId` instead of an email automatically make logs anonymous?

**Answer:** No. An ID can still be linked to an individual; policies and access/retention controls are still required.

**Q10.** Can you copy all JWT claims into MDC and push them through a queue for convenience?

**Answer:** No. Claims may contain secrets or sensitive data; select only necessary safe fields and never pass raw tokens.

**Q11.** What could cause `actorRef` to be missing from output even though MDC was set?

**Answer:** The encoder does not output that key, the scope was not set on the right thread, the context was cleared, or the collector failed to parse/index the field.

**Q12.** Does MDC automatically propagate over the network to another microservice?

**Answer:** No. An appropriate trace/correlation context propagation mechanism is required, and logging headers must never be used as authentication proof.

**Q13.** Should `actorRef` be used as a metric label to count requests per user?

**Answer:** Usually no. It creates high cardinality, increases cost, and introduces privacy risk; metrics should use dimensions with bounded value sets.

**Q14.** If audit event logs must be durable, are `ConsoleAppender` and `actorRef` enough?

**Answer:** No. Diagnostic logging can be filtered, dropped, or stored non-durably; use dedicated audit storage with its own contract when required.

**Q15.** In the Java 17 demo, why doesn't `worker.idle` print `usr-7`?

**Answer:** The `audit.enqueued` task restored `previous` MDC in `finally`; the worker is reused but no longer holds the previous request's context.

## 21. Summary

**User context in logging is a way to attach minimal information about an event's actor for investigation and log correlation—not a way to store user profiles or replace security systems.**

A solid design must simultaneously ensure:

1. **Right actor:** distinguish actor, subject, service, and anonymous.
2. **Right timing and scope:** create context after trusted authentication, and clear/restore it in `finally`.
3. **Right execution flow:** snapshot/propagate MDC when switching threads; do not assume `ThreadLocal` propagates automatically.
4. **Right schema:** `requestId`, `actorType`, `actorRef`, and `tenantRef`/`traceId` when needed, output via a queryable encoder.
5. **Right security policy:** never log credentials, avoid unnecessary PII collection, and enforce access controls and retention.
6. **Right boundary of responsibility:** MDC serves logging; security context serves authorization; an audit store serves durable retention requirements if applicable.

When these principles are applied, Java logs provide enough context to investigate incidents while limiting data leakage and preventing cross-request or cross-thread contamination.
