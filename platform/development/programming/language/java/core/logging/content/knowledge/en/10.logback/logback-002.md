# Logback Logger — How It Works and How to Use It in Java

## 1. Concept

A **Logback Logger** is the object representing a log event source in the **Logback Classic** system. Application code typically calls methods such as trace, debug, info, warn, or error to describe an event; Logback evaluates the logging level, creates a log event, and dispatches it to the configured output destinations.

It is important to distinguish two Logger types with similar names but different roles:

- **org.slf4j.Logger**: an interface in the SLF4J API. Business code should use this type so it is not tightly coupled to a specific backend.
- **ch.qos.logback.classic.Logger**: the concrete implementation class of Logback Classic. In addition to the SLF4J methods, it provides configuration and diagnostic APIs such as getLevel, getEffectiveLevel, setLevel, setAdditive, and addAppender.

A common example in a service class:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void finishOrder(String orderId) {
        LOG.info("event=order.completed orderId={}", orderId);
    }
}
~~~

This is an **illustrative snippet**, not a standalone program with a main method. To use it, the project needs the SLF4J API and a corresponding provider/backend, such as Logback Classic. When running with Logback, the object behind the SLF4J interface performs the logging work.

**Goal of this article:** understand where loggers are managed, how the effective level is derived, how additivity and appenders affect output, and how to use them in a Java 17 application with clear configuration.

## 2. Overall Architecture

~~~text
Java code calls org.slf4j.Logger
                 |
                 v
      SLF4J LoggerFactory
                 |
            Provider
           (Logback)
                 |
                 v
 ch.qos.logback.classic.Logger
                 |
      Level / TurboFilter
                 |
          ILoggingEvent
                 |
     Logger and ancestors
        (additivity)
                 |
                 v
        Appender / Filter
                 |
                 v
       Encoder or Layout
                 |
                 v
   Console / File / Collector
~~~

| Component | Role |
| --- | --- |
| LoggerFactory | Returns a logger by name or class, going through SLF4J's provider mechanism |
| LoggerContext | Context that manages the logger tree and Logback Classic configuration |
| Logger | Event source with a name, assigned level, and effective level |
| Root logger | Root logger of the name hierarchy; usually holds shared appenders and level |
| ILoggingEvent | Event object containing level, message, arguments, and context information |
| Appender | Receives events and writes them to a destination such as console/file |
| Filter and TurboFilter | Allows or rejects events based on additional conditions |
| Encoder / Layout | Converts events into formatted text/bytes |
| MDC | Key-value context, typically holding requestId/traceId when propagated properly |

**A Logger is not a log file.** Calling LOG.info only means the application sends an event to the logging API. Whether a record is actually emitted depends on the level, filters, appenders, encoder, and destination state. Logback is not built into the JDK; the appropriate dependencies are required.

## 3. Obtaining a Logger

Common convention:

~~~java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(MyService.class);
~~~

The snippet above sits **inside the MyService class**. The logger's name matches the fully qualified class name, for example com.example.order.MyService. Another approach is obtaining it by an explicit name:

~~~java
org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger("com.example.order");
~~~

Within the same LoggerContext, a logger for a given name is managed and reused; there is no need to create a new LoggerContext or backend object per request. The **private static final** convention avoids fetching a logger per instance, keeps the name stable, and makes package-level configuration straightforward.

You can name loggers by feature instead of class name, but you should stay consistent across the project. Avoid dynamic names containing orderId/requestId per request: the logger hierarchy is meant for managing event sources and configuration, whereas requestId is **event context**, not a logger name.

## 4. Logger Name Hierarchy

Logback organizes loggers using dot-separated names:

~~~text
ROOT
  |
  +-- com
       |
       +-- com.example
            |
            +-- com.example.order
            |      |
            |      +-- com.example.order.OrderService
            |
            +-- com.example.payment
~~~

With this hierarchy, a configuration on **com.example.order** can affect child loggers under the order group. **com.example.ordering** is not a child along the name boundary of **com.example.order**, even though the prefix looks similar.

Two separate mechanisms use the hierarchy:

