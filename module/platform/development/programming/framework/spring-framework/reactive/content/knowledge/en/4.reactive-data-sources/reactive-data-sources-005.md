# Time-Based Sources with interval and delay in Project Reactor

> **Topic:** Creating Data Sources · **Module:** Spring Framework – Reactive. This lesson explains how to emit signals over time and delay sources/signals using Reactor Mono and Flux; it includes a self-running Java 17+ program, virtual-time tests, and an example applied with Spring WebFlux.

## 1. Desired Outcomes

After completing this lesson, you need to:
1. Create a **Mono.delay** source that emits only one value after a wait and a **Flux.interval** source that emits ticks periodically.
2. Distinguish **delaySubscription**, **delayElement**, **delayElements**, and **delaySequence**; accurately predict the timing of subscribe, onNext, and onComplete.
3. Understand Scheduler, cold publishers, cancel, take, and overflow from insufficient demand; never block the event-loop with Thread.sleep or block in WebFlux.
4. Write tests with **StepVerifier.withVirtualTime** to verify hours of logical time without waiting hours in real time.
5. Bring tick sources into polling or Server-Sent Events (SSE) with clear lifecycle, load limits, and slow-client handling.

**Core mindset:** these methods **describe asynchronous time-based work**; the pipeline's clock normally starts upon subscription, not when declaring the Flux or Mono variable. Duration is a relative time interval, not a fixed schedule by time zone.

~~~text
Mono.delay(2s)                 subscribe ─── 2s ─── 0L | complete
Flux.interval(1s)              subscribe ─ 1s ─ 0 ─ 1s ─ 1 ─ 1s ─ 2 ─ ...
Flux.interval(2s, 1s)          subscribe ─── 2s ─── 0 ─ 1s ─ 1 ─ ...
delaySubscription(2s)          subscribe ─── 2s ─── upstream subscribe → data
Flux.just(A,B,C).delayElements(1s)   subscribe ─ 1s ─ A ─ 1s ─ B ─ 1s ─ C
Flux.just(A,B,C).delaySequence(1s)   subscribe ─ 1s ─ A,B,C
~~~

The diagram conveys **approximate** order and waiting intervals. Scheduler, machine load, upstream execution time, request demand, and buffering can affect actual observed timing. In Reactive Streams, a source may emit multiple onNext signals and finally onComplete or onError; subscriber cancellation signals the running source to stop. Mono has at most one onNext, whereas Flux can have many.

## 2. Mono.delay: Emitting Exactly One Tick

**Mono.delay(Duration delay)** creates a Mono<Long>. After subscribing and the delay elapses, it emits **0L** and completes. The value 0L is the first tick per the API contract, **not a timestamp** and not the number of elapsed seconds.

~~~java
Mono<Long> timer = Mono.delay(Duration.ofSeconds(2));
// subscribe, wait about 2 seconds, onNext(0L), onComplete.
~~~

The timer variable in this fragment only describes the pipeline; there is no subscriber yet, so nothing is emitted. To return a message after a wait:

~~~java
Mono<String> welcomeLater = Mono.delay(Duration.ofSeconds(2))
    .map(tick -> "Ready");
~~~

To have only a completion signal after the wait without needing the 0L data:

~~~java
Mono<Void> finishedLater = Mono.delay(Duration.ofSeconds(2)).then();
~~~

**When to use:** scheduling a one-off signal, creating testable delays, simulating slow responses, coordinating timeouts/fallbacks. **Do not use** Mono.delay as a durable job system: if there is no subscription or the process stops, there is no mechanism to persist jobs to run after a restart. To schedule by wall-clock time (e.g., 08:00 every day), choose a calendar/cron scheduler and corresponding persistence, rather than deriving from interval/delay.

Mono.delay has an overload accepting a Scheduler when you need dedicated control over where the timer runs. There is no need to create threads or call sleep for timing; the Scheduler is responsible for scheduling.

## 3. Flux.interval: Emitting 0, 1, 2... Periodically

