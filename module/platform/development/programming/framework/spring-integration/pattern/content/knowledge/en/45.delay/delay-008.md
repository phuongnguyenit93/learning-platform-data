# Time zones and absolute timestamps in Spring Integration Delayer

## 1. The problem: where is "send at 09:00"?

A sales application receives a request: **"On 2026-12-01 at 09:00, send a notification to a customer in Vietnam."** If it only stores the string `2026-12-01 09:00`, the system does not know the actual point in time. The server runs in UTC, Vietnam uses the `Asia/Ho_Chi_Minh` time zone, and operators might inspect logs on a machine in a different time zone. Using the wrong time zone can cause the notification to be released hours off schedule.

Delayer in Spring Integration can delay a message:

- **By relative duration:** "wait 30 more seconds from receipt".
- **By absolute timestamp:** "wait until `2026-12-01T02:00:00Z` to become eligible for release".

In the **SPRING_INTEGRATION_PATTERN** module, time choices affect how Filter, Transformer, Router, Gateway, retry, error channel, and correlation are composed. The goal is to build a loosely coupled, extensible, testable message flow that can trace **when it was due**, **when it was released**, and **why it was released late**.

For the problem at the start of the lesson:

~~~text
User requested:     2026-12-01 09:00, Asia/Ho_Chi_Minh
UTC timestamp:      2026-12-01T02:00:00Z
Java Instant:       2026-12-01T02:00:00Z
Date for Delayer:   Date.from(instant)  // represents the same point in time
~~~

**Key point:** Delayer takes a **resolved point in time** for scheduling. Converting "local time + time zone + business rules" into that timestamp should happen **before** Delayer and be explicitly tested.

## 2. Java time types to distinguish

| Type | What information does it carry? | Role in the flow |
| --- | --- | --- |
| `LocalDateTime` | Date and time on a wall clock, **without a time zone** | Accepts user-entered schedules, e.g., `2026-12-01T09:00` |
| `ZoneId` | Time zone with regional rules | `Asia/Ho_Chi_Minh`, `America/New_York` |
| `ZonedDateTime` | Local date-time + `ZoneId` and matching offset | Interprets a local schedule into an unambiguous point in time |
| `ZoneOffset` | UTC offset at a point in time, e.g., `+07:00` | Validates local times, handles daylight saving time |
| `OffsetDateTime` | Date-time + fixed offset at that moment | Exchanges an instant with offset, without full regional zone rules |
| `Instant` | Absolute point on the UTC timeline | Stores and compares deadlines stably |
| `java.util.Date` | Absolute point in time, millisecond precision | Value Delayer expressions can use as a **release timestamp** |
| `long` | A number | When Delayer interprets it as a delay, **the unit is relative milliseconds** |

**`LocalDateTime` is not enough to schedule accurately.** The same "09:00" on a clock in Hanoi and New York represents two different instants. Conversely, one `Instant` can be displayed as many local times while still being **a single point in time**.

### From the same 09:00 to different UTC timestamps

Suppose the date is **2026-12-01**:

| User input | Time zone | Corresponding UTC timestamp |
| --- | --- | --- |
| 09:00 | `Asia/Ho_Chi_Minh` (UTC+07:00) | 02:00Z |
| 09:00 | `UTC` | 09:00Z |
| 09:00 | `America/New_York` (UTC−05:00 on this date) | 14:00Z |

In this example, every record says "09:00", yet they must not share the same deadline if recipients are in different time zones.

## 3. Relative numeric delays vs. absolute `Date`

In Delayer, the delay expression can supply a number of milliseconds or a `java.util.Date`:

| Expression returns | Interpretation | Illustration |
| --- | --- | --- |
| `30_000L` | Wait **30 seconds from when Delayer receives the message** | Received 10:00:00 → expected release from 10:00:30 |
| `Date.from(instant)` | Wait until **timestamp `instant`** | `2026-12-01T02:00:00Z` |
| `0L` or negative number | No positive wait needed | May forward immediately |
| `Date` in the past | Timestamp already due | May forward immediately |
| `null` from missing header | Use `defaultDelay` | Depends on configuration |

