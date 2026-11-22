# Default Configuration of Logging Systems in Java

## 1. What is a Default Configuration?

**Default logging configuration** is the set of rules applied by the runtime environment when a program does not specify its own configuration, or when a framework proactively provides an initial configuration. This rule set determines very practical questions:

- **Which logs are accepted?** INFO, DEBUG, WARN, ERROR levels, or the equivalent levels of each library.
- **Where do logs go?** Console, file, another appender, or nowhere if there is no logging provider.
- **What do logs look like?** Timestamp, level, logger name, thread, message, exception.
- **Who decides?** The JDK, logging backend, starter/framework, configuration file, JVM arguments, or code that changes configuration at runtime.
- **What if there is no configuration file?** Each backend has its own initialization policy; there is no single "Java default" that applies to all.

This lesson focuses on the **effective default configuration** in a Java application, how to identify it, why one project may see different logs from another, and how to change it safely when needed. Do not assume that every application prints INFO to the console or writes to a file automatically.

### Distinguishing Three Cases

1. **No custom configuration file written:** the system may still initialize logging automatically with the default configuration provided by the JDK, backend, or framework.
2. **Configuration file exists, but not all properties are set:** undeclared values are taken from each component's defaults or from inherited configuration.
3. **Missing logging API implementation/provider:** API calls may not be written anywhere, as in the case of using SLF4J without a compatible provider.

These are three different situations. Seeing a single log line or seeing none at all is not enough to conclude the cause.

## 2. Layers That Determine Logging Configuration

In Java, you should analyze from the API down to the destination:

~~~text
Java Application
  │
  ├── JDK's java.util.logging (JUL) ── LogManager / Handler
  │
  └── SLF4J API (if used)
       │
       └── provider/backend: Logback, Log4j2 adapter, JUL adapter, ...
                                      │
                                      ▼
                         Logger level / filter
                                      │
                                      ▼
                         Appender / Handler / Layout
                                      │
                                      ▼
                             Console / File / Sink
~~~

- **JUL** resides in the JDK's **java.logging** module and has **LogManager**, **Logger**, **Handler**, and **Formatter**.
- **SLF4J** is primarily an API/facade. It does not impose a single common backend configuration across all applications.
- **Logback** is a logging backend commonly paired with SLF4J; it has a file-loading mechanism or a fallback configuration when no file is found.
- **Log4j2** consists of an API and an implementation (Log4j Core); you must check both whether the implementation is on the runtime classpath and the actual configuration.
- **Spring Boot** has its own logging configuration layer. When using the default starter, Boot typically initializes Logback and provides console/level settings. Therefore, the default behavior of a Boot application differs from the fallback behavior of standalone Logback.

An application may contain multiple logging APIs pulled in by different dependencies. Bridges/adapters can route them to a single backend, but if there are multiple providers or incompatible adapters, the result may be inconsistent or produce warnings. Only by identifying the **final backend** do you know where levels, patterns, and destinations are applied.

## 3. Common Defaults Comparison Table

The entries below apply when using the named implementation directly, without custom configuration or special environment variables. Versions and integrated frameworks may change behavior.

| Environment | Common Default When Unconfigured | Key Points to Remember |
| --- | --- | --- |
| **JDK 17 – java.util.logging (JUL)** | Loads settings from the JDK's **conf/logging.properties** file; typical JDK config has a root logger and console handler at INFO level. | The JDK config file may be modified by the distributor/system administrator. Handlers also filter levels independently. |
| **SLF4J 2.x API only, no provider** | Emits a missing-provider warning and uses a NOP logger, discarding log events. | It is not "SLF4J defaults to console INFO". |
| **Standalone Logback Classic, no config found** | **BasicConfigurator** fallback: ConsoleAppender on root, root level **DEBUG**. | Differs from the default provided by Spring Boot. |
| **Log4j Core, no config found** | **DefaultConfiguration** fallback: console, typical root level **ERROR**. | The value can be changed via the **log4j2.level** property. |
| **Spring Boot with default logging starter** | Typically uses Logback; prints INFO, WARN, ERROR to console, does not write to a file unless configured. | Boot applies Boot's own configuration; do not infer from BasicConfigurator. |

