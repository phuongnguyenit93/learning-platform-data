# Avoiding Environment Configuration Mixing in Java Logging

## Objectives

When a Java application runs in **development (dev)**, **test**, **staging**, and **production (prod)**, logging goals can differ. Developers need information for debugging; testing needs reproducible results; staging needs behavior observation close to production; production needs stable logs sufficient for operations, with cost control and data protection. **Avoiding environment configuration mixing** means that the same application artifact always uses **the approved logging policy for the running environment**, even when multiple configuration layers, profiles, and environment variables coexist.

After this lesson, you will:

1. Distinguish between **deployment environment**, **Spring profile**, **logging backend**, and **effective logging configuration**.
2. Know how to choose levels, destinations, layouts, retention, and allowed log data for each environment.
3. Understand why packaged configuration files, environment variables, JVM system properties, and command-line arguments can override one another.
4. Design a single deployable artifact across multiple environments without accidentally copying parameters.
5. Run a standalone Java 17 example with **java.util.logging** and identify the active policy.
6. Know how to test, diagnose, and prevent production from accidentally enabling DEBUG/TRACE, writing to the wrong file, or sending logs to another system.

## 1. What Is the “Environment Configuration Mixing” Problem?

This is the error where **environment A accidentally uses part or all of environment B's logging configuration**, or the application combines so many configuration sources that it is no longer clear which policy is in effect.

Examples:

- Production accidentally runs with **root level DEBUG**, causing log volume to spike and potentially exposing data in debug messages.
- Staging sends logs to the same **index, tenant, bucket, or dashboard** as production; test records pollute operational signals.
- A production container uses **an absolute file path from a developer's machine**, failing to write logs or writing to an uncollected disk.
- A build works in dev, but test has **logback-test.xml** and production has a different **logback.xml** without anyone tracking it.
- Configuration in **application-prod.yml** sets INFO, but the environment variable **LOGGING_LEVEL_ROOT=DEBUG** in the deployment has higher precedence.
- An application running in multiple environments uses the same **service name + environment tag**, mixing observability data and making incident filtering difficult.

Configuration mixing is not just about the wrong log level. It also involves **log destination, format, sensitive data, log lifecycle, retention policy, trace correlation, and log access permissions**.

~~~text
Same source code / same artifact
            │
          Deploy
            │
    ┌───────┼─────────┬─────────┐
    ▼       ▼         ▼         ▼
   dev     test     staging    prod
    │       │         │         │
    ▼       ▼         ▼         ▼
  policy  policy    policy    policy
    │       │         │         │
    └───────┴─────────┴─────────┘
        Logging backend
             │
     Correct level / destination
     Correct environment label
     Correct data protection
~~~

In the diagram, environments may share the same backend, but **policy values and collection destinations** are explicitly chosen for each environment.

## 2. Distinguishing Easily Confused Concepts

| Concept | Role | What Not to Assume |
| --- | --- | --- |
| **Runtime environment** | Where the app runs: local, CI test, staging, production. | The environment name does not automatically configure logging without a mechanism that reads it. |
| **Spring profile** | Active Spring configuration group, such as dev or prod. | A profile is not automatically equivalent to a namespace or infrastructure access rights. |
| **Logger level** | Event acceptance threshold at the logger; can inherit from root/parent. | Setting a logger to DEBUG does not guarantee the appender/handler will pass it through. |
| **Appender/handler** | Component that writes events to console, file, or sink. | Having an appender does not mean the sink persists reliably or has write permissions. |
| **Formatter/encoder/layout** | How an event is represented, such as text or JSON. | Changing the layout does not mean the log destination has changed. |
| **Logging backend/provider** | Logback, Log4j2, JUL, or another backend that executes logging. | Using the SLF4J API does not mean the backend is Logback. |
| **Configuration source** | Properties/YAML/XML, env var, system property, command line, runtime code. | A file in the repo is not necessarily the final source of truth. |
| **Environment label** | Field used to filter logs by environment in a collector/backend. | A correct label does not compensate for sending logs to the wrong account/tenant. |

The most important rule is to **verify the values actually active**, rather than stopping at reading an intended configuration file.

## 3. Choosing a Logging Policy per Environment

The following table is a **sample policy for learning and design**, not a mandatory default of Java, Logback, Log4j2, or Spring Boot. Adjust it to fit your system's needs.

