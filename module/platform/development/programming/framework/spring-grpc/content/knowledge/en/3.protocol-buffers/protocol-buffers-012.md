# Timestamp, Duration, and Well-Known Types

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **Timestamp** (representing an absolute point in time) from **Duration** (representing a span of time).
- Declare and import these two well-known types in a proto3 schema.
- Convert accurately between Protobuf and Java **Instant** and **java.time.Duration**.
- Understand bounds, precision, and seconds/nanos normalization rules.
- Recognize how ProtoJSON represents Timestamp and Duration.
- Choose appropriate well-known types and avoid misusing their semantics in Spring gRPC contracts.

## 1. What Are Well-Known Types?

Protocol Buffers provides a standard set of built-in messages called **well-known types (WKT)**. They model common concepts such as timestamps, durations, dynamic data, fields to update, or empty payloads. These types have standard schemas, corresponding Java classes, and well-defined ProtoJSON rules.

The two most commonly used time types:

- **google.protobuf.Timestamp**: a specific point in time on the timeline, measured from the Unix epoch.
- **google.protobuf.Duration**: a span of time that can be positive, negative, or zero.

In **SPRING_GRPC** services, use them to exchange order creation times, expiration times, processing durations, or configured wait intervals. Using standard types keeps representations consistent between Java clients and clients in other languages.

Some other WKTs:

| Type | Purpose |
| --- | --- |
| **google.protobuf.Empty** | Message with no fields, often used when an RPC needs no request/response data. |
| **google.protobuf.FieldMask** | Specifies fields to read or update. |
| **google.protobuf.Any** | Holds a Protobuf message along with a type URL. |
| **google.protobuf.Struct**, **Value**, **ListValue** | Represents dynamically structured data close to JSON. |
| **google.protobuf.StringValue**, **BoolValue**, and other wrappers | Wraps a scalar; common in older schemas before proto3 optional became widespread. |

WKTs are not a single type with one serialization rule. Each type has its own schema and JSON rules. This lesson focuses on Timestamp and Duration.

## 2. Importing Timestamp and Duration in .proto

The standard definitions are provided in the Protobuf library. Import the exact file and use the fully qualified name:

~~~proto
syntax = "proto3";

package learning.orders.v1;

option java_package = "com.example.orders.v1";
option java_multiple_files = true;

import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

message OrderEvent {
  string order_id = 1;
  google.protobuf.Timestamp occurred_at = 2;
  google.protobuf.Duration processing_time = 3;
}
~~~

Do not define your own custom message named Timestamp or Duration to replace a WKT. Using the standard types lets code generators, runtimes, and ProtoJSON understand the intended semantics.

In Java, the two corresponding classes are:

- **com.google.protobuf.Timestamp**
- **com.google.protobuf.Duration**

Conversion and formatting utilities live in the **protobuf-java-util** artifact, such as **com.google.protobuf.util.Timestamps**, **Durations**, and **JsonFormat**. The version of this library must be compatible with the Protobuf runtime version used by the project.

## 3. Timestamp Represents an Absolute Point in Time

Timestamp represents seconds and nanoseconds relative to the **Unix epoch: 1970-01-01T00:00:00Z**. It does not store a local timezone, region name such as **Asia/Ho_Chi_Minh**, or how a user reads a wall clock.

The message has two fields:

| Field | Meaning |
| --- | --- |
| **seconds** | Seconds relative to the Unix epoch. |
| **nanos** | Non-negative fractional nanoseconds, from 0 to 999,999,999. |

Timestamp has **nanosecond** precision. For example, **1970-01-01T00:00:01.250Z** corresponds to **seconds = 1**, **nanos = 250000000**.

Negative values are also normalized with non-negative nanos. For instance, half a second before the epoch:

~~~text
seconds = -1
nanos   = 500000000
~~~

The two components combine to **−0.5 seconds**. Do not represent this case as **seconds = 0**, **nanos = -500000000**; Timestamp rules require nanos to lie in the non-negative range.

### Valid Range

Timestamp supports approximately **0001-01-01T00:00:00Z** to **9999-12-31T23:59:59.999999999Z**:

- **seconds**: from **-62,135,596,800** to **253,402,300,799**.
- **nanos**: from **0** to **999,999,999**.

