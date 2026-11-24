# `firstWithValue` and `firstWithSignal` in Project Reactor

> **Module:** Spring Framework – reactive · **Parent topic:** Combining and Splitting Streams. This lesson covers two operators that pick one winning source in a race among multiple Publishers: **firstWithSignal** selects the source that emits any signal earliest, while **firstWithValue** selects the source that emits a value earliest. Contents include mechanics, a runnable Java 17+ example, virtual-time testing, composite errors, cancellation, and Spring WebFlux applications.

## 1. What Should You Be Able to Do After This Lesson?

1. Accurately distinguish an **onNext** value from an **onComplete** (empty source) and **onError** (errored source) signal.
2. Choose appropriately among **Mono.firstWithSignal**, **Mono.firstWithValue**, **Flux.firstWithSignal**, and **Flux.firstWithValue** based on business requirements.
3. Predict the outcome when one source completes empty, one source emits an error, one source emits data slowly, and one source never emits.
4. Explain why with a Flux, the source that wins with the first element **continues emitting all subsequent elements**, while losing sources are cancelled if already subscribed.
5. Understand NoSuchElementException with a **composite cause** when no source produces a value, and know how to inspect each cause.
6. Write tests with **StepVerifier.withVirtualTime**, avoiding Thread.sleep tests and unsafe ordering assumptions when sources emit nearly simultaneously.
7. Apply controlled racing for dual-region/replica queries in WebFlux and distinguish it from sequential fallback, merge, zip, and concat.

**One-sentence rule:** `firstWithSignal` races on **signals**; `firstWithValue` races on **values**. Empty completion and errors are signals, not values.

## 2. Foundation: Publishers, Signals, and Subscriptions

**Mono<T>** can emit 0 or 1 value. **Flux<T>** can emit 0 to many values. A source can:
- Call **onNext(value)** to emit data; Reactive Streams forbids emitting null.
- Call **onComplete** to end successfully; if no onNext preceded it, the source is **empty**.
- Call **onError(error)** to end with an error.
- Receive cancellation from a subscriber to stop emitting and release resources if supported.

**onSubscribe** only supplies the Subscription and the request(n) mechanism; it is **not** one of the three winning signals under `firstWithSignal`'s contract. Distinguish **Mono.empty()** (empty completion) from **Mono.just(value)** (has data) and **Mono.error(error)** (error).

With **cold** Publishers, work typically begins only when a subscriber subscribes. When running a race, Reactor arranges subscriptions to multiple sources to observe signals; a synchronous source can emit and win immediately, causing later sources not even to be subscribed to yet. Do not rely on argument order as a priority rule when sources emit concurrently. With **hot** sources, whether events were emitted before subscription or whether replay is enabled also affects the outcome.

~~~text
A: subscribe ── 100 ms ── onComplete (empty)
B: subscribe ── 300 ms ── onNext("B") ─ onComplete

firstWithSignal(A, B) → empty onComplete at 100 ms
firstWithValue(A, B)  → onNext("B") at 300 ms, then onComplete

C: subscribe ── 50 ms ── onError("offline")
D: subscribe ── 200 ms ── onNext("D") ─ onComplete

firstWithSignal(C, D) → onError("offline") at 50 ms
firstWithValue(C, D)  → onNext("D") at 200 ms, then onComplete
~~~

The timestamps only illustrate **order**; Scheduler, OS, network latency, CPU, and downstream demand can shift actual timings. Use virtual time for tests that need deterministic logic.

## 3. `firstWithSignal`: The Source Emitting Any Signal Earliest

The Javadoc specifies that **firstWithSignal** selects the first Publisher to emit **onNext, onError, or onComplete**, and then forwards all subsequent signals from that Publisher. It is a race for the **first observed outcome**, even if that outcome is empty or an error.

~~~java
Mono<String> fastestSignal = Mono.firstWithSignal(monoA, monoB);
Flux<String> fastestStreamSignal = Flux.firstWithSignal(fluxA, fluxB);
~~~

The variables monoA, monoB, fluxA, and fluxB here represent real application Publishers; this is an **API signature fragment**, not a standalone program.