| Factor | Dev | Automated test | Staging | Production |
| --- | --- | --- | --- | --- |
| Suggested root level | INFO; DEBUG for the package under development | WARN/ERROR, unless a test needs to verify INFO | INFO | INFO or an operationally approved level |
| DEBUG/TRACE | Enabled selectively, temporarily | Only for specific test cases | Time-bound, scoped to specific packages | Only during time-bound, controlled incident troubleshooting |
| Log destination | Console/IDE; local file if needed | Console or isolated test sink | Dedicated staging collector/namespace | Dedicated production collector/namespace |
| Environment label | dev | test | staging | prod |
| Representation | Human-readable for developers | Stable and easy to assert | Compatible with production pipeline | Standard format with correlation ID |
| Sensitive data | Still must be redacted; do not log secrets | Dummy data; do not use real secrets | Use safe test data | Strictly controlled, minimize PII/secrets |
| Rotation / retention | Lightweight, local | Short or cleaned up after tests | Per staging budget and policy | Per organization's retention and access policy |
| Behavior on config error | Clear message to fix | Fail test if needed | Do not proceed if destination/label is critically wrong | Fail deploy/startup for safety-impacting discrepancies |

**Principle:** log level is just one parameter. Each environment needs a policy covering **level + destination + format + metadata + allowed log data + lifecycle/retention**.

A safe operational default can be **root INFO, console output, no verbose logging or external log shipping when configuration is missing**. For services requiring explicit destination and environment identification, **refuse to start** without a valid environment identifier. Avoid defaulting to dev/DEBUG when a configuration variable is missing: that is an easy way to flood production with logs.

## 4. Which Configuration Source Wins?

Depending on the backend, configuration can come from:

1. **JDK/backend/framework defaults.**
2. **Resources packaged inside the application:** logging.properties, logback.xml, logback-spring.xml, log4j2.xml, application.yml, application-prod.yml...
3. **Files external to the artifact:** files mounted via Kubernetes Secret/ConfigMap, host config files, or release system files.
4. **Environment variables:** such as SPRING_PROFILES_ACTIVE, LOGGING_LEVEL_ROOT, or custom application-defined variables.
5. **JVM system properties:** passed at startup with -D..., such as java.util.logging.config.file or logback.configurationFile.
6. **Command-line properties:** with Spring Boot, such as --spring.profiles.active=prod, --logging.level.root=INFO.
7. **Configuration modified by code/framework at runtime.**

**There is no single universal precedence order.** In Spring Boot, property sources have a documented precedence order; command-line properties typically override file-based configuration. In JUL, LogManager reads JUL's own logging configuration. In Logback, configuration file lookup and initialization follow a different order. Log4j2 has its own rules.

In practice, answer three questions:

- **Which sources were loaded?** For example, was application-prod.yml actually applied to this process?
- **Did a higher-precedence source override it?** For example, was the same key logging.level.root set in an env var or command line?
- **What are the final values and actual destination?** Record the effective level, appender/handler, and log routing after initialization.

Do not guess precedence from experience with another version; check the documentation for the **running version** and test with an actual process.

## 5. Designing Configuration with “Safe Base + Environment Differences”

A maintainable approach is to place shared properties in a base configuration and only override what **genuinely needs to differ**. Do not duplicate entire logging files per environment if only a few levels differ, because when updating a shared pattern or filter, copies can drift out of sync.

Reference model:

~~~text
Shared configuration (root INFO; controlled output)
              │
              ▼
      Environment profile
     /       |       \
    dev    staging    prod
     \       |       /
       External overrides
           approved
              │
              ▼
        Effective config
              │
              ▼
         Startup check
~~~

Separate two scopes:

- **Invariant or shared standards:** JSON field names, redaction rules, correlation ID name, timestamp conventions, schema, and service identification scheme.
- **Environment-specific:** verbosity, sampling, sink/tenant, retention, file paths, or collector parameters (provisioned per deployment).

Avoid packaging production collector endpoints or production credentials into default files hoping dev will override everything. The fewer external connections and the safer the defaults, the lower the risk of environment mixing.

## 6. Spring Boot Example: Isolating Logging with Profiles

With Spring Boot using the default logging starter (typically Logback), common levels can be managed via **application.yml** and **application-{profile}.yml** files. Spring Boot supports other backends as well, but this example uses Boot's generic logging properties and **does not replace advanced backend-specific configuration**.

Suppose the structure is:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-test.yml
├── application-staging.yml
└── application-prod.yml
~~~

