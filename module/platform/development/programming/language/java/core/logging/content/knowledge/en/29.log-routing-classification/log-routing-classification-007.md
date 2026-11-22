# Per-Tenant Log Separation in Java Core Logging

## 1. The Problem: One Application, Multiple Tenants, Multiple Log Streams

In a **multi-tenant** system, multiple customers or organizations (tenants) share a single service. If logs from different tenants are mixed into one stream without a reliable identifier, investigating incidents, enforcing retention policies, reconciling costs, and granting log-viewing permissions become very difficult. **Per-tenant log separation** means attaching a tenant identifier to each event, then **routing or partitioning** events to the appropriate storage destination so that, when needed, tenant A can be queried independently without mixing in tenant B's data.

For example, a single process handling three requests:

~~~text
tenant=acme request=req-101 event=invoice_created
tenant=nova request=req-102 event=invoice_created
tenant=acme request=req-103 event=invoice_paid
~~~

The desired output might be two separate files `acme.log` and `nova.log`, two separate streams, two access-controlled indexes, or **a single structured log stream containing `tenantId`** with partitioning policies in the log collector. Creating a physical file per tenant is not mandatory.

**Distinguish three operations:** attaching the `tenantId` field to an event is **enrichment**; deciding which appender/stream an event goes to is **routing**; dropping an event from an unsuitable sink is **filtering**. Permission enforcement at the storage layer is a separate **access control** layer. This lesson focuses on *per-tenant log routing and partitioning* along with operational risks.

## 2. Choosing the Right Log Separation Model

| Model | How It Works | When It Fits | Risks / Limitations |
| --- | --- | --- | --- |
| **Shared structured stream** | Every event carries `tenantId`; collector/index supports filtering and access control | Many tenants, container infrastructure, centralized logging systems | If query permissions are misconfigured, other tenants' logs can still be exposed |
| **Collector routes by tenant** | Application writes JSON/stdout; collector pushes to per-tenant stream/index/bucket | Need storage separation while keeping the application simple | Must ensure the collector does not trust unverified fields, and has retries and drop observability |
| **Separate file per tenant** | Logger creates or selects an appender/file by `tenantId` | Small number of tenants, clear limits, specific operational needs | Many file descriptors, rollover overhead, resources scale with tenants, path risks |
| **Dedicated sink/deployment** | Each tenant uses independent logging resources | Strict isolation or compliance constraints | Increases cost and deployment complexity |

For systems with hundreds or thousands of tenants, **structured logs + collector + backend RBAC** is usually preferred. A separate file per tenant is a practical choice for a tightly managed number of tenants, not the optimal default. Do not equate having an `acme.log` file with having that file encrypted, read-protected, backed up, and retained according to commitments.

### Shared Stream and Dedicated Streams Coexisting

An architecture can send the same event to two destinations:

~~~text
Request / Job
   |
   v
Authenticate -> resolve canonical tenant -> attach tenantId, requestId
   |
   v
LogEvent (immutable per-event metadata)
   |
   +----> COMMON (operational logs, operator-only access)
   |
   +----> ROUTER by tenantId
                 |
                 +---- acme -> acme sink
                 +---- nova -> nova sink
                 +---- unknown/invalid -> quarantine/isolation sink
~~~

`COMMON` helps investigate startup, infrastructure, or missing-tenant request issues. **Do not grant tenant users read access to COMMON** just because they can view their own tenant logs. For events whose tenant cannot be determined, establish a clear policy: route them to an internal `unknown` channel, alert, and investigate; never automatically assign them to a default tenant.

## 3. Where Must the Tenant ID Come From?

**The tenant ID used for routing must be derived from an authenticated context and authorized by the application.** For example: after token verification, middleware binds the principal to an authorized tenant; a worker reads the tenant from validated job metadata; a message consumer verifies the message source/permissions before determining the tenant.

A self-declared HTTP header such as `X-Tenant-Id: acme` or query parameter `?tenant=nova` **is not trustworthy enough** to select a file, bucket, or index. Use them only as inputs to validate, never as the conclusion about which tenant owns the event.

Distinguish the following:

- **`tenantId`:** canonical, stable tenant identifier suitable as a routing key; constrain cardinality and length.
- **`requestId`/`jobId`:** identifier for a single execution to correlate logs within the same request/job.
- **`traceId`/`spanId`:** correlates distributed traces; does not replace `tenantId` for log partitioning or access control.
- **`userId`:** an individual within a tenant; may be sensitive, should not be used in file names, and is usually unnecessary for routing.

If a tenant ID is included in a **file name**, use a safe internal code with an allowlist such as `[A-Za-z0-9_-]{1,40}` and cap the number of values that can be created. Block relative paths (`..`), path separators, control characters, interpolation syntax, special characters, and overly long strings. Character validation **does not prove the caller has access to that tenant**; these two checks must be done separately.

Rules for missing tenants are also part of the design: `unknown` must not represent a real tenant; if there is insufficient data to determine the tenant, route internally or refuse to write to a tenant-specific sink.

## 4. Binding Tenant and Request to MDC with the Proper Lifecycle

In applications using **SLF4J + an MDC-supporting backend**, you can attach the tenant to the logging thread's `MDC (Mapped Diagnostic Context)`. Below is an application helper (requires SLF4J and a compatible backend, **not a JDK-only program**):

~~~java
import java.util.Map;
import java.util.Objects;
import org.slf4j.MDC;

public final class TenantLogScope {
    private TenantLogScope() {}

    public static void run(String authenticatedTenantId,
                           String requestId,
                           Runnable action) {
        Objects.requireNonNull(action, "action");

        // Validate format; tenant authorization must be verified beforehand.
        if (authenticatedTenantId == null ||
                !authenticatedTenantId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("invalid tenant id");
        }

        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            MDC.put("tenantId", authenticatedTenantId);
            if (requestId == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", requestId);
            }
            action.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }
}
~~~

A call site after the tenant has been **authenticated and authorized**:

~~~java
TenantLogScope.run(verifiedTenantId, requestId, () -> {
    logger.info("event=invoice_started invoiceId={}", invoiceId);
    performInvoiceWork();
    logger.info("event=invoice_finished invoiceId={}", invoiceId);
});
~~~

This call site requires `verifiedTenantId`, `requestId`, `logger`, `invoiceId`, and `performInvoiceWork()` defined by the application. Setting `tenantId` in MDC only matters if the backend **captures MDC when creating the LogEvent** or has proper propagation; it does not automatically create separate files or grant file read permissions.

`finally` is mandatory when server/worker threads are reused. For example, if request A sets `tenantId=acme` and forgets to clean up afterward, request B running on the same thread could be misrouted into `acme.log`. The pattern above saves/restores the previous context to support nested calls. If an application framework manages request scope itself, verify who is responsible for cleanup so error paths are not missed.

### Handling Asynchronous Execution and Thread Pools

MDC is typically bound to the **current thread**, so a task submitted to an `ExecutorService`, `CompletableFuture`, or callback may execute on another thread that does not carry the caller's tenant. A worker thread may also retain stale MDC if it was not cleaned up.

Capture a snapshot on the **submitting thread**, apply it in the worker, and restore the worker's original context:

~~~java
import java.util.Map;
import org.slf4j.MDC;

final class MdcPropagation {
    static Runnable wrap(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        return () -> {
            Map<String, String> prior = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (prior == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(prior);
                }
            }
        };
    }
}
~~~

Call `wrap(...)` at **submission** time, while the caller is still in the right tenant scope:

~~~java
executor.execute(MdcPropagation.wrap(() ->
    logger.info("event=invoice_email_queued")));
~~~

This snippet assumes `executor` and `logger` are available. For independent tasks on a pool, ensure the worker's initial context is clean; restoring the worker's `prior` context only preserves its state and cannot cure a stale context leaked from other code. Establish a convention of **leaving no MDC behind between independent tasks** at the executor/framework boundary. For messaging or schedulers, the tenant must be passed in validated envelope/job metadata; do not rely on `InheritableThreadLocal` to propagate tenant per task in a pool.

**Important for async logging:** filters or routers running on the log-writing thread must read **the event's metadata** (the captured event MDC/context map), rather than calling `MDC.get("tenantId")` on the writer thread and assuming it is the originating tenant.

