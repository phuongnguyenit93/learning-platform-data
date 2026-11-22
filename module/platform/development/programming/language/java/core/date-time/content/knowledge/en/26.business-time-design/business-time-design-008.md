# Naming Fields and Parameters to Express Units, Time Zones, and Meaning

## 1. Temporal Names Are Part of the Contract

Consider a method:

```java
void configure(long time, int offset);
```

This illustrative signature leaves too many questions:

- Is `time` an instant in time or a wait duration?
- If it is a numeric time value, is the unit seconds, milliseconds, or nanoseconds?
- Is `offset` a UTC offset, a schedule shift duration, or a pagination position?
- Which zone is the value tied to, and is a zone needed to interpret it?

A clear name does not replace all documentation, but it saves callers from having to guess the basics. For temporal data, good naming requires coordinating **business meaning, data type, unit, and zone context**.

There is no need to cram every piece of information into every name. If the type already expresses part of it clearly, the name should focus on the remaining meaning. For example, `Duration requestTimeout` already tells you it is a duration; you do not have to rename it to a long name listing seconds and nanoseconds.

## 2. Before Naming, Identify the Kind of Information

| What to represent | Common suitable type | Suggested name |
| --- | --- | --- |
| When an event actually occurred | `Instant` | `occurredAt` |
| When the system received an event | `Instant` | `receivedAt` |
| Business delivery date | `LocalDate` | `deliveryDate` |
| Opening hour on a local clock | `LocalTime` | `openingLocalTime` |
| Local date-time not yet resolved to an instant | `LocalDateTime` | `scheduledLocalDateTime` |
| Zone used for a schedule | `ZoneId` | `scheduleZone` |
| Specific UTC offset | `ZoneOffset` | `utcOffset` |
| Maximum wait duration | `Duration` | `requestTimeout` |
| Deadline as an absolute point in time | `Instant` | `requestDeadline` |
| Year-month period | `YearMonth` | `reportingPeriod` |

[Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) represents a point on the timeline. [LocalDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html) has no time zone or offset, so it does not uniquely identify an instant. Merely renaming a `LocalDateTime` variable to `eventInstant` does not create the missing information.

Names must be honest with the actual type and data. If the domain requires an instant, choose the appropriate type and conversion step instead of using an instant-sounding name for data that is still ambiguous.

The `At`, `Date`, and `LocalTime` suffixes in this article are consistent suggestions, not mandatory Java rules. A project may choose different conventions as long as they are used clearly and consistently.

## 3. For Integers, State the Unit Explicitly

### 3.1. long Does Not Carry a Unit

Both of the following values are `long`, yet they differ by a factor of one thousand:

```java
long occurredAtEpochSeconds = 1_704_067_200L;
long occurredAtEpochMillis = 1_704_067_200_000L;
```

Both can represent the same instant `2024-01-01T00:00:00Z` when passed to the right conversion method:

```java
Instant a = Instant.ofEpochSecond(occurredAtEpochSeconds);
Instant b = Instant.ofEpochMilli(occurredAtEpochMillis);
```

If both are named `timestamp`, the `long` type cannot help the compiler catch passing the wrong one. The name `occurredAtEpochMillis` simultaneously states:

- This is when the event occurred, not when it was received.
- This is a count from the epoch per the contract.
- The unit is milliseconds.

Naming is only one layer of defense. At data-reading boundaries, you still need to validate value ranges and source contracts, rather than guessing the unit by counting the digits of an arbitrary number.

### 3.2. Use Unit Suffixes with Clear Meaning

| Ambiguous name | Clearer name if still using numbers |
| --- | --- |
| `timeout` | `requestTimeoutMillis` |
| `delay` | `retryDelaySeconds` |
| `timestamp` | `occurredAtEpochMillis` |
| `nano` | `nanoOfSecond` or `elapsedNanos` depending on meaning |
| `offset` | `utcOffsetSeconds` if actually storing an offset in seconds |
| `ttl` | `sessionTtlSeconds` if it is a duration in seconds |

Do not attach a `Millis` suffix to a number that actually holds seconds. When changing units, you must change the calculation as well as the name and contract. Changing the name alone can make bugs harder to spot because callers will trust the new name.

For nanoseconds, distinguish `nanoOfSecond` (the component within a second) from a total duration in nanoseconds. A number like `123_456_789` may be the nanosecond part of the current second, not an independent instant.

