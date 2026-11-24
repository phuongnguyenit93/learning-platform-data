# Changing or Restoring Log Levels for Loggers and Logger Groups at Runtime

## 1. Why Change Log Levels at Runtime?

A processing branch is failing, yet `INFO` logs do not show enough of what is happening. If you only edit a configuration file and redeploy, you can lose runtime state or miss the window you need to observe. Spring Boot Actuator's `loggers` endpoint lets you read and change log levels in a running process.

An observation session should have a complete lifecycle:

~~~text
Read current state
    → save state to restore
    → change the smallest sufficient scope
    → trigger or wait for the behavior to observe
    → re-read effective level and new logs
    → restore
    → confirm state after restore
~~~

What matters is not just sending a POST with `DEBUG`. You need to know which logger the POST affects, how child loggers inherit from it, and which restore operation actually returns the original configuration.

This lesson uses Spring Boot 3.3.x with the default Logback from the starter. The sample requests apply to the practice application on loopback. When working with another system, use the proper management URL, instance, and granted operational permissions. [Spring Boot 3.3 — managing loggers](https://docs.spring.io/spring-boot/3.3/reference/actuator/loggers.html).

## 2. Three Concepts That Determine How Changes and Restores Work

### 2.1. Loggers and the Name Tree

A logger is a named object used to emit logs. Its name usually follows a class or package name, though it can also be chosen by the developer.

Example:

~~~text
ROOT
└── demo
    ├── demo.alpha
    │   ├── demo.alpha.Worker
    │   └── demo.alpha.Fixed
    └── demo.beta
        └── demo.beta.Worker
~~~

In Logback, inheritance relationships are determined by dot-separated names. `demo.alpha.Worker` is a descendant of `demo.alpha`. Logger names are case-sensitive; an abbreviated name shown on the console is not necessarily the full name to send to the endpoint.

### 2.2. configuredLevel and effectiveLevel

A logger response can look like:

~~~json
{
  "configuredLevel": null,
  "effectiveLevel": "INFO"
}
~~~

- `configuredLevel`: the level assigned directly to the queried logger itself.
- `effectiveLevel`: the effective level after inheritance is resolved.

A `null` value, or the `configuredLevel` field being omitted when serialization drops null fields, means the logger has no directly assigned level. It can still emit logs by inheriting from a parent logger.

If `demo.alpha=INFO` and `demo.alpha.Worker` has no explicit level of its own, Worker has an effective level of INFO. Directly setting Worker to DEBUG enables Worker to emit additional DEBUG logs. Clearing Worker's direct level makes it inherit again—it does not "disable the logger".

A child logger that already has its own level can keep that level when the parent logger changes. For example, `demo.alpha.Fixed=WARN` remains WARN even when `demo.alpha` is switched to DEBUG.

With Logback, the ROOT level is not a global ceiling forcing every child logger to stay quiet: a child logger with its own DEBUG level can still emit DEBUG when ROOT is INFO. Appenders or filters can still affect whether messages are output.

[Logback — logger tree, level inheritance, and log selection rules](https://logback.qos.ch/manual/architecture.html).

### 2.3. A Logger Group Is a Set of Logger Names, Not a Parent Logger

Spring Boot lets you declare:

~~~properties
logging.group.diagnostics=demo.alpha,demo.beta
~~~

The `diagnostics` group bundles two logger names so they can be operated on together. It does not insert a parent node named `diagnostics` into the inheritance tree.

When setting a group's level to DEBUG, Spring Boot applies that level to the member loggers. Child loggers without their own level can receive DEBUG via inheritance from a member. Child loggers that already have their own level do not have their level automatically erased.

A logger or branch can belong to multiple groups. Changing overlapping groups affects some of the same loggers; there is no "group priority level" independent of the actual levels on those loggers.

Group names must be declared and verified beforehand. Do not POST an arbitrary name and assume you have created a group with the desired members. Choose clear group names and avoid colliding with logger names so operators do not confuse the target.

[Spring Boot 3.3 — declaring logging groups](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html).

## 3. HTTP Contract Used

With the default management path:

| Purpose | Request | Main result |
| --- | --- | --- |
| Read loggers, groups, and supported levels | `GET /actuator/loggers` | JSON containing `levels`, `loggers`, `groups` |
| Read one logger | `GET /actuator/loggers/{loggerName}` | Directly assigned level and effective level |
| Read one group | `GET /actuator/loggers/{groupName}` | Members and the level set for the group, if any |
| Set level for a logger or group | `POST /actuator/loggers/{name}` with `{"configuredLevel":"DEBUG"}` | Write operation; normally returns HTTP 204 |
| Clear directly assigned level | Same POST, body `{}` | Removes the assigned level; does not reload initial config |

Use `Content-Type: application/json` for POST requests. Body `{}` is an empty JSON object; it differs from a request with no body, a JSON string `"{}"`, or a body with the wrong field name.

HTTP 204 has no JSON to read. After writing, use GET to confirm the level; do not interpret an empty 204 response body as a failed request.

The `levels` list reflects the levels supported by the system. Do not arbitrarily send a string like `VERBOSE` or `ALL` because you saw that name in another tool. The examples below use `DEBUG`, `INFO`, and `WARN`.

A group has no single `effectiveLevel` field that reliably represents every member. Read `members` and inspect the relevant loggers. [Spring Boot 3.3 — loggers REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

## 4. Practice Project with Observable Output

Use Java 21, Gradle 8.5, and Spring Boot 3.3.0 to reproduce the example. The versions are pinned for this lesson, not a requirement to change the version of an operating project.

### 4.1. Build and Configuration Files

`settings.gradle`:

~~~groovy
rootProject.name = 'runtime-loggers-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.address=127.0.0.1
management.endpoint.loggers.enabled=true
management.endpoints.web.exposure.include=health,loggers
logging.level.root=INFO
logging.group.diagnostics=demo.alpha,demo.beta
logging.level.demo.alpha=INFO
logging.level.demo.beta=WARN
logging.level.demo.alpha.Fixed=WARN
~~~

Only `health` and `loggers` are exposed. The practice application does not add Spring Security and listens only on loopback. This configuration is not a template for exposing management endpoints to the Internet.

The initial levels were chosen intentionally:

- `demo.alpha` has its own level INFO.
- `demo.beta` has its own level WARN.
- `demo.alpha.Fixed` has its own level WARN.
- The two Worker loggers have no own level, so they inherit.
- The `diagnostics` group has declared members but has not yet been given a shared level.

### 4.2. Complete Java Program

Create `src/main/java/demo/RuntimeLoggersApplication.java`:

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RuntimeLoggersApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeLoggersApplication.class, args);
    }

    @RestController
    public static class LogProbeController {

        private static final Logger ALPHA =
            LoggerFactory.getLogger("demo.alpha.Worker");
        private static final Logger BETA =
            LoggerFactory.getLogger("demo.beta.Worker");
        private static final Logger FIXED =
            LoggerFactory.getLogger("demo.alpha.Fixed");

        @GetMapping(value = "/demo/log", produces = "text/plain")
        public String emit() {
            ALPHA.debug("ALPHA_DEBUG");
            ALPHA.info("ALPHA_INFO");
            ALPHA.warn("ALPHA_WARN");
            BETA.debug("BETA_DEBUG");
            BETA.info("BETA_INFO");
            BETA.warn("BETA_WARN");
            FIXED.debug("FIXED_DEBUG");
            FIXED.info("FIXED_INFO");
            FIXED.warn("FIXED_WARN");
            return "emitted\n";
        }
    }
}
~~~