1. **Level inheritance:** a logger without its own level uses the level of its nearest ancestor that has a configured level.
2. **Event propagation to appenders:** events from a child logger can pass through appenders on parent loggers and root if additivity allows.

Understanding the difference between these two mechanisms is the most important part of configuring Logback Loggers.

## 5. Assigned Level and Effective Level

Common levels in Logback Classic:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

The **assigned level** is the level set directly on a logger. If not set, this value can be **null**. The **effective level** is the level actually applied, derived from the current logger or the nearest ancestor that has a level.

Example:

~~~text
ROOT                         INFO
com.example                  (not set)
com.example.order            DEBUG
com.example.order.OrderService (not set)
com.example.payment          (not set)
~~~

| Logger | Assigned level | Effective level |
| --- | --- | --- |
| ROOT | INFO | INFO |
| com.example | null | INFO |
| com.example.order | DEBUG | DEBUG |
| com.example.order.OrderService | null | DEBUG |
| com.example.payment | null | INFO |

In this scenario:

- A **debug** call in OrderService passes the basic threshold check because its effective level is DEBUG.
- A **debug** call in PaymentService under com.example.payment is normally dropped because its effective level is INFO.
- **info, warn, error** calls in both components meet the threshold.
- Logger.getLevel() returning null does not mean the logger is disabled; you must check the effective level.

Normally, an event's level must be **at least as severe as** the emitting logger's effective level. A TurboFilter can additionally affect event acceptance, while a Filter on an appender can block events that already passed the logger.

### Does Root INFO Block DEBUG from a Child Logger?

Under Logback's standard level handling, **no**. If a child logger has an effective level of DEBUG and has created a DEBUG event, the event can travel to an appender attached to root via additivity, even when root is set to INFO. **Root's level is not re-applied to reject an event already accepted by a child logger** as it traverses the appender chain. However, if the appender has a ThresholdFilter set to INFO, that filter can still block DEBUG.

## 6. What Is Additivity?

**Additivity** is the rule for forwarding events from the current logger to the appenders of its ancestors. The default setting is **true**.

Tree example:

~~~text
ROOT -> Appender CONSOLE
  com.example.order -> Appender ORDER_FILE
    com.example.order.OrderService
~~~

If additivity=true, events from OrderService can be written to both **ORDER_FILE** and **CONSOLE**. If the same appender is attached at multiple levels, it can receive the same event multiple times.

Example configuration prone to duplicate logs:

~~~xml
<logger name="com.example.order" level="DEBUG">
    <appender-ref ref="STDOUT"/>
</logger>
<root level="INFO">
    <appender-ref ref="STDOUT"/>
</root>
~~~

This XML snippet assumes the STDOUT appender has already been declared. Because the child logger has default additivity, both it and root can invoke the STDOUT appender, causing the event to appear twice. **Two identical log lines do not necessarily mean the business logic ran twice.**

Two sound design approaches:

**Approach A: shared appender at root, child logger only sets the level.**

~~~xml
<logger name="com.example.order" level="DEBUG"/>
<root level="INFO">
    <appender-ref ref="STDOUT"/>
</root>
~~~

**Approach B: child logger uses its own appender and stops forwarding.**

~~~xml
<logger name="com.example.order"
        level="DEBUG"
        additivity="false">
    <appender-ref ref="ORDER_FILE"/>
</logger>
~~~

In Approach B, ORDER_FILE must exist. When **additivity=false**, events are not forwarded to ancestor appenders along that path. **If no appender is attached to the child branch, events may never reach the expected destination.**

Additivity **is not a level threshold**. A logger can inherit its level from a parent while having additivity disabled, or set its own DEBUG level while still emitting logs through an appender on root.

## 7. Complete Example with Java 17 and Maven

Goal: an application with **root INFO** but **demo.order DEBUG**, using **only one ConsoleAppender at root**, to clearly observe level inheritance and additivity.

### 7.1. Project Structure

