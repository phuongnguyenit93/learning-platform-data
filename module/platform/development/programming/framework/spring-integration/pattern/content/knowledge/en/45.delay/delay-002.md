# Fixed and dynamic delay periods in Spring Integration

## 1. Why choose how delay duration is calculated?

In Enterprise Integration Patterns (EIP), a **Delayer** receives a message, holds it for a specified duration, and then forwards it to the next endpoint. In Spring Integration, this is how you decouple **when an event is received** from **when processing continues** without putting the producer's thread to sleep.

A system typically encounters two requirements:

- **Fixed:** every order event must wait 2 seconds before being sent to the next processor.
- **Dynamic:** normal orders wait 2 seconds, but priority orders wait only 500 ms; a payment reminder may wait 15 minutes; another notification needs to be released at a given point in time.

In the **SPRING_INTEGRATION_PATTERN** module, choosing a delay period is a message flow design decision: it affects Routers, Filters, Transformers, Gateways, error handling, correlation, and how each branch is observed. This article focuses on **how to configure and test fixed delays versus dynamic delays**, along with the operational limits of each approach.

### Overall model

~~~mermaid
flowchart LR
    P[Producer] --> D{How wait duration is determined}
    D -->|Fixed| F["defaultDelay: 2,000 ms"]
    D -->|Per message| H["headers['delayMs']"]
    D -->|Absolute timestamp| A["headers['deliverAt']: Date"]
    F --> S[Delayer schedules]
    H --> S
    A --> S
    S --> Q[Next endpoint]
~~~

Positive delays are released by a `TaskScheduler`. The time a message actually reaches the consumer may be later than the scheduled release due to the scheduler, CPU, message store, or a busy consumer. **The delay period sets when the message becomes eligible for release**, not a guarantee that the entire business operation completes at that exact moment.

## 2. Distinguishing fixed and dynamic delays

| Criterion | Fixed | Dynamic per message |
| --- | --- | --- |
| Time source | One `defaultDelay` for the endpoint | Header, payload, or expression/function result |
| Unit of numeric values | Milliseconds | Milliseconds |
| Flexibility | Simple, easy to control | Each message can have its own duration |
| Common configuration | `.delay(d -> d.defaultDelay(2000L))` | `.delay(d -> d.defaultDelay(2000L).delayExpression("headers['delayMs']"))` |
| Main risk | Slows down every message, even priority cases | Invalid or abused headers, unpredictable wait times |
| Best suited for | General pause intervals, simple spaced processing | Priority-based notifications, scheduled appointments, expiration times |

**Key point:** when using a dynamic expression, `defaultDelay` remains useful as a fallback value. Both mechanisms can coexist in a single Delayer.

## 3. Fixed delay with `defaultDelay`

A Delayer can be configured to release every message after about 2,000 ms:

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.fixed.delay.v1")
        .defaultDelay(2_000L))
~~~

When no separate delay expression is specified, every message receives the same default wait duration. The value `2_000L` is in **milliseconds**, which is about 2 seconds.

Suppose three messages arrive at:

| Message | Time received by Delayer | Delay | Earliest possible release time |
| --- | --- | --- | --- |
| A | 10:00:00.000 | 2,000 ms | 10:00:02.000 |
| B | 10:00:00.300 | 2,000 ms | 10:00:02.300 |
| C | 10:00:01.000 | 2,000 ms | 10:00:03.000 |

Each message has its **own starting timestamp** based on when Delayer receives it; Delayer does not batch all messages together to release them all at the end of a 2-second cycle.

Situations well suited for a fixed delay:

- Creating a short wait so another system can finish updating data before it is read.
- Slowing down a business step that always requires a minimum wait.
- Simulating asynchronous conditions in integration exercises and tests.

Do not use a fixed Delayer as a requests-per-second rate limiter: 1,000 messages arriving together with a 2-second delay can still **all become due at the same time after about 2 seconds**, causing a traffic spike. Rate limiting and traffic shaping require dedicated mechanisms.

