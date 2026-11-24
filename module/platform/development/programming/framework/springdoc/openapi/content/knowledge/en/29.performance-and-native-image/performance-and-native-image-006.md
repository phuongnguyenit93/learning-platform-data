# Measuring Documentation Endpoint Performance Separately from Business APIs

Springdoc-openapi exposes documentation endpoints such as /v3/api-docs and /v3/api-docs.yaml alongside the business endpoints published by a Spring Boot application. These two groups of endpoints have different purposes and load characteristics: business APIs are typically called continuously to serve users, whereas documentation endpoints return a potentially large document containing many paths, operations, schemas, and components.

When measuring performance, separate documentation endpoints from business APIs to understand the cost of generating and serving the OpenAPI document, rather than lumping all requests into a single combined latency figure. Only after establishing separate baselines should you run a mixed workload test to observe whether fetching documentation affects business APIs.

## 1. Why Measure Documentation Endpoints Separately?

Documentation endpoints and business endpoints differ in processing, response size, and access frequency.

| Characteristic | Documentation Endpoints | Business APIs |
|---|---|---|
| Examples | /v3/api-docs, /v3/api-docs.yaml | /api/orders, /api/customers/{id} |
| Primary work | Generate or retrieve OpenAPI document, serialize JSON/YAML | Execute business logic, access cache/database/services |
| Response size | Can be large depending on operation and schema counts | Typically depends on request data |
| Access frequency | Usually low, concentrated among developers/tools/CI | Can be high and continuous |
| Load profile | Can consume CPU, allocations, and bandwidth when document is large | Can be bound by database, downstream services, or business logic |
| Measurement goal | Cost of generating, caching, serializing, and transferring the document | Business latency, throughput, and stability |

Measuring only an aggregate URL or mixing both endpoint groups in the same test fails to reveal the root cause when latency rises. Separating them answers:

- How long does the OpenAPI endpoint take to return the document the first time?
- Are repeated requests faster thanks to caching?
- How do JSON and YAML documents differ in serialization cost and size?
- As operation and schema counts grow, how do CPU, memory, and latency change?
- Does documentation load contend for resources with business APIs?

## 2. Identifying Endpoints to Measure

Under default configuration, commonly used endpoints are:

| Endpoint | Content |
|---|---|
| /v3/api-docs | OpenAPI JSON |
| /v3/api-docs.yaml | OpenAPI YAML |
| /v3/api-docs/{group} | Group OpenAPI JSON |
| /v3/api-docs.yaml/{group} | Group OpenAPI YAML |
| /swagger-ui.html | Swagger UI entry page |
| /v3/api-docs/swagger-config | Swagger UI configuration |

To measure document cost, prefer calling the JSON/YAML endpoints directly. Do not use /swagger-ui.html load time as a proxy for OpenAPI document generation time because the UI page also downloads JavaScript, CSS, fonts, and other assets.

If the application changes springdoc.api-docs.path, has a context path, or sits behind a reverse proxy, use the actual configured URL. If there are multiple groups, measure each relevant group separately because document size and operation count can differ.

Select at least one representative business API for comparison, such as:

- A simple read-only GET.
- A GET that queries a database or returns a list.
- A POST with validation and business processing.

Do not pick an artificially trivial business API if production mainly handles complex queries, or vice versa. The reference endpoint should reflect real workload.

## 3. Metrics to Collect

Do not record only an average duration. At minimum, monitor:

| Metric | Meaning |
|---|---|
| Latency p50 | Half of requests complete in or below this duration |
| Latency p95 | 95% of requests complete within or before this duration |
| Latency p99 | Reflects the slow tail of the distribution |
| Throughput | Requests completed per unit time, typically requests/second |
| Error rate | Percentage of requests failing or returning unexpected status codes |
| Response size | Number of JSON/YAML bytes transferred |
| CPU utilization | CPU usage of the process/container |
| Heap and memory | Heap usage, RSS, or container memory limit consumption |
| Allocation and GC | Object allocation rate, garbage collection time and frequency |
| Server-side duration | Processing time inside the server, if instrumented |

