# Designing Benchmarks Representative of Real Data and Behavior

A benchmark is only valuable when it simulates closely enough how the system will be used. A test sending the same small request repeatedly can yield very high throughput, yet that result does not reflect the service when data varies in size, users send concurrent requests, caches change state, or workloads run across different types of cloud compute.

For compute systems, results also depend on CPU, memory, GPU, storage, network, runtime, containers, data placement, and scaling mechanisms. If the test dataset is too small, the entire dataset may fit in cache; if payloads have only one size, the benchmark misses large cases; if load is generated improperly, measured latency can be much lower than real-world experience.

This lesson guides you through designing benchmarks based on real data and usage behavior, from capturing workload characteristics to generating test data, driving load, measuring, and analyzing results. After this lesson, you can:

- Describe workloads using measurable and reproducible characteristics.
- Select representative test data while protecting sensitive data.
- Simulate size distributions, access skew, locality, and request arrival timing.
- Distinguish between micro, component, and end-to-end benchmarks.
- Choose an appropriate load model, and measure latency, throughput, errors, and resource utilization.
- Design repeatable runs, make fair comparisons, and interpret results meaningfully.

## 1. Start with the Question the Benchmark Needs to Answer

Before creating data or writing scripts, identify the decision the benchmark needs to support. For example:

- Choosing a VM type or CPU/RAM configuration for an image-processing API.
- Comparing two GPU types during model inference across different batch sizes.
- Determining the throughput limit of a worker reading data from object storage.
- Testing the impact of block size and queue depth on storage.
- Evaluating startup time and scale-out capability during sudden traffic spikes.
- Verifying whether a new configuration meets SLOs at an acceptable cost per task.

A good benchmark has a hypothesis and acceptance criteria. For example: "Given the current input image distribution and 120 requests/second, configuration B must keep p95 under 250 ms, error rate under 0.1%, and cost per 1,000 images lower than configuration A." This goal is clearer than "measure which machine is faster."

### Translating Product Requirements into Measurable Criteria

| Requirement | Measurable Metric |
|---|---|
| Fast response | p50, p95, p99 latency |
| Serve many requests | Throughput, requests/second, or tasks/second |
| Process large data | MB/s, GB/s, records/s, images/s, or tokens/s |
| Do not drop requests | Error rate, timeouts, retries, and failed items |
| Maintain quality | Correct results, error margin, model quality, or task success rate |
| Scale well | Scale-out time, warm-up time, and post-scale capacity |
| Cost-effective | Cost per request, per GB, per image, per job, or per million tokens |

Conditions accompanying each metric must be stated explicitly. A throughput of 1,000 requests/second means little if the payload is only 1 KB, the error rate is high, or p99 exceeds service limits.

## 2. Describing Workloads with Real Data

A workload is the combination of input data, how users or systems generate requests, internal processing, and output results. Do not describe a workload solely by average request count or total data volume.

A workload profile should include the following groups of information:

| Group | Characteristics to Record | Example |
|---|---|---|
| Data size | Small/medium/large sizes, record counts, field counts, content length | 70% of images under 300 KB, 25% from 300 KB to 2 MB |
| Access distribution | Popular keys, hot keys, skew across users | 10% of accounts generate 65% of reads |
| Locality | Data accessed repeatedly over time or by region | A hot set of files read repeatedly over 15 minutes |
| Arrival rate | Requests/second, jobs/second, batches over time | 40 requests/second baseline, rising to 180 for 2 minutes |
| Concurrency | Number of sessions, workers, active connections | 300 concurrent sessions, 40 workers |
| Operation mix | Read/write, query, inference, transform, upload/download | 85% reads, 15% writes |
| Operation correlation | Actions frequently occurring in sequence | Login, query, download file, update status |
| Processing time | CPU, GPU, I/O time, dependency waits | 20 ms CPU, 80 ms waiting on database |
| Output | Output size, success rate, quality | 1 input image generates 3 thumbnails |
| Timing | Peak hours, nightly batches, seasonality, bursts | Traffic quadruples at end of day |

### Use Distributions Instead of a Single Average

Suppose an API receives files averaging 500 KB. If the benchmark only uses 500 KB files, it fails to simulate the case where most files are small while a small fraction are very large. Large files can increase transfer time, buffering memory, decoding time, and I/O.

Collect histograms or percentiles such as p50, p90, p95, and p99 for:

- Request and response sizes.
- Number of records returned per query.
- Text length or token sequence length.
- Batch sizes and job runtimes.
- Number of retries and dependencies called.

Distributions can be split into buckets for easier test data generation. Illustrative example for an image API:

| Bucket | Assumed Share | Size |
|---|---:|---:|
| Small | 65% | 50–300 KB |
| Medium | 25% | 300 KB–2 MB |
| Large | 9% | 2–8 MB |
| Very large | 1% | 8–20 MB |

This is an illustrative distribution. Replace it with metrics measured from the target workload and retain the tail of the distribution if it impacts SLOs.

### Modeling Skew and Hot Keys

In many systems, data is not accessed uniformly. Certain accounts, products, files, or partitions receive disproportionate traffic. If a benchmark selects keys uniformly at random, cache hit ratios and lock contention can differ drastically from production.

Identify:

- Share of accesses hitting the most popular group of keys.
- Number of unique keys within a time window.
- Frequency with which a single key is accessed repeatedly.
- Distribution across partitions, shards, tenants, or regions.
- Likelihood of multiple requests writing concurrently to a hot key.

A Zipf-like distribution or sampling from empirical histograms can be used to simulate skew. An exact mathematical model fit is unnecessary if an anonymized and safely sanitized trace can be replayed.

### Simulating Locality and Caching

A benchmark repeating the same dataset may primarily measure cache speed. This is useful if production also has a similarly warm cache, but unsuitable for evaluating cold reads or workloads with large working sets.

Design separate scenarios for:

- **Cold cache:** data is not yet in cache; measures first reads and initialization overhead.
- **Warm cache:** hot dataset is already loaded; measures behavior after the system stabilizes.
- **Large working set:** total frequently accessed data exceeds expected cache capacity.
- **Skewed access:** a small subset of data is accessed very frequently.
- **Churn:** hot data changes over time, forcing the cache to evict and replace entries.

Do not arbitrarily clear caches between runs if the goal is measuring production warm state. Document cache state and how it is prepared in the benchmark manifest.

## 3. Data Collection and Privacy Protection

Data sources can come from application traces, access logs, metrics, query logs, queues, storage statistics, or approved business datasets. Production data is valuable because it reflects real skew and correlations, but it may contain personal information, secrets, tokens, customer content, or protected data.

Before using data:

1. Identify the data owner and benchmark purpose.
2. Select the minimum dataset required for the measurement question.
3. Remove or transform identifiers, tokens, passwords, auth headers, and secrets.
4. Anonymize or pseudonymize join keys in a way that preserves required distributions and relationships.
5. Verify storage policies, processing locations, retention periods, and access permissions.
6. Provide test data only to controlled environments and delete it according to procedure upon completion.

Anonymization is more than replacing usernames. URLs, IP addresses, exact timestamps, free-form text, and combinations of fields can identify a person or organization. When real data cannot be used safely, generate synthetic data with the required structure, distributions, skew, and correlations.

### Generating Controlled Synthetic Data

Synthetic data should preserve characteristics that affect performance:

- Field sizes and lengths.
- Null rates, optional fields, and rare values.
- Key distributions, repetition levels, and access skew.
- Nested structures, cardinality, and relationship counts.
- Compression ratio, entropy, and encoding characteristics.
- Output sizes and serialization/deserialization costs.

For example, a JSON with 10 short fields does not represent a record with deeply nested fields, long arrays, and large text strings. Two files of the same byte size can also have very different compression ratios and parsing costs.

When generating data, fix the random seed so results are reproducible. If multiple datasets are needed, record the seed, generator version, distribution parameters, and checksum of the generated dataset.

Python example generating a list of request sizes by bucket with a fixed seed:

~~~python
import random

random.seed(20261122)

def sample_payload_size():
    bucket = random.random()
    if bucket < 0.65:
        return random.randint(50_000, 300_000)
    if bucket < 0.90:
        return random.randint(300_001, 2_000_000)
    if bucket < 0.99:
        return random.randint(2_000_001, 8_000_000)
    return random.randint(8_000_001, 20_000_000)

sizes = [sample_payload_size() for _ in range(100_000)]
print("count:", len(sizes))
print("min:", min(sizes))
print("max:", max(sizes))
print("mean:", round(sum(sizes) / len(sizes)))
~~~

