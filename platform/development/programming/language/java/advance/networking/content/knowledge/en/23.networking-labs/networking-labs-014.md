# Writing Conclusions from Measurement Data and Distinguishing Evidence from Speculation

*Java Advance – networking · Track: Networking Labs · Java 17+*

## 1. What must a good conclusion be able to state?

In networking labs, learners often measure ping, HTTP latency, throughput, error counts, or timeout rates and immediately write: "the new version is faster", "the network is slow", "TCP is dropping packets", "TLS causes delay", or "the server can handle 10,000 users". These statements **may be hypotheses**, but they do not become conclusions simply because there are a few numbers.

A proper report needs to distinguish:

1. **Observation:** what was measured/recorded under specific conditions, for example "in 12 trials with the illustrative dataset, version A had 10 status 200 responses, one status 503, and one timeout".
2. **Evidence:** observation accompanied by source, tool, measurement method, time, conditions, sample size, integrity, and reproducibility.
3. **Inference:** what we deduce from the evidence, for example "the completed requests of B had a lower median than A in this sample".
4. **Hypothesis:** an explanation or prediction that needs testing, for example "connection reuse configuration reduces HTTP completion time".
5. **Bounded conclusion:** a statement supported by evidence, **explicitly stating its scope and uncertainty**.
6. **Recommendation/decision:** a change or follow-up measurement based on results and risk, not equated with a proven fact.

**Golden rule:** "Measured X" does not automatically prove "Y caused X", "every environment has X", or "X will continue to occur under a different load".

~~~text
Experimental question
       |
       v
Hypothesis + measurement criteria + test plan
       |
       v
Record raw observations / metadata / errors
       |
       v
Controlled cleaning + statistical analysis
       |
       v
Specific evidence (n, units, conditions, distributions)
       |
       v
Compare against hypothesis and alternative explanations
       |
       v
Bounded conclusion + uncertainty + limitations
       |
       v
Decision / next trial / independent verification
~~~

The goal of this lesson is not to "make a data table look convincing", but to turn a networking measurement into **a testable, falsifiable, and non-misleading argument**.

## 2. How does evidence differ from speculation?

| Statement type | HTTP networking example | How far can it be claimed? |
|---|---|---|
| **Recorded fact** | "Trial #17, GET /ping received HTTP 200 and a 4-byte body." | Accurately describes the record and measurement method |
| **Aggregate metric** | "Out of 100 requests, 98 succeeded, 2 timed out." | True for the 100 recorded trials, if no samples were dropped |
| **Observed comparison** | "The median of successful responses for B is 13.5 ms, for A is 14.5 ms." | Only within the sample and the definition of success |
| **Hypothesis** | "B is faster because keep-alive is enabled." | Requires an experiment isolating connection reuse |
| **Insufficient-data speculation** | "p95 decreased so B is definitely more optimal in production." | Insufficient: different load, errors, small sample, confounders |
| **Causal judgment** | "503 occurred because ThreadPoolExecutor had too few threads." | Needs metrics/executor traces proving the bottleneck |
| **Prediction** | "B will maintain low p95 at 500 concurrent users." | Needs a load test at that concurrency level |
| **Bounded conclusion** | "Across 5 runs on the test host, B had a lower median; there is not yet strong enough evidence to attribute this to the new configuration." | Has evidence and acknowledges uncertainty |

### 2.1. How to write a responsible conclusion

Instead of:

> B is 50% faster than A thanks to HTTP/2, so deploy B to production immediately.

Write:

> Under the same 100 RPS load configuration, on a single test host, across 5 independent runs, the completion time **of successful requests** in B had a lower median than in A. However, the test did not isolate HTTP/2 from connection pooling, the error rates in the two versions still differed, and production load was not measured. The results currently **support the hypothesis that B has lower latency under the test conditions**, without confirming the cause or the benefit in production.

The numbers "100 RPS, 5 runs" in the sample sentence **are only for illustrating how to draft a report**, not results from the Java program in this lesson.

### 2.2. Three verbs to use accurately

- **"Observed"**: when referring to direct data.
- **"Consistent with / supports the hypothesis"**: when results align with one explanation while alternatives remain.
- **"Proves causality"**: use only very cautiously when experimental design and exclusion of confounders are truly strong enough; in real-world noisy operations, usually use "there is causal evidence under the assumptions ...".

Do not "bypass" uncertainty by completely omitting the measurement conditions. A result accurate to 6 decimal places can still point to **the wrong conclusion**.

## 3. Start from a testable question

A good question specifies **the subject, measurement, comparison conditions, and decision criteria**.

| Vague question | Testable question |
|---|---|
| "Is the server fast?" | "With 20 clients maintaining 10 concurrent requests per client, does a 1 KiB HTTP GET have an end-to-end p95 below 100 ms?" |
| "Is HTTP/2 better than HTTP/1.1?" | "On the same host/path/TLS/payload, at concurrency 50, how do p95 completion latency and request success rate differ?" |
| "Does the proxy cause slowness?" | "Keeping origin/payload/client constant, when enabling the proxy, how much do the connect phase and full-response latency change?" |
| "Does DNS cause errors?" | "Among failed attempts, how many are `UnknownHostException` errors and how many are TCP connect errors?" |
| "Is the cache effective?" | "For labeled hits/misses, how do full-response bytes/s and elapsed time differ after warmup?" |
| "Can the server handle 1,000 users?" | "With a defined traffic mix, session model, and SLA, how much RPS/concurrency can the system sustain before p95 or error rate exceeds the threshold?" |

**Do not start with the conclusion you want to write and then pick a convenient metric.** Choose hypotheses, metrics, sample size, and analysis decisions **before seeing the results**, whenever possible.

## 4. Define the metric clearly: what is being timed?

In networking, "latency" has many meanings:

~~~text
Client starts operation
    |
    +-- DNS lookup (may use cache)
    +-- TCP connect (may reuse socket, thus skipped)
    +-- TLS handshake (may use session resumption or connection reuse)
    +-- write request bytes
    +-- network transit + server queue + server processing
    +-- receive HTTP response headers       <-- TTFB-like point
    +-- receive/decode full response body    <-- Full completion point
    |
Client operation complete
~~~

**TTFB (time to first byte)**, header receipt time, and **full body receipt time** are not necessarily equal. With streaming, a server can send 200 headers after 5 ms and then take 40 seconds to finish sending the body. Writing "latency 5 ms" without stating the measurement endpoint makes the conclusion meaningless.

### 4.1. Table of common metrics

| Metric | Definition to state in the report | Pitfalls |
|---|---|---|
| TCP connect time | From before the connect operation until TCP connection succeeds, per the tool | Are DNS/proxy/TLS included in the measurement window? |
| DNS resolve time | Hostname lookup time | Did cache and resolver policy change? |
| TLS handshake time | From start to completion of the TLS handshake | Full handshake differs from resumption |
| Headers latency | From operation start until headers are received | The body may not have arrived yet |
| Full-body latency | From before sending the request until the body completes | Must state body handler/stream consumption |
| RTT | Round-trip of a packet/ping or specified protocol | ICMP ping does not represent HTTP latency |
| Throughput | Total bytes/second or requests/second | Which bytes, at which layer, are retries counted? |
| Goodput | Useful payload/second | Not equal to TCP line rate |
| Error rate | Failed attempts / total attempts | Do not drop timeouts/503s from the denominator |
| Timeout rate | Timed-out attempts / attempts | Client timeout may differ from server limit |
| Concurrency | Number of operations active simultaneously | Not RPS |
| Tail latency | p95/p99 over a predefined observation set | Small samples and filtering can distort the tail |

In `java.net.http.HttpClient`, `BodyHandlers.ofByteArray()` collects the entire response body into a `byte[]` before the response completes. With `BodyHandlers.ofInputStream()`, `HttpResponse<InputStream>` may be returned **before the body is fully read**. Timing around `send(...)` must be described according to the **specific BodyHandler**, not generalized across all body types.

### 4.2. Resolution and clocks

Java's `System.nanoTime()` provides a high-resolution time source **that should only be used to compute elapsed time**, not as a wall clock or cross-process clock. Per the Java SE 17 Javadoc:

~~~java
long start = System.nanoTime();
// Perform an operation to be measured.
long elapsedNs = System.nanoTime() - start;
double elapsedMs = elapsedNs / 1_000_000.0;
~~~

**Do not use two `nanoTime` values collected from two different JVMs/machines to directly compute network one-way latency.** The origin of the time source is arbitrary. The nanosecond unit of the API **does not guarantee true nanosecond-level resolution**. Use `Instant.now()`/wall clock for timestamps linking experimental events; use `nanoTime()` *deltas within the same JVM* for duration.

Additionally, client-side timing includes many components: scheduling, request construction if inside the measured window, queuing, DNS if uncached, TCP/TLS if not reused, server time, network, body reading, and body handler. It **does not automatically isolate server processing time**.

## 5. p50, p95, p99, mean, and variability

Given a list of latencies of **successful responses**, one can compute:

- **Mean**: total time / sample count; sensitive to outliers.
- **Median (p50)**: midpoint of the sorted distribution; for even n, usually the average of the two middle positions.
- **p95/p99**: tail percentiles; must state **the calculation method** because libraries use different interpolation/ranking rules.
- **Min/max**: observed bounds; max may be due to a rare event and does not replace p99.
- **Distribution/histogram**: represents load/distribution better than a single number.
- **Error/timeout rates**: should be reported alongside latency, because counting only successful responses causes survivor bias.

### 5.1. Intentional synthetic data example

A **synthetic dataset for learning how to draw conclusions**, not collected from a real network:

~~~text
A (10 successes, ms): 10,11,12,13,14,15,16,17,18,100
B (10 successes, ms):  9,10,11,12,13,14,15,16,17,19

A: 12 attempts = 10 success + 1 HTTP 503 + 1 timeout
B: 12 attempts = 10 success + 2 HTTP 503 + 0 timeout
~~~

Using **nearest-rank percentile** with rank = `ceil(p*n)` (sorted ascending, 1-based):

| Metric | A | B | What is permitted to say |
|---|---:|---:|---|
| Attempts | 12 | 12 | Equal number of attempts |
| HTTP 200 | 10 | 10 | 10/12 = 83.3% success |
| HTTP 503 | 1 | 2 | B has more 503s in the sample |
| Timeout | 1 | 0 | A has one timeout in the sample |
| Median success latency | 14.5 ms | 13.5 ms | B is 1.0 ms lower on successful samples |
| p95 nearest-rank success latency | 100 ms | 19 ms | B is lower in the sample calculation |
| Failure proportion | 2/12 | 2/12 | Same 16.7% unsuccessful attempts |

**Do not conclude** "B reduces p95 by 81%, definitely better for production". With 10 successful samples, nearest-rank p95 **is simply the maximum value** (rank `ceil(0.95*10)=10`). Changing just one outlier changes p95 dramatically. Moreover, B had two HTTP 503s while A had one 503 and one timeout: the failure mechanisms differ, and failure latencies are not included in the success percentiles.

### 5.2. Selection bias when keeping only completed requests

Scenario:

~~~text
A: 100 requests -> 80 succeeded (all fast), 20 timed out
B: 100 requests -> 99 succeeded (slower), 1 timed out
~~~