Latency measured from a load generator includes network, DNS, TCP/TLS handshake, and server processing time. It is an important client-facing metric but is not identical to CPU time or internal document generation time inside the application.

When analyzing root causes, combine client-side latency with server metrics, tracing, or profiling. Do not conclude springdoc is slow solely from a single curl measurement over an unstable network.

## 4. Distinguishing Latency, TTFB, and Response Transfer Time

For large documents, time to first byte and time to download the complete response can differ substantially.

- Time to first byte (TTFB) reflects the time from when the client starts the request until it receives the first byte. This value is also affected by connection and network conditions.
- Total time is the duration to complete the entire response.
- Download size indicates how much data was transferred.

If TTFB is high, check whether the server spends significant time before writing the response. If TTFB is low while total time is high, the document may be large or bandwidth between client and server may be constrained.

For OpenAPI endpoints, JSON and YAML can differ in size due to serialization. Never compare latencies while ignoring response size and HTTP compression settings.

## 5. Preparing a Comparable Measurement Environment

For meaningful results, keep the following conditions identical between documentation endpoint measurements and business API measurements:

1. Same application, JDK, and springdoc versions.
2. Same CPU/memory limits and container configuration.
3. Same replica count or the same isolated instance.
4. Same network path, TLS termination, and reverse proxy.
5. Same logging level and instrumentation.
6. Same security configuration and token delivery method.
7. Same cache state, unless specifically measuring cold/warm behavior.
8. Same load testing tool and load generator placement.

Do not run the load generator inside the application container if the goal is to measure the server. CPU contention between client and server skews results.

When measuring on Kubernetes, record CPU requests/limits, memory requests/limits, pod count, node type, and autoscaling policy. If an autoscaler changes replica counts between runs, throughput and latency are no longer comparable under equal conditions.

## 6. Separating Cold-Start and Warm-Request Measurements

The first request after application startup can be affected by:

- JVM class loading and JIT compilation.
- Spring application context startup.
- Bean initialization or lazy initialization.
- Springdoc's initial analysis of mappings, models, and annotations.
- Serializer or cache initialization.
- Client-side DNS, TCP, and TLS handshakes.

Subsequent requests can be faster because the JVM has warmed up, connections are reused, or the OpenAPI document is cached. Therefore, do not mix the first request with steady-state requests in the same statistical summary.

Perform two separate measurements:

| Measurement | Execution Method | Goal |
|---|---|---|
| Cold/first-hit | Start a fresh instance, wait for readiness, then call docs for the first time | Measure first-access experience after startup |
| Warm/steady-state | Send warm-up requests first, then collect samples | Measure stable performance once the application is running |

Note: process cold-start and endpoint first-hit are not completely identical. If a readiness probe or another component already hit the OpenAPI endpoint before your test, the request you treat as a client first-hit is no longer springdoc's first-hit.

## 7. Understanding the Role of Caching

Springdoc has an OpenAPI description caching mechanism in versions that support the corresponding configuration. Caching can make repeated requests faster because the application avoids repeating all document generation work on every call. Exact behavior depends on the version, configuration, and whether the document varies per request.

A common property for controlling caching is:

~~~yaml
springdoc:
  cache:
    disabled: false
~~~

Setting disabled: true can be useful when specifically measuring document generation cost without cache, but confirm this property in the documentation for the exact springdoc version running. Do not alter production cache configuration solely for benchmarking.

At least two cases should be measured if the application needs a clear cost breakdown:

- Production-like cache configuration: measures normal request experience.
- Cache disabled in a test environment: estimates document regeneration cost.

Do not confuse springdoc's cache with HTTP caching at a reverse proxy, gateway, or CDN. A proxy may serve a cached response without hitting the application. In that case, client measurements do not reflect actual server load.

## 8. Quick Measurement with curl

curl is well suited for quickly checking an endpoint, status, response size, and timing. Bash example:

~~~bash
DOCS_URL="http://localhost:8080/v3/api-docs"

curl -sS \
  -o /dev/null \
  -w "status=%{http_code} bytes=%{size_download} ttfb=%{time_starttransfer}s total=%{time_total}s\n" \
  "$DOCS_URL"
~~~

This command does not write the document to disk; it prints status, byte count, TTFB, and total time. Run it multiple times to observe variance:

~~~bash
for i in $(seq 1 10); do
  curl -sS \
    -o /dev/null \
    -w "status=%{http_code} bytes=%{size_download} ttfb=%{time_starttransfer}s total=%{time_total}s\n" \
    "$DOCS_URL"
done
~~~

This is a smoke/baseline check, not a load test. Each new curl process may open a fresh connection and pay DNS/TCP/TLS overhead. To measure many requests with keep-alive and controlled concurrency, use a load testing tool.

On Windows PowerShell, invoke curl.exe explicitly if curl is an alias:

~~~powershell
$Url = "http://localhost:8080/v3/api-docs"
curl.exe -sS -o NUL -w "status=%{http_code} bytes=%{size_download} ttfb=%{time_starttransfer}s total=%{time_total}s" $Url
~~~

## 9. Using k6 to Measure the OpenAPI Endpoint Independently

k6 generates repeatable load with a specified virtual user count and duration. Create docs.js:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '60s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
  },
};

export default function () {
  const headers = __ENV.OPENAPI_TOKEN
    ? { Authorization: 'Bearer ' + __ENV.OPENAPI_TOKEN }
    : {};

  const response = http.get(
    __ENV.BASE_URL + '/v3/api-docs',
    { headers }
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
    'content type is JSON': (r) =>
      String(r.headers['Content-Type'] || '').includes('application/json'),
    'body contains OpenAPI version field': (r) =>
      r.body !== null && r.body.includes('"openapi"'),
  });

  sleep(1);
}
~~~

Run the test:

~~~bash
k6 run -e BASE_URL=http://localhost:8080 docs.js
~~~

If the endpoint requires a token, pass it via a secret environment variable on the test runner:

~~~bash
k6 run -e BASE_URL=https://test.example.com -e OPENAPI_TOKEN="$OPENAPI_TOKEN" docs.js
~~~

The thresholds in the example are illustrative values showing how to configure them. Replace them with your system's SLO or acceptance thresholds. Do not treat a one-second p95 as a universal standard for every OpenAPI document.

## 10. Measuring Business APIs with a Separate Script

Create business.js using the same virtual user count, duration, and load generator:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '60s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
};

export default function () {
  const response = http.get(
    __ENV.BASE_URL + '/api/orders'
  );

  check(response, {
    'business API returns 200': (r) => r.status === 200,
    'business response is JSON': (r) =>
      String(r.headers['Content-Type'] || '').includes('application/json'),
  });

  sleep(1);
}
~~~

Run separately:

~~~bash
k6 run -e BASE_URL=http://localhost:8080 business.js
~~~

If the business endpoint requires authentication, add the corresponding header and use the same token policy across runs. If the API is a POST or needs query parameters, adjust the request accordingly and use deterministic payloads.

Run docs and business in two independent passes first. Keep VU count, duration, sleep, network, and load generator host identical for a fair comparison. The p95 thresholds of the two endpoint types can differ because their purposes and SLOs differ.

## 11. Do Not Mix Load on the First Measurement

A measurement workflow can consist of three phases:

~~~mermaid
flowchart TD
    A[Prepare fixed environment] --> B[Measure OpenAPI endpoint separately]
    B --> C[Measure business API separately]
    C --> D[Compare baselines and response sizes]
    D --> E[Run mixed workload]
    E --> F[Observe cross-impact and resource usage]
~~~

Only in the final phase do you run docs and business concurrently to answer whether documentation load degrades business API quality. Starting with mixed load makes it difficult to tell which endpoint creates CPU, allocation, or network pressure.