This snippet only generates sample sizes, not file contents. In an actual benchmark, the generator must produce payloads with matching structure and characteristics, while avoiding making data generation on the load generator a bottleneck.

## 4. Simulating User and System Behavior

Data is only half the workload. How requests arrive, wait times between operations, and concurrency levels can change results dramatically.

### Action Sequences Instead of Isolated Requests

A user typically performs multiple related actions. For example:

1. Open a page or log in.
2. Query a list.
3. Open details of a record.
4. Upload a file or submit a processing request.
5. Update status.
6. Log out or let the session expire.

If a benchmark only calls the list-query endpoint, it misses dependencies and state generated by the action sequence. Describe the proportion of users taking each branch, call counts, think time between actions, and data passed from one step to the next.

### Open Model vs. Closed Model

Two common load generation models generate traffic differently:

- **Closed workload model:** fixes the number of concurrent users or workers. When a request is slow, that worker sends the next request later. This model fits systems with a bounded number of concurrent workers or sessions.
- **Open workload model:** fixes the request arrival rate over time, independent of response time. When the system slows down, requests continue arriving on schedule, fitting external traffic simulations like an API receiving user traffic.

If the goal is evaluating capacity at a fixed arrival rate, an open model usually reflects reality better. A closed model can mask overload because the slower the system gets, the fewer requests are generated. This distortion relates to *coordinated omission*: the load generator fails to record the full wait time real users would experience when requests arrive steadily.

No single model fits every workload. For queue workers, the number of concurrent consumers may be the primary control variable. For an HTTP service receiving independent client requests, arrival rate is usually more important.

### Think Time and Usage Cadence

Users do not send requests continuously without pause. They read results, think, enter data, and navigate pages. Think time alters the request rate per session and concurrency levels.

Use wait-time distributions rather than a fixed interval if real data shows diverse user behavior. Also simulate:

- Short and long active sessions.
- New and returning users.
- Steady background load and short bursts.
- Synchronous tasks and asynchronous batches.
- Retries after errors or timeouts per client policy.

### Load Scenarios Should Have Multiple Shapes

| Scenario | How Load Is Generated | Question Answered |
|---|---|---|
| Baseline | Low, steady load | How does the system behave under light conditions? |
| Typical load | Average load following common distribution | What are cost and latency at typical usage? |
| Peak load | High load over a defined window | Does it maintain SLOs during peak hours? |
| Burst | Rapid increase then decrease | How does the system react to sudden spikes? |
| Stress | Increase beyond expected load | What is the saturation point and does degradation stay controlled? |
| Soak/endurance | Sustained steady load over long duration | Are there memory leaks, queue growth, or degradation over time? |
| Recovery | Reduce load after overload or dependency failure | How quickly and cleanly does the system recover? |
| Scale test | Change number of instances/workers | Is autoscaling fast and effective enough? |

Do not use a stress test in place of a peak test. The goal of peak testing is verifying expected requirements; stress testing finds limits and how the system fails beyond them.

## 5. Choosing the Right Benchmark Level

Benchmarks can be divided into three levels:

### Microbenchmark

Measures a small operation under controlled conditions, for example:

- JSON parsing time with fixed size and structure.
- Encryption or decryption speed for a block of data.
- Matrix operation throughput on a GPU.
- Block read latency from a volume.
- Object serialization cost.

Microbenchmarks help compare components or test a specific hypothesis. They typically exclude networking, orchestration, queues, and dependencies, so they do not represent end-to-end experience.

### Component Benchmark

Measures a component close to real deployment, such as an API service with a test database, a worker reading object storage, or an image-processing container. Component benchmarks are useful for pinpointing bottlenecks within a segment of a pipeline.

### End-to-End Benchmark

Measures the full path of a transaction or job from request arrival until the final result. End-to-end tests must include real components such as load balancers, authentication, queues, databases, object storage, networking, and autoscaling if they sit on the processing path.

Combine all three levels. Microbenchmarks explain root causes, component benchmarks validate interactions among a few components, and end-to-end benchmarks verify whether the system meets product goals.

## 6. Designing Workloads for Different Compute Types

Each resource type has specific characteristics to simulate.

