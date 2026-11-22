# The logger Field in JSON Logging: Log Source Name and Proper Usage

## Learning Objectives

In JSON logging, a record typically includes fields such as **timestamp**, **level**, **message**, **logger**, **thread**, **service.name**, and **traceId**. Among these, the **logger field** indicates **the logger name used to emit the event**. This is an important field when you want to search logs by package, class, module, or functional group rather than searching only by keywords in the message.

This lesson belongs to the **JSON logging** group in **Java Core Logging** and focuses directly on the **“logger field”**. After this lesson, you will be able to:

- Accurately explain the meaning, origin, and data type of the **logger** field.
- Distinguish the **logger name** from the actual class invoking the log statement, thread, service, level, message, MDC, and log file path.
- Know how to create logger names using **SLF4J**, **Logback**, and **java.util.logging (JUL)**, and how that name flows into a JSON encoder/formatter.
- Understand why a backend might output the field under the name **logger**, **logger_name**, or **log.logger**, and how to normalize the schema during ingestion.
- Run two **Java 17+** examples: a JDK-only JUL example with an illustrative JSON Formatter; and a practical SLF4J + Logback + JSON encoder example with Maven that reads back the JSON using Jackson.
- Verify the logger field using a parser rather than plain string matching, handle missing/renamed/wrong-type fields, and avoid MDC collisions and untrusted-data risks.
- Design a stable, easily queryable logger name convention with reasonable cardinality across a multi-service system.

**Terminology note:** “field logger” / “the logger field” in this lesson refers to **the logger field inside a JSON log event**. It is not synonymous with **the Java member variable** commonly declared as **private static final Logger LOG**, although the LOG variable is the object that produces the logger name appearing in the event.

## 1. What Is the logger Field?

Example of a JSON log event:

~~~json
{
  "@timestamp": "2026-11-09T13:20:30.123Z",
  "level": "INFO",
  "logger": "com.example.checkout.OrderService",
  "thread": "http-worker-4",
  "message": "event=order.created orderId=OD-42",
  "requestId": "req-17"
}
~~~

In this event:

- **logger** is a JSON string with the value **com.example.checkout.OrderService**.
- It identifies **the logger identifier** that the code used to emit the event.
- **level** indicates the severity of the record (INFO).
- **message** describes the event, not the logger source.
- **thread** indicates the name of the thread associated with the event.
- **requestId** is contextual information for a request, typically obtained from MDC or a correlation mechanism.
- **@timestamp** is the event timestamp following the encoder/backend convention.

The JSON above is an **illustrative schema example**, not the fixed default output of every Java logger. In some backends, the actual field name is **logger_name**; in some schemas, it resides inside a **log** object as **log.logger**.

Key takeaway:

**The logger field = the identifier name of the logger object used to write the event; it is not the log file name, not the message, and not automatically the name of the class currently executing.**

Why is this name needed? When millions of log lines from many packages are sent to a centralized system, you can filter:

~~~text
All records emitted from com.example.checkout.OrderService
All records under the com.example.checkout branch
All ERRORs from com.example.payment.PaymentClient
~~~

The logger name helps **narrow down the relevant code/module** before reading the message and stack trace.

## 2. Where Is the Logger Name Created?

Depending on the logging API, Java code can obtain a logger **by class** or **by string name**.

### SLF4J: obtaining a logger by Class

~~~java
// Illustration in the class com.example.checkout.OrderService.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
~~~

In SLF4J, **LoggerFactory.getLogger(Class)** creates/retrieves a logger named after **Class.getName()**. If the class is **com.example.checkout.OrderService**, the common logger name is also:

~~~text
com.example.checkout.OrderService
~~~

Therefore, the JSON encoder can write:

~~~json
{"logger":"com.example.checkout.OrderService"}
~~~

### SLF4J: obtaining a logger by custom name

~~~java
// Illustration; LOG is of type org.slf4j.Logger.
org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger("checkout.workflow");
~~~

In that case, the logger field can be:

~~~json
{"logger":"checkout.workflow"}
~~~

**This is a custom name, not a Java class name.** Do not build a parser that tries to turn every logger value into a loadable class. A logger name can be a category, package, subsystem, or framework-managed name.

### JUL: obtaining a logger by name

~~~java
// Illustration; the java.util.logging API is built into the JDK.
java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger("com.example.checkout.OrderService");
~~~

When JUL creates a **LogRecord**, the record provides **getLoggerName()** with the corresponding name. A custom Formatter or JSON encoder for JUL can read that information to produce the JSON field.

### Log4j 2: same naming principle

In Log4j 2, obtaining a logger by Class or by name also provides a **logger name** for the backend to process and for a JSON serializer to output. However, property names, encoder/layout configuration, and serialization behavior are implementation-specific details. Do not copy a **logback.xml** file to Log4j 2 and assume it will automatically understand the same configuration.

**Practical rule:** business code should use a stable logger name by class or module, while the backend/encoder is responsible for outputting that name under the chosen schema's key.

## 3. How Does the logger Field Differ from Other Fields?