## 4. Dynamic delay by header or expression

With a dynamic delay, the producer or a Transformer step before Delayer provides a specific wait duration per message:

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.dynamic.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("headers['delayMs']"))
~~~

The SpEL expression `headers['delayMs']` reads the `delayMs` header value. If the header is missing and the expression returns `null`, Delayer uses `defaultDelay`. When the expression returns a valid duration value, that value takes precedence.

Examples of messages entering the same Delayer:

| Message | Header `delayMs` | Delay used | Meaning |
| --- | ---: | ---: | --- |
| Normal notification | Absent | 2,000 ms | Fall back to default |
| Priority notification | `500L` | 500 ms | Shorter wait |
| Payment reminder | `900_000L` | 900,000 ms | Wait 15 minutes |
| Event needing immediate forwarding | `0L` | 0 ms | No wait scheduled |

A numeric value of `0` or negative causes the message to be forwarded immediately, typically on the sender's thread. If the application requires processing to always be asynchronous, you must design the channel/execution path accordingly rather than assuming Delayer creates a thread for every message.

### Headers are not the only source

When the wait duration is calculated by business logic from the payload, SpEL can be used:

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.priority.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("payload.priority == 'HIGH' ? 500L : 5000L"))
~~~

The expression above only makes sense if the payload actually has a `priority` property, such as a Java record with a corresponding accessor. In real-world applications, a **Transformer** step can normalize incoming data into a type-checked delay header, keeping Delayer decoupled from payload structure.

Design limitation to remember: dynamic duration depends on **the message's own value when passing through the endpoint**. If the business changes priority rules after a message has already been scheduled, that change does not automatically update all previously created schedules.

### Absolute timestamp with `java.util.Date`

Another requirement is "release at 09:00 tomorrow" rather than "release after 10 minutes". Delayer's expression can supply a `java.util.Date` object indicating an **absolute release timestamp**:

~~~java
.delay(delayer -> delayer
        .messageGroupId("reminders.absolute.delay.v1")
        .defaultDelay(1_000L)
        .delayExpression("headers['deliverAt']"))
~~~

Producer:

~~~java
import java.time.Instant;
import java.util.Date;
import org.springframework.messaging.support.MessageBuilder;

var message = MessageBuilder.withPayload("REMINDER-42")
        .setHeader("deliverAt", Date.from(Instant.now().plusSeconds(30)))
        .build();
~~~

If `deliverAt` is about 30 seconds after the message is received, Delayer will schedule release for that timestamp. If the timestamp is in the past, the message is already due and is forwarded immediately. When the header is missing, `defaultDelay` applies.

**Distinguishing data types:** a `Long` such as `30_000L` represents a **30-second wait duration**, whereas a `Date` represents a **point on the clock**. Do not send Unix epoch milliseconds as a `Long` expecting Delayer to automatically interpret it as an absolute timestamp; convert it to a `Date` in your data normalization layer.

## 5. Complete Java DSL example: two independent flows

The example below declares two flows in the same configuration for comparison. Each flow has an input channel, a Delayer, and an output `QueueChannel` for easy testing. In a real system, the output could be a Service Activator, Router, Gateway, or adapter.

**Dependencies:** Spring Integration and `spring-boot-starter-integration` if using Spring Boot; the imports below illustrate Spring Integration Java DSL.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class DelayPeriodConfig {

    @Bean("fixed.in")
    public MessageChannel fixedIn() {
        return new DirectChannel();
    }

    @Bean("fixed.out")
    public PollableChannel fixedOut() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow fixedDelayFlow() {
        return IntegrationFlow.from("fixed.in")
                .delay(delayer -> delayer
                        .messageGroupId("demo.fixed.delay.v1")
                        .defaultDelay(1_000L))
                .channel("fixed.out")
                .get();
    }

    @Bean("dynamic.in")
    public MessageChannel dynamicIn() {
        return new DirectChannel();
    }

    @Bean("dynamic.out")
    public PollableChannel dynamicOut() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow dynamicDelayFlow() {
        return IntegrationFlow.from("dynamic.in")
                .delay(delayer -> delayer
                        .messageGroupId("demo.dynamic.delay.v1")
                        .defaultDelay(1_500L)
                        .delayExpression("headers['delayMs']"))
                .channel("dynamic.out")
                .get();
    }
}
~~~