**application.yml** (base policy: limit default verbosity):

~~~yaml
spring:
  application:
    name: order-service

logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

**application-dev.yml** (allow debugging application code in dev):

~~~yaml
logging:
  level:
    com.example.orders: DEBUG
~~~

**application-test.yml** (reduce noise during tests, if the suite does not need to capture INFO):

~~~yaml
logging:
  level:
    root: WARN
    com.example.orders: WARN
~~~

**application-staging.yml** (keep policy close to production; avoid flooding DEBUG system-wide):

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

**application-prod.yml** (root INFO, prevent accidental debug from the application package):

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

These files are **configuration examples**, not a standalone runnable program. The package **com.example.orders** is just a placeholder package name and must be changed for your application. Because profiles only change levels, separate XML appender files are not needed yet.

### 6.1. Activating a Profile Explicitly

Example when running a packaged application named **order-service.jar**:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
java -jar order-service.jar --spring.profiles.active=staging
java -jar order-service.jar --spring.profiles.active=prod
~~~

These three commands are **three independent runs**, selecting **one** deployment environment per process. The JAR name is illustrative. In real deployments, **SPRING_PROFILES_ACTIVE** is usually provided via environment configuration; the example above uses the command line to make the selected value explicit.

**Do not put spring.profiles.active inside application-prod.yml expecting the file to activate itself.** The profile must be selected from a configuration source read at the right startup phase, such as an environment variable, command line, or appropriate base file.

If no profile is selected, Spring Boot may use the **default** profile, meaning the app runs with **application.yml** and other valid sources. Therefore, a deployment check is needed to prevent production from starting without the prod profile. A Spring profile is not the sole infrastructure identification mechanism: a process could still be started with the wrong profile in a production namespace.

### 6.2. Be Careful When Multiple Profiles Are Active

Spring Boot can activate multiple profiles, such as an environment profile and a feature profile. Having multiple profiles is not automatically an error. However, by operational convention, **dev/test/staging/prod should be mutually exclusive**: a deployment belongs to exactly one environment. If both dev and prod are active, both files can participate in resolution and lead to unpredictable log levels.

Establish a startup/CI check ensuring the environment profile group has **exactly one** value. Feature profiles (e.g., metrics-enabled) can be active alongside it if designed and tested separately.

### 6.3. Environment Variables Can Override Profile Files

In Spring Boot, **LOGGING_LEVEL_ROOT=DEBUG** configures the root logger level from the environment. Even if **application-prod.yml** specifies INFO, a higher-precedence override can still cause the process to run at DEBUG.

In many environments, you cannot guarantee the right configuration just by inspecting files inside the JAR. You must also check:

- Deployment environment variables and command-line arguments.
- ConfigMap/Secret, Helm values, and final rendered templates if using an orchestrator.
- Higher-precedence Spring property sources.
- Effective levels after the application initializes.

Spring Boot supports environment variable mapping for package-level logging; changing a specific class logger via env var has limitations due to relaxed binding rules. When setting a level for a specific **class**, prefer standard logger names in properties/YAML or the backend's native mechanism rather than guessing env variable representation.

### 6.4. Avoid Accidental Configuration in Code

Anti-patterns:

~~~java
// Anti-pattern: production missing APP_ENV will be treated as dev.
String environment = System.getenv().getOrDefault("APP_ENV", "dev");
~~~

~~~java
// Anti-pattern: unconditionally modifying the global log level.
java.util.logging.Logger.getLogger("")
        .setLevel(java.util.logging.Level.FINE);
~~~

Instead, validate the environment and use an explicit policy, or let the framework configure logging uniformly from a controlled source. **Do not set log levels across multiple beans/configurators without knowing which component runs last.**

## 7. Standalone Java 17 Example: Selecting the Right JUL Policy

To observe this mechanism without Spring Boot, we use **java.util.logging (JUL)** built into JDK 17. The program requires **one environment name** at startup; only four names are valid: dev, test, staging, prod. Missing or invalid names are rejected instead of silently enabling debug.

The program sets the same level on both the **root logger** and **ConsoleHandler**, because JUL filters at both places. It also prints the active environment name for easy verification. The log format is fixed for the demo so output is predictable.

Save as **EnvironmentLoggingDemo.java**:

~~~java
import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class EnvironmentLoggingDemo {

    private static Level levelFor(String environment) {
        return switch (environment) {
            case "dev" -> Level.FINE;
            case "test" -> Level.WARNING;
            case "staging", "prod" -> Level.INFO;
            default -> throw new IllegalArgumentException(
                    "Unknown environment: " + environment);
        };
    }

    private static Logger configure(Level level) {
        Logger root = Logger.getLogger("");

        for (Handler old : root.getHandlers()) {
            root.removeHandler(old);
            old.close();
        }

        root.setLevel(level);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(level);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + ": " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        root.addHandler(console);
        return root;
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java EnvironmentLoggingDemo dev|test|staging|prod");
            System.exit(2);
            return;
        }

        String environment = args[0].toLowerCase(Locale.ROOT);
        final Level level;
        try {
            level = levelFor(environment);
        } catch (IllegalArgumentException ex) {
            System.err.println(ex.getMessage());
            System.exit(2);
            return;
        }

        Logger root = configure(level);
        Logger log = Logger.getLogger("example.orders");
        log.setLevel(null); // Inherit root level for demo.

        System.out.println("environment=" + environment);
        System.out.println("root-level=" + root.getLevel().getName());

        log.fine("Chi tiet xu ly");
        log.info("Da nhan yeu cau");
        log.warning("Do tre tang");
    }
}
~~~

Compile:

~~~bash
javac EnvironmentLoggingDemo.java
~~~

Run with dev:

~~~bash
java EnvironmentLoggingDemo dev
~~~

**stdout** of the command above:

~~~text
environment=dev
root-level=FINE
~~~

**stderr** emitted by JUL ConsoleHandler:

~~~text
FINE: Chi tiet xu ly
INFO: Da nhan yeu cau
WARNING: Do tre tang
~~~

Run with production:

~~~bash
java EnvironmentLoggingDemo prod
~~~

**stdout**:

~~~text
environment=prod
root-level=INFO
~~~

**stderr**:

~~~text
INFO: Da nhan yeu cau
WARNING: Do tre tang
~~~

Command with an invalid environment:

~~~bash
java EnvironmentLoggingDemo unknown
~~~

Printed to stderr:

~~~text
Unknown environment: unknown
~~~

The process exits with **exit code 2**. No “dev” logging policy is silently applied.

Note carefully about output: **ConsoleHandler writes to stderr**, while the two identification lines in the program write to stdout. If a terminal/IDE merges both streams, display ordering between them is not guaranteed; verify **each stream separately**. The example intentionally uses ASCII in log messages so output does not depend on terminal encoding.

**Takeaway from the demo:** environment separation is shown in three verifiable behaviors: the env is explicitly identified, the log threshold is consistently applied to both logger and handler, and an invalid environment is not treated as dev. The code only demonstrates **level and console handler**; a real production system must also decide sink, schema, permissions, and retention.

In large programs, do not arbitrarily modify the root logger or close handlers while other subsystems are logging. Configuring JUL as in the demo is suitable for learning at startup; in framework-based applications, use the framework's configuration API or a configuration file loaded before loggers start operating.

## 8. With Real-World JUL: Separating Configuration Files

JUL allows using **java.util.logging.config.file** to select a properties file at JVM startup. Instead of setting log levels in code mid-lifecycle, you can manage separate files per environment.

Example **logging-dev.properties**:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
com.example.orders.level=FINE
~~~

Example **logging-prod.properties**:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
com.example.orders.level=INFO
~~~

In the dev example above, only the **com.example.orders** namespace is allowed FINE; root is at INFO. The handler is allowed FINE so FINE logs from the child logger are not blocked. This is **selective configuration**, unlike the section 7 demo which sets the entire root to FINE.

Select the right file at startup, for example:

~~~bash
java -Djava.util.logging.config.file=logging-dev.properties -cp out com.example.orders.Main
java -Djava.util.logging.config.file=logging-prod.properties -cp out com.example.orders.Main
~~~

These two commands illustrate an application that already has **com.example.orders.Main** compiled in **out**; they are not commands to run the standalone section 7 demo. In production, the file path must be provisioned by the corresponding deployment and validated before running.

Do not create a default file named “prod” inside a dev image if there is a risk of it being referenced by mistake. If choosing relative paths, remember that the **working directory** can differ across IDEs, containers, Windows services, and CI.

## 9. With Logback and Log4j2: Separating Backend Configuration

In applications using **SLF4J + Logback**, the backend typically reads **logback.xml** from the classpath, a separate test file **logback-test.xml** on the test classpath, or a path specified via the JVM system property **logback.configurationFile**. Crucially, a filename existing in the repository does not prove that file is loaded at runtime.

Example selecting Logback configuration from a deployment-provisioned path:

~~~bash
java -Dlogback.configurationFile=/etc/order-service/logback-prod.xml -jar order-service.jar
~~~

The command above illustrates a Unix-like environment; paths differ on Windows. Ensure the path and file actually exist, have read permissions, and the system property is set **before** Logback initializes. Do not use the same file that connects to remote production in dev.

With **Log4j2**, you can use **log4j2.xml** or external configuration via **log4j2.configurationFile** depending on backend/version. Verify the exact API/backend in use and status messages during initialization. Regardless of XML/JSON/YAML format, maintain one approved source of control for levels, appenders, rollover, and routing.

### 9.1. Spring Boot and logback-spring.xml

If Spring Boot needs deeper configuration beyond **logging.level.*** keys, you can use **logback-spring.xml**. This file supports Boot extensions such as **springProfile** to select configuration blocks by profile.

**Standalone XML illustration**, for Spring Boot applications with Logback integrated:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="dev">
        <root level="DEBUG">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="!dev">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>
</configuration>
~~~

In this example, dev runs root DEBUG; all cases **without dev** run root INFO. This **is not a policy that guarantees the right environment** if a process is assigned both dev and prod simultaneously; a profile validation step and a convention that only one environment profile is active are needed. If you choose to configure levels via this XML, avoid declaring conflicting policies in application.yml/env vars without actively managing precedence.

Use **logback-spring.xml** instead of **logback.xml** if you need **springProfile** syntax and Boot extensions. Logback's scan/reload mechanism is incompatible with these extensions according to Spring Boot documentation; do not enable `scan=true` arbitrarily. When only changing levels by profile, **application-{profile}.yml** files are usually simpler and easier to verify.

**Key takeaway:** profiles help **select a policy**, but you still need to **verify the active profile, effective level, and sink**. Valid XML syntax does not guarantee the process is running in the right environment.

## 10. Preventing Environment Mixing at Deployment and Log Collector Levels

A complete logging policy must also control where logs go after leaving the JVM.

### 10.1. Choosing Sinks per Environment

Example of a system with separate collectors:

~~~text
dev     -> console local / collector-dev
test    -> isolated test capture
staging -> collector-staging / index-staging
prod    -> collector-prod / index-prod
~~~

Names are illustrative. If the same collector supports multi-tenancy/namespaces, clearly define **tenant, namespace, index, service name, and retention** per environment. Physical infrastructure can be shared, but data partitioning must be explicit and protected by corresponding credentials/permissions.

**Do not rely solely on the `environment=prod` label for access control.** If a staging process has credentials that can write to the production index, a correct staging label will not stop data from going to the wrong place. Restrict permissions at the sink, namespace, token, and network policy levels.

### 10.2. Accurate Labeling

Centralized logs typically require fields such as:

~~~json
{
  "service": "order-service",
  "environment": "staging",
  "severity": "INFO",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "Order accepted"
}
~~~

This is illustrative data, not stdout from the Java program in section 7. The **environment** value should be provided at deployment and controlled via config; do not default to “prod” in code and accidentally label dev logs as production. **trace_id**, if present, must come from the actual tracing context, not be fabricated to make logs look complete.

If the log collector automatically adds Kubernetes namespace or deployment environment labels, avoid having the application inject conflicting values. Choose an authoritative source and cross-check at the log indexing layer.

### 10.3. Keep Secrets Out of Logs and Config Repos

Do not log tokens, passwords, authentication headers, session cookies, raw payment data, or sensitive user data in log messages. This applies to dev and test as well; dev environments may contain real data. Choose a schema-based **redaction** mechanism and test sensitive fields before logs leave the process.

Collector URLs, tenant IDs, and credentials should be managed per deployment policy. Credentials must reside in an appropriate secret store, follow least privilege, and be injected at runtime via approved channels; do not hard-code them into committed **application-prod.yml** files. Do not dump all environment variables or configurations in startup logs because they may contain secrets.

### 10.4. Retention, Rollover, Disk Limits

Dev can just print to console or keep small files; production typically needs proper retention, rotation, and disk space limits. Do not copy production's long retention to test (wasting resources), nor copy dev's short policy to production (risking loss of incident history). In containers, logging to console and letting the platform collect logs is usually easier to manage than each container managing its own files; the final choice depends on infrastructure.

