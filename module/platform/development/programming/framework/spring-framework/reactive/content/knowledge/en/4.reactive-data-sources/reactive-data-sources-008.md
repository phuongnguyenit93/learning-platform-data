# Integrating Callback APIs via `Flux.create` and Handling Cancellation Requests

## 1. Problem: Traditional Callbacks Meet Reactive Programming

In Spring WebFlux, many components process data as `Mono<T>` or `Flux<T>`. However, an SDK, networking library, IoT device, or legacy Java API may use **callbacks/listeners**:

- `onData(value)` is called each time the source has data.
- `onComplete()` is called when the work finishes successfully.
- `onError(error)` is called when the work fails.
- `register(listener)`, `start(listener)`, or `subscribe(listener)` returns a handle to stop the work and remove the listener.

The goal is to turn callbacks emitting **0 to many events** into a `Flux<T>`, while propagating **cancellation signals from downstream** back to the SDK. Without the second step, when a user closes the page or an HTTP client disconnects, the SDK may keep working, holding sockets/timers and retaining unnecessary listeners.

`Flux.create` is Project Reactor's tool for creating a `Flux` via active signals, especially useful when integrating asynchronous callback APIs that can emit multiple events, including from multiple threads. However, `create` **does not automatically spawn threads, does not turn blocking code into non-blocking, and does not automatically know how to cancel SDK resources**.

## 2. Mapping Callbacks to Flux Signals

Suppose an external API defines:

~~~java
// Illustrates the SDK contract only, not a standalone program.
interface EventListener {
    void onData(String value);
    void onComplete();
    void onError(Throwable error);
}
~~~

Inside `Flux.create(sink -> ...)`, Reactor provides a `FluxSink<T>`. We map:

| Event | Action in Bridge | Signal Seen by Subscriber |
| --- | --- | --- |
| Callback receives a valid value | `sink.next(value)` | `onNext(value)` |
| SDK completes successfully | `sink.complete()` | `onComplete()` |
| SDK reports an error | `sink.error(error)` | `onError(error)` |
| Subscriber requests cancellation | `sink.onCancel(...)` | Propagates stop request to source |
| Any termination/cancellation | `sink.onDispose(...)` | Reclaims listener and resources |

A `Flux` can emit **0, 1, or N `onNext` signals** and then end with **one of the two** terminal signals: `onComplete` or `onError`. After a terminal signal, no more elements may be emitted; `null` is not allowed as an `onNext` value. If the source has no elements and finishes successfully, `sink.complete()` is valid.

Simple bridge pattern:

~~~java
// Illustrative structure only; SDK, Handle, and callbacks must be implemented.
Flux<String> stream = Flux.create(sink -> {
    Handle handle = sdk.start(
        value -> sink.next(value),
        error -> sink.error(error),
        () -> sink.complete()
    );
    sink.onCancel(handle::cancel);
    sink.onDispose(handle::close);
});
~~~

Unlike a callback that returns **a single result**, where `Mono.create` and `MonoSink` can be used, `Flux.create` is meant for cases that can receive **multiple** values. `Flux.push` is more suitable if all signals come from **a single producer thread**; `Flux.create` supports multi-threaded sources. `Flux.generate` has a synchronous turn-by-turn emission model allowing at most one `next` per generator invocation, so it is not equivalent to an asynchronous listener bridge.

### When Does Registration Happen?

`Flux.create` creates a publisher whose emitter lambda is normally executed **for each subscription**. Therefore, calling `Flux<String> flux = adapt(api)` only constructs the source; calling `flux.subscribe(...)` is what triggers registering the corresponding listener. Two subscribers by default will produce **two registrations** if the lambda calls `api.start(...)` each time.

This matters when integrating with HTTP: listener lifecycle must be tied to **each subscription**, without mistakenly using a global handle variable that lets subscriber A cancel subscriber B's work. If you need a **hot** event source shared across multiple clients, design an explicit sharing and subscriber-counting mechanism; do not assume `Flux.create` automatically shares a single listener.