| Field | Example value | Question answered | Do not confuse with |
| --- | --- | --- | --- |
| **logger** | com.example.checkout.OrderService | Which logger emitted the event? | File name or source code line |
| **logger_name** | com.example.checkout.OrderService | Same meaning in a different schema | A different logger |
| **log.logger** | com.example.checkout.OrderService | Logger name in ECS | A literal dotted string in every JSON style |
| **level** | INFO | What severity level? | Logger name |
| **message** | event=order.created orderId=OD-42 | What was recorded? | Logger name or structured data by default |
| **thread** | http-worker-4 | Which thread created the record? | Request ID or logger |
| **service.name** | checkout-api | Which service is running the code? | Logger name |
| **traceId** | 2d3d... | Which distributed trace? | Logger name |
| **requestId** | req-17 | Which specific request? | Logger name |
| **class** or **caller_class** | com.example.infrastructure.LoggingHelper | Actual caller inferred by the backend | Logger name if a custom name is used |
| **file** / **log.file.path** | /var/log/app.jsonl | Which file stores/collects the record? | Logger name |
| **exception** | NumberFormatException | Which error accompanies the event? | Logger name |

There is an important trap: **logger name and caller class can be identical, but they are not the same data**.

If the **PaymentService** class calls a helper that uses a logger named **checkout.workflow**, the JSON might contain:

~~~json
{
  "logger": "checkout.workflow",
  "message": "event=payment.authorized"
}
~~~

Do not infer that the executing Java source file is **checkout.workflow.java**. This is simply a category chosen by the developer.

**The logger name is also not an instance object ID.** A logger is typically held in a static final variable and reused across many requests. Two events with the same logger may belong to two completely different users, threads, or transactions.

## 4. The logger Field in a JSON Pipeline

A conceptual pipeline with SLF4J and Logback:

~~~mermaid
flowchart LR
    A["Java Code: LOG.info"] --> B["SLF4J API"]
    B --> C["Logback LoggingEvent"]
    C --> D["JSON encoder"]
    D --> E["JSON with logger/level/message"]
    E --> F["Console or file"]
    F --> G["Collector / Search backend"]
~~~

Step by step:

1. Code obtains a Logger via **LoggerFactory.getLogger(...)** and emits an event.
2. SLF4J forwards the request to the compatible provider/backend.
3. Logback receives the event with the **logger name**, level, message, timestamp, and other metadata.
4. The JSON encoder chooses which fields to include in JSON, which keys to use, and how to escape data.
5. The appender writes the JSON bytes to a file, stdout, or another destination.
6. The collector or ingest pipeline parses/indexes those fields.

During this process, the **logger name** is already present on the logging event. The encoder **does not need to guess it with a regex on the message**. If the output JSON is missing the logger field, the cause may be that **the encoder does not output this field, the schema renamed it, the field was excluded, or the collector transformed/dropped it**; it does not necessarily mean the code failed to create a logger.

### Logger name and additivity/level

In many frameworks, package/class-based logger names also serve as **the basis for applying log levels by namespace**. For example, enabling DEBUG for the checkout package while keeping root at INFO.

However, **the logger field in JSON is only exported data**. It does not itself decide which records get emitted. Log levels, filters, appenders, and backend configuration have already acted before or during writing. Enabling/disabling the logger field in JSON **does not mean** enabling/disabling logging for that package.

## 5. Field Names: logger, logger_name, and log.logger

A common integration mistake is services recording the same concept using different keys:

~~~json
{"logger":"com.example.checkout.OrderService","message":"event=order.created"}
~~~

~~~json
{"logger_name":"com.example.checkout.OrderService","message":"event=order.created"}
~~~

~~~json
{"log":{"logger":"com.example.checkout.OrderService"},"message":"event=order.created"}
~~~

Semantically, all three can hold the **logger name**. However, their JSON schemas and queries **differ**. You cannot use the same **.logger** access path to retrieve all three unless the parser normalizes them.

- **logger**: top-level key chosen by the team, used in this lesson's examples.
- **logger_name**: default key of **LogstashEncoder** from the logstash-logback-encoder library for Logback.
- **log.logger**: field described in **Elastic Common Schema (ECS)**. When represented as nested JSON, you may see **{"log":{"logger":"..."}}**; depending on the ingest pipeline, how dotted and nested keys are mapped must be explicitly defined.

**There is no rule requiring every Java JSON logging system to use the exact key logger.** A system may follow ECS or an internal schema. What matters is **standardizing the key, data type, and mapping before relying on dashboards/alerts**.

### Suggested schema for a small application

~~~json
{
  "@timestamp": "2026-11-09T13:20:30.123Z",
  "level": "INFO",
  "logger": "com.example.checkout.OrderService",
  "service": "checkout-api",
  "message": "event=order.created orderId=OD-42",
  "requestId": "req-17"
}
~~~

**This is an illustrative schema chosen by a team**, not a fixed structure of SLF4J. If your organization uses ECS, prefer standard fields such as **log.logger**, **log.level**, and **service.name** as supported by your encoder/ingest pipeline. Avoid trying to output **logger**, **logger_name**, and **log.logger** simultaneously “just to be safe”: duplicated data complicates dashboards and increases cost.

