# Setting Thresholds for Low-Traffic and High-Traffic Flows

Circuit Breaker thresholds determine when the application stops sending calls to a dependency showing signs of ill health. If thresholds are too sensitive, a few transient errors can open the circuit even though the service still serves most requests. If thresholds are too loose, the application keeps sending many calls into a degrading dependency, increasing latency and consuming caller resources.

An appropriate threshold set depends on traffic volume, normal latency, variability, and the consequence of call failures. The same configuration can work well for a dependency receiving thousands of calls per second yet fail for one receiving only a few calls per minute.

This lesson explains how to choose the sliding window type, minimum sample count, failure rate threshold, slow-call threshold, and HALF_OPEN probe count for low-traffic and high-traffic flows. Examples use Resilience4j within Spring Cloud CircuitBreaker; the numbers provided are starting points for measurement, not universal thresholds for every system.

## 1. Why does traffic affect thresholds?

A Circuit Breaker evaluates outcomes of calls passing through it. To compute failure rate or slow-call rate, Resilience4j needs enough samples. How quickly samples arrive depends directly on the dependency's traffic volume.

Suppose two dependencies both experience a 50% call failure rate:

- Dependency A receives 1,000 calls per second. Within a single second there are roughly 1,000 samples to evaluate.
- Dependency B receives 1 call per minute. It takes many minutes to accumulate an equivalent sample count.

If both use minimumNumberOfCalls set to 100, A's Circuit Breaker can start evaluating almost immediately, whereas B may never reach 100 samples within the chosen time window.

Conversely, setting minimumNumberOfCalls to 1 for every dependency means a single error on a low-traffic dependency can open the circuit. That can disrupt functionality even when the error was only a transient glitch.

Therefore, three factors must be balanced:

1. **Sample reliability:** how many outcomes are needed before concluding the dependency is failing?
2. **Detection speed:** how long can the system wait before tripping calls?
3. **Blast radius:** if calls continue going to the failing dependency, how many resources will the caller consume and how many requests will be impacted?

## 2. Sliding window and minimumNumberOfCalls

Resilience4j supports two primary sliding window types:

| Window type | How it counts | Best suited when |
| --- | --- | --- |
| COUNT_BASED | Keeps outcomes of a fixed number of most recent calls | You want sample-count evaluation and traffic is relatively steady |
| TIME_BASED | Aggregates outcomes over a recent time interval | You want real-time window evaluation, especially with fluctuating traffic |

With COUNT_BASED, slidingWindowSize is the number of most recent calls retained in the window. For example, a size of 100 means rates are computed over up to the last 100 calls once minimum samples are reached.

With TIME_BASED, slidingWindowSize is the window length in seconds. For example, a size of 60 means outcomes from the last 60 seconds are evaluated.

minimumNumberOfCalls is the minimum number of calls required before the Circuit Breaker calculates failure rate and slow-call rate. Until the sample count in the window reaches this number, the Circuit Breaker cannot conclude that rates have exceeded thresholds.

Key point: TIME_BASED does not automatically solve low-sample issues. If the window spans 5 minutes but only one request arrives in that period, minimumNumberOfCalls of 10 is still not met. Window type determines the span of time or calls retained; minimumNumberOfCalls determines how many samples are needed to begin evaluation.

## 3. Estimating sample counts from traffic

Expected calls in a window can be estimated with a simple formula:

\[
N \approx \lambda \times W
\]

Where:

- N is the expected number of calls in the window.
- λ is the average call rate in calls per second.
- W is the window duration in seconds.

For example, a dependency receiving an average of 2 calls per minute using a 5-minute window:

\[
N \approx \frac{2}{60} \times 300 = 10
\]

At this traffic level, a 5-minute window expects about 10 samples. If minimumNumberOfCalls is set to 20, the Circuit Breaker will normally lack enough samples to evaluate within such a window.

This is only an average estimate. Real traffic can arrive in bursts, with peak hours and idle periods without requests. Measure traffic distribution over time rather than relying solely on a daily average.