Examples:
- A = Mono.empty() completes at 50 ms; B = Mono.just("OK") emits at 200 ms. `firstWithSignal` **completes empty at 50 ms**; B gets no chance to become the winner.
- A = Mono.error(new IllegalStateException("down")) errors at 50 ms; B emits "OK" after 200 ms. `firstWithSignal` **returns A's error**.
- A emits its first element at 80 ms then errors at 300 ms; B emits a value at 150 ms. A already won at 80 ms, so **A's later error is still forwarded**. It does not switch to B when A fails after winning.

**Strength:** selects the earliest response literally as “any outcome”. **Risk:** an early empty or erroring source can terminate the result even when another source has valid data. Therefore it is not the default choice for “get the earliest value”.

## 4. `firstWithValue`: The Source Emitting `onNext` Earliest

**firstWithValue** selects only the first Publisher to emit an **onNext value**. A source that completes empty or emits an error before emitting a value **does not win**; Reactor continues waiting for other sources that may still produce data.

~~~java
Mono<String> firstUseful = Mono.firstWithValue(monoA, monoB);
Flux<String> firstUsefulStream = Flux.firstWithValue(fluxA, fluxB);
~~~

Examples:
- A = Mono.empty() at 50 ms; B emits "OK" at 200 ms → `firstWithValue` emits **"OK"** at 200 ms.
- A = Mono.error("down") at 50 ms; B emits "OK" at 200 ms → `firstWithValue` still emits **"OK"**, not letting A's error win.
- A emits "A1" at 80 ms; B emits "B1" at 100 ms → A wins; if A is a Flux, the rest of A is forwarded downstream.

**Note on Flux:** once Flux A has won with an onNext, all subsequent onNext/onComplete/onError signals **from A** are forwarded. This operator is **not** zip, merge, or a function that takes a single element from every source. If you only want one element, consider **next()** or **take(1)** after selecting.

### 4.1. When all sources are empty or error

With **two or more sources**, if no source can provide a value, `firstWithValue` signals **NoSuchElementException**. The Javadoc describes this exception as having a **composite cause** containing one cause per source:

- If a source emitted a real error, the original cause is preserved at its corresponding index.
- If a source merely completed empty, a NoSuchElementException representing that empty source is recorded at that position.
- Use **reactor.core.Exceptions.unwrapMultiple(topLevel.getCause())** to retrieve the list of causes.

This differs from `firstWithSignal`: if an empty source finishes early, `firstWithSignal` completes empty; if an erroring source finishes early, `firstWithSignal` directly returns that winning error. With a single source, do not assume the “combined error from two sources” rule generalizes identically; verify the contract of the specific overload and source.

### 4.2. The `never` case

~~~java
Mono<String> result = Mono.firstWithValue(
    Mono.<String>never(),
    Mono.<String>empty());
~~~

The second source already ended empty, yet the first source **never emits or terminates**. `firstWithValue` can wait indefinitely because one source might still produce data. Set a time budget:

~~~java
Mono<String> bounded = Mono.firstWithValue(
        Mono.<String>never(),
        Mono.<String>empty())
    .timeout(Duration.ofSeconds(2));
~~~

Both snippets above are fragments requiring imports for reactor.core.publisher.Mono and java.time.Duration. Timeout can raise an error after 2 seconds if no result has arrived; it does not turn the result into a useful value by itself. If you want a fallback on timeout, design one separately as needed.

## 5. Comparison Table of Important Cases

| Case | `firstWithSignal` | `firstWithValue` |
| --- | --- | --- |
| A has a value before B | Selects A | Selects A |
| A completes empty before B has a value | Selects A: empty completion | B wins when it emits a value |
| A errors before B has a value | Selects A: returns A's error | B wins when it emits a value |
| A emits a value then later errors | A wins and A's later error is forwarded | A wins and A's later error is forwarded |
| Both A and B are empty | Completes empty per the faster source | NoSuchElementException with causes for both |
| A is empty, B errors, no values | Result matches whichever signal arrives first | NoSuchElementException with empty/error causes |
| Both A and B error before emitting a value | Whichever error arrives first wins | NoSuchElementException with composite cause |
| A = never, B has a value | B wins | B wins |
| A = never, B is only empty/error | B can win via completion/error | May wait forever: requires timeout |
| A and B emit almost simultaneously | Whichever signal Reactor observes first wins | Whichever onNext Reactor observes first wins |