~~~text
logback-logger-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LogbackLoggerDemo.java
        └── resources/
            └── logback.xml
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>logback-logger-demo</artifactId>
    <version>1.0.0</version>

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
                <configuration>
                    <mainClass>demo.LogbackLoggerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The versions in this example are specified to pin dependencies for the exercise, **not as a claim that they are the latest versions**. The logback-classic dependency typically pulls in compatible logback-core and SLF4J API artifacts via Maven; real projects should manage versions centrally, check for dependency conflicts, and apply appropriate security patches.

### 7.3. src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.order" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Key characteristics of this configuration:

- Logback's **ConsoleAppender** writes to **stdout** by default, unlike JUL's ConsoleHandler which typically writes to **stderr**.
- **demo.order** has level DEBUG, while root has INFO.
- The child logger **demo.order.OrderService** inherits DEBUG.
- The child logger has no appender of its own, so there is no duplicate output with root under this configuration.
- **%level**, **%logger**, **%msg**, and **%n** control the format; timestamps are omitted so the output is easy to compare.
- In production, you typically include timestamp, thread, service name, request/trace ID, and an appropriate Throwable formatting strategy.

### 7.4. src/main/java/demo/LogbackLoggerDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class LogbackLoggerDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger("demo.order.OrderService");

    public static void main(String[] args) {
        LOG.debug(
                "event=order.pricing orderId={} base={} discount={}",
                "ORD-7", 100, 10);

        LOG.info(
                "event=order.completed orderId={} total={}",
                "ORD-7", 90);

        LOG.warn(
                "event=order.fallback reason={}",
                "cache_miss");
    }
}
~~~

The logger is explicitly named **demo.order.OrderService**, different from the main class name **demo.LogbackLoggerDemo**. This lets the example demonstrate the exact effect of the demo.order configuration.

### 7.5. Running the Example

Requires **JDK 17+** and Maven installed; on the first run, Maven needs to download dependencies. Open a terminal in the logback-logger-demo directory:

~~~bash
mvn -q compile exec:java
~~~

**Stdout of the Java program** (excluding Maven/terminal output):

~~~text
DEBUG | demo.order.OrderService | event=order.pricing orderId=ORD-7 base=100 discount=10
INFO | demo.order.OrderService | event=order.completed orderId=ORD-7 total=90
WARN | demo.order.OrderService | event=order.fallback reason=cache_miss
~~~

Why does the DEBUG line appear?

1. The logger is obtained under the name **demo.order.OrderService**.
2. Logger **demo.order** is set to DEBUG, so its child logger has an effective level of DEBUG unless overridden.
3. The debug call meets the threshold at the emitting logger.
4. The event is forwarded to the STDOUT appender attached to root because additivity remains enabled.
5. Root INFO does not re-filter a DEBUG event already accepted by the child logger; the appender configuration above has no filter blocking DEBUG.
6. The encoder formats the **{}** placeholders and prints the level, logger name, and message.

To test the threshold, change logback.xml to:

~~~xml
<logger name="demo.order" level="INFO"/>
~~~

Run the same program again. **Application stdout** now contains only two lines:

~~~text
INFO | demo.order.OrderService | event=order.completed orderId=ORD-7 total=90
WARN | demo.order.OrderService | event=order.fallback reason=cache_miss
~~~

No Java code changes are needed. This is the value of decoupling events emitted by the Logger from backend configuration.

## 8. Difference Between Logger and Appender

A Logger determines the **event source name** and **emission threshold**, whereas an Appender determines the **output destination**. One logger can route events to multiple appenders according to the hierarchy configuration. For example, the console might receive INFO and above while a diagnostic file receives DEBUG and above.

An Appender can have its own **filter**. The following snippet sets an INFO threshold on ConsoleAppender:

~~~xml
<appender name="STDOUT"
          class="ch.qos.logback.core.ConsoleAppender">
    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
        <level>INFO</level>
    </filter>
    <encoder>
        <pattern>%level | %logger | %msg%n</pattern>
    </encoder>
</appender>
~~~

Even if the demo.order logger accepts DEBUG, this appender filter drops DEBUG before output. This is only an illustrative snippet, **not a complete standalone logback.xml**. To see DEBUG output, you must check the effective level, filters, and the appender path.