During design, answer:

- Under normal conditions, how many samples are in a window?
- When traffic drops, does the Circuit Breaker still get enough samples?
- When the dependency starts failing, how long does it take to reach minimumNumberOfCalls?
- How long can the system wait to react before users suffer excessive latency?

## 4. Designing for low-traffic dependencies

Low-traffic dependencies are common in infrequently called features, such as periodic report generation services, rare quota checks, or integrations with low-volume partner systems.

For this class of dependencies, a large COUNT_BASED window could take hours or days to accumulate enough samples. TIME_BASED is usually easier to reason about because it states that the system evaluates outcomes within a specific time span.

However, a long time window does not mean fast failure detection. If traffic is very low, choose minimumNumberOfCalls small enough to be reachable, yet not so small that a single error opens the circuit unintentionally.

### 4.1. Low-traffic configuration example

Suppose a dependency receives an average of 1 to 2 calls per minute. You can start testing with a 5-minute window and a minimum of 3 samples:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      partner-report:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 300
        minimumNumberOfCalls: 3
        failureRateThreshold: 50
        slowCallDurationThreshold: 3s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 1
~~~

In this example:

- TIME_BASED and slidingWindowSize of 300 evaluate outcomes over the last 5 minutes.
- minimumNumberOfCalls of 3 allows evaluation to begin once at least 3 samples exist.
- failureRateThreshold of 50 means a failure rate at or above 50% can open the circuit.
- slowCallDurationThreshold of 3 seconds marks calls lasting that long or longer as slow.
- waitDurationInOpenState of 30 seconds is the wait duration before probing.
- permittedNumberOfCallsInHalfOpenState of 1 permits only one probe call at a time under this configuration.

The values above are illustrative only. If the dependency only receives one request every 10 minutes, a 5-minute window may still lack enough samples. A longer window may be needed, while accepting that the Circuit Breaker will react more slowly. If enough samples cannot be reached reliably, add health checks, synthetic probes, or independent monitoring instead of forcing the Circuit Breaker to conclude from too little data.

### 4.2. Avoiding overly sensitive thresholds

With 3 samples and a 50% failure threshold, two failures produce a failure rate of roughly 66.7%, enough to open the circuit. This can be reasonable if every failure has major impact, but may be too sensitive if the dependency occasionally returns transient errors.

If minimumNumberOfCalls is 1 and the failure threshold is 50%, just a single failed call produces a 100% rate. The circuit can open immediately after the very first failure. Such a configuration should only be used when there is a clear operational reason and its impact has been tested.

Another option is using a higher minimum sample count, accepting slower detection, and relying on timeouts to cap per-request wait times. No threshold setting can both react instantaneously and completely eliminate false positives when samples are too scarce.

## 5. Designing for high-traffic dependencies

High-traffic dependencies can generate hundreds or thousands of samples in seconds. With a COUNT_BASED window that is too small, the window turns over very rapidly. A brief error spike or traffic burst can make the failure rate swing wildly and cause the Circuit Breaker to flap open and closed if parameters are poorly tuned.

With high traffic, TIME_BASED evaluates over a fixed time interval that maps easily to operational trends. You can also use COUNT_BASED with a sufficiently large window if you want to bound sample counts rather than time.

### 5.1. High-traffic configuration example

Suppose a dependency receives roughly 500 calls per second. You can start with a 30-second window and minimumNumberOfCalls of 200:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 200
        failureRateThreshold: 40
        slowCallDurationThreshold: 500ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 10
~~~

Under steady traffic, 500 calls per second can generate roughly 15,000 samples in 30 seconds. minimumNumberOfCalls of 200 is reached very quickly, while the 30-second window ensures rates reflect recent trends rather than just a tiny cluster of requests.

The values 40%, 500 ms, 50%, and 15 seconds are not universal standards. They must be compared against Inventory's baseline, SLO, and business error tolerance. If normal p99 response time is already 700 ms, a slowCallDurationThreshold of 500 ms will flag most requests as slow; thresholds must be grounded in actual data.