**There is no guarantee the winner is the first argument passed.** When two sources emit close together, ordering can be affected by scheduling; if you want preference by geography, freshness, or reliability, design that criterion explicitly. “Fastest” does not mean “most accurate”.

## 6. Pick One `Mono` or Pick an Entire `Flux`?

### 6.1. `Mono`: a single record/result

~~~java
Mono<String> profile = Mono.firstWithValue(
    lookupFromRegionA(),
    lookupFromRegionB());
~~~

Here `lookupFromRegionA` and `lookupFromRegionB` are application-defined methods returning Mono<String>. When one region fails fast and the other returns a profile later, the region with the profile can win. Conversely, if neither region has data, the caller must handle the composite NoSuchElementException; do not blindly convert all errors into 404.

### 6.2. `Flux`: the winning source continues emitting until it finishes

~~~java
Flux<String> winner = Flux.firstWithValue(
    Flux.just("A-1", "A-2").delayElements(Duration.ofMillis(200)),
    Flux.just("B-1", "B-2").delayElements(Duration.ofMillis(80)));
~~~

If B emits B-1 first, the output is **B-1, B-2**, with no A-1/A-2. The Flux winner is chosen by the first onNext and **never switches sources again** if B later completes or fails. If you only want one element, use `winner.next()` to obtain a Mono<String>, taking the first element and cancelling the rest.

### 6.3. Cancellation and side-effect concerns

Once a winner is determined, already-subscribed competitors normally receive **cancel**; timers, I/O publishers, and streams supporting cancellation can stop. However, this **does not undo** work that already happened outside the process: an HTTP request may have already reached the server, a database transaction may have committed, or an email may have been sent.

**Only race read operations, idempotent operations, or operations with an explicit duplicate-write prevention strategy.** Never race two payment commands or database writes and assume the loser “never executed”. With hot sources, an event emitted before subscription can also be missed; evaluate cache/replay needs.

## 7. Distinguishing `firstWithValue` from Other Composition Operators

| API | Mechanism | When to use |
| --- | --- | --- |
| `firstWithSignal` | Races first onNext/onComplete/onError | Need the earliest response **regardless of outcome**. |
| `firstWithValue` | Races first onNext; ignores sources without data yet | Need useful data from at least one replica. |
| `switchIfEmpty` | Subscribes to fallback only when prior source is empty | Cache then database, reducing secondary query cost. |
| `onErrorResume` | Recovers from an error with another Publisher | Fallback when a known error type occurs. |
| `concat` / `concatWith` | Subscribes to sources sequentially | Need to preserve order and avoid running multiple sources at once. |
| `merge` / `mergeWith` | Emits values from **all** sources, possibly interleaved | Need to combine events from multiple sources. |
| `zip` / `zipWith` | Waits for corresponding values from **all** sources | Need both A and B to build a result. |
| `timeout` | Bounds waiting time | Prevent hanging forever on never / stalled networks. |

Given a cache and database with the same data type:

~~~java
Mono<Profile> sequential = cache.find(id)
    .switchIfEmpty(Mono.defer(() -> database.find(id)));

Mono<Profile> raced = Mono.firstWithValue(
    cache.find(id),
    database.find(id));
~~~

This is a **fragment**, assuming `cache.find(id)`, `database.find(id)`, and `Profile` are defined. **sequential** avoids calling the database on a cache hit. **raced** may subscribe to both to fetch data as fast as possible, at the cost of extra DB load and possibly picking an older version if cache/DB versions differ. If the primary source errors, `switchIfEmpty` itself does not catch errors; use conditional `onErrorResume` for error recovery.

**Do not use `firstWithValue` when you need data from both A and B.** For example, computing a total score requiring two sources should use Mono.zip(a, b) rather than cancelling one source based on a winner. And if you need data **meeting a condition**, filter/validate each source before racing:

~~~java
Mono<Profile> selected = Mono.firstWithValue(
    regionA.find(id).filter(this::isAcceptable),
    regionB.find(id).filter(this::isAcceptable));
~~~

The filter example is a service fragment with a synchronous, non-blocking `isAcceptable(Profile)` method. Unacceptable values are turned into empty and cannot win `firstWithValue`.

## 8. Complete Java 17+ and Maven Example

To see the difference between the two operators, run **Reactor Core 3.8.8** in a Java 17 command-line application. We create two source pairs: an early empty/error source and a later value source; finally we add a Flux case where the winner continues emitting subsequent elements.

### 8.1. Structure

~~~text
reactor-race/
├── pom.xml
├── src/main/java/com/example/race/RaceDemo.java
└── src/test/java/com/example/race/RaceTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-race</artifactId>
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

### 8.3. RaceDemo.java

**src/main/java/com/example/race/RaceDemo.java**

~~~java
package com.example.race;

import java.time.Duration;
import java.util.List;
import java.util.NoSuchElementException;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class RaceDemo {
    public static void main(String[] args) {
        // A is empty after ~20ms; B has a value after ~80ms.
        Mono<String> emptyEarly = Mono.<String>empty()
            .delaySubscription(Duration.ofMillis(20));
        Mono<String> valueLater = Mono.just("OK")
            .delayElement(Duration.ofMillis(80));

        String signal = Mono.firstWithSignal(emptyEarly, valueLater)
            .defaultIfEmpty("<empty>")
            .block();
        System.out.println("empty/signal=" + signal);

        String value = Mono.firstWithValue(emptyEarly, valueLater)
            .block();
        System.out.println("empty/value=" + value);

        // A errors early; B still produces data later.
        Mono<String> errorEarly = Mono.<String>error(
                new IllegalStateException("down"))
            .delaySubscription(Duration.ofMillis(20));
        Mono<String> healthy = Mono.just("healthy")
            .delayElement(Duration.ofMillis(80));

        String errorSignal = Mono.firstWithSignal(errorEarly, healthy)
            .onErrorResume(ex -> Mono.just(
                ex.getClass().getSimpleName() + ":" + ex.getMessage()))
            .block();
        System.out.println("error/signal=" + errorSignal);

        String valueDespiteError = Mono.firstWithValue(errorEarly, healthy)
            .block();
        System.out.println("error/value=" + valueDespiteError);

        // Winning Flux continues emitting all of its own elements.
        Flux<String> slow = Flux.just("slow-1", "slow-2")
            .delayElements(Duration.ofMillis(150));
        Flux<String> fast = Flux.just("fast-1", "fast-2")
            .delayElements(Duration.ofMillis(40));
        List<String> stream = Flux.firstWithValue(slow, fast)
            .collectList()
            .block();
        System.out.println("flux=" + stream);

        // All candidates fail to emit a value.
        Mono<String> noValue = Mono.firstWithValue(
            Mono.<String>empty(),
            Mono.<String>error(new IllegalArgumentException("failed")));
        try {
            noValue.block();
        } catch (NoSuchElementException ex) {
            int causeCount = Exceptions.unwrapMultiple(
                ex.getCause()).size();
            System.out.println("noValue=" +
                ex.getClass().getSimpleName() + ";causes=" + causeCount);
        }
    }
}
~~~

**Explanation:** `firstWithSignal` receives the empty onComplete first, so `defaultIfEmpty` is used to print the status label; `firstWithValue` ignores empty and chooses OK. With an early error, `firstWithSignal` preserves the error (`onErrorResume` is only for demoing how to print it), while `firstWithValue` waits for healthy. With Flux, `fast` emits fast-1 first and continues with fast-2; `slow`'s data is cancelled. When neither source yields a value, NoSuchElementException holds a composite cause for both sources.

**block() is used here only at the end of the CLI program** to await ordered stdout. In a WebFlux controller/service, never call block() on the event loop; return Mono/Flux for the framework to manage the subscription.

### 8.4. Running and Stdout

The machine needs JDK 17+, Maven, and access to download Maven Central dependencies.