Not every long value forms a valid Timestamp. When data can arrive from external clients, validate the range instead of merely trusting that the builder succeeded.

## 4. Duration Represents a Span of Time

Duration describes an amount of time between two instants or a configured wait/timeout interval. It is not anchored to a specific start date.

Duration also has two fields:

| Field | Meaning |
| --- | --- |
| **seconds** | Signed seconds portion. |
| **nanos** | Signed nanoseconds portion, having the same sign as seconds unless one of them is 0. |

Examples:

| Span | seconds | nanos |
| --- | ---: | ---: |
| **2.5 seconds** | 2 | 500,000,000 |
| **2 seconds** | 2 | 0 |
| **-1.5 seconds** | -1 | -500,000,000 |
| **-0.5 seconds** | 0 | -500,000,000 |
| **0 seconds** | 0 | 0 |

The same-sign rule keeps Duration in a normalized form. Do not set **seconds = 1** and **nanos = -500000000**; that is not a valid normalized representation of 0.5 seconds.

Duration supports a range of approximately **±10,000 years**:

- **seconds**: from **-315,576,000,000** to **315,576,000,000**.
- **nanos**: from **-999,999,999** to **999,999,999**.
- **seconds** and **nanos** must share the same sign, except when one component is 0.

Duration is not a calendar day/month calculation. A calendar month can have 28, 29, 30, or 31 days; therefore do not convert a month into a fixed Duration if business rules genuinely mean calendar months.

## 5. Declaring and Reading Time Fields

Timestamp and Duration are **message fields**, so they have explicit presence in proto3 without needing the optional label:

~~~proto
import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

message Job {
  string job_id = 1;
  google.protobuf.Timestamp started_at = 2;
  google.protobuf.Timestamp finished_at = 3;
  google.protobuf.Duration timeout = 4;
}
~~~

Java generates methods such as:

- **hasStartedAt()** and **getStartedAt()**.
- **hasFinishedAt()** and **getFinishedAt()**.
- **hasTimeout()** and **getTimeout()**.

When a field is unset, the getter returns a default instance. Default Timestamp is the epoch (**seconds = 0**, **nanos = 0**); default Duration is a 0-second span. Therefore, never use getter values to infer whether the field was sent:

~~~java
Job job = Job.newBuilder().setJobId("job-42").build();

System.out.println(job.hasStartedAt()); // false
System.out.println(job.getStartedAt().getSeconds()); // 0
System.out.println(job.hasTimeout()); // false
System.out.println(job.getTimeout().getSeconds()); // 0
~~~

If the application needs to distinguish “timestamp not provided” from “epoch timestamp”, check **hasStartedAt()**. If it needs to distinguish “timeout not configured” from “zero timeout”, check **hasTimeout()**.

## 6. Converting Timestamp with java.time.Instant

**java.time.Instant** also represents an absolute point in time on the Unix epoch. It is the right Java type for converting to and from **google.protobuf.Timestamp**.

### From Instant to Timestamp

~~~java
import com.google.protobuf.Timestamp;
import com.google.protobuf.util.Timestamps;
import java.time.Instant;

Instant instant = Instant.parse("2026-11-19T08:30:15.123456789Z");

Timestamp timestamp = Timestamp.newBuilder()
    .setSeconds(instant.getEpochSecond())
    .setNanos(instant.getNano())
    .build();

if (!Timestamps.isValid(timestamp)) {
    throw new IllegalArgumentException("Timestamp outside Protobuf range");
}
~~~

**Instant.getNano()** returns the fractional nanoseconds within the second, not total nanoseconds since the epoch. Using **getEpochSecond()** and **getNano()** preserves nanosecond precision.

### From Timestamp to Instant

~~~java
Instant restored = Instant.ofEpochSecond(
    timestamp.getSeconds(),
    timestamp.getNanos());
~~~

You can use **Timestamps.fromMillis(...)** and **Timestamps.toMillis(...)** when the system only needs millisecond precision:

~~~java
Timestamp fromMillis = Timestamps.fromMillis(
    System.currentTimeMillis());

long epochMillis = Timestamps.toMillis(fromMillis);
~~~

Millisecond helpers discard sub-millisecond precision. If data must preserve nanoseconds, convert seconds/nanos directly.

### Timestamp Is Not LocalDateTime

**LocalDateTime** contains no timezone or offset, so it cannot identify an absolute instant on its own. If input is local time, you must know the timezone or offset and convert it to Instant:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local = LocalDateTime.of(2026, 11, 19, 15, 30);
Instant instant = local.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")).toInstant();
~~~

Timestamp stores only the resulting absolute instant. If business logic requires “15:30 local time every day” or a regional schedule, also store the timezone ID and schedule rules; a standalone Timestamp cannot capture that meaning.

## 7. Converting Duration with java.time.Duration

Java **java.time.Duration** represents a time span with seconds and nanoseconds. You can use **Durations** for common values:

~~~java
import com.google.protobuf.util.Durations;

com.google.protobuf.Duration timeout = Durations.fromMillis(1500);
long timeoutMillis = Durations.toMillis(timeout);
~~~

**fromMillis()** fits when input only has millisecond precision. If nanoseconds must be preserved, watch the difference in how negative numbers are normalized between Java and Protobuf.

### Normalizing Negative Durations

Java **java.time.Duration** stores seconds rounded toward negative infinity and a non-negative nano fraction. For example, **java.time.Duration.ofMillis(-500)** has:

~~~java
java.time.Duration javaDuration =
    java.time.Duration.ofMillis(-500);

System.out.println(javaDuration.getSeconds()); // -1
System.out.println(javaDuration.getNano());    // 500000000
~~~

Protobuf Duration requires seconds and nanos to have the same sign. Therefore, do not copy those two values directly into a Protobuf message. Proper conversion:

~~~java
import com.google.protobuf.util.Durations;

static com.google.protobuf.Duration toProtoDuration(
        java.time.Duration value) {

    long seconds = value.getSeconds();
    int nanos = value.getNano();

    // Java represents -0.5s as (-1s, +500ms);
    // Protobuf represents it as (0s, -500ms).
    if (seconds < 0 && nanos > 0) {
        seconds += 1;
        nanos -= 1_000_000_000;
    }

    com.google.protobuf.Duration result =
        com.google.protobuf.Duration.newBuilder()
            .setSeconds(seconds)
            .setNanos(nanos)
            .build();

    if (!Durations.isValid(result)) {
        throw new IllegalArgumentException(
            "Duration outside Protobuf range");
    }
    return result;
}
~~~

In the reverse direction, use **java.time.Duration.ofSeconds(seconds, nanos)**:

~~~java
static java.time.Duration toJavaDuration(
        com.google.protobuf.Duration value) {
    if (!com.google.protobuf.util.Durations.isValid(value)) {
        throw new IllegalArgumentException("Invalid Protobuf Duration");
    }
    return java.time.Duration.ofSeconds(
        value.getSeconds(), value.getNanos());
}
~~~

**Duration.ofSeconds(long, long)** automatically normalizes the nano portion when needed. Checking **Durations.isValid()** beforehand rejects out-of-range or mismatched-sign messages.

## 8. How ProtoJSON Represents Timestamp and Duration

ProtoJSON uses special formats for these two WKTs:

- **Timestamp** is represented as an RFC 3339 string.
- **Duration** is represented as a string ending with the suffix **s**.

Example message:

~~~proto
message Job {
  google.protobuf.Timestamp started_at = 1;
  google.protobuf.Duration timeout = 2;
}
~~~

Corresponding JSON:

~~~json
{
  "startedAt": "2026-11-19T08:30:15.123456789Z",
  "timeout": "1.5s"
}
~~~

Timestamp JSON can accept valid offsets on input, while standard ProtoJSON output uses UTC with the **Z** suffix. Fractional seconds may use 3, 6, or 9 decimal digits depending on the precision required.

Duration JSON uses strings such as:

- **"3s"** for 3 seconds.
- **"1.5s"** for 1.5 seconds.
- **"-0.5s"** for negative half a second.
- **"0s"** for zero duration.

Do not use a JSON number like **1500** in place of Duration in ProtoJSON. The unit and **s** suffix are part of the format.

Java can print and parse using **JsonFormat**:

~~~java
import com.google.protobuf.util.JsonFormat;

String json = JsonFormat.printer().print(job);

Job.Builder builder = Job.newBuilder();
JsonFormat.parser().merge(json, builder);
Job parsed = builder.build();

System.out.println(parsed.hasStartedAt());
System.out.println(parsed.getTimeout().getSeconds());
~~~

If using Jackson or another general-purpose JSON serializer, do not assume the output conforms to ProtoJSON. Use **JsonFormat** when exchanging JSON under a Protobuf contract.

## 9. Other WKTs and Choosing the Right Type

Timestamp and Duration do not replace every date/time type or dynamic structure. Some choices:

| Requirement | Suitable type | Notes |
| --- | --- | --- |
| An absolute point in time | **Timestamp** | UTC instant, stores no timezone ID. |
| A time span or configured timeout | **Duration** | Seconds/nanos, not calendar months. |
| A calendar date without time of day | A dedicated date message, e.g., **google.type.Date** if provided by the ecosystem | Do not force a birthday into a midnight Timestamp if time of day has no meaning. |
| A local schedule with timezone | Message holding local date/time and timezone ID | Must retain timezone rules to compute instants. |
| Time limit by which an RPC must finish | **io.grpc.Deadline** in the gRPC API | Duration can configure a wait interval, but does not replace a call-attached deadline. |
| Measuring elapsed execution time in one process | **System.nanoTime()** | Use a monotonic clock for elapsed time; do not use wall-clock Timestamp. |
| Partial message updates | **FieldMask** | Lists field paths to update. |
| Message payload whose type is unknown at compile time | **Any** | Pairs a type URL with the packed message bytes. |
| Request/response with no data | **Empty** | Standard message with no fields. |

Specifically, **Duration is not a deadline**. In a gRPC client, **io.grpc.Deadline** attaches an expiration time to a specific RPC. A Duration field in a request can serve as a business timeout setting, yet the server still decides how to apply and cap it.

## 10. Example Contract and Time Handling in Spring gRPC

An event with an occurrence timestamp and processing duration:

~~~proto
syntax = "proto3";

package learning.audit.v1;

option java_package = "com.example.audit.v1";
option java_multiple_files = true;

import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

message RecordEventRequest {
  string event_id = 1;
  google.protobuf.Timestamp occurred_at = 2;
  google.protobuf.Duration processing_time = 3;
}
~~~

In Java, the application can validate presence and validity before saving:

~~~java
import com.example.audit.v1.RecordEventRequest;
import com.google.protobuf.util.Timestamps;
import com.google.protobuf.util.Durations;

void validate(RecordEventRequest request) {
    if (request.getEventId().isBlank()) {
        throw new IllegalArgumentException("event_id is required");
    }

    if (!request.hasOccurredAt()) {
        throw new IllegalArgumentException("occurred_at is required");
    }
    if (!Timestamps.isValid(request.getOccurredAt())) {
        throw new IllegalArgumentException("occurred_at is invalid");
    }

    if (request.hasProcessingTime()
            && !Durations.isValid(request.getProcessingTime())) {
        throw new IllegalArgumentException("processing_time is invalid");
    }
}
~~~

**occurred_at** is a message field so it has **hasOccurredAt()** even without declaring optional. The example requires the occurrence timestamp at the business layer; the Protobuf schema itself does not enforce the field's presence.

Do not trust a Timestamp from a client merely because its range is valid. If timestamps affect business ordering, replay protection, or access control, the server must also validate allowed clock skew, time source, and business rules. A structurally valid Timestamp does not prove the client's clock is accurate.

## 11. Testing Conversions and Time Boundaries

Cases to test:

1. Timestamp with nanoseconds round-trips through Java and binary without precision loss.
2. Timestamp before the Unix epoch to verify seconds/nanos normalization.
3. Negative Duration with fractional seconds, especially **-0.5s**.
4. Out-of-range or mismatched-sign Timestamp/Duration values are rejected.
5. ProtoJSON uses RFC 3339 for Timestamp and the **s** suffix for Duration.
6. Absent message field differs from a field set to the default instance.

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.protobuf.Timestamp;
import com.google.protobuf.util.Timestamps;
import com.google.protobuf.util.Durations;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class TimeTypesTest {
    @Test
    void preservesNanosecondsInTimestamp() throws Exception {
        Instant instant =
            Instant.parse("2026-11-19T08:30:15.123456789Z");

        Timestamp source = Timestamp.newBuilder()
            .setSeconds(instant.getEpochSecond())
            .setNanos(instant.getNano())
            .build();

        Timestamp parsed = Timestamp.parseFrom(source.toByteArray());
        assertTrue(Timestamps.isValid(parsed));
        assertEquals(instant.getEpochSecond(), parsed.getSeconds());
        assertEquals(123456789, parsed.getNanos());
    }

    @Test
    void validatesNegativeDurationNormalization() {
        java.time.Duration javaValue =
            java.time.Duration.ofMillis(-500);

        com.google.protobuf.Duration protoValue =
            toProtoDuration(javaValue);

        assertEquals(0, protoValue.getSeconds());
        assertEquals(-500000000, protoValue.getNanos());
        assertTrue(Durations.isValid(protoValue));
        assertEquals(javaValue, toJavaDuration(protoValue));
    }
}
~~~

The **toProtoDuration()** and **toJavaDuration()** methods in the test are the conversion helpers shown in section 7. In a real project, place them in a shared mapper class and also test the ±10,000-year boundaries.

## 12. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using Timestamp for a time span | Unclear which start/end instants produced the value | Use **Duration**. |
| Using Duration for calendar months | A month has no fixed number of seconds | Use a calendar/date type and appropriate timezone. |
| Treating Timestamp as local time | Misinterpreted when clients are in different timezones | Convert local time to Instant with an explicit timezone. |
| Converting only via milliseconds | Loses microsecond/nanosecond precision | Convert seconds and nanos directly when high precision is needed. |
| Copying negative seconds/nanos directly from Java Duration | Produces a Protobuf Duration violating sign rules | Normalize first and validate with **Durations.isValid()**. |
| Ignoring **hasXxx()** | Confuses an absent field with the epoch or zero duration | Check message field presence. |
| Treating a valid Timestamp as trustworthy time | Clients can send skewed timestamps | Enforce server-side time policies. |
| Using Duration instead of gRPC Deadline | Does not directly bound RPC lifecycle | Set deadlines on client calls using the gRPC API. |

## 13. Practice Exercise

A task processing service needs to store request receipt time, completion time, and processing duration:

~~~proto
import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

message TaskTiming {
  string task_id = 1;
  google.protobuf.Timestamp received_at = 2;
  google.protobuf.Timestamp completed_at = 3;
  google.protobuf.Duration processing_time = 4;
}
~~~

Tasks:

1. Explain why **received_at** and **completed_at** are Timestamps, while **processing_time** is a Duration.
2. Construct two Timestamps from **java.time.Instant** with nanosecond precision.
3. Convert **java.time.Duration.ofMillis(-500)** to Protobuf Duration and prove seconds/nanos share the same sign.
4. Export the message to ProtoJSON, identifying the RFC 3339 format and the **s** suffix.
5. Test the case where **completed_at** is unset versus set to the epoch Timestamp.
6. Explain why measuring elapsed runtime within one process should use a monotonic clock, whereas event timestamps need Timestamp.
7. Describe how to apply a gRPC Deadline if a client allows an RPC to run for at most a configured duration.

**Completion criteria:** choose accurate time semantics, convert in Java without unintended precision loss, normalize negative Durations, validate presence/validity, and distinguish WKTs from gRPC's deadline API.

## 14. Key Takeaways

- **Timestamp** is an absolute point in time measured from the Unix epoch; **Duration** is a signed time span.
- Both use seconds and nanos, yet follow different normalization rules and value ranges.
- Timestamp maps well to **java.time.Instant**; Duration maps to **java.time.Duration** with care for negative normalization.
- ProtoJSON represents Timestamp as an RFC 3339 string and Duration as a string ending in **s**.
- Timestamp/Duration are message fields and therefore have presence; use **hasXxx()** to distinguish absent fields from default values.
- **Duration does not replace io.grpc.Deadline**; use the right API for measuring time versus bounding an RPC.
- Use standard WKTs instead of inventing custom time messages whenever semantics align.

Using Timestamp, Duration, and well-known types properly keeps Protocol Buffers contracts consistent between Java and other clients, while avoiding timezone, precision, and time-interpretation bugs in Spring gRPC services.
