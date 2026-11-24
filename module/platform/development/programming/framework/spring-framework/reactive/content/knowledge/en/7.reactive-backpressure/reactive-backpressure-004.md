# `limitRate` and How It Differs from Time-Based Rate Limiting

## 1. One Name, Two Different Concepts

In Project Reactor, **Flux.limitRate** is an operator that adjusts **backpressure** signals: it splits element demand from downstream into **smaller request batches** when propagating upstream. This is an element-count coordination mechanism between Publisher and Subscriber.

In HTTP systems, **time-based rate limiting** means something else: for example, at most **10 HTTP requests/second** or **600 requests/minute** per API key. That mechanism must track time, identify the user/group consuming the quota, and decide whether to allow, wait, or reject each operation.

**Key point: Flux.limitRate(10) does not mean 10 elements/second, does not mean 10 HTTP requests/second, and does not mean taking only 10 elements in total.**

Three easily confused types of limits:

| Limit Category | Unit | Question Solved | Example |
| --- | --- | --- | --- |
| **Backpressure / demand** | Elements per request | How many more elements is upstream allowed to emit? | Flux.limitRate(10, 0) |
| **Concurrency** | Simultaneously active work | How many HTTP calls or inner Publishers execute at the same time? | flatMap(mapper, 4) |
| **Time-based rate limit** | Operations / second, minute, or window | How many requests may an API key start within a time period? | Token bucket 20 calls/s |

All three categories may be needed in the same application. They have different purposes and operating boundaries.

## 2. Recap of the Reactive Streams Contract

Reactive Streams defines the **Publisher**, **Subscriber**, **Subscription**, and **Processor** interfaces. After receiving a Subscription, a Subscriber can call:

~~~java
subscription.request(5);
~~~

This call grants **demand for up to five more elements**, rather than requesting exactly five elements immediately. The Publisher may emit fewer if data is not yet ready or the stream completes.

~~~text
Subscriber                               Publisher
    |                                        |
    |----------- subscribe() -------------->|
    |<---------- onSubscribe(s) ------------|
    |----------- s.request(5) ------------->|
    |<---------- onNext(item1) -------------|
    |<---------- onNext(item2) -------------|
    |                  ...                   |
    |<---------- onNext(item5) -------------|
    |----------- s.request(5) ------------->|
    |                  ...                   |
~~~

Principles to remember:

- **request(n)** counts **elements**, not bytes, packets, database queries, or HTTP requests.
- Demand accumulates across calls; **Long.MAX_VALUE** represents unbounded demand in element count.
- A spec-compliant source must not send `onNext` exceeding the demand granted to the subscription.
- Intermediate operators have the right to **transform demand**. For example, `buffer(10)` must request more original elements to form one buffer.
- Cancellation, errors, and completion end the subscription lifecycle in accordance with the contract.
- Demand carries no information about **seconds/minutes** and does not create any scheduler or thread on its own.

When downstream wants everything, many consumption styles like plain `subscribe()` or `collectList().block()` send **Long.MAX_VALUE**; therefore, shaping upstream demand can help with sources that should not handle huge single requests.

## 3. Where Does `Flux.limitRate` Operate?

Two commonly used overloads:

~~~java
Flux<T> limitRate(int prefetchRate);
Flux<T> limitRate(int highTide, int lowTide);
~~~

Suppose a source emits 100 integers and downstream wants all of them:

~~~java
Flux<Integer> values = Flux.range(1, 100)
                           .limitRate(10);
~~~

**limitRate(10)** limits the size of request batches forwarded upstream; it **does not stop at the 10th element**. If there are no errors/cancellations and downstream continues having demand, all 100 numbers can be emitted.

Position in the pipeline:

~~~text
[Downstream Subscriber]
    |
    | request(Long.MAX_VALUE)
    v
[limitRate(4, 0)]
    |
    | request(4) -> receive a batch
    | request(4) -> receive the next batch
    | request(4) -> continue if needed
    v
[Upstream Publisher]
~~~

The diagram depicts **demand**, not time intervals. Those request rounds can happen extremely fast if both source and consumer are fast. There is no "wait one second" step.

Common benefits:

- Split an unbounded request into batches that upstream can manage more easily.
- Tune prefetching and demand replenishment within a pipeline.
- Prevent a source from being asked to pull too many elements at once if the source honors backpressure.
- Observe and optimize data requesting from an adapter, data store, or batch-oriented source.