Do not attach the same appender at multiple levels arbitrarily. If you see duplicate logs, inspect appender-ref on the child logger, ancestors, and root along with the additivity attribute before concluding that business logic was invoked twice.

## 9. Logback's LoggerContext

**LoggerContext** is the context Logback Classic uses to manage loggers and configuration. When application code only needs to log, it does not need to access it; using SLF4J LoggerFactory is enough.

When building Logback administration or diagnostic tools, you can access the implementation after checking the backend:

~~~java
// Illustrative code inside a method; requires Logback and SLF4J dependencies.
org.slf4j.ILoggerFactory factory =
        org.slf4j.LoggerFactory.getILoggerFactory();

if (factory instanceof ch.qos.logback.classic.LoggerContext context) {
    ch.qos.logback.classic.Logger logger =
            context.getLogger("demo.order.OrderService");

    ch.qos.logback.classic.Level assigned = logger.getLevel();
    ch.qos.logback.classic.Level effective =
            logger.getEffectiveLevel();

    System.out.println("assigned=" + assigned);
    System.out.println("effective=" + effective);
}
~~~

In the section 7 example configuration, logger **demo.order.OrderService** has no level set directly: assigned can be **null**, while effective is **DEBUG**. These two values are not equivalent.

**Why is instanceof needed?** If an application uses another SLF4J backend, ILoggerFactory may not be Logback's LoggerContext. An unchecked cast can throw ClassCastException. Library code using SLF4J should avoid depending directly on the backend when unnecessary.

Logback allows changing levels at runtime, for example:

~~~java
// Illustrative snippet in an administrative component; context has already been verified.
ch.qos.logback.classic.Logger target =
        context.getLogger("demo.order");
target.setLevel(ch.qos.logback.classic.Level.DEBUG);
~~~

This affects the logger in the running context. It is not an operation to call freely from a request handler or business library; you need authorization controls, a time limit for keeping DEBUG enabled, and alignment with the active configuration. When configuration reloads, levels changed programmatically may be overwritten by the new configuration.

## 10. Parameterized Logging and Cost

SLF4J supports **{}** placeholders:

~~~java
LOG.info("event=order.created orderId={} total={}", orderId, total);
~~~

This is an illustrative snippet inside a class that has a Logger and variables. This approach keeps message templates readable and avoids unnecessary string concatenation when the log level is disabled.

**However, Java still evaluates arguments before calling the method.** For example:

~~~java
LOG.debug("orderDetail={}", serializeExpensively(order));
~~~

The serializeExpensively(order) method still executes before debug is called, even when DEBUG is disabled. For expensive data construction:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("orderDetail={}", serializeExpensively(order));
}
~~~

The snippets above rely on variables and methods in real code; **they are not standalone programs**. isDebugEnabled() avoids message construction cost when the level is filtered out, but it does not guarantee the final appender will write the log (a filter or destination failure could still prevent it).

Do not tie required business actions to DEBUG message construction; if that branch is disabled, the action will not run.

## 11. Logging Exceptions with Logger

SLF4J Logger allows passing a Throwable alongside the message:

~~~java
try {
    performPayment();
} catch (java.io.IOException ex) {
    LOG.error("event=payment.failed requestId={}", requestId, ex);
}
~~~

This is **illustrative code**, requiring LOG, requestId, and performPayment() in a real program. When the appropriate overload is used, Logback retains the Throwable in the event so the encoder/layout can output the stack trace and cause chain.

Logging only **LOG.error(ex.getMessage())** loses the stack trace and omits business context. When an error propagates through multiple layers, choose a **responsible logging boundary** rather than having every layer log the same Throwable and rethrow it.

Do not assume every pattern preserves full error details. Verify the encoder, throwable converter, parsing behavior, and retention in the target environment. For sensitive internal data, exception messages and stack traces must also be protected.

## 12. MDC — Attaching requestId to Log Events

**MDC** (Mapped Diagnostic Context) is a key-value context that helps correlate logs belonging to the same request. With SLF4J/Logback:

~~~java
// Illustrative code placed in a method that has a LOG variable.
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", "req-42")) {
    LOG.info("event=order.created outcome=success");
}
~~~

In logback.xml, the pattern can read from MDC:

~~~xml
<pattern>%level requestId=%X{requestId} %logger - %msg%n</pattern>
~~~

This is a configuration snippet inside an appropriate encoder. When MDC contains requestId=req-42, Logback can include that value in logs without concatenating it into every message.

**MDC does not automatically generate correlation IDs and does not automatically propagate context across all asynchronous tasks.** With thread pools or CompletableFuture, you must propagate the context appropriately and clear MDC after processing so reused threads do not retain an old request's ID.

Do not store passwords, tokens, cookies, sensitive personal data, or entire request bodies in MDC.

## 13. Logback Logger and Structured Logging

Logback can output plain text logs or combine with an appropriate encoder to produce structured records. Key=value example:

~~~text
INFO event=order.completed orderId=ORD-7 total=90
~~~

and illustrative JSON:

~~~json
{"level":"INFO","logger":"demo.order.OrderService","event":"order.completed","orderId":"ORD-7","total":90}
~~~

The JSON line above **is not output from the section 7 program**; it merely illustrates the goal of structured logging. To emit real JSON, a project needs the corresponding encoder, dependency configuration, and verified parser/escaping behavior. Using {} placeholders **does not automatically turn a message into typed JSON fields**.

Consistent event names, requestId/traceId, and error codes aid searching, but avoid logging large objects or raw payloads. Log injection can occur when untrusted data contains newlines or quotes and the formatter does not escape them properly.

## 14. Choosing the Right Log Level

| SLF4J/Logback Level | Typical Purpose |
| --- | --- |
| TRACE | Very fine-grained tracing when deep diagnosis is needed |
| DEBUG | Execution branches, intermediate state, and key decisions |
| INFO | Meaningful operational milestones |
| WARN | Anomaly worth attention, though execution can continue |
| ERROR | Significant failure requiring handling and investigation |

Logger.error(...) does not throw an exception, trigger a rollback, or stop the application. Application logic itself is responsible for error handling. Do not default to logging every validation error as ERROR; the log level should reflect service impact and operational intent.

Do not leave TRACE/DEBUG enabled across all of production indefinitely. Enable them selectively by package/logger for investigation, monitor the cost, and plan to revert to operational levels.

## 15. How Logback Differs from JUL and Log4j 2

| System | Logger API and Configuration |
| --- | --- |
| JUL (java.util.logging) | Logger and Level are in the JDK; typically configured via logging.properties; Handler/Formatter |
| SLF4J | Facade API org.slf4j.Logger; requires an appropriate provider to write logs |
| Logback Classic | SLF4J implementation; ch.qos.logback.classic.Logger, LoggerContext, logback.xml, Appender |
| Log4j 2 | Has its own API and implementation; uses Appender and its own configuration |
| Spring Boot | Provides a logging configuration layer over the active framework/backend |

Do not write **java.util.logging.Level.FINE** expecting it to be **ch.qos.logback.classic.Level.DEBUG**. Those are two different APIs. If a JUL → SLF4J bridge is present, behavior depends on bridge configuration; avoid installing conflicting providers/bridges or forwarding loops.

In shared libraries, depending on the SLF4J API is generally more flexible than using Logback implementation classes directly.