## 5. Standalone Java 17 Example: Routing by Per-LogRecord Metadata

`java.util.logging` (JUL) is part of the JDK and has no standard MDC like Logback. To learn the routing mechanism **without any dependencies**, this example attaches a `TenantContext` to each `LogRecord` and uses a custom `Handler` to select an in-memory sink. This is an illustrative mechanism, not a production file router. It intentionally uses an allowlist of tenants and keeps events missing a tenant in `unrouted`.

Save as **`TenantRoutingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class TenantRoutingDemo {
    private static final Set<String> ALLOWED = Set.of("acme", "nova");

    record TenantContext(String tenantId, String requestId) {}

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.tenant.routing");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        TenantHandler handler = new TenantHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            emit(logger, "acme", "req-101", "invoice_created");
            emit(logger, "nova", "req-102", "invoice_created");
            emit(logger, "acme", "req-103", "invoice_paid");
            emit(logger, null, "req-104", "tenant_missing");
            handler.printAll();
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }

    private static void emit(Logger logger, String tenantId,
                             String requestId, String name) {
        LogRecord record = new LogRecord(Level.INFO, "event=" + name);
        record.setLoggerName(logger.getName());
        // Demo convention: the context snapshot lives on the event itself.
        record.setParameters(new Object[] {
                new TenantContext(tenantId, requestId)
        });
        logger.log(record);
    }

    private static final class TenantHandler extends Handler {
        private final Map<String, List<String>> buckets =
                new LinkedHashMap<>();

        TenantHandler() {
            buckets.put("acme", new ArrayList<>());
            buckets.put("nova", new ArrayList<>());
            buckets.put("unrouted", new ArrayList<>());
        }

        @Override
        public synchronized void publish(LogRecord event) {
            if (!isLoggable(event)) {
                return;
            }

            Object[] parameters = event.getParameters();
            if (parameters == null || parameters.length != 1 ||
                    !(parameters[0] instanceof TenantContext ctx)) {
                buckets.get("unrouted").add("invalid_context");
                return;
            }

            String tenant = ctx.tenantId();
            String target = tenant != null && ALLOWED.contains(tenant)
                    ? tenant : "unrouted";
            buckets.get(target).add("requestId=" + ctx.requestId()
                    + " " + event.getMessage());
        }

        synchronized void printAll() {
            for (String target : List.of("acme", "nova", "unrouted")) {
                System.out.println(target + ": " + buckets.get(target));
            }
        }

        @Override
        public void flush() {
            // In-memory, no I/O buffer to flush.
        }

        @Override
        public void close() {
            // In-memory, no external resources to close.
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 TenantRoutingDemo.java
java TenantRoutingDemo
~~~

**Deterministic stdout** for the program above:

~~~text
acme: [requestId=req-101 event=invoice_created, requestId=req-103 event=invoice_paid]
nova: [requestId=req-102 event=invoice_created]
unrouted: [requestId=req-104 event=tenant_missing]
~~~

Explanation:

1. `emit(...)` attaches a `TenantContext` to the **`LogRecord` itself** via `setParameters(...)`. This is the demo's contract, **not a standard JUL MDC**; other formatters/handlers will not automatically understand this record type.
2. `TenantHandler` decides the destination based on `ctx.tenantId()`; it does not parse the `"event=..."` message string. Events for `acme` are not added to `nova`'s list.
3. Missing or non-allowlisted tenants go to `unrouted` instead of creating an arbitrary sink.
4. Because the demo creates events sequentially with an in-memory handler, element order is deterministic. For multi-threaded producers, proper ordering, synchronization, and I/O design are required.
5. `Logger.setUseParentHandlers(false)` prevents demo logs from propagating to root handlers and printing duplicates or altering stdout/stderr. `handler.isLoggable(event)` still applies the handler's level and filter if configured.

The key takeaway from this example is to **decouple the routing key from the log message text**, capture it per event, route events into controlled sinks, and provide a path for `unknown`. In production, real logging backends already provide appenders/routers, retries, rolling, and lifecycle management; do not copy this in-memory handler to write business log files.

## 6. Logback: Using SiftingAppender to Create Per-Tenant Files

With **SLF4J + Logback Classic**, `SiftingAppender` can select a child appender based on an MDC key. When a `tenantId` value appears for the first time, it creates an appender for that tenant using the template inside `<sift>`. Subsequent log calls with the same key can reuse the live appender.

Example **`logback.xml`** (the application must use Logback; the input tenant ID must pass the authentication and character checks from Section 3):

~~~xml
<configuration>
    <appender name="COMMON" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level tenant=%X{tenantId} request=%X{requestId} %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="BY_TENANT"
              class="ch.qos.logback.classic.sift.SiftingAppender">
        <timeout>10 minutes</timeout>
        <maxAppenderCount>32</maxAppenderCount>
        <discriminator>
            <key>tenantId</key>
            <defaultValue>unknown</defaultValue>
        </discriminator>
        <sift>
            <appender name="FILE-${tenantId}"
                      class="ch.qos.logback.core.rolling.RollingFileAppender">
                <file>logs/tenants/${tenantId}.log</file>
                <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
                    <fileNamePattern>logs/tenants/${tenantId}.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
                    <maxFileSize>10MB</maxFileSize>
                    <maxHistory>7</maxHistory>
                    <totalSizeCap>100MB</totalSizeCap>
                </rollingPolicy>
                <encoder>
                    <pattern>%d{ISO8601} %-5level tenant=%X{tenantId} request=%X{requestId} - %msg%n</pattern>
                </encoder>
            </appender>
        </sift>
    </appender>

    <root level="INFO">
        <appender-ref ref="COMMON"/>
        <appender-ref ref="BY_TENANT"/>
    </root>
</configuration>
~~~

**This configuration illustrates file-per-tenant for a controlled number of tenants**; the limits are examples and must be chosen based on load and retention policies. With MDC `tenantId=acme`, the active file `logs/tenants/acme.log` is used. With MDC `tenantId=nova`, data goes to `nova.log`. When the key is missing, `MDCBasedDiscriminator` uses `defaultValue=unknown` and may create `unknown.log`; **grant only internal access** to this file.

- `<sift>` is a template for creating **child appenders**; the name, file, and rolling policy must vary by key. `${tenantId}` in XML is the variable exported by `SiftingAppender` after the discriminator runs.
- `timeout` closes idle child appenders; too small causes constant churn of creating/closing, while too large keeps many file descriptors open.
- `maxAppenderCount` caps how many child appenders coexist. This is **not** a guarantee on total tenant count, total disk usage, or zero log loss.
- `maxHistory` and `totalSizeCap` belong to **each child appender's** rolling policy. With 100 tenants, disk usage is not automatically capped at 100MB system-wide; you still need global quotas/retention and monitoring.
- `COMMON` receives all events matching the root level; `BY_TENANT` routes an additional copy to a dedicated file. The two sinks serve different purposes and require different access policies.
- `SiftingAppender` is not a tenant authentication mechanism; if MDC is wrong, it can misroute. Never build file names from unverified HTTP headers.

**Important security note:** several Logback versions have changed how `MDCBasedDiscriminator` handles unsafe MDC values. Even though newer library versions block certain path characters, the application must still authenticate the tenant, use normalized internal codes, stay updated with patched versions, and restrict valid route values. Do not rely on logging framework sanitization as a data-isolation boundary. <https://logback.qos.ch/news.html>

### When Should You Avoid SiftingAppender?

If each new tenant creates a file, encoder, and rolling policy, too many tenants increase file handles, heap usage, metadata, and I/O. A low `maxAppenderCount` can cause churn when traffic from hundreds of tenants interleaves; a high timeout keeps many appenders open. At large scale, emitting structured JSON with `tenantId` and splitting at the collector/backend usually scales much better. In containers with ephemeral filesystems, splitting files inside the container also requires a sidecar/shipper, volumes, and clear file-cleanup policies.

## 7. Log4j 2: RoutingAppender with ThreadContext

**Log4j 2** uses `ThreadContext` to attach metadata to log events. `RoutingAppender` can select an appender based on a context key, dynamically create appenders inside `Route`, and clean up idle appenders with `IdlePurgePolicy`.

The **`log4j2.xml`** example below only demonstrates routing with `File`. Production deployments must add rolling/retention, file permissions, and I/O monitoring:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="COMMON" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{ISO8601} %-5level tenant=%X{tenantId} - %msg%n"/>
        </Console>

        <Routing name="BY_TENANT">
            <Routes pattern="$${ctx:tenantId:-unknown}">
                <Route>
                    <File name="FILE-${ctx:tenantId:-unknown}"
                          fileName="logs/tenants/${ctx:tenantId:-unknown}.log"
                          append="true">
                        <PatternLayout pattern="%d{ISO8601} %-5level tenant=%X{tenantId} - %msg%n"/>
                    </File>
                </Route>
            </Routes>
            <IdlePurgePolicy timeToLive="10" timeUnit="MINUTES"/>
        </Routing>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="COMMON"/>
            <AppenderRef ref="BY_TENANT"/>
        </Root>
    </Loggers>
</Configuration>
~~~

**Explaining the two interpolation forms:** `$${ctx:tenantId:-unknown}` in `Routes.pattern` must be deferred so it is evaluated **per LogEvent**, whereas `${ctx:tenantId:-unknown}` inside `Route`'s child appender definition is interpolated when that appender is created. `IdlePurgePolicy` stops rarely used appenders; it does not guarantee that files have been shipped or deleted according to retention.

The Log4j 2 API snippet requires `log4j-api` and a compatible Log4j Core backend (**not a standalone JDK program**):

~~~java
import org.apache.logging.log4j.CloseableThreadContext;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

final class TenantProcessor {
    private static final Logger LOG = LogManager.getLogger(TenantProcessor.class);

    void process(String verifiedTenantId, String jobId) {
        try (CloseableThreadContext.Instance ignored =
                     CloseableThreadContext.put("tenantId", verifiedTenantId)
                                           .put("jobId", jobId)) {
            LOG.info("event=job_started");
            LOG.info("event=job_completed");
        }
    }
}
~~~

`verifiedTenantId` must pass authentication, character validation, and an allowlist if used to build paths. `CloseableThreadContext` scopes the lifetime of keys added within the block, though you still need to verify behavior for nested contexts and async execution. If code dispatches tasks to another thread, pass metadata at the task boundary; do not assume `ThreadContext` propagates automatically.

When you have a small, fixed set of tenants, you can use `Route key="..." ref="..."` pointing to preconfigured appenders. When the tenant count varies, dynamic routes are convenient but require bounding keys, lifecycle, and resources. Consult the documentation for your exact Log4j 2 version: <https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html>.

## 8. Large-Scale Architecture: Splitting at the Collector Instead of Dynamic Files

Container/microservice systems typically write **a single JSON stream containing a `tenantId` field** to stdout or a controlled shared transport. The log collector receives records and can partition them into indexes/streams/buckets or keep them together and enforce per-tenant query policies.

Illustrative JSON example:

~~~json
{
  "timestamp": "2026-11-10T09:40:00Z",
  "level": "INFO",
  "service": "billing",
  "tenantId": "acme",
  "requestId": "req-101",
  "event": "invoice_created",
  "invoiceId": "inv-2042"
}
~~~

The advantages are consistent formatting and transport, no thousands of files/appenders in the JVM, and easier management of retention, quotas, and search. However, the pipeline must be configured properly:

1. **Producer** attaches the verified `tenantId` to each event, keeps schema/keys stable, and formats exception stack traces sensibly.
2. **Collector** parses data, normalizes or validates tenant format, and has an `unknown/quarantine` route. Do not blindly trust every field sent by any producer.
3. **Router/indexer** partitions by tenant or indexes the `tenantId` field. When tenants have dedicated access, query policies must be enforced **server-side**, not merely as a default UI filter.
4. **Storage** enforces retention, encryption, access control, access auditing, and per-tenant quotas per contract.
5. **Observability** tracks backlog, dropped/retried events, destination utilization, `unknown` event counts, and active tenant counts.

**Cardinality:** putting `tenantId` in a **log field** is usually reasonable; putting every `tenantId` into metric labels, partitions, or physical indexes can cause cardinality/resource explosions. Partitioning choices should be based on tenant count and log rate, without assuming every tenant needs its own index.

**Noisy neighbor:** a tenant emitting millions of DEBUG lines can consume bandwidth/storage and impact other tenants. You can apply quotas or sampling to diagnostic logs, but never silently sample or drop mandatory audit logs. Plan for backpressure, retries, and alerts when the pipeline is overloaded.

## 9. Data Isolation: Correct Routing Is Not Enough

Operational log separation often comes with security requirements. Control at least the following layers:

| Layer | Risk If Missing | Mitigation |
| --- | --- | --- |
| Tenant authentication | Client spoofs tenant to write into the wrong sink | Canonical tenant ID from authenticated principal/job, verify authorization |
| Context propagation | MDC missing or leaked in thread pools | Scoped context; capture/restore across async; test reuse |
| Path / route key | Path traversal, route explosion | Allowlist internal codes, block `..`/separators/interpolation, cap tenants |
| Log payload | Tokens, passwords, PII logged | Data minimization/redaction before logging, never log full bodies |
| Storage | Tenant A user reads tenant B's logs | Server-side RBAC/ACL, encryption, auditing, separate policies |
| Retention | Data kept too long or fills disk | TTL/rolling/quota/cap at the right scope, monitor total disk usage |
| Centralized system | Wrong index or easily bypassed UI filter | Enforce policy at storage/API; test cross-tenant access |
| Pipeline failures | Events dropped or stuck in dead letter | Alerts, retries, quarantine, reconciliation appropriate to log type |

Do not treat checking `tenantId` in logging code as a standalone security boundary. In particular, logs **can contain another tenant's data in the payload** if business code accidentally puts it into the message; even accurate metadata-based routing cannot fix bad message content. Combine log payload reviews, access testing, and storage policies.

System logs such as startup, GC, connection pools, or stack traces before a request arrives usually have no tenant. They belong to the shared internal channel and should not be forced into a specific tenant's sink. If an event spans multiple tenants, define ownership/relationships explicitly rather than guessing from the current thread.

## 10. Testing Per-Tenant Log Separation

Do not just assert that `logger.info(...)` was called; tests must observe the **actual destination**: which appender received which events, which files/streams were created, and which tenant can read that data.

### Minimum Test Matrix

| Test | Input / Scenario | Expected Result |
| --- | --- | --- |
| Alternating A and B | `acme`, `nova`, `acme` | Sink A receives exactly two A events; B receives exactly one B event |
| Missing tenant | Event without `tenantId` | Goes to internal `unknown` or handled per policy; never randomly lands in A/B |
| Unknown tenant | `tenantId=not-allowed` | Does not create a sink/file outside the allowlist if policy forbids it |
| Spoofed client tenant | Self-declared header unauthorized for principal | Rejected / does not control routing |
| Thread pool reuse | One worker runs task A then B | No MDC from A appears in event B |
| Async logging | Producer MDC changes after event A is enqueued | Event A still routes using the captured context A |
| Exception path | Task A throws an exception | Context is cleared/restored; stack trace is written to the right place |
| File rollover | Generate enough logs to rotate | Active/archive files belong to the right tenant; retention/cap take effect |
| Too many tenants | Load with many keys or fake tenants | File descriptors and disk do not grow unbounded |
| Sink access | User A requests to view sink B | Denied by backend, even if UI filter is removed |
| Collector overload | Queue full, destination temporarily failing | Drops/retries/quarantine are measurable and alerted |

For multi-threaded tests, use `requestId`/`jobId` to compare event sets; do not assert ordering across threads if the executor does not guarantee it. Measure **received** events and **successfully written** events separately, because async queues can lose or delay logs. When testing permissions, verify the backend API/queries, not just file names.

### Manual Test Scenarios

1. Send valid requests for tenants A and B with distinct IDs; inspect COMMON and both tenant sinks.
2. Send requests with no tenant, an invalid tenant, and a tenant attempting to spoof B; verify fail-closed behavior in dedicated sinks.
3. Run a 1-worker pool with tasks `A → B → missing`, force callbacks/exceptions, and verify events belong to the right tenant.
4. Generate enough log volume to trigger rotation and enough tenants to test appender limits. Measure file creation time, handle count, and disk usage.
5. Ship logs through the collector to the backend; try querying B's data with tenant A's account and confirm the server blocks it.
6. Shut down the application while a backlog exists and verify enqueued logs are drained according to policy.

## 11. Common Operational Pitfalls

**Pitfall 1 – relying on `Thread.currentThread().getName()` to infer the tenant.** Pools reuse threads, so each worker runs requests for many tenants. Per-event metadata is required.

**Pitfall 2 – forgetting to set or clear MDC.** Logs without a tenant pile into `unknown`, or B's logs get tagged with A due to stale context. Setup/cleanup at boundaries and async propagation are required.

**Pitfall 3 – using client-supplied tenant IDs in file paths.** Values with special characters can produce unintended paths, causing misrouting or resource exhaustion. Always authenticate the tenant and use a bounded, stable key.

**Pitfall 4 – creating an unbounded appender/file per tenant.** Increases file descriptors, archive counts, and rollover overhead. Use `timeout`/`maxAppenderCount` and cap tenants; consider a centralized collector.

**Pitfall 5 – treating a separate sink as absolute security.** If COMMON or a shared backend index is readable by anyone, file separation alone is insufficient. Use RBAC/ACL and inspect payloads.

**Pitfall 6 – filtering out system logs and ERRORs.** Events before a tenant is resolved must not be dropped from operational channels. Maintain an internal `unknown/quarantine` channel and alert on unexpected spikes.

**Pitfall 7 – logging the same error multiple times.** An exception appearing in both COMMON and a tenant sink may be **two copies in two destinations** by design; that differs from a service/controller logging the full stack trace repeatedly into the same sink. When counting errors, use event IDs and a duplicate-aware model.

**Pitfall 8 – ignoring async queue errors and timeouts.** A logging API returning does not guarantee the event reached disk or the collector. Shut down gracefully, monitor backlogs, and track drops.

**Pitfall 9 – assuming retention rules in a child rolling appender act as a global quota.** Each tenant may have its own `totalSizeCap`; a global quota requires additional monitoring or storage policies.

**Pitfall 10 – deleting/renaming a tenant without handling old logs.** Retention policies, legal holds, query permissions, and partition names must be managed across the tenant lifecycle; do not automatically delete logs when a tenant is renamed if retention obligations exist.

## 12. Implementation Checklist

- Define whether separation is physical or logical, expected tenant count, log volume per tenant, open-file limits, and retention requirements.
- Derive the canonical tenant from an authenticated context; define format/allowlist rules, missing-tenant handling, and system-log policy.
- Attach the tenant to **event metadata**; propagate context across request, job, thread pool, and async boundaries, always cleaning up.
- Choose appender-level or collector-level routing; keep COMMON internal for incident investigation and define which appenders can see which events.
- If using per-tenant files, configure rollover, appender timeouts, resources, file permissions, storage quotas, and shippers.
- Apply redaction and query/storage access control; never put secrets into MDC/messages, and never trust UI-only filters.
- Write tests for A/B/missing, concurrency, path injection, high-cardinality, sink failures, and cross-tenant access.
- Monitor active tenants, unknown events, drops/retries, disk/handles, cost, and shutdown latency.

**Key takeaway:** per-tenant log separation is only trustworthy when **the tenant is authenticated**, **metadata is preserved per event**, **routing handles missing/invalid cases**, and **access control is enforced at storage**. At large scale, a single structured log stream split at the collector is usually easier to operate than thousands of dynamic files; at smaller scale where dedicated files are required, `SiftingAppender`/`RoutingAppender` are useful when lifecycle and security are properly controlled.

### References

- Logback Manual — [SiftingAppender, MDC discriminator, timeout, maxAppenderCount](https://logback.qos.ch/manual/appenders-async-sift.html) and [RollingFileAppender](https://logback.qos.ch/manual/appenders-rolling.html).
- Logback — [MDC](https://logback.qos.ch/manual/mdc.html); [version and patch announcements](https://logback.qos.ch/news.html).
- Log4j 2 — [RoutingAppender and IdlePurgePolicy](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html); [Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html).
- SLF4J — [MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html).
- Java 17 — [java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html), [LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html).