If you only plot the latency of the 80 successful requests in A and say "A is faster", you may inadvertently **erase the 20 worst requests**. You must report `attempts, successes, HTTP errors, timeouts, cancellations` using the same denominator, alongside successful latency. A timeout is **censored** data at the test limit: it proves non-completion before the deadline, without providing the true completion time.

**Do not silently replace timeouts with 0 ms**, nor assign them 1000 ms and call that observed latency. If you want "effective latency with failures" or SLO violations, define a separate metric upfront and explicitly state how censored observations are handled.

### 5.3. Small n cannot reliably measure the tail

For p99 analysis, 10 samples is obviously insufficient; even with 100 samples, nearest-rank p99 relies near the very end of the list so uncertainty can be huge. In real traffic with bursts/autocorrelation, "100 consecutive requests" is not the same as 100 independent samples. You need many samples, **multiple runs**, coverage across load levels, and appropriate error analysis.

**There is no magic number n** that guarantees accurate p95/p99 in every system; sample size also depends on variance, the effect size to detect, error probability, independence, and confidence requirements.

## 6. Distinguishing correlation from causation

Seeing lower latency in B than A does not prove **the single change** in B is the cause. Many confounding variables exist:

| Confounder group | Examples | Impact on the claim |
|---|---|---|
| JVM warmup | JIT compilation, class loading, GC | B running later may benefit from JVM state |
| Caches | DNS cache, HTTP keep-alive, TLS session resumption, OS page cache | Later requests often differ from initial requests |
| Network | RTT, packet loss, congestion, route, proxy | Differences come from the network path |
| Server state | Queue length, thread pool, DB connection pool | Requests must wait downstream |
| Payload | Request/response byte size, JSON shape, compression | Different amount of data transferred |
| Protocol | HTTP/1.1 vs HTTP/2, keep-alive, redirect | Multiple factors change simultaneously |
| Concurrency | 1, 10, 100 in-flight requests | Latency and error rate vary with load |
| Resource limits | CPU throttling, memory, kernel socket buffers, open FDs | Increases latency tail |
| Clock/instrumentation | Clocks on different machines, different start/end points | Comparing mismatched metrics |
| Environment | JDK patch level, OS, TLS settings, proxy config | Results are not under identical conditions |
| Order/time | A measured in the morning, B measured after evening restart | Time-of-day confounding |
| Measurement overhead | Debug logs, JFR, packet capture enabled on one branch | Measurement tools alter performance |

To strengthen causal evidence:

1. **Change only one primary variable** when possible, e.g., enabling/disabling keep-alive with the same client JDK, endpoint, payload, and load.
2. **Interleave/randomize execution order**: A-B-B-A or random blocks, rather than always running all of A then all of B.
3. **Equivalent warmup** and separate pre/post-warmup measurements; if cold-start is the subject of study, measure cold-start separately instead of discarding it.
4. **Repeat across multiple time blocks and environments**, recording run IDs so independent runs are not conflated with dependent requests.
5. **Keep and record failures**, avoiding counting only successful requests.
6. **Use confidence intervals / uncertainty analysis** if the conclusion requires statistical confidence; do not turn a single run into universal evidence.

Perfect randomization/control is not possible in some production tests; in those cases, explicitly state that this is **observational evidence**, not phrased as a controlled causal experiment.

## 7. Designing a repeatable network experiment

A test plan should be written before running. Template:

| Plan attribute | What to record |
|---|---|
| Research question | What is being compared? E.g., HTTP/1.1 vs HTTP/2 at fixed load |
| H0 / H1 | H0: no difference on the chosen metric; H1: directional change exists |
| Primary metric | E.g., p95 full-body latency among successful requests |
| Reliability guardrail | E.g., `success_rate >= 99.9%` under described load conditions |
| Secondary metrics | p50, p99, RPS, bytes/s, 4xx/5xx/timeouts |
| Load model | Open/closed loop, RPS, concurrency, ramp-up, duration |
| Payload/URL | Same URI template, body size, HTTP method, response expectations |
| Network scope | Loopback/LAN/WAN, DNS/proxy/TLS, geographic region |
| Environment | Host/CPU/memory, OS, JDK version, flags, container limits |
| Client settings | HttpClient version, pooling/reuse, timeouts, redirects |
| Server settings | Thread pools, executors, rate limits, data source |
| Warmup | Number of requests/time and how excluded from measured sample |
| Trial ordering | Randomized/interleaved/paired |
| Data capture | CSV/JSON schema, units, error categories, timestamps, run ID |
| Analysis plan | Percentile convention, confidence intervals, outlier policy |
| Decision threshold | Minimum meaningful improvement and allowable error impact |
| Stop conditions | Overload, rising errors, production impact limits |
| Security | Do not log credentials/full tokens/raw private URLs |

Conditions may not be completely fixed; what matters is **recording which variables were controlled and which were not**. Do not claim an experiment is "fair" just because it ran on the same laptop.

### 7.1. Open-loop vs. closed-loop load

- **Closed-loop**: a set of virtual users/concurrent clients wait for a response to finish before issuing the next request. When the server slows down, **the request issuance rate drops automatically**.
- **Open-loop**: requests are issued on a preset schedule/rate without waiting for prior requests to finish. If load exceeds capacity, **queue length and latency can grow rapidly**.

If you measure a system with closed-loop and claim "handles 1,000 RPS" while the test actually only issued 400 RPS under overload, the conclusion does not reflect incoming demand. Explicitly record **offered load, achieved throughput, drop/error rate, concurrency, and queueing**.

### 7.2. Independent runs and condition labels

Sample configuration log:

~~~yaml
experiment_id: http-compare-2026-11-01
run_id: run-03
variant: candidate
environment: controlled-lab
network: loopback
java_version: "17"
http_version: "HTTP/1.1"
method: GET
route_template: /ping
request_body_bytes: 0
expected_response_bytes: 4
warmup_requests: 3
measured_requests: 5
timeout_ms: 3000
metric: elapsed_client_nanoTime_to_full_body
latency_unit: ns
analysis: descriptive_only
~~~