## 3. Distinguishing `onCancel` and `onDispose`

These two hooks handle different parts of the lifecycle:

| How Did the Subscription End? | `sink.onCancel(...)` | `sink.onDispose(...)` |
| --- | --- | --- |
| Downstream calls `cancel()` | Yes | Yes |
| `Disposable` returned by `subscribe()` has `dispose()` called | Yes | Yes |
| Operator `take(n)` cancels upstream after receiving enough | Yes on cancelled upstream | Yes |
| SDK calls `sink.complete()` | No | Yes |
| SDK calls `sink.error(e)` | No | Yes |

On **cancellation**, `onCancel` runs **before** `onDispose`. On natural completion/error, **only** `onDispose` is triggered. Therefore responsibilities should be separated:

- **`onCancel`**: sends a *stop/cancel* command to the running operation in the SDK if the handle supports cancellation. This signal is specifically for when downstream no longer needs data.
- **`onDispose`**: *unregisters/closes/detaches* the listener and releases resources owned by a subscription, regardless of cancel, error, or complete.
- **`sink.error` / `sink.complete`**: represent how the source terminates; do not manually invoke `onCancel` to simulate an error or normal completion.

`onCancel` and `onDispose` each accept one primary callback per `FluxSink`. If multiple things must be cleaned up, combine the related cleanup actions into the managed callback consistently. Cleanup should be **idempotent**: if there is a race between threads or the SDK signals a terminal event right as the client cancels, running cleanup must not error or close the wrong resource.

An easily confused distinction: `Disposable.dispose()` on the object returned by `subscribe()` normally **sends cancel**. Meanwhile, `sink.onDispose` is a **cleanup hook** that can run after natural termination, even when there is no cancel.

## 4. Runnable Java 17+ Example: Callbacks, Cancellation, and Listener Cleanup

The standalone example below needs only **Reactor Core** and Maven; it simulates an SDK capable of registering multiple listeners. `main` emits events in a fixed order to verify the exact output. Each registration returns a `Registration`, where `cancel()` stops that subscription's work and `close()` removes the listener from the list. `AtomicBoolean` prevents those two operations from running repeatedly; `CopyOnWriteArrayList` allows modifying the list while callbacks are being iterated.

Create the structure:

~~~text
callback-bridge/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── CallbackBridgeDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>callback-bridge</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/CallbackBridgeDemo.java`:

~~~java
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

public class CallbackBridgeDemo {
    interface Listener {
        void onData(String value);
        void onCompleted();
        void onFailure(Throwable error);
    }

    static final class CallbackApi {
        private final CopyOnWriteArrayList<Registration> registrations =
                new CopyOnWriteArrayList<>();

        Registration start(Listener listener) {
            Registration registration = new Registration(this, listener);
            registrations.add(registration);
            return registration;
        }

        void emit(String value) {
            for (Registration registration : registrations) {
                if (!registration.cancelled.get()) {
                    registration.listener.onData(value);
                }
            }
        }

        void finish() {
            for (Registration registration : registrations) {
                if (!registration.cancelled.get()) {
                    registration.listener.onCompleted();
                }
            }
        }

        int activeCount() {
            return registrations.size();
        }

        static final class Registration {
            private final CallbackApi api;
            private final Listener listener;
            private final AtomicBoolean cancelled = new AtomicBoolean();
            private final AtomicBoolean closed = new AtomicBoolean();

            Registration(CallbackApi api, Listener listener) {
                this.api = api;
                this.listener = listener;
            }

            void cancel() {
                if (cancelled.compareAndSet(false, true)) {
                    System.out.println("API: cancel work");
                }
            }

            void close() {
                if (closed.compareAndSet(false, true)) {
                    api.registrations.remove(this);
                    System.out.println("API: unregister listener");
                }
            }
        }
    }

    static Flux<String> adapt(CallbackApi api) {
        return Flux.<String>create(sink -> {
            Listener listener = new Listener() {
                @Override
                public void onData(String value) {
                    if (!sink.isCancelled()) {
                        sink.next(value);
                    }
                }

                @Override
                public void onCompleted() {
                    sink.complete();
                }

                @Override
                public void onFailure(Throwable error) {
                    sink.error(error);
                }
            };

            CallbackApi.Registration registration = api.start(listener);

            // Runs only when downstream cancels the subscription.
            sink.onCancel(registration::cancel);

            // Runs after complete, error, or cancel.
            sink.onDispose(registration::close);
        }, FluxSink.OverflowStrategy.ERROR);
    }

    public static void main(String[] args) {
        CallbackApi api = new CallbackApi();
        Flux<String> events = adapt(api);

        Disposable first = events.subscribe(
                item -> System.out.println("first: " + item),
                error -> System.out.println("first error: " + error.getMessage()),
                () -> System.out.println("first complete")
        );
        api.emit("A");
        api.emit("B");
        first.dispose();       // Cancel the first subscription.
        api.emit("C");         // The first listener is gone.
        System.out.println("active: " + api.activeCount());

        events.subscribe(
                item -> System.out.println("second: " + item),
                error -> System.out.println("second error: " + error.getMessage()),
                () -> System.out.println("second complete")
        );
        api.emit("D");
        api.finish();          // API completes naturally.
        System.out.println("active: " + api.activeCount());
    }
}
~~~

In the `callback-bridge` directory, with JDK 17+ and Maven run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=CallbackBridgeDemo
~~~

**Program output** (ignoring extra Maven notices if present in the environment):

~~~text
first: A
first: B
API: cancel work
API: unregister listener
active: 0
second: D
second complete
API: unregister listener
active: 0
~~~

Explanation:

1. The first `subscribe()` registers a listener. Both `api.emit("A")` and `api.emit("B")` callbacks are turned into `sink.next` and the subscriber receives `first: A`, `first: B`.
2. `first.dispose()` triggers **cancellation from downstream**. Reactor calls `onCancel` so `registration.cancel()` signals stop, then calls `onDispose` so `registration.close()` removes the listener. Therefore event `C` is no longer received.
3. The second subscription creates an independent `Registration`, then receives `D`. When `api.finish()` calls the `onCompleted()` callback, the adapter calls `sink.complete()`; the subscriber receives `second complete` and `onDispose` unregisters the listener.
4. The second run does not print `API: cancel work` because the source **completed naturally**, without being cancelled by downstream. The two `active: 0` lines prove the listener list is cleaned up after each branch.

In the example, `CallbackApi` is a **simple simulation**: `main` invokes callbacks on the same thread for deterministic output. In practice, an SDK may invoke callbacks from worker threads, thread pools, or network threads. `Flux.create` is designed for multi-producer-thread scenarios as well, but the adapter and SDK handles still need thread-safety.

## 5. Flow When the Subscriber Cancels

~~~text
downstream subscribe()
       |
       v
Flux.create(...) runs for this subscription
       |
       v
api.start(listener) -> Registration
       |
       +-- SDK data callback -----> sink.next(value) -----> onNext(value)
       |
       +-- SDK finish callback ---> sink.complete() -------> onComplete
       |                                |
       |                                +--> onDispose: unregister
       |
       +-- SDK error callback ----> sink.error(error) ----> onError
       |                                |
       |                                +--> onDispose: unregister
       |
       +-- downstream cancel()
              |
              +--> onCancel: cancel upstream work
              |
              +--> onDispose: unregister listener
~~~

Common situations triggering cancellation: calling `Disposable.dispose()`, a subscriber calling `Subscription.cancel()`, an operator like `take(3)` receiving enough elements and cancelling upstream, or an HTTP client closing the stream causing the server to cancel the subscription upon detecting disconnect.

Remember that **`sink.isCancelled()` does not stop the SDK**. It only returns the state the sink observed when read; cancellation can race with late-arriving callbacks. The adapter must invoke the actual `cancel/stop/unregister` mechanism on the external API, while avoiding emitting after a terminal signal. When an SDK provides no way to cancel work, at minimum detach the callback and prevent retaining resources indefinitely; you may have to accept that the background task finishes even though the client is no longer listening.

Practical implementation notes:

- Register the listener and cleanup hooks **per subscription**, keeping the handle local inside the lambda.
- Clean up resources on completion/error **and** on cancellation; `onCancel` alone does not cover all three paths.
- Write idempotent cleanup; guard against races between unregistering the listener, the SDK invoking a final callback, and downstream cancelling.
- An SDK may invoke callbacks synchronously during `start/register`. When attaching `onDispose` after obtaining the handle, Reactor can invoke the hook immediately if the sink is already disposed. Verify the SDK contract so resources are not leaked if registration synchronously completes or throws mid-way.
- If a callback might re-send terminal signals or emit `onNext` after a terminal signal, guard at the SDK boundary and do not assume stale events are all handled as desired.
- Never close connections or stop **application-wide shared** resources just because one subscriber cancels; distinguish per-subscription sources from shared hot sources.

## 6. Backpressure: Callbacks Pushing Faster Than Consumption Capacity

Reactive Streams allows downstream to request a number of elements via `request(n)`. However, a push-style callback SDK can emit at its own pace. `Flux.create` lets you pick a `FluxSink.OverflowStrategy` to handle signals exceeding demand:

| Strategy | Behavior | Risk / Choice |
| --- | --- | --- |
| `BUFFER` (default) | Buffers signals when demand is insufficient | **Unbounded buffer**; fast infinite sources can exhaust RAM |
| `DROP` | Drops new values when downstream is not ready | Loses some events; use only if business logic permits |
| `LATEST` | Keeps the latest value to deliver when demand arrives | Suits state updates where intermediate versions can be skipped |
| `ERROR` | Emits an error when downstream cannot keep up | Suits cases where data loss is unacceptable and failing fast is needed |
| `IGNORE` | Ignores demand at the sink, keeps pushing | Downstream may fail due to full queues; weigh carefully |

The example uses `ERROR` to avoid holding every value in memory. `subscribe(onNext, onError, onComplete)` by default requests unbounded data, so the simple example does not trigger overflow. With a subscriber limiting demand, `ERROR` can lead to `onError` and trigger cleanup.

**Best if the SDK supports throttling at the source:** use `sink.onRequest(n -> api.requestMore(n))` to proactively request more data, or use the SDK's pause/resume mechanism. This is **illustrative** because `api.requestMore` is not a built-in Reactor method. `requestedFromDownstream()` reports the remaining demand at the moment of reading; do not treat reading this number as a synchronization lock across threads. With sources that cannot slow down, establish a clear data-loss policy, bounded queue, or explicit error reporting depending on the event type.

**Do not misunderstand:** having a backpressure strategy on `Flux.create` does not mean the SDK itself stops generating data. To save upstream work, you must wire demand/cancellation into the SDK's corresponding mechanism.

## 7. Bringing Callback Flux into Spring WebFlux

For HTTP streaming, you can return the `Flux` directly from a controller:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

@RestController
class SensorController {
    private final SensorSdk sdk;

    SensorController(SensorSdk sdk) {
        this.sdk = sdk;
    }

    @GetMapping(value = "/sensor/updates",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<String> updates() {
        return Flux.<String>create(sink -> {
            SensorHandle handle = sdk.subscribe(
                value -> sink.next(value),
                error -> sink.error(error),
                () -> sink.complete()
            );
            sink.onCancel(handle::cancel);
            sink.onDispose(handle::close);
        }, FluxSink.OverflowStrategy.LATEST);
    }
}
~~~

**This is an illustrative pattern placed in a Spring Boot WebFlux app with `SensorSdk` and `SensorHandle` provided by the SDK**, not standalone-compilable like the Maven example above. Actual callback API names may vary in real libraries. Only choose `LATEST` when a sensor stream can skip older updates; do not use it if every event is a transaction that must be delivered completely.

Because the controller **returns the publisher** to WebFlux, the framework manages the subscription alongside writing the HTTP response. When a client closes SSE and the server detects the lost connection, cancellation usually propagates back to the source and triggers the hooks; when disconnect detection happens also depends on the environment, network, and write attempts. Verify this behavior by logging active listener counts or testing client mid-stream disconnects.

Do not call `subscribe()` manually inside the controller to launch the adapter and return a different publisher: that detaches the source work from the HTTP lifecycle and can prevent client cancellation from stopping the SDK.

## 8. Common Mistakes

1. **Forgetting to register cleanup**: the SDK retains the listener even after the client leaves. Fix with `onDispose`, and `onCancel` to stop work if possible.
2. **Using only `onCancel`**: the `complete` and `error` branches do not run that hook, easily leaking resources. Attach `onDispose` for shared cleanup.
3. **Using `sink.error` for cancellation requests**: cancel is a downstream signal, whereas error is a failed termination from the source. Keep the two directions separate.
4. **Sharing one handle across all subscribers**: cancelling A drops B's data. Create a registration per subscription or design managed sharing.
5. **Believing `Flux.create` automatically makes an SDK asynchronous**: if the lambda calls blocking APIs, the thread is still blocked. Do not wait on I/O or run infinite loops inside an emitter on the event loop.
6. **Emitting `null` or emitting after terminal**: Reactive Streams does not accept `null` and allows no elements after `onComplete/onError`. Normalize callbacks at the adapter.
7. **Keeping `BUFFER` for high-rate, unbounded callbacks**: risk of OutOfMemoryError. Pick an explicit strategy and throttle the source when possible.
8. **Only checking `isCancelled`**: checking can race and does not automatically close sockets. You must execute cancel/unregister on the SDK.
9. **Not testing the error path**: when the SDK fails, the bridge needs `sink.error` so the subscriber receives the error and `onDispose` runs cleanup.
10. **Assuming every `Flux.create` is a hot shared stream**: the lambda typically re-runs per subscription. Decide explicitly whether the adapter creates per-subscription sources or truly shares one.

## 9. QA Scenarios to Test Before Using with a Real SDK

| Scenario | Expected Outcome |
| --- | --- |
| Source completes without emitting any elements | `onComplete`; listener is removed, `onCancel` does not run |
| Source emits multiple elements then completes | Each `onNext` in order guaranteed by SDK; cleanup runs once |
| Source emits a few elements then errors | `onError`; no `onComplete` after error; cleanup runs once |
| Subscriber cancels immediately after subscribing | SDK receives stop/cancel if supported, listener is removed |
| `take(2)` receives two elements | Upstream is cancelled, SDK stops and cleans up, downstream terminates per contract |
| Cancel happens concurrently with a callback | No listener leak, no error from repeated cleanup, no out-of-contract emissions |
| Two subscribers listening together | Two appropriate registrations; cancelling one does not affect the other |
| Callback is faster than demand | BUFFER/DROP/LATEST/ERROR policy matches business rules and memory is verified |
| SSE client disconnects | Once the server detects cancellation, active handle/listener count drops |

**Takeaway:** Integrating callback APIs via `Flux.create` has **two mandatory directions**: events from the SDK go into `sink.next/error/complete`, and cancellations from the subscriber flow back to the SDK via `onCancel`. The `onDispose` hook ensures listener/resource reclamation across **all three** termination paths: completion, error, and cancellation. Only with full lifecycle management is a bridge ready for WebFlux data streams with many clients and mid-stream disconnects.

**Official documentation:** [Project Reactor – Programmatically Creating a Sequence](https://projectreactor.io/docs/core/release/reference/coreFeatures/programmatically-creating-sequence.html), [FluxSink API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/FluxSink.html), [FluxSink.OverflowStrategy](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/FluxSink.OverflowStrategy.html).