### 3.1. Three Basic Ways to Write It

~~~java
// Emits 0L after about 1s; 1L after about 2s; continues indefinitely.
Flux<Long> oneSecond = Flux.interval(Duration.ofSeconds(1));

// Waits about 2s before tick 0, then one tick every 1s.
Flux<Long> withInitialDelay = Flux.interval(
    Duration.ofSeconds(2), Duration.ofSeconds(1));

// With a dedicated time scheduler, in an application that already manages lifecycle:
Flux<Long> customTimer = Flux.interval(
    Duration.ofSeconds(2),
    Duration.ofSeconds(1),
    scheduler);
~~~

In the final fragment, scheduler is a **Scheduler** variable already created/injected in the application, not a built-in variable in Reactor. By default, timer operators use an appropriate Reactor Scheduler, typically parallel. You do not need to manually spawn a thread per tick.

**Mandatory rules to remember:**
- The interval(period) form emits **tick 0 after period**, not immediately; the interval(initialDelay, period) form lets you change the initial mark.
- The tick has type Long and increments from 0, without containing system time. To attach a timestamp, create it on emission, e.g. map(tick -> Instant.now()), and understand the non-determinism of wall clock in tests.
- Flux.interval itself is an **infinite source**, normally having no onComplete. In finite examples use take(n); in real streams you need a cancel mechanism when clients leave.
- Each subscription to a cold interval source has its own rhythm. Two subscribers subscribing at different times will not automatically synchronize to a global rhythm.

### 3.2. Ending an Infinite Source with take

~~~java
Flux<Long> firstThree = Flux.interval(Duration.ofMillis(100))
    .take(3); // 0L, 1L, 2L, then onComplete downstream.
~~~

Once three elements are reached, take completes downstream and cancels upstream to stop new ticks. When an HTTP request is cancelled, Spring WebFlux usually forwards cancel to the Publisher; however, business code still needs to manage resources not owned by the subscription.

Do not call blockLast() on an infinite Flux.interval: the operation will wait forever because there is no terminal signal. In WebFlux controllers, also do not call block()/blockFirst() even on finite sequences because it can lock the event-loop.

### 3.3. Backpressure: interval Cannot Stop Time

Reactive Streams allows a subscriber to signal demand via request(n). Flux.interval is a **clock-driven source** and cannot force time to “wait” for enough requests. Per the Reactor API, if a tick is due and downstream has not requested enough, interval can emit **onError(IllegalStateException: overflow)**. This is not a random network or thread error, but a reaction to insufficient demand.

The solution must follow business requirements:
- Subscriber needs regular ticks: ensure proper demand; test with non-zero initial request and cancellation policy.
- Only need the latest state (e.g., UI heartbeat): consider **onBackpressureLatest** or **onBackpressureDrop** with an explicit tick-loss policy.
- Need to preserve every event: do not treat interval as an event log; use a queue/broker/storage and replay/ack mechanisms.
- Do not use an unbounded buffer to mask overflow, as it can cause RAM growth when consumers stay slow.

A tick can trigger an I/O task. If using flatMap to call a remote API, limit concurrency and set timeouts; when processing takes longer than the period, tasks can overlap. If sequential execution is needed, consider concatMap, while also having a policy for when the source emits faster than consumption.

## 4. Not All Delays Are the Same

There is an important difference between **creating a time-based source** (Mono.delay/Flux.interval) and **applying time effects to an existing Publisher**.

| Method | What Is Delayed | Meaning |
| --- | --- | --- |
| Mono.delay(d) | Creating a single onNext(0L) after d | One-shot source, then completes. |
| Flux.interval(d) | Creating a tick stream every d | Periodic source, infinite unless taken/cancelled. |
| source.delaySubscription(d) | Subscription to upstream | Upstream starts working later. |
| mono.delayElement(d) | The onNext value of a Mono with data | Empty/error Mono does not wait d as a value. |
| flux.delayElements(d) | Each onNext element | Can pace elements of an immediately-emitting source. |
| flux.delaySequence(d) | Shifting the whole sequence later | Preserves relative spacing between elements from the source. |

