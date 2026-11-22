# Exception Fields in JSON Logging: Recording Java Errors as Structured Data

## 1. What Are Exception Fields?

In **JSON logging**, each log event is represented as a **JSON object** consisting of fields with explicit names and data types. **Exception fields** are one or more fields used to describe an exception (*exception/Throwable*) that occurs while processing an event: the error type, error message, stack trace, and sometimes the root cause.

Instead of just writing a long string:

```text
ERROR Checkout failed: java.lang.IllegalStateException: Payment unavailable
```

a JSON log can separate the data into distinct fields:

```json
{
  "@timestamp": "2026-11-09T10:20:00.000Z",
  "log.level": "ERROR",
  "service.name": "orders-service",
  "message": "Checkout failed",
  "error.type": "java.lang.IllegalStateException",
  "error.message": "Payment unavailable",
  "error.stack_trace": "java.lang.IllegalStateException: Payment unavailable\n\tat demo.OrderService.checkout(OrderService.java:42)"
}
```

This is an **illustrative example of an Elastic Common Schema (ECS)-style schema**; the timestamp, class name, and line number are sample data, not the exact output of the program shown later.

The `error.stack_trace` field is **a single JSON string**. In a JSON Lines file, newline characters inside the stack trace are encoded as `\n`, tabs as `\t`, and double quotes as `\"` when needed. An event can still reside on **a single physical line**, allowing tools that read JSON line by line to parse it without mistaking a stack frame for a new record.

**Do not confuse exception fields with the `java.lang.Exception` class.** A field is **part of the log record format**, whereas `Exception`, `RuntimeException`, `Error`, and their subclasses all belong to the `Throwable` hierarchy in Java. The backend receives the `Throwable` and decides how to convert it into JSON fields.

### After this lesson, you will be able to

- Distinguish between a log event's `message` and an exception's `message`.
- Understand `error.type`, `error.message`, and `error.stack_trace`; and compare them with other field names such as `exception.type`.
- Pass the full `Throwable` into the logging API instead of merely concatenating `getMessage()` into a string.
- Write JSON Lines with exception fields using **Log4j2 JsonTemplateLayout** on Java 17.
- Query, inspect, and handle error fields when there is no exception, when there is a cause chain, or when there are suppressed exceptions.
- Design a stable schema with correlation IDs, while avoiding sensitive data leaks and overly long stack traces.

## 2. Structure of a JSON Log Event

An event may include the following field groups:

| Group | Example field | Meaning |
| --- | --- | --- |
| Timestamp | `@timestamp` | Time when the event was created |
| Level | `log.level` | INFO, WARN, ERROR... |
| Source | `service.name`, `log.logger` | Service and logger emitting the event |
| Context | `trace.id`, `request.id`, `labels` | Locate logs belonging to the same transaction |
| Event | `message` | Describes what the application is doing or what failed |
| Exception | `error.type` | Exception type name |
| Exception | `error.message` | Message of the Throwable object |
| Exception | `error.stack_trace` | Stack trace, typically including frames and causes |
| Business classification | `error.code` | Stable application-defined error code, if any |

**Not every schema uses these names.** For example, a pipeline following OpenTelemetry semantic conventions might use `exception.type`, `exception.message`, and `exception.stacktrace`, whereas an ECS-based template uses `error.type`, `error.message`, and `error.stack_trace`. Dots in field names can also carry different meanings when stored in different search engines.

Therefore, you need to **choose a consistent schema** for your application and collection system. Do not assume that because field names look similar, every system will query, index, and store them the same way.

### A common point of confusion: dotted names

The following two JSON objects are both valid, but **they do not have the same structure**:

```json
{
  "error.type": "java.lang.IllegalStateException"
}
```

```json
{
  "error": {
    "type": "java.lang.IllegalStateException"
  }
}
```

The first object has **a single literal key** named `"error.type"`; the second object has an `error` object containing a `type` key. Some indexing systems may map these forms according to their own rules, but at the raw JSON level they are two different structures. When parsing with code or `jq`, you must use the corresponding access syntax.

## 3. How Do Exception Fields Differ from the `message` Field?

A log event has **two layers of meaning**:

1. **The event's message** answers: *Which operation failed, at which step, and with what business context?*
2. **The exception's message** answers: *What cause message does the Throwable object carry?*

Example:

```java
IllegalStateException failure =
        new IllegalStateException("Payment gateway unavailable");

LOG.error("Checkout for order ORD-42 failed", failure);
```

The snippet above assumes `LOG` is a compatible logger inside a method. Target structured data:

```json
{
  "message": "Checkout for order ORD-42 failed",
  "error.type": "java.lang.IllegalStateException",
  "error.message": "Payment gateway unavailable"
}
```