This is an **illustrative schema example**, not metadata automatically exported by the demo, and it does not prove the running JVM itself is Java 17 (the demo was compiled with `--release 17` but runtime uses the actual JDK version). `java_version` should be obtained from the actual running environment rather than hardcoded.

## 8. How to record raw observations sufficiently for auditing

A data record may look like:

~~~csv
experiment_id,run_id,variant,iteration,phase,http_status,error_category,elapsed_ns,body_bytes
exp1,run01,A,1,measured,200,NONE,12000000,4
exp1,run01,A,2,measured,503,HTTP_503,18000000,4
exp1,run01,A,3,measured,,TIMEOUT,,0
~~~

This is a **synthetic example, not CSV generated by the program below**. For a timeout before response, `http_status` and elapsed completion can be left blank or **duration until timeout** stored in another field, without pretending to know when the server finished. If status 503 is received, record it as an **HTTP error response**, not lumped into `IOException`.

Each record should have:

- Specific units: `elapsed_ns` is nanoseconds, `elapsed_ms` is milliseconds; do not mix.
- Run ID, variant, iteration, warmup/measured phase.
- HTTP status **if present**, error class/category, and termination reason.
- Message/body size and protocol/connection state if actually measured.
- Wall-clock timestamp with timezone for log correlation, while duration is measured using monotonic elapsed time.
- Environment/version metadata and config **stored separately or linked via experiment ID**.
- Failed, cancelled, timed-out, and interrupted requests remain in the attempts set.
- Do not store raw secrets, URIs with tokens, cookies, or personal data.

**Data provenance:** save the command, version/revision of the measurement program, schema definition, and processing method. If files are edited/filtered, record **the transformations** and keep a protected raw copy for auditing; a cryptographic checksum/hash can be added to detect unintended file modifications.

### 8.1. A metric log is not a packet trace

A CSV recorded by an HTTP client from `System.nanoTime` is **evidence of client-observed duration**, and does not by itself indicate TCP retransmissions, packet loss, or DNS time. To conclude about packet loss/RTT/server queues, measure accordingly using packet capture, socket metrics, server instrumentation, or distributed traces with properly understood clock boundaries.

**ICMP ping != TCP connect != HTTP full-body latency.** Do not substitute one metric for another without explaining the relationship.

## 9. Java 17: complete experimental program

The following example does **two separate things**:

1. Analyzes a **synthetic dataset** A/B with 12 attempts per side, including HTTP 200, HTTP 503, and timeout. It prints the exact median and p95 according to the stated formula, but **this is not a real benchmark**.
2. Creates a **loopback 127.0.0.1** HTTP server using `jdk.httpserver`, uses JDK 17's `HttpClient` to make 3 warmup requests (excluded from data), and then measures **5 real requests** using `System.nanoTime()`. `BodyHandlers.ofByteArray()` ensures the body is collected when `send` returns. Actual latency results vary, so default stdout only reports validity and sample count; enable `--csv` to print the actual `elapsed_ns` values, **without pretending to have fixed stdout latencies**.

**Limitations:** five loopback trials only verify the measurement pipeline, **cannot be used to conclude production performance**, and the synthetic data only illustrates how to analyze/write conclusions.

### 9.1. File EvidenceInferenceDemo.java

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class EvidenceInferenceDemo {
    record Trial(int status, double elapsedMs, boolean timeout) {}
    record Sample(int iteration, int status, long elapsedNs, int bodyBytes) {}

    static double median(List<Double> numbers) {
        List<Double> sorted = new ArrayList<>(numbers);
        sorted.sort(Double::compare);
        int n = sorted.size();
        if (n == 0) throw new IllegalArgumentException("No successes");
        return n % 2 == 0
                ? (sorted.get(n / 2 - 1) + sorted.get(n / 2)) / 2
                : sorted.get(n / 2);
    }

    static double nearestRank(List<Double> numbers, double probability) {
        List<Double> sorted = new ArrayList<>(numbers);
        sorted.sort(Double::compare);
        if (sorted.isEmpty() || probability <= 0 || probability > 1) {
            throw new IllegalArgumentException();
        }
        return sorted.get((int) Math.ceil(probability * sorted.size()) - 1);
    }

    static List<Trial> trials(double[] successes, int http503, int timeouts) {
        List<Trial> rows = new ArrayList<>();
        for (double millis : successes) rows.add(new Trial(200, millis, false));
        for (int n = 0; n < http503; n++) {
            rows.add(new Trial(503, 30, false));
        }
        for (int n = 0; n < timeouts; n++) {
            rows.add(new Trial(0, 200, true));
        }
        return rows;
    }

    static double printSummary(String name, List<Trial> rows) {
        List<Double> successes = new ArrayList<>();
        int http503 = 0, timeouts = 0;
        for (Trial row : rows) {
            if (row.status() == 200) successes.add(row.elapsedMs());
            if (row.status() == 503) http503++;
            if (row.timeout()) timeouts++;
        }
        double med = median(successes);
        double p95 = nearestRank(successes, 0.95);
        System.out.printf(Locale.ROOT,
                "%s attempts=%d ok=%d http503=%d timeouts=%d median_ms=%.1f p95_nearest_rank_ms=%.1f%n",
                name, rows.size(), successes.size(), http503, timeouts,
                med, p95);
        return med;
    }

    static List<Sample> measureLoopback() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ping", exchange -> {
            byte[] reply = "PONG".getBytes(StandardCharsets.US_ASCII);
            exchange.sendResponseHeaders(200, reply.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(reply);
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/ping");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(3)).GET().build();

            // Explicit warmup: does not enter the measured data set.
            for (int i = 0; i < 3; i++) {
                HttpResponse<byte[]> warmup = client.send(
                        request, HttpResponse.BodyHandlers.ofByteArray());
                if (warmup.statusCode() != 200) throw new IllegalStateException();
            }

            List<Sample> samples = new ArrayList<>();
            for (int i = 1; i <= 5; i++) {
                long start = System.nanoTime();
                HttpResponse<byte[]> response = client.send(
                        request, HttpResponse.BodyHandlers.ofByteArray());
                long elapsed = System.nanoTime() - start;
                samples.add(new Sample(i, response.statusCode(), elapsed,
                        response.body().length));
            }
            return samples;
        } finally {
            server.stop(0);
        }
    }

    public static void main(String[] args) throws Exception {
        List<Trial> baseline = trials(
                new double[]{10,11,12,13,14,15,16,17,18,100}, 1, 1);
        List<Trial> candidate = trials(
                new double[]{9,10,11,12,13,14,15,16,17,19}, 2, 0);
        System.out.println("dataset=synthetic_not_a_real_benchmark");
        double baseMedian = printSummary("baseline", baseline);
        double candMedian = printSummary("candidate", candidate);
        System.out.printf(Locale.ROOT,
                "observed_median_delta_ms=%.1f%n", candMedian - baseMedian);
        System.out.println("claim=descriptive_only_not_causal");

        List<Sample> measured = measureLoopback();
        System.out.println("loopback_samples=" + measured.size());
        System.out.println("loopback_all_status_200=" + measured.stream()
                .allMatch(s -> s.status() == 200));
        System.out.println("loopback_all_body_4=" + measured.stream()
                .allMatch(s -> s.bodyBytes() == 4));
        System.out.println("loopback_elapsed_positive=" + measured.stream()
                .allMatch(s -> s.elapsedNs() > 0));

        if (Arrays.asList(args).contains("--csv")) {
            System.out.println("iteration,status,elapsed_ns,body_bytes");
            for (Sample s : measured) {
                System.out.printf(Locale.ROOT, "%d,%d,%d,%d%n",
                        s.iteration(), s.status(), s.elapsedNs(), s.bodyBytes());
            }
        }
    }
}
~~~