Logger names are written explicitly for easy comparison. They are not three separate Java classes. Each GET `/demo/log` calls all DEBUG/INFO/WARN statements; the logging system decides which events are emitted.

The response of the probe API is always:

~~~text
emitted
~~~

This response only confirms the handler ran; it does not prove that every DEBUG message was emitted.

### 4.3. Build and Run

If the project does not yet have a wrapper, use Gradle 8.5 to generate it:

~~~shell
gradle wrapper --gradle-version 8.5
~~~

Then in the project directory, in PowerShell:

~~~powershell
java -version
.\gradlew.bat bootJar
java -jar build/libs/runtime-loggers-lab-1.0.0.jar
~~~

Use JDK 21 for the Java command. The first build needs access to the plugin repository and Maven Central. This is a Spring Boot program requiring the dependency classpath; do not run `javac RuntimeLoggersApplication.java` standalone.

Keep the application running in the first terminal. Requests in the following sections are sent from a second terminal to this same practice application.

## 5. Changing and Then Restoring a Single Logger

### 5.1. Two PowerShell Functions to Read and Write with Status Checking

In the request terminal, declare:

~~~powershell
$loggerBase = 'http://127.0.0.1:8080/actuator/loggers'
$probeUri = 'http://127.0.0.1:8080/demo/log'