**Explanation of each choice:**

1. `fixedDelayFlow()` uses `defaultDelay(1_000L)` for all messages. There is no override expression.
2. `dynamicDelayFlow()` uses the `delayMs` header if present; otherwise it uses 1,500 ms.
3. Two different `messageGroupId` values distinguish the waiting message groups. This is especially important when moving to a shared `MessageGroupStore`.
4. `DirectChannel` receives messages from the producer; positive delays are later forwarded through the scheduler.
5. `QueueChannel` is a test endpoint that supports `receive(timeout)`. It does not process business logic itself.

### Sending messages through both flows

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class DelayPublisher {
    private final MessageChannel fixedIn;
    private final MessageChannel dynamicIn;

    public DelayPublisher(MessageChannel fixedIn, MessageChannel dynamicIn) {
        this.fixedIn = fixedIn;
        this.dynamicIn = dynamicIn;
    }

    public void publish() {
        fixedIn.send(MessageBuilder.withPayload("FIXED-A").build());
        fixedIn.send(MessageBuilder.withPayload("FIXED-B").build());

        dynamicIn.send(MessageBuilder.withPayload("DEFAULT").build());
        dynamicIn.send(MessageBuilder.withPayload("URGENT")
                .setHeader("delayMs", 250L).build());
        dynamicIn.send(MessageBuilder.withPayload("LATER")
                .setHeader("delayMs", 3_000L).build());
    }
}
~~~

`DelayPublisher` is only an illustrative class; when using it in an application, inject the proper `fixed.in` and `dynamic.in` channel beans, for example with `@Qualifier`. If all five messages arrive at nearly the same time, `URGENT` may come out before `DEFAULT`, `FIXED-A`, and `LATER`. Delayer does not guarantee release order matches arrival order when wait durations differ.

## 6. Testing wait durations and fallback behavior

Measure elapsed time with `System.nanoTime()` to compare actual wait times within the same process. Use `receive(timeout)` to avoid hanging tests indefinitely; do not assert that a message must emerge at an exact millisecond.

~~~java
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(DelayPeriodConfig.class)
class DelayPeriodTest {

    @Autowired
    @Qualifier("fixed.in")
    MessageChannel fixedIn;

    @Autowired
    @Qualifier("fixed.out")
    PollableChannel fixedOut;

    @Autowired
    @Qualifier("dynamic.in")
    MessageChannel dynamicIn;

    @Autowired
    @Qualifier("dynamic.out")
    PollableChannel dynamicOut;

    @Test
    void fixedPeriodAppliesToEveryMessage() {
        long start = System.nanoTime();
        assertTrue(fixedIn.send(MessageBuilder.withPayload("F1").build()));

        assertNull(fixedOut.receive(100), "Must not be released before the 1-second deadline");
        Message<?> result = fixedOut.receive(3_000);

        assertNotNull(result);
        assertEquals("F1", result.getPayload());
        assertTrue(elapsedMs(start) >= 1_000L);
    }

    @Test
    void messageHeaderOverridesDefaultPeriod() {
        long start = System.nanoTime();
        assertTrue(dynamicIn.send(MessageBuilder.withPayload("URGENT")
                .setHeader("delayMs", 650L).build()));

        assertNull(dynamicOut.receive(100));
        Message<?> result = dynamicOut.receive(2_500);

        assertNotNull(result);
        assertEquals("URGENT", result.getPayload());
        assertTrue(elapsedMs(start) >= 650L);
    }