| Compute Type | Data / Behavior Characteristics | Metrics to Measure |
|---|---|---|
| CPU-bound | Record size, algorithm complexity, branch distribution, worker count | Tasks/s, CPU time, utilization, p95 latency |
| Memory-bound | Working set, locality, object size, allocation, and garbage collection | Memory bandwidth, RSS, cache misses, GC pauses |
| Storage-bound | Block size, read/write mix, random/sequential, queue depth | IOPS, MB/s, p95/p99 I/O latency |
| Network-bound | Payload, connection count, RTT, packet size, TLS, bursts | Throughput, RTT, retransmissions, connection errors |
| GPU/accelerator | Model, tensor shape, batch size, precision, sequence length | Samples/s, tokens/s, GPU utilization, VRAM, latency |
| Container platform | Image size, startup time, readiness, replica count, resource limits | Time-to-ready, throttling, restarts, scale latency |
| Serverless | Invocation rate, payload, execution duration, concurrency, cold starts | Duration, cold-start latency, concurrency, cost/invocation |

### CPU-bound

Data must be diverse enough to reflect processing branches and computational intensity. A simplistic input set can let compilers or runtimes over-optimize. Test both single-threaded and multi-threaded execution, concurrency levels, context switching, CPU throttling, and actual CPU usage.

### Memory-bound

Working set size should be compared against RAM, LLC cache, and other caches. If all data fits in cache, results will not represent large working sets. Record allocation rates, garbage collection, page faults, swap, and peak memory usage.

### Storage-bound

Do not test only sequential reads/writes on one large file if the real workload performs many small random accesses. Simulate block size, read/write ratio, queue depth, client count, filesystem, cache policy, and durability settings. If the application requires fsync or durable write confirmation, the benchmark must enable the corresponding behavior.

### Network-bound

Large payloads measure throughput, whereas small payloads with many connections measure per-request overhead and packet processing. RTT, TLS handshakes, connection reuse, DNS, and retries can all impact results. Place the load generator in a network location similar to real users or workloads.

### GPUs and Accelerators

GPU benchmarks require representative tensor shapes, sequence lengths, batch sizes, and precision. For model inference, distinguish prefill and decode where applicable, measuring both per-request latency and tokens/second. For training, keep dataset, step count, optimizer, precision, and distributed strategy identical. Monitor VRAM, memory bandwidth, GPU utilization, and CPU/data loader wait time.

## 7. Preparing a Fair Benchmark Environment

Results are comparable only when conditions are controlled and documented. A benchmark configuration should include:

- Instance type, vCPU count, RAM, GPU, VRAM capacity, and device topology.
- Region/zone, network interface type, bandwidth, and load generator placement.
- Volume type, provisioned IOPS/throughput, filesystem, and mount options.
- Operating system, kernel, drivers, runtime, libraries, and container image digest.
- Application version, thread/worker settings, resource requests/limits, and autoscaling policy.
- Cache state, dataset version, seed, and data loading method.
- Benchmark tool version, scripts, arrival rate settings, and run duration.

### Avoiding Making the Load Generator the Bottleneck

The load generator must have enough CPU, RAM, network, and sockets to generate the target traffic. If the generator reaches 100% CPU, measured throughput will reflect the generator's limit rather than the system under test.

Monitor separately:

- Generator CPU and memory.
- Network bandwidth and packet drops.
- Connection count and file descriptor limits.
- Event loop lag or request generation time.
- Percentage of requests sent on schedule compared to expected arrival rate.

At high load, multiple generators may be needed. In that case, partition the workload with distinct seeds and aggregate results across all generators. Avoid placing all generators on the same host or same network bottleneck as the system under test unless that reflects the real architecture.

### Pinning Versions and Configurations

Do not change instance type, kernel, application, and dataset simultaneously and attribute the outcome to a single variable. When comparing two configurations, change only the factor under evaluation and keep everything else equivalent. If exact parity is impossible, explicitly document differences and comparison limitations.

## 8. Benchmark Execution Workflow

A benchmark run can be divided into phases:

1. **Preflight:** verify environment, data, access permissions, capacity, and dependencies.
2. **Warm-up:** prime application, JIT compilation, model weights, connection pools, and caches according to test goals.
3. **Ramp-up:** gradually increase load to target level, avoiding an unrepresentative startup burst.
4. **Measurement:** hold load according to scenario and collect metrics, logs, and traces.
5. **Ramp-down:** reduce load in a controlled manner and wait for queues to drain.
6. **Cooldown:** verify resources and data have returned to expected state.
7. **Repeat:** run enough iterations to evaluate variance.

