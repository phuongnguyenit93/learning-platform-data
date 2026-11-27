# Collecting logs, metrics, and incident data from native processes

## 1. Why design observability specifically for native processes?

A Spring Boot application running as a GraalVM Native Image still needs logs, metrics, traces, and diagnostic data to operate. Application signals such as HTTP requests, business errors, database pools, and queue lag typically continue to rely on Spring Boot Actuator, Micrometer, and your logging framework. However, when a native process crashes, hits OOM, or fails inside a native library, the operations team also needs process- and OS-level data such as exit codes, signals, core dumps, native stack traces, and debug symbols.

You cannot assume JVM/HotSpot collection tools work unchanged with Native Image. JFR, heap dumps, JMX, debuggers, and profilers depend on the GraalVM distribution, version, build options, and operating system. Verify what is supported on the exact target executable.

In the **SPRING_BOOT_NATIVE_IMAGE** module, this lesson establishes how to collect incident data from the moment a request enters until the native process terminates. The goal is to preserve enough context for investigation without exposing secrets, adding unnecessary overhead, or relying on a shell inside distroless containers.

## 2. Signal layers to collect

| Layer | Data | Questions answered |
|---|---|---|
| Application logs | Events, errors, stack traces, request IDs | What did the application process and where did it fail? |
| Metrics | Request rate, latency, errors, CPU/RAM, pool usage | How is the system behaving over time? |
| Distributed traces | Spans, parent/child, dependency calls | Which service made the request slow or fail? |
| Process/container | Exit code, signal, restarts, OOM, RSS | How did the process exit and how much resource did it consume? |
| Native diagnostics | Core dumps, native stacks, debug symbols | Which native frame or library crashed? |
| Build provenance | Commit, toolchain, flags, binary digest | Which exact binary is running and how was it built? |
| Runtime profiles | JFR/heap dumps if supported | Are there signs of allocation, GC, or object retention issues? |

No single signal replaces all others. Logs provide events, metrics reveal trends, traces connect components across a request, and core dumps/native stacks aid process-level crash investigation.

## 3. Logging to stdout and stderr

In containers, applications should write logs to `stdout`/`stderr` so Docker/Kubernetes or a logging agent collects them. There is no need to write log files inside the container if the platform already manages log streams.

Spring Boot typically uses the logging framework configured in the application. Log levels can be adjusted via runtime configuration:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
```

During investigations, you can raise the level for a specific package for a limited window. Avoid enabling global `DEBUG`/`TRACE` long term, as log volume, CPU, I/O, and sensitive data exposure can increase significantly.

With distroless/scratch images, `stdout`/`stderr` are still collected by the container runtime even without a shell. Verify that logs actually appear in `kubectl logs`, Docker logs, or your centralized logging system.

## 4. Using structured logging to search and correlate events

Free-text logs are difficult to query across hundreds of replicas. Structured logging puts fields into a consistent schema:

```json
{
  "timestamp": "2026-11-23T10:15:30.123Z",
  "level": "ERROR",
  "service": "orders-service",
  "environment": "production",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "requestId": "req-82f1",
  "event": "payment_authorization_failed",
  "orderId": "ord-1001",
  "errorType": "PaymentTimeoutException"
}
```

This is an example schema; actual fields must comply with data governance policies. Never log access tokens, passwords, private keys, full payment payloads, or unnecessary personal data.

Useful fields:
- Timestamp with explicit timezone, typically normalized to UTC.
- Service name, environment, and version.
- Trace ID/span ID when tracing is enabled.
- Request/correlation ID.
- Stable event name.
- Error type and stack trace according to policy.
- Instance/pod identity if the platform does not attach it automatically.

Avoid using user IDs, order IDs, or arbitrary values as metric labels because cardinality can explode. Specific identifiers belong in secured logs/traces instead.

## 5. Preserving correlation IDs across requests

When a request traverses a gateway, Order API, payment service, and database, you need a way to link logs across components. Use W3C Trace Context or a standardized correlation mechanism.

If the system uses Micrometer Tracing/OpenTelemetry, trace context can propagate via HTTP client and server instrumentation. Log correlation can place trace ID/span ID into MDC or structured fields depending on your logging setup.

Do not generate a fresh trace ID at every layer when a parent request already supplied context. Doing so breaks parent-child span relationships. For message brokers, propagate context via message headers according to your instrumentation/conventions.

When requests come from untrusted clients, never use arbitrary incoming header values directly as internal identifiers without validating length/format. The gateway can generate or normalize the request ID.

## 6. Collecting Java exception stack traces

A native executable still runs Java application code and can throw Java exceptions. Exception logs must preserve the exception type, an appropriate message, and enough stack trace to pinpoint the execution path.

Example:

```java
try {
    paymentGateway.authorize(command);
} catch (PaymentException ex) {
    log.error(
            "Payment authorization failed for orderId={}",
            command.orderId(),
            ex);
    throw ex;
}
```

Do not log and swallow exceptions that callers must handle; nor should you log the same exception at every layer, causing duplication. Pick a clear boundary responsible for error logging and attach correlation context.

Native stack trace detail may depend on build options and GraalVM version. If fuller traces are needed, verify the corresponding flags on your exact toolchain and inspect results on the executable—do not infer from JVM tests.

## 7. Structured startup and shutdown logs

Startup logs should show which milestones the process reached:
- Process started.
- Spring context initialized.
- Server bound to port.
- Required dependencies ready.
- Readiness transitioned to true.

Shutdown logs should record:
- Stop signal received.
- Stopped accepting traffic / draining.
- Closed listeners, datasources, broker consumers, and schedulers.
- Shutdown completed or grace period expired.

Never log secrets or full connection strings. Use durations and states to measure time-to-ready and shutdown duration. If the process is killed via `SIGKILL` or OOM, shutdown logs may not appear; combine container events and exit metadata.

## 8. Application metrics with Actuator and Micrometer

Spring Boot Actuator together with Micrometer provides application-level metrics. Commonly needed groups include:
- HTTP server request counts and durations.
- JVM/native process memory metrics provided by the registry/runtime.
- CPU/process metrics.
- Database connection pools.
- Executor/thread pools.
- Cache hits/misses.
- Queue depth/consumer lag.
- Business counters such as orders accepted/rejected.

Required dependencies and registries must be added properly, such as the Prometheus registry if Prometheus scrapes the service. Configuring the endpoint alone does not automatically produce every desired metric.

Example exposure configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
```