    @Test
    void absentHeaderUsesDynamicFlowsDefault() {
        long start = System.nanoTime();
        assertTrue(dynamicIn.send(MessageBuilder.withPayload("DEFAULT").build()));

        assertNull(dynamicOut.receive(100));
        Message<?> result = dynamicOut.receive(3_000);

        assertNotNull(result);
        assertEquals("DEFAULT", result.getPayload());
        assertTrue(elapsedMs(start) >= 1_500L);
    }

    private static long elapsedMs(long startNanos) {
        return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startNanos);
    }
}
~~~

Running tests with a real scheduler means results can arrive **later than** the configured number of milliseconds. Under heavy CI load, increase the timeout for `receive(...)`, but do not relax the check that it "does not arrive before the deadline". Do not use `Thread.sleep(650)` and expect exact precision; checking behavior at the output is stronger evidence.

Test cases to expand in a real project:

- Header equal to `0L`: message passes through immediately; verify interaction with synchronous channels.
- Negative header: verify business policy (forward immediately or reject before Delayer).
- Missing header: fall back to `defaultDelay`.
- Header with invalid type: verify expression handling and normalized data.
- `Date` in the future and in the past: verify absolute timestamps.
- Multiple messages with the same wait duration: verify load, ordering, metrics, and behavior when the scheduler is busy.
- Application restart while messages are still pending: verify durability and redelivery capability.

## 7. Handling dynamic data safely

If wait durations come from an API, message broker, or another system, do not blindly trust every header value. Excessively large values cause messages to be held unexpectedly long; wrong data types can cause expression evaluation errors; negative values can skip the waiting step.

Place business policy **before Delayer**:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean sendWithValidatedDelay(
        MessageChannel input, String payload, long requestedMs) {

    final long maximumMs = 15 * 60 * 1_000L;

    if (requestedMs < 0L || requestedMs > maximumMs) {
        throw new IllegalArgumentException("delayMs is outside the allowed range");
    }

    return input.send(MessageBuilder.withPayload(payload)
            .setHeader("delayMs", requestedMs)
            .build());
}
~~~

The example code allows a range from 0 to 15 minutes; a real system can set limits by event type, SLA, or authorization. If *priority* rules are needed, assign the value after validation:

| Event type | Allowed delay | Reason |
| --- | --- | --- |
| Critical alert | 0–500 ms | Do not hold alerts too long |
| Regular notification | 1,000–5,000 ms | Controlled short delay |
| Payment reminder | Per business policy, potentially several minutes | Need to check order status before sending |
| Scheduled on-time delivery | Normalized absolute `Date` | Time zone must be explicitly determined when creating the schedule |

For `Date`, convert a zoned local time into an explicit `Instant` before creating the `Date`. Avoid parsing a string like `"09:00"` without knowing the date, time zone, and daylight saving time rules; those decisions belong to the business layer before Delayer.

### Fallback does not replace validation

`defaultDelay` is a fallback when an expression fails to provide a valid delay according to Delayer's rules. It is **not** responsible for blocking malicious payloads, enforcing SLAs, or fixing all bad data. Ensure the producer/Transformer creates headers with accepted types, and write tests for absent values, wrong types, and very large numbers.

If an expression evaluation error is configured to be ignored by Spring Integration, Delayer may use the default value and log the error. If the application needs to fail explicitly when delay data is invalid, use `ignoreExpressionFailures(false)` and handle the error before or at the endpoint. The choice must align with business requirements; never silently fall back for messages whose release time is a commitment.

## 8. Observability and operations

A loosely coupled, extensible system needs to track **why a message was released at that time**. Business fields should be added:

- `eventId`, `correlationId`: trace a message across Filter, Transformer, Delayer, and Router.
- `requestedDelayMs` or `deliverAt`: the requested wait duration after validation.
- `receivedAt`: timestamp when entering the flow (UTC).
- `releasedAt`: timestamp when the step after Delayer actually sees the message.