Limitations: **limitRate does not create HTTP quotas**, does not determine latency, does not guarantee total memory stays below `highTide`, and does not make a non-backpressure-compliant Publisher compliant merely by wrapping it with this operator.

## 4. `highTide`, `lowTide`, and Replenishment

### `highTide`: Upstream Request Size per Batch

In **limitRate(highTide, lowTide)**, `highTide` is the upper batch level of demand propagated to the source.

Example:

~~~java
Flux<Integer> source = Flux.range(1, 100)
                           .limitRate(8, 0);
~~~

In this strict mode, each batch can request eight elements. The 100-element source is not capped at eight elements in total; demand is replenished in batches as long as the subscription still needs more data.

### `lowTide`: Replenishment Strategy

Single-argument **limitRate(8)** uses a **prefetch-and-replenish** strategy: once roughly 75% of the initial requested amount has been consumed, the operator proactively requests replenishment upstream. The goal is to avoid waiting until the previous batch is completely empty before asking for more.

**limitRate(highTide, lowTide)** lets you tune the demand replenishment strategy. If **lowTide = 0**, Reactor uses **strict batches** of `highTide`, without the proactive replenishment of the default overload.

~~~java
Flux<Integer> eagerReplenishment = Flux.range(1, 100)
                                      .limitRate(8);

Flux<Integer> strictBatches = Flux.range(1, 100)
                                 .limitRate(8, 0);
~~~

Both streams can emit all 100 elements. The difference is **when and how upstream receives `request(n)` signals**. Call counts and sizes of individual requests when `lowTide` is non-zero also depend on downstream demand, consumed element counts, and other operators.

Do not interpret **limitRate(8, 2)** as "8 elements every 2 seconds". **`lowTide` has no time unit.**

### Why Not Always Pick a Very Small `highTide`?

A batch that is too small can increase request frequency and coordination overhead, hurting throughput. A batch that is too large can cause the source to load or prepare more elements than necessary, increasing buffer/resource pressure. Appropriate values are determined through **profiling**, not a fixed rule.

## 5. Nine-Element Example: Zero Elements Lost

With a synchronous 9-element source and **limitRate(4, 0)**:

~~~text
Source: [1, 2, 3, 4, 5, 6, 7, 8, 9]

Downstream requests everything
          |
          v
request(4): source emits 1, 2, 3, 4
request(4): source emits 5, 6, 7, 8
request(4): source emits 9, completes

Downstream collects: [1, 2, 3, 4, 5, 6, 7, 8, 9]
~~~

The final batch does not necessarily contain four full elements because the source is exhausted. **The total element count is nine, not four.** And because no timing is defined at all, all nine elements can be processed very quickly on the same thread when all components are synchronous.

In complex pipelines, operators such as `flatMap`, `buffer`, or `publishOn` may generate extra requests and alter the trace. This diagram shows a simple **strict batch** case so learners can see the mechanism.

## 6. Runnable Java 17+ Program

The following program records request signals on both sides of `limitRate` to show how they differ. It then compares with `take(4)` and a time-delayed stream.

Requires **JDK 17+** and **Maven 3.9+**.

Structure:

~~~text
reactor-demand-demo/
  pom.xml
  src/main/java/example/DemandVsTimeDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-demand-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.17</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/DemandVsTimeDemo.java**:

~~~java
package example;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class DemandVsTimeDemo {
    public static void main(String[] args) {
        List<Long> upstreamRequests = new ArrayList<>();
        List<Long> downstreamRequests = new ArrayList<>();

        List<Integer> numbers = Flux.range(1, 9)
                .doOnRequest(upstreamRequests::add)
                .limitRate(4, 0)
                .doOnRequest(downstreamRequests::add)
                .collectList()
                .block();

        System.out.println("downstream=" + downstreamRequests);
        System.out.println("upstream=" + upstreamRequests);
        System.out.println("numbers=" + numbers);

        List<Integer> onlyFour = Flux.range(1, 9)
                .take(4)
                .collectList()
                .block();

        System.out.println("take(4)=" + onlyFour);

        List<Integer> delayed = Flux.range(1, 3)
                .concatMap(n -> Mono.delay(Duration.ofMillis(100))
                                    .thenReturn(n))
                .collectList()
                .block();

        System.out.println("delayed=" + delayed);
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.DemandVsTimeDemo
~~~

**Lines printed by the program** with the synchronous `Flux.range` source:

~~~text
downstream=[9223372036854775807]
upstream=[4, 4, 4]
numbers=[1, 2, 3, 4, 5, 6, 7, 8, 9]
take(4)=[1, 2, 3, 4]
delayed=[1, 2, 3]
~~~

Explanation:

1. **collectList()** collects the entire source, so downstream of `limitRate` sends demand **Long.MAX_VALUE** (`9223372036854775807`).
2. **limitRate(4, 0)** splits demand propagated to the source into four-element batches; nine elements require three rounds.
3. **numbers** still contains **all nine** elements, proving `limitRate` does not cap the total count.
4. **take(4)** caps the total number of elements to four; this is a different operator.
5. **Mono.delay** introduces a time delay in each inner Publisher. **concatMap** waits for each inner publisher to complete in order, so the delays run sequentially for one subscription. The data result is still `1, 2, 3`.

Delay durations can fluctuate due to the Scheduler and machine load; the output only prints values and does not assert exact millisecond timings. **block()** is used at the CLI boundary to observe results; avoid placing `block()` inside WebFlux request handling or event-loop threads.

For pipelines with async sources, prefetching, cancellation, or complex operators, the `request(n)` trace may differ in timing and counts. Do not assume the `[4,4,4]` pattern is a promise for every source.

## 7. Difference from Total Element Limits: `take(n)`

~~~java
Flux<Integer> all = Flux.range(1, 100).limitRate(10);
Flux<Integer> firstTen = Flux.range(1, 100).take(10);
~~~

- **all** can emit all 100 elements; `limitRate` only changes how batches are requested.
- **firstTen** emits at most 10 elements, then completes and performs upstream cancellation when appropriate.

Some older Reactor docs mention **limitRequest(n)** for total demand capping; in modern Reactor versions, that operator is deprecated, and **take(n)** is the appropriate choice for capping total elements.

Do not confuse:

~~~text
limitRate(10) : Shapes demand into batches; can receive 100/100.
take(10)      : Stops after at most 10 elements; receives 10/100.
~~~

These are two completely different needs. Similarly, **take(Duration)** ends the stream based on a duration, but does not automatically become an API requests-per-second quota.

## 8. How Does Time-Based Rate Limiting Work?

Time-based limiting must define at least four things:

1. **What is counted**: HTTP requests, email sends, queries, events, or other operations.
2. **Quota scope**: application-wide, per API key, user, tenant, IP, or route.
3. **Time unit and burst**: e.g., 60/minute, 5/second, and whether short bursts are allowed.
4. **Policy when quota is exhausted**: bounded wait, reject with HTTP 429, or place work in a bounded queue.

Some common algorithms:

| Mechanism | Idea | Notes |
| --- | --- | --- |
| **Fixed window counter** | Count operations in each fixed window | Can burst across window boundaries |
| **Sliding window** | Count or estimate within a sliding window | Can be fairer, but costs more state |
| **Token bucket** | Each operation consumes a token; tokens refill over time | Allows bursts up to bucket capacity |
| **Leaky bucket / pacing queue** | Operations are released at a relatively steady rate | Requires a queue, timeout, and overflow policy |
| **Semaphore** | Allows at most K operations running concurrently | A concurrency limit, **not** a time-based rate limit |

For example, a token bucket with capacity **10 tokens**, refilling **5 tokens/second**. If the bucket is full, it can accept a burst of 10 requests nearly instantaneously. Afterward, available tokens depend on time. Because bursts are allowed, this mechanism **does not necessarily satisfy a strict wording like "no more than five requests in any one-second window"**; choose an algorithm matching your concrete SLA/quota requirements.

Limiter units are **requests/second**, **tokens/second**, **requests/minute**, or similar. Meanwhile, `limitRate`'s `highTide` only has units of **elements in a demand batch**.

## 9. Why `delayElements` Cannot Replace a Production Rate Limiter

~~~java
Flux<Integer> paced = Flux.range(1, 4)
        .delayElements(Duration.ofMillis(250));
~~~

The snippet above is an example placed inside a method that already imports `Flux` and `Duration`. It introduces a time delay between elements of **a single subscription**. This is a reasonable tool for demos, tests, or a processing stream that needs controlled slowing down.

However:

- Each subscriber has its own delay sequence. Two subscribers do not automatically share a common quota.
- If an HTTP API is called **before** the delay, you are delaying the **response** rather than preventing the request from starting.
- Delays fluctuate with the Scheduler and do not define burst or identity policies.
- Multiple instances, threads, retries, and out-of-pipeline work can generate additional requests.
- Delays do not automatically return HTTP 429 or enforce gateway backlog limits.

For strict API quotas, you need a mechanism that grants a **permit before starting the operation**, with state matching the quota scope. Delay can only be part of a pacing strategy in controlled cases.

## 10. Difference from Concurrency Limits

For example, suppose a list of IDs needs API calls:

~~~java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(id -> fetchProduct(id), 8);
~~~

This is an illustrative snippet, assuming `ids` is already defined and `fetchProduct(id)` returns `Mono<Product>`. The parameter **8** limits the number of **inner Publishers** processed concurrently within `flatMap` per the operator contract. That **does not mean 8 requests/second**.

If each HTTP call finishes in 10 ms, eight slots can be reused many times in one second. If each call takes 5 seconds, far fewer new calls start per second. Concurrency measures **currently active** work, whereas a rate limiter measures work **started/admitted over time**.

~~~text
limitRate(8)
    -> upstream receives demand in element batches.

flatMap(fetch, 8)
    -> at most 8 inner publishers subscribed concurrently.

tokenBucket(5 calls/sec)
    -> grants or rejects permits according to time quota.

The three numbers 8, 8, and 5 have three different meanings.
~~~

In systems calling partner services, **both concurrency limits and time-based rate limiters** may be needed. The first protects concurrent connections/in-flight work; the second protects quotas.

## 11. Spring WebFlux: Limiting Inbound HTTP Requests

A requirement like "at most 100 requests/minute per API key" is an **HTTP ingress policy**, not a policy on how a `Flux` inside a controller requests elements.

A typical architecture:

~~~text
HTTP client
    |
    v
[Gateway / WebFilter / edge]
    |-- identify user / API key / tenant
    |-- check time-based quota
    |-- within quota: let request proceed
    |-- quota exceeded: return 429 or configured policy
    v
[Spring WebFlux controller]
    |
    v
[Service returning Mono / Flux]
    |
    v
[Reactor Netty response]
~~~

This can be implemented with **Spring Cloud Gateway RequestRateLimiter**, a `WebFilter`, or an external API gateway. If deployed distributed and the quota must be shared system-wide, you need an appropriate distributed/atomic state backend (such as Redis) or equivalent quota coordination mechanism.

Decisions to align on:

- Is the quota per API key, authenticated principal, tenant, route, or IP?
- When exceeding quota, return HTTP **429 Too Many Requests**, do a bounded wait, or queue?
- Should **Retry-After** be sent when a valid wait time can be computed?
- Does the token bucket allow bursts; if so, up to how many?
- Are there multiple pods, and does every pod see the same counters?
- Do logging/metrics reflect requests rejected before reaching the handler?

**Attaching `Flux.limitRate(100)` to a response body does not stop clients from sending 1,000 HTTP requests/second.** Each HTTP request can create an independent pipeline/subscription. When spam protection or resource quotas are needed, enforce them at the ingress boundary.

## 12. Spring WebFlux: Limiting Outbound HTTP Requests

Suppose an external API enforces **5 calls/second** for the entire integration account. `WebClient` code iterating over multiple IDs might look like:

~~~java
Flux<PartnerResponse> result = Flux.fromIterable(ids)
    .flatMap(id ->
        webClient.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(PartnerResponse.class),
        8
    );
~~~

This is an illustrative snippet only; `ids`, `webClient`, `PartnerResponse`, and application configuration must be defined. The **8** in `flatMap` is concurrency, not 8 calls/second. Adding **limitRate(5)** to the chain also does not turn it into a 5 calls/second quota.

You must ensure **each HTTP attempt acquires a permit** from the rate limiter before starting:

~~~text
ID to call
   |
   v
[Rate limiter: acquire permit for key "partner"]
   |                       |
   | permitted             | quota exceeded
   v                       v
Start WebClient        bounded wait / reject / reschedule
   |
   v
HTTP response / timeout / retry
~~~

An illustrative interface for an asynchronous limiter:

~~~java
Mono<Void> awaitPermit(String quotaKey);
~~~

This interface is **illustrative**, not an implementation. Assuming `awaitPermit` returns a `Mono` that completes when a permit is available, you can compose:

~~~java
Flux<PartnerResponse> result = Flux.fromIterable(ids)
    .flatMap(id ->
        awaitPermit("partner")
            .then(Mono.defer(() ->
                webClient.get()
                    .uri("/items/{id}", id)
                    .retrieve()
                    .bodyToMono(PartnerResponse.class)
            )),
        8
    );
~~~

The snippet above is **not yet a standalone runnable program** because application classes and beans are omitted. It simply shows the **correct placement of the limiter**: granting a permit before the `Publisher` representing the HTTP call is subscribed to.

Important note with **retryWhen**: each actual attempt can be a new HTTP request. If the partner's quota counts every attempt, **every retry must pass through the limiter**. Placing the permit outside the entire retry chain without re-acquiring can allow exceeding the quota. You also need to bound retry counts, backoff, timeouts, and the size of the queue waiting for permits.

## 13. Mechanisms That Must Work Together in Production

Example requirements:

- A job processes 10,000 records.
- The partner allows at most 10 HTTP requests/second.
- At most 4 concurrent HTTP calls.
- Each call times out after 2 seconds.
- The record source benefits from receiving demand in batches of 32 elements.

Different mechanisms solve different parts:

~~~text
[Source of 10,000 records]
       |
       | limitRate(32): splits upstream demand
       v
[Flux of records]
       |
       | flatMap(..., 4): limits concurrent inner Publishers
       v
[Rate limiter: 10 calls/s]
       |
       | permit per HTTP attempt
       v
[WebClient / partner service]
       |
       | timeout, retry, backoff, and cancellation
       v
[Result]
~~~

A pipeline must choose the **position** of each mechanism so the right work is protected. For example, if a rate limiter sits after request creation that triggers side effects at assembly time, it is already too late; if concurrency limits are placed only on one worker group while another worker calls the same partner, total quota can still be exceeded.

Do not place faith in a single parameter to "solve every problem of backpressure, rate, and errors".

## 14. Placing `doOnRequest` to Observe Demand

You can observe requested element counts on both sides of the operator:

~~~java
Flux<Integer> pipeline = Flux.range(1, 100)
    .doOnRequest(n -> System.out.println("upstream request=" + n))
    .limitRate(10, 0)
    .doOnRequest(n -> System.out.println("downstream request=" + n));
~~~

Here **doOnRequest before limitRate** is near the source and sees the split requests. **doOnRequest after limitRate** is near the subscriber and sees demand before the operator transforms it.

~~~text
Source -- doOnRequest("upstream") -- limitRate -- doOnRequest("downstream") -- Subscriber
~~~

Several variables affect the trace:

- **buffer(N)** converts demand from buffer counts to original element counts.
- **flatMap** has concurrency and prefetch on inner Publishers.
- **publishOn** has a queue and prefetch to switch execution context.
- **take**, cancellation, and errors can leave a large request partially unused.
- Hot sources or adapters with different buffer/drop policies may not honor requests the same way a simple cold source does.

Therefore, use traces to understand a **specific boundary** rather than inferring every part of the pipeline receives identical requests. In high-load production, avoid flooding logs with per-item/per-request lines; use appropriate metrics/sampling.

## 15. Does `limitRate` Protect Memory or the Event Loop?

Only partially, and with no general guarantee. It can reduce how aggressively upstream is asked to supply data, yet other factors can still overload the system:

- The source itself still holds a large buffer before returning the `Flux`.
- A `flatMap` operator uses many inner Publishers, each with its own prefetch.
- Multiple Subscribers or multiple independent HTTP requests run concurrently.
- Unbounded queues exist outside Reactor.
- A callback uses blocking JDBC or `Thread.sleep` on the Netty event loop.
- The connection pool is too small or too many retries happen at once.
- Hot sources exhibit drop/buffer behavior when downstream is slow.

**limitRate does not turn blocking into non-blocking**, does not create schedulers, does not protect inbound requests, and does not manage total RAM on its own. To protect the event loop, use non-blocking APIs or isolate blocking tasks on an appropriate scheduler when legacy APIs cannot be replaced. To protect memory, inspect all buffers, queues, and concurrent work counts.

## 16. Which Metrics to Measure to Know You Are Solving the Right Problem?

| Metric | Meaning | Used to Verify |
| --- | --- | --- |
| `request(n)` values near source | Actual demand propagated upstream | Whether `limitRate` splits requests as expected |
| Total elements emitted/consumed | Final data volume | Whether `limitRate` is being confused with a total count limit |
| HTTP requests started/second | Actual calls initiated over time | Whether outbound quota is respected |
| HTTP 429 and rejected-permit count | Frequency of hitting quota | Rate limiting policy |
| Active HTTP calls | In-flight HTTP work | Concurrency limit, connection pool |
| Queue length and waiting time | Work waiting for resources or permits | Risk of queue overflow/latency spikes |
| p50/p95/p99 latency, throughput | Application performance/latency | Impact of batching/prefetch and limiters |
| Retry attempts, timeouts, cancellations | Reliability/operation lifecycle | Whether each attempt counts toward quota |

These are **suggested metric categories**, without claiming all exact metric names are built into Reactor or Spring Boot.

When measuring a **distributed rate limiter**, check the aggregate rate across all instances; per-pod statistics alone can mask exceeding the global quota.

## 17. Common Mistakes

| Misconception | Consequence | Fix |
| --- | --- | --- |
| `limitRate(10)` means 10 requests/second | Can severely exceed HTTP quotas | Use a time-based limiter at ingress/egress |
| `limitRate(10)` takes exactly 10 elements | Stream still emits all data when demand exists | Use `take(10)` to cap total elements |
| `limitRate(10, 2)` means 10 elements every 2 seconds | `lowTide` units misunderstood | Both `highTide`/`lowTide` belong to demand control |
| `flatMap(..., 8)` means 8 HTTP calls/second | Fast calls can start many times per second | Combine concurrency limits with a rate limiter |
| `delayElements(1 second)` protects the whole system | Multiple subscriptions/pods add up in rate | Shared limiter matching the actual quota |
| `limitRate` is an exact RAM limit | Buffers and sources outside the operator still exist | Tune queues, prefetch, concurrency, backpressure |
| An in-memory per-pod rate limiter is a global quota | Multiple pods accumulate permits | Synchronize quota cluster-wide when needed |
| Retries do not count as new requests | Exceeds partner API quota | Acquire a permit per HTTP attempt |
| Source must emit all n immediately after `request(n)` | Misunderstands Publisher contract | Demand is only maximum permitted emission |
| Adding `limitRate` on response to stop HTTP spam | Clients still create new requests | Enforce rate limiting at Gateway/WebFilter/edge |

## 18. Self-Check Questions

**1.** How many elements can `Flux.range(1, 1000).limitRate(20)` emit at most if downstream wants all of them and does not cancel?

**1,000.** 20 is the upstream batch request level, not a cap on total elements.

**2.** Does `limitRate(20, 0)` guarantee 20 elements per second?

**No.** This is strict batch demand, with no time parameter.

**3.** When an API requires 5 calls/s, is `flatMap(fetch, 5)` sufficient?

**Not necessarily.** The 5 limits concurrency, not the number of calls started within one second.

**4.** When is `take(10)` more appropriate than `limitRate(10)`?

When the goal is to **process at most 10 elements and then complete**, rather than tuning how demand is propagated to the source.

**5.** With three instances, each having a 100 requests/minute limiter, is the system-wide quota definitely 100 requests/minute?

**No.** If state is not shared, the instances together can allow total requests exceeding 100/minute.

**6.** To avoid exceeding an external service's quota, where should permits be acquired?

**Before starting each HTTP attempt** that must be counted. Retries can create new attempts, so they must be accounted for under the quota policy.

**7.** Downstream calls `request(Long.MAX_VALUE)`; does `limitRate(4, 0)` still matter?

**Yes.** It splits that huge demand into smaller upstream request batches per `highTide`, even though upstream may eventually emit all data.

**8.** Does a 250 ms delay inside a `concatMap` enforce 4 requests/s across all instances?

**No.** It only paces execution of that single pipeline/subscription. A stateful rate limiter matching the scope is needed to enforce the total quota.

## 19. References

- [Reactor Core Reference Guide — Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): `request(n)`, `limitRate`, `highTide`, `lowTide`, and replenishment.
- [Reactor Core 3.6 — Flux API](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Flux.html): `limitRate`, `take`, `flatMap`, `delayElements`, `doOnRequest`.
- [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm): Publisher–Subscriber–Subscription contract.
- [Spring Cloud Gateway RequestRateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html): example of enforcing HTTP quotas at the Gateway.
- [Java 17 Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): duration type used in pacing examples.

**Key takeaway:** **limitRate** is a mechanism to **split upstream demand into element batches**, not a time-based quota. **take(n)** caps total elements, **flatMap(..., concurrency)** limits concurrent inner Publishers, **delayElements** adds per-pipeline delay, and a **time-based rate limiter** grants permits per operations over time within a quota scope. Pick the right layer, measure the right signal, and do not infer requests/second from `request(n)`.