**Note:** level names are not completely identical. JUL uses **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**; Logback uses **ERROR, WARN, INFO, DEBUG, TRACE**; Log4j2 also has **FATAL**. When reading the table, do not treat FINE and DEBUG or WARNING and WARN as identical classes/enums.

## 4. Defaults of java.util.logging (JUL) in the JDK

JUL is built into the JDK, so the examples do not require Maven, Gradle, or external libraries. The JDK ships with a standard configuration file typically located at:

~~~text
<JAVA_HOME>/conf/logging.properties
~~~

In a typical JDK 17 installation, this file configures a **ConsoleHandler** for the root logger and uses the INFO level. **ConsoleHandler** writes to **System.err**, not System.out, and usually uses **SimpleFormatter**. The specific values remain configuration data of the running JDK build, not invariants of the Java language.

### 4.1. Java 17: Observing the Actual Effective Configuration

Create the file **DefaultLoggingDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogManager;
import java.util.logging.Logger;

public class DefaultLoggingDemo {
    public static void main(String[] args) {
        Logger log = Logger.getLogger("course.logging.DefaultLoggingDemo");
        Logger root = LogManager.getLogManager().getLogger("");

        System.out.println("logger-level="
                + (log.getLevel() == null
                    ? "<inherited>" : log.getLevel().getName()));
        System.out.println("root-level="
                + (root.getLevel() == null
                    ? "<inherited>" : root.getLevel().getName()));
        System.out.println("INFO-enabled=" + log.isLoggable(Level.INFO));
        System.out.println("FINE-enabled=" + log.isLoggable(Level.FINE));

        for (Handler handler : root.getHandlers()) {
            System.out.println("root-handler="
                    + handler.getClass().getSimpleName()
                    + ", level=" + handler.getLevel().getName());
        }

        log.info("Order was accepted");
        log.fine("Detailed processing data");
    }
}
~~~

Compile and run:

~~~bash
javac DefaultLoggingDemo.java
java DefaultLoggingDemo
~~~

On **JDK 17 with a typical default JUL configuration, not overridden by JVM options or application code**, stdout is:

~~~text
logger-level=<inherited>
root-level=INFO
INFO-enabled=true
FINE-enabled=false
root-handler=ConsoleHandler, level=INFO
~~~

In addition, there is an **INFO: Order was accepted** record on stderr with timestamp/logger details formatted by **SimpleFormatter**. Time, formatting, locale, and ordering when stdout/stderr are merged may vary, so that part should not be treated as fixed stdout. The **log.fine** call does not produce a log line under the INFO configuration above.

If your machine's output differs, that is precisely what needs checking: the defaults may have been overridden.

### 4.2. Logger Level and Handler Level Are Two Separate Filters

A record appears only when it passes **all relevant filtering layers**:

1. The logger emits the record if the record's level is permitted by the logger's effective level.
2. A Filter (if present) may reject the record.
3. The handler receives the record and checks its own level/Filter before outputting.
4. The formatter and stream determine the representation and display target.

For example, suppose the root logger is set to INFO and ConsoleHandler is also INFO. If a child logger calls:

~~~java
// Illustrative snippet added to an application using JUL.
log.setLevel(Level.FINE);
log.fine("Debug detail");
~~~

The child logger has accepted FINE, but **ConsoleHandler can still drop it** because the handler is at INFO. Changing only the logger level does not guarantee FINE appears: you must check both the handler level and any filters. Conversely, changing the handler to FINE while the logger still inherits INFO is also not enough.

### 4.3. Log Level Inheritance

JUL logger names are usually hierarchical using dots, such as **course**, **course.orders**, **course.orders.OrderService**. If a child logger does not have an explicit level set, **getLevel() returns null** (meaning no level is directly assigned), and it obtains its effective level from the appropriate parent logger. This does not mean the logger is disabled.