### 3.3. Convert to a Duration Type Early at the Boundary

In business code, a numeric configuration can be converted into a `Duration`:

```java
Duration requestTimeout = Duration.ofMillis(requestTimeoutMillis);
```

[Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html) models a duration in seconds and nanoseconds. It lets internal methods accept a meaningful quantity rather than a bare `long`.

The conversion parameter name should state the input unit clearly, such as `requestTimeoutFromMillis(long requestTimeoutMillis)`. After conversion, `requestTimeout` is clear enough because the `Duration` type already conveys duration.

Value validation is still required. `Duration` can be negative; whether a negative timeout is accepted is an application contract. The example in this article accepts only positive timeouts.

## 4. Distinguish Duration, Calendar Days, and Deadlines

A name like `retentionDays` may still be unclear: does "days" mean individual days on a local calendar or exact 24-hour blocks?

| Meaning | Suggested expression |
| --- | --- |
| Retain for exactly 72 elapsed hours | `Duration retentionDuration` |
| Add three days on the business calendar | `int retentionCalendarDays` with zone/date policy |
| Determined expiration instant | `Instant expiresAt` |
| Business expiration date | `LocalDate expirationDate` |

`Duration.ofDays(1)` is a duration of exactly 24 hours per the API contract. It does not by itself express "the same local time on the next calendar day" in a zone with daylight saving transitions.

Similarly:

- `requestTimeout` is an amount of time.
- `requestDeadline` is an instant in time.
- `processingDelay` is a shift amount.
- `scheduledAt` is a decided instant in time.

Do not name a `Duration` `deadline`, because callers may interpret it as an absolute point in time. Do not name an `Instant` `timeoutMillis`, because that name claims both a different meaning and a different representation type.

If a method needs to compute an expiration from a starting point, a clearer signature is:

```java
Instant calculateExpiry(
        Instant activatedAt,
        Duration validityDuration);
```

This is an illustrative signature. Rules for negative, zero, or out-of-range `validityDuration` values must be defined in the implementation. Good names reveal the roles, while input validation enforces that contract.

## 5. Time Zones: Name by Role, Not by Host Environment

[ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html) can represent a region with rules such as `Europe/Berlin` or a fixed offset. `ZoneOffset` represents a specific UTC offset.

Names with clear roles:

| Name | Intended meaning |
| --- | --- |
| `businessZone` | Zone used to determine business dates |
| `scheduleZone` | Zone tied to a local schedule |
| `displayZone` | Zone used when displaying an instant |
| `sourceOffset` | Offset provided by the source |
| `utcOffset` | Specific UTC offset |

`zone` may be sufficient in a small method with a single role. When there are two zones—such as source/target or display/business—distinguish them by name.

Do not use `serverZone` as an implicit substitute for `businessZone`. Where the current server happens to run does not determine which zone the business unit uses to partition dates.

Naming an integer `timezone` does not clarify whether it is in hours or seconds, nor does it represent zone rules. If the data is actually a zone identifier string, `zoneId` or `scheduleZoneId` is clearer.

Do not use ambiguous abbreviations in place of a full zone contract. A current offset is also not enough to replace a zone name for a recurring schedule that must follow future rule changes.

### 5.1. Instant Usually Does Not Need a Utc Suffix to Be Meaningful

`Instant occurredAt` already represents an absolute point in time, with no separate display zone inside the object. There is no need to rename everything to `occurredAtUtcInstant` by default.

At an API boundary, if you need to emphasize that a string must use the UTC format ending in `Z`, document that representation rule and enforce it in the converter. The name `occurredAtUtc` only helps if the data actually conforms; it does not validate the string by itself.

In particular, `LocalDateTime createdAtUtc` is only an out-of-type promise. That type does not carry an offset; if you need to store a true instant, consider `Instant` instead of relying on the name alone.

### 5.2. LocalDate Does Not Carry a Zone, but Can Be Derived Using One

A `LocalDate businessDate` does not contain a zone. However, if it is computed from an `Instant`, the calculation requires the business zone:

```java
LocalDate businessDate =
        occurredAt.atZone(businessZone).toLocalDate();
```