Both messages are useful and do not replace each other. If you only store the exception message, the log may lack the order ID, processing step, endpoint, or service details. If you only store the event message, the log may lack the exception class and stack trace needed to pinpoint where the error occurred.

**Do not log exceptions as text via string concatenation:**

```java
LOG.error("Checkout failed: " + failure);
LOG.error("Checkout failed: " + failure.getMessage());
```

These two calls only pass a **message string** to the backend, typically without attaching the actual `Throwable` object to the event. As a result, the JSON encoder has no separate exception object from which to extract `type`, `stack_trace`, or cause.

**Pass the Throwable through the appropriate overload:**

```java
LOG.error("Checkout failed", failure);
```

In standard Log4j2 and SLF4J, the `error(String, Throwable)` overload makes the intent explicit. When using parameterized logging, you also need to know the specific API's rules for handling a trailing Throwable argument. This example uses the explicit overload to avoid ambiguity.

## 4. Core Exception Fields

### 4.1. Type/class name

The `error.type` or `exception.type` field typically records the fully qualified class name:

```text
java.lang.IllegalArgumentException
java.lang.IllegalStateException
java.io.IOException
java.net.SocketTimeoutException
```

The class name allows grouping events by exception type. However, **an exception type is not a business error code**: a single `IllegalArgumentException` can have many different causes and handling paths.

Some systems use the simple name `IllegalStateException`, while others record the full package name. Standardize on one convention for reliable querying, avoiding a setup where one service logs the short name and another logs the full name without a consistent rule.

### 4.2. Exception message

`Throwable.getMessage()` returns the message attached to the Throwable; this value **can be `null`**.

Example:

```java
Throwable a = new IllegalArgumentException("Invalid amount");
Throwable b = new IllegalStateException();

System.out.println(a.getMessage());
System.out.println(b.getMessage());
```

**Exact stdout** when running this snippet in an appropriate Java method:

```text
Invalid amount
null
```

The `null` line is the result of `println(Object)` / string concatenation when the argument is null; it does not mean every JSON encoder will output the literal string `"null"`. Depending on the schema and serializer, an exception message field may be **omitted**, rendered as JSON `null`, or handled by another rule. Do not coerce it into a fabricated string if your system needs to preserve the semantics of missing data.

### 4.3. Stack trace

A stack trace describes the execution thread's frames, typically including class, method, file, and line number when available. When there is a wrapped exception, a text stack trace usually includes **`Caused by:`** sections and may include **`Suppressed:`**.

In JSON, there are two common representations:

**String form:**

```json
{
  "error.stack_trace": "java.lang.IllegalStateException: Payment unavailable\n\tat demo.PaymentService.pay(PaymentService.java:30)\nCaused by: java.lang.IllegalArgumentException: Rejected"
}
```

**Structured array of frames:**

```json
{
  "exception": {
    "type": "java.lang.IllegalStateException",
    "frames": [
      {
        "class": "demo.PaymentService",
        "method": "pay",
        "file": "PaymentService.java",
        "line": 30
      }
    ]
  }
}
```

Both snippets are **illustrative schemas**, not the exact JSON that every Log4j2 or Logback encoder is required to produce. The string form is easy to read and display in a UI; the object/array form is convenient for filtering by frame, though storage cost, field count, and parser requirements differ.

Do not pass an entire `Throwable` object to a generic JSON serializer without explicit rules: internal `Throwable` fields, cause chains, suppressed exceptions, cyclic references, or custom properties can make the output unstable. A **dedicated logging layout/encoder** that understands `Throwable` is generally more reliable than arbitrarily calling `ObjectMapper.writeValueAsString(exception)`.

### 4.4. Root cause and cause chain

Java exceptions can wrap an underlying cause:

```java
Throwable cause =
        new IllegalArgumentException("Gateway rejected");
Throwable outer =
        new IllegalStateException("Payment unavailable", cause);
```

When logging `outer`:

- **Outer type:** `java.lang.IllegalStateException`.
- **Outer message:** `Payment unavailable`.
- **Root-cause type:** `java.lang.IllegalArgumentException`.
- **Root-cause message:** `Gateway rejected`.

If you use a single `error.type` field, you must define whether it represents the **outermost** exception or the **deepest root cause**. Different systems may choose differently. Prefer adding dedicated fields such as `root_cause.type` if you need root-cause analysis, rather than changing the meaning of `error.type` across services.

**`Throwable.getCause()` returns the direct cause**, which may be null. A cause chain is not limited to two levels; when traversing the chain manually, guard against unexpected reference cycles and set a depth limit.

### 4.5. Suppressed exceptions

`try-with-resources` blocks can attach an exception thrown during `close()` as a **suppressed exception**:

```java
Throwable error = new IllegalStateException("Primary failure");
error.addSuppressed(new IllegalArgumentException("Cleanup failure"));
```

A stringified stack trace produced by a supporting backend may contain a `Suppressed:` section. However, a JSON encoder **does not by default** generate a separate `suppressed` array; that must be supported and configured by the schema or resolver. Do not strip suppressed information if you need to diagnose shutdown or cleanup failures.

## 5. JSON Lines: An Exception Must Not Break a Record

A JSON Lines file (typically with a `.jsonl` or `.ndjson` extension) contains **one JSON object per line**. When an exception stack trace spans multiple lines, the serializer must escape special characters inside the JSON string.

Valid example, all on **one physical line**:

```json
{"log.level":"ERROR","message":"Order failed","error.stack_trace":"java.lang.IllegalStateException: Failed\n\tat demo.OrderService.place(OrderService.java:17)"}
```

Do not do this in a JSON Lines file:

```text
{"message":"Order failed","error.stack_trace":"java.lang.IllegalStateException: Failed
    at demo.OrderService.place(OrderService.java:17)"}
```

The second form has a **raw newline character inside an unescaped JSON string**, making the JSON invalid and causing a log collector tailing the file to treat a stack frame as a new line.

A dedicated JSON serializer handles this properly:

- Double quotes `"` → escaped as `\"` when needed.
- Backslashes `\` → escaped as `\\` when needed.
- Tabs, newlines, and control characters → corresponding JSON escapes.
- Unicode → output or escaped as valid UTF-8/JSON according to configuration.

**Do not assemble JSON manually using Java string concatenation** if the message contains client data or exception details. Input containing quotes, newlines, or control characters can break the schema, disrupt the log collector, or forge log lines. Use a layout/encoder with verified escaping rules.

## 6. Maven + Java 17 Example: Log4j2 JSON Template Layout

This example uses **Apache Log4j2** and `JsonTemplateLayout`, producing two events: a normal INFO event and an ERROR event with a `Throwable` containing a cause. The output file is written in JSON Lines format using the ECS template. No manual exception serialization is needed in business code.

### 6.1. Project structure

```text
exception-json-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── JsonExceptionDemo.java
        └── resources/
            └── log4j2.xml
```

### 6.2. The `pom.xml` file

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>exception-json-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.24.3</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-layout-template-json</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Why are three dependencies needed?**

- `log4j-api`: Java code imports `LogManager` and `Logger`.
- `log4j-core`: backend providing appenders and configuration.
- `log4j-layout-template-json`: module containing `JsonTemplateLayout` and event templates such as `EcsLayout.json`.

The three versions are pinned together solely to give this lesson a deterministic configuration. They are **not claimed to be the latest releases** or the optimal production choice at all times. In real deployments, keep versions maintained with security patches and avoid arbitrarily mixing Log4j2 artifacts across different major/minor versions.

### 6.3. The `src/main/resources/log4j2.xml` file

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="JsonFile"
              fileName="logs/events.jsonl"
              append="false">
            <JsonTemplateLayout
                    eventTemplateUri="classpath:EcsLayout.json"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="JsonFile"/>
        </Root>
    </Loggers>
</Configuration>
```

Key points:

1. `File` is an appender writing to `logs/events.jsonl` relative to the working directory.
2. `append="false"` is only for **standalone demos** so the file is overwritten on each run for easy comparison. **Do not use it for operational logs that must retain history**, unless another archiving policy is in place.
3. `JsonTemplateLayout` generates JSON; the `EcsLayout.json` template is packaged inside the JSON Template Layout module, so you do not need to create the JSON template file yourself.
4. The layout uses an event delimiter, which defaults to the platform newline. Each event is encoded as **one JSON record**, with the stack trace escaped inside a string.
5. `Root level="info"` allows INFO/WARN/ERROR... but does not emit DEBUG/TRACE through the root logger in this configuration.
6. No Console appender is attached so the demo's own stdout stays easy to verify.
7. Log4j2 Core and the template-layout module must be present at **runtime**; adding only `log4j-api` will not provide this functionality.

### 6.4. The `src/main/java/demo/JsonExceptionDemo.java` file

```java
package demo;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.ThreadContext;

public final class JsonExceptionDemo {
    private static final Logger LOG =
            LogManager.getLogger(JsonExceptionDemo.class);

    public static void main(String[] args) {
        ThreadContext.put("requestId", "REQ-204");

        try {
            LOG.info("JSON exception demo started");

            try {
                throw new IllegalArgumentException("Gateway rejected");
            } catch (IllegalArgumentException cause) {
                throw new IllegalStateException(
                        "Payment unavailable", cause);
            }
        } catch (IllegalStateException exception) {
            LOG.error("Order ORD-42 failed", exception);
        } finally {
            ThreadContext.remove("requestId");
        }

        System.out.println("demo-finished");
    }
}
```