## 6. Hands-on 1 — Java 17, JUL, and the JSON logger Field

The first example requires only JDK 17. It uses **java.util.logging.Logger** and **LogRecord.getLoggerName()**, attaching a **StreamHandler** to an in-memory buffer and a custom Formatter to output three fields: logger, level, and message.

**Scope warning:** This Formatter is a **learning model** showing how the logger name comes from LogRecord. It includes an escaping helper for basic JSON strings; **do not build your own production JSON serializer** when Jackson or an official JSON encoder is available. A general-purpose serializer must also handle all data types, malformed Unicode, arrays/objects, exception structures, and consistent schemas.

Create the file **LoggerFieldDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggerFieldDemo {
    private static final Logger LOG =
            Logger.getLogger("com.example.checkout.OrderService");

    private static String jsonString(String source) {
        StringBuilder result = new StringBuilder("\"");
        for (int i = 0; i < source.length(); i++) {
            char c = source.charAt(i);
            switch (c) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (c < 0x20) {
                        result.append(String.format("\\u%04x", (int) c));
                    } else {
                        result.append(c);
                    }
                }
            }
        }
        return result.append('"').toString();
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        StreamHandler handler = new StreamHandler(buffer, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return "{\"logger\":" + jsonString(record.getLoggerName())
                        + ",\"level\":" + jsonString(record.getLevel().getName())
                        + ",\"message\":" + jsonString(formatMessage(record))
                        + "}\n";
            }
        });
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.INFO);

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(handler);
        try {
            LOG.log(Level.INFO, "event=order.created orderId={0}", "OD-42");
            LOG.warning("event=payment.retry attempt=2");
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.print(buffer.toString(StandardCharsets.UTF_8));
    }
}
~~~

Compile and run:

~~~bash
javac LoggerFieldDemo.java
java LoggerFieldDemo
~~~

**Exact stdout from running the program on JDK 17+:**

~~~json
{"logger":"com.example.checkout.OrderService","level":"INFO","message":"event=order.created orderId=OD-42"}
{"logger":"com.example.checkout.OrderService","level":"WARNING","message":"event=payment.retry attempt=2"}
~~~

This is the **JSON Lines / NDJSON** format: each independent line is one JSON object. Do not treat two adjacent objects as a single JSON document; readers must parse **line by line** or use an NDJSON parser.

### Analyzing the JUL example

1. The logger is obtained from **Logger.getLogger("com.example.checkout.OrderService")**, so **record.getLoggerName()** carries that name in the emitted calls.
2. **Formatter.format(LogRecord)** receives the record and builds JSON with the keys **logger**, **level**, and **message**. With JUL, **getLevel().getName()** returns names such as INFO/WARNING.
3. **formatMessage(record)** resolves JUL parameter patterns; in this example, **{0}** is replaced with **OD-42**. Do not confuse this placeholder with SLF4J's **{}**.
4. **jsonString(...)** escapes quotes, backslashes, newlines, carriage returns, tabs, and low control characters, preventing syntax breakage when a message contains those characters. It is not a general-purpose serializer.
5. **StreamHandler** writes to a ByteArrayOutputStream rather than directly to a file/console. After **handler.close()**, the program reads the buffer and prints to stdout.
6. **setUseParentHandlers(false)** prevents records from propagating to parent handlers and producing duplicate output. Both Logger and Handler are set to INFO so both events are accepted.
7. Timestamps are omitted so the output is not time-dependent. In real systems, a JSON record typically needs timestamp/trace/service according to a unified schema.

**Limitation:** this example illustrates **how the logger field is generated from a logging event**; it does not prove that every backend uses the same schema. When moving to Logback, choose a JSON encoder that already handles escaping/serialization and configuration management.

## 7. Hands-on 2 — SLF4J + Logback + JSON Encoder

The next example is closer to production usage: Java code calls only the **SLF4J API**, Logback serves as the backend, and **logstash-logback-encoder** produces JSON. The default **logger_name** field is **renamed to logger** via LogstashEncoder's **fieldNames** configuration.

This example was tested with **Java 17, Logback Classic 1.5.18, and logstash-logback-encoder 8.0**. These versions are pinned for the lesson, not necessarily the latest releases; real projects should check their BOM, compatibility, and update policy. **Jackson** is also pulled in via the encoder's dependencies so the example's parser can read the JSON.

### Project structure

~~~text
logger-field-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── logging/
        │               └── LogbackLoggerFieldDemo.java
        └── resources/
            └── logback.xml
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>logger-field-demo</artifactId>
  <version>1.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>ch.qos.logback</groupId>
      <artifactId>logback-classic</artifactId>
      <version>1.5.18</version>
    </dependency>
    <dependency>
      <groupId>net.logstash.logback</groupId>
      <artifactId>logstash-logback-encoder</artifactId>
      <version>8.0</version>
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

### File src/main/resources/logback.xml