### 5.2. COUNT_BASED with high traffic

If using COUNT_BASED, understand how much wall-clock time the window covers at current traffic rates.

For example, a 1,000-call window at 500 calls per second covers only about 2 seconds. A 2-second error burst can fill most of the window and trip the circuit quickly. If the goal is smoothing fluctuations over 30 seconds, you need a window of around 15,000 calls or switch to a 30-second TIME_BASED window.

Traffic can vary sharply between off-peak and peak hours. COUNT_BASED keeps sample count fixed while covered time varies with request rate. TIME_BASED keeps time fixed while sample count varies. Choose based on what the operations team wants to compare.

## 6. Choosing failureRateThreshold based on error tolerance

failureRateThreshold is the error percentage that triggers the Circuit Breaker to transition to OPEN once minimumNumberOfCalls has been met.

Example with failureRateThreshold set to 50%:

| Samples | Failures | Failure rate | Result once minimumNumberOfCalls is met |
| ---: | ---: | ---: | --- |
| 10 | 1 | 10% | Below threshold |
| 10 | 4 | 40% | Below threshold |
| 10 | 5 | 50% | Threshold reached, can open circuit |
| 10 | 8 | 80% | Above threshold |
| 20 | 10 | 50% | Threshold reached |

Resilience4j opens the circuit when the rate meets or exceeds the threshold, after minimum samples are reached. Do not pick a threshold just because a number like 50% looks clean. Examine the error rate the business can tolerate before calls must stop.

A cache-reading API may tolerate a higher failure rate if its fallback works well. A payment-confirmation or inventory-reservation API may need to react sooner because errors or timeouts directly impact transactions.

Distinguish the Circuit Breaker's failure rate from the user-visible error rate. If Retry sits inside the Circuit Breaker, one request may make multiple attempts yet produce only one final outcome. If the Circuit Breaker sits inside Retry, each attempt can contribute a sample. Thresholds only make sense when you know the exact call boundary being measured.

## 7. Choosing minimumNumberOfCalls intentionally

minimumNumberOfCalls prevents drawing conclusions from too few samples. Yet setting it too high can prevent the Circuit Breaker from ever evaluating within the chosen window.

You can follow this process:

1. Measure request rates during off-peak and peak hours.
2. Choose the window type and expected length.
3. Estimate sample counts under typical low-traffic conditions.
4. Pick minimumNumberOfCalls not exceeding the samples that can accumulate in a normal window.
5. Check the time from when the dependency starts failing until the Circuit Breaker opens.
6. Adjust if detection is too slow or if circuits open from too few samples.

For example, a dependency receives 3 requests per minute and uses a 5-minute window. Expected samples are about 15. Setting minimumNumberOfCalls to 50 prevents the Circuit Breaker from evaluating under normal traffic. Setting it to 3 allows early evaluation, though rates become more sensitive to individual errors.

Do not lower minimumNumberOfCalls merely to make dashboards display failure rates sooner. When samples are low, display the sample count clearly and avoid alerting on statistically unreliable rates.

## 8. Choosing slowCallDurationThreshold and slowCallRateThreshold

Failure rate detects failed calls. However, a dependency may keep returning HTTP 200 while taking many seconds to respond. Slow calls tie up threads and connections and increase caller latency.

slowCallDurationThreshold defines the duration above which a call is counted as slow. slowCallRateThreshold defines the percentage of slow calls that causes the Circuit Breaker to open once enough samples exist.

How to select thresholds:

- Measure normal latency by percentiles such as p50, p95, and p99.
- Base slowCallDurationThreshold on latency budgets and SLOs, not just averages.
- Choose slowCallRateThreshold according to acceptable slowness within a window.
- Check HTTP client and TimeLimiter timeouts; slow-call thresholds do not cancel calls by themselves.
- Account for differences between off-peak and peak hours.

