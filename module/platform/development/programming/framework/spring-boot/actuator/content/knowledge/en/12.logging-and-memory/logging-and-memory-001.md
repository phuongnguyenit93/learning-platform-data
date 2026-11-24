# Reading Configured and Effective Log Levels Using the Loggers Endpoint

When a `DEBUG` line does not appear, the first question is usually "what level is this logger currently at?". In an application with many packages and libraries, looking at a single `logging.level.root` line is not enough to answer: individual loggers may have their own explicitly set level or inherit a level from a closer parent logger.

Spring Boot Actuator's `loggers` endpoint lets you read the log level state of a running process. Two pieces of information need to be clearly distinguished:

- **Directly configured level — `configuredLevel`**: the level explicitly assigned to the queried logger itself.
- **Effective level — `effectiveLevel`**: the final level the logger uses after accounting for the logging system's inheritance mechanism.

This lesson focuses on `GET` requests to observe and interpret these two fields. The examples use **Java 21, Spring Boot 3.3.13, and the default Logback from the Spring Boot starter**.

## 1. Loggers Have Names and Parent–Child Relationships

A logger is an object that receives calls such as `debug()`, `info()`, `warn()`, and `error()`. A logger name is usually a fully qualified class name, though it can also be a string chosen by the application:

```java
// Illustrative snippet showing how to obtain a logger; not a standalone program.
org.slf4j.Logger logger =
        org.slf4j.LoggerFactory.getLogger("demo.orders.InventoryService");
```

In Logback, dots create a hierarchical relationship. For example:

```text
ROOT
└── demo
    └── demo.orders
        └── demo.orders.InventoryService
```

`demo.orders` is an ancestor of `demo.orders.InventoryService`. This name may resemble a package name, but a logger does not need to correspond to a package object or an actual class declared in Java code.

Logger names are case-sensitive. `demo.orders.InventoryService` and `demo.orders.inventoryservice` are two different names.

### How Logback Determines the Effective Level

Starting from the queried logger:

1. If it has its own level, use that level.
2. If not, move up to the parent logger.
3. Continue to the nearest ancestor that has its own level.
4. Finally, the `ROOT` logger serves as the fallback inheritance point.

Example:

```text
ROOT                                      WARN
└── demo.orders                           DEBUG
    ├── demo.orders.InventoryService      not explicitly set
    ├── demo.orders.payment               INFO
    │   └── ...payment.RefundService      not explicitly set
    └── ...audit.SecurityAudit            ERROR
```

Result:

| Logger | Own level | Effective level | Source of effective level |
| --- | --- | --- | --- |
| `ROOT` | `WARN` | `WARN` | The root logger itself |
| `demo.orders` | `DEBUG` | `DEBUG` | This logger itself |
| `demo.orders.InventoryService` | Not set | `DEBUG` | `demo.orders` |
| `demo.orders.payment` | `INFO` | `INFO` | This logger itself |
| `demo.orders.payment.RefundService` | Not set | `INFO` | `demo.orders.payment` |
| `demo.orders.audit.SecurityAudit` | `ERROR` | `ERROR` | This logger itself |

`RefundService` receives `INFO` from the closer ancestor, even though the `demo.orders` branch above is set to `DEBUG`.