The name `businessDate` states that this is a business date, not a default UTC date. If you need to preserve how it was derived, you must also store or pass the corresponding zone/rule; the name itself cannot recover discarded data.

Conversely, a birth date or a user-entered date may be meaningful as a pure calendar date, not necessarily derived from an `Instant`. Do not force a time zone into every `LocalDate` field when the domain does not require one.

## 6. Name According to the Event That Occurred

A system that receives and processes events may have multiple timestamps:

| Field | Meaning to establish |
| --- | --- |
| `occurredAt` | When the source reports the event occurred |
| `receivedAt` | When the system received the event |
| `processedAt` | When the system finished the processing step |
| `persistedAt` | Storage recording instant per the chosen contract |
| `scheduledAt` | Planned instant |
| `startedAt` | Actual start instant |
| `completedAt` | Actual completion instant |

If everything is named `timestamp` or `time`, it is hard to tell which instant is used for latency reporting, which is used for date partitioning, and which is supplied by the source.

Names should also help distinguish planned from actual times. `scheduledStartAt` and `actualStartAt` may be appropriate when both appear together. Do not write a planned time into `completedAt` just because no completion instant exists yet.

The clock source is part of what needs to be documented. `occurredAt` sent by a device may not be synchronized with `receivedAt` recorded by a server. Clear names help identify the two sources, but do not guarantee they are always in chronological order. Do not infer causality or reliable latency from field names alone.

## 7. Boundaries Must Clearly State Inclusive or Exclusive

The names `start` and `end` do not indicate whether data exactly at `end` belongs to the range.

For a half-open interval, you can use:

```java
Instant fromInclusive;
Instant toExclusive;
```

or a type with clearer business meaning:

```java
record ValidityWindow(
        Instant activeFromInclusive,
        Instant expiresAtExclusive) {}
```

The record above only illustrates naming; the complete program below adds validation and methods.

The contract `[activeFromInclusive, expiresAtExclusive)` clearly states:

- At the exact start instant, it is valid.
- Immediately before the end instant, it is valid.
- At the exact end instant, it is expired.

A common name like `expiresAt` still works if the entire system clearly defines that exact instant as expired. The `Exclusive` suffix is useful where endpoints could be confused or when a method handles multiple interval types.

Do not let names and operators contradict each other. A variable named `toExclusive` used with `<=` creates a broken contract right in the code.

For dates, use `LocalDate startDateInclusive`/`endDateExclusive` when you need to distinguish the interval style clearly. Do not pass a date into an `Instant` parameter by arbitrarily assigning `00:00` in an unspecified zone.

## 8. Complete Java 17+ Program