### 9.2. Compile and run commands

JDK 17 or higher, no external libraries needed. `jdk.httpserver` is a standard module providing the local server:

~~~bash
javac --release 17 --add-modules jdk.httpserver EvidenceInferenceDemo.java
java --add-modules jdk.httpserver EvidenceInferenceDemo
~~~

**Default stdout verified with `javac --release 17` on OpenJDK 24:**

~~~text
dataset=synthetic_not_a_real_benchmark
baseline attempts=12 ok=10 http503=1 timeouts=1 median_ms=14.5 p95_nearest_rank_ms=100.0
candidate attempts=12 ok=10 http503=2 timeouts=0 median_ms=13.5 p95_nearest_rank_ms=19.0
observed_median_delta_ms=-1.0
claim=descriptive_only_not_causal
loopback_samples=5
loopback_all_status_200=true
loopback_all_body_4=true
loopback_elapsed_positive=true
~~~

To output **actual measured values**, run:

~~~bash
java --add-modules jdk.httpserver EvidenceInferenceDemo --csv
~~~

After the default lines, the program prints:

~~~csv
iteration,status,elapsed_ns,body_bytes
~~~

followed by **five lines with `elapsed_ns` varying per run and machine**. These are real measurements from loopback. **Do not copy fixed stdout numbers** or claim those numbers are stable benchmark results. The program was tested in `--csv` mode and returned five records with `status=200`, `body_bytes=4`.

### 9.3. Why must the two data sources not be conflated?

| Source | Role | What can be concluded |
|---|---|---|
| `baseline/candidate` hardcoded arrays | **Synthetic** data to illustrate percentiles and errors | Calculations/reporting logic are accurate for the given arrays |
| `measureLoopback()` | Real elapsed measurement using `nanoTime` around `HttpClient.send` | Five loopback requests recorded with status, body bytes, duration |
| `loopback_all_...=true` lines | Basic integrity checks for the 5 samples | **Does not** prove production p95 or HTTP/2/TLS performance |
| `--csv` | Exports real per-request measurement data | Can inspect and analyze this run; metadata must be preserved |

A **toy** test illustrating a pipeline does not become a production benchmark just because it measures with a high-resolution timer. It does not heavily load the server, nor does it have WAN latency, TLS, typical DNS lookups, packet loss, proxies, or realistic distributions.

### 9.4. Reading the synthetic results properly

- B has a median success latency of 13.5 ms, A has 14.5 ms. **The observed difference is -1.0 ms**. It is unknown whether this is a real improvement or noise, because the data was handcrafted.
- B has nearest-rank p95 of 19 ms, A has 100 ms. Because there are only 10 successes per side, p95 is **the max**, so the number easily creates an illusion of tail performance.
- Both have 10/12 successful attempts. A has 1 timeout + 1 HTTP 503; B has 2 HTTP 503s. Looking only at success latency while ignoring errors can lead to choosing the wrong option.
- One cannot claim "B is more optimal due to keep-alive/HTTP2" because **no A/B technical change was actually implemented and measured in the synthetic dataset**.
- To obtain real evidence, one must run A/B on the same endpoint, under the same load, with sufficient samples, controlled interleaving, and recorded error/timeout categories.

## 10. How to compute effect and uncertainty

A good comparison does not just state "A=20, B=18", but determines **effect size** and uncertainty.

### 10.1. Absolute difference and percentage

~~~text
absolute_difference = metric_B - metric_A
relative_change_pct = (metric_B - metric_A) / metric_A * 100%