For example, if the SLO requires 99% of Inventory calls to finish within 700 ms, you might test slowCallDurationThreshold around 700 ms and track the slow-call rate. However, if the HTTP client timeout is 500 ms, calls can fail before reaching 700 ms; in that case, the slow-call threshold provides little signal for timed-out requests.

Do not set slowCallDurationThreshold lower than the dependency's normal latency. If set below p50, most valid calls will be flagged as slow and the Circuit Breaker can open constantly.

## 9. Configuring OPEN duration and HALF_OPEN probe counts

waitDurationInOpenState specifies how long the Circuit Breaker stays OPEN before allowing recovery probes. Too short a duration can send the application back to calling an unstable dependency. Too long a duration keeps functionality disrupted even after the dependency has recovered.

permittedNumberOfCallsInHalfOpenState limits probe calls in HALF_OPEN. This is the trial traffic sent to the dependency before the Circuit Breaker decides whether to close again or reopen.

| Condition | Configuration consideration |
| --- | --- |
| Low-traffic dependency | Small probe count to avoid sudden bursts; may need to wait longer to observe enough outcomes |
| High-traffic dependency | Can permit more probes, but must stay within the dependency's recovery capacity |
| Slow-recovering dependency | Increase waitDurationInOpenState to avoid retrying too early |
| Dependency with strict concurrency limits | Keep probe count low and coordinate with a Bulkhead |
| Multiple replicas opening together | Consider synchronized HALF_OPEN transitions creating a burst |

If multiple replicas use the same wait duration, they can transition to HALF_OPEN nearly simultaneously. Multiple caller instances then send probes to the dependency at the same time. You can use per-instance wait variation or an appropriate coordination mechanism if the system is sensitive to recovery bursts.

Under low traffic, a single probe may suffice to confirm an initial outcome, but one successful probe does not guarantee stable recovery. Consider the probe count, real requests arriving in HALF_OPEN, and how the system handles a failed probe.

## 10. Per-dependency configuration

Do not apply one shared configuration to every dependency just because they live in the same application. Each dependency has different traffic, SLOs, load tolerance, and criticality.

You can use configs as a base profile and override per instance:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 100
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 5

    instances:
      inventory:
        baseConfig: default
        minimumNumberOfCalls: 200
        slowCallDurationThreshold: 500ms
        failureRateThreshold: 40

      partner-report:
        baseConfig: default
        slidingWindowSize: 300
        minimumNumberOfCalls: 3
        slowCallDurationThreshold: 3s
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 1
~~~

inventory uses a high-traffic-oriented configuration with its own minimum sample count and latency threshold. partner-report uses a 5-minute window, fewer minimum samples, and only one probe in HALF_OPEN.

This configuration illustrates policy separation. Before using it, verify the request rate and latency baseline of each dependency. If partner-report actually receives only one request every 15 minutes, a 5-minute window still cannot produce three samples; adjust the window or use another health monitoring mechanism.

## 11. When traffic is too low for the Circuit Breaker to gather enough samples

A Circuit Breaker relies on actual calls passing through it. It does not proactively send periodic health probes while CLOSED to test a dependency when there is no traffic.

If a dependency is only called once per hour, the sliding window may not accumulate enough samples within a useful timeframe. Lowering minimumNumberOfCalls to 1 makes the circuit react to one failure, but also increases the risk of opening from an isolated glitch.

In such cases, consider:

- Using a health endpoint or independent synthetic probe to test the dependency on a schedule.
- Using timeouts to bound wait duration for real requests.
- Using fallbacks or caches if business rules permit.
- Tracking errors at the HTTP client and service-monitor layers.
- Keeping the Circuit Breaker as an additional safeguard when enough requests arrive, rather than relying on it as the sole health-check tool.

Health checks and Circuit Breakers serve different purposes. A health check asks whether the dependency is ready at the moment of the probe. A Circuit Breaker evaluates real calls made by the caller within the window. Combining both handles very sparse traffic dependencies more effectively.

## 12. Avoiding continuous opening and closing (flapping)