## 16. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Confusing SLF4J Logger with Logback Logger | Cannot find APIs like getEffectiveLevel on SLF4J | Only use backend classes in Logback management code |
| Treating getLevel()==null as logging disabled | Misunderstanding effective level | Use getEffectiveLevel to account for inheritance |
| Root INFO and assuming child DEBUG is always blocked | Misguided debugging | Evaluate the emitting logger's level and appender filters |
| Duplicate appender-ref on child and root | Logs appear twice | Attach the appender at root or configure additivity properly |
| additivity=false without attaching an appender | No expected output | Attach an appender to the branch or allow parent propagation |
| Changing level on the wrong package/name | No visible difference | Verify the actual logger name |
| Logger DEBUG but appender filters at INFO | DEBUG is not emitted | Check filters at the destination as well |
| Casting ILoggerFactory directly to LoggerContext | Possible ClassCastException | Check the backend with instanceof |
| Multiple SLF4J providers present | Wrong backend selected or warnings | Inspect the dependency tree and keep the setup consistent |
| Expensive string building inside debug | Wastes CPU even when debug is off | Use placeholders/guards for expensive computations |
| Not clearing MDC after a request | Correlation IDs leak across tasks | Clear by scope and propagate context properly |
| Logging raw payloads/secrets | Data exposure risk | Log only necessary fields and mask sensitive data |
| Logging Throwable at every layer | Duplicate stack traces | Place logging responsibility at the boundary |
| Editing the wrong logback.xml file | Configuration does not change | Check classpath, framework, profile, and reload behavior |

## 17. Checklist When Logs Are Missing

1. Does execution actually reach the corresponding LOG.debug/info call?
2. Is the logger obtained by class name or explicit string? Does it match the configured name?
3. What is the logger's effective level?
4. Are a TurboFilter or appender filter rejecting the event?
5. Is an appender attached to receive it? Is additivity=false set at some level without an appender?
6. Are logs going to stdout, stderr, a file, or a collector?
7. Is Logback Classic actually the active backend? Are there conflicting SLF4J providers or bridges?
8. Is logback.xml packaged on the classpath and loaded?
9. Is the thread context/MDC set properly to filter logs for that request?
10. Could data be delayed, sampled, dropped due to buffering, or expired in the centralized logging system?

If a log line is missing, **you cannot conclude from that alone that the code branch did not execute**.

## 18. Self-Check Questions

**Q1.** Why should business code declare org.slf4j.Logger instead of ch.qos.logback.classic.Logger?

**Answer:** Because SLF4J is an intermediary facade API; code can work with other backends without tight coupling to Logback's internal classes. Backend classes are mainly needed when managing or configuring Logback.

**Q2.** Root is INFO, logger demo.order is DEBUG, the appender is on root, and there are no special filters: can DEBUG logs from demo.order.OrderService appear?

**Answer:** Yes. The child logger has an effective level of DEBUG, the event is accepted, and it travels to the root appender via additivity. Root INFO does not re-filter an event already accepted by the child logger.

**Q3.** What does it mean when Logger.getLevel() returns null?

**Answer:** The logger has no level assigned directly and normally inherits its effective level from an ancestor; it does not mean logging is disabled.

**Q4.** A log line appears twice when both the child logger and root attach STDOUT. What is a likely cause?

**Answer:** Additivity allows the event to reach the appender at both levels. Adjust appender-ref or configure additivity to avoid duplicate output.

**Q5.** What happens when additivity=false and the child logger has no appender of its own?

**Answer:** Events do not travel to the root appender along the forwarding path, so they may not be written to any destination.

**Q6.** Why does LOG.debug("data={}", expensive(data)) still consume CPU when DEBUG is disabled?

**Answer:** Java evaluates expensive(data) before the method call; use an isDebugEnabled guard if the computation is truly expensive.

**Q7.** Should you assume MDC automatically propagates across CompletableFuture and thread pools?

**Answer:** No. You need an appropriate context-propagation strategy and must clear MDC to avoid mixing data between requests.

**Q8.** If the backend is not Logback Classic and you still cast ILoggerFactory to LoggerContext, what can happen?

**Answer:** ClassCastException. Check with instanceof before using Logback internal APIs.

**Q9.** A log event contains a Throwable, but the system only displays the message. What should you check?

**Answer:** The encoder/layout/formatter, appender filters, and exception rendering configuration; do not assume every format includes the full stack trace.

**Key takeaway:** **Logback Logger** is the implementation behind **SLF4J Logger**. To understand why a log appears or disappears, trace **logger name → effective level → filter → additivity → appender → encoder/destination**. Use SLF4J in business code, configure and manage Logback at the appropriate layer, keep logs useful, and protect sensitive data.