## 11. Testing to Catch Configuration Mixing Before Deployment

To ensure rules do not exist only on paper, test with the **actual built artifact**, using configuration resembling the target environment.

### 11.1. Policy Test Matrix

| Scenario | What to Verify |
| --- | --- |
| Running dev | Dev profile/label; DEBUG only on allowed loggers; logs go to dev sink. |
| Running test | Does not touch production sink; log output matches assertion needs. |
| Running staging | No production credentials; logs have staging label and reach the right index. |
| Running prod | Root/selected loggers at right levels; no debug outside allowlist; correct production sink. |
| Environment unset | Process fails or uses a safe base that blocks misdeployment by design; never silently enables dev DEBUG. |
| Invalid environment | Clear error message, non-zero exit code (if required by policy). |
| Two environment profiles active | Detected and rejected per deployment convention. |
| Env var override present | Effective level matches policy after precedence rules apply. |
| Collector/destination failure | Operational signal emitted and fallback follows policy; never reroutes to another tenant. |
| Shutdown/restart | File/async buffers drain per policy; no logs emitted to another deployment's destination. |

The most important tests are **outcome tests**, not just file content checks: a YAML file might correctly state INFO while the process still runs DEBUG due to another override.

### 11.2. Recommended Assertions

- **Active environment** is defined and within the allowed set.
- **Exactly one environment deployment profile** (if you adopt this convention).
- **Root level** and logger exceptions match expected values.
- **Appender/handler destination** is valid, with no unexpected duplicate console + remote appenders.
- **No secrets** in sample events, even at DEBUG.
- **Environment label and collector namespace** match.
- **Startup errors** are caught early with clear messages; the process does not silently fall back to dangerous defaults.

In Spring Boot tests you can use **@ActiveProfiles("test")** to explicitly select the test profile, but still verify test files and CI runtime overrides. Logging is a JVM-wide resource; if tests programmatically alter the root logger/backend, restore state afterward, and avoid parallel tests mutating the same global logging context.

### 11.3. Manual Testing with the Java 17 Example

With the program in section 7, try:

~~~bash
java EnvironmentLoggingDemo dev
java EnvironmentLoggingDemo test
java EnvironmentLoggingDemo staging
java EnvironmentLoggingDemo prod
java EnvironmentLoggingDemo unknown
~~~

INFO/FINE/WARNING output can be compared for each environment. With **test**, root WARNING should only show WARNING logs; with staging and prod, root INFO should show INFO and WARNING. This is a level-mechanism exercise and does not replace real sink/schema testing.

## 12. Diagnostic Guide When Logs Show “Wrong Environment”

When production suddenly logs too much DEBUG or staging logs appear in the production dashboard, trace across each boundary:

1. **Inspect deployment info:** container/image digest, JVM arguments, active profile, namespace, service name, deployment configuration.
2. **Check loaded config sources:** application files, Logback/Log4j config, JUL config, mounted configs, test configs accidentally packaged.
3. **Look for high-precedence overrides:** environment variables, command-line properties, system properties, central config, runtime code changing logger levels.
4. **Verify actual backend:** is the app using Logback, Log4j2, JUL, or another provider? Are there multiple providers or unexpected bridges?
5. **Check effective logger levels and handlers/appenders:** find where events are being allowed through. Do not read only the root level if a package has its own level.
6. **Check appender/collector and namespace:** distinguish mislabeled logs from logs sent to the wrong sink.
7. **Check timing of changes:** new deploy, restart, profile change, config reload, feature flag, manual log-level override.
8. **Controlled recovery:** restore levels/destinations to approved policy, redeploy if needed; add a regression test for the discovered issue.

Do not fix by relabeling the environment tag in the log collector if the real issue is cross-used credentials or sinks. Fix the configuration selection and access permissions at the source.

### Scenario: “application-prod.yml Is Correct but Logs Are Still DEBUG”

Root-cause workflow:

~~~text
application-prod.yml: root=INFO
       │
       ├── Is prod profile active? -> if not, file was not selected
       │
       ├── Other overrides?        -> LOGGING_LEVEL_ROOT, CLI, external config?
       │
       ├── Child logger DEBUG?     -> package/class exception?
       │
       ├── Correct backend?        -> Logback/Log4j2/JUL/other provider?
       │
       └── Correct log target?     -> filter, appender, collector, stale deployment?