**Do not send epoch milliseconds as a `Long` expecting Delayer to treat it as an absolute timestamp.** For example, `1_796_090_400_000L` is a huge number; when interpreted as a *relative delay*, it can create a wait of many years. If you want a deadline, convert those epoch milliseconds into a `Date`:

~~~java
long epochMillis = java.time.Instant.parse("2026-12-01T02:00:00Z")
        .toEpochMilli();
java.util.Date deliverAt = new java.util.Date(epochMillis);
~~~

Even though `Date` has a name suggesting "date", it represents an instant in time and carries no `ZoneId`. The same `Date` may display differently on different machines because default formatting uses the JVM's default time zone. **Do not use `Date.toString()` as a canonical deadline representation in logs or API communication.**

## 4. Safely converting local time to an absolute timestamp

### 4.1. Standard procedure

1. Receive **date**, **local time**, and **IANA time zone** from input data.
2. Parse the input into `LocalDateTime` and `ZoneId`; check whether the time exists and is unique in that time zone.
3. Convert to `Instant`.
4. Validate the deadline: still in the future, not too far out, and complies with business rules.
5. Create `Date.from(instant)` to send to Delayer; also retain `eventId` and the requested time zone metadata for auditing.

~~~mermaid
flowchart LR
    A["User: 09:00 2026-12-01"] --> B["ZoneId: Asia/Ho_Chi_Minh"]
    B --> C["Validate date-time in ZoneRules"]
    C --> D["Instant: 2026-12-01T02:00:00Z"]
    D --> E["Date.from(instant)"]
    E --> F["Delayer: delayExpression"]
    F --> G["Release when due"]
~~~

### 4.2. Conversion helper with daylight saving time validation

Java 17+ example rejecting both **non-existent** local times and times with **two interpretations**; an application can choose another policy, provided it is explicit and testable:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public final class ScheduleTimes {
    private ScheduleTimes() {
    }

    public static Instant resolveStrict(
            LocalDateTime localTime, ZoneId zone) {

        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(localTime);

        if (offsets.size() == 0) {
            throw new IllegalArgumentException(
                    "Local time does not exist in the selected time zone");
        }
        if (offsets.size() > 1) {
            throw new IllegalArgumentException(
                    "Local time has two valid instants; an offset must be chosen");
        }

        return ZonedDateTime.ofStrict(localTime, offsets.get(0), zone)
                .toInstant();
    }
}
~~~

Using it for Vietnam time:

~~~java
LocalDateTime localTime =
        LocalDateTime.of(2026, 12, 1, 9, 0);
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant deliverAtInstant =
        ScheduleTimes.resolveStrict(localTime, businessZone);

// 2026-12-01T02:00:00Z
System.out.println(deliverAtInstant);

java.util.Date deliverAt = java.util.Date.from(deliverAtInstant);
~~~

Never pick `ZoneId.systemDefault()` out of habit when a schedule belongs to a specific customer or market. The JVM's default time zone can change when containers deploy to different environments.

## 5. Daylight saving time (DST): missing or repeated hours

Some regions shift their offset seasonally. There are two special cases:

- **Gap:** clocks spring forward, so certain local times do not exist at all.
- **Overlap:** clocks fall back, so the same local time occurs **twice** with two different offsets.

Examples using current `America/New_York` time zone rules:

| Local date-time | Phenomenon | Handling in this example |
| --- | --- | --- |
| `2026-03-08 02:30` | Gap when entering DST | Reject, ask user to pick another time |
| `2026-11-01 01:30` | Overlap when returning to standard time | Reject until an explicit offset is chosen |
| `2026-12-01 09:00` | Valid, unique time | Convert to `Instant` |