Warm-up and measurement durations depend on the workload. Short latency benchmarks may need many iterations; soak benchmarks may run for hours. Record the exact measurement window so results are comparable.

### Do Not Mix Warm-up with Measurement Time

The initial run may include image pulls, model loading, cache population, opening connections, or JIT compilation. If the goal is steady-state throughput, exclude this period from the measurement window. If the goal is cold start or scale-out time, measure it separately and do not discard it from results.

### Repetition and Test Ordering

Run multiple iterations under identical conditions. If possible, alternate the order of configurations A/B to reduce the impact of infrastructure drift over time. Record errors and anomalous runs; do not silently discard a result merely because it disagrees with expectations. If excluding a run, state an objective reason such as a generator crash or unplanned infrastructure change.

## 9. Collecting and Interpreting Metrics

### Latency and Percentiles

Latency is the time from a defined start point to a defined end point. Standardize whether measurement is client-side or server-side and whether it includes queues, network, serialization, authentication, or retries.

- **p50:** median experience.
- **p90/p95:** represents the tail experienced by many users.
- **p99/p99.9:** surfaces rare slow requests that can still have severe impact.

Do not average p95 values across multiple machines to obtain a cluster-wide p95. Aggregate histograms or raw samples using statistically valid methods. Mean latency can hide tail latency.

### Throughput and Error Rate

Throughput must be counted on successfully completed tasks, not merely requests sent. Record request timeouts, retries, HTTP 4xx/5xx responses, failed jobs, incorrect outputs, and dropped tasks.

If the system fails fast, total throughput may rise while successful throughput falls. Always report successful throughput alongside error rate.

### Saturation and Resources

Collect CPU utilization, CPU throttling, memory RSS, page faults, swap, GC pauses, disk IOPS/throughput/latency, network bandwidth/retransmissions, GPU utilization, and VRAM. Also monitor internal queues and pending connection counts.

A service may be below 100% CPU yet still saturated on a connection pool, disk queue, or thread limit. Metrics must be sufficient to explain why latency increased.

### Cost per Unit of Work

For cloud compute, convert cost to per-unit-of-work terms:

**Cost per 1,000 tasks = Resource cost during measurement window / Successful tasks × 1,000**

For inference models, use cost per million tokens; for image processing, cost per thousand images; for batch, cost per job or per million records. Include supporting resources, idle time, and startup time in the calculation if they occur in production.

## 10. Tool Example: k6 Simulating an API with Staged Load

k6 can generate HTTP load and record latency, throughput, and error rates. The example below uses a hypothetical endpoint and gradually ramps virtual users. It illustrates script structure; for a representative benchmark, replace the fixed payload with a dataset generated from real distributions and choose the appropriate load model.

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 20 },
    { duration: '5m', target: 80 },
    { duration: '2m', target: 120 },
    { duration: '3m', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.001'],
    http_req_duration: ['p(95)<250', 'p(99)<500'],
  },
};

export default function () {
  const payload = JSON.stringify({
    customerId: 'test-customer-0042',
    operation: 'estimate',
    items: [
      { sku: 'SKU-1001', quantity: 2 },
      { sku: 'SKU-2033', quantity: 1 },
    ],
  });

  const response = http.post(
    __ENV.BASE_URL + '/api/estimate',
    payload,
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { scenario: 'estimate' },
    }
  );

  check(response, {
    'status is 200': function (r) { return r.status === 200; },
  });

  sleep(1);
}
~~~

This script uses a VU/closed workload model: each virtual user waits for a response before sending the next request and sleeps for one second. It is useful for illustrating concurrent sessions, but does not guarantee a fixed arrival rate when the system slows down. If an open model is needed, use k6's arrival-rate executors such as constant-arrival-rate or ramping-arrival-rate, and check dropped iterations to verify whether the generator is sustaining the target load.

Do not run tests directly against production without approval, load caps, and a stop plan. An endpoint might create records, send emails, trigger billing, or initiate unintended tasks. Use a test environment, test accounts, and data that has no customer impact.

## 11. Benchmark Design Example for an Image Processing Service

Suppose a service receives images, generates thumbnails, and writes outputs to object storage. The team needs to choose between two compute configurations:

- Configuration A: 4 vCPU, 16 GB RAM.
- Configuration B: 8 vCPU, 32 GB RAM.

A benchmark using only 256 KB images and a single worker will not reflect the real workload. The team needs to simulate:

1. Small/medium/large image size distribution based on real statistics.
2. Image formats and aspect ratios with varying metadata or resolutions.
3. Ratio of requests generating one thumbnail versus multiple sizes.
4. Number of tenants, object keys, and repeat access levels.
5. Background, peak, burst loads, and concurrent uploads.
6. Time to read objects, decode, resize, encode, and write new objects.

The team runs warm-up to prime the runtime and connection pools, then measures 10 minutes at typical load, 10 minutes at peak, and a short burst scenario. Run multiple iterations on each configuration, with the same dataset version and object storage location.

Metrics to compare:

| Metric | Configuration A | Configuration B |
|---|---|---|
| Successfully processed images/second | Measured | Measured |
| p95/p99 processing time | Measured | Measured |
| Decode/upload error rate | Measured | Measured |
| Peak CPU and memory | Measured | Measured |
| I/O and network throughput | Measured | Measured |
| Cost per 1,000 successful images | Calculated from price and throughput | Calculated from price and throughput |

If B achieves higher throughput but peak memory nears its limit, test very large images and high concurrency. If A meets SLOs at lower cost, A may be the better choice for baseline load; B can be used for batch or peak hours if scaling mechanisms fit.

## 12. Benchmark Design Example for AI Model Inference

Suppose an API uses GPUs for language model inference. Measuring only tokens/second on a single short prompt ignores differences between prefill and decode, context lengths, concurrent sessions, and KV cache.

A workload suite should include:

- Prompt and output length distributions, including long-tail cases.
- Mix of short, medium, and long requests.
- Concurrent session count and arrival rate.
- Batch size or dynamic batching policy.
- Precision and quantization configuration.
- Cache hit ratio if prompt caching is enabled.
- Cold-start and warm steady-state loads.
- Output quality requirements and error limits.

Measure time-to-first-token (TTFT), inter-token latency, total latency, input/output tokens per second, request throughput, GPU utilization, and VRAM. If using multiple GPUs, monitor communication overhead and network fabric utilization.

For interactive workloads, p95 TTFT and inter-token latency may matter more than average throughput. For offline batch workloads, total tokens completed per hour and cost per million tokens may matter more than single-request latency.

## 13. Analyzing Results and Identifying Bottlenecks

Benchmark results should answer three questions:

1. Does the system meet SLOs at target load?
2. As load increases, which component saturates first?
3. Which configuration meets targets with acceptable cost and stability?

Some diagnostic signals:

| Observation | Possible Cause | Investigation Direction |
|---|---|---|
| High CPU, flat throughput | CPU saturation, lock contention, or excessive context switching | Profile CPU, thread count, parallelism |
| Low CPU, high latency | I/O wait, network, queues, or slow dependencies | Trace requests, disk/network metrics, queue depth |
| RAM grows over time | Memory leak, unbounded cache, or queue buildup | Heap/RSS profile, GC, object lifetimes |
| Low GPU utilization | Data loader, CPU preprocessing, or batch too small | Measure input pipeline, batching, and host-to-device transfer |
| High GPU utilization but low tokens/s | Memory bandwidth, kernel launch, sequence length, or communication | Profile kernels, VRAM, precision, and topology |
| High disk throughput but poor latency | Queue depth or random I/O exceeding capability | Check IOPS, block size, and queues |
| Error rate rises during bursts | Capacity, connection pool, or rate limit | Observe queues, autoscaling, and dependency limits |
| Generator hits max CPU/network | Load generator is the bottleneck | Scale up generator or distribute load |

Do not optimize a single metric in isolation. For instance, increasing batch size can raise throughput while also increasing latency and memory. Reducing authentication frequency can cut CPU usage while altering security requirements. Every optimization must be re-measured on the same workload and checked for output quality.

## 14. Repeatability and Statistical Reliability

A single result can be skewed by noisy neighbors, network changes, caching, autoscaling, or background tasks. For reliable conclusions:

- Run enough repetitions; short measurements require more samples than long ones.
- Report medians and percentiles rather than averages alone.
- Record min/max, variance, or confidence intervals when appropriate.
- Use the same measurement window and warm-up conditions.
- Document runs affected by unexpected events.
- Compare improvements against the natural variance of the measurement.

If configuration B is 2% faster than A while run-to-run variance is 5%, there is insufficient evidence to conclude B is better. Increase repetition count or reduce sources of noise.