Save as `TemporalNamingDemo.java`. The example uses fixed values to focus on name and type contracts.

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public class TemporalNamingDemo {
    record ValidityWindow(
            Instant activeFromInclusive,
            Instant expiresAtExclusive) {

        ValidityWindow {
            Objects.requireNonNull(activeFromInclusive);
            Objects.requireNonNull(expiresAtExclusive);
            if (expiresAtExclusive.isBefore(activeFromInclusive)) {
                throw new IllegalArgumentException("Reversed validity window");
            }
        }

        boolean isActiveAt(Instant checkedAt) {
            Objects.requireNonNull(checkedAt);
            return !checkedAt.isBefore(activeFromInclusive)
                    && checkedAt.isBefore(expiresAtExclusive);
        }
    }

    static Duration requestTimeoutFromMillis(long requestTimeoutMillis) {
        if (requestTimeoutMillis <= 0) {
            throw new IllegalArgumentException("Timeout must be positive");
        }
        return Duration.ofMillis(requestTimeoutMillis);
    }

    static LocalDate businessDateOf(
            Instant occurredAt, ZoneId businessZone) {
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(businessZone);
        return occurredAt.atZone(businessZone).toLocalDate();
    }

    public static void main(String[] args) {
        Instant occurredAt = Instant.parse("2024-01-01T00:00:00Z");
        long occurredAtEpochSeconds = occurredAt.getEpochSecond();
        long occurredAtEpochMillis = occurredAt.toEpochMilli();

        System.out.println("epoch seconds = " + occurredAtEpochSeconds);
        System.out.println("epoch millis = " + occurredAtEpochMillis);
        System.out.println("correct seconds conversion = "
                + Instant.ofEpochSecond(occurredAtEpochSeconds));
        System.out.println("correct millis conversion = "
                + Instant.ofEpochMilli(occurredAtEpochMillis));
        System.out.println("wrong unit conversion = "
                + Instant.ofEpochMilli(occurredAtEpochSeconds));

        Duration requestTimeout = requestTimeoutFromMillis(90_000);
        Instant requestDeadline = occurredAt.plus(requestTimeout);
        System.out.println("request timeout = " + requestTimeout);
        System.out.println("request deadline = " + requestDeadline);

        ValidityWindow window = new ValidityWindow(
                occurredAt, requestDeadline);
        System.out.println("active at start = "
                + window.isActiveAt(occurredAt));
        System.out.println("active just before expiry = "
                + window.isActiveAt(requestDeadline.minusNanos(1)));
        System.out.println("active at expiry = "
                + window.isActiveAt(requestDeadline));

        Instant lateEventOccurredAt =
                Instant.parse("2024-01-01T23:30:00Z");
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        System.out.println("UTC calendar date = " + businessDateOf(
                lateEventOccurredAt, ZoneId.of("UTC")));
        System.out.println("business date = " + businessDateOf(
                lateEventOccurredAt, businessZone));
        System.out.println("business zone ID = " + businessZone.getId());
    }
}
```

Compile and run:

```shell
javac --release 17 TemporalNamingDemo.java
java TemporalNamingDemo
```

Stdout:

```text
epoch seconds = 1704067200
epoch millis = 1704067200000
correct seconds conversion = 2024-01-01T00:00:00Z
correct millis conversion = 2024-01-01T00:00:00Z
wrong unit conversion = 1970-01-20T17:21:07.200Z
request timeout = PT1M30S
request deadline = 2024-01-01T00:01:30Z
active at start = true
active just before expiry = true
active at expiry = false
UTC calendar date = 2024-01-01
business date = 2024-01-02
business zone ID = Asia/Ho_Chi_Minh
```

Points to observe:

- The two epoch variables have different units, yet passing each to the matching method yields the same instant.
- Passing seconds to `ofEpochMilli` still compiles and runs, but produces a wrong instant in 1970. Clear naming and boundary conversion help prevent this mistake.
- `requestTimeout` is a `90`-second duration; `requestDeadline` is a specific `Instant`.
- `ValidityWindow` enforces the endpoint contract and does not treat the expiration instant itself as active.
- An event at `23:30Z` has a UTC date of Jan 01, whereas its business date in the example's `Asia/Ho_Chi_Minh` zone is Jan 02.

Names do not create these rules, but they make them visible in the code and help verification choose the right test cases.

## 9. APIs, Configuration, and Schemas Must Preserve the Same Meaning

### 9.1. Data Transfer Boundaries Should Declare the Representation

If an API uses numbers:

```json
{
  "occurredAtEpochMillis": 1704067200000,
  "requestTimeoutMillis": 90000
}
```

If an API uses instant strings:

```json
{
  "occurredAt": "2024-01-01T00:00:00Z"
}
```

These are two representations with different contracts. You must specify fractional seconds, offset/UTC requirements, and how invalid input is handled. Naming a string `occurredAt` does not by itself mean every format is accepted.

Do not silently change a field from seconds to milliseconds while keeping the old contract. API consumers may keep sending data matching the previous documentation and get wrong results instead of a clear error.

If you must rename or change the representation type of a published API, you need a compatibility or versioning strategy. If both old and new fields are supported during a transition period, you must define how conflicts are handled when both are present; do not silently pick one at random.

### 9.2. Numeric Configuration Must Include Units

Configuration names like `request-timeout-ms` or `request-timeout-millis` state the unit when the format only accepts numbers. If the format allows a self-describing duration such as `PT1M30S`, document the accepted syntax and parse it into a `Duration`.

A configuration entry `timeout=90` does not say whether it is seconds or milliseconds. The unit belongs in the name, syntax, or clearly published schema—ideally not only in the author's memory.

### 9.3. Column Names Do Not Replace Column Types

A column named `created_at` does not prove what time zone or precision it has. A column named `expires_at_epoch_millis` must actually store the published unit.

Java code, DTOs, API documentation, SQL queries, and migrations must agree. If a column only stores microseconds while the API keeps nanoseconds, truncation/rounding or rejection rules must be part of the contract; a name suffix does not solve precision by itself.

Do not slap a `_utc` suffix onto a local column and assume time zone bugs are fixed. You must check the actual values, column type, and how the driver maps them.

## 10. Null, State, and Missing-Data Meanings

A `completedAt` field may be absent because the task has not finished yet. A missing `expiresAt` field may mean never expires, not yet determined, or not yet configured. Those three meanings are not automatically the same.

Names and types can work alongside a state model:

- If `null` means not yet completed, state its relationship to the task status explicitly.
- If "never expires" is a real domain option, express that choice explicitly instead of using a "very far" fake date.
- If an instant is required, reject missing data at the boundary instead of defaulting to epoch or the current time.

Do not name a field `optionalDate` without saying what date it is. The word "optional" only describes that it may be absent, not its business meaning. `deliveryDate` with a clear absence contract is usually easier to understand.

## 11. Clear Names Still Need Types and Guard Checks

A method `sendAfterMillis(long delayMillis)` is clearer than `send(long time)`, yet callers can still pass seconds by mistake. Where possible, use `Duration` internally and only accept raw integers at boundaries that require compatibility.

When there are multiple quantities of the same type whose positions are easy to swap, you can create a meaningful record instead of a long parameter list. For example, `ValidityWindow` groups both endpoints and validates their order once.

However, there is no need to create a separate class for every short-lived temporal variable. Weigh the risk of confusing meanings, how many places use it, and the benefit of enforcing invariants/constraints.

Long names are not automatically better than short ones. In a small method handling a single `LocalDate`, `date` may be clear enough. In a method dealing with a delivery date, a reporting date, and a receipt date, full role-based names become much more important.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Every field is named `timestamp` | Unknown which business milestone it is | Name by event: `occurredAt`, `receivedAt`, etc. |
| `long` without a unit | Seconds and milliseconds get mixed up | State epoch and unit at boundaries |
| Naming a `LocalDateTime` `instant` | Name promises more than the data holds | Use the right type or state local explicitly |
| Naming a duration `deadline` | Confuses a wait amount with an absolute point | Distinguish `Duration` and `Instant` |
| `days` without saying calendar or 24 hours | Wrong addition across DST transitions | State calendar vs. duration contract |
| Changing unit by updating only value or only name | Data mismatch across layers | Update and verify the entire contract |
| Using `offset` for multiple meanings | Confuses UTC offset with shift amount | Name by role and type |
| Using server zone for business dates | Dates shift with host environment | Pass `businessZone` explicitly |
| `toExclusive` but filtering inclusively | Off-by-one results at the boundary | Align name with operator |
| Using epoch or a far-future date as a missing signal | Mixes real values with state | Model missing state explicitly |

## 13. Self-Verification and Practice

1. Refactor the signature `configure(long time, int offset)` into two signatures for two different purposes: configuring a timeout and scheduling a local time. Choose the right types, not just new names.
2. Identify the bug when receiving `1704067200` into a variable named `occurredAtEpochMillis`. Explain why digit count can only be a clue to investigate, not a substitute for the source contract.
3. Design three separate fields for when an event occurred, was received, and was processed. State the clock source for each field.
4. Name the endpoints for a half-open reporting interval and write the condition that checks the endpoints accurately.
5. Describe the difference between `LocalDate expirationDate` and `Instant expiresAt`. What additional information is needed to convert from the date to the expiration instant?
6. Convert a numeric millisecond configuration to `Duration` at the boundary. Check negative values, zero, and values exceeding the application's allowed range.
7. For an event near UTC midnight, check the business date in two different zones and explain the zone parameter names in the method signature.
8. Design an API using epoch numbers and an API using instant strings. Clearly declare units/format, fractional seconds, and invalid-input handling.
9. Define the meaning of `null` for `expiresAt`. If both "never expires" and "not yet determined" exist, do not merge them just because both lack an `Instant`.
10. Review a method with multiple date-time parameters: for each parameter, identify the kind of information, business role, unit if any, interpretation zone, and endpoint convention. Any unclear parts are what need fixing in the contract.

A good temporal name tells readers what data they are holding and how they must use it. Combining business-oriented names with appropriate Java types, explicit boundary conversions, and constraint checks significantly reduces bugs that the compiler cannot catch on its own from bare numbers or strings.