A Circuit Breaker can oscillate continuously between states if thresholds are too sensitive or the dependency hovers near the error threshold. This phenomenon is sometimes called flapping.

Common causes:

- Window is too small.
- minimumNumberOfCalls is too low.
- failureRateThreshold is too close to the normal baseline error rate.
- waitDurationInOpenState is too short.
- HALF_OPEN permits too many probes at once.
- Multiple replicas probe simultaneously.
- Retries inflate failure sample counts in the window.

Flapping can be reduced by:

1. Increasing window size or switching to an appropriate TIME_BASED window.
2. Increasing minimumNumberOfCalls to avoid deciding from too few samples.
3. Choosing waitDurationInOpenState long enough to give the dependency time to recover.
4. Limiting HALF_OPEN probe counts.
5. Considering jitter or staggered probe timing across replicas at an appropriate orchestration layer.
6. Monitoring state transition counts and time spent in each state.

Do not simply raise the wait duration to mask a bad configuration. Inspect failure rate, slow-call rate, sample count, retry attempts, and latency together to locate the root cause.

## 13. Retries change how thresholds should be chosen

When Retry is combined with a Circuit Breaker, nesting order determines how many samples one logical request contributes:

- Retry outside, Circuit Breaker inside: each attempt can become a sample.
- Circuit Breaker outside, Retry inside: the Circuit Breaker typically records the final outcome of the entire retry chain.

For example, one request with three attempts that all fail:

| Nesting order | Failure samples received by Circuit Breaker |
| --- | ---: |
| Retry outside, Circuit Breaker inside | Potentially 3 |
| Circuit Breaker outside, Retry inside | 1 |

Therefore, you cannot pick minimumNumberOfCalls solely from incoming HTTP request volume while ignoring retries. Clarify whether Circuit Breaker samples represent attempts or logical requests, then tune windows and thresholds in that unit.

If Retry sits outside the Circuit Breaker, ignore CallNotPermittedException so you do not retry a call already rejected by the Circuit Breaker. Retries also need bounded attempt counts, backoff, and an overall timeout so they do not amplify load.

## 14. Data-driven tuning process

Do not ship thresholds to production based solely on a sample YAML snippet. Tune iteratively:

1. **Measure baseline:** collect request rate, failure rate, p50/p95/p99 latency, and timeout rate under normal conditions.
2. **Classify traffic:** separate off-peak hours, peak hours, and bursts.
3. **Choose window:** COUNT_BASED for fixed sample count; TIME_BASED for fixed evaluation time.
4. **Choose minimumNumberOfCalls:** ensure it is reachable under normal traffic and yields appropriate detection time.
5. **Choose failure threshold:** base it on the error rate acceptable to the business.
6. **Choose slow-call threshold:** base it on latency budgets and SLOs.
7. **Choose OPEN duration and HALF_OPEN probes:** balance recovery time against probe load.
8. **Simulate failures:** inject connection errors, HTTP 5xx, timeouts, and slow responses.
9. **Measure reaction time:** from when errors begin until the circuit opens.
10. **Measure impact:** rejected requests, fallbacks, latency, and caller resources.
11. **Adjust one parameter at a time:** change one factor per iteration to understand its effect.
12. **Roll out in stages:** monitor metrics after applying changes and prepare rollback capability.

If possible, test on staging with production-like traffic. When deploying multiple replicas, monitor each Circuit Breaker instance because each instance normally keeps its own state and sliding window. Do not sum sample counts across replicas and assume every Circuit Breaker shares one global window.

## 15. Reading metrics to verify whether thresholds fit

Metrics to monitor include:

| Metric | Used to evaluate |
| --- | --- |
| Calls by kind | Successful, failed, and ignored call counts |
| Failure rate | Error percentage in the sliding window |
| Slow-call rate | Percentage of calls exceeding slowCallDurationThreshold |
| Buffered calls | Current sample count in the window |
| Not permitted calls | Calls rejected by the Circuit Breaker |
| State transitions | Frequency of CLOSED, OPEN, HALF_OPEN transitions |
| Retry attempts | Retry count and retry success rate |
| HTTP client latency | Actual latency per attempt |
| Fallback count | How often the application used fallback results |