In a mixed workload, keep request ratios close to production. If documentation is only downloaded a few times per hour, do not send docs requests at the same rate as business requests unless intentionally stress-testing an extreme scenario.

## 12. Measuring JSON, YAML, and Each Group Separately

OpenAPI JSON and YAML carry the same contract meaning, but serialization cost and transfer size can differ. Measure separately:

- /v3/api-docs
- /v3/api-docs.yaml
- /v3/api-docs/{group}
- /v3/api-docs.yaml/{group}

If an application has multiple groups, a small group and a large group can differ in latency and response size. Do not let a small group's results represent the entire documentation surface.

To compare properly:

1. Keep the same instance and warm-up state.
2. Call each endpoint with the same request count and concurrency.
3. Record status, content type, response bytes, and latency.
4. Verify the proxy does not cache one endpoint while forwarding the other.
5. Repeat enough times to distinguish network jitter from steady trends.

## 13. Monitoring Server-Side Metrics with Micrometer

Spring Boot Actuator and Micrometer can provide HTTP server metrics such as http.server.requests. Tags typically distinguish method, URI, status, outcome, and exception. Use server-side metrics to verify whether the docs endpoint actually creates additional processing time or errors inside the application.

Example histogram configuration for HTTP requests:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

Depending on the metrics backend, additional percentiles, histogram buckets, or scrape intervals may need configuration. Not all metrics systems calculate p95/p99 identically.

If the Actuator metrics endpoint is enabled, you can query http.server.requests and filter by the corresponding URI tag. Example:

~~~text
/actuator/metrics/http.server.requests
~~~

Inspect the uri tag values in the metric response to determine the actual value for /v3/api-docs. Do not assume tags always preserve the full raw URL; frameworks commonly normalize URIs to avoid high cardinality.

Only expose metrics endpoints on an administrative network or protect them with appropriate authentication. Never expose all of Actuator to the public Internet just for benchmarking.

## 14. Measuring CPU, Heap, Allocation, and Garbage Collection

When an OpenAPI document is large or regenerated frequently, CPU and allocations can rise. Cost sources may include:

- Analyzing mappings and annotations.
- Building OpenAPI models and schemas.
- Applying customizers, filters, and group configurations.
- Serializing objects into JSON/YAML.
- Compressing responses or transferring large payloads.

Monitor CPU, heap, allocation rate, GC pauses, and RSS over the same window as the load test. If latency rises alongside CPU, inspect a profile to find CPU-intensive methods. If heap grows sharply or GC runs frequently, check object allocations and document size.

Java Flight Recorder (JFR) can collect profiles while the application runs on the JVM:

~~~bash
jcmd <pid> JFR.start name=OpenApiDocs settings=profile duration=60s filename=openapi-docs.jfr
~~~

Analyze the JFR file with Java Mission Control or a compatible tool. Capture separate profiles while loading only docs and while loading only business APIs to easily distinguish hot methods between the two workloads.

JFR is a diagnostic tool; avoid enabling heavier profiling than necessary during baseline latency measurements if profiler overhead alters results.

## 15. Analyzing Response Size and Document Complexity

An OpenAPI document can grow gradually as the API module adds:

- Paths and operations.
- Request/response schemas.
- Shared components.
- Examples and lengthy descriptions.
- Security schemes and groups.
- External documentation or extensions.

Record response size alongside path count, operation count, and component schema count. This helps distinguish a document that is slow due to complex schema generation from one slow due to transferring many bytes.

If JSON/YAML is large, verify HTTP compression at the server/proxy and whether the client supports gzip. Measure both compressed response size over the network and uncompressed document size if evaluating serialization cost. Never compare byte counts from one compressed run against another uncompressed run.

## 16. Separating Application Cost from Network Cost

Client-side measurements typically include:

- DNS lookup.
- TCP connection.
- TLS handshake.
- Reverse proxy/gateway.
- Server processing.
- Response transfer.

If you need to measure the endpoint directly, run the load generator near the server or in the same network zone and document its placement. If you need to measure client experience, use the public URL through the same proxy/TLS path as production.