Event flow explanation:

- The `INFO` event has a `message` but **no Throwable**.
- The `ERROR` event has the event message `Order ORD-42 failed` and the full `IllegalStateException`.
- The outer exception has the message `Payment unavailable`, and the inner cause is `IllegalArgumentException` with the message `Gateway rejected`.
- `ThreadContext` adds `requestId` to events on the same thread; the ECS template may represent the context map under `labels` depending on the specific template.
- The `finally` block clears the context after logging to prevent request data from leaking into unrelated work on a reused thread.
- `System.out.println` does not go through Log4j2; it writes directly to stdout.

### 6.5. Running the program

From the `exception-json-demo` directory, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.JsonExceptionDemo
```

**Exact stdout produced by `JsonExceptionDemo` itself:**

```text
demo-finished
```

Logger events go into `logs/events.jsonl`, not to the console in this demo configuration. Maven, plugins, or other tooling may print their own messages; those are not output from `System.out.println` in the class.

**Result to inspect in the file**: two newline-separated JSON objects, one INFO and one ERROR. The ERROR record contains ECS-style exception fields, typically:

```json
{
  "log.level": "ERROR",
  "message": "Order ORD-42 failed",
  "error.type": "java.lang.IllegalStateException",
  "error.message": "Payment unavailable",
  "error.stack_trace": "java.lang.IllegalStateException: Payment unavailable\nCaused by: java.lang.IllegalArgumentException: Gateway rejected"
}
```

This is an **illustration of the key fields to observe**, not the full output or verbatim JSON string from the template. The actual file also contains timestamp, logger, thread, context, and **multiple stack trace frames**; `error.stack_trace` holds a fuller string than the abbreviated example above. The template is not configured to pretty-print across multiple lines: the contents of `events.jsonl` are JSON Lines.

For the INFO event, there is no Throwable from which to populate `error.type`/`error.message`/`error.stack_trace`. Those fields may be **absent or represented according to the template/encoder's null rules**; do not expect a default string such as `"No exception"`.

### 6.6. Inspecting JSON Lines

On Linux/macOS:

```bash
cat logs/events.jsonl
```

On PowerShell:

```powershell
Get-Content logs/events.jsonl
```

If `jq` is installed, you can inspect only the exception fields of the ERROR event:

```bash
jq -c 'select(."log.level" == "ERROR") |
       {message: .message, type: ."error.type", cause: ."error.message"}' \
       logs/events.jsonl
```

Expected output for **the selected fields**, assuming the template emits those exact field names:

```json
{"message":"Order ORD-42 failed","type":"java.lang.IllegalStateException","cause":"Payment unavailable"}
```

The command uses `."error.type"` because in raw JSON it is a **literal key containing a dot**. Writing `.error.type` would only match a nested schema `{"error":{"type":"..."}}`, which is not the same structure.

Verify that every line parses as valid JSON:

```bash
jq -c . logs/events.jsonl
```

If the command reports a JSON error, check whether the actual file has interleaved plain-text logs, was truncated mid-write, or contains unescaped multi-line output.

## 7. Log4j2 Exception Resolvers: Customizing Fields per Schema

`JsonTemplateLayout` lets you define a custom event template instead of using the built-in ECS template. Throwable resolvers in Log4j2 include:

- `exception`: extracts data from `LogEvent.getThrown()`, i.e., the outermost exception.
- `exceptionRootCause`: extracts data from the deepest root-cause exception.
- `field="className"`: the class name.
- `field="message"`: `Throwable.getMessage()`.
- `field="stackTrace"`: the stack trace in the configured representation.

Example fragment in an **event template JSON**, not a log output line:

```json
{
  "exception": {
    "type": {
      "$resolver": "exception",
      "field": "className"
    },
    "message": {
      "$resolver": "exception",
      "field": "message"
    },
    "stack_trace": {
      "$resolver": "exception",
      "field": "stackTrace",
      "stackTrace": {
        "stringified": true
      }
    },
    "root_cause_type": {
      "$resolver": "exceptionRootCause",
      "field": "className"
    },
    "root_cause_message": {
      "$resolver": "exceptionRootCause",
      "field": "message"
    }
  }
}
```

The `exception.type` and `exception.message` keys in this example form a **custom nested object you define**, and do not automatically become ECS `error.type`. To use the ECS schema, choose the corresponding keys in your event template or use `EcsLayout.json`.

### 7.1. A minimal complete template

If you want explicit control over field names, create `src/main/resources/ExceptionLayout.json`:

```json
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
  "logger": {
    "$resolver": "logger",
    "field": "name"
  },
  "message": {
    "$resolver": "message",
    "stringified": true
  },
  "error.type": {
    "$resolver": "exception",
    "field": "className"
  },
  "error.message": {
    "$resolver": "exception",
    "field": "message"
  },
  "error.stack_trace": {
    "$resolver": "exception",
    "field": "stackTrace",
    "stackTrace": {
      "stringified": true
    }
  },
  "error.root_cause_type": {
    "$resolver": "exceptionRootCause",
    "field": "className"
  }
}
```

Replace the layout in the demo's `log4j2.xml` with:

```xml
<JsonTemplateLayout
        eventTemplateUri="classpath:ExceptionLayout.json"/>