The **root logger** has an empty string as its name. Do not use **getLevel() == null** to conclude that the system has no default; check **isLoggable(level)** and the parent/handler configuration.

### 4.4. How to Override JUL with a Properties File

Create a custom **logging.properties** file for the application:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=WARNING
java.util.logging.ConsoleHandler.level=WARNING
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
course.logging.level=FINE
~~~

Run from the directory containing the file:

~~~bash
java -Djava.util.logging.config.file=logging.properties DefaultLoggingDemo
~~~

This file **replaces the initial JUL configuration source** that LogManager reads under normal circumstances. In the example above, the **course.logging** logger is set to FINE, but the root handler remains WARNING; therefore, the program's INFO/FINE logs do not appear in ConsoleHandler. You can change **java.util.logging.ConsoleHandler.level=FINE** to see the effect of the handler level; note that root and parent loggers still follow their own inheritance rules.

The file location must be a path readable by the running JVM. Changing the JVM option after JUL has already initialized does not automatically make the whole system reload the configuration; reloading requires LogManager mechanisms or an appropriate lifecycle.

## 5. SLF4J: Without a Provider, There Is No Useful Logging Configuration

Suppose application code uses:

~~~java
// Illustration for a project that already has SLF4J:
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

LOG.info("Order created: {}", orderId);
~~~

This snippet is illustrative code, **not a standalone compilable Java class**: it requires SLF4J, the **OrderService** class, and the **orderId** variable.

With **SLF4J 2.x**, if the runtime only has **slf4j-api** without a provider recognized by ServiceLoader, SLF4J emits a missing-provider warning and uses the **NOP logger**. No INFO lines are processed by any backend even though calling LOG.info succeeds. Providers can be Logback Classic, SLF4J Simple, or an adapter to JUL/Log4j2; default behavior depends on the chosen provider.

Distinguish:

- **SLF4J API** determines the logger call syntax and common interface.
- **Provider/backend** determines log levels, appenders, encoders, output, and how configuration is loaded.
- **Bridge** forwards logs from another API to the chosen backend when properly configured.
- A project should control the number of compatible providers/bindings on the runtime classpath; multiple providers can cause warnings or unpredictable backend selection.
- SLF4J 1.7 and SLF4J 2.x have different backend discovery mechanisms; avoid mixing an old provider with a new API without checking versions.

How to check: inspect the dependency tree and startup warnings, then identify **which backend is actually being used**. Do not try to change a Logback pattern when the application only has a JUL provider.

## 6. Standalone Logback Classic: When No Configuration File Exists

Logback typically searches for configuration on the classpath, notably **logback-test.xml** for tests and **logback.xml** for the application. When no suitable configuration is found and no other mechanism intervenes, Logback Classic falls back to **BasicConfigurator** with a **ConsoleAppender** attached to root and root set to **DEBUG**.

This explains why a plain Java application using SLF4J + Logback can show DEBUG output even when you have not written any configuration. However, a **Spring Boot** application may load its own logging configuration beforehand, so do not apply the root DEBUG conclusion to every Logback project.

A minimal configuration example, placed at **src/main/resources/logback.xml** in a project using Logback:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Once this file exists and is loaded properly, the root level is **explicitly set to INFO**; this is a **custom configuration**, no longer the BasicConfigurator fallback. It can differ from the default in both level and pattern. Child loggers without their own defined level can inherit the level from root.

Things to remember:

- **logback.xml** is a resource on the runtime classpath, not merely a file sitting somewhere in the repository.
- A **logback-test.xml** file on the test runtime classpath can make logs during tests differ from running the application.
- Root appenders and logger appenders can cause **duplicate logs** if additivity/inheritance causes the same event to pass through multiple appenders.
- There may be more Logback configuration mechanisms than the common file names; if behavior differs from expectations, check the status/configuration actually loaded by the backend.

## 7. Log4j2: Log4j Core's Fallback Is Not Like Logback's