Signs the configuration may be too sensitive:

- Circuit Breaker opens after one or two isolated errors.
- State transitions continuously between OPEN and CLOSED.
- Low error rate yet rejection counts rise sharply.
- HALF_OPEN fails because too many probes are sent at once.

Signs the configuration may be too loose:

- Dependency fails persistently while the Circuit Breaker stays CLOSED.
- Too much time passes from when errors start until the circuit opens.
- Caller continues holding many pending requests.
- Timeouts and thread/connection usage climb before the Circuit Breaker reacts.

Read metrics together with sample count. A high failure rate with only a few samples has a very different meaning from a high failure rate across thousands of samples. If the dashboard does not display sample counts, add a buffered calls metric or equivalent panel.

## 16. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Circuit Breaker does not open under low traffic | minimumNumberOfCalls not reached in window | Measure request rate, adjust window/minimum, or add health probes |
| A single error opens the circuit | minimumNumberOfCalls is too low | Raise minimum samples if business permits |
| Circuit opens too fast during peak hours | COUNT_BASED window is too short in wall-clock time | Increase sample count or switch to TIME_BASED |
| Circuit reacts too slowly | Window is too long or minimumNumberOfCalls is too high | Measure sample accumulation time and adjust |
| Failure rate swings wildly | Too few samples, bursts, or threshold too close to baseline | Increase window, sample minimum, and inspect trends |
| Circuit flaps OPEN/CLOSED repeatedly | Short wait duration or too many HALF_OPEN probes | Increase wait duration and limit probes |
| Slow-call rate is always high | Threshold is below normal latency | Base thresholds on percentiles and SLOs |
| Dashboard reports high failure rate with few requests | Sample count not considered | Display buffered calls and add alert conditions |
| Configuration not applied | Wrong instance name or overridden configuration | Check instance name, baseConfig, and effective runtime config |
| Retries open circuit unexpectedly fast | Circuit Breaker is counting individual attempts | Verify wrapping order and calibrate by attempt count |

## 17. Design principles

- Measure request rates per dependency before selecting a window.
- Use COUNT_BASED when you want fixed sample counts; use TIME_BASED when you want fixed evaluation duration.
- Choose minimumNumberOfCalls to avoid deciding from too few samples while remaining reachable under normal traffic.
- Never lower minimumNumberOfCalls solely to make the Circuit Breaker react fast without evaluating false positives.
- Set failureRateThreshold based on acceptable business error tolerance.
- Set slowCallDurationThreshold based on latency percentiles and SLOs.
- Choose waitDurationInOpenState and HALF_OPEN probe counts according to the dependency's recovery capacity.
- Separate configurations for low-traffic and high-traffic dependencies.
- Account for retry ordering because it changes how many samples the Circuit Breaker receives.
- Monitor sample count, state transitions, rejections, fallbacks, and latency.
- Add health checks or synthetic probes when a dependency has very sparse traffic.
- Test burst, sustained failure, timeout, and recovery scenarios before release.

No single Circuit Breaker threshold set fits all traffic levels. For low-traffic dependencies, avoid deciding from too few samples and consider longer time windows or independent health probes. For high-traffic dependencies, gather enough samples to smooth out noise while still detecting incidents within an acceptable timeframe. When windows, minimumNumberOfCalls, failure thresholds, slow-call thresholds, and HALF_OPEN probes are chosen from real data, Circuit Breakers in Spring Cloud and Resilience4j protect dependencies effectively without causing unnecessary disruptions.

## References

- [Resilience4j CircuitBreaker — Sliding window and configuration](https://resilience4j.readme.io/docs/circuitbreaker)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Resilience4j Micrometer metrics](https://resilience4j.readme.io/docs/micrometer)