### 4.1. delaySubscription: Waiting Before Starting the Source

~~~java
Mono<String> remote = Mono.defer(() -> {
    System.out.println("Upstream subscribed");
    return Mono.just("OK");
}).delaySubscription(Duration.ofSeconds(2));
~~~

Mono.defer defers creating the Publisher until subscription. With delaySubscription, the log line only appears after the wait if the subscription is still active. This is the core difference from delayElement: a source with side effects on subscribe can start immediately if only the output signal is delayed. Note: if a hot task was already launched outside the pipeline, delaySubscription does not automatically delay that task.

### 4.2. Mono.delayElement: Waiting Before Receiving the Value

~~~java
Mono<String> result = Mono.just("OK")
    .delayElement(Duration.ofSeconds(2));
~~~

The source is still subscribed to; **onNext("OK")** reaches downstream late. With Mono.empty() or an erroring source, there is no element for delayElement to delay, so empty completion/error typically forwards without waiting 2 seconds. If you need to delay the entire upstream process, use delaySubscription. If you need a delay before switching to another publisher, use Mono.delay(d).then(otherPublisher).

### 4.3. Flux.delayElements: Delaying Each onNext

~~~java
Flux<String> paced = Flux.just("A", "B", "C")
    .delayElements(Duration.ofSeconds(1));
~~~

With an **immediately-emitting** source, A is seen after about 1s, B around 2s, C around 3s. delayElements often acts as downstream pacing while preserving order; however, it should not be viewed as a complete rate limiter for every kind of asynchronous source. It only delays signals, does not automatically increase DB/HTTP capacity, and does not guarantee exact clock precision. Per the Javadoc, direct empty/error signals are not delayed like onNext.

### 4.4. Flux.delaySequence: Shifting the Whole Stream

~~~java
Flux<String> shifted = Flux.just("A", "B", "C")
    .delaySequence(Duration.ofSeconds(1));
~~~

The source is subscribed to **immediately**, while downstream is time-shifted by about 1 second; relative intervals between elements are preserved. With an immediate source, A/B/C can appear close together after 1 second. With a source emitting every 500ms, the ~500ms spacing is preserved rather than being turned into 1 second between each element.

**Quick comparison on the same source Flux.just(A,B,C):**
- delaySubscription(2s): subscribes to upstream after 2s, A/B/C arrive quickly.
- delayElements(2s): A after ~2s, B after 4s, C after 6s.
- delaySequence(2s): subscribes to upstream immediately, A/B/C after ~2s and close together.
  
These are predictions for a synchronous upstream; for a source that already takes time to produce values, measure/test the real signals.

### 4.5. What Is Not a Delay?

Thread.sleep(1000) **blocks the running thread**. On a Netty event-loop server, a sleep can slow down many other requests. Mono.delay and delayElements use scheduling mechanisms and do not require blocking a thread while waiting. However, **there is no magic**: if a map/timer callback does heavy CPU work or calls synchronous JDBC, the Scheduler thread can still become busy. When bridging a blocking library, isolate with a bounded boundedElastic or choose a reactive driver; do not use Schedulers.parallel for blocking I/O.

## 5. Scheduler and Time Management

The Scheduler handles execution/timing. Time operators usually have overloads accepting a Scheduler; if unspecified, Reactor provides a default Scheduler. subscribeOn affects the subscribe path and upstream source; publishOn switches context for downstream operators. They are not substitutes for delay when the requirement is waiting an exact Duration.

~~~java
Scheduler timer = Schedulers.newSingle("app-timer");
// Place timer in a bean with a clear lifecycle; do not dispose before subscription.
Flux<Long> ticks = Flux.interval(
    Duration.ofSeconds(1), Duration.ofSeconds(1), timer);
~~~