Applications using Log4j2 must distinguish **Log4j API** from **Log4j Core** or a suitable implementation. When using Log4j Core and no configuration file is detected, Core uses **DefaultConfiguration** and emits messages from the status logger. The typical default root level is **ERROR**; the console displays logs that meet that threshold. The **log4j2.level** property can adjust the root level of the default configuration.

Log4j2 typically looks for configuration names such as **log4j2-test.xml**, **log4j2.xml**, and other supported formats/variants. When a specific configuration file is present, its contents determine appenders, levels, filters, and layouts; do not apply the ERROR fallback rule mechanically.

Minimal **log4j2.xml** example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

This is a **custom configuration** switching root to INFO, not a verbatim description of DefaultConfiguration. The file name, classpath location, and **log4j-core** dependency must match the runtime. Log4j2 documentation allows specifying the file location via **log4j2.configurationFile**; default files vary by discovery mechanism and version.

**Comparison example:** the same **logger.info("Started")** call may appear under Logback's DEBUG fallback, but not appear when Log4j Core is using its ERROR fallback. That is why the first step is to check the backend before changing code.

## 8. Spring Boot: "No logback.xml" Still Has Boot's Default Logging

When a Spring Boot project uses the standard logging starter, Boot typically selects Logback and supplies its own logging configuration at startup. Common default characteristics:

- Logs to the **console**.
- Displays **INFO**, **WARN**, and **ERROR**.
- Does not create a log file automatically unless file output settings are enabled.
- Console format includes timestamp, level, process ID, thread name, logger name, and message according to the running Boot version/configuration.
- Can capture logs from other libraries through bridges configured appropriately by the starter.

Thus, a Boot project using Logback **without logback.xml** can still show only INFO and above; it is using Boot's default setup, not standalone Logback's DEBUG fallback.

### 8.1. Minimal Changes via application.properties

Place the following lines in **src/main/resources/application.properties**:

~~~properties
# Default level for most loggers
logging.level.root=INFO

# Enable DEBUG for the application's package when investigation is needed
logging.level.com.example.orders=DEBUG

# Optional example: enable file logging alongside console
logging.file.name=logs/application.log
~~~

This is a **user-defined configuration**; not all of these values are applied by Boot when the project is unconfigured. The path **logs/application.log** is relative to the current working directory, so you must check write permissions, volumes, and where the container runs. If you omit **logging.file.name**, Boot normally logs only to the console. Boot's file output property names are **logging.file.name** or **logging.file.path** in modern versions; avoid copying outdated properties from old tutorials.

You can use the equivalent **application.yaml**:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
  file:
    name: logs/application.log
~~~

In examples, pick only one primary configuration format suited to the project, and avoid declaring the same key with conflicting values across multiple files/profiles without knowing the precedence order.

### 8.2. Spring Boot Debug Mode Does Not Mean Root DEBUG

The **--debug** argument or **debug=true** causes Boot to enable additional logging for certain framework logger groups; **it does not automatically switch every logger in the entire application to DEBUG**. If you want DEBUG for code in a specific package, set **logging.level.<package>=DEBUG**; to change root, use **logging.level.root=DEBUG**.

Note that an application can change logging by **profile**, environment variable, command line, and dedicated configuration files. Therefore, finding a line in application.properties does not prove it is the final applied value.

### 8.3. Advanced Configuration Files

When you need to control multiple appenders, rolling policies, filters, and layouts in Logback style, Boot recommends using **logback-spring.xml** when possible to take advantage of Boot's integration; for Log4j2, use **log4j2-spring.xml** where appropriate. The **logging.config** property can be used to specify the configuration path.

Logging initializes very early, before the application context finishes. Do not expect an **@PropertySource** on a configuration bean to be read early enough to govern the entire logging bootstrap.

## 9. Default Config, Inheritance, and Precedence Order

There is no single unified precedence list that applies to JUL, Logback, Log4j2, and Spring Boot. Each system has its own file discovery algorithm, defaults, system properties, and initialization timing. Use the following process instead of guessing the order:

1. **Identify the API and backend:** does the code call JUL or SLF4J? If SLF4J, is the actual provider Logback, Log4j2, or something else?
2. **Identify the environment:** standalone Java SE app, Spring Boot, servlet container, test runner, or a third-party managed host?
3. **Find the loaded configuration source:** JDK **conf/logging.properties**, XML/properties files on the classpath, JVM arguments, **logging.config**, profiles, or programmatic configuration.
4. **Find the effective level:** logger levels may inherit from a parent; handlers/appenders and filters may further drop events.
5. **Identify the output:** console stdout or stderr, a file in which working directory, or a centralized appender/collector?
6. **Verify in practice:** run a test logger with INFO and DEBUG/FINE, inspect records in the actual runtime environment and backend logger status if available.

### Causes Table When the Same Code Produces Different Results

| Symptom | Possibilities to Check |
| --- | --- |
| Java SE app using JUL prints INFO but not FINE | Root or ConsoleHandler is at INFO, or both. |
| SLF4J app prints no logs despite calling logger | No compatible provider; provider is NOP; filter/level disabled; sink error. |
| Standalone Logback prints DEBUG even without logback.xml | BasicConfigurator fallback sets root DEBUG. |
| Project using Logback only prints INFO and above | Spring Boot default configuration, or a file/properties changed the root level. |
| Log4j Core only prints ERROR when unconfigured | DefaultConfiguration typically sets root ERROR. |
| Tests print more logs than production runs | Test classpath has its own config file, different profile, or different dependencies. |
| INFO still does not appear after setting logger level INFO | Handler/appender filter has a higher threshold, logger is disabled elsewhere, or provider/sink is mismatched. |
| Logs appear twice | Multiple appenders receive the same event, or appender additivity/inheritance causes duplicate writes. |

**Exact distinction:** the **logger** level decides whether a record is emitted at the logger layer; the **handler/appender** level and filters can filter further. Meanwhile, console colors, timestamps, and thread names are the responsibility of the formatter/layout, and do not independently decide whether a log level is accepted.

## 10. How to Self-Verify on a Running Project

A short, reproducible diagnostic workflow:

### Step 1: Inspect Classpath and Dependencies

With Gradle or Maven, check runtime dependencies. Look for **slf4j-api**, **logback-classic**, **log4j-core**, adapters/bridges, and logging starters. Use the project's dependency report to see which provider is actually present. Do not randomly swap libraries just to "see if logs appear."

### Step 2: Emit a Deliberate Test Log

In a class belonging to the package you want to inspect, log one INFO line and one DEBUG/FINE line. For JUL, you can use the standalone program in section 4. For SLF4J, use the application's program that already has the dependency. Log simple test messages; do not use user accounts, secrets, tokens, or real data.

### Step 3: Distinguish Three Situations

- **No event:** level/filter, NOP provider, wrong logger, wrong code path, or event not yet invoked.
- **Event emitted but not seen at destination:** appender/handler, file path, write permissions, sink error, collector pipeline, or async buffer.
- **Event present but wrong format:** layout/formatter, timezone, logger name, MDC, or structured logging mapping.

### Step 4: Check the Actual Runtime Environment

An application launched from an IDE has a different working directory than a container or CI. Environment variables, JVM system properties, profiles, and runtime classpaths may differ. With containers, console logs are typically collected by the container runtime, but that does not mean the application also writes a file on its own. Confirm actual output via stdout/stderr and the log agent.

### Step 5: Document Defaults and Overrides

Once you find the right configuration, record it in operational documentation: backend/version, config source, root level, logger exceptions, appenders, retention/rotation if any, and error behavior. "No file in the repository" by itself is not sufficient proof of a default.

## 11. Common Mistakes

**Confusing framework defaults.** "Logback root defaults to DEBUG" only describes the BasicConfigurator fallback under the right conditions; Boot typically defaults to INFO for its applications. Likewise, JUL, Log4j Core, and SLF4J do not share a single configuration.