Expose only necessary endpoints and restrict access via network policies/authentication. Never expose metrics, environment, or config dump endpoints to the public internet.

## 9. Distinguishing JVM metrics from native process metrics

Some metrics bearing JVM names may not share the same meaning or availability in Native Image as on HotSpot. Micrometer binders and Spring Boot versions can expose different metric sets depending on the runtime.

Distinguish:
- Heap/object metrics provided by the Native Image runtime.
- Process RSS/CPU from the OS/container.
- Cgroup memory/CPU limits and throttling.
- Application-level request/connection metrics.
- GC metrics if exposed by the collector/runtime.

Do not assume every JMX-based JVM binder works in a native executable. Inspect the actual metric registry and cross-check against container platform telemetry. When accurate RSS is required, cgroup/container runtime metrics are usually the more reliable source.

## 10. Choosing metrics with controlled cardinality

Metric labels should have finite, bounded value sets: HTTP method, status class, outcome, region, or bounded dependency name. Avoid labeling by:
- Request ID.
- Trace ID.
- User ID.
- Order ID.
- URL paths containing arbitrary identifiers.
- Unbounded exception messages.

High-cardinality labels can inflate memory and storage usage in metrics backends. Granular identifying details belong in logs/traces with appropriate access controls and retention.

Build dashboards grouped by service, environment, and version showing request rate, error rate, p95/p99 latency, saturation, dependency latency, RSS, and restart count.

## 11. Distributed tracing for dependency calls

Traces reveal which spans make up a request: inbound HTTP, service methods, SQL, outbound HTTP, broker publish/consume. Spring Boot can use Micrometer Tracing with an appropriate bridge/exporter or the OpenTelemetry SDK/instrumentation matching your stack.

Verify:
- Trace context is received and propagated.
- Outbound HTTP clients are instrumented.
- Database/broker spans are meaningful.
- Sampling matches traffic volume.
- Exporters deliver data to collectors.
- The native executable supports the chosen instrumentation.

Native Image build metadata and tracing runtime config are separate concerns. Frameworks/dependencies need native support/metadata, whereas OTLP endpoints, service names, and sampling rates are runtime configuration.

Do not export 100% of requests at high volume without accounting for cost. Keep error/high-latency sampling policies and avoid placing sensitive data in span attributes.