~~~bash
java -version
mvn -version
mvn test
mvn -q exec:java -Dexec.mainClass=com.example.race.RaceDemo
~~~

**Stdout lines printed by main** (excluding Maven logs):

~~~text
empty/signal=<empty>
empty/value=OK
error/signal=IllegalStateException:down
error/value=healthy
flux=[fast-1, fast-2]
noValue=NoSuchElementException;causes=2
~~~

The values and ordering are designed using distinct delays. Actual emission schedules can still be affected by machine load; use **virtual time** testing to prove timing behavior deterministically.

## 9. Testing with `StepVerifier.withVirtualTime`

For race operators, the key test is **which signal arrives first**, not how many milliseconds the code took on a machine. **StepVerifier.withVirtualTime** installs a virtual-time scheduler before constructing the Publisher inside the lambda; `thenAwait` advances the clock instantaneously, while `expectNext`/`verifyComplete`/`expectError` assert the exact signals.

**src/test/java/com/example/race/RaceTest.java**

~~~java
package com.example.race;

import java.time.Duration;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

class RaceTest {

    @Test
    void emptyCompletionWinsFirstWithSignal() {
        StepVerifier.withVirtualTime(() -> Mono.firstWithSignal(
                Mono.<String>empty()
                    .delaySubscription(Duration.ofSeconds(1)),
                Mono.just("OK")
                    .delayElement(Duration.ofSeconds(3))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .verifyComplete();
    }

    @Test
    void firstWithValueWaitsForValueDespiteEarlyEmpty() {
        StepVerifier.withVirtualTime(() -> Mono.firstWithValue(
                Mono.<String>empty()
                    .delaySubscription(Duration.ofSeconds(1)),
                Mono.just("OK")
                    .delayElement(Duration.ofSeconds(3))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext("OK")
            .verifyComplete();
    }

    @Test
    void fastErrorWinsFirstWithSignal() {
        StepVerifier.withVirtualTime(() -> Mono.firstWithSignal(
                Mono.<String>error(new IllegalStateException("down"))
                    .delaySubscription(Duration.ofSeconds(1)),
                Mono.just("OK")
                    .delayElement(Duration.ofSeconds(3))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .expectErrorMatches(ex ->
                ex instanceof IllegalStateException &&
                "down".equals(ex.getMessage()))
            .verify();
    }

    @Test
    void firstWithValueCanIgnoreEarlyError() {
        StepVerifier.withVirtualTime(() -> Mono.firstWithValue(
                Mono.<String>error(new IllegalStateException("down"))
                    .delaySubscription(Duration.ofSeconds(1)),
                Mono.just("OK")
                    .delayElement(Duration.ofSeconds(3))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext("OK")
            .verifyComplete();
    }

    @Test
    void allSourcesWithoutValueProduceCompositeFailure() {
        StepVerifier.withVirtualTime(() -> Mono.firstWithValue(
                Mono.<String>empty()
                    .delaySubscription(Duration.ofSeconds(1)),
                Mono.<String>error(new IllegalStateException("down"))
                    .delaySubscription(Duration.ofSeconds(2))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectError(NoSuchElementException.class)
            .verify();
    }

    @Test
    void fluxWinnerEmitsAllItsValues() {
        StepVerifier.withVirtualTime(() -> Flux.firstWithValue(
                Flux.just("slow-1", "slow-2")
                    .delayElements(Duration.ofSeconds(3)),
                Flux.just("fast-1", "fast-2")
                    .delayElements(Duration.ofSeconds(1))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext("fast-1", "fast-2")
            .verifyComplete();
    }

    @Test
    void loserIsCancelled() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.withVirtualTime(() -> {
                Mono<String> slow = Mono.just("slow")
                    .delayElement(Duration.ofSeconds(5))
                    .doOnCancel(() -> cancelled.set(true));
                Mono<String> fast = Mono.just("fast")
                    .delayElement(Duration.ofSeconds(1));
                return Mono.firstWithValue(slow, fast);
            })
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("fast")
            .verifyComplete();

        assertTrue(cancelled.get());
    }
}
~~~

These are virtual-time unit tests, requiring no web server or waiting 3–5 real seconds. The first two tests prove the difference between signal and value on the **same inputs**. The next two tests confirm behavior with an early error. The Flux test preserves the entire winning sequence; the cancellation test checks that the already-subscribed losing source receives cancel.

**Test-writing rules:**
- Create the Mono/Flux **inside the `withVirtualTime` supplier**. If created outside and passed in, the real Scheduler may already be captured, preventing virtual time from controlling it.
- Call `expectSubscription` before `expectNoEvent` if used; subscription counts as an event.
- Use `thenAwait` to advance the clock; with infinite sources add `take(n)` or `thenCancel` instead of waiting for a `verifyComplete` that never arrives.
- Do not assert which source wins when both emit at **the exact same instant** and assume the first argument wins. Separate timestamps like 1s and 3s, or assert only business invariants on race ties.
- Cancellation only means the subscription was cancelled; do not assert that no request from the loser reached a remote server.

### 9.1. Inspecting a specific composite cause

Place the following fragment **inside a test method** (requiring the corresponding JUnit/StepVerifier imports):

~~~java
StepVerifier.create(Mono.firstWithValue(
        Mono.<String>empty(),
        Mono.<String>error(new IllegalStateException("db-down"))))
    .expectErrorSatisfies(ex -> {
        org.junit.jupiter.api.Assertions.assertTrue(
            ex instanceof NoSuchElementException);
        Throwable cause = ex.getCause();
        org.junit.jupiter.api.Assertions.assertNotNull(cause);

        java.util.List<Throwable> details =
            reactor.core.Exceptions.unwrapMultiple(cause);
        org.junit.jupiter.api.Assertions.assertEquals(2, details.size());
        org.junit.jupiter.api.Assertions.assertTrue(
            details.get(0) instanceof NoSuchElementException);
        org.junit.jupiter.api.Assertions.assertTrue(
            details.get(1) instanceof IllegalStateException);
    })
    .verify();
~~~

The cause list matches source order; record the region name associated with each index when debugging. **Do not expose the raw composite exception in an HTTP response** because it can leak backend names or stack traces. The boundary layer should classify domain errors and record appropriate metrics/logs.

## 10. Spring WebFlux Application Example: Reading Two Replicas

Suppose two HTTP endpoints return the same **Profile** type, and we want to read from whichever region **produces a value first**. You can use non-blocking WebClient and Mono.firstWithValue. If 404 means “no profile”, convert 404 to Mono.empty() on **each source**, before entering the race; WebClient.retrieve() converts 4xx/5xx into errors by default. If one region returns 500 while the other returns a profile, `firstWithValue` can select the profile.

The example below is a **controller fragment to integrate into Spring Boot WebFlux**, requiring a Spring Boot application, the `spring-boot-starter-webflux` dependency, a `WebClient.Builder` bean, and real environment URLs:

~~~java
package com.example.web;

import java.time.Duration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {
    public record Profile(String id, String displayName) {}

    private final WebClient east;
    private final WebClient west;

    public ProfileController(WebClient.Builder builder) {
        this.east = builder.clone()
            .baseUrl("https://east.example.internal").build();
        this.west = builder.clone()
            .baseUrl("https://west.example.internal").build();
    }

    private Mono<Profile> lookup(WebClient client, String id) {
        return client.get()
            .uri("/profiles/{id}", id)
            .exchangeToMono(response -> {
                if (response.statusCode().value() == 404) {
                    return Mono.empty();
                }
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(Profile.class);
                }
                return response.createError();
            })
            .timeout(Duration.ofSeconds(2));
    }

    @GetMapping("/{id}")
    public Mono<Profile> get(@PathVariable String id) {
        Mono<Profile> a = lookup(east, id);
        Mono<Profile> b = lookup(west, id);

        return Mono.firstWithValue(a, b)
            .timeout(Duration.ofSeconds(3));
    }
}
~~~

**Why use `exchangeToMono`?** We classify responses explicitly: HTTP 404 becomes Mono.empty(), 2xx decodes the body, and other errors become onError signals; this WebClient method manages body consumption/release around the callback. Do not mistakenly assume that `onStatus(..., response -> Mono.empty())` on `retrieve()` automatically turns the entire 404 response body into Mono.empty(); it only suppresses generating the corresponding exception.

**Design limits:**
- **Both replicas can be called.** Racing consumes up to two HTTP requests per user request; ensure proper connection pools, rate limits, and load budgets.
- **Cancelling the loser does not undo server-side requests.** Apply only to reads/idempotent calls to avoid duplicate writes.
- **The fastest source may hold stale data.** If consistency matters, check versions, timestamps, or an authoritative source. `firstWithValue` has no mechanism to pick the newest record.
- **If both return 404 or errors**, `firstWithValue` across two sources can raise NoSuchElementException with a composite cause, **not automatically returning 404**. Map 404/503/timeout based on policy and causes: two 404s differ from one 404 and one 500.
- **If one region is never/hung**, per-source timeouts and an overall deadline prevent waiting forever.
- **If the request is cancelled**, monitor I/O cancellation, per-region metrics, trace context, and connection leaks; never call subscribe manually in the controller.
- **Security:** enforce authentication, authorization, TLS, never log tokens/secrets, rate-limit queries, and propagate Reactor Context via framework mechanisms.

**Do not use `firstWithValue` if every read must return data from a single source of truth.** When strong consistency outweighs tail latency, choose an appropriate data architecture instead of racing by default.

## 11. Practical Scenarios for Choosing an Operator

### 11.1. Fast cache miss

Cache returns Mono.empty() at 10ms, DB returns profile at 90ms:
- **firstWithSignal(cache, db):** empty cache wins, client gets no profile.
- **firstWithValue(cache, db):** DB with a value wins, yet DB is typically called even when cache has data.
- **cache.switchIfEmpty(Mono.defer(dbQuery)):** hits DB only on cache miss, reducing load on cache hits. When cache hit rate is high and DB queries are expensive, this is usually the right design.

### 11.2. Fast error in one region

Region A has a network error after 20ms, region B returns profile at 120ms:
- **firstWithSignal:** returns A's error at 20ms.
- **firstWithValue:** B returns profile at 120ms.
- **onErrorResume:** can fail over from A to B **sequentially**; suitable if you only want to call B when A actually errors, avoiding 2 concurrent requests.

### 11.3. Stream wins then fails later

Flux A emits A1 at 10ms then onError at 100ms. Flux B emits B1 at 50ms then emits continuously:
- **firstWithValue:** A already won at A1, so downstream receives A1 then **A's onError**, without automatically switching to B.
- **firstWithSignal:** A also wins on A1's onNext.
- If you want to switch sources after A errors, define **staged recovery** (resume/switch) and handle duplicates, ordering, and replay; do not expect an initial race to do that.

### 11.4. Two sources return no data

A is empty, B errors, C emits nothing:
- **firstWithSignal:** an early onComplete/onError can win.
- **firstWithValue:** waits for C since no value has appeared yet; needs a timeout. When all three terminate with no value, the composite error holds each source's cause.

### 11.5. Need both A and B data

If a requirement **must have both the payment result and loyalty points**, never use a race because one source is discarded. Use `zip` when you need both; use `merge` when you need all events and accept interleaving; use `concat` when A must finish before B.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Treating `firstWithSignal` as getting the fastest value | Early empty/error can win | Use `firstWithValue` when you need the first onNext. |
| Treating `Mono.empty()` as null | Misunderstands signals and fallbacks | Empty is onComplete with no onNext; never use Mono.just(null). |
| Assuming `firstWithValue` always succeeds | When no source yields a value, NoSuchElementException occurs | Inspect composite cause and map errors per domain rules. |
| Thinking `firstWithValue` takes only one element from a Flux | Overlooks later elements from the winner | Winner keeps emitting its full sequence; use `next()` for 1 element. |
| Assuming if the winner later errors it switches to the loser | Pipeline ends with the winner's error | Design explicit `onErrorResume`/failover separately. |
| Assuming cancelling the loser means its request never ran | May already have committed or sent email | Race only reads/idempotent work; handle side effects safely. |
| Racing DB and cache when only sequential fallback is needed | Increases DB request volume | Use `switchIfEmpty` for sequential fallback when appropriate. |
| Omitting a timeout | `firstWithValue` can wait forever on Mono.never | Set an overall request deadline and per-source timeouts. |
| Returning 404 on every NoSuchElementException | Hides unavailable-region errors | Classify composite causes: 404 differs from 503. |
| Testing with sleep and predicting ties | Flaky tests depending on CPU/scheduler | Use virtual time with distinct timestamps; do not assert ties. |
| Using a race instead of `zip` | Missing half the data needed to aggregate | If both are required, use `zip` instead of picking one winner. |
| Trusting the fastest source is the freshest version | Returns stale data | Check consistency, versions, and freshness rules. |

## 13. Exercises with Suggested Answers

**Exercise 1: Comparing signal vs. value.** A completes empty after 1s; B returns "OK" after 3s. Write two StepVerifier.withVirtualTime tests: `firstWithSignal` completes empty at 1s; `firstWithValue` returns OK at 3s. **Hint:** `delaySubscription` on `Mono.empty` and `delayElement` on `Mono.just`.

**Exercise 2: Fast-failing source.** A fails with IllegalStateException at 500ms, B returns "OK" at 2s. Predict `firstWithSignal` returns A's error, `firstWithValue` returns OK. Use `expectErrorMatches` to verify the original error; do not use `onErrorResume` in the test if the goal is proving the error.

**Exercise 3: Composite error.** A is empty, B fails with IllegalArgumentException. Use `StepVerifier.expectErrorSatisfies` to verify `NoSuchElementException` and `Exceptions.unwrapMultiple(...).size() = 2`. Explain why HTTP 404 cannot be returned in both cases if one region actually failed with 500.

**Exercise 4: Flux winner.** A emits A1/A2 every 3s; B emits B1/B2 every 1s. Expected output is B1, B2 then complete. Test with virtual time and use `doOnCancel` to confirm A is cancelled.

**Exercise 5: Choosing a fallback model.** 95% cache hit rate, expensive DB: should you use sequential `switchIfEmpty` or a `firstWithValue` race? Account for tail latency, DB traffic, data freshness, and pool capacity; justify the choice rather than picking by operator name alone.

## 14. Pre-Deployment Checklist

- [ ] Clearly state whether the requirement is **first signal** or **first value**.
- [ ] Have tests for A empty first, A erroring first, A emitting data first, and all sources producing no value.
- [ ] For Flux, understand the winner keeps emitting the rest of its stream; losers are cancelled if subscribed.
- [ ] Bound max competitors, timeouts, limited retries, and connection budgets.
- [ ] Never race non-idempotent writes; cancellation does not undo side effects.
- [ ] Classify composite NoSuchElementException and standardize HTTP error codes.
- [ ] Use VirtualTimeScheduler/StepVerifier for timed races; never assume tie-breaking behavior.
- [ ] Compare against `switchIfEmpty`/`onErrorResume`/`zip`/`merge`/`concat` before choosing a race.
- [ ] Define consistency/freshness requirements when reading from multiple replicas.
- [ ] In WebFlux, return Mono/Flux to the framework; never call `block` or ad-hoc `subscribe` on the request path.

## 15. References

1. Reactor Core Mono Javadoc – firstWithSignal, firstWithValue: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
2. Reactor Core Flux Javadoc – firstWithSignal, firstWithValue: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
3. Reactor Core Exceptions Javadoc – unwrapMultiple: https://projectreactor.io/docs/core/release/api/reactor/core/Exceptions.html
4. Reactor Test StepVerifier – withVirtualTime and signal assertions: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
5. Project Reactor Reference Guide – errors, cancellation, testing: https://projectreactor.io/docs/core/release/reference/
6. Spring Framework WebFlux – Publishers and WebClient: https://docs.spring.io/spring-framework/reference/web/webflux.html

**Self-assessment:** If you can explain why a `Mono.empty()` can win `firstWithSignal` yet cannot win `firstWithValue`, why `firstWithValue` produces a composite error when all sources lack a value, and why a winning `Flux` continues emitting subsequent elements, you have mastered these two core race operators.