The fragment above requires importing reactor.core.scheduler.Scheduler and Schedulers; it is not a standalone program, and to observe ticks you must subscribe at an appropriate boundary. With a self-created Scheduler, the application must dispose it when no subscriptions remain or on shutdown; avoid creating many Schedulers per request. In Spring, let the framework manage it or configure a bean lifecycle. Do not use Schedulers.newSingle for heavy blocking I/O.

**Accuracy:** timers are affected by thread scheduling, GC pauses, CPU, container throttling, and system load. The 100th tick does not prove exactly 100 seconds have elapsed. Interval is a schedule *relative to subscription*, and does not solve exact calendar/date scheduling, DST, time zones, catch-up after restart, or leader election across multiple instances.

## 6. Runnable Java 17+ Project

Uses Reactor Core **3.8.8** (stable release of Project Reactor at writing time) and JUnit 5. Examples run in a **CLI**, where block() only serves to wait for results at the final boundary to print output; when using WebFlux, return Mono/Flux to the framework and do not block.

### 6.1. Structure

~~~text
reactor-timed-sources/
├── pom.xml
├── src/main/java/com/example/timed/TimedDemo.java
└── src/test/java/com/example/timed/TimedDemoTest.java
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactor-timed-sources</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/com/example/timed/TimedDemo.java**:

~~~java
package com.example.timed;

import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class TimedDemo {
    public static void main(String[] args) {
        Long once = Mono.delay(Duration.ofMillis(50)).block();
        System.out.println("delay=" + once);

        List<Long> periodic = Flux.interval(Duration.ofMillis(50))
            .take(3).collectList().block();
        System.out.println("interval=" + periodic);

        List<Long> afterInitialWait = Flux.interval(
                Duration.ofMillis(100), Duration.ofMillis(50))
            .take(3).collectList().block();
        System.out.println("initialWait=" + afterInitialWait);

        String message = Mono.just("OK")
            .delayElement(Duration.ofMillis(50)).block();
        System.out.println("delayElement=" + message);

        List<String> paced = Flux.just("A", "B", "C")
            .delayElements(Duration.ofMillis(50)).collectList().block();
        System.out.println("delayElements=" + paced);

        List<String> shifted = Flux.just("A", "B", "C")
            .delaySequence(Duration.ofMillis(50)).collectList().block();
        System.out.println("delaySequence=" + shifted);

        List<Integer> startLater = Flux.range(1, 3)
            .delaySubscription(Duration.ofMillis(50))
            .collectList().block();
        System.out.println("delaySubscription=" + startLater);
    }
}
~~~

In the project directory, Java 17+ and Maven are required:

~~~bash
java -version
mvn -version
mvn test
mvn -q exec:java -Dexec.mainClass=com.example.timed.TimedDemo
~~~

**Stdout lines printed by main** (excluding Maven logs):

~~~text
delay=0
interval=[0, 1, 2]
initialWait=[0, 1, 2]
delayElement=OK
delayElements=[A, B, C]
delaySequence=[A, B, C]
delaySubscription=[1, 2, 3]
~~~

Values/order are fixed; actual latency may vary by a few milliseconds or more. The block() calls appear only in CLI main and **do not belong in WebFlux APIs**.

## 7. Testing with VirtualTimeScheduler / StepVerifier

This is how to verify **logical time** without waiting in real time. StepVerifier.withVirtualTime takes a supplier to build the Publisher **after the virtual scheduler has been installed**. Each thenAwait(Duration) advances the virtual clock; expectNext and verifyComplete assert exact signals.

**src/test/java/com/example/timed/TimedDemoTest.java**:

~~~java
package com.example.timed;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TimedDemoTest {

    @Test
    void intervalStartsWithZeroAndStopsAfterTake() {
        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofSeconds(1)).take(3))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(0L)
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(1L)
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(2L)
            .verifyComplete();
    }

    @Test
    void monoDelayCanWaitADayInVirtualTime() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofDays(1)))
            .expectSubscription()
            .thenAwait(Duration.ofDays(1))
            .expectNext(0L)
            .verifyComplete();
    }

    @Test
    void delayElementsPacesSynchronousValues() {
        StepVerifier.withVirtualTime(() ->
                Flux.just("A", "B", "C")
                    .delayElements(Duration.ofSeconds(1)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("A")
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("B")
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("C")
            .verifyComplete();
    }

    @Test
    void delaySubscriptionDefersUpstreamSideEffect() {
        AtomicInteger starts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.defer(() -> {
                    starts.incrementAndGet();
                    return Mono.just("ready");
                }).delaySubscription(Duration.ofHours(2)))
            .expectSubscription()
            .then(() -> assertEquals(0, starts.get()))
            .thenAwait(Duration.ofHours(2))
            .expectNext("ready")
            .verifyComplete();

        assertEquals(1, starts.get());
    }

    @Test
    void intervalWithoutDemandSignalsOverflow() {
        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofSeconds(1)), 0)
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

The tests illustrate: ticks start at 0 and stop thanks to take; waiting 1 virtual day; delayElements spaces elements out; delaySubscription blocks side effects; interval without demand at emission time signals an error.

**Rules for proper testing:**
- Construct Flux.interval/Mono.delay **inside the lambda** of withVirtualTime, do not pass a pre-created Flux using a real Scheduler.
- Advance the clock using thenAwait or expectNoEvent; do not use Thread.sleep in tests.
- When testing infinite sources, use take(n) or thenCancel; do not wait indefinitely on verifyComplete.
- With expectNoEvent, call expectSubscription first, because the subscription event counts too; you can choose a mark like 999ms to be sure the 1s tick has not arrived yet.
- For operators using a custom Scheduler created outside the test or real I/O, VirtualTimeScheduler cannot control them automatically; mock/fake the dependency or redesign the test boundary.

### 7.1. Testing Cancellation with Finite Request

The fragment below goes inside a test method, using the same imports as the file above:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)), 2)
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(1L)
    .thenCancel()
    .verify();
~~~

The subscriber requests two elements and actively cancels before the third tick. The interval subscription stops emitting for this subscriber. If upstream has an external Future/library already running without being tied to reactive lifecycle, cancel is not guaranteed to stop that work automatically; cancellation support must be designed from the source.

### 7.2. Testing Timeout with Fallback

Fragment inside a test method:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5))
            .timeout(Duration.ofSeconds(2))
            .onErrorReturn(-1L))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(-1L)
    .verifyComplete();
~~~

Here timeout cancels the 5-second waiting upstream and switches to the fallback value -1L when 2 virtual seconds elapse. In practice, choose fallbacks according to the domain; do not turn data/integrity failures into unchecked “success” results.

## 8. Applying in Spring WebFlux: SSE

Reactor can emit ticks over **Server-Sent Events** so browsers/HTTP clients receive a continuous stream of updates. In WebFlux, the controller **returns a Publisher**, and the framework subscribes and streams data out over HTTP; do not call block()/subscribe() in the controller.

The controller snippet below is an **integration fragment**, not the standalone Maven program in section 6: it needs a Spring Boot app with spring-boot-starter-webflux, server configuration, and WebFlux imports.

~~~java
package com.example.web;

import java.time.Duration;
import java.time.Instant;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
class ClockController {
    record Tick(long sequence, String time) {}