Take two perspectives:

| Perspective | Measurement Method | Question Answered |
|---|---|---|
| Client perspective | k6/curl calling public URL | How long does a user/tool take to receive the document? |
| Server perspective | Micrometer, tracing, JFR | How many resources and processing time does the app spend? |

Do not subtract two numbers from different tools or different timestamps to deduce exact network latency. Separating time accurately requires tracing or synchronized instrumentation.

## 17. Controlling Concurrency and Load Levels

Increase virtual users in steps to observe where degradation begins:

| Level | Example VUs | Purpose |
|---|---:|---|
| Smoke | 1 | Verify endpoint and test script |
| Low | 2–5 | Low-load baseline |
| Medium | 10–20 | Observe concurrent request handling |
| High | 50+ | Find limits in a controlled test environment |

These are reference levels only. Choose concurrency based on expected client counts and environment capacity. Do not ramp up load directly in production without proper planning, limits, and monitoring.

Docs endpoints may not be designed to sustain the same throughput as business APIs. The goal of measurement is to know current capacity and impact, not to force both endpoints to achieve identical RPS.

## 18. Accounting for HTTP Caching and Springdoc Caching

When measuring through a reverse proxy, CDN, or gateway, responses may be cached outside the application. To verify whether requests reach the server:

- Track server-side request counts.
- Inspect response headers such as Age, Via, Cache-Control, or proxy-specific headers if available.
- Compare the public URL with the internal URL in a test environment.
- Use production-like cache settings when benchmarking real user experience.

Do not arbitrarily add long-lived HTTP caching policies for documentation just to lower latency. OpenAPI documents can change across deployments and can vary by group, profile, hostname, or security context. If HTTP caching is used, define appropriate TTLs and invalidation so clients do not receive stale documentation.

Springdoc caching and HTTP caching operate at two different layers:

| Cache Layer | Effect |
|---|---|
| In-application cache | Reduces work of building the OpenAPI document inside the process |
| HTTP/proxy cache | Can return responses without calling the application process |

Measure and report both cases separately when both exist.

## 19. Interpreting Results When Docs Are Slow

| Symptom | Possibilities to Check |
|---|---|
| First hit is slow, subsequent requests are fast | Warm-up, lazy initialization, or caching |
| High TTFB, small response size | Server processing before writing response |
| Low TTFB, high total time | Large document, compression, or network throughput |
| CPU spikes when fetching docs | Model creation, customizers, reflection, or serialization |
| Heap/allocations grow and GC is frequent | Large document or repeated object creation |
| JSON is noticeably faster than YAML | Serializer cost or YAML configuration |
| Docs are slow but business APIs remain stable | Isolated documentation cost without major contention |
| Business p95 rises when docs run concurrently | Both workloads contend for CPU, heap, connections, or network |
| High client latency but low server duration | Network, proxy, TLS, or load generator |
| Server request count is lower than client request count | Possible proxy caching, blocked requests, or mismatched metrics filter |

These are hypotheses for investigation, not automatic conclusions. Confirm with server metrics, tracing, or profiles before changing configuration.

## 20. Mistakes That Skew Benchmarks

- Measuring Swagger UI instead of JSON/YAML endpoints.
- Measuring a single request and treating it as steady-state latency.
- Mixing cold-start with steady-state samples.
- Running docs and business concurrently from the very first baseline.
- Using an underpowered load generator or running it on the same machine as the server.
- Comparing two environments with different CPU/memory limits.
- Failing to record response size or gzip status.
- Allowing proxy caching in one run while bypassing cache in another.
- Ignoring HTTP status; 401/403/500 responses still get recorded as latency samples.
- Setting concurrency far beyond realistic workload and using results to predict normal experience.
- Reporting only averages while ignoring p95/p99 and error rates.
- Changing caching, logging, or instrumentation between two runs.

## 21. Repeatable Benchmark Procedure

