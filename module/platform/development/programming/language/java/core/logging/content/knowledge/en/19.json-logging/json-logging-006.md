# The timestamp Field in Java JSON Logging

## 1. What is a timestamp in a JSON log record?

In **JSON logging** for **Java Core Logging**, the **timestamp field** indicates **the point in time when a log event was recorded**. It helps operators query by time, correlate events belonging to the same request, investigate root causes of incidents, and observe latency between the log source and the collection system.

Example:

~~~json
{
  "timestamp": "2026-11-09T08:15:30.125Z",
  "level": "INFO",
  "service": "catalog",
  "event": "order.accepted",
  "orderId": "ORD-17"
}
~~~

Here, **timestamp** is a point in time in **UTC**, represented down to **milliseconds**; **Z** indicates a UTC offset of 0. The other fields explain which event occurred, in which service, and at what level. The timestamp answers *when*, though it does not by itself explain *why*.

If all services share the same timestamp contract, dashboards and collectors can:
- Filter logs within a time range.
- Build a relative timeline across records.
- Measure ingest lag or detect late-arriving events.
- Correlate logs with metrics, traces, and business milestones.
- Detect an event far in the future or past caused by a wrong clock or parser.

**Key takeaway:** a timestamp must represent a **meaningful instant**, not just a human-readable date-time string. A string missing an offset such as **2026-11-09 15:15:30** can be interpreted differently on machines with different timezones.

## 2. JSON has no dedicated time type

JSON only has **string, number, boolean, null, array, and object** types; it has no dedicated **Date/Instant** type. Therefore, a timestamp field in logs typically uses:

**A string with an explicit offset:**

~~~json
{"timestamp":"2026-11-09T08:15:30.125Z"}
~~~

**A number counting Unix epoch milliseconds:**

~~~json
{"timestampEpochMs":1794212130125}
~~~

Both represent **2026-11-09T08:15:30.125Z**, but they have **different JSON types and parser rules**.

There is no single mandatory key name across all log platforms. Some schemas use **timestamp**, while others use **@timestamp**, **time**, **eventTime**, or another field. The chosen name must match the schema of the application, codec, and search system.

**Do not change the type of the same key across version upgrades.** For example:

~~~json
{"timestamp":"2026-11-09T08:15:30.125Z"}
~~~

is completely different from:

~~~json
{"timestamp":1794212130125}
~~~

Both are valid JSON, but a dashboard or index mapping configured for a string may reject a number. If you want to emit both formats, use two clearly named keys, compute them from **the same Instant**, and test for consistency.

## 3. ISO 8601, RFC 3339, and UTC Z

The string:

~~~text
2026-11-09T08:15:30.125Z
~~~

has the following components:

~~~text
2026 - 11 - 09 T 08 : 15 : 30 . 125 Z
 year month day   hour minute sec millis UTC
~~~

It is the standard offset-aware time format commonly used in JSON, belonging to the **ISO 8601** family and conforming to the **RFC 3339** timestamp representation.

Another valid example:

~~~text
2026-11-09T15:15:30.125+07:00
~~~

The two strings above refer to **the exact same instant**, because **15:15 at offset +07:00** equals **08:15 UTC**. Changing the offset does not change the instant.

| String | Remarks |
| --- | --- |
| **2026-11-09T08:15:30Z** | Includes UTC, no fractional seconds |
| **2026-11-09T08:15:30.125Z** | UTC, three fractional second digits |
| **2026-11-09T15:15:30.125+07:00** | Different offset, same instant |
| **2026-11-09T08:15:30** | Missing offset, insufficient to determine an instant |
| **2026-11-09 08:15:30** | Not a complete RFC 3339 timestamp |
| **11/09/2026 08:15:30** | Ambiguous day/month order and locale-dependent |

A simple policy for multi-service systems is to **store the instant in UTC with Z**, then convert to local time at display time. There is no need to alter the instant in log files to match a user's timezone.

### Do not confuse offset with ZoneId

- **Offset** such as +07:00 is a fixed difference relative to UTC.
- **ZoneId** such as Asia/Ho_Chi_Minh or America/New_York includes historical rules and regional Daylight Saving Time (DST) transitions where applicable.
- **Instant** is an absolute point on the timeline, without local calendar context.

Do not use a fixed offset as a substitute for all instants in a region with DST. Logs should keep the instant as the source of truth, while regional timezones are used for UI or reporting.

## 4. Event time and ingestion time are two different concepts

In a logging pipeline:

~~~text
Java code emits LogEvent
    |
    | timestamp = time when the event was recorded
    v
Logger / Formatter / Async queue
    |
    v
Console/File/Network Appender
    |
    v
Agent / Collector
    | observedAt = when the collector saw the event
    v
Parser / Queue / Storage
    | indexedAt = when the data was written to the index
    v
Dashboard / Alert
~~~

Example:

~~~json
{
  "timestamp": "2026-11-09T08:15:30.125Z",
  "observedAt": "2026-11-09T08:15:31.000Z",
  "event": "order.accepted"
}
~~~

Here **timestamp** is the event time; **observedAt** is the collection time. The difference can be caused by **I/O, buffering, network, queues, or a slow collector**.

**Do not generate the timestamp with Instant.now() at formatting time or in an async worker** if you want to know when the event occurred. An event enqueued at 08:15:30 but written out at 08:15:35 will be off by 5 seconds if the Formatter discards the LogEvent's time and reads the clock again.

Conversely, if logs arrive late from a device or the device's clock is wrong, **event time** may not be fully trustworthy. You can additionally retain **ingestion/observed time** for investigation. Use clear field names and avoid generic ones like time1/time2.

## 5. Precisions: seconds, millis, micros, nanos

The same second:

~~~text
2026-11-09T08:15:30Z
2026-11-09T08:15:30.125Z
2026-11-09T08:15:30.125456Z
2026-11-09T08:15:30.125456789Z
~~~

| Display resolution | Fractional second digits | Use case |
| --- | --- | --- |
| Seconds | 0 | Infrequent jobs, basic applications |
| Milliseconds | 3 | Most application logs and dashboards |
| Microseconds | 6 | Multiple events occurring within one millisecond |
| Nanoseconds | 9 | When both timestamp source and backend support it |

**Display resolution does not equal actual clock accuracy.** A timestamp with nine digits does not prove the clock is truly accurate to the nanosecond.

In Java 17:

- **Instant** represents seconds plus a nanosecond adjustment.
- **java.util.logging.LogRecord.getInstant()** preserves the timestamp as an Instant.
- **LogRecord.getMillis()** only returns epoch milliseconds, discarding sub-millisecond precision.
- **DateTimeFormatterBuilder.appendInstant(3)** outputs UTC with three fractional second digits.
- **DateTimeFormatter.ISO_INSTANT** formats in UTC, but the fractional length can vary depending on the value.

Align precision across the **schema**, backend, and collector. Do not artificially inflate precision just to show more digits if the clock source does not provide that information.

## 6. Unix epoch: the unit must be explicit

The **Unix epoch** starts at **1970-01-01T00:00:00Z**. The same example instant:

~~~text
UTC string:       2026-11-09T08:15:30.125Z
epoch seconds:    1794212130.125
epoch millis:     1794212130125
epoch micros:     1794212130125000
epoch nanos:      1794212130125000000
~~~

Field names should express the unit:

| Field name | Type/meaning |
| --- | --- |
| timestamp | UTC ISO/RFC 3339 String |
| timestampEpochSeconds | Number of seconds since epoch |
| timestampEpochMs | Number of milliseconds since epoch |
| timestampEpochUs | Number of microseconds |
| timestampEpochNs | Number of nanoseconds or String per policy |

If a receiving system treats **1794212130125** as **seconds** instead of **milliseconds**, the time will be off by a factor of 1000. This is a very common integration bug.

**Warning about JavaScript/JSON numbers:** modern epoch nanosecond values have 19 digits, exceeding the IEEE-754 double exact integer limit of **2^53 - 1**. Do not assume every JSON parser preserves 64-bit integers. If end-to-end nanoseconds are required, consider a String, seconds + nanoseconds, or a data type/log platform with explicit support.

In production, emitting both a string and an epoch number is not mandatory. If you keep both for querying convenience, compute them from **the same Instant** so there is no drift from two separate clock reads.

## 7. Java time APIs to use for timestamps

| Java type | Role |
| --- | --- |
| **Instant** | Absolute point in time; best suited for event time |
| **OffsetDateTime** | Time with an offset; useful when parsing sources with +07:00 |
| **ZonedDateTime** | Regional time with DST rules; suitable for calendar display |
| **LocalDateTime** | Date and time without offset/zone; should not be used alone for cross-machine log timestamps |
| **Clock** | Swappable clock source for testing |
| **Duration** | A span of time, not a timestamp |

Converting an offset to UTC:

~~~java
Instant fromUtc = Instant.parse("2026-11-09T08:15:30.125Z");
Instant fromOffset =
        OffsetDateTime.parse("2026-11-09T15:15:30.125+07:00")
                .toInstant();
System.out.println(fromUtc.equals(fromOffset));
~~~

This is a snippet requiring imports for **java.time.Instant** and **OffsetDateTime**. The output is:

~~~text
true
~~~

### Clock.fixed for testing

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-09T08:15:30.125Z"),
        ZoneOffset.UTC);
Instant timestamp = Instant.now(fixed);
~~~

This is a snippet requiring imports for **Clock**, **Instant**, and **ZoneOffset**. It allows unit tests to produce a deterministic instant. In production, the system should use the real clock or an injected clock per the architecture, **never hard-coded test times**.

### Duration vs. timestamp

~~~java
long start = System.nanoTime();
// Run a task to measure.
long elapsedNs = System.nanoTime() - start;
~~~

**System.nanoTime()** is designed for measuring relative elapsed time within the JVM. Its return value is **not Unix epoch nanos**. Never write it into a timestamp field. When measuring duration, emit **durationMs/durationNs** with an explicit unit so it is not confused with when an event occurred.

## 8. LogRecord.getInstant() and getMillis() in JUL

In **java.util.logging (JUL)**, **LogRecord** holds the message, level, loggerName, Throwable, and the time the event occurred.

- When a LogRecord is created, it is assigned an **Instant** from the available current clock.
- **getInstant()** returns the time as a java.time.Instant.
- **setInstant(Instant)** lets you set the time explicitly, which is useful for testing.
- **getMillis()** returns milliseconds since the epoch, losing sub-millisecond nanoseconds.
- **setMillis(long)** is **deprecated**; use setInstant in Java 17.
- Once a LogRecord has been handed to the framework, application code should not continue mutating its fields.
- A Formatter/Handler should use **record.getInstant()** to preserve event time rather than recording a delayed processing time.

JUL does not output JSON out of the box; **ConsoleHandler** normally writes to **System.err**, whereas **StreamHandler** can accept an OutputStream of your choice, such as System.out. Producing structured JSON requires an appropriate Formatter, encoder, or logging framework.

A simple formatting line:

~~~java
String utc = DateTimeFormatter.ISO_INSTANT
        .format(record.getInstant());
~~~

This is a snippet assuming a LogRecord variable `record` and an import for `DateTimeFormatter`. When exactly three fractional second digits are required, the full example below uses **appendInstant(3)**.

## 9. Standalone Java 17+ example: UTC-normalized JSON timestamp

This example uses **only the JDK**; no Maven, Logback, or Log4j is needed. It explicitly creates LogRecords with a fixed instant so the output does not depend on the machine clock.

Goals:

1. Use **OffsetDateTime** with offset +07:00 and convert it to a UTC Instant.
2. Use **LogRecord.setInstant** to attach the event time.
3. Use **StreamHandler(System.out)** and a Formatter to produce **one JSON object per line**.
4. Emit **timestamp** as ISO UTC with 3 millisecond digits and **timestampEpochMs** from the same Instant.
5. Also emit level, event, and orderId as JSON-escaped Strings.
6. Set Logger level to ALL and Handler level to INFO, so FINE is filtered out.
7. Flush after publishing without closing System.out.

Save the entire code as **TimestampJsonDemo.java**:

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class TimestampJsonDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.timestamp");

    private static final DateTimeFormatter UTC_MILLIS =
            new DateTimeFormatterBuilder()
                    .appendInstant(3)
                    .toFormatter();

    private static final class JsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Instant timestamp = record.getInstant();
            Object[] parameters = record.getParameters();
            String orderId = (parameters != null
                    && parameters.length > 0)
                    ? String.valueOf(parameters[0]) : "";

            return "{\"timestamp\":"
                    + jsonString(UTC_MILLIS.format(timestamp))
                    + ",\"timestampEpochMs\":"
                    + timestamp.toEpochMilli()
                    + ",\"level\":"
                    + jsonString(record.getLevel().getName())
                    + ",\"event\":"
                    + jsonString(record.getMessage())
                    + ",\"orderId\":"
                    + jsonString(orderId)
                    + "}" + System.lineSeparator();
        }
    }

    private static String jsonString(String value) {
        StringBuilder result = new StringBuilder("\"");

        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        result.append("\\u");
                        for (int shift = 12; shift >= 0; shift -= 4) {
                            result.append(Character.forDigit(
                                    (ch >>> shift) & 0xF, 16));
                        }
                    } else {
                        result.append(ch);
                    }
                }
            }
        }
        return result.append('"').toString();
    }

    private static void emit(
            Level level, String event, String orderId, Instant at) {
        LogRecord record = new LogRecord(level, event);
        record.setInstant(at);
        record.setParameters(new Object[] { orderId });
        LOG.log(record);
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        StreamHandler stdout =
                new StreamHandler(System.out, new JsonFormatter()) {
                    @Override
                    public synchronized void publish(LogRecord record) {
                        super.publish(record);
                        flush();
                    }
                };
        stdout.setLevel(Level.INFO);
        LOG.addHandler(stdout);

        try {
            Instant at = OffsetDateTime.parse(
                    "2026-11-09T15:15:30.125+07:00").toInstant();

            emit(Level.INFO, "order.accepted",
                    "ORD-17", at);
            emit(Level.WARNING, "inventory.retry",
                    "ORD-17", at.plusMillis(25));
            emit(Level.FINE, "cache.hit",
                    "ORD-17", at.plusMillis(30));
        } finally {
            LOG.removeHandler(stdout);
            stdout.flush();
        }
    }
}
~~~

### Running with JDK 17 or later

~~~bash
javac TimestampJsonDemo.java
java TimestampJsonDemo
~~~

**Exact stdout of the demo**:

~~~text
{"timestamp":"2026-11-09T08:15:30.125Z","timestampEpochMs":1794212130125,"level":"INFO","event":"order.accepted","orderId":"ORD-17"}
{"timestamp":"2026-11-09T08:15:30.150Z","timestampEpochMs":1794212130150,"level":"WARNING","event":"inventory.retry","orderId":"ORD-17"}
~~~

This is **JSON Lines/NDJSON**: each line is a JSON object, not a JSON array. The program writes nothing to stderr. Physical line separators may vary by environment, but the logical content of each line is as shown above.

### Why is the output deterministic?

1. **OffsetDateTime.parse** parses the +07:00 time and **toInstant()** converts it to 08:15:30.125 UTC.
2. **record.setInstant(at)** keeps the event time fixed for demonstration purposes.
3. **appendInstant(3)** produces exactly three fractional second digits and Z.
4. **toEpochMilli()** derives **1794212130125** from the same Instant; adding 25 ms yields **1794212130150**.
5. **Logger level ALL** does not filter FINE at the source; **StreamHandler level INFO** filters FINE at the destination.
6. **JsonFormatter** builds fields in a deterministic order and uses **jsonString(...)** to escape quotes, backslashes, and control characters.
7. **setUseParentHandlers(false)** prevents parent Logger handlers from printing duplicate output to the console.
8. Overriding **publish()** calls **flush()** after the Handler writes, ensuring the demo output appears promptly.
9. **Do not call close() on a StreamHandler wrapping System.out**: closing it can close the application's standard output stream.
10. **WARNING** is JUL's level name; other backends may use WARN, but the timestamp logic remains the same.

**Limitations:** This Formatter is meant to illustrate the timestamp field, not to serve as a production JSON encoder for arbitrary object types, Throwables, malformed Unicode, or nested fields. In real systems, use a tested JSON encoder/layout and a well-defined schema.

## 10. Should real applications call setInstant for every event?

Usually **no**. The logging backend creates the timestamp when the log event is emitted. If you construct domain events yourself, **Instant.now()** or **Instant.now(clock)** is appropriate depending on your architecture, but you should never generate two timestamps from two separate clock calls and claim they represent the same instant.

~~~java
Clock clock = Clock.systemUTC();
Instant eventTime = Instant.now(clock);
~~~

This is a snippet; an application can inject a `Clock` into services so tests can swap in `Clock.fixed`.

Notes:

- Do not use **LocalDateTime.now()** without an offset as the standard timestamp field in multi-service logs.
- Do not use the time when the Formatter runs if you want the event time at the emission site.
- Do not set the LogRecord timestamp from untrusted client data without clearly documenting the source and policy.
- If you need a **business occurredAt** distinct from the log timestamp, use a separate field instead of overwriting it.
- With async loggers, verify that the backend preserves the timestamp at event creation and that the encoder does not refresh it.
- For replayed logs, typically preserve the original eventTime and add processedAt/ingestedAt as needed.

## 11. Log4j 2: JsonTemplateLayout and timestamp resolver

**Apache Log4j 2** provides **JsonTemplateLayout** to output a LogEvent according to a JSON template. It belongs to the **log4j-layout-template-json** module, which must match the **log4j-core** version.

An **EventTemplate.json** file may look like:

~~~json
{
  "timestamp": {
    "$resolver": "timestamp",
    "pattern": {
      "format": "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
      "timeZone": "UTC"
    }
  },
  "level": {
    "$resolver": "level",
    "field": "name"
  },
  "message": {
    "$resolver": "message",
    "stringified": true
  }
}
~~~

This is a **template** defining fields, not log output. **$resolver=timestamp** reads the timestamp from the LogEvent; **timeZone=UTC** sets the formatting timezone; the pattern determines display precision.

**Watch out for literal Z:** **'Z'** in the pattern is a literal character. Only print Z like this if you are actually formatting in **UTC**. Changing the timezone while keeping Z will cause records to **falsely claim the wrong offset**.

Appender snippet in **log4j2.xml**:

~~~xml
<Console name="JSON" target="SYSTEM_OUT">
    <JsonTemplateLayout eventTemplateUri="classpath:EventTemplate.json"/>
</Console>
~~~

Place this under **Configuration/Appenders**, reference it via `AppenderRef` in the `Loggers` section, and put `EventTemplate.json` on the classpath. The Log4j 2 backend is required; adding only `log4j-api` or using SLF4J with Logback will not make this configuration work.

Log4j 2 also supports an **epoch timestamp resolver**, for example:

~~~json
{
  "$resolver": "timestamp",
  "epoch": {
    "unit": "millis",
    "rounded": true
  }
}
~~~

This is **a resolver expression**, not a complete event. **unit=millis** and **rounded=true** produce an integer epoch milliseconds value according to the layout's rules. If using seconds or nanoseconds, check the unit and the capabilities of your JSON consumer.

**PatternLayout %d is not the same as a schema-typed JSON timestamp.** It typically emits text, and its default timezone may not be UTC. When you need typed fields, use JSON Template Layout or a compatible encoder and verify the actual output.

## 12. Logback: %date/%d and timezone in patterns

**Logback** commonly runs behind **SLF4J**. In `PatternLayout`, **%date** or **%d** reads the LogEvent's time.

A text pattern explicitly configured for UTC:

~~~text
%d{yyyy-MM-dd'T'HH:mm:ss.SSS'Z', UTC} %-5level %logger - %msg%n
~~~

This is a **text pattern**, not JSON. The literal **'Z'** is only valid because **UTC** is specified. Never use this pattern with a different timezone while keeping Z.

**ISO8601 trap:** across Logback versions, traditional **%date{ISO8601}** can use a space between date and time and a comma for milliseconds, so it is **not necessarily a strict RFC 3339 timestamp**. Check the documentation for your Logback version and configure an explicit pattern/encoder.

For **proper JSON logging**, the application needs a **compatible JSON encoder**, rather than hand-crafting JSON with a text PatternLayout such as:

~~~text
{"timestamp":"%d","message":"%msg"}
~~~

If `%msg` contains quotes, newlines, or backslashes, this hand-crafted output can break JSON. With a proper JSON encoder, the timestamp must be emitted from the event time with a consistent timezone, precision, and field name.

**The SLF4J facade does not define the timestamp field itself.** The backend and encoder determine how timestamps are serialized, so switching backends must be accompanied by field contract tests.

## 13. Log timestamps vs. business timestamps

An **order.completed** event might carry these timestamps:

~~~json
{
  "timestamp": "2026-11-09T08:15:30.125Z",
  "event": "order.completed",
  "orderId": "ORD-17",
  "orderCreatedAt": "2026-11-08T16:00:00Z",
  "paymentAuthorizedAt": "2026-11-09T08:14:50Z"
}
~~~

**timestamp** is the logging time of the event; **orderCreatedAt** and **paymentAuthorizedAt** are business milestones. They must not be used interchangeably just because they are all date-time values.

Other names with distinct semantics include:

- **occurredAt**: when the business event occurred at the source.
- **recordedAt**: when the application or database recorded the event.
- **publishedAt**: when the event was pushed to a broker.
- **processedAt**: when a consumer processed it.
- **observedAt**: when the observability system collected it.

For example, an offline device emits an event at 08:00 and syncs with the server at 11:00. The business `occurredAt` and the server's log `timestamp` can differ by hours with **no contradiction**. Use clear field names and documentation to prevent dashboards from subtracting the wrong fields.

## 14. Timestamps do not establish a total order in distributed systems

Timestamps are very useful for building timelines, but they do not guarantee an exact **total order**:

1. Clocks on two hosts can drift (**clock skew**).
2. NTP/PTP can step or slew clocks.
3. Two events can fall within the same millisecond.
4. Async queues, collectors, and networks cause logs to arrive late or be observed out of order.
5. Event time may come from a client or device with an inaccurate clock.
6. Wall-time clock sources can jump; they are not monotonic Duration sources.
7. A timestamp formatted to nanoseconds does not prove the clock is accurate to nanoseconds.
8. A single request may span multiple threads/processes without a single global sequence.

To reconstruct causality, combine **timestamp with requestId, traceId/spanId, service/instance, and a clearly scoped sequence number**. If business logic requires a strict commit order, rely on transactions, broker offsets, or an appropriate protocol—not the log order displayed by a console or collector.

**Duration** should be measured with an appropriate monotonic source; subtracting two wall-clock timestamps is affected by clock adjustments. The `durationMs` field means something completely different from `timestampEpochMs`.

## 15. Querying by time range

Log platforms typically parse timestamps into an internal date/time type. Example pseudo-query condition:

~~~text
timestamp >= "2026-11-09T08:00:00Z"
AND timestamp < "2026-11-09T09:00:00Z"
AND service == "catalog"
AND level == "ERROR"
~~~

This is a **pseudo query**, not universal syntax for Elasticsearch, Loki, or other systems.

Guidelines:

- Prefer half-open intervals **[start, end)** so events on window boundaries are not double-counted.
- If logs are displayed in local time, convert query bounds to the same timeline/offset before filtering.
- Avoid lexical string comparisons across inconsistent timezones or precisions.
- If logs arrive late, querying by event time vs. ingestion time can return different result sets.
- The collector must parse the field as a date, not just leave it inside message text.
- If the system stores epoch numbers, know the exact **unit, signed range, and precision**.
- Dashboards can render in the user's timezone while storage remains in UTC.
- When changing a field name or type, update the corresponding index mappings, dashboards, and alerts.

Never assume that seeing a timestamp in JSON means the log platform has indexed it as a **queryable time field**.

## 16. Clock skew, late events, and alerting

In multi-service systems, timestamps can differ from observed reality due to wrong clocks, slow networks, or replayed data.

**Example:**

~~~json
{
  "timestamp": "2026-11-09T08:15:30.125Z",
  "observedAt": "2026-11-09T08:17:10Z",
  "event": "payment.authorized"
}
~~~

Here `observedAt` is over a minute later; this may be due to pipeline lag rather than the business action happening late. If logs are delivered late, a dashboard may place the event into an earlier time bucket.

Strategies:

1. Preserve the **event timestamp** from the source when appropriate.
2. Record **observedAt** at the collector to measure ingest lag.
3. Monitor **clock skew** and keep host/VM clocks synchronized.
4. Alert on events unusually far in the future or too old per policy.
5. Do not drop all late events by default; consider analytics goals and retention limits.
6. For auditing, store both source time and system receipt time if traceability is needed.
7. Cross-reference traceId/requestId when two timestamps cannot explain ordering.
8. Test alert windows while accounting for ingest latency.

Timestamps do not replace audit trail integrity or transactional ordering guarantees.

## 17. Schema evolution: changing timestamps requires migration

The timestamp schema is a **data contract**, just like an API consumed by dashboards and alerts.

| Item | Convention to define |
| --- | --- |
| Field name | timestamp, @timestamp, or a single canonical name |
| Type | ISO/RFC 3339 String or epoch Number with unit |
| Timezone | UTC Z or full offset |
| Precision | Seconds/millis/micros/nanos |
| Semantics | Event time, observed time, or processed time |
| Missing | Drop event, default, quarantine, or error? |
| Invalid format | Reject, fallback, or dead-letter? |
| Out-of-range | Handling timestamps too far in the past/future |
| Late arrival | Preserve original event timestamp or not? |
| Version | Compatibility testing between producer and consumer |

**Do not change timestamp from String to Number in a single release without updating parsers and index mappings.** The system may still ingest logs, but queries will break. Changing from UTC Z to a timezone-less string is also a semantic breaking change, even though the JSON remains valid.

If a schema change is unavoidable, consider a parallel transition period with a clearly named new field, contract tests, and dashboard/alert migrations. Never arbitrarily alter timestamps after they have been indexed.

## 18. Performance when formatting timestamps

Date-times may be formatted across very high log volumes. Design for efficiency without sacrificing correctness.

- **DateTimeFormatter is immutable and thread-safe**; it can be reused via **static final**.
- **SimpleDateFormat** holds mutable state and is not thread-safe if shared without synchronization.
- Each event only needs **one source Instant**, which can then be formatted to ISO and epoch if truly required.
- Do not instantiate a new DateTimeFormatter on every log call without reason.
- Backend-provided JSON layouts/encoders are usually better than formatting every event manually in business code.
- Choose milliseconds when sufficient; emitting nanoseconds produces longer strings and may consume extra index resources.
- Async logging reduces some I/O overhead, but queues can fill up and drop logs depending on policy.
- Do not strip timestamps from important events just to optimize: reduce noisy logs and choose appropriate levels and encoders instead.
- Benchmark high-volume hot paths; measure CPU and allocations rather than relying on assumptions.
- If logs are needed after a crash, understand that **flush does not mean the collector has durably stored the data**.

## 19. Security and time-related risks

Although timestamps are less sensitive than tokens or passwords, they still affect system security and reliability:

1. **Client-controlled timestamps:** user input can carry forged times, so never trust it unconditionally.
2. **Log injection:** if JSON is concatenated without escaping, input can inject a fake record with a different timestamp.
3. **Audit trails:** distinguish between source emission time and server receipt time; do not treat a single timestamp as tamper-proof evidence.
4. **Clock drift/spoofing:** can mislead incident investigation timelines.
5. **Far-out timestamps:** can break retention or filtering if storage blindly trusts every event time.
6. **User timezones:** can leak activity patterns when combined with other fields; apply appropriate access controls.
7. **Retention:** retention periods may be calculated by event time or ingestion time, affecting late events differently.
8. **Numeric overflow:** epoch nanos can be rounded or corrupted across parsers.
9. **PII alongside timestamps:** correlation with userId/tenantId can constitute personal data requiring minimization.
10. **Backups/collectors:** read permissions and retention policies must also apply to replicated data.

Accurate timestamps aid investigation, but **pipeline integrity and trustworthiness** require dedicated design and monitoring.

## 20. Common pitfalls and how to fix them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Log has time but no timezone | Using LocalDateTime or pattern without offset | Convert from Instant, emit UTC Z/offset |
| Log shows Z but is actually local time | Literal 'Z' without configuring UTC | Check timezone in Layout/Formatter |
| Events shifted by 7 hours | Treating +07:00 as UTC or converting twice | Parse to Instant and compare |
| 13-digit epoch treated as seconds | Milliseconds/seconds mismatch | Name field EpochMs, verify unit |
| Nano timestamp off in last digits | JSON parser uses double and loses integer precision | Use an appropriate representation |
| Multiple events share same timestamp | Precision is only seconds/millis | Choose sufficient precision, add sequence if needed |
| Events appear in the future | Host clock wrong or offset parsed wrongly | Check NTP/timezone/parser |
| Timestamp reflects file write time | Formatter calls Instant.now after async queue | Read timestamp from LogEvent |
| Logback ISO8601 is not valid RFC 3339 | Default pattern uses space/comma | Choose strict pattern + timezone |
| Log4j2 JSON missing timestamp | Template lacks timestamp resolver | Check EventTemplate.json/layout |
| Log has timestamp but cannot filter by date | Collector stores as String message or wrong mapping | Check parsing and index type |
| Range query misses late events | Relying only on ingestion time or narrow windows | Separate event vs. observedAt |
| UI timezone differs from file | Viewer converts timezone on display | Compare Instant, not just UI strings |
| Unit tests fail intermittently | Tests use real Instant.now | Use Clock.fixed/setInstant |
| Wrong fractional seconds | Pattern missing or mixing nano/milli | Test .000/.125/.999 and precision |
| Async logs missing records | Queue/drop policy or incomplete flush | Test shutdown, collector, and metrics |

**Diagnostic sequence:** identify field schema → identify event time source → parse as Instant → check timezone/offset → check precision/unit → check layout/encoder → check collector/index → compare against observedAt and clock source.

## 21. End-to-end timestamp testing

**Unit tests:**

- An Instant must round-trip through format/parse unchanged within the chosen precision.
- **2026-11-09T15:15:30.125+07:00** must equal **2026-11-09T08:15:30.125Z**.
- Test millisecond values **.000**, **.125**, and **.999**.
- Test year boundaries, leap years, and pre-Unix-epoch dates if the application handles historical data.
- For ZoneIds with DST, test transition days and ambiguous times.
- Use **Clock.fixed** or **LogRecord.setInstant**; never use Thread.sleep to stabilize expected stdout.

**Integration tests:**

- Start the actual backend version and verify the timestamp field is emitted.
- JSON must parse into an object; timestamp must parse into the expected Instant.
- Change the JVM timezone: the canonical UTC field's instant must not change.
- If output includes epoch millis, compare against **toEpochMilli()**.
- Simulate a slow async queue and ensure event timestamp is not replaced by output time.
- Test messages with Unicode, quotes, and newlines to verify the encoder does not break JSON.
- The collector must produce a queryable date field, not just an unindexed String.
- Verify Log4j2 JsonTemplateLayout has the right module and resolver.
- Verify dashboards/alerts target the right event time or ingestion time field.
- Test late-arriving data, anomalous future timestamps, and failure policies.

**Do not merely assert that the string contains the key "timestamp".** Parse it back and verify the instant, timezone, unit, precision, schema, and ingest path.

## 22. Practical checklist

1. Choose one **canonical timestamp field** and document its semantics.
2. Pick either a **UTC ISO/RFC 3339 string** or an epoch number with an **explicit unit**.
3. In Java, prefer **Instant** and **Clock** for testability.
4. Never use **LocalDateTime** without an offset as an absolute timestamp.
5. Never hard-code **'Z'** unless you are actually formatting in UTC.
6. Choose a precision that matches your clock, backend, and collector.
7. Derive ISO and epoch values from **one Instant**, not two clock reads.
8. With async logging, read **event time** from the LogEvent/LogRecord.
9. Use thread-safe **DateTimeFormatter**; avoid unsynchronized SimpleDateFormat singletons.
10. Verify Logback/Log4j2/JUL differences in formatting and timezone handling.
11. Separate **observedAt/ingestedAt/processedAt** if latency analysis is needed.
12. Never treat timestamps as a total order in distributed systems.
13. Verify the collector parses it into a date field with the right type, mapping, and timezone.
14. Manage contracts and migrations when changing keys, types, precision, or semantics.
15. Account for clock skew, replays, late events, and retention.
16. Guard against untrusted input, broken JSON escaping, read permissions, and audit gaps.
17. Test with fixed clocks, boundary values, and the real pipeline.

**Conclusion:** The **timestamp field** in JSON logging must make clear **what instant it represents, where it came from, which offset it uses, what precision it has, and which schema it follows**. With Java 17, **Instant** and **LogRecord.getInstant()** provide a reliable foundation for event time; emit **UTC Z** or an explicit-unit epoch value, then verify that your JSON encoder and collector interpret it correctly.

## 23. Official references

- [Oracle Java 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): getInstant, getMillis, and setInstant.
- [Oracle Java 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): timeline, epoch milliseconds, Instant.now.
- [Oracle Java 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): ISO_INSTANT and thread-safety.
- [Oracle Java 17 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): appendInstant(3).
- [Oracle Java 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): Clock.systemUTC and Clock.fixed.
- [Apache Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): timestamp resolver, epoch, and timeZone.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): %d and timezone options.
- [Logback — Layouts](https://logback.qos.ch/manual/layouts.html): %date and ISO8601/UTC.
- [RFC 3339 — Date and Time on the Internet](https://www.rfc-editor.org/rfc/rfc3339): timestamp representation for data interchange.
