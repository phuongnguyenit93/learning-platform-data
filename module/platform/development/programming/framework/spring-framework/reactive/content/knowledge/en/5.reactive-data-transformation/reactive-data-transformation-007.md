# handle for Conditional Emission Logic in Project Reactor

## 1. When Is \`handle\` Needed?

When processing reactive data, sometimes an input element needs to be **transformed if a condition holds**, **skipped if invalid**, or **terminate the stream if a special business signal is encountered**. A \`filter(...).map(...)\` chain covers many cases, but sometimes filtering and result computation share a single calculation, or a conversion function can return \`null\`, or an error needs to be emitted in a specific branch.

In Project Reactor, the **\`handle\`** operator provides a \`SynchronousSink\` for **each element emitted by the upstream source**. The callback decides whether to emit a resulting element:

- Call \`sink.next(output)\` **at most once** per callback invocation to emit a result.
- Do not call \`sink.next\` if you want to **skip the input element**.
- Call \`sink.error(exception)\` when you want to **terminate with an error**.
- Call \`sink.complete()\` when you want to **complete normally right here**.

This operator exists on both **\`Flux\` and \`Mono\`**. With \`Flux\`, the number of output elements can be smaller than the number of input elements; with \`Mono\`, the result is still **0 or 1 element**. \`handle\` does not create a standalone data stream from scratch and is not an asynchronous emission API for callbacks running later.

Core example:

~~~java
Flux<Integer> positive =
        Flux.just(-3, 2, 0, 5)
            .<Integer>handle((number, sink) -> {
                if (number > 0) {
                    sink.next(number * 10);
                }
            });
// When subscribed: emits 20, 50 then completes.
~~~

This snippet illustrates an expression inside a Java method with \`reactor.core.publisher.Flux\` imported, not a standalone class. Negative elements and \`0\` produce no output \`onNext\` signal because the callback does not call \`sink.next\`.

## 2. Position of \`handle\` in the Pipeline

~~~text
Flux<T> upstream
    |
    | onNext(input)
    v
handle((input, sink) -> ...)
    |
    +-- sink.next(result) --> downstream receives onNext(result)
    |
    +-- no next() ----------> skips input, awaits next input
    |
    +-- sink.error(err) ----> downstream receives onError(err), terminates
    |
    +-- sink.complete() ----> downstream receives onComplete(), terminates
~~~

When the upstream source completes normally after emitting all data, downstream also completes even if the \`handle\` callback does not call \`complete()\`. \`handle\` is only invoked for **upstream \`onNext\` elements**: if upstream is \`Flux.empty()\`, \`Mono.empty()\`, or errors before emitting any element, the \`handle\` callback is not called to generate data on its own.

Conceptual signatures:

~~~java
// Project Reactor Flux<T>:
<R> Flux<R> handle(BiConsumer<? super T, SynchronousSink<R>> handler);

// Project Reactor Mono<T>:
<R> Mono<R> handle(BiConsumer<? super T, SynchronousSink<R>> handler);
~~~

The \`BiConsumer\` receives two arguments: **the input \`T\`** and **the sink for result \`R\`**. If type inference cannot clearly deduce the output type, declare it explicitly with \`.<Integer>handle(...)\` or \`.<String>handle(...)\`.

The \`SynchronousSink\` specification allows **at most one \`next\` and at most one terminal signal** (\`complete\` or \`error\`) per invocation. You may call \`next\` followed by \`complete\` to emit the final element and terminate, but **do not call \`next\` multiple times**, and do not emit both \`complete\` and \`error\`. A simple, readable pattern is to choose **one clear branch** and \`return\` after a terminal signal.

## 3. Outcome of Each Handling Branch

| Inside \`handle\` callback | Output signal | Meaning |
| --- | --- | --- |
| \`sink.next(value)\` | Emits one non-null \`value\` element | Transforms or keeps the input |
| No emission method called | No \`onNext\` for this input | Filters out the element |
| \`sink.error(e)\` | Emits \`onError(e)\` and terminates the stream | Data is invalid to the point where processing must stop |
| \`sink.complete()\` | Emits \`onComplete()\` and terminates the stream | Early-stop condition reached |
| \`sink.next(v)\` then \`sink.complete()\` | Emits the final element and completes | Allowed, while obeying signal limits |

**Never call \`sink.next(null)\`.** Reactive Streams/Reactor does not allow \`null\` as an \`onNext\` element; if data does not exist, omit \`next\` or represent optional state with another object (such as \`Optional\`, if the problem requires it).

**Do not use \`sink.error\` to discard a bad record and keep processing the next element.** \`error\` is a terminal event for that subscription. If the goal is “skip bad records while still processing later records”, do not call \`next\` for bad records; if the goal is “fail fast”, call \`error\`.

## 4. How \`handle\` Differs from \`map\`, \`filter\`, \`flatMap\`, and \`generate\`

| Operator | Elements emitted per input | How it works | When to choose |
| --- | --- | --- | --- |
| \`map\` | Exactly one valid element | Computes \`R\` from \`T\` | Pure transformation that always produces a non-null value |
| \`filter\` | 0 or 1, keeps type \`T\` | Evaluates predicate and keeps/drops input | Only a condition is needed and type does not change |
| \`filter(...).map(...)\` | 0 or 1 | Filters then transforms across two operators | Clearer when the condition is separate from the transformation |
| **\`handle\`** | **0 or 1** | Synchronous callback decides to emit, skip, error, or stop | Filtering and mapping in one step; using a conversion result once; branching rules |
| \`flatMap\` | Can be 0, 1, or many | Each input becomes an inner Publisher | Asynchronous work or one input producing multiple outputs |
| \`concatMap\` | Can be 0, 1, or many | Subscribes to inner Publishers in order | Need to preserve order while processing inner Publishers |
| \`Flux.generate\` | At most one \`next\` per generation turn | Creates a sequence from a generator, no upstream Flux needed | Generating data step-by-step from state/generator |
| \`Flux.create\` / \`Mono.create\` | Depends on sink and API | Bridges arbitrary callback sources, possibly async | Integrating external callback/event APIs |

Easy-to-remember trait: **\`handle\` is a single-input transformation that may yield no output**. \`generate\` is a way to **create a source** (source generator); \`handle\` is a way to **process an existing stream**.

If you only need \`filter(n -> n > 0).map(n -> n * 10)\`, the two familiar operators are usually clearer than \`handle\`. The benefit of \`handle\` stands out when the condition needs information from the conversion result—for example, a parse method returning \`null\` or avoiding parsing the same string twice.

## 5. Scenario 1 — Parsing Data and Skipping Invalid Values

Suppose we receive multiple input strings and only want to emit **positive integers**. We need to handle non-numeric strings, \`0\`, negative numbers, and continue processing the remaining strings.

~~~java
Flux<Integer> parsed = Flux.just(" 12 ", "bad", "3", "0", "-5", " 7 ")
    .<Integer>handle((raw, sink) -> {
        try {
            int number = Integer.parseInt(raw.trim());
            if (number > 0) {
                sink.next(number);
            }
        } catch (NumberFormatException ignored) {
            // Policy for this example: skip unparseable records.
        }
    });

// When subscribed: 12, 3, 7.
~~~

This is a good fit for \`handle\` because **converting the string to a number** and **checking positivity** are coupled; parsing happens only once. In real applications, the decision to skip invalid inputs must follow business requirements; count dropped records or log errors at an appropriate level. Do not silently drop important data by default.

If you only want conditional decoding from a method returning \`null\`, you can do:

~~~java
String parsedOrNull = legacyLookup(input);
if (parsedOrNull != null) {
    sink.next(parsedOrNull);
}
~~~

This callback snippet is **illustrative code**, assuming \`input\`, \`sink\`, and \`legacyLookup\` exist. You must not write \`map(this::legacyLookup)\` if the function can return \`null\`, because \`map\` does not accept emitted \`null\` values. In Reactor versions supporting \`mapNotNull\`, that operator is also a concise option specifically for “map then drop null results”; \`handle\` is useful when logic has more branches.

## 6. Scenario 2 — Distinguishing “Skip” from “Error”

For the same malformed string, there are at least two **business policies**:

**Lenient policy:** skip the invalid input and continue reading other inputs.

~~~java
Flux<Integer> tolerant = Flux.just("1", "oops", "2")
    .<Integer>handle((text, sink) -> {
        try {
            sink.next(Integer.parseInt(text));
        } catch (NumberFormatException ignored) {
            // Emit no output for "oops".
        }
    });
// Output: 1, 2, then complete.
~~~

**Strict policy:** halt the entire stream on an invalid input.

~~~java
Flux<Integer> strict = Flux.just("1", "oops", "2")
    .<Integer>handle((text, sink) -> {
        try {
            sink.next(Integer.parseInt(text));
        } catch (NumberFormatException error) {
            sink.error(new IllegalArgumentException(
                    "Invalid number: " + text, error));
        }
    });
// Output: 1, then onError(IllegalArgumentException).
// "2" is not processed further by this subscription.
~~~

Both snippets above are expressions inside a Java method with \`Flux\` imported. Both are syntactically valid, yet carry **different business semantics**. If downstream places \`onErrorResume\`, it can replace the stream with a fallback **after the error**, but do not assume that restores processing of source elements interrupted after the error; the source has already terminated/canceled under terminal semantics.

Example:

~~~java
List<Integer> values = strict
        .onErrorResume(IllegalArgumentException.class, e -> Flux.just(-1))
        .collectList()
        .block();
// With the strict source above: [1, -1].
// Input "2" is not automatically processed again.
~~~

## 7. Scenario 3 — Stopping Early Based on Data Content

When a stream contains a sentinel value marking the stopping point, \`sink.complete()\` can terminate without waiting for upstream to finish emitting:

~~~java
Flux<Integer> untilStop = Flux.just(10, 20, -1, 30)
    .<Integer>handle((number, sink) -> {
        if (number == -1) {
            sink.complete();
            return;
        }
        sink.next(number);
    });
// Output: 10, 20, then complete.
// 30 is not delivered to the handler in this subscription.
~~~

\`sink.complete()\` is a terminal signal for **the entire downstream subscription**, not “skip input -1 and wait for the next input”. If you only want to skip the marker value while still processing 30, do not call \`complete()\`:

~~~java
Flux<Integer> withoutMarker = Flux.just(10, 20, -1, 30)
    .<Integer>handle((number, sink) -> {
        if (number != -1) {
            sink.next(number);
        }
    });
// Output: 10, 20, 30, then complete.
~~~

You can emit the final element and then complete in the same callback when the problem requires it. For example, “read up to and including 3”:

~~~java
Flux<Integer> throughThree = Flux.range(1, 5)
    .<Integer>handle((n, sink) -> {
        sink.next(n);
        if (n == 3) {
            sink.complete();
        }
    });
// Output: 1, 2, 3, then complete.
~~~

All three examples are standalone operator-level expression snippets, not complete Java programs. In practice, sources with side effects or prefetch/buffer read-ahead may perform some upstream work before cancellation propagates; \`complete\` is not a promise that “zero upstream bytes/tasks were processed beforehand”.

## 8. Scenario 4 — \`Mono.handle\` for Present or Absent Results

A \`Mono<T>\` emits at most one successful element. \`Mono.handle\` can convert that element to type \`R\`, or **emit nothing** if the condition is not met.

~~~java
Mono<String> source = Mono.just("  hello ");
Mono<String> normalized = source.<String>handle((raw, sink) -> {
    String value = raw.trim();
    if (!value.isBlank()) {
        sink.next(value.toUpperCase());
    }
});
// normalized: Mono emitting "HELLO".
~~~

If the input is a whitespace-only string, \`handle\` does not call \`next\`, so the result is **\`Mono.empty()\` in terms of signals**:

~~~java
Mono<String> empty = Mono.just("   ")
    .<String>handle((raw, sink) -> {
        String value = raw.trim();
        if (!value.isEmpty()) {
            sink.next(value);
        }
    });

Boolean hasValue = empty.hasElement().block(); // false
~~~

If **upstream is already empty**, e.g. \`Mono.<String>empty().handle(...)\`, the callback is not invoked either. \`handle\` does not automatically turn a \`Mono.empty()\` into a default value; for that situation, use \`defaultIfEmpty\`, \`switchIfEmpty\`, or \`onErrorResume\` depending on signal type and requirements.

Example with explicit business semantics:

~~~java
Mono<String> answer = Mono.just(" ")
    .<String>handle((raw, sink) -> {
        String trimmed = raw.trim();
        if (!trimmed.isEmpty()) sink.next(trimmed);
    })
    .defaultIfEmpty("UNKNOWN");
// When subscribed, answer emits "UNKNOWN".
~~~

Use \`handle\` when “a value is present yet invalid” can be modeled as “no result”. If invalidity must be an **error**, emit \`sink.error\` rather than skipping.

## 9. Complete Java 17+ Program with Verifiable Output

The following program brings these scenarios together into a compilable, runnable example. It demonstrates:

1. Conditional emission with \`Flux.handle\`.
2. \`Mono.handle\` returning 1 or 0 elements.
3. \`sink.error\` terminating the stream and \`onErrorResume\` replacing the error with a fallback.
4. \`sink.complete\` stopping the stream at a sentinel element.

Requirements: **JDK 17+** and **Maven 3.9+**. Create the layout:

~~~text
reactor-handle-demo/
├── pom.xml
└── src/main/java/example/HandleDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-handle-demo</artifactId>
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

**src/main/java/example/HandleDemo.java**

~~~java
package example;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class HandleDemo {
    public static void main(String[] args) {
        Flux<Integer> accepted = Flux.just(
                " 12 ", "skip", "3", "0", "-5", " 7 ")
            .<Integer>handle((raw, sink) -> {
                try {
                    int number = Integer.parseInt(raw.trim());
                    if (number > 0) {
                        sink.next(number);
                    }
                } catch (NumberFormatException ignored) {
                    // Demo: invalid strings are skipped.
                }
            });

        System.out.println("accepted=" + accepted.collectList().block());

        Mono<Integer> one = Mono.just(" 42 ")
            .<Integer>handle((raw, sink) ->
                    sink.next(Integer.parseInt(raw.trim())));

        Mono<String> none = Mono.just("  ")
            .<String>handle((raw, sink) -> {
                if (!raw.isBlank()) {
                    sink.next(raw.trim());
                }
            });

        System.out.println("one=" + one.block());
        System.out.println("none.hasValue=" + none.hasElement().block());

        Flux<Integer> strict = Flux.just("2", "bad", "4")
            .<Integer>handle((raw, sink) -> {
                try {
                    sink.next(Integer.parseInt(raw));
                } catch (NumberFormatException cause) {
                    sink.error(new IllegalArgumentException(
                            "bad number: " + raw, cause));
                }
            });

        System.out.println("strictRecovered=" +
                strict.onErrorResume(IllegalArgumentException.class,
                        error -> Flux.just(-1))
                      .collectList().block());

        Flux<Integer> untilMarker = Flux.range(1, 5)
            .<Integer>handle((number, sink) -> {
                if (number == 4) {
                    sink.complete();
                    return;
                }
                sink.next(number);
            });

        System.out.println("untilMarker=" +
                untilMarker.collectList().block());
    }
}
~~~

From the \`reactor-handle-demo\` directory, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.HandleDemo
~~~

**Lines printed by the program:**

~~~text
accepted=[12, 3, 7]
one=42
none.hasValue=false
strictRecovered=[2, -1]
untilMarker=[1, 2, 3]
~~~

Line-by-line explanation:

- \`accepted\`: \`skip\` fails to parse, \`0\` and \`-5\` are not positive, so only \`12, 3, 7\` are emitted.
- \`one\`: \`Mono.handle\` converts \`" 42 "\` to the number \`42\`.
- \`none.hasValue\`: because the whitespace-only input does not call \`next\`, \`Mono\` completes empty.
- \`strictRecovered\`: emits \`2\`, hits \`bad\` and emits an error; \`onErrorResume\` replaces the error with \`-1\`. The trailing string \`"4"\` **is not automatically emitted afterward**.
- \`untilMarker\`: when the input is \`4\`, the callback calls \`complete\`; \`5\` never becomes output.

The \`block()\` calls in the example exist only at **the console program boundary** to collect results for easy observation. In WebFlux or on an event loop, you normally **return the Publisher for the framework to process**, avoiding \`block()\` in the request flow.

## 10. Synchronous Constraint of \`SynchronousSink\`

The name **SynchronousSink** is a real constraint. You must call \`next\`, \`error\`, or \`complete\` **while the \`handle\` callback is executing**. Do not store \`sink\` in a global variable, queue, or callback that will be triggered later:

~~~java
// WRONG under the SynchronousSink contract:
Flux<String> invalid = Flux.just("a")
    .<String>handle((value, sink) -> {
        someAsyncClient.fetch(value, result -> {
            sink.next(result); // Callback runs after handle has already returned.
        });
    });
~~~

This is only an **anti-pattern illustrative snippet**: \`someAsyncClient\` is undeclared and it is not runnable source. The mistake is using \`sink\` asynchronously, even though the callback syntax may look plausible. \`SynchronousSink\` is not designed to be stored and emitted from a later arriving event.

If the work returns **\`Mono<R>\` or \`Flux<R>\`**, choose an operator that handles inner Publishers:

~~~java
Flux<Result> results = requests.flatMap(
        request -> asyncService.fetch(request)
);
~~~

This is also an **illustrative** snippet, assuming \`requests\` is \`Flux<Request>\` and \`asyncService.fetch(request)\` returns \`Mono<Result>\`. \`flatMap\` can run multiple inner publishers concurrently and does not guarantee output order matching input order. If you need order preservation under a specific policy, see \`concatMap\` or \`flatMapSequential\`.

If you need to **adapt a callback API into a reactive source**, see \`Mono.create\`, \`Flux.create\`, the \`Sinks\` APIs, and appropriate cancellation/backpressure policies. Once you have a valid \`Mono\`/\`Flux\`, use \`flatMap\`/\`concatMap\` to compose it into the stream. Do not use \`handle\` as an “asynchronous event-emitting gateway” because its contract is synchronous.

## 11. Does \`handle\` Create Threads, Non-Blocking Behavior, or New Backpressure?

**No.** \`handle\` is a signal-processing operator on an existing Publisher. The callback normally runs on the thread delivering \`onNext\` through the pipeline, unless other operators change the execution context (such as \`publishOn\`).

~~~java
Flux<String> source = Flux.just("a", "b")
    .<String>handle((value, sink) -> {
        // This is synchronous processing on the thread used by the pipeline.
        sink.next(value.toUpperCase());
    });
~~~

If the callback calls \`Thread.sleep\`, synchronous JDBC, or a blocking HTTP client, it still **blocks the current thread**. In a WebFlux application, blocking on a Netty event loop can slow down other requests. Do not add \`handle\` expecting it to handle threading issues automatically; choose a genuinely non-blocking API or isolate blocking work on an appropriate scheduler such as \`boundedElastic\` when legacy systems are unavoidable.

**Backpressure** still follows the Reactive Streams contract. \`handle\` may drop some inputs, so downstream asking for \`N\` results may cause upstream to process more than \`N\` input elements. Do not assume downstream \`request(1)\` always corresponds to exactly one upstream \`onNext\`; operators, fusion, prefetching, sources, and cancellation all influence execution details.

In particular, \`handle\` is not a holistic memory-throttling mechanism. If upstream is faster than processing capacity, examine the entire source, buffers, downstream speed, and resource management policies. Dropping an input element does not guarantee upstream had no earlier side effects.

## 12. Error, Completion, and Cancellation Semantics

A pipeline can end in three ways:

| Situation | Sent downstream | Are subsequent inputs still processed? |
| --- | --- | --- |
| Callback does not call \`next\` | No onNext for this input | **Yes**, if upstream keeps emitting |
| Callback calls \`error\` | Terminal onError | **No**, on this subscription |
| Callback calls \`complete\` | Terminal onComplete | **No**, on this subscription |
| Upstream completes on its own | Terminal onComplete once pending signals finish | No |
| Downstream cancels | Subscription is canceled | No longer allowed to emit on this subscription; stopping upstream resources depends on implementation |

In a business branch, use \`sink.error\` when you **genuinely want to terminate the stream with an error**. If you simply need to continue without emitting data, let the callback finish normally without calling \`next\`.

When the callback throws a \`RuntimeException\`, Reactor can propagate it as \`onError\`; use \`onErrorResume\` or \`onErrorMap\` downstream when needed. Handle errors explicitly per application policy. **Avoid using \`onErrorContinue\` as the default way to rescue an entire stream**, because behavior depends on operators and can make error semantics, dropped elements, and handling scope hard to predict.

\`handle\` can carry side effects such as logging, incrementing metrics, or calling services. If the pipeline is **retried/resubscribed**, the callback may run again for inputs re-emitted by the source. Side effects must be designed accordingly; \`handle\` provides no “run exactly once” guarantee across multiple subscriptions.

## 13. Using \`handle\` in Spring WebFlux

In WebFlux, a controller can return a \`Flux<R>\` filtered/transformed with \`handle\`; the framework takes responsibility for subscribing and turning data into an HTTP response.

Controller example, assuming a Spring Boot WebFlux application with appropriate dependencies:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class NumberController {

    @GetMapping("/positive-numbers")
    public Flux<Integer> positiveNumbers() {
        return Flux.just("10", "bad", "-1", "4")
            .<Integer>handle((raw, sink) -> {
                try {
                    int value = Integer.parseInt(raw);
                    if (value > 0) {
                        sink.next(value);
                    }
                } catch (NumberFormatException ignored) {
                    // Example: drop malformed input.
                }
            });
    }
}
~~~

The snippet above is a complete Java controller, yet **must be placed inside a Spring Boot WebFlux project with server configuration/entry point**; it cannot be run standalone with \`java NumberController\`. Accessing the endpoint with default HTTP JSON produces \`[10,4]\`.

Distinguish **“omitting elements”** from **“rejecting an HTTP request”**. If the user payload is invalid and the API contract requires a 400 error, do not silently drop all data with \`handle\`. When a request must be rejected, use validation and proper error mapping (such as \`ResponseStatusException\`, \`@Valid\`, or WebFlux error handling) to avoid misleading the client into thinking input was fully accepted.

For very large datasets or streaming, check media types, response writing behavior, cancellation, and the correctness of dropping data. \`handle\` only processes elements once the Publisher is subscribed; it does not replace network/server resource controls.

## 14. Safe Usage Pattern: One Callback, One Decision

A readable \`handle\` callback usually follows this order:

~~~java
Flux<Output> result = source.<Output>handle((input, sink) -> {
    // 1. Check condition that must stop the entire stream.
    if (shouldStop(input)) {
        sink.complete();
        return;
    }

    // 2. Check cases where the input does not need to be emitted.
    if (shouldSkip(input)) {
        return;
    }

    // 3. Compute output (may throw if policy requires).
    Output output = transform(input);

    // 4. Decide whether to emit or skip the output.
    if (output != null) {
        sink.next(output);
    }
});
~~~

This is **typed Java pseudocode**, not a standalone program; \`source\`, \`Output\`, \`shouldStop\`, \`shouldSkip\`, and \`transform\` must be defined by the application. Not every callback needs all four steps. The goal is for reviewers to clearly see **the skip branch**, **the error/stop branch**, and **the emission branch**.

For validation errors, you can emit:

~~~java
if (isInvalid(input)) {
    sink.error(new IllegalArgumentException("invalid input"));
    return;
}
~~~

If the output is an **asynchronous Publisher**, use \`flatMap\`:

~~~java
Flux<Output> result = source.flatMap(input -> transformAsync(input));
~~~

If only a simple keep/drop condition is needed, use \`filter\`:

~~~java
Flux<Integer> result = Flux.range(1, 10).filter(n -> n % 2 == 0);
~~~

If every element simply needs to be transformed into a valid value, use \`map\`:

~~~java
Flux<Integer> result = Flux.range(1, 10).map(n -> n * 2);
~~~

The last three illustrations must live inside a Java method or class declaring the corresponding source/functions.

## 15. Common Mistakes and How to Spot Them

| Mistake | Symptom / consequence | Proper understanding |
| --- | --- | --- |
| Calling \`sink.next\` multiple times in one callback | Violates SynchronousSink contract; may error at runtime | At most one \`next\` per input; for one input → many outputs, use \`flatMap\` or an appropriate operator |
| Calling \`sink.next(null)\` | No valid null element exists in Reactor | Omit \`next\` or convert null to a valid value |
| Not calling \`next\` yet expecting the element to pass through | Output is lost for that input | \`handle\` **does not auto-forward** inputs; you must call \`sink.next(input)\` |
| Saving \`SynchronousSink\` to call from an async callback | Violates the synchronous boundary of the sink | Use Mono.create/Flux.create/Sinks and compose with flatMap |
| Using \`sink.error\` to “skip” a bad record | Stream terminates; subsequent elements are not processed | To continue, omit calling \`next\` |
| Using \`sink.complete\` to “skip one element” | Entire stream ends early | Skip only by not emitting data |
| Assuming \`handle\` automatically makes blocking code safe | Signal-processing thread is still blocked | Use non-blocking APIs or run blocking work on an appropriate scheduler |
| Calling \`block()\` inside \`handle\` to wait for another Mono | Can block event loops, cause deadlocks, or throw in non-blocking threads | Use \`flatMap\` to compose Publishers |
| Failing to distinguish nullable results from business errors | May silently drop data or cause unexpected errors | Explicitly design skip/error/default policies |
| Asserting fixed thread ordering | Breaks when pipelines involve schedulers or async sources | Rely on operator contracts; use \`publishOn\`/\`subscribeOn\` when needed |

An advanced topic is **discard**: when an element is dropped in a pipeline, resources held by that element (if any) still need proper management according to the data type. For objects with special lifecycles like reference-counted buffers, do not assume “not calling next” automatically closes every resource. Check the source's contract, supported discard hooks, and the library's resource release rules.

## 16. Tips for Testing Important Branches

For a \`handle\` with multiple branches, test each separately:

1. **Valid input**: emits exact expected values and order.
2. **Skipped input**: emits no element, yet the subscription still processes subsequent inputs.
3. **Errored input**: emits the expected error type and stops emitting further elements.
4. **Complete condition**: terminates at the desired position.
5. **Empty source**: callback is not invoked; downstream receives complete.
6. **Mono.handle**: output is only 0 or 1 element.
7. **Cancellation / backpressure**: if the source has side effects or resources, verify cancellation behavior and load limits with appropriate integration tests.

In Reactor applications, the **reactor-test** library provides \`StepVerifier\` to describe expected signals:

~~~java
StepVerifier.create(
        Flux.just(-2, 3, 0, 5)
            .<Integer>handle((n, sink) -> {
                if (n > 0) sink.next(n * 2);
            })
)
    .expectNext(6, 10)
    .verifyComplete();
~~~

This is an illustrative test snippet requiring \`io.projectreactor:reactor-test\` matching \`reactor-core\`, importing \`reactor.test.StepVerifier\`, and running inside an appropriate test method. It verifies **values and the complete signal**, not merely the result of \`collectList\`.

## 17. Self-Check Knowledge Quiz

**Question 1.** \`Flux.just("1", "bad", "2")\` passes through \`handle\` which only calls \`next\` for parseable strings. What is the result?

Emits \`1\`, \`2\`, then completes. Input \`bad\` is skipped **if the callback catches NumberFormatException and does not emit an error**.

**Question 2.** If the \`handle\` callback does not call any method on sink, does the input continue downstream?

No. \`handle\` does not auto-forward the input downstream; that input is skipped. The callback continues to be invoked for subsequent inputs as long as the source emits and the subscription stays active.

**Question 3.** What is the difference between \`sink.complete()\` and not calling \`sink.next\`?

Not calling \`next\` skips only **one input**. Calling \`complete\` terminates **the entire stream** on that subscription.

**Question 4.** Can you call \`sink.next(a)\` and \`sink.next(b)\` for the same input to emit two results?

No. \`SynchronousSink\` allows at most one \`next\` per callback invocation. If one input produces multiple elements, map it to a \`Flux\` via \`flatMap\`/\`concatMap\` or build an appropriate source.

**Question 5.** Can \`handle\` be used to emit after receiving an HTTP response from an async callback?

Not safely. \`SynchronousSink\` must be used within the current callback. Use a reactive API or bridge the callback to Mono/Flux and compose via \`flatMap\`.

**Question 6.** Is \`Mono.handle\` invoked for \`Mono.empty()\`?

No. There is no upstream \`onNext\`, so the callback is not called; downstream receives an empty completion.

**Question 7.** When is \`filter().map()\` easier to read than \`handle\`?

When the keep/drop condition and transformation are cleanly separable without sharing computation or controlling terminal signals. Choose the simplest operator that clearly expresses intent.

**Question 8.** If a \`handle\` callback executes blocking JDBC, does it automatically move to another thread?

No. \`handle\` is a synchronous callback; you must choose a suitable execution context or switch to a non-blocking driver. In WebFlux, avoid blocking the event loop.

## 18. References

- **Project Reactor Reference Guide — Handle**: [Programmatically creating a sequence, Handle section](https://projectreactor.io/docs/core/release/reference/coreFeatures/programmatically-creating-sequence.html).
- **Reactor API — Flux.handle(...)**: [Flux JavaDoc](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Flux.html).
- **Reactor API — Mono.handle(...)**: [Mono JavaDoc](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html).
- **Reactor API — SynchronousSink**: [SynchronousSink JavaDoc](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/SynchronousSink.html).
- **Reactor testing**: [StepVerifier documentation](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html).

**Remember:** **\`handle\` processes each upstream element synchronously and decides to emit \`0\` or \`1\` element, complete, or signal an error**. A callback may call \`sink.next\` at most once; **no \`next\` means skip input**, **\`complete\` means end stream**, **\`error\` means error termination**. Choose \`handle\` when filtering and transformation are coupled or when per-element signal control is needed; use \`flatMap\` for async work or when one input yields multiple results.