function Read-LogTarget {
    param([string]$Name)

    $encodedName = [Uri]::EscapeDataString($Name)
    Invoke-RestMethod -Method Get -Uri "$loggerBase/$encodedName" -ErrorAction Stop
}

function Write-LogTarget {
    param(
        [string]$Name,
        [AllowNull()][string]$Level
    )

    $body = if ([string]::IsNullOrEmpty($Level)) {
        '{}'
    } else {
        @{ configuredLevel = $Level } | ConvertTo-Json -Compress
    }

    $encodedName = [Uri]::EscapeDataString($Name)
    $request = @{
        Method = 'Post'
        Uri = "$loggerBase/$encodedName"
        ContentType = 'application/json'
        Body = $body
        UseBasicParsing = $true
        ErrorAction = 'Stop'
    }
    $response = Invoke-WebRequest @request

    if ($response.StatusCode -ne 204) {
        throw "Unexpected HTTP status: $($response.StatusCode)"
    }
}
~~~

In the write function, null/empty string is converted into `{}`. Any other level is converted into a JSON object with the `configuredLevel` key. Commands share the same `$loggerBase` variable in this terminal.

Overview read:

~~~powershell
$catalog = Invoke-RestMethod -Uri $loggerBase
$catalog.levels
$catalog.groups.diagnostics
~~~

Confirm the group contains `demo.alpha` and `demo.beta` before using it.

### 5.2. Record the Initial State

~~~powershell
$loggerName = 'demo.alpha.Worker'
$beforeLogger = Read-LogTarget -Name $loggerName
$beforeLogger

Invoke-RestMethod -Uri $probeUri
~~~

Worker has configuredLevel null and effectiveLevel INFO. The message parts of the logs from the probe endpoint, in order, are:

~~~text
ALPHA_INFO
ALPHA_WARN
BETA_WARN
FIXED_WARN
~~~

Do not include timestamps, PID, or thread names in fixed expectations: those fields vary per run. If other logs come from the framework, compare only the messages starting with `ALPHA_`, `BETA_`, or `FIXED_`.

### 5.3. Set Worker Directly to DEBUG

~~~powershell
Write-LogTarget -Name $loggerName -Level 'DEBUG'
Read-LogTarget -Name $loggerName
Invoke-RestMethod -Uri $probeUri
~~~

GET on the logger should show configuredLevel DEBUG and effectiveLevel DEBUG. The new probe call emits:

~~~text
ALPHA_DEBUG
ALPHA_INFO
ALPHA_WARN
BETA_WARN
FIXED_WARN
~~~

This change applies only to Worker, not turning on DEBUG for every logger in the application. `demo.alpha` still keeps INFO; the beta and Fixed loggers were not changed by this operation.

Older logs not containing `ALPHA_DEBUG` remain normal. Changing the current level does not regenerate events that were dropped earlier.

### 5.4. Restore Using the Saved Directly Assigned Level