Synthetic median example:
A = 14.5 ms
B = 13.5 ms
absolute = -1.0 ms
relative ≈ -6.9%
~~~

**Condition:** percentages are only meaningful when the denominator is reasonable and the metric is consistently defined; if A is near 0, percentage ratios can be very misleading. In particular, do not compute "% faster" from p95 of **two differently filtered success sets** while ignoring error rates.

### 10.2. A confidence interval is not a promise

Confidence intervals can be computed for mean, median, error rate, or effect matching the statistical design. However:

- Sampling procedure, independence, and distribution assumptions determine whether the calculation is trustworthy.
- Consecutive requests can correlate via cache, connection reuse, background load, or queues; bootstrapping individual requests as independent can misestimate uncertainty.
- With repeated experimental runs, one can use **run-level summaries**, paired differences, or block/run resampling when appropriate.
- "95% CI" does not mean "a 95% probability that the fixed parameter lies in the obtained interval" under the standard frequentist interpretation.
- If very few failures are observed, "no errors seen" does not mean the true error rate is 0; an upper bound or more testing is needed.
- p99 from very few samples is unreliable even if the code can still compute a number.

This lesson does not force learners to write statistical tests before having good enough data. First, **define the sample and the sampling process**.

### 10.3. P-value does not replace effect size or reproducibility

A small p-value does not mean the change is operationally large enough; a test with a non-small p-value also does not prove the two versions are identical. In networking, always look at effect size, confidence intervals, error budgets, tail behavior, resource cost, and reproducibility.

In particular, **do not test 30 metrics, pick the "best-looking" metric, and present it as the predefined primary metric**. If analyzing post hoc, label it *exploratory* and require an independent test.

## 11. How to state findings when data contradicts expectations

If B was expected to be faster but measured data shows B has more 503s and higher tail latency, do not "explain it away" by dropping outliers or picking one favorable run.

Good report:

> The hypothesis that B reduces latency is not supported by the data collected in this test. There is variation across runs, but p95 and error rate did not consistently improve. We have not yet identified the cause; queue saturation, GC, and the network path need to be inspected with appropriate instrumentation.

Do not write:

> B is still better because the test machine had noise.

If noise is suspected, that **is a new hypothesis** to test, not a license to dismiss observations.

### 11.1. Absence of evidence is not evidence of absence

- **No difference seen** in a small sample != proof that two versions are equivalent.
- **No timeout seen** in 10 trials != the system never times out.
- **No packet loss seen in client logs** != no retransmission/loss at TCP.
- **No SSLHandshakeException seen** != all clients trust the certificate.
- **One instance of lower p95** != the protocol change caused the improvement.

When the question exceeds what can be proven, state **"insufficient evidence to conclude"** and specify the additional test needed.

## 12. Common misconceptions in Java networking

| Hasty conclusion | Why it is insufficient | Additional evidence needed |
|---|---|---|
| "TCP has no packet loss because HTTP 200." | TCP can retransmit while the request still succeeds | Appropriate TCP metrics/packet capture |
| "TLS causes slowness because HTTPS is slower than HTTP." | TLS may differ in origin, keep-alive, proxy, payload | Isolate handshake/reuse and variables |
| "Server is slow because getResponseCode took 500 ms." | Client timing includes network, DNS, proxy, TLS, queue | Correlated server-side spans/metrics |
| "HTTP/2 is always faster." | Multiplexing helps/hurts depending on load/path and config | Compare under identical conditions across load levels |
| "Lower p95 latency means higher reliability." | Tail latency of successes can hide 503s/timeouts | Success/error/timeout rates with same denominator |
| "100% success so there are no errors." | Small n and unrepresentative traffic | Multiple runs/cases/loads, confidence bounds |
| "0 ms on the clock means an instant request." | Clock resolution/rounding | `nanoTime` delta and sufficiently granular units |
| "JFR shows a GC pause so GC caused all tail spikes." | Merely temporal correlation | Correlate pauses/runs, test under controlled GC |
| "B is faster because B runs executed later." | Warm caches/JIT are a confounder | Order randomization, warmup control |
| "CPU is low so the server is not overloaded." | Bottleneck could be I/O, DB pool, locks | Queue length, blocked time, downstream |
| "One TCP connection = one request." | HTTP/2 multiplexes streams | In-flight requests and separate stream metrics |
| "A timed-out request has 3000 ms latency." | Timeout is a deadline/censoring, completion unobserved | Record timeout category and waited duration separately |
| "Increasing sample count automatically fixes all bias." | Bias from sampling method does not disappear on its own | Proper sampling design and instrumentation |

## 13. Writing an auditable experimental report

Recommended structure in order:

1. **Question and scope:** what needs to be known, why.
2. **Pre-measurement hypothesis/criteria:** primary metric, expected effect, guardrails.
3. **Environment and configuration:** JDK/OS/hardware/network/proxy/TLS/HTTP version/load/payload.
4. **Methodology:** timer start/end points, warmup, number of runs/attempts, variant ordering.
5. **Observed results:** raw IDs, attempt counts, success/error/timeout, distribution, percentile convention.
6. **Comparison:** effect size, uncertainty, consistency across runs.
7. **Limitations:** unisolated confounders, sampling bias, missing data, missing client/server instrumentation.
8. **Bounded conclusion:** statement within scope, without attributing causality when unproven.
9. **Decision/action:** deploy, keep as-is, rollback, or test further; state trigger conditions.

### 13.1. Reusable report template

~~~markdown
# Report: [Experimental Question]

## Scope
Subject, environment, version, time, and traffic model.

## Pre-measurement Hypothesis
H0: ...
H1: ...
Primary metric and success/error guardrail: ...

## Methodology
Tools, measurement points, warmup, n, order, timeout, protocol, payload,
CPU/memory/JDK/network conditions, handling of missing samples.

## Evidence
- Run IDs / data locations / checksum
- Total attempts, 2xx, 4xx, 5xx, timeout, cancel
- Latency p50/p95/p99 and success population definition
- Throughput/error rate and per-run variation
- Instrumentation logs/traces (with sensitive info redacted)

## Observations
Measured figures, with units, samples, and conditions.

## Explanations and Alternative Hypotheses
What fits the data; remaining confounders.

## Bounded Conclusion
We observed ..., under conditions ....
There is not yet evidence to claim ....
Confidence level/limitations ....

## Decision and Next Trials
Actions, owner, verification conditions, and rollback criteria.
~~~

**This is a template for learners to fill in from their real data**; it is not output automatically generated by the program. For a Knowledge lesson, do not replace it with "proven" without an actual test.

### 13.2. Example of rewriting a conclusion from demo data

**Poor:**

> B reduced p95 from 100 to 19 ms, 81% faster, proving cache optimization succeeded.

**Properly scoped:**

> In the **synthetic dataset** of 12 attempts per variant (each side having 10 HTTP 200s), the median latency of successes is 14.5 ms for A and 13.5 ms for B; nearest-rank p95 is 100 ms and 19 ms, respectively. A had one HTTP 503 and one timeout; B had two HTTP 503s. Because this is synthetic data, it only illustrates the calculation. With n=10 successes, nearest-rank p95 equals the max and is not stable enough to infer true tail latency. **There is no evidence from this data that a cache/HTTP/2 change improved performance.** A controlled experiment with sufficient samples, identical load, and clear error categorization is required.

The proper sentence is longer, but it prevents readers from acting wrongly due to misreading a single metric.

## 14. Making decisions under uncertainty

Not every study needs to conclude "A is better than B". There are at least four reasonable outcome categories:

| Situation | Conclusion | Action |
|---|---|---|
| Consistent effect, guardrails met, sufficiently powered test | Evidence supports the change within measured scope | Canary/rollout with monitoring and rollback |
| Effect smaller than practically meaningful | No clear operational benefit seen within test scope | Keep configuration or optimize another area |
| Variable results, rising errors, or missing data | Insufficient evidence to decide | Repeat/redesign experiment |
| Reliability degrades noticeably even if success latency drops | Trade-off unacceptable per guardrail | Prioritize fixing errors and re-verify |

**Do not "cherry-pick the best-looking metric" to ignore the error budget.** If p50 improves but 503s increase, analyze target SLOs and user impact before recommending rollout.

### 14.1. Conclusion confidence also has levels

A useful reporting scale:

- **High within test scope:** clearly defined metrics, enough independent runs, few confounders, supported by confidence intervals/guardrails.
- **Medium:** consistent evidence but limited in traffic mix or duration.
- **Low:** single run, small n, missing failure data, different environment, unclear method.
- **Unable to evaluate:** no raw records/provenance or metrics lost meaning.

This is an **internal descriptive scale**, not a universal statistical standard. Do not convert it into 90%/99% probabilities without a valid quantitative model.

## 15. Suggested next experiments after the demo results

After understanding the synthetic results and loopback pipeline, learners can run a real test (on resources **authorized for testing**, without running unapproved load tests against public APIs):

1. Pick a toggleable change, such as `HttpClient` reuse vs. creating a new client, **while keeping all other factors consistent**.
2. Use a local server with a fixed payload, scale from 5 attempts to a substantial sample size, and split into multiple runs.
3. Log every attempt to CSV: variant, run ID, timestamp, status, exception, elapsedNs, and bodyBytes. Protect sensitive data.
4. Test cold start and warm connections separately; do not mix them.
5. Randomize/interleave A/B ordering and label run/phase.
6. Compare median/tail latency **alongside** success/error/timeout rates and queue/concurrency.
7. After loopback, if network behavior needs study, add LAN/WAN with RTT/proxy/TLS measured separately.
8. Only state causality when supported by instrumentation or a sufficiently isolated design.

**Important note:** continuously creating a new `HttpClient` is not a practice to take to production just to "optimize"; it can be an experimental variable, requiring cleanup/lifecycle management and identical request semantics.

## 16. Common statistical and reporting mistakes

| Mistake | Consequence | How to avoid |
|---|---|---|
| Reporting p95 without stating n/method | Uncomparable and may just be the max of a small n | Record population, n, percentile definition |
| Measuring only successful requests | Hides timeouts/503s, selection bias | Report attempts and failures in full |
| Averaging p95 across runs and calling it global p95 | Percentiles are not linear | Pool raw samples conditionally or report per-run distributions |
| Using `System.currentTimeMillis()` for very short intervals | Resolution/clock adjustment issues | Use `System.nanoTime()` delta |
| Comparing clocks from two unsynchronized machines | Wrong one-way latency | Clock-sync/trace model or measure client end-to-end |
| Different start points for A and B | Cache/JIT/cold-start confound | Standardize measurement points |
| Timing HTTP headers but writing "download complete" | Body not yet consumed | Measure until end of body |
| Excluding cancelled/timed-out attempts | Wrong denominator | Record terminal outcome of every attempt |
| Treating synthetic data as production evidence | Completely wrong conclusion | Clearly label synthetic in data and reports |
| Dropping outliers because they "look ugly" | Tail is distorted | Only exclude per pre-registered rule and also report raw |
| Running many comparisons and picking the small p-value | False positives | Pre-register primary metric/adjust for multiple testing |
| Inferring network causes from a CPU profile alone | Bottleneck may be outside the JVM | Add network/server/queue metrics |
| Forgetting version/config/traffic | Cannot reproduce | Save experiment manifest |
| Using many decimal places | False precision | Precision matching clock/sampling |
| Writing overly certain conclusions | Wrong recommendations/hard to audit | Bounded claims, alternatives, uncertainties |
| Logging raw credentials in logs/CSV | Security risk | Route templates, redaction, synthetic accounts |