~~~mermaid
flowchart TD
    A["LocalDateTime + ZoneId"] --> B{"Number of valid offsets?"}
    B -->|0| C["Gap: reject or adjust per policy"]
    B -->|1| D["Convert to Instant"]
    B -->|2| E["Overlap: require choosing offset or apply explicit policy"]
    C --> F["Return guided error"]
    E --> F
    D --> G["Store absolute deadline"]
~~~

`ZonedDateTime.of(localTime, zone)` has a default policy for gaps/overlaps; if the application does not want automatic adjustment, use `ZoneRules.getValidOffsets(...)` as shown above. Do not treat Java's automatic local-time adjustment as a business decision approved by the user.

**Recurring schedule rule:** if a user wants "every day at 09:00 New York time", retain **local time + ZoneId + recurrence rule** to compute **a new deadline for each occurrence**. You cannot replace this schedule by endlessly adding `24 * 60 * 60 * 1000` to the previous `Instant`, because DST transition days can be 23 or 25 hours long. A single Delayer only delays **one message until one deadline**; it is not a cron scheduler itself.

### When should the user's chosen offset be stored?

For an overlap, the application can present the user with the two valid timestamps (the pre-transition offset and post-transition offset). Once chosen, store that choice or store the final `Instant`. Do not guess "the first 01:30" or "the second 01:30" for critical business operations like payment schedules and legal notices.

## 6. Java DSL: Delayer accepting an absolute deadline

This example declares a flow with a `deliverAt` header containing a `java.util.Date`. The input channel receives messages from the producer; Delayer waits until the deadline; the output `QueueChannel` facilitates testing with `receive(timeout)`.

Spring Boot dependencies include `spring-boot-starter-integration`; the test below needs `spring-boot-starter-test`.

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
public class AbsoluteTimeDelayConfig {

    @Bean("scheduled.in")
    public MessageChannel scheduledInput() {
        return new DirectChannel();
    }

    @Bean("scheduled.ready")
    public PollableChannel scheduledReady() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow absoluteTimeDelayFlow() {
        return IntegrationFlow.from("scheduled.in")
                .delay(spec -> spec
                        .messageGroupId("notifications.absolute-time.delay.v1")
                        .defaultDelay(1_000L)
                        .delayExpression("headers['deliverAt']"))
                .channel("scheduled.ready")
                .get();
    }
}
~~~

Here:

| Setting | Meaning |
| --- | --- |
| `messageGroupId(...)` | Identifies Delayer's waiting message group; important when using a persistent store |
| `delayExpression("headers['deliverAt']")` | Reads the absolute `Date` from the header |
| `defaultDelay(1_000L)` | **1-second fallback** if there is no valid deadline per expression rules |
| `scheduled.ready` | Output channel to observe when the message has been released |

**Note on business correctness:** a 1-second fallback is handy for demonstrating the mechanism, but may be inappropriate for a feature that "must send at the scheduled date and time". In a real system, **strictly validate `deliverAt` before sending into Delayer**, and route invalid messages to an error branch. Do not rely on fallback to patch a missing appointment time.

### Producer: accepting local time and sending the message

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Date;

import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public final class ScheduledNotificationPublisher {
    private final MessageChannel input;

    // Pass the "scheduled.in" bean when constructing this class.
    public ScheduledNotificationPublisher(MessageChannel input) {
        this.input = input;
    }

    public boolean schedule(String eventId,
                            String payload,
                            LocalDateTime localTime,
                            ZoneId zone) {
        Instant dueAt = ScheduleTimes.resolveStrict(localTime, zone);

        if (!dueAt.isAfter(Instant.now())) {
            throw new IllegalArgumentException(
                    "Deadline must be in the future");
        }

        if (dueAt.isAfter(Instant.now().plusSeconds(90L * 24 * 3600))) {
            throw new IllegalArgumentException(
                    "Deadline exceeds this example's 90-day limit");
        }

        return input.send(MessageBuilder.withPayload(payload)
                .setHeader("eventId", eventId)
                .setHeader("deliverAt", Date.from(dueAt))
                .setHeader("requestedLocalTime", localTime.toString())
                .setHeader("requestedZoneId", zone.getId())
                .build());
    }
}
~~~