~~~powershell
Write-LogTarget -Name $loggerName -Level $beforeLogger.configuredLevel
Read-LogTarget -Name $loggerName
Invoke-RestMethod -Uri $probeUri
~~~

Because the initial configuredLevel was null, the function sends `{}`. Worker no longer has an explicit level and returns to inheriting INFO in the current configuration. The probe messages return to the original four lines.

Do not write `INFO` just because you previously saw effectiveLevel INFO. Doing so creates a new explicit level and prevents Worker from following future parent logger level changes.

Rule for restoring a regular logger:

| Saved state | Restore request |
| --- | --- |
| configuredLevel null, effectiveLevel INFO | Send `{}` to return to inheritance |
| configuredLevel WARN | Send `{"configuredLevel":"WARN"}` |
| configuredLevel DEBUG | Send `{"configuredLevel":"DEBUG"}` |

If the parent logger changed during observation, restoring configuredLevel null may yield a different effectiveLevel than before. In that case, distinguish "restored the inheritance policy" from "the entire logger tree returned to its prior state".

ROOT is the root of the tree and has no parent logger to inherit from like Worker. If there is a reason to change ROOT, save and restore ROOT's explicit level; do not use the level-clearing action of a regular logger as a generic template for ROOT.

## 6. Changing a Group's Level and Seeing the Exact Scope of Impact

Perform this section after Worker has been restored in section 5. Keep the same application process running to observe runtime changes.

### 6.1. Save the Group and Each Member Before Writing

~~~powershell
$groupName = 'diagnostics'
$beforeGroup = Read-LogTarget -Name $groupName

$beforeMembers = @(
    foreach ($member in $beforeGroup.members) {
        $state = Read-LogTarget -Name $member
        [pscustomobject]@{
            name = $member
            configuredLevel = $state.configuredLevel
            effectiveLevel = $state.effectiveLevel
        }
    }
)

$beforeGroup
$beforeMembers | Format-Table name, configuredLevel, effectiveLevel
~~~

In the example, the record before changes is:

| Target | configuredLevel | effectiveLevel |
| --- | --- | --- |
| group diagnostics | Not set | No single shared effectiveLevel in the group response |
| demo.alpha | INFO | INFO |
| demo.beta | WARN | WARN |

`members` is also part of the record. Do not save only the group level: a group having no shared level does not mean every member has no explicit level.

### 6.2. Set the Group to DEBUG

~~~powershell
Write-LogTarget -Name $groupName -Level 'DEBUG'

Read-LogTarget -Name $groupName
Read-LogTarget -Name 'demo.alpha'
Read-LogTarget -Name 'demo.beta'
Read-LogTarget -Name 'demo.alpha.Worker'
Read-LogTarget -Name 'demo.alpha.Fixed'

Invoke-RestMethod -Uri $probeUri
~~~

Results that must be explainable:

- Both members `demo.alpha` and `demo.beta` are directly assigned DEBUG.
- Both branch Workers have no own level, so they inherit DEBUG.
- `demo.alpha.Fixed` still keeps WARN because it has its own explicit level.
- ROOT can still be INFO; that is not a contradiction with DEBUG on child branches.

Probe messages:

~~~text
ALPHA_DEBUG
ALPHA_INFO
ALPHA_WARN
BETA_DEBUG
BETA_INFO
BETA_WARN
FIXED_WARN
~~~

A group level does not erase explicit levels of loggers deeper in a branch. To know whether a specific class or logger name is actually at DEBUG, read that logger itself and check new logs.

### 6.3. A Group's Displayed Level Does Not Guarantee Members Always Stay Uniform

You can experiment further in the same practice session:

~~~powershell
Write-LogTarget -Name 'demo.beta' -Level 'ERROR'

Read-LogTarget -Name $groupName
Read-LogTarget -Name 'demo.beta'
Read-LogTarget -Name 'demo.beta.Worker'

Invoke-RestMethod -Uri $probeUri
~~~