```

This is an **optional variation** after running the default demo. Fields like `error.root_cause_type` are a choice of **this lesson's custom schema**, not a standard ECS field name by default. When the outermost exception and root cause differ, this setup is useful for comparing the two error classes.

Depending on the resolvers and configuration, fields that evaluate to null may be omitted or rendered according to layout rules. Always verify both INFO and ERROR events in practice rather than assuming every key appears when there is no Throwable.

### 7.2. String stack trace or array of frames?

The `exception` resolver with `field="stackTrace"` can produce an **array of stack frames**. If you want to keep it as a string containing `at ...` and `Caused by:` lines, use:

```json
{
  "$resolver": "exception",
  "field": "stackTrace",
  "stackTrace": {
    "stringified": true
  }
}
```

Remember to distinguish the resolver configuration from **the resolved JSON value**. In the template file, `"$resolver"` is a Log4j2 directive; in the output event file, you see the generated string or array, not an object containing `"$resolver"`.

Some older documentation versions show `"stringified": true` at the resolver level. In current Log4j2 documentation, prefer configuring `stackTrace.stringified` as shown above and check the exact version you are deploying.

## 8. Other APIs: JUL, SLF4J, and Logback

The JSON destination is not determined solely by the logger API you call. Each API has its own way of attaching a `Throwable`.

| API | Exception logging example | What determines the JSON fields? |
| --- | --- | --- |
| JUL | `logger.log(Level.SEVERE, "Failed", ex)` | Handler/Formatter, or the receiving backend/bridge |
| SLF4J | `log.error("Failed", ex)` | Provider/backend, typically Logback or Log4j2 |
| Log4j2 API | `LOG.error("Failed", ex)` | Log4j2 Core Layout, such as JsonTemplateLayout |
| `System.err.println` | Prints plain text only | No built-in JSON schema |

### 8.1. JUL `LogRecord` has its own `Throwable`

In Java Util Logging:

```java
try {
    Integer.parseInt("bad");
} catch (NumberFormatException ex) {
    logger.log(java.util.logging.Level.SEVERE,
            "Failed to parse integer", ex);
}
```

This is a snippet inside a method that already has `java.util.logging.Logger logger`. `LogRecord` holds the exception via `getThrown()`. A formatter designed for JSON can read this field and encode it into separate keys. **JUL's default `SimpleFormatter` produces plain text, not JSON**; you must use an appropriate formatter/handler or bridge to a backend with a JSON encoder.

### 8.2. SLF4J does not decide exception fields on its own

`org.slf4j.Logger` provides overloads that attach a `Throwable`, such as `log.error("Failed", ex)`. However, `slf4j-api` alone does not know whether the output is console text, a JSON file, or another target. An application using SLF4J + Logback may have `logback.xml` and an appropriate JSON encoder; an application using SLF4J + Log4j2 needs the compatible provider.

If you only add `slf4j-api` without a provider, no logs may be emitted. If multiple providers are present, the runtime schema may differ from what you expect. Always identify the actual backend before troubleshooting why exception fields are missing.

### 8.3. Logback: equivalent model, different XML

In Logback Classic, calling `log.error("Checkout failed", ex)` informs the backend that a `Throwable` is present. Whether it outputs `exception.class`, `exception.message`, `stack_trace`, or other fields depends on the chosen JSON encoder, version, and configuration. **Do not use Log4j2's `JsonTemplateLayout` inside `logback.xml`**, as it is a plugin for Log4j2 Core.

A Logback configuration using `PatternLayoutEncoder` and `%ex` can print a text stack trace, but it does not automatically turn the record into valid JSON:

```xml
<encoder>
    <pattern>%d %-5level %logger - %msg%n%ex</pattern>
</encoder>
```

This is a **Logback configuration fragment**. To produce JSON, you need an encoder/formatter that supports JSON along with explicit field mapping configuration. Encoder options and schemas vary by version; do not copy field names from Log4j2 and assume Logback will emit the exact same output.

## 9. Root Cause and Suppressed Exceptions in JSON: Intentional Design

A Java exception can contain:

```text
IllegalStateException: Payment unavailable
  caused by IllegalArgumentException: Gateway rejected
  suppressed IOException: Cleanup failed