~~~xml
<configuration>
  <appender name="JSON" class="ch.qos.logback.core.FileAppender">
    <file>target/logger-field.jsonl</file>
    <append>false</append>

    <encoder class="net.logstash.logback.encoder.LogstashEncoder">
      <fieldNames>
        <logger>logger</logger>
      </fieldNames>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="JSON"/>
  </root>
</configuration>
~~~

Explanation:

- **FileAppender** writes JSON Lines to **target/logger-field.jsonl**. The target directory is created after the Maven compile step.
- **LogstashEncoder** produces syntactically valid JSON records and provides standard fields.
- **fieldNames / logger** **renames the output field** from the default **logger_name** to **logger**. It does not change the Logger object's name inside the application.
- **append=false** ensures the test has only one record without mixing previous runs. In production, an appropriate append/rolling/retention policy is required.
- **root INFO** allows INFO and more severe levels through the appender; backends may have additional filters in real systems.

**If you omit the fieldNames block above**, LogstashEncoder will typically output **logger_name** per its default schema, rather than **logger**. This is an important difference when a dashboard expects a specific key.

### File src/main/java/com/example/logging/LogbackLoggerFieldDemo.java

~~~java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class LogbackLoggerFieldDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger("com.example.checkout.OrderService");

    public static void main(String[] args) throws Exception {
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        MDC.put("requestId", "req-17");
        try {
            LOG.info("event=order.created orderId={}", "OD-42");
        } finally {
            MDC.remove("requestId");
            context.stop();
        }

        List<String> lines = Files.readAllLines(
                Path.of("target", "logger-field.jsonl"), StandardCharsets.UTF_8);
        JsonNode event = new ObjectMapper().readTree(lines.get(0));

        System.out.println("records=" + lines.size());
        System.out.println("logger=" + event.path("logger").asText());
        System.out.println("level=" + event.path("level").asText());
        System.out.println("message=" + event.path("message").asText());
        System.out.println("requestId=" + event.path("requestId").asText());
        System.out.println("hasLoggerName=" + event.has("logger_name"));
        System.out.println("loggerIsText=" + event.path("logger").isTextual());
    }
}
~~~

### Maven run command

In the directory containing pom.xml:

~~~bash
mvn -q compile exec:exec "-Dexec.executable=java" "-Dexec.args=-classpath %classpath com.example.logging.LogbackLoggerFieldDemo"
~~~

The Maven Exec Plugin launches a **child JVM** and provides the project's classpath. This separates the program's logging backend from Maven's own logging. The command requires Maven and its dependencies to be validly downloaded/cached.

**Exact verified stdout of the program:**

~~~text
records=1
logger=com.example.checkout.OrderService
level=INFO
message=event=order.created orderId=OD-42
requestId=req-17
hasLoggerName=false
loggerIsText=true
~~~

These lines are **stdout printed by the JSON-checking program**, not the entire JSON written to the file. In the actual file, there may also be **@timestamp, @version, thread_name**, and other fields supported by LogstashEncoder. Values such as timestamp are not hardcoded into the expected output because they depend on execution time.

### Why is this result trustworthy?

1. **LOG** is named **com.example.checkout.OrderService**, even though the main class running the example is **LogbackLoggerFieldDemo**. This proves the logger field **does not have to be the caller class name**.
2. **LogstashEncoder** includes the logger name in the JSON output. **fieldNames** renames the key to **logger**.
3. **Jackson ObjectMapper.readTree** parses the record into a JsonNode; **loggerIsText=true** proves the field has the JSON string type, not merely a grepped substring.
4. **hasLoggerName=false** shows that when renamed properly, the default **logger_name** field does not simultaneously exist in the demo's record.
5. **requestId=req-17** comes from MDC; it is distinct from the logger name and has a per-request lifecycle.
6. **level=INFO** is the event severity; **message** is the content resolved by SLF4J for the **{}** placeholder.
7. **context.stop()** closes the logging context before the file is read, reducing the chance of reading incomplete data. Stopping does not by itself guarantee fsync/durable ingestion across external systems.
8. The example uses a **JSON parser**, not comma or colon splitting, because valid JSON strings can contain those characters.

**Lifecycle warning:** casting ILoggerFactory to Logback's LoggerContext is only valid when the backend is actually Logback Classic. If the application uses another SLF4J provider, code must use the appropriate lifecycle or let the framework manage logging. In a real application, do not stop the global logging context after every request; stop it only during full application shutdown.

## 8. Default Logger Field in LogstashEncoder

The official **logstash-logback-encoder** documentation lists the standard fields of LogstashEncoder, including:

| Default name | Meaning |
| --- | --- |
| **@timestamp** | Timestamp of the logging event |
| **@version** | Logstash format version |
| **message** | Message after parameter formatting |
| **logger_name** | Name of the logger emitting the event |
| **thread_name** | Thread associated with the event |
| **level** | Level as text |
| **level_value** | Numeric severity value if configured in the output |

You can use **fieldNames** to rename standard fields. The XML element **logger** is the configuration property name for the logger name, **not logger_name**:

~~~xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder">
  <fieldNames>
    <logger>logger</logger>
  </fieldNames>
</encoder>
~~~

This is a **configuration fragment** that must be placed inside an appropriate appender. Some library versions have different configuration options; check the documentation matching your actual dependency.

Besides LogstashEncoder, **LoggingEventCompositeJsonEncoder** allows selecting individual providers. When using the composite encoder, the list of fields depends on the declared providers; **do not assume logger_name is always present automatically**.

An illustrative composite configuration:

~~~xml
<encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
  <providers>
    <timestamp/>
    <loggerName>
      <fieldName>logger</fieldName>
    </loggerName>
    <logLevel/>
    <message/>
  </providers>
</encoder>
~~~

This block shows selecting providers for timestamp, loggerName, level, and message. **Do not place both LogstashEncoder and a composite encoder in the same appender** just to produce two logger name keys; choose one clear output schema strategy.

**Recognition tip:** in Logback's text-based PatternLayout, the **%logger** converter outputs the same logger name; when you need a **JSON field**, use a proper JSON encoder/provider instead of manually wrapping **%logger** in quotes.

## 9. Should You Shorten Logger Names in JSON?

A full class-based logger name such as:

~~~text
com.example.checkout.internal.service.OrderValidationService
~~~

can be long, yet informative. Some encoders support shortening, such as **shortenedLoggerNameLength** in logstash-logback-encoder. However, shortening should be weighed carefully.

**Benefits:**
- Fewer bytes in logs for high-volume systems.
- Easier to read in terminals or narrow-column tables.

**Risks:**
- Two different classes may have shortened forms that are hard to distinguish.
- Dashboards filtering by full logger name may stop matching.
- Changing the algorithm/version can alter field values even when code has not changed.
- Tracing from the logger back to the source class can become harder.

If your centralized logging system bills by volume, you can consider shortening to save cost, but first decide **whether you truly need the full class name for querying**. For debugging and incident investigation, full logger names are usually valuable.

**Do not include requestId or userId in a logger name** just to avoid declaring separate fields. For example, **checkout.req-17.user-42** creates a huge number of logger values and makes logger-based level configuration hard to manage. RequestId/traceId belong to **context fields**, not long-lived logger identifiers.

## 10. The logger Field in ECS and Distinguishing Fields

Elastic Common Schema has the **log.logger** field to indicate the logger name inside the application, typically the class creating the logger or a custom name.

An ECS-style JSON object can be represented as:

~~~json
{
  "@timestamp": "2026-11-09T13:20:30.123Z",
  "log": {
    "level": "INFO",
    "logger": "com.example.checkout.OrderService"
  },
  "service": {
    "name": "checkout-api"
  },
  "message": "event=order.created"
}
~~~

Distinguish it from these ECS fields:

- **log.logger**: application logger name.
- **log.level**: textual severity.
- **log.file.path**: path to the file from which the event was read; not the logger name. If the event did not come from a file, do not fabricate a dummy value.
- **log.origin.file.name / log.origin.file.line**: source code location information that may be collected at an extended level; different from the logger name.
- **service.name**: identity of the service running the application.
- **process.thread.name**: thread, if the pipeline maps data according to that schema.

**Do not treat logger name as service.name**: a single service can have hundreds of loggers. Conversely, multiple services can use a library with the same logger name; to distinguish the source, combine **service.name, deployment environment, pod/host/instance, and timestamp** according to your chosen schema.

If your system uses **OpenTelemetry**, note that the logger name may be mapped via **InstrumentationScope** in the data model, not always emitted under a top-level **logger** key. Verify your ingest pipeline/OTLP exporter and target schema before comparing fields.

## 11. Searching and Aggregating by the logger Field

Once the data is **valid JSON Lines**, you can use a JSON parser to extract the field.

### Examples with jq

Suppose **application.jsonl** contains JSON objects with a top-level logger field:

~~~bash
jq -r '.logger' application.jsonl
~~~

The command above prints the logger value of each record. If a record is missing the field, jq typically prints **null**, so do not treat null as a real logger.

Filter for an exact class:

~~~bash
jq -c 'select(.logger == "com.example.checkout.OrderService")' application.jsonl
~~~

Filter for a package group:

~~~bash
jq -c 'select((.logger // "") | startswith("com.example.checkout."))' application.jsonl
~~~