### 16.1. Percentiles cannot be arbitrarily added/averaged

If run 1 has 10 samples and run 2 has 10,000 samples, averaging `(p95_run1+p95_run2)/2` gives each run equal weight and **does not equal the p95 of the 10,010 observations**. When a global distribution is needed, compute it from raw samples per the plan, or analyze run-level variability separately. If runs have different loads, do not silently pool them either.

### 16.2. False precision when reporting units

A tool printing latency as `0.783219 ms` does not mean the conclusion is accurate to six decimal places. Timer precision, scheduling, and network noise can be much larger. Record sufficient precision for analysis, but present conclusions with reasonable precision and CI/variability.

## 17. Checklist before signing off on a networking conclusion

**Measurement definition**

- [ ] Question, hypothesis, primary metric, and guardrails recorded before viewing data.
- [ ] Is latency connect, headers, first byte, or full-body? Same units?
- [ ] Using `nanoTime` delta within the same JVM, not mixing clocks across hosts.
- [ ] HTTP status distinguished from transport exceptions and timeouts?
- [ ] Measuring the intended protocol/version/payload/traffic model?

**Completeness and comparison**

- [ ] Are attempts, successes, 4xx/5xx, timeouts, cancels, and dropped requests all included?
- [ ] Outliers/failed requests not arbitrarily dropped.
- [ ] n, number of runs, warmup, concurrency, and order recorded.
- [ ] Cache/JIT/GC/proxy/TLS/DNS/OS confounders checked?
- [ ] Percentile method and dataset population are clear.
- [ ] Confidence interval/uncertainty matches the sampling method.

**Conclusion and action**

- [ ] Every claim is based only on observations within the data's scope.
- [ ] Alternative hypotheses and areas lacking sufficient evidence are stated.
- [ ] Causality is not inferred merely because A/B have different numbers.
- [ ] Effect size, guardrail, and rollout/rollback thresholds included when needed.
- [ ] Follow-up testing direction and reproduction steps included.
- [ ] No tokens, sensitive URIs, or personal data included in raw observations.

## 18. Self-check questions

**1. What is "HTTP GET returned status 200 in 5 loopback requests" evidence of?** It is evidence that those 5 specific requests received status 200 in that test; it does not prove production will always succeed.

**2. Does "B has lower p95 than A" prove B caused the improvement?** No. A design controlling confounders, sufficient samples, and uncertainty analysis are required.

**3. Why must n be reported alongside p95/p99?** Because tail percentiles on small n are extremely unstable.

**4. With n=10 using nearest-rank p95, which element is selected?** The 10th, i.e., the max.

**5. What is the median of successes for A in the demo data?** 14.5 ms.

**6. What is the median of successes for B in the demo data?** 13.5 ms.

**7. Do the two options have the same success rate?** In the synthetic dataset, both are 10/12; however, the error types differ.

**8. Why should timeouts not be removed from attempts?** Because it distorts the success rate and survivorship bias analysis.

**9. Does `getResponseCode` taking 100 ms mean the server processed for 100 ms?** No; client-side time includes network/proxy/TLS/queue and the measurement boundary.

**10. Why is `nanoTime` not used to measure one-way latency between two JVMs?** Clock source origins differ, and there is no wall-clock synchronization.

**11. Can `BodyHandlers.ofInputStream()` cause `send` to finish before the body is completely read?** Yes; one must measure until EOF/close if the goal is full-body time.

**12. Does the demo use HTTP/2 or TLS?** No, it forces HTTP/1.1 on loopback and has no HTTPS.

**13. What misconception does the line `dataset=synthetic_not_a_real_benchmark` protect readers from?** It affirms that the A/B numbers were not measured from a real server.

**14. What is the `--csv` flag used for?** Outputs five real `elapsed_ns` measurements from loopback, whose values vary on every run.

**15. When A runs first and B runs second, what confounders are common?** JIT warmup, caches, connection reuse, background load.

**16. Can per-run p95s be averaged and called the global p95?** No, percentiles do not add linearly.

**17. Does a confidence interval automatically eliminate sampling bias?** No, it must match the sampling design and independence assumptions.

**18. Does seeing no 503s in 20 requests mean the server never returns 503?** No; it was simply not observed in that sample.

**19. What should be done if the data does not support the initial hypothesis?** State it clearly, consider alternatives, and plan additional tests, without discarding unfavorable data.

**20. What does a good conclusion need?** Claim, numbers and scope, conditions, measurement method, uncertainty, limitations, and next steps.

## 19. Official references and further reading

- [Java SE 17 – System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): duration within one JVM; nanosecond precision differs from nanosecond resolution.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, client reuse, HTTP version, and body handling.
- [Java SE 17 – HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofByteArray` vs `ofInputStream` and when the body completes.
- [Java SE 17 – HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout, methods, and URI.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): creating a local HTTP server for testing.
- [Java SE 17 – HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): response status/body and closing.
- [Java SE 17 – Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html): tool for collecting runtime events when deeper JVM observation is needed.
- [OpenJDK JMH](https://github.com/openjdk/jmh): Java micro/macro benchmark harness suited for JVM behavior; **microbenchmarks do not replace** end-to-end networking load tests.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status codes and HTTP request/response semantics.
- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): streams and multiplexing; note that TCP connection count does not equal request count.

**Remember:** A chart only becomes evidence when you know **what was measured, how it was measured, what the sample consists of, and under what conditions**. Clearly state observations, hypotheses, effect sizes, failure rates, uncertainties, and alternative explanations. A good networking conclusion is usually bounded: **"Under conditions X, we observed Y; that supports/does not support Z; we cannot yet claim W; the next test is Q."**