    @GetMapping(path = "/api/ticks",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Tick>> stream() {
        return Flux.interval(Duration.ZERO, Duration.ofSeconds(1))
            .map(n -> ServerSentEvent.<Tick>builder()
                .id(Long.toString(n))
                .event("tick")
                .data(new Tick(n, Instant.now().toString()))
                .build());
    }
}
~~~

Against a server running on localhost:8080, you can try:

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/ticks
~~~

Example SSE data frame, **illustrative only** (time values are determined by the real clock at runtime):

~~~text
id:0
event:tick
data:{"sequence":0,"time":"2026-11-08T01:00:00Z"}

id:1
event:tick
data:{"sequence":1,"time":"2026-11-08T01:00:01Z"}
~~~

Considerations before going to production:
- **Each HTTP subscriber gets its own cold interval.** If you must broadcast shared events, design multicast/Sinks with explicit replay, late clients, and overload policies.
- Clients can disconnect at any time; the pipeline needs proper cancellation, cleanup, timeouts, and metrics. SSE through proxies may be buffered or timed out; check network configuration and reconnects.
- If map() does heavy CPU work or blocks, timer threads can become congested. With remote WebClient returning Mono, use flatMap with bounded concurrency and a slow-consumer policy.
- **Instant.now() is not altered by virtual time**. To test timestamps you can inject java.time.Clock, while testing intervals with VirtualTimeScheduler.
- SSE tick emission does not guarantee event retention/replay; you need durable event IDs and a broker/storage if business rules require zero data loss.
- Authentication, authorization, connection limits, and resource protection are needed just like other HTTP APIs.

## 9. Asynchronous Polling: Using Ticks to Trigger Work

Example fragment for a service with a reactive WebClient/repository API:

~~~java
Flux<Status> statuses = Flux.interval(Duration.ofSeconds(5))
    .flatMap(tick -> statusClient.fetchStatus(), 2);
~~~

Assuming statusClient.fetchStatus() is an actual application method returning **Mono<Status>**. The fragment is illustrative only and does not run standalone since Status/statusClient are not defined. flatMap(..., 2) limits at most two concurrent inner subscriptions; results may differ from tick order. If sequential execution is needed, consider concatMap, while also understanding what happens when a task takes longer than the period. Do not use interval(5s) and assume it waits for the previous poll to finish before starting the next round.

**Set operational limits:** timeouts for remote calls and the overall stream, conditional retry/backoff for transient errors, concurrency/connection/queue limits, and stopping polling when the subscriber cancels. If polling performs writes, idempotency is needed on retry; if zero missed triggers are required, use a durable job queue instead of interval. For upstream errors, decide whether onError terminates the entire stream or uses onErrorResume within each inner call to continue next period; do not swallow errors vaguely.

## 10. Quick Selection Table

| Situation | Choose | Note |
| --- | --- | --- |
| Emit one signal after 1 second then complete | Mono.delay(1s) | Value is 0L. |
| Generate ticks every 1 second indefinitely | Flux.interval(1s) | First tick after ~1s. |
| Wait 3 seconds before ticking, then every 500ms | Flux.interval(3s, 500ms) | Initial delay separate from period. |
| Wait 2 seconds before connecting remotely | source.delaySubscription(2s) | Defers upstream subscription. |
| Have a Mono with a value, want to deliver after 2 seconds | mono.delayElement(2s) | Empty/error Mono is not delayed like onNext. |
| Have A,B,C emitted immediately, want them 1 second apart | flux.delayElements(1s) | Per-element pacing. |
| Want the whole sequence 1 second later while keeping source rhythm | flux.delaySequence(1s) | Upstream subscribes immediately. |
| Want exactly 5 ticks then finish | interval(...).take(5) | Cancels source after enough elements. |
| Test a 24-hour timer in a few milliseconds | StepVerifier.withVirtualTime | Build Publisher inside the lambda. |
| Run a job precisely at 08:00 and recover after restart | Calendar scheduler + storage | Do not use interval as a durable cron. |

## 11. Common Mistakes and Fixes

1. **Seeing no ticks:** only created Flux, have not subscribed yet. In WebFlux return Flux so the framework subscribes; in tests use StepVerifier; in CLI use an appropriate boundary.
2. **Program hangs:** waiting for completion of an infinite interval. Add take, a stop condition, or cancel. Do not use blockLast() on non-terminating sources.
3. **First tick arrives 1 period late:** interval(period) waits for period by design. If you want the first one nearly immediately, use initial delay Duration.ZERO.
4. **Confusing delaySequence with delayElements:** delaySequence shifts the whole sequence and preserves source rhythm, whereas delayElements delays each value. With Flux.just, outputs differ clearly.
5. **Mono.empty().delayElement still completes immediately:** delayElement only delays values; choose delaySubscription or Mono.delay(...).then(...) if you want to delay anything else.
6. **Overflow when downstream does not request:** interval needs demand at tick time; design demand/drop/latest or a queued source, never unbounded buffering.
7. **Virtual time test hangs:** created Publisher before the supplier, forgot thenAwait, or used a custom Scheduler not managed by virtual time.
8. **CPU/HTTP congested despite using delay:** there is a blocking operation inside a callback. Offload blocking I/O to bounded boundedElastic or use reactive APIs, and measure with a profiler.
9. **Timestamp drift or wrong cron:** interval uses relative duration; scheduling delays and wall clock are not exact calendar SLAs.
10. **Putting retry on an entire pipeline with side effects:** retry re-subscribes, which can recreate ticks or re-invoke writes. Define retry scope and idempotency before using.

## 12. Self-Check Exercises

**Exercise 1 – 5 ticks:** Generate numbers 0..4 with a 200ms period and verify successful completion with StepVerifier.withVirtualTime.

~~~java
Flux<Long> five = Flux.interval(Duration.ofMillis(200)).take(5);
~~~

**Exercise 2 – Do not open the source too early:** Use Mono.defer(...) with an AtomicInteger incremented on subscription, add delaySubscription(3s), and verify the counter remains 0 before the deadline and becomes 1 after 3 virtual seconds.

**Exercise 3 – Changing rhythm:** A source already emits two events 500ms apart. Try delayElements(2s) and delaySequence(2s); write tests observing the spacing between events downstream to prove the difference.

**Exercise 4 – Stopping a stream:** Create an infinite Flux.interval and write StepVerifier.withVirtualTime(...).thenCancel().verify(); explain how cancellation differs from onComplete and why blockLast should not be called.

**Exercise 5 – Designing SSE for slow clients:** At 1 tick/100ms and a client consuming 1 tick/s, pick one of the policies: drop old ticks/keep latest, bounded buffer with overflow reporting, or durable event storage and replay. Write a low-demand test. No single operator simultaneously guarantees zero data loss, zero resource growth, and zero latency for an infinitely slow consumer.

## 13. Checklist for Production Applications

- [ ] Distinguished **time-based emitting sources** from **operators delaying sources/signals**.
- [ ] Identified first tick, period, termination condition, and subscription ownership.
- [ ] Chosen an appropriate Scheduler and closed self-created Schedulers according to lifecycle.
- [ ] Defined behavior when downstream demand is insufficient and when callbacks are slower than the period.
- [ ] Controlled timeouts, concurrency, memory buffers, and retries; no blocking on the WebFlux event-loop.
- [ ] Have tests with virtual time for onNext/onComplete/onError and cancel.
- [ ] For SSE, verified disconnect, reconnect, replay/buffering, and resource limits.
- [ ] For critical jobs, designed scheduling/persistence instead of plain interval.

## 14. Further Reading

1. Project Reactor – Flux.interval, delayElements, delaySequence, delaySubscription (API 3.8.8): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
2. Project Reactor – Mono.delay, delayElement, delaySubscription: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
3. Reactor Test – StepVerifier.withVirtualTime: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
4. Reactor Reference – Schedulers, backpressure, and testing: https://projectreactor.io/docs/core/release/reference/
5. Spring WebFlux – Reactive web and streaming: https://docs.spring.io/spring-framework/reference/web/webflux.html

**Outcomes you should be able to explain yourself:** (a) why Mono.delay(1s) produces 0L, (b) why interval is infinite despite starting at tick 0, (c) when delaySubscription actually prevents side effects, (d) the difference between delayElements and delaySequence, (e) how StepVerifier controls virtual hours, and (f) why interval can error if downstream does not request.