The **(.logger // "")** expression avoids errors when the field is absent or null in simple records. If data may contain a non-string logger (object/number), check the type before calling startswith or normalize the schema at ingest.

**Note:** jq is an external tool outside the JDK; the examples only run if jq is installed. JSONL must have one complete object per line; files containing multiline text stack traces or corrupted concatenated data will not parse properly.

### With nested JSON fields

If the schema is:

~~~json
{"log":{"logger":"com.example.checkout.OrderService"}}
~~~

then the jq query path is:

~~~bash
jq -r '.log.logger' application.jsonl
~~~

If the JSON has a literal top-level key named **"log.logger"**, the syntax must differ:

~~~bash
jq -r '.["log.logger"]' application.jsonl
~~~

This is a small detail that easily leads to wrong conclusions. A document with **{"log":{"logger":...}}** is not structurally identical to **{"log.logger":...}**; how the search backend handles dotted fields also depends on mapping/ingest.

### In a centralized system

You can build dashboards for:

- Event counts by logger name and level.
- Top loggers with the most WARN/ERROR events in a service.
- Error growth rate in the checkout package.
- Logs of a specific logger before/after deployment.
- Loggers emitting the most DEBUG events to optimize cost.

However, **the logger field alone is not enough** for a multi-service incident. Combine service.name, traceId/requestId, timestamp, and environment. Also note that **logger** is a categorical string value (keyword/category), not a numeric quantity to sum or average.

## 12. The logger Field and MDC: Avoiding Overwrites and Key Collisions

MDC is used to attach execution context, typically **requestId**, **traceId**, or an allowed **tenantId**. The logger name comes from the **Logger object**; these two sources serve different purposes.

Example:

~~~java
// Illustration in Java using SLF4J.
org.slf4j.MDC.put("requestId", "req-17");
try {
    LOG.info("event=order.created");
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

A JSON encoder can output:

~~~json
{
  "logger": "com.example.checkout.OrderService",
  "requestId": "req-17",
  "message": "event=order.created"
}
~~~

**Do not do this just to change the logger name:**

~~~java
// Example of misuse because it causes a schema collision.
org.slf4j.MDC.put("logger", "special-value");
~~~

In some JSON encoders, MDC entries are emitted as top-level fields. If an MDC key is also named **logger**, it can produce **two JSON properties with the same name**, overwrite values, or cause parser/serializer-dependent behavior. A JSON object with duplicate keys should be avoided; downstream systems may keep the first value, the last value, or raise an error.

**The right approach:** let the encoder take the logger field from the logging event, use MDC for correlation/metadata, and choose non-colliding field names. If you need to rename the logger field, do so via **fieldNames/provider configuration**, not via arbitrary MDC keys.

In thread-pool systems, clean up MDC promptly; a new request may inherit stale values if a thread is reused and the context is not cleared. By contrast, the **logger name** is tied to the Logger and does not normally change per request. Do not use the logger field as a substitute for propagating context across async boundaries.

## 13. Logger Name Stability and Cardinality

A good design typically has these characteristics:

| Rule | Why it helps | Example |
| --- | --- | --- |
| **Package/class-based name** when appropriate | Easy to trace back to source and configure hierarchy | com.example.checkout.OrderService |
| **Intentional custom name** | Represents a subsystem spanning class boundaries | checkout.workflow |
| **No dynamic IDs** | Limits cardinality and config clutter | Do not use checkout.user-12345 |
| **No secrets/PII** | Avoids leaking data in a heavily indexed field | Do not use email/token as logger name |
| **Stable across environments** | Queries/dev/prod can share the same config | Keep logger name across deployments |
| **Consistent JSON string type** | Parsers and indexers avoid mixed-type handling | logger is always a string |
| **Defined fallback convention** | Reduces unexplained null/missing fields | Follow encoder/ingest policy |
| **Separate service identity** | Distinguishes two services sharing a library | service.name independent of logger |

In a multi-module application, a naming structure like **com.example.feature.Component** enables selective DEBUG logging in the backend. If every class shares a single logger name **app**, package/class filtering loses its effectiveness and incident investigation becomes harder.

At the same time, do not try to turn every log call into a new logger. Dynamic logger names consume resources and make the namespace hard to manage. Choose stable class names or a finite, meaningful set of categories.

## 14. When the logger Field Has an Unexpected Value

Some real-world scenarios:

**Scenario A: logger has the helper's name instead of the business class**

~~~java
// Illustration: LoggingHelper holds the logger and multiple services share it.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(LoggingHelper.class);
~~~

If code inside the helper emits events for every service, the logger name may always be **LoggingHelper**. If you need to trace the calling service, design per-class loggers or pass an explicit category; do not enable caller data as an automatic fix without considering its cost.

**Scenario B: logger is a custom name**

~~~java
org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger("payment.events");
~~~

This is a valid name. Do not report “wrong class name” simply because no Java class named payment.events exists.

**Scenario C: all records show ROOT**

Some records may use the root logger. This is not automatically a JSON encoder bug. However, if every module logs through root, you lose the ability to group by source; review how Loggers are obtained.

**Scenario D: class is renamed/refactored**

When code uses **LoggerFactory.getLogger(MyClass.class)**, the logger name changes with the Class name after refactoring. Dashboards filtering on the old class name will stop matching. For important long-lived events, you can use **event.name** or a separate stable business category so you do not rely solely on the class name.

**Scenario E: library uses a different logger name from the app**

A third-party library typically uses its own namespace, such as **org.some.library.Component**. This is expected; when searching logs, filter by service.name alongside logger to know which service the library is running in.

**Scenario F: bridged from JUL or Log4j API**

When logs are routed from another API to SLF4J/the backend, the logger name is usually preserved or mapped by the adapter, though details depend on the bridge/provider configuration. Verify the actual value of a record through the pipeline rather than assuming bridges behave identically across all versions.

## 15. Testing the logger Field in JSON Logging

A QA check should inspect real data read by a parser, not just visually scan logs on screen.

**Recommended steps:**

1. Pick a logger with a **fixed, easily verifiable name**, such as com.example.checkout.OrderService.
2. Emit an INFO event with a message and a distinct requestId.
3. Ensure the backend actually receives the event: check root/logger levels, filters, and appenders.
4. Write **JSON Lines** to a dedicated test file or capture console output appropriately.
5. Read each record with a JSON parser; verify **one record is one valid JSON object**.
6. Confirm the field has the exact **key name** agreed upon: logger, logger_name, or log.logger.
7. Confirm **the field type is string**; not a number, array, or object.
8. Confirm **the value equals the chosen logger name**, not the main class name or thread name unless they happen to match.
9. Confirm **level/message** are accurate; requestId is a separate field and does not replace logger.
10. Emit an event with a different logger to verify grouping actually changes by source.
11. Test messages containing quotes, backslashes, newlines, and Vietnamese characters; the JSON encoder must still produce valid JSON.
12. If using the ECS schema, check **log.logger** and the index mapping, not just top-level keys.
13. Verify that records with exceptions and multiline stack traces still parse cleanly.
14. Confirm the collector/indexer does not rename or drop the logger field.
15. Check dashboards/alerts that depend on the field name after deployment or encoder version upgrades.

Illustrative assertions in Java/Jackson style:

~~~java
// Illustrative snippet; event is a parsed Jackson JsonNode.
if (!event.path("logger").isTextual()) {
    throw new IllegalStateException("logger must be a JSON string");
}
if (!"com.example.checkout.OrderService"
        .equals(event.path("logger").asText())) {
    throw new IllegalStateException("unexpected logger name");
}
~~~

This is a **verification snippet**, not a standalone program. In the Maven example in Section 7, similar conditions were checked against the parser output.

### Test cases must handle missing fields

An event may lack a logger field because:
- The encoder/provider is not enabled.
- The schema was changed to logger_name or log.logger.
- The field was removed by an encoder exclusion filter.
- The ingest pipeline transformed/renamed the key.
- A record was constructed manually without a logger name.
- The data is not the same kind of logging event (access log, audit event, metric, etc.).

Do not fill a missing logger with an arbitrary string without a policy. If the source is genuinely unknown, the system may mark an “unknown” value according to the schema for observability and alerting; do not substitute a class name guessed from the message.

## 16. Common Errors and How to Fix Them

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| JSON has **logger_name** but dashboard queries **logger** | Encoder uses default name differing from schema | Standardize key via fieldNames/ingest |
| Missing logger field | Encoder does not include it or field was dropped | Check provider, encoder, exclusions, and collector |
| logger always has the same helper name | Single shared Logger in a utility | Organize loggers by class/subsystem |
| logger looks like a package with no real class | Logger created with a custom string | Accept it as a category; do not assume a loadable Class |
| logger changed after refactor | getLogger(Class) changes with Class.getName | Update queries; use a stable event name |
| logger contains userId or email | Logger name built dynamically from input | Remove request data; use MDC/separate field and never log PII |
| JSON has two logger keys | MDC or custom fields collide with encoder key | Eliminate key collision; check parser output |
| logger is an object instead of a string | Inconsistent schema or wrong ingest mapping | Fix producer/transform; verify type |
| Filtering by logger finds no logs | Logs use a different field name or level filter | Verify raw JSON, schema, and backend |
| logger and caller_class differ | Custom logger category or helper | Understand the difference; add caller only if truly needed |
| Record fails to parse due to quotes/newlines in message | Manual string concatenation missing escaping | Use a standard JSON encoder/serializer |
| Missing requestId mistaken for missing logger | Confusing MDC field with logger name | Check the two fields independently |
| Searching by library logger returns data from many services | Not filtering by service.name | Combine service, environment, and logger |
| Logger name is shortened | Encoder configured with shortened name | Restore full name or adjust query convention |
| Logs via OpenTelemetry lack top-level logger field | Different data model/instrumentation scope | Verify appropriate export/ingest mapping |

**Do not use regex to rewrite a raw JSON event** when it can be handled structurally by a parser/transformer. Regex can break when messages contain escapes, nested objects, or unexpected field ordering.

## 17. Security, Performance, and Observability

### Security

Never write **passwords, tokens, API keys, personal emails, phone numbers, or sensitive payloads** into a logger name. Logger names typically appear in every record, are indexed long-term, and are displayed in dashboards. Building loggers from untrusted input risks both data leakage and creating thousands of categories that exhaust resources.

**JSON string escaping** is essential: quotes, backslashes, and control characters must never break JSON syntax. In production, use a reliable encoder/serializer rather than concatenating string templates for untrusted messages.

**Log injection** can still occur if downstream systems render data improperly or share a text-based pipeline. Valid JSON gives parsers clear field boundaries, but it does not replace input validation and access control.

### Performance/cardinality

The logger field typically has a **bounded number of values matching the number of classes/categories**, much smaller than requestId which changes continuously. Embedding UUIDs/requestIds in logger names spikes cardinality, consuming memory in backends, indexes, and dashboards. Use stable class/subsystem names.

**Caller class/method/line** can be expensive because it requires stack inspection; the **logger name** is already attached to the logger and is usually much cheaper than collecting caller data. Do not enable caller data for every record just to get a field that the Logger already provides.

### Multi-service observability

When the same library emits a logger name like **org.apache.http...** across multiple services, add service.name or deployment metadata to identify the source. In tracing systems, traceId/requestId add event context. The logger field answers **who emitted the record in the logger namespace**, whereas traceId answers **which transaction/trace the record belongs to**.

### Source of truth

Like other log fields, the logger name **does not prove** that a business operation completed; it is metadata from a single log write. A message like event=order.completed may be emitted before a commit or lost if an appender/collector fails. Verify business outcomes in the appropriate data store.

## 18. Self-Check Questions

**Question 1.** In the JSON **{"logger":"com.example.checkout.OrderService"}**, what is logger?

**Answer:** The name of the logger that emitted the logging event, with type JSON string. It is not necessarily the name of the executing class.

**Question 2.** With SLF4J **LoggerFactory.getLogger(MyClass.class)**, where does the logger name usually come from?

**Answer:** From **MyClass.class.getName()** per the SLF4J API.

**Question 3.** When LogstashEncoder outputs logger_name by default, how do you change it to logger?

**Answer:** Configure **fieldNames** with the **logger** element in LogstashEncoder, or normalize the schema at ingest.

**Question 4.** Are logger and service.name the same?

**Answer:** No. Logger name is usually a class/category; service.name is the application/service. One service has many loggers, and one library logger can appear across many services.

**Question 5.** Why is **getLogger("payment.events")** valid even though there is no Java class named payment.events?

**Answer:** Because a logger can be given a custom name for a category/subsystem; it does not have to be a Class name.

**Question 6.** Should you use MDC.put("logger", requestId) to put the request ID into the logger field?

**Answer:** No. That can cause key collisions, distort the field's meaning, and increase cardinality. Use requestId/traceId as separate fields.

**Question 7.** Why is ECS's **log.logger** not automatically equivalent to a literal **"log.logger"** key in JSON?

**Answer:** A dotted field name represents a field path in the schema; nested JSON **{"log":{"logger":"..."}}** and a top-level literal key have different structures and require consistent mapping.

**Question 8.** If the logger name and caller class differ, is the JSON definitely wrong?

**Answer:** No. Code may use a custom logger category or a helper, so the two pieces of information do not have to match.

**Question 9.** Can you grep the string logger in text and conclude the JSON field has type string?

**Answer:** No. You must parse the JSON and check the field type; grep could match the message or another field.

**Question 10.** Why is a JSON encoder better than manual JSON string concatenation for production?

**Answer:** A dedicated encoder/serializer handles escaping, data types, schema, exceptions, and integration. Manual string concatenation easily produces invalid JSON or duplicate keys.

**Question 11.** Can you identify a specific request from the logger field alone?

**Answer:** No. You need requestId/traceId or other context because a single logger is usually shared across many requests.

**Question 12.** Why should you check the logger field after changing the backend/encoder?

**Answer:** Backends and encoders can rename keys, shorten logger names, change structure, or omit the field. Parsers/dashboards may stop matching even though LOG.info calls did not change.

## 19. Technical References

- [SLF4J Logger API](https://slf4j.org/apidocs/org/slf4j/Logger.html): **getName()** and the role of SLF4J Logger.
- [SLF4J LoggerFactory API](https://slf4j.org/apidocs/org/slf4j/LoggerFactory.html): **getLogger(Class)** and **getLogger(String)**.
- [logstash-logback-encoder — README](https://github.com/logfellow/logstash-logback-encoder/blob/main/README.md): default **logger_name**, **fieldNames** configuration, JSON encoders, and the loggerName provider.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): how **%logger** outputs the logger name in PatternLayout.
- [Oracle Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): **getLoggerName()** and JUL record metadata.
- [Elastic Common Schema — Log fields](https://www.elastic.co/docs/reference/ecs/ecs-log): definitions of **log.logger**, **log.level**, **log.file.path**, and other fields.
- [OpenTelemetry — Instrumentation scope](https://opentelemetry.io/docs/concepts/instrumentation-scope/): instrumentation scope semantics when logs flow through a telemetry pipeline.

## Key Takeaways

**The logger field is the name of the logger that emitted the log event, typically as a JSON string.** It is useful for filtering by class, package, or subsystem, but it is not synonymous with caller class, thread, service, requestId, or file path. SLF4J/JUL provide the logger name through their APIs; the encoder determines the actual JSON key (**logger**, **logger_name**, **log.logger** depending on schema). In production, choose a stable schema, use a proper JSON serializer/encoder, verify with a parser, avoid key collisions with MDC, and never use request data as a logger name. **The logger name is metadata about the log source, not the entire context of an event.**