```

A JSON schema can choose one of the following forms:

**Store only the stringified stack trace:** sufficient for reading/investigation, but hard to query individual causes separately.

**Also store root cause fields:**

```json
{
  "error.type": "java.lang.IllegalStateException",
  "error.message": "Payment unavailable",
  "error.root_cause_type": "java.lang.IllegalArgumentException",
  "error.root_cause_message": "Gateway rejected"
}
```

**Use a structured cause array if the system truly needs it:**

```json
{
  "exception": {
    "type": "java.lang.IllegalStateException",
    "causes": [
      {
        "type": "java.lang.IllegalArgumentException",
        "message": "Gateway rejected"
      }
    ]
  }
}
```

This is a **custom schema example**. Backends do not automatically guarantee `causes[]` or `suppressed[]` output unless a supporting resolver/encoder is configured. When designing your own schema, decide:

1. Will you use the outer exception, the root cause, or both for error grouping?
2. How will you limit the depth of causes/suppressed exceptions to avoid oversized events?
3. How will you represent class names, null messages, and stack frames without line numbers?
4. When an exception has no cause, will the key be omitted, set to null, or set to an empty array?
5. Could cause messages contain secrets or PII?
6. Do different services apply the same schema?

**Do not strip causes or suppressed exceptions just to make JSON shorter** if the system needs to investigate I/O or shutdown failures. At the same time, do not log unbounded data: set sensible length limits and define a truncation policy.

## 10. Exceptions Without Messages, Checked Exceptions, and `Error`

In Java, exceptions do not necessarily have a message; some types may carry dynamic messages or be wrapped by another exception. The `Throwable` type covers both `Error` and `Exception`; many logging APIs accept `Throwable` rather than only `Exception`.

Example:

```java
Throwable failure = new IllegalStateException();
System.out.println(failure.getClass().getName());
System.out.println(failure.getMessage());
```

**Stdout when run in a Java method:**

```text
java.lang.IllegalStateException
null
```

When the message is null, the JSON encoder must handle the missing value appropriately. **Do not convert null into the string `"null"` just for query convenience**, because they have different semantics.

Also avoid logging the same error twice: the same `Throwable` might be logged at ERROR in a service and logged at ERROR again in an HTTP handler, causing the pipeline to collect two independent events with the same stack trace. Choose an appropriate boundary where the exception is handled or translated into a response, write a clear event message, and preserve the cause chain.

When an error is handled as a normal business case (such as invalid user input), a stack trace at ERROR level is not always needed. The log level should match the impact, operational policy, and expected error volume.

## 11. Querying Exception Fields in Log Aggregation

The main benefit of JSON logging is **field-level querying**, not full-text scanning of stack traces.

Suppose your system stores these fields:

```json
{
  "service.name": "orders-service",
  "log.level": "ERROR",
  "error.type": "java.lang.IllegalStateException",
  "error.message": "Payment unavailable",
  "error.code": "PAYMENT_UNAVAILABLE",
  "request.id": "REQ-204"
}
```

You can build queries such as:

- Which service has the most `error.type=java.net.SocketTimeoutException` events?
- Which events did a given `request.id` appear in before the error?
- Has the ERROR rate increased for a specific deployment version?
- Is `error.code=PAYMENT_UNAVAILABLE` increasing over time or only on a single instance?
- Which high-frequency exception types do not yet have alerts?

**Do not group all errors solely by `error.message`**: messages can contain order IDs, URLs, addresses, or dynamic values, creating an enormous number of groups (*high cardinality*). Relatively stable fields such as `service.name`, `error.type`, `error.code`, or a controlled fingerprint are usually better suited for aggregation.

In `jq`, when the field is a literal key:

```bash
jq -r 'select(."log.level" == "ERROR") | ."error.type"' logs/events.jsonl
```

For a nested schema `{"error":{"type":"..."}}`, the query is different:

```bash
jq -r 'select(.level == "ERROR") | .error.type' logs/events.jsonl
```

Both commands are **schema-dependent query patterns**; do not run one arbitrarily and conclude the data is missing. In Elasticsearch/OpenSearch, Loki, Splunk, Datadog, or other collectors, indexing behavior and query syntax also differ.

## 12. Exception Fields and Correlation IDs

An error event with a stack trace but no context can still be hard to investigate when many requests are processed concurrently. Therefore, combine exception fields with **correlation IDs**:

```json
{
  "service.name": "orders-service",
  "request.id": "REQ-204",
  "trace.id": "8c9e89f60b014eee9bc2c6f4d6b43d16",
  "log.level": "ERROR",
  "message": "Order failed",
  "error.type": "java.lang.IllegalStateException"
}
```

This is **illustrative data**. Sharing a request ID lets you find events before and after the error; `trace.id` can link to distributed tracing when tracing is integrated.

In Log4j2, `ThreadContext.put("requestId", value)` can add an MDC/context field. However:

- The context map does not automatically propagate to other threads or `CompletableFuture` tasks.
- If using thread pools, you must **clear the context** in a `finally` block or an appropriate auto-closeable scope.
- The template/encoder must be configured to output the required keys.
- Logging a trace ID in JSON **does not automatically create a span or distributed trace**.
- Do not use sensitive data such as tokens or user session IDs as correlation IDs.

A large exception log may be truncated by a collector, while earlier events hold the needed context. In addition to the stack trace, include controlled business milestones and IDs to trace the execution flow.

## 13. Cost and Size: You Do Not Always Need the Full Stack Trace

A single stack trace can take thousands or tens of thousands of characters. When errors occur hundreds of times per second, storing the full trace for every event increases:

- CPU usage from generating and formatting stack traces.
- Memory usage and allocations during serialization.
- I/O to files, stdout, or network sinks.
- Storage volume and indexing/search costs.
- Risk of truncation at the collector or hitting event size limits.
- Dashboard and alert noise if the same error repeats continuously.

Ways to optimize:

1. **Choose the right log level:** frequently handled errors may only need WARN or INFO depending on their semantics.
2. **Log exceptions at the right boundary:** do not generate three ERROR stack traces across three layers when one suffices.
3. **Add a stable error code:** enables aggregation without reading the entire stack.
4. **Use sampling/rate limiting where appropriate:** be explicit about which cases are always retained in full, especially rare incidents or audit requirements.
5. **Limit length intentionally:** if you must truncate stack traces, include a truncation indicator and keep enough of the cause to remain useful.
6. **Monitor collector truncation limits:** the layout may produce valid JSON, but a byte limit in the collector can corrupt the record or drop trailing fields.
7. **Separate critical transaction events from diagnostic logs:** logging does not replace durable transaction storage.

With Log4j2 `JsonTemplateLayout`, the `stackTraceEnabled` setting can control stack trace emission; common default templates enable stack traces. Limits such as `maxStringLength` apply to string values, **not necessarily to the entire JSON object**. Check the documentation for your exact version and verify the actual output when making changes.

## 14. Security and Privacy of Exception Fields

**Exception messages and stack traces easily leak sensitive data.** An exception from an HTTP client, JDBC driver, filesystem, or authentication library can carry:

- URLs with query strings containing tokens.
- Internal filesystem paths, hostnames, or account names.
- SQL statements, table names, or input data.
- Request headers, cookies, or payloads.
- Details about application structure and library versions.

Even if your log `message` is written safely, **`error.message` or `error.stack_trace` can still contain sensitive data** from a `Throwable` created by another library.

Protection principles:

- Avoid putting secrets, passwords, access tokens, API keys, session cookies, or card data into exception messages whenever possible.
- Do not log raw request bodies alongside stack traces just to debug a routine error.
- When identifying information must be logged, use approved, controlled IDs and avoid unnecessary personal data.
- Consider redaction/masking at both source and pipeline, but **test the event message, error message, root cause, and stack trace**.
- Enforce access controls and retention policies on JSON files, log collectors, search stores, and dashboards.
- Ensure proper encoding/JSON escaping so untrusted input cannot forge fields or new log records.
- Do not make exception data publicly queryable simply because the application writes logs to stdout.
- If full stack traces must be stored for severe incidents, protect them at the same level as sensitive internal data.

**Do not assume that replacing `getMessage()` with `getClass().getSimpleName()` is sufficient for security.** Root causes, stack traces, and context fields can still expose sensitive data. Schema design and data minimization must account for the entire event.

## 15. Common Pitfalls and Troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| JSON has `message` but no `error.type` | Only logged a string without passing the Throwable | Use the overload that accepts Throwable; check encoder |
| `error.type` is present, but `error.stack_trace` is missing | Layout disabled stack traces or template omits the field | Check `stackTraceEnabled` / event template |
| `error.message` is null | Throwable has no message | Handle null/missing per schema; do not force a fake string |
| One error emits two JSON records | Same exception logged at multiple layers, or duplicate additivity/appender | Trace call paths and logging boundaries |
| JSONL file fails to parse | Plain text interleaved or stack trace contains unescaped newlines | Use a real JSON encoder and validate line by line |
| Querying `.error.type` returns nothing | JSON uses literal key `"error.type"`, not a nested object | Use `."error.type"` or query matching the actual schema |
| Error message contains sensitive data | Exception created with URL/query/token or client input | Redact/minimize data at source and sink |
| Grouping by message creates thousands of groups | Message contains dynamic IDs or URLs | Group by type, code, or stable fingerprint |
| Cause is not emitted separately | Template only uses `exception` resolver, not `exceptionRootCause` | Add root cause fields if needed |
| Suppressed exception does not appear as a field | Encoder does not support a separate suppressed array | Check stringified stack trace or custom schema |
| `events.jsonl` file is not created | Wrong path, write permissions, config not loaded, missing Core | Check runtime classpath, appender/status logs |
| `JsonTemplateLayout` plugin not recognized | Missing `log4j-layout-template-json` or version mismatch | Add matching dependency and check startup errors |
| Code logs via SLF4J but no exception fields appear | Actual runtime provider/backend differs from expected | Inspect dependency tree and runtime provider |
| JSON is truncated at the end | Process crash, file/collector size limit, unflushed buffer | Check lifecycle, size limits, parser, and pipeline |
| Field names do not match documentation | Using a different template or backend schema | Verify exact `eventTemplateUri` and config file |

### Diagnostic checklist

1. Which **API** is the code calling: JUL, SLF4J, Log4j2, or direct text printing?
2. Is the **full Throwable** passed to the logger?
3. What is the actual backend/provider, and does it support a JSON layout/encoder?
4. Does the active schema define `error.type`, `exception.type`, or another field?
5. Are the configuration file and JSON template loaded from the runtime classpath?
6. Are there normal events without a Throwable to verify how missing/null fields behave?
7. For exceptions with causes, are both the outer type and root-cause type correct?
8. Does the stack trace retain the needed frames and causes, or is it truncated?
9. Does every line in the JSONL file parse as valid JSON?
10. Do exception fields, MDC, or log files leak sensitive information?
11. Do ERROR events include request/trace IDs when needed for investigation?
12. Before signing off on QA, verify the output of the **actual deployed version**, not just the intended configuration.

## 16. Knowledge Check

**Q1.** Why are exception fields more useful than just writing `exception.toString()` inside the message?  
**Answer:** They separate type, message, and stack trace into distinct fields that can be searched, filtered, grouped, and formatted independently.

**Q2.** How do the event `message` and `error.message` differ?  
**Answer:** The event message describes the operation context; the exception message comes from `Throwable.getMessage()`. They can be different.

**Q3.** Does calling `LOG.error("Failure: " + ex.getMessage())` guarantee creating an `error.type` field?  
**Answer:** No. It only passes a string; you should pass the full Throwable using the appropriate overload.

**Q4.** Can a multi-line stack trace be stored in JSON Lines?  
**Answer:** Yes. The serializer escapes newlines as `\n` inside the JSON string so that each event remains a single physical line.

**Q5.** Do `"error.type"` and `{"error":{"type":...}}` have the same JSON structure?  
**Answer:** No. One uses a literal key containing a dot, while the other is a nested object.

**Q6.** If a Throwable has no message, should you write `"error.message":"null"`?  
**Answer:** Not arbitrarily. Null and missing values have distinct semantics; follow the schema and encoder rules.

**Q7.** What does Log4j2's `exceptionRootCause` do?  
**Answer:** It extracts data from the deepest Throwable in the cause chain, helping distinguish the outer wrapper exception from the underlying cause.

**Q8.** Why can `error.stack_trace` pose a privacy risk?  
**Answer:** Stack frames and exception messages can contain URLs, file paths, input data, service names, or secrets included in the error.

**Q9.** Is adding `slf4j-api` enough to emit JSON exception fields?  
**Answer:** No. You also need a provider/backend and an encoder/layout with an appropriate schema.

**Q10.** What `jq` syntax queries the literal key `"error.type"`?  
**Answer:** Use `."error.type"` or `.["error.type"]`; `.error.type` only works for a nested object.

**Q11.** If an ERROR event has a cause, does every encoder automatically produce a `causes[]` array?  
**Answer:** No. Some encoders only output a stringified stack trace; a structured array requires a matching schema and resolver.

**Q12.** Why is it useful to have a business error code in addition to the exception type?  
**Answer:** The exception type only identifies the error class, whereas a stable error code helps distinguish business scenarios and aggregate alerts.

**Key takeaway:** **Exception fields turn a `Throwable` into structured JSON data**. To do this properly, pass the full `Throwable` to the logger, choose a consistent schema, and let a dedicated encoder produce `type`, `message`, `stack_trace`, and root cause when needed. Validate real JSON Lines output, handle missing/null fields according to their semantics, and always protect sensitive data inside exceptions.