**Assuming SLF4J writes to the console on its own.** SLF4J is an abstraction; it needs a provider/backend. With SLF4J 2.x and no provider, the warning paired with the NOP logger is a signal that needs fixing.

**Setting only the logger level and concluding the backend is broken.** Especially with JUL, ConsoleHandler also has its own level. With other backends, appender filters, thresholds, and routing can drop events.

**Silencing too many logs with root level ERROR.** In operations, you may miss useful INFO/WARN details. Conversely, root DEBUG/TRACE in production can increase I/O, storage costs, and the risk of exposing sensitive data. Choose levels by environment and purpose, enabling detail on specific packages when needed.

**Placing the config file on the wrong classpath.** Having **logback.xml** or **log4j2.xml** in the project directory does not guarantee it is packaged into runtime. Check actual resources in the JAR/CLASSPATH and configuration values from the environment.

**Using Boot's --debug flag and expecting system-wide DEBUG.** This argument has a specific meaning in Boot; it is not a substitute for logging.level.root=DEBUG or logging.level.<package>=DEBUG.

**Forgetting the difference between stdout and stderr.** JUL's ConsoleHandler writes to stderr by default; many other console appenders may write to stdout depending on configuration. Collectors separating streams can sometimes make you think logs were lost.

**Confusing default logging with data durability.** Console logging does not guarantee logs are persisted long-term. Production requires collectors, retention, rotation, and error alerting.

**Putting sensitive data into test logs.** Default configurations can expose messages directly on the console and in log collectors. Protect secrets by filtering/redacting data from the start.

## 12. Self-Check Exercises

1. Run **DefaultLoggingDemo.java** on an uncustomized JDK 17. Record the root level, number of handlers, where INFO appears, why FINE does not appear, and the lines printed to stdout/stderr.
2. Create **logging.properties** from section 4.4 and run again. Predict the INFO/FINE filtering result beforehand; check the logger level, effective level, and handler level separately.
3. In a standalone SLF4J + Logback application with no config file, inspect the root level and appender. Add logback.xml setting root to INFO and confirm the change.
4. If you have a Spring Boot project, remove custom logging config files in a controlled test environment and observe the console. Try changing only one package's logging.level and confirm that package's DEBUG output changes without changing root.
5. With Log4j Core, compare using DefaultConfiguration against adding log4j2.xml with root set to INFO. Note the differences from Logback and Boot.

Comprehension check questions:

- Why does **getLevel() == null** not mean the logger is OFF?
- Why can a JUL Logger at FINE still fail to show FINE lines?
- Why is missing an SLF4J provider different from missing logback.xml?
- Why can't you say "Java logging defaults to INFO" without naming the framework?
- Which logging values must be checked at runtime before concluding what configuration is in effect?

## 13. Takeaways

**Default logging configuration is the behavior of a specific stack, not a general rule of Java syntax.** JUL takes initial settings from LogManager/JDK; SLF4J needs a provider; Logback and Log4j Core have their own fallbacks; Spring Boot has the framework's logging auto-configuration. To understand which logs appear and where they go, always trace from **runtime dependencies → loaded config → logger effective level → handler/appender/filter → formatter/output**. Keep helpful defaults while learning, but in real applications explicitly configure key operational factors and verify on the target runtime environment.

### Official Documentation

- Oracle Java 17 – Java Logging Overview: https://docs.oracle.com/en/java/javase/17/core/java-logging-overview.html
- Oracle Java 17 – ConsoleHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- SLF4J – Manual and missing provider errors: https://www.slf4j.org/manual.html and https://www.slf4j.org/codes.html
- Logback – Configuration, BasicConfigurator fallback: https://logback.qos.ch/manual/configuration.html
- Apache Log4j2 – Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Apache Log4j2 – Configuration properties: https://logging.apache.org/log4j/2.x/manual/systemproperties.html
- Spring Boot – Logging reference: https://docs.spring.io/spring-boot/reference/features/logging.html