~~~

Only after checking each point should you conclude “the framework ignored the configuration file.”

## 13. Common Design Mistakes

**1. Using dev as the default when environment is missing.** Convenient on a developer laptop, dangerous in deployment: production could log DEBUG and use dev resources. Replace with a safe base or require explicit env declaration.

**2. Copying a production file to dev and changing a few lines.** The copy may retain production endpoints, credentials, file paths, or retention. Use a shared base, small overrides, and test sinks per deployment.

**3. Treating active profile as sufficient proof.** A process can have prod active yet be overridden to root DEBUG by an env var or have a misconfigured collector. Check the effective logging policy.

**4. Mixing levels across YAML, XML, env vars, and code.** Multiple sources controlling the same key make it hard to know which wins. Pick an authoritative source for each config type and document override rules.

**5. Enabling DEBUG/TRACE across all of production indefinitely.** Increases CPU, I/O, storage cost, and data exposure risk. Prefer package-scoped levels, time limits, approval, and log volume monitoring.

**6. Packaging test configs into production artifacts.** Files like **logback-test.xml** may load during tests but should not unexpectedly appear on the production classpath. Check packaging and runtime classpath.

**7. Using log labels instead of access control.** Tagging `environment=staging` on a record does not stop staging credentials from writing to the production tenant. Separate permissions and routing at the infrastructure layer.

**8. Logging all config/env for debugging.** Can expose credentials, tokens, or personal data. Only log permitted diagnostic fields such as profile name, config version, backend name, and levels (filtered)—never secrets.

**9. Testing only in dev.** Environment mixing bugs often surface when CI/CD changes property sources, container working directories, profiles, or collectors. Test staging/prod policies at least via smoke/config validation.

**10. Forgetting runtime config changes.** Some frameworks/backends support dynamic level changes or file reloads. Audit who changed it, when, the revert deadline, and the final value after reload.

## 14. Enforceable Project Control Template

A workflow a development team can adopt:

1. **Define an environment contract:** valid environment names, root level, package exceptions, sink/tenant, format, retention, and sensitive fields forbidden from logging.
2. **Choose a safe base:** without a specific profile, the app does not enable verbose logging or ship to external sinks.
3. **Standardize config sources:** define what is packaged vs. what exceptions are injected at deploy time; avoid uncontrolled multiple sources for the same policy.
4. **Validate at startup:** profile matches environment, no two conflicting deployment profiles, sink/credentials match namespace; fail on critical mismatches.
5. **Measure effective policy:** root level, logger exceptions, appender targets, service/environment labels; do not print secrets.
6. **Test the deployment pipeline:** smoke tests for dev/test/staging/prod plus missing/invalid env, overrides, and config reloads.
7. **Monitor production:** log volume by severity, unexpected DEBUG/TRACE counts, collector routing, and log write errors.
8. **Temporary debug procedure:** specify logger, purpose, scope, auto-revert deadline, and approver per team policy.

Following these steps allows the same codebase to deploy across multiple environments while keeping logging meaningful, reducing confusion during incident investigations, and controlling operational costs.

## 15. Review Questions

1. Why can `application-prod.yml` set INFO yet production still print DEBUG?
2. Why does an active `prod` profile not prove logs are reaching the right production collector?
3. In JUL, why can changing only the logger level while forgetting the ConsoleHandler level cause “lost logs”?
4. Why should you have a safe default or fail startup instead of defaulting to dev when an environment variable is missing?
5. How do you distinguish **a mislabeled log line** from **a log line sent to the wrong sink/tenant**?
6. In Spring Boot, when should you use `application-{profile}.yml` and when do you need `logback-spring.xml`?
7. What test can catch staging accidentally using credentials that write production logs?
8. If you need to enable DEBUG temporarily in production, what conditions must be controlled?

## 16. Key Takeaways

**Avoiding environment configuration mixing** means ensuring every Java process is bound to the right environment and uses the right **effective logging policy** from startup through runtime. The consistent approach is **safe base + small per-environment overrides + sink access restrictions + effective configuration checks + regression tests**. Do not judge by a single YAML/XML file or an environment label alone. Check levels, filters, appenders/handlers, file/collector destinations, sensitive data, and the impact of higher-precedence configuration sources.

### References

- Spring Boot Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Logback Configuration Manual: https://logback.qos.ch/manual/configuration.html
- Java 17 LogManager API: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- Log4j2 Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