### Benchmark Manifest

Each run should have a manifest so others can reproduce it:

~~~yaml
benchmark:
  name: image-resize-api
  dataset_version: images-v3
  dataset_checksum: sha256:replace-with-real-checksum
  seed: 20261122
  scenario: peak-load
  arrival_rate_rps: 120
  duration: 10m
  warmup: 3m
target:
  instance_type: replace-with-instance-type
  region: replace-with-region
  os_image: replace-with-image-id
  application_version: replace-with-version
  container_digest: sha256:replace-with-real-digest
measurement:
  latency_percentiles: [50, 95, 99]
  collect_cpu_memory_io_network: true
  record_errors_and_retries: true
~~~

The placeholder `replace-*` values must be filled with actual details. Never use placeholder strings as reported results. Store the manifest alongside results, scripts, logs, metrics, and test dataset versions.

## 15. Common Mistakes

1. **Using a single payload:** misses tail distributions and large-data processing costs.
2. **Using uniformly random data:** fails to reproduce hot keys, large tenants, or cache locality.
3. **Testing isolated requests only:** skips action sequences, think time, and dependencies.
4. **Using closed models for everything:** load drops as latency rises and can mask overload.
5. **Not monitoring the generator:** results become bounded by the load generator.
6. **Mixing warm-up with steady-state:** leads to wrong conclusions about steady throughput or cold starts.
7. **Reporting only averages:** hides tail latency and rare errors.
8. **Comparing configurations with multiple differing factors:** impossible to tell which change caused the difference.
9. **Using unsanitized production data:** risks exposing personal information or secrets.
10. **Not saving seeds and manifests:** impossible to reproduce or verify results.
11. **Counting only requests sent:** ignores failed, timed-out, or generator-dropped requests.
12. **Optimizing for overly simple synthetic benchmarks:** improves benchmark scores while degrading real-workload experience.

## 16. Pre-Publication Benchmark Checklist

- [ ] Benchmark question, hypothesis, and pass criteria clearly defined.
- [ ] Workload describes data, size distributions, skew, and action sequences.
- [ ] Data is approved, anonymized, or safely synthesized.
- [ ] Dataset, seed, and generator version recorded.
- [ ] Open/closed load model matches real request arrival behavior.
- [ ] Includes baseline, typical, peak, and other needed scenarios.
- [ ] Environment, instance, image, driver, runtime, and network documented.
- [ ] Generator has sufficient capacity and is not a bottleneck.
- [ ] Warm-up, ramp-up, measurement, ramp-down, and cooldown clearly separated.
- [ ] Percentile latency, successful throughput, errors, and saturation measured.
- [ ] Multiple runs performed with variance analysis.
- [ ] Cost converted per successful unit of work.
- [ ] Results include manifest, logs, metrics, and interpretation limits.

## 17. Practice Exercise

A document-processing service receives an average of 50 requests/second. 80% of requests process files under 200 KB, 15% process files from 200 KB to 3 MB, and 5% process files larger than 3 MB. Traffic rises to 160 requests/second during peak hours. A team wants to compare two compute configurations using a 5-minute benchmark repeatedly sending a single 100 KB file.

1. Why is the current benchmark not representative of the workload?
2. Propose a test data distribution and access behaviors to simulate.
3. Should an open or closed workload model be used to test sustaining 160 requests/second? Why?
4. What metrics should be measured besides throughput?
5. Propose the phases of a benchmark run and the information to record for reproducibility.

Hint: keep the three size buckets at the given ratios and add variations in content, page/field counts, and operation types if they affect processing. Use an open arrival-rate model to test a fixed arrival rate of 160 requests/second; monitor dropped iterations to verify whether the generator sustains full load. Measure p50/p95/p99, error rate, CPU, memory, I/O, network, queue depth, and cost per successful document. Run warm-up, ramp-up, peak window, ramp-down, and repeat with the same dataset version, seed, and configuration.

## Conclusion

Reliable benchmarks begin with understanding real-world data and load-generation behavior. Describe distributions, skew, locality, action sequences, and request cadence; choose safe test data that preserves performance-impacting characteristics. Combine micro, component, and end-to-end benchmarks, select the right load model, control the environment, and measure percentile latency, successful throughput, errors, saturation, and cost. With saved manifests and controlled repetitions, results provide a solid foundation for choosing compute configurations and optimizing systems.