Measure `actualWaitMs = releasedAt - receivedAt`, and if there is an expected timestamp, measure `scheduleLagMs = releasedAt - expectedReleaseAt`. The lag between "due" and "actually released" helps identify an overloaded scheduler or slow store.

~~~mermaid
flowchart LR
    A[Receive message] --> B[Filter + validate]
    B --> C[Transformer computes delay]
    C --> D[Fixed or dynamic Delayer]
    D --> E{Event type router}
    E --> F[Email handler]
    E --> G[Webhook handler]
    F --> H[Metrics, logs, tracing]
    G --> H
~~~

### Message store and restart

If Delayer uses an in-memory store, pending messages may be lost when the application stops. For important notifications or long delays, consider `JdbcMessageStore` (or a suitable persistent `MessageGroupStore`), attach a stable `messageGroupId`, and test message recovery after restart.

A persistent store does not automatically provide *exactly-once* guarantees. Consumers must process idempotently by `eventId` or business key. When running multiple instances, design a coordination mechanism rather than assuming sharing one database is enough to prevent duplicate message delivery.

### Release errors and retries

With a positive delay, consumer errors occur **after** the producer has already sent the message. Therefore, the producer may receive a successful send result while a downstream step later fails. Design an error channel, retry policy, and error observability on the release branch; do not infer that `send() == true` means the business operation succeeded.

To distinguish operational issues:

| Symptom | What to check |
| --- | --- |
| Message arrives immediately even though waiting was intended | `delayMs` header is 0/negative, wrong expression, or message bypassed Delayer |
| Every message waits the same duration | `delayExpression` not attached properly, header missing, or fallback always applies |
| Message arrives later than scheduled | Overloaded scheduler, slow downstream processing, slow store, application recently restarted |
| Message lost after restart | Using in-memory store or recovery not configured |
| A message is processed twice | Retry/redelivery after error or distributed execution; check idempotency |
| Synchronous gateway times out | Response released by Delayer after timeout; design asynchronous reply or adjust timeout per business requirements |

## 9. When to choose each approach?

Use **fixed** when all messages in an endpoint follow the same timing policy. This approach is easy to explain, requires less data validation, and is useful when only a uniform pause interval is needed.

Use **dynamic by header** when each message carries a different priority, SLA, or event type. Normalize and bound the header before feeding it into Delayer, and keep `defaultDelay` as an intentional fallback.

Use **dynamic by absolute `Date` timestamp** when business logic states "release at time X". This timestamp must be calculated with explicit normalized time; if the policy can change continuously, design a mechanism to cancel/update schedules.

**All three approaches only decide when each individual message is released.** If the requirement is rate limiting, periodic scheduled jobs, or holding a workflow waiting for a response over several days, also consider a rate limiter, business scheduler, message broker, saga/workflow engine, or an appropriate orchestrator.

## 10. Practice exercises and self-check questions

1. Configure the first flow with a fixed 800 ms delay; prove with a test that the message is not released early.
2. Extend the dynamic flow with levels `NORMAL = 2000`, `HIGH = 200`, and `DEFERRED = 10000`; place a Transformer before Delayer to generate the `delayMs` header.
3. Send one message with `delayMs = 0`, one message missing the header, and one message with `delayMs = 3_000L`. Explain the possible release order.
4. Create a `Date` representing 30 seconds in the future from `Instant`; send it through a Delayer using `headers['deliverAt']` and measure release drift.
5. Simulate heavy scheduler load: does an actual delay greater than requested mean Delayer is buggy, or just delayed release?
6. Replace the store with a persistent implementation, restart the application while messages are pending, and verify consumer side effects are not duplicated.
7. From the flow `Filter → Transformer → Delayer → Router`, identify where to validate input, generate `correlationId`, measure `scheduleLagMs`, and handle the error channel.

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): default delay configuration, expressions, absolute time, scheduler, and message storage.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): declaring `IntegrationFlow` and endpoints with Java DSL.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): storing pending messages and persistence options.