## 12. Recording exit codes, signals, and restart reasons

When a native process terminates, application logs may not flush in time. The container runtime/orchestrator supplies additional evidence:
- Exit code.
- Termination reason.
- Signal or `OOMKilled` status.
- Restart count.
- Container start/finish timestamps.
- Previous container logs.
- Pod events and node pressure.

With Kubernetes:

```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name> --previous
kubectl get events --sort-by=.lastTimestamp
```

With Docker:

```bash
docker inspect orders-service
docker logs --timestamps orders-service
```

Preserve this information in the incident timeline. An exit code alone is not always enough to determine the root cause; combine signals, kernel events, cgroup memory, and native diagnostics.

## 13. OOM and memory data

A native process can be terminated by the OS/container runtime when exceeding its memory limit. In an OOM kill, the application may have no chance to write an exception or shutdown log.

Collect:
- Container memory usage and peak.
- Memory limit/request.
- Process RSS if available.
- Heap limit/runtime metrics if supported.
- CPU throttling and request concurrency.
- Restart/`OOMKilled` events.
- Workload/traffic prior to the failure.

Distinguish heap from RSS. RSS also includes code, native memory, thread stacks, mapped files, and shared libraries. Never raise the heap limit mechanically while keeping the container memory limit unchanged.

## 14. Core dumps and native crash diagnostics

When a process crashes in native code or the runtime, a core dump can help analyze process state at failure time. Core dump generation depends on the OS, kernel, container runtime, `ulimit`, security policies, and storage.

On Linux, inspect process/container core dump limits and host configuration per policy. Core dumps can be huge and contain sensitive in-memory data. Never enable unbounded core dumps across all production replicas.

General procedure:
1. Identify the signal/exit reason.
2. Confirm whether a core dump was generated.
3. Preserve the exact binary alongside debug symbols.
4. Record architecture, OS/kernel, and shared library versions.
5. Open the core dump with a compatible debugger/toolchain.
6. Analyze the native stack and map addresses to symbols.
7. Correlate native frames with Java/application frames when information is available.

Never use a newly rebuilt binary to analyze a core dump from an older binary unless symbol/layout equivalence is guaranteed.

## 15. Keeping debug symbols and build provenance

When building with debug information, archive symbol files or unstripped executables per policy. Artifacts should carry:
- Git commit.
- Native executable SHA-256.
- GraalVM distribution/version.
- JDK/compiler/plugin versions.
- Build arguments.
- Target architecture/OS.
- Dependency/SBOM identity.
- Debug symbol artifact ID.

If production images strip symbols, the symbol archive must match the exact binary digest. Use a dedicated artifact store with restricted access and retention aligned to incident policies.

Debug symbols can reveal source paths, packages, and function names. Do not publish them inside public images unnecessarily.

## 16. JFR, heap dumps, and JMX depend on version

GraalVM Native Image can support monitoring capabilities such as JFR, heap dumps, or JMX in specific distributions/versions. Feature sets, build flags, and activation mechanisms vary; never assume they behave identically to HotSpot.

Before relying on them:
1. Record the exact GraalVM distribution/edition/version.
2. Check the Native Image documentation and compiler help output.
3. Enable the monitoring feature at build time if required.
4. Test on the actual native executable.
5. Verify recordings/dumps are actually generated and readable by compatible tools.
6. Measure overhead and configure output paths/quotas.

If a feature is unavailable in your toolchain, rely on OS/container metrics, structured logs, core dumps, or supported profilers instead. Do not pass JFR/heapdump flags in a pipeline merely because a compiler accepts syntax from a different release.

## 17. Collecting logs and diagnostics in distroless containers

Distroless/scratch images typically lack a shell, package manager, `curl`, or debugger. This does not prevent `stdout`/`stderr` collection, but it changes the investigation workflow.

Prepare:
- Node/platform-level logging collector.
- Metrics scraper or exporter.
- Tracing collector.
- Ephemeral debug containers with appropriate network/process context.
- Host-level tools for core dumps and process inspection.
- Dedicated diagnostic storage/volumes if enabled.
- Image digests and binary/symbol artifacts.

Never install debuggers into a running production container. Use debug images or ephemeral containers per platform policy, ensuring collected data belongs to the exact pod/process and incident window.

## 18. Protecting incident data

Logs, traces, heap dumps, and core dumps can contain sensitive data. Enforce policies:
- Mask/redact tokens before writing.
- Restrict payload logging.
- Encrypt data in transit and at rest.
- Apply RBAC to log/trace/diagnostic stores.
- Enforce retention and deletion schedules.
- Audit access to incident data.
- Cap dump sizes and storage quotas.
- Never pass secrets via command-line arguments or build logs.

Core dumps/heap dumps must be treated as highly sensitive data because they can contain raw process memory. Collect them only when justified, secure their storage, and delete them after the approved retention period.

## 19. Incident workflow for native processes

When a native service crashes or spikes in memory:

1. Record timestamp, service version, pod/container ID, and image digest.
2. Gather logs before/after the incident along with relevant trace IDs/request IDs.
3. Gather CPU, RSS, cgroup memory, latency, error, and restart metrics.
4. Check exit codes, signals, `OOMKilled`, and orchestrator events.
5. Preserve native stacks/core dumps if configured and safely collectible.
6. Retrieve debug symbols matching the exact binary digest.
7. Check dependency/native library and toolchain versions.
8. Reproduce with the exact same image/config/workload in staging.
9. Document root cause, trigger conditions, and remediation.
10. Add alerts/tests/runbooks to catch recurrence earlier.

Never rebuild and overwrite artifacts before preserving evidence. Replacing an image or restarting can destroy process state and temporary diagnostic data needed for investigation.

## 20. Evidence matrix by incident type

| Incident | Priority data |
|---|---|
| Elevated HTTP latency | Request metrics, traces, dependency spans, CPU/throttling |
| Business exceptions | Structured logs, stack traces, trace IDs |
| Native crash/segfault | Signals, core dumps, debug symbols, native stacks |
| `OOMKilled` | Cgroup peak, RSS, heap metrics, memory limits, restart events |
| Startup failure | Startup logs, exit code, config/secret mounts, loader errors |
| Database outage | Dependency metrics, connection pools, readiness, DB logs |
| DNS/TLS failure | Resolver/network events, certificate/trust config, client errors |
| GC pauses/heap pressure | GC/runtime metrics if supported, allocation/live set, JFR if available |

This matrix helps on-call engineers collect targeted evidence. Do not turn on every diagnostic mode for every incident when cost or sensitivity is inappropriate.

## 21. Hands-on lab: setting up incident evidence for a native Order API

**Context:** Order API runs as a native executable inside a distroless container, showing occasional unexpected restarts and elevated RSS after burst traffic.

**Step 1 — Standardize logs.** Emit structured JSON to `stdout`, include service/version/trace ID/request ID, and never log secrets.

**Step 2 — Enable metrics.** Collect request rate, p95/p99, errors, process/container memory, CPU, connection pools, and restart counts.

**Step 3 — Enable tracing.** Verify inbound/outbound propagation and sampling; confirm traces reach the collector from the native executable.

**Step 4 — Attach provenance.** Store image digest, binary checksum, GraalVM version, build arguments, and symbol artifacts.

**Step 5 — Verify crash evidence.** Verify exit codes/signals, OOM events, and core dump policy in staging; enable dumps only when storage and access controls are verified.

**Step 6 — Verify profiler support.** If your distribution supports JFR/heap dumps, enable per documentation and capture a sample; otherwise document the limitation and rely on OS/container metrics.

**Step 7 — Run an incident drill.** Generate burst traffic in staging, observe RSS, latency, restarts, and logs; rehearse collecting evidence before restarting/redeploying.

**Step 8 — Write the runbook.** Document commands for logs/events, where to fetch dumps/symbols, access controls, and retention.

Completion criteria: logs/metrics/traces correlate; restarts/OOMs have clear evidence; native crashes have a core/symbol workflow if supported by the platform; image digests and toolchains are traceable; incident data is secured.

## 22. Conclusion

Operating Native Image requires combining application signals with process- and OS-level data. Spring Boot Actuator/Micrometer and tracing continue to track requests, dependencies, and business behavior; container events, exit codes, cgroup metrics, native stacks, core dumps, and debug symbols support crash/OOM investigations.

Standardize structured logs and correlation, collect cardinality-bounded metrics, verify JFR/heap dumps/JMX for your exact GraalVM distribution/version, and tie debug symbols to binary digests. For distroless containers, prepare external logging/metrics collectors and debug workflows. Gather sufficient evidence before restarting or replacing artifacts, and protect logs, traces, and dumps as sensitive data.