In this example's Spring Boot 3.3, the level set on the group is still reported as DEBUG, yet `demo.beta` has been changed individually to ERROR. There is no mechanism locking every member permanently to the last level set through the group.

Because the beta probe only calls DEBUG, INFO, and WARN, no beta messages are emitted this time:

~~~text
ALPHA_DEBUG
ALPHA_INFO
ALPHA_WARN
FIXED_WARN
~~~

This is also why a group value that looks right is not enough to conclude that the observed component's logger has the desired level.

## 7. Clearing a Group's Temporary Level Differs from Restoring the Initial Record

### 7.1. What Happens When Sending {} to a Group?

Continue in the same session:

~~~powershell
Write-LogTarget -Name $groupName -Level $null

Read-LogTarget -Name 'demo.alpha'
Read-LogTarget -Name 'demo.beta'
Invoke-RestMethod -Uri $probeUri
~~~

This command clears the assigned level on the group's members. It does not restore INFO and WARN respectively from the record you saved.

In this lesson's logger tree:

| Member | Before group change | After clearing group level |
| --- | --- | --- |
| demo.alpha | configured INFO, effective INFO | configured null, inherits INFO |
| demo.beta | configured WARN, effective WARN | configured null, inherits INFO |

Even though alpha has the same effectiveLevel as at the start, its configuredLevel has changed. For beta, both the configuration meaning and the effective level changed.

The probe messages now are:

~~~text
ALPHA_INFO
ALPHA_WARN
BETA_INFO
BETA_WARN
FIXED_WARN
~~~

`BETA_INFO` appears additionally compared to the initial state. That is concrete proof that "clearing DEBUG on the group" is not equal to "restoring the exact state before enabling DEBUG".

The endpoint does not maintain a stack of previous levels so that each `{}` reverts one prior configuration change. The pre-change record is held by the operator or the tool managing the observation session.

### 7.2. Restoring the Group and Each Member Properly

To restore the record from section 6.1, the order is:

1. Restore the group's level, to return the reported group state as well.
2. Restore the `configuredLevel` of each member, to preserve pre-existing individual overrides.
3. Re-read the group, members, and relevant child loggers.

Do not reverse the first two write operations: writing the group last would re-apply a shared level over the members you just restored.

With the data saved in the terminal, you can run:

~~~powershell
Write-LogTarget -Name $groupName -Level $beforeGroup.configuredLevel

foreach ($saved in $beforeMembers) {
    Write-LogTarget -Name $saved.name -Level $saved.configuredLevel
}

Read-LogTarget -Name $groupName
foreach ($saved in $beforeMembers) {
    Read-LogTarget -Name $saved.name
}

Read-LogTarget -Name 'demo.alpha.Worker'
Read-LogTarget -Name 'demo.beta.Worker'
Read-LogTarget -Name 'demo.alpha.Fixed'
Invoke-RestMethod -Uri $probeUri
~~~

In the example, the group returns to having no shared level, `demo.alpha` returns to its own level INFO, `demo.beta` returns to its own level WARN, and Fixed stays WARN. The Workers continue inheriting from their respective branches.

The messages are once again:

~~~text
ALPHA_INFO
ALPHA_WARN
BETA_WARN
FIXED_WARN
~~~

If before observation the group had level INFO while one member had been individually set to WARN, you must likewise save both layers: restore the group to INFO first, then restore that member's WARN override.

The results in sections 6–7 are the observed behavior from this project's Spring Boot 3.3/Logback configuration. When changing the logging backend or management mechanism, re-verify group operations and inheritance instead of guessing from the group name.

## 8. Organizing a Change Session with Explicit Restoration

### 8.1. Using finally and Reporting Restore Failures per Target

The steps above explain each individual action. When combining them into a test session, use `try/finally` so restoration is still attempted if the observation part throws an exception.

The snippet below reuses the `Read-LogTarget` and `Write-LogTarget` functions declared earlier. Run it after completing the restoration in section 7. It assumes you are the only one changing these targets during the practice session.

~~~powershell
$sessionGroupName = 'diagnostics'
$sessionGroupBefore = Read-LogTarget -Name $sessionGroupName

$sessionMembersBefore = @(
    foreach ($member in $sessionGroupBefore.members) {
        $state = Read-LogTarget -Name $member
        [pscustomobject]@{
            name = $member
            configuredLevel = $state.configuredLevel
            effectiveLevel = $state.effectiveLevel
        }
    }
)

try {
    Write-LogTarget -Name $sessionGroupName -Level 'DEBUG'
    Read-LogTarget -Name $sessionGroupName
    Read-LogTarget -Name 'demo.alpha.Worker'
    Read-LogTarget -Name 'demo.beta.Worker'
    Invoke-RestMethod -Uri $probeUri -ErrorAction Stop
}
finally {
    $restoreErrors = [System.Collections.Generic.List[string]]::new()

    try {
        Write-LogTarget -Name $sessionGroupName -Level $sessionGroupBefore.configuredLevel
    }
    catch {
        $restoreErrors.Add("group $sessionGroupName : $($_.Exception.Message)")
    }

    foreach ($saved in $sessionMembersBefore) {
        try {
            Write-LogTarget -Name $saved.name -Level $saved.configuredLevel
        }
        catch {
            $restoreErrors.Add("logger $($saved.name) : $($_.Exception.Message)")
        }
    }

    if ($restoreErrors.Count -gt 0) {
        throw "Restore incomplete: $($restoreErrors -join '; ')"
    }
}
~~~

Failing to restore one target does not skip the remaining targets in `finally`. Even so, separate POST requests are not an atomic transaction: if one request fails, the state may only be partially restored.

Do not report "restored" solely because the `finally` block ran. Re-read after writing:

~~~powershell
$groupAfter = Read-LogTarget -Name $sessionGroupName

if ([string]$groupAfter.configuredLevel -ne [string]$sessionGroupBefore.configuredLevel) {
    throw 'Group configuredLevel was not restored'
}

$expectedMembers = @($sessionGroupBefore.members | Sort-Object) -join '|'
$actualMembers = @($groupAfter.members | Sort-Object) -join '|'

if ($actualMembers -ne $expectedMembers) {
    throw 'Group membership changed during the session'
}

foreach ($saved in $sessionMembersBefore) {
    $actual = Read-LogTarget -Name $saved.name

    if ([string]$actual.configuredLevel -ne [string]$saved.configuredLevel) {
        throw "Configured level mismatch: $($saved.name)"
    }

    if ([string]$actual.effectiveLevel -ne [string]$saved.effectiveLevel) {
        throw "Effective level mismatch: $($saved.name)"
    }
}

Read-LogTarget -Name 'demo.alpha.Fixed'
Invoke-RestMethod -Uri $probeUri -ErrorAction Stop
~~~

The comparison casts `configuredLevel` to string so an absent field and null are treated as the same unset state in this lesson's responses. Comparing `effectiveLevel` helps detect effects from a parent logger if an unexpected change occurred.

A forcibly closed session, killed PowerShell process, or lost connection is not guaranteed to finish `finally`. A person or tool must still follow up to verify and restore, rather than blindly trusting cleanup code to always run.

### 8.2. Records Must Be Tied to the Right Process

In multi-instance operations, log level is state belonging to the process that receives the request. A POST through a load balancer may change instance A, while the next GET reads instance B.

Save the record alongside the application identifier, instance, timestamp, logger/group, and observation purpose. Confirm that read/write requests reach the intended target. A record captured before an application restart must not be blindly applied to the new process.

If another person or tool is also changing levels, the initial record may no longer be the state to return to. Before restoring, check whether live state still matches your session's change or has been superseded by another change. When there is a conflict, stop overwriting from the old record and coordinate with the owner of the other change.

### 8.3. Time Scope and Data Scope

Changes via the endpoint do not automatically modify `application.properties`, YAML, or environment variables. Nor is there a built-in expiration parameter for automatic rollback in this lesson's POST contract. If a short observation window is needed, explicitly define the end time and restoration responsibility in tooling or process outside the endpoint.

A restart reloads logging configuration from startup sources; backend auto-reload or intervention from an external controller can also change levels. Therefore, use `GET loggers` to read live state rather than looking only at `logging.level` in files or `Environment`.

DEBUG/TRACE can increase log volume, processing overhead, and written data. Choose a logger or group narrow enough for the issue; do not default to changing ROOT or a broad group to hunt a narrow bug. Log levels do not automatically redact sensitive data, so log-emitting code must still conform to what data is permitted to be logged.

When finished, confirm that both the configuration and new log volume have returned to the required state. Logs already emitted during the DEBUG window remain according to the system's retention policy; restoring the level does not delete them.

## 9. Classifying Errors When Requests or Results Are Wrong

| Symptom | What to check |
| --- | --- |
| GET/POST returns 404 | Actuator dependency, endpoint enabled, HTTP exposure, base path/management port, and exact instance address |
| POST returns 401/403 | Authentication, authorization, write-request protection policy, and CSRF if using Spring Security |
| POST returns 400 | JSON syntax, `configuredLevel` key name, and whether the level is in the supported list |
| POST returns 415 | `Content-Type` and actual body format sent |
| POST returns 204, but client expects JSON | 204 has no response body; follow up with GET to confirm |
| GET shows DEBUG, but no new DEBUG lines appear | Correct logger, code path executed after change, filters/appenders blocking, reading logs from the right instance |
| Group reports DEBUG, yet a child logger stays WARN | Child logger's own level, individual operation on a member, or overlapping groups |
| Sent {} yet did not return to old level | Cleared directly assigned level; did not restore saved record or parent logger changed |
| File still shows WARN, yet live GET is DEBUG | Runtime change did not alter configuration sources on disk |

Do not assume every mistyped logger name will be cleanly rejected: depending on the backend, a new name may still be created or queried with an inherited level. Confirm the name from code or the logger list instead of treating a successful request as proof you picked the right component.

POST may be blocked even when GET on the same endpoint succeeds. In applications with Spring Security, keep write-request protection aligned with your authentication mechanism; do not disable CSRF application-wide just to make one test command pass.

If the application changes its management port or Actuator path, use the real URL. The HTTP codes in the table are a classification guide, not a substitute for reading the response and checking proxies or system-specific policies. [Spring Boot 3.3 — exposing and securing endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 10. Self-Check

**Question 1:** Logger Worker initially had configuredLevel null and effectiveLevel INFO. After observing at DEBUG, is setting Worker to INFO an accurate restore?

No. You created a directly assigned level. To return to the prior policy, clear the direct level so Worker continues inheriting; then verify `effectiveLevel` in the current tree.

**Question 2:** Two members of a group were initially INFO and WARN respectively. Is enabling DEBUG on the group and then sending `{}` to the group sufficient?

No. Clearing the level does not remember the two initial levels. You need a record of each member and must restore them.

**Question 3:** The group reports DEBUG, yet `demo.alpha.Fixed` remains WARN. Is the endpoint necessarily broken?

No. Logger Fixed has a direct level of WARN. Read that specific logger to distinguish the group level, member level, and child logger level.

**Question 4:** After a runtime change, `application.properties` still says WARN. Why?

The endpoint changes levels in the running logging system; it is not a configuration file editor. Live state must be read from `loggers`.

**Question 5:** Does restoring members first and then restoring the group afterward always preserve the previous overrides?

No. The final group operation can re-apply a shared level over the members. Restore the group level first, then restore each member's explicit level and verify.

**Exercise:** Run a complete session with the `diagnostics` group. Record the levels of the group, both members, and Fixed beforehand; enable DEBUG; generate logs; clear the group level to observe the difference; then restore from the saved record. Conclude completion only when `configuredLevel`, `effectiveLevel`, and the probe messages match the saved state.