1. Record application, JDK, and springdoc versions, CPU/memory limits, and proxy configuration.
2. Select the JSON/YAML docs endpoint and a representative business API.
3. Verify both endpoints return expected status, content type, and payload.
4. Run a smoke test with curl.
5. Start a fresh instance and measure the first-hit separately.
6. Warm up the JVM and endpoint, then measure steady-state docs.
7. Run the business endpoint with the same load profile and duration.
8. Record p50, p95, p99, RPS, error rate, and response size.
9. Collect CPU, heap, allocation, GC, and server-side HTTP metrics.
10. Run JSON, YAML, and separate groups if needed.
11. Run a mixed workload at a ratio close to production.
12. Repeat measurements to verify stability and archive scripts/configurations alongside results.

Do not change multiple variables at once. To compare caching on vs. off, run two separate passes with identical workload and environment.

## 22. Sample Results Report Table

Results can be recorded in a table like this:

| Environment | Endpoint | Cache | VUs | p50 | p95 | p99 | RPS | Error rate | Bytes |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Test | /v3/api-docs | On | 5 | — | — | — | — | — | — |
| Test | /v3/api-docs.yaml | On | 5 | — | — | — | — | — | — |
| Test | /api/orders | On | 5 | — | — | — | — | — | — |
| Test | Mixed workload | On | Per profile | — | — | — | — | — | — |

Also record:

- Commit/build ID.
- Spring Boot, springdoc, and JDK versions.
- CPU/memory limits and replica count.
- Public or upstream URL.
- Compression and proxy cache settings.
- Warm-up duration and test duration.
- Load generator placement.
- Timestamp and notes on anomalies.

Do not fill the report with hypothetical numbers. Only record measurements taken from a real benchmark environment.

## 23. Choosing Optimizations After Measurement

Only optimize once a bottleneck is identified:

- If first-hit is the issue, review startup/readiness and when documentation is accessed.
- If repeated requests still consume CPU, check springdoc caching and whether customizers re-run.
- If the document is too large, review groups, schemas/examples, and redundant descriptions; do not delete contract details solely to save bytes.
- If network transfer dominates, evaluate compression and bandwidth.
- If business p95 increases during concurrent docs traffic, consider rate-limiting docs fetches, scaling instance resources, or distributing static artifacts.
- If a proxy serves stale documents, review cache TTL and post-deploy invalidation.

Every change requires re-benchmarking both the docs endpoint and business APIs. An optimization that speeds up docs while raising CPU or worsening business p95 may not be a net improvement.

## 24. Design Principles

- Measure /v3/api-docs and /v3/api-docs.yaml separately from business APIs.
- Separate first-hit, cold-start, and warm steady-state.
- Record p50/p95/p99, throughput, error rate, and response size.
- Combine client-side latency with server metrics and profiling.
- Measure each group when document sizes differ.
- Keep environment, cache, compression, and network conditions constant across comparisons.
- Measure mixed workloads only after establishing separate baselines.
- Do not use Swagger UI load time as a proxy for OpenAPI document generation.
- Do not use WebTestClient integration tests as a load testing tool.
- Only optimize after identifying a bottleneck through metrics or profiles.
- Save scripts, configuration, and build IDs so benchmarks remain repeatable.

## Conclusion

Documentation endpoints and business APIs have distinct load characteristics, so separate baselines are essential before evaluating overall impact. Measure JSON/YAML endpoints directly with curl for smoke checks and use k6 or a load testing tool for concurrency; separate first-hit from warm steady-state, and record latency percentiles, throughput, error rates, and response sizes. Combine Micrometer/Actuator, CPU, heap, GC, and JFR to distinguish in-application processing costs from network costs. Finally, run a mixed workload to determine whether fetching OpenAPI documents affects business APIs.

## References

- [springdoc-openapi documentation](https://springdoc.org/)
- [Spring Boot Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [k6: Test types and load testing](https://grafana.com/docs/k6/latest/testing-guides/test-types/)
- [k6: Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)
- [curl: Write-out variables](https://curl.se/docs/manpage.html#-w)
- [Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/using-jdk-flight-recorder.html)