Background reference: [Logback — Logger hierarchy and level inheritance](https://logback.qos.ch/manual/architecture.html).

## 2. Reading Both Fields Without Misinterpreting Them

A logger with its own level may be reported as:

```json
{
  "configuredLevel": "INFO",
  "effectiveLevel": "INFO"
}
```

In the Logback example, if a logger has no explicit level of its own and inherits `DEBUG`, the default response looks like:

```json
{
  "effectiveLevel": "DEBUG"
}
```

The `configuredLevel` field does not appear because there is no directly configured level to report. When read through a tool's data model, this state may also be represented as `null`.

**Having no explicit level can still go along with a valid effective level.** Do not reinterpret this state as `OFF`, a configuration error, or "the logger is inactive".

| Observed state | Interpretation |
| --- | --- |
| `configuredLevel=DEBUG`, `effectiveLevel=DEBUG` | The logger has its own level set to `DEBUG` |
| No `configuredLevel`, `effectiveLevel=DEBUG` | The logger is inheriting `DEBUG` |
| No `configuredLevel`, `effectiveLevel=WARN` | The logger is inheriting `WARN` |
| `configuredLevel=OFF`, `effectiveLevel=OFF` | The logger has its own level set to `OFF`; distinct from the unset state |

The directly configured level reflects the current state in the logging system. The endpoint does not say that the value necessarily came from `application.yml`: it may have originated from startup configuration, a logging file, or a runtime change.

The endpoint also does not include a source file or line number to explain who set the level. When you need to trace the origin, you must cross-check deployment configuration, logging configuration, and operational change history.

## 3. Two Main Forms of Read Requests

### 3.1. Overview Read

```text
GET /actuator/loggers
```

Main parts of the response:

| Field | Content |
| --- | --- |
| `levels` | The levels supported by the logging system |
| `loggers` | Map of loggers, keyed by logger name |
| `groups` | Declared logger groups, including their member lists |

The actual list can be long and contain many framework or library loggers. This is not a list of every Java class in the application; a class that has not created a logger does not necessarily have a corresponding entry.

Do not hardcode the number of loggers or JSON ordering when writing verification tools. Use the full name as the lookup key.

### 3.2. Single-Logger Read

```text
GET /actuator/loggers/{logger.name}
```

Example:

```shell
curl "http://127.0.0.1:18082/actuator/loggers/demo.orders.InventoryService"
curl "http://127.0.0.1:18082/actuator/loggers/ROOT"
```

In Spring Boot configuration, the root logger is usually set with the key `logging.level.root`; when reading the endpoint, the canonical root name is `ROOT`.

If the application has a context path, base path, or separate management port, use the corresponding address instead of the default in the example. For names containing URL-special characters, apply appropriate URL encoding while keeping the decoded logger name intact.

Official response structure: [Loggers endpoint REST API — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

## 4. A Standalone Project for Cross-Checking

Create the directory:

```text
actuator-loggers-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── learning/
        │       └── actuator/
        │           └── LoggersDemoApplication.java
        └── resources/
            └── application.yml
```

JDK 21 and Maven 3.6.3 or later are required. The first build needs access to the Maven repository to download dependencies.

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>learning</groupId>
    <artifactId>actuator-loggers-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The starter uses Logback by default. If you replace the logging backend, check the new backend's inheritance mechanism and supported levels.

### 4.2. `src/main/java/learning/actuator/LoggersDemoApplication.java`

```java
package learning.actuator;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LoggersDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoggersDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner emitExampleLogs() {
        return args -> {
            emit("demo.orders.InventoryService");
            emit("demo.orders.payment.RefundService");
            emit("demo.orders.audit.SecurityAudit");
            emit("external.health.Probe");
        };
    }

    private static void emit(String name) {
        Logger logger = LoggerFactory.getLogger(name);
        logger.trace("{} TRACE", name);
        logger.debug("{} DEBUG", name);
        logger.info("{} INFO", name);
        logger.warn("{} WARN", name);
        logger.error("{} ERROR", name);
    }
}
```

The four logger name strings intentionally create four different cases. You do not need to create separate classes `InventoryService`, `RefundService`, `SecurityAudit`, or `Probe`: these are strings passed to `LoggerFactory.getLogger(String)`.

Each logger is called in sequence at five levels: `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`. `ApplicationRunner` runs the demonstration once after the application has started successfully.

### 4.3. `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 18082

spring:
  main:
    banner-mode: "off"

management:
  endpoints:
    web:
      exposure:
        include: loggers

logging:
  level:
    root: WARN
    demo.orders: DEBUG
    demo.orders.payment: INFO
    demo.orders.audit.SecurityAudit: ERROR
  group:
    orderops: demo.orders,demo.shipping
  pattern:
    console: "%msg%n"
```

Choices made for the experiment:

- `server.address=127.0.0.1` restricts the server to loopback.
- Only the `loggers` endpoint is included in HTTP exposure.
- `root=WARN` makes it clear that individual branches can have a more detailed level than the root logger.
- `logging.pattern.console=%msg%n` prints only the message body, making output comparison easy.
- The `orderops` group is declared to observe the difference between a logger and a logger group.

The example omits Spring Security to focus on reading data on a local machine. The `loggers` endpoint also supports changing log levels; exposing it does not make it read-only. In production, network access and permissions must be restricted per operation; this lesson only performs `GET`.

### 4.4. Packaging and Running

In the directory containing `pom.xml`:

```shell
mvn clean package
java -jar target/actuator-loggers-demo-1.0.0.jar
```

Make sure no arguments, environment variables, or external configuration override the experiment's `logging.level.*` settings. If port `18082` is already in use, choose another port via `--server.port` and update the check URLs accordingly.

With the configuration above, the ten messages emitted by the runner and written to the console are:

```text
demo.orders.InventoryService DEBUG
demo.orders.InventoryService INFO
demo.orders.InventoryService WARN
demo.orders.InventoryService ERROR
demo.orders.payment.RefundService INFO
demo.orders.payment.RefundService WARN
demo.orders.payment.RefundService ERROR
demo.orders.audit.SecurityAudit ERROR
external.health.Probe WARN
external.health.Probe ERROR
```

All `TRACE` messages are filtered out by the example's log level thresholds. The inventory branch logs starting at `DEBUG`; the payment branch logs starting at `INFO`; the audit logger logs only `ERROR`; and the logger outside the orders branch inherits `WARN` from `ROOT`.

The list above is the demonstration output. Operational warnings generated by the environment, if any, should be distinguished from these messages.

## 5. Reading Each Logger and Explaining the Response

Open a second terminal while the application is running. On Windows PowerShell, use `curl.exe` instead of `curl` if `curl` is aliased to a PowerShell command.

### 5.1. Root Logger

```shell
curl "http://127.0.0.1:18082/actuator/loggers/ROOT"
```

Body in the experiment:

```json
{
  "configuredLevel": "WARN",
  "effectiveLevel": "WARN"
}
```

This is the root level currently applied in the process. It does not prove that every child logger has an effective level of `WARN`.

### 5.2. Logger Receiving Its Level from the Orders Branch

```shell
curl "http://127.0.0.1:18082/actuator/loggers/demo.orders.InventoryService"
```

Body:

```json
{
  "effectiveLevel": "DEBUG"
}
```

The inventory logger has no explicit level of its own. Read the parent logger next:

```shell
curl "http://127.0.0.1:18082/actuator/loggers/demo.orders"
```

Body:

```json
{
  "configuredLevel": "DEBUG",
  "effectiveLevel": "DEBUG"
}
```

Combining the two responses explains the inheritance source in this configuration: inventory's `DEBUG` level comes from `demo.orders`.

### 5.3. Logger Receiving Its Level from a Closer Ancestor

```shell
curl "http://127.0.0.1:18082/actuator/loggers/demo.orders.payment.RefundService"
```

Body:

```json
{
  "effectiveLevel": "INFO"
}
```

Checking `demo.orders.payment` shows that it has an explicit level of `INFO`. Because this ancestor is closer than `demo.orders`, the refund logger inherits `INFO` instead of `DEBUG`.

When investigating a large logger tree, start from the target logger and walk backward through each prefix to find the nearest explicitly set level. Do not just read `ROOT` and stop.

### 5.4. Logger with Its Own Explicit Level

```shell
curl "http://127.0.0.1:18082/actuator/loggers/demo.orders.audit.SecurityAudit"
```

Body:

```json
{
  "configuredLevel": "ERROR",
  "effectiveLevel": "ERROR"
}
```

The direct `ERROR` level on this logger is used even though its ancestor `demo.orders` is at `DEBUG`.

Final comparison table for the experiment:

| Queried logger | `configuredLevel` | `effectiveLevel` |
| --- | --- | --- |
| `ROOT` | `WARN` | `WARN` |
| `demo.orders` | `DEBUG` | `DEBUG` |
| `demo.orders.InventoryService` | Field absent | `DEBUG` |
| `demo.orders.payment` | `INFO` | `INFO` |
| `demo.orders.payment.RefundService` | Field absent | `INFO` |
| `demo.orders.audit.SecurityAudit` | `ERROR` | `ERROR` |
| `external.health.Probe` | Field absent | `WARN` |

## 6. Reading All Loggers and Distinguishing Logger Groups

Call:

```shell
curl "http://127.0.0.1:18082/actuator/loggers"
```

Inside `loggers`, look up by exact full name. The loggers used by the runner can be cross-checked against the table in section 5. Framework entries and intermediate parent loggers may appear alongside them.

The `levels` field identifies which levels the logging system supports. Do not assume every logging backend has the exact same levels or the same mapping; for example, Spring Boot maps `FATAL` to `ERROR` when using Logback.

### A Group Is a List of Members, Not a Parent Logger

The `orderops` group in YAML contains two named members:

```text
demo.orders
demo.shipping
```

You can read a group using the same path pattern:

```shell
curl "http://127.0.0.1:18082/actuator/loggers/orderops"
```

Body in the experiment:

```json
{
  "members": [
    "demo.orders",
    "demo.shipping"
  ]
}
```

The group has not been assigned an explicit level, so it has no `configuredLevel`. The group response also does not have a single shared `effectiveLevel` for all members.

A group name gathers loggers together for configuration management; it does not create a name-based parent–child relationship like `demo.orders → demo.orders.InventoryService`. To know the effective level of a specific logger in the group, you still must read that logger.

A member listed by name in a group also does not prove that every class or child logger in that branch has been created. Do not use the group list to infer how many classes have executed.

## 7. From Effective Level to Messages Actually Written

Under Logback's standard threshold rules, with no custom filter altering the decision:

```text
TRACE < DEBUG < INFO < WARN < ERROR
```

A message whose level is equal to or higher than the logger's threshold can pass the log level check.

| `effectiveLevel` | Message levels that pass the standard threshold |
| --- | --- |
| `TRACE` | `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `DEBUG` | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `INFO` | `INFO`, `WARN`, `ERROR` |
| `WARN` | `WARN`, `ERROR` |
| `ERROR` | `ERROR` |
| `OFF` | None of the five levels above |

Therefore, `effectiveLevel=INFO` does not mean the logger only writes `INFO` messages. It still allows `WARN` and `ERROR` messages to pass the threshold.

### Why Is Root WARN Yet DEBUG Still Appears?

In the experiment, inventory has an effective level of `DEBUG`. Its `DEBUG` message passes the check at the emitting logger, and is then forwarded to the console appender inherited from the parent branch.

In this standard Logback setup, root's `WARN` level is not re-applied as a global filter to drop `DEBUG` messages already accepted by a child logger. To understand a specific message, you must read the logger that emitted it.

### Effective Level Does Not Describe the Entire Logging Pipeline

Around or after the level check, the outcome also depends on components such as:

- Threshold or content filters on the appender.
- Custom Logback `TurboFilter` implementations.
- Appender inheritance and the `additivity` attribute.
- The log destination: console, file, collector, or another transport.
- Buffers and limits of an asynchronous logging pipeline, if configured.

Thus, `effectiveLevel=DEBUG` is evidence of the logger's current level, not enough on its own to claim a given message was written to a specific file. You still need to verify that the logging call actually ran and check the pipeline to the destination.

Conversely, a logger currently at `INFO` does not prove that `DEBUG` lines in an older file are anomalous. The file may contain data from a time with a different configuration or from multiple processes.

## 8. Diagnostic Reading Workflow

### Step 1: Identify the Exact Emitting Logger

Find the logger name the code actually uses. With `LoggerFactory.getLogger(SomeClass.class)`, that is usually the fully qualified class name. With `getLogger(String)`, use the passed string.

Logger names on the console may be abbreviated by a pattern. Do not copy that abbreviated name and treat it as the full name to query.

Also make sure the line you are looking for was emitted through the logging system managed by Actuator. A `System.out.println` call is not governed by this logger's threshold.

### Step 2: Read the Target Logger

Call `GET /actuator/loggers/<full-name>` and record:

- The queried logger name.
- Whether `configuredLevel` is present.
- The `effectiveLevel` value.
- The application instance and time of observation.

### Step 3: Trace the Inheritance Source

If there is no explicit level, read the appropriate ancestor loggers or look them up in the overview map. The nearest ancestor with an explicit level explains the inheritance result in the Logback example.

If the logger has an explicit level, check which configuration or runtime action set it. The endpoint reports current state, not an authorship history of changes.

### Step 4: Compare the Threshold Against the Call Level

If the message is `DEBUG` and the effective level is `INFO`, not seeing the message matches standard level filtering.

If the effective level is `DEBUG` yet the message is still missing, continue verifying whether the code branch executes, whether the logger name is right, and whether there are filters or another destination. Lowering a global level further can flood logs without addressing the real cause.

### Step 5: Match the Same Process and Timestamp

In a multi-instance system, each JVM has its own logging state. A read through a load balancer may hit a different instance than the one that produced the log line under investigation.

Record the instance address or appropriate operational identifier. Do not compare the current response of instance A with the log file of instance B and conclude that inheritance is broken.

## 9. When the Endpoint Does Not Return Expected Data

| Symptom | What to check |
| --- | --- |
| Cannot connect | Did the application start successfully, and are the port and network route right? |
| `401` or `403` | Check credentials and read permissions in the real application |
| `404` for the endpoint | Check starter dependency, enabled state, exposure, base path, and management port |
| `404` for a single logger name | Check the exact name and whether the logger exists in the current logging system |
| No `configuredLevel`, but `effectiveLevel` is present | The logger may be inheriting; this is a valid result |
| Receive `members` instead of `effectiveLevel` | You are reading a logger group |
| Value differs from expected YAML | Check override sources, logging files, profiles, and runtime changes |
| `DEBUG` is enabled, but no log lines appear | Check the actual emitting logger, execution flow, filters, appenders, and destination |

With Logback in the experiment, a nonexistent logger such as `does.not.exist.LoggerInThisDemo` returns `404` when queried via the single-logger endpoint. Do not infer an inherited level by treating a `404` response as `configuredLevel=null`: one means no result exists for the queried name, while the other means an existing logger has an effective level.

Also do not use the endpoint as a probe for whether a class exists in the JAR. Logger names and class existence are two separate facts.

## 10. Self-Check

Using the initial experiment configuration, answer:

1. Why does inventory have no `configuredLevel` yet still write `DEBUG`?
2. Why does refund receive `INFO` even though the orders branch is at `DEBUG`?
3. Why does audit write only `ERROR` out of the runner's five calls?
4. Why can you not use root's `WARN` level to conclude that inventory does not write `DEBUG`?
5. Why does the `orderops` group response not have a single shared `effectiveLevel`?

Answers should pinpoint the right logger or inheritance source: inventory receives `DEBUG` from `demo.orders`; refund receives `INFO` from `demo.orders.payment`; audit has its own level `ERROR`; each emitting logger is evaluated against its own effective level; a group is a member list for configuration management.

Then stop the application and restart it with:

```shell
java -jar target/actuator-loggers-demo-1.0.0.jar --logging.level.demo.orders=TRACE
```

Predict, then re-read:

| Logger | Predicted effective level |
| --- | --- |
| `demo.orders` | `TRACE` |
| `demo.orders.InventoryService` | `TRACE` |
| `demo.orders.payment.RefundService` | `INFO` |
| `demo.orders.audit.SecurityAudit` | `ERROR` |
| `external.health.Probe` | `WARN` |

Inventory receives the new level from the orders branch; the payment branch and audit logger still have their own explicit levels. This is a configuration change for a **new startup**, allowing you to observe the same mechanism without sending an endpoint update request.

Also consult [Spring Boot Logging](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html) and [LoggerConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/logging/LoggerConfiguration.html) when working with another logging system or version. A useful diagnostic conclusion clearly states **which logger, which own level, which effective level, and at what time**.
