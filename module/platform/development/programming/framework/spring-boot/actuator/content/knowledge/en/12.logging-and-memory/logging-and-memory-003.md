# Distinguishing Temporary Log Level Changes from Persisted Configuration

## 1. Two Different Places Can Both Talk About Log Levels

When investigating an ongoing issue, we can increase log detail directly on the running process. However, when every subsequent deployment needs to use a specific log level, we must change the configuration source used to start the application.

Both operations can cause a logger to show `DEBUG` at a given moment, yet they have different lifecycles:

~~~text
Stored configuration source
    └── read at startup ─────────> logging system state

Actuator loggers
    └── changed at runtime ──────> logging system state
~~~

Spring Boot's `loggers` endpoint controls log levels in the current logging system. It has no operation to write the newly set level back to `application.properties`, YAML, environment variables, or deployment configuration files.

Here, **temporary** means the change does not automatically become configuration for future startups. It does **not** mean the log level will automatically expire after a few minutes.

This lesson uses Spring Boot **3.3.0**, Java **21**, and Logback provided by the default starter to verify behavior. The content focuses on the lifecycle of log levels, restoration operations, and how to make changes reproducible across restarts.

| Criterion | Change via Actuator at runtime | Change stored configuration source |
| --- | --- | --- |
| Direct effect | The application's logging system receives the operation. | Data source used for configuration loading. |
| Restart needed for effect? | Usually no; the new level is applied at runtime. | With standard Boot config, a restart is required to load the new value. |
| Modifies config file automatically? | No. | Yes, if you edit and save the managed file/source yourself. |
| Across a new process/JVM | A level set at runtime does not automatically carry over to a new process. | Reloaded if that source is still provided and active. |
| Auto-expiring? | No built-in rollback timeout from the log-level request. | Depends on lifecycle and config source management process. |
| When to use? | Scoped investigation needing immediate extra visibility. | When logging rules should apply consistently in future runs. |

Reading and changing log levels at runtime is described in [Boot 3.3 Actuator Loggers](https://docs.spring.io/spring-boot/3.3/reference/actuator/loggers.html).

## 2. Distinguishing Directly Set Levels from Effective Levels

A logger can receive a level directly or inherit a level from a parent logger.

Name tree example:

~~~text
ROOT
└── lab
    └── lab.orders                 INFO
        └── lab.orders.CheckoutService   WARN
~~~

In a logger response:

- `configuredLevel` is the level set directly on that logger, if any.
- `effectiveLevel` is the level currently in effect after resolving inheritance.

For the child logger above, both fields are `WARN`. If you clear the child logger's own level, it inherits `INFO` from `lab.orders`. Then `configuredLevel` is absent or `null`, while `effectiveLevel` is `INFO`.

The name `configuredLevel` can be misleading: it does not prove that level is stored in a file. After setting `DEBUG` via Actuator, this field is also `DEBUG`, even if the file still declares `WARN`.

A single `loggers` read shows the current state; it does not fully tell who set that level, when, which file it came from, or whether it will survive the next deployment. Answering origin questions requires cross-checking configuration and change history separately.

Level inheritance rules by logger name are explained in [Logback architecture](https://logback.qos.ch/manual/architecture.html#effectiveLevel). A logger with its own level uses its own level; switching a parent to `DEBUG` does not automatically lower a child logger explicitly set to `WARN`.

## 3. Practice with a WARN Baseline and an Activatable Logger

Create a separate project:

~~~text
log-level-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/
    │   ├── LogLevelLabApplication.java
    │   ├── DemoController.java
    │   └── orders/CheckoutService.java
    └── resources/application.properties
~~~

### 3.1. Build Setup and Initial Log Levels

Contents of `settings.gradle`:

~~~groovy
rootProject.name = 'log-level-lab'
~~~

Contents of `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Contents of `src/main/resources/application.properties`:

~~~properties
spring.application.name=log-level-lab
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,loggers
management.endpoint.loggers.enabled=true
logging.level.root=INFO
logging.level.lab.orders=INFO
logging.level.lab.orders.CheckoutService=WARN
~~~

Here we intentionally set the parent logger to `INFO` and the class logger to `WARN`. Two different levels help distinguish **clearing the explicit level** from **restoring the baseline level**.

Only `health` and `loggers` are exposed over HTTP. In Boot 3.3, an endpoint being enabled does not mean it is exposed over HTTP; by default only `health` is exposed. Write operations are also subject to the application's security rules. See [exposing and securing endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

The lesson's server listens only on loopback and adds no Spring Security. Do not use the open permissions of a practice environment as governance rules for deployed systems.

### 3.2. Source Code

File `src/main/java/lab/LogLevelLabApplication.java`:

~~~java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogLevelLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogLevelLabApplication.class, args);
    }
}
~~~

File `src/main/java/lab/orders/CheckoutService.java`:

~~~java
package lab.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private static final Logger log =
            LoggerFactory.getLogger(CheckoutService.class);

    public void inspect() {
        log.debug("checkout diagnostic: phase=validate");
        log.info("checkout demo invoked");
        log.warn("checkout demo warning");
    }
}
~~~

File `src/main/java/lab/DemoController.java`:

~~~java
package lab;

import java.util.Map;
import lab.orders.CheckoutService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    private final CheckoutService checkoutService;

    public DemoController(CheckoutService checkoutService) {
        this.checkoutService = checkoutService;
    }

    @GetMapping("/demo/checkout")
    public Map<String, String> inspect() {
        checkoutService.inspect();
        return Map.of("status", "inspected");
    }
}
~~~

The `/demo/checkout` path merely triggers three fixed log statements for observation. It does not create orders or process payment data.

The logger name is the full class name `lab.orders.CheckoutService`. Therefore, the configuration key and the name in the Actuator URL must match this name, including case.

### 3.3. Running the Project

With Gradle 8.5 installed, generate the wrapper once in the project directory:

~~~powershell
gradle wrapper --gradle-version 8.5
~~~

Run on Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

On Linux/macOS use `./gradlew bootRun`. The first run needs to download Gradle and dependencies. The Java files require the Spring classpath; this is not a single-file program to run with bare `javac`.

Open another PowerShell window to call:

~~~powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/demo/checkout'
~~~

The response has `status=inspected`. With this lesson's baseline configuration, among the three log statements of `CheckoutService`, only the following is written:

~~~text
checkout demo warning
~~~

This is the message body; the actual console line also contains timestamp, log level, logger name, and other formatting info. Do not confuse Spring startup logs with the test's three log statements.

## 4. Changing Levels at Runtime, Re-reading, and Restoring Proper State

The PowerShell snippets below operate on **a single local practice application**, assuming no one else is concurrently changing log levels. Run them sequentially in the same PowerShell session.

### 4.1. Capture State Before Making Changes

~~~powershell
$base = 'http://127.0.0.1:8080'
$loggerName = 'lab.orders.CheckoutService'
$loggerUri = "$base/actuator/loggers/$loggerName"

$before = Invoke-RestMethod -Uri $loggerUri
$before | ConvertTo-Json
~~~

Initial result:

~~~json
{
  "configuredLevel": "WARN",
  "effectiveLevel": "WARN"
}
~~~

Save `configuredLevel` before changing, not just `effectiveLevel`. If a logger originally inherited `INFO`, restoring by hardcoding `INFO` creates a new explicit level and alters the inheritance relationship.

The scope of the captured state is also tied to the exact instance/process queried. If going through a load balancer, you must have a way to ensure read and write requests reach the same instance.

### 4.2. Set DEBUG and Verify the Effect

~~~powershell
$debugRequest = @{
    Method = 'Post'
    Uri = $loggerUri
    ContentType = 'application/json'
    Body = '{"configuredLevel":"DEBUG"}'
}
Invoke-RestMethod @debugRequest
Invoke-RestMethod -Uri $loggerUri | ConvertTo-Json
Invoke-RestMethod -Uri "$base/demo/checkout"
~~~

The write operation uses `POST`, with a JSON payload containing `configuredLevel`. On HTTP success, Boot normally returns **204 No Content**; there is no JSON document required in the POST response. The subsequent GET request verifies the state:

~~~json
{
  "configuredLevel": "DEBUG",
  "effectiveLevel": "DEBUG"
}
~~~

This `/demo/checkout` trigger shows all three messages:

~~~text
checkout diagnostic: phase=validate
checkout demo invoked
checkout demo warning
~~~

It is not only the DEBUG statement that gets written. In this Logback example, `DEBUG` allows statements at DEBUG and higher levels; TRACE is still not enabled.

`INFO` on ROOT does not create a "global ceiling" blocking any child logger from explicitly setting DEBUG. However, appender filters or the log collection system can still drop events at another stage.

The API for setting and reading log levels is described at [Boot 3.3 Loggers REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

### 4.3. Clearing the Explicit Level: Why Did It Become INFO?

Per the Boot 3.3 API, send an empty JSON object `{}` to clear the explicitly set level:

~~~powershell
$clearRequest = @{
    Method = 'Post'
    Uri = $loggerUri
    ContentType = 'application/json'
    Body = '{}'
}
Invoke-RestMethod @clearRequest
Invoke-RestMethod -Uri $loggerUri | ConvertTo-Json
Invoke-RestMethod -Uri "$base/demo/checkout"
~~~

The child logger no longer has a direct level and inherits from its parent `lab.orders=INFO`. The response has `effectiveLevel=INFO`; `configuredLevel` has no value and may be omitted from JSON. A common representation:

~~~json
{
  "effectiveLevel": "INFO"
}
~~~

The next trigger produces only two messages:

~~~text
checkout demo invoked
checkout demo warning
~~~

**Clearing the explicit level does not mean re-reading `logging.level.lab.orders.CheckoutService=WARN` from the file.** Nor does this operation set the level to `OFF`, delete the logger, or erase previously written log lines.

If the goal is to return to the example's `WARN`, you must restore that level or reload configuration through the appropriate process.

### 4.4. Restoring the Captured Value

~~~powershell
$restoreBody = if ($null -eq $before.configuredLevel) {
    '{}'
} else {
    @{ configuredLevel = $before.configuredLevel } | ConvertTo-Json -Compress
}

$restoreRequest = @{
    Method = 'Post'
    Uri = $loggerUri
    ContentType = 'application/json'
    Body = $restoreBody
}
Invoke-RestMethod @restoreRequest
$afterRestore = Invoke-RestMethod -Uri $loggerUri
$afterRestore | ConvertTo-Json
~~~

With the example's `$before`, the restore request sets `WARN`; reading back yields WARN/WARN and the probe writes only the warning statement.

If the previous state had no explicit level, the snippet sends `{}` to restore the inheritance mechanism. It does not hardcode the captured effective level. If the parent logger also changed during the investigation, the effective level may differ even though the child logger's explicit level was properly restored.

Do not use the string `"null"` instead of clearing the explicit level: that is a character string, not a null value or an empty JSON object.

### 4.5. Tracking the Full Sequence of States

These states were verified with Boot 3.3.0's `LoggersEndpoint` and Logback:

| Action | Child logger's own level | Effective level | Example's three log statements emitted |
| --- | --- | --- | --- |
| Startup from original file | WARN | WARN | WARN |
| Change parent logger alone to DEBUG | WARN | WARN | WARN |
| Keep parent INFO, set child DEBUG | DEBUG | DEBUG | DEBUG, INFO, WARN |
| Clear child's own level | None | INFO | INFO, WARN |
| Restore captured own level | WARN | WARN | WARN |
| Set DEBUG then start a new JVM, still using original file | WARN | WARN | WARN |

The table assumes no custom filters/appenders altering output and no other overriding configuration source.

### 4.6. Rolling Back in a Short Diagnostic Session

In a local project with only one operator, the restore step can be placed in `finally`. This snippet reuses `$base`, `$loggerUri`, and `$debugRequest` declared above:

~~~powershell
$original = Invoke-RestMethod -Uri $loggerUri
$originalBody = if ($null -eq $original.configuredLevel) {
    '{}'
} else {
    @{ configuredLevel = $original.configuredLevel } | ConvertTo-Json -Compress
}

try {
    Invoke-RestMethod @debugRequest
    Invoke-RestMethod -Uri "$base/demo/checkout"
} finally {
    $rollbackRequest = @{
        Method = 'Post'
        Uri = $loggerUri
        ContentType = 'application/json'
        Body = $originalBody
    }
    Invoke-RestMethod @rollbackRequest
    Invoke-RestMethod -Uri $loggerUri | ConvertTo-Json
}
~~~

This is rollback after the work block ends, not an auto-expiration feature of Actuator. If PowerShell is forcibly closed, the machine goes down, or the control process is stopped, `finally` should not be treated as a guaranteed rollback commitment.

In a shared system, coordinate change permissions and check for newer changes before restoring; do not overwrite a level that someone else just intentionally set.

## 5. Proving Runtime Changes Do Not Become Startup Configuration

Run the experiment on the local project:

1. Keep the class logger config line as `WARN`.
2. Use Actuator to set the class logger to `DEBUG`.
3. Verify GET returns DEBUG/DEBUG.
4. Stop the application and run it again with the same configuration source.
5. Re-read the logger: the result returns to WARN/WARN.

What is lost is the level change in the old process. Previously written DEBUG log lines are not deleted from log storage because of this.

Similarly, changing a level via `loggers` does not automatically change the `logging.level...` value in Spring `Environment`. Thus you can simultaneously observe:

~~~text
Configuration source / Environment: WARN
Runtime logger state:               DEBUG
~~~

These two pieces of information answer two different questions. To know which level the logger is currently using, read `loggers`; to investigate which source a configuration value came from, inspect configuration sources and the appropriate diagnostic tools.

A process can run for many days. Without active rollback or another configuration reload event, a "temporary" level can persist for that entire duration. The endpoint does not automatically attach a 5-minute or 15-minute expiration to `configuredLevel` requests.

## 6. Making Changes Persistent and Reproducible

### 6.1. Edit the Right Configuration Source

If the intention is to use DEBUG for future runs of the practice environment, update the corresponding line in `application.properties`:

~~~properties
logging.level.lab.orders.CheckoutService=DEBUG
~~~

Save the file, stop, and restart. If this configuration is packaged inside a JAR, the old JAR does not change automatically when editing the source file; a new build must be created for deployment.

Configuration methods supported by Boot include properties/YAML files, profile-specific configuration, environment variables, and startup arguments. External sources outside the application can override packaged configuration. See [externalized configuration in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Development-only configuration can be kept in `application-dev.properties` with the proper profile activated. A saved file that is not loaded has no effect.

### 6.2. How Long Do Startup Arguments Last?

Example running with the wrapper on Windows:

~~~powershell
.\gradlew.bat bootRun --args="--logging.level.lab.orders.CheckoutService=DEBUG"
~~~

This argument configures the log level for that startup and can override the WARN line in the file. It does not edit the file.

If subsequent startups need the same argument, it must be saved in run configurations, the service manager, or deployment manifests. Typing it once in a terminal does not cause future deployments to inherit that command.

Likewise, an environment variable is only "persistent" according to the lifecycle of where the variable is stored and re-injected. Setting a variable only in one shell session does not mean it has been saved in deployment configuration.

Specifically for logger names that are classes with mixed case like `CheckoutService`, do not assume a regular `LOGGING_LEVEL_...` variable will preserve the class casing: environment variable binding converts names to lowercase. Use configuration files, startup arguments, or `SPRING_APPLICATION_JSON` following Boot's rules when configuring a specific class. See [log level configuration and environment variables](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.log-levels).

### 6.3. Saved Does Not Mean Currently Active

With standard Boot, merely editing a file does not guarantee a running process reloads the file automatically. "Saving" and "applying to the process" are two separate things to verify.

If the system has a configuration reloader, Logback scanning, or a centralized config controller, application behavior is governed by that mechanism. It may overwrite a level just set via Actuator. Do not assume Boot and `loggers` provide built-in two-way synchronization.

Native configurations like `logback-spring.xml` are also sources that can be managed long-term. Understand where log levels are being set, and avoid editing multiple sources without knowing their precedence. `loggers` does not write changes back into those files.

A post-deployment check should confirm:

- The changed configuration source has been saved in the managed location.
- The new process actually picked up the right source/profile/arguments.
- `configuredLevel` and `effectiveLevel` after startup match the target.
- A test request produces the needed logs.

Do not use a single successful POST as a substitute for all four pieces of evidence.

## 7. Common Operational Mistakes

### "DEBUG appears in configuredLevel, so it must have been persisted"

False. This field represents the level currently assigned directly. Setting it via Actuator changes it as well, even while configuration sources remain untouched.

### "Clearing the explicit level will restore the exact initial configuration"

False if the logger originally had its own explicit level. In the example, clearing the explicit level yields inherited INFO; restoring the captured level yields WARN. With multiple loggers, save the individual state of each modified target.

### "Changing ROOT or a parent logger makes everywhere emit DEBUG"

Child loggers with their own levels can keep different levels. Appender filters, log shipping configuration, and collectors can also drop events. Use the narrowest-scoped logger that answers the investigation question.

Boot's `--debug` flag also does not mean setting all application code to DEBUG; it enables extra detail for a set of Boot-selected loggers. To control a specific class, set the exact logger name. See [debug mode in logging docs](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.console-output).

### "One POST updates the entire cluster"

Actuator does not automatically broadcast changes to other instances. After container replacement, restart, or scaling out instances, new processes take their startup configuration.

If multiple instances currently have different levels, GET requests through a load balancer can return different results. Know exactly which instance was modified and re-read against the same target; cluster-wide configuration must be rolled out via the proper deployment mechanism.

### "A logger group can be restored using a single captured level"

A logger group can contain many members with different explicit levels. Setting a group level can affect many loggers; re-assigning one shared level cannot recreate every previous state. Do not generalize this lesson's single-logger experiment to group or ROOT changes while ignoring scope and rollback mechanics.

### "Seeing no POST response body means an error"

Success can be 204 with no response body. Check the HTTP status and GET to confirm. If you encounter 401/403, check authentication, authorization, and CSRF policy for write operations; do not assume you should disable all security.

### "Temporary levels do not need tracking because they will disappear soon"

There is no built-in rollback timeout. When raising DEBUG/TRACE for diagnosis, identify the logger, instance, purpose, owner, and termination condition. High verbosity can increase log volume or expose data that application code put into log statements.

This lesson's example logs only fixed messages to avoid mixing level configuration with sensitive data handling.

## 8. Self-Verification Exercises

**Exercise 1 — Clearing differs from restoring.** Start from the original config, capture state, set DEBUG, then send `{}`. Afterward, restore the captured level.

Compare: WARN/WARN → DEBUG/DEBUG → no explicit level/INFO → WARN/WARN. Explain why step three does not return to WARN.

**Exercise 2 — Parent–child relationship.** While the child logger is still set to WARN, change parent logger `lab.orders` to DEBUG and trigger the probe.

Compare: the child logger remains WARN/WARN. After the test, return the parent logger to INFO; do not revert only the child logger and forget the parent logger.

**Exercise 3 — Across process boundaries.** Set the child to DEBUG via Actuator, verify, then stop and restart without editing the configuration source.

Compare: the new JVM reads WARN from the original file again. This result does not say that DEBUG lines already saved in log storage were deleted.

**Exercise 4 — Persisted configuration.** Edit the class logger line to DEBUG in the configuration source, save, and restart. Then temporarily set WARN via Actuator and restart once more.

Compare: when the DEBUG source is reloaded and not overridden by another source, the new process returns to DEBUG. The runtime WARN level did not permanently overwrite the file.

**Exercise 5 — Initial state is inherited.** In the practice project, remove just the class logger configuration line, keep the parent INFO, and restart. Capture state, set DEBUG, and restore from the captured state.

Compare: initial own level is absent, effective level is INFO; restore with `{}` to return to inheritance, rather than hardcoding INFO on the class.

After the tests, restore the practice environment's desired configuration and log levels. What must be distinguished are: **current level**, **inherited level**, **stored configuration source**, and **the mechanism that reloads that source**.