The code sets a 90-day limit **as an example policy**, not a Spring Integration limit. In a real application, compute `Instant.now()` once and check business contracts (customer, reschedule permissions, max deadline, request status). For very distant deadlines, consider a scheduler or schedule repository supporting edit/cancel rather than leaving messages in Delayer for months.

`requestedLocalTime` and `requestedZoneId` are for auditing. The `deliverAt` header is the absolute timestamp used by Delayer for scheduling; those two descriptive input headers do not cause Delayer to change its deadline if time zone rules change later.

## 7. Testing local times, DST, and release

Good tests separate **time zone conversion correctness** from **scheduler behavior**:

1. Test static time calculation results independently of machine speed.
2. Verify Delayer does not release before the deadline and eventually releases within a sufficiently wide timeout.
3. Do not demand millisecond-exact release; the scheduler may release late when the JVM or host is busy.

### 7.1. Unit tests for time zone conversion

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ScheduleTimesTest {

    @Test
    void convertsVietnamLocalTimeToUtcInstant() {
        Instant actual = ScheduleTimes.resolveStrict(
                LocalDateTime.of(2026, 12, 1, 9, 0),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(Instant.parse("2026-12-01T02:00:00Z"), actual);
    }

    @Test
    void rejectsDstGapAndOverlap() {
        ZoneId newYork = ZoneId.of("America/New_York");

        assertThrows(IllegalArgumentException.class, () ->
                ScheduleTimes.resolveStrict(
                        LocalDateTime.of(2026, 3, 8, 2, 30), newYork));

        assertThrows(IllegalArgumentException.class, () ->
                ScheduleTimes.resolveStrict(
                        LocalDateTime.of(2026, 11, 1, 1, 30), newYork));
    }
}
~~~

The two New York tests are illustrated using current 2026 time zone data. Civil rules can be changed by governments; keep the JVM's **tzdb** updated when regions change rules.

### 7.2. Integration test for Delayer

~~~java
import java.time.Instant;
import java.util.Date;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(AbsoluteTimeDelayConfig.class)
class AbsoluteTimeDelayTest {

    @Autowired
    @Qualifier("scheduled.in")
    MessageChannel input;

    @Autowired
    @Qualifier("scheduled.ready")
    PollableChannel ready;

    @Test
    void releasesMessageWhenAbsoluteDeadlineIsReached() {
        Instant deadline = Instant.now().plusMillis(800);

        assertTrue(input.send(MessageBuilder.withPayload("NOTICE-101")
                .setHeader("eventId", "notice-101")
                .setHeader("deliverAt", Date.from(deadline))
                .build()));

        assertNull(ready.receive(100), "Must not release too early");

        Message<?> released = ready.receive(5_000);
        assertNotNull(released, "Message must appear after deadline");
        assertEquals("NOTICE-101", released.getPayload());
        assertEquals("notice-101",
                released.getHeaders().get("eventId"));
        assertFalse(Instant.now().isBefore(deadline),
                "Clock must pass deadline before seeing the message");
    }
}
~~~

The test above uses a deadline roughly 800 ms after send and assumes the host does not stall for several seconds between creating the deadline and sending. Under heavy CI load, widen the deadline gap and timeout to reduce failures from scheduler or VM startup jitter. Do not use `Thread.sleep(...)` as the sole evidence that a message was released.

**Cases to add:** deadline in the past (immediate release), missing or wrong-type `deliverAt` header, message becoming due while the application is restarting, and many messages sharing a deadline causing consumer load spikes.

## 8. Persistence and restarts with absolute deadlines

If Delayer uses a RAM store, pending messages can be lost when the process stops. For critical notifications, substitute a persistent `MessageGroupStore` such as `JdbcMessageStore`, using a stable `messageGroupId`.

Additional configuration snippet in a flow that already has `JdbcMessageStore`:

~~~java
.delay(spec -> spec
        .messageGroupId("notifications.absolute-time.delay.v1")
        .messageStore(jdbcMessageStore)
        .defaultDelay(1_000L)
        .delayExpression("headers['deliverAt']"))
~~~

This is a **configuration snippet**, not a standalone runnable JDBC application: it requires a `DataSource`, Message Store schema, transactions, and complete bean configuration.

Suppose the deadline is `2026-12-01T02:00:00Z`:

| Situation | Expected outcome |
| --- | --- |
| Restart before deadline | Delayer reads the message from store and reschedules for the stored absolute timestamp |
| Restart after deadline | Message is overdue, may be released once recovery completes |
| New server has a different default time zone | `Date`/`Instant` still represent the same instant; display formatting may differ |
| DST rule update occurs during wait | Stored absolute deadline **does not automatically change**; if business requires following the new local time, recalculate intentionally |

Distinguish **preserving an absolute instant** from **preserving the desired future local clock time**. If legislation changes a time zone's offset before the scheduled date, these two goals can conflict. Storing `requestedLocalTime` and `requestedZoneId` helps the application re-evaluate schedules when necessary; Delayer does not automatically resolve changes to business calendar rules.

Persistence does not yet guarantee exactly-once. If the consumer calls an external service successfully but the process crashes before confirmation, retry/recovery can create duplicate side effects. Use a stable `eventId`, an idempotent consumer, and outbox/inbox mechanisms where needed. If two instances read the same store, control schedule ownership and transactions; sharing a database does not automatically guarantee only one instance releases each event.

## 9. Deadlines, Gateway timeouts, and processing errors

**Delayer's deadline** determines when a message becomes eligible for release. **Gateway reply timeout** determines how long the caller waits for a reply; these are two distinct thresholds.

For example, a Gateway waits only 5 seconds while Delayer schedules 30 minutes out: the caller may time out long ago while the message is still waiting in Delayer. A temporary Gateway reply channel is usually unsuitable for notification schedules spanning restarts. Instead, acknowledge receipt of the request, store `eventId`, and deliver results asynchronously or via a queryable status.

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as API
    participant D as Delayer
    participant C as Consumer
    U->>A: Request schedule 09:00 Asia/Ho_Chi_Minh
    A->>A: Convert to Instant/Date, validate
    A->>D: Message + deliverAt + eventId
    A-->>U: Acknowledge receipt
    Note over D: Stored UTC mark reached
    D->>C: Release message
    C-->>A: Record result by eventId
~~~

Errors while Delayer releases downstream can occur after the API has already responded. Spring Integration provides options like `maxAttempts`, `retryDelay`, and `delayedMessageErrorChannel` for release failures; the error flow must record the failed event and decide between retry, dead letter, or manual intervention.

More importantly, a deadline is not a **business expiration**. A reminder that comes due late after downtime might no longer need sending because the customer already paid. Use a Filter or Service Activator **after Delayer** to check the latest state before calling external services.

## 10. Observability: one absolute instant, many display views

Every deadline-related log should include the canonical UTC timestamp:

~~~text
eventId=notification-101
requestedLocalTime=2026-12-01T09:00:00
requestedZoneId=Asia/Ho_Chi_Minh
dueAtUtc=2026-12-01T02:00:00Z
releasedAtUtc=2026-12-01T02:00:00.350Z
releaseLagMs=350
outcome=RELEASED
~~~

The fields above are **application-designed logs**, not all emitted automatically by Spring Integration. A `Date` should be converted to `Instant` when logging to avoid relying on the JVM's time zone:

~~~java
Date dueAt = Date.from(Instant.parse("2026-12-01T02:00:00Z"));
String utc = dueAt.toInstant().toString();

ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
String userView = dueAt.toInstant().atZone(userZone).toString();
~~~

`utc` is the canonical timestamp, whereas `userView` is the presentation for the user. When a specific format is desired, use `DateTimeFormatter` along with the stored `ZoneId`.

Useful metrics:

| Metric | Formula / interpretation | What it detects |
| --- | --- | --- |
| `pendingCount` | Number of messages remaining in the delay group | Excessive backlog |
| `overdueCount` | Number of waiting messages with `dueAtUtc` before current time | Slow scheduler / recovery |
| `releaseLagMs` | `releasedAt - dueAt` | Actual deadline drift |
| `invalidLocalTimeCount` | Number of schedules rejected due to gap/overlap | Data issues or DST policy issues |
| `rescheduledCount` | Number of schedules intentionally adjusted | Time zone, appointment, or business requirement changes |
| `duplicateEventCount` | Number of `eventId` instances redelivered/received again | Retries or multi-instance contention |

A message eligible at `dueAt` can still emerge late due to a busy scheduler, database, host, or consumer. Also measure `consumerStartedAt` and `businessCompletedAt` if you want to control real SLAs rather than only observing Delayer's release mark.

### Common troubleshooting

| Symptom | Causes to check |
| --- | --- |
| Notification is off by exactly 7 hours | Converted `LocalDateTime` to UTC without `Asia/Ho_Chi_Minh`, or assigned wrong time zone |
| Off by one hour in a DST region | DST rules, gap/overlap, outdated time zone database |
| Date in logs differs between two servers | Used `Date.toString()` or default JVM time zone for formatting |
| Message waits an extremely long time | Passed epoch milliseconds as `Long`, interpreted as a relative delay |
| Message released immediately | `Date` is in the past, numeric delay is 0/negative |
| Not released after restart | Non-persistent store, `messageGroupId` changed, recovery or serialization error |
| Message released late after deadline | App downtime, overloaded scheduler, slow DB or downstream |
| Released twice | Retry/recovery/multi-instance; missing idempotency by `eventId` |

## 11. Practice exercises

1. Convert `2026-12-01 09:00 Asia/Ho_Chi_Minh` to `Instant`; verify the result with a unit test.
2. Take the same `09:00` in `Asia/Ho_Chi_Minh` and `America/New_York` on 2026-12-01. Explain why their deadlines differ.
3. Create input `2026-03-08 02:30 America/New_York`. Use `getValidOffsets(...)` to prove this local time does not exist.
4. Create input `2026-11-01 01:30 America/New_York`. List the two valid offsets; propose a selection policy for users.
5. Build a Delayer flow using `headers['deliverAt']`, send `Date.from(Instant.now().plusSeconds(5))`, and measure release lag.
6. Intentionally send epoch milliseconds as a `Long` into the delay header in a test environment. Explain why this is a serious unit error (without waiting for the message to expire).
7. Switch the application to a different JVM time zone in a test environment. Keep `Instant` unchanged and verify the deadline does not shift.
8. Use a persistent store, restart before/after the deadline; explain behavior when the application stops right when release is supposed to occur.
9. Implement the requirement "every day at 09:00 in the user's time zone" and explain why each deadline should be generated from the local calendar rather than adding a fixed 24 hours in UTC.
10. Add a Filter after Delayer to skip expired reminders, even when messages are recovered after downtime.

### Self-check questions

- Why isn't `LocalDateTime` sufficient to identify a point in time globally?
- Does `Date` carry `ZoneId` information? How does it differ from a `Long` delay?
- Why do gaps and overlaps pose risks for schedules based on local clocks?
- Why shouldn't the JVM's default time zone be used as the customer's time zone?
- If a country changes its time zone law in the future, does an already-stored absolute deadline change automatically?
- Why are Gateway `replyTimeout` and Delayer's deadline two independent concerns?
- Which timestamps should be recorded to distinguish late release from late business processing?

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): relative delays, absolute `java.util.Date`, scheduler, and message store.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): declaring `IntegrationFlow`, endpoint configuration, and channels.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): options for persisting pending messages across restarts.
- [Java SE API — java.time](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html): `Instant`, `LocalDateTime`, `ZonedDateTime`, and temporal types.
- [Java SE API — ZoneRules](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html): looking up valid offsets for local times, including DST gaps/overlaps.
