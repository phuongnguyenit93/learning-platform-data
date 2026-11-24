# Building Results with Health.Builder and Diagnostically Meaningful Details

A `DOWN` result reports that a health condition failed, yet does not help the operator know what to inspect. Conversely, a response containing hundreds of fields is not necessarily useful if it lacks information about the check, threshold, and reason.

`Health.Builder` helps construct a result consisting of a **status** and **diagnostic context**. The goal of this lesson is to build explainable results: what was checked, what was observed, why that status was chosen, and which information should be exposed.

The examples use Java 21 and Spring Boot Actuator 3.3.x. The hands-on program pins Actuator 3.3.0 so learners can verify the exact demonstrated behavior.

## 1. How Are Health, Builder, and Checks Related?

A `Health` represents the condition of a component or subsystem. The two parts to care about are:

- `status`: a status such as UP, DOWN, OUT_OF_SERVICE, or UNKNOWN.
- `details`: a map of supplementary data with `String` keys and `Object` values.

`Health.Builder` is the object used while constructing the result. Chained methods return the Builder; `build()` returns `Health`. [Boot 3.3 Health API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.html).

The design flow should be:

```text
Collect observations
        ↓
Evaluate observations against the component's policy
        ↓
Select status
        ↓
Add details explaining the decision
        ↓
build() → Health
```

Builder does not check connections, measure capacity, or verify business logic on its own. It represents the result that application code has evaluated.

A simple example, placed inside a method capable of returning `Health`:

```java
return Health.down()
        .withDetail("target", "archive-store")
        .withDetail("check", "write-capacity")
        .withDetail("reasonCode", "LOW_CAPACITY")
        .withDetail("freeMiB", 40L)
        .withDetail("requiredMiB", 100L)
        .build();
```

This is a method body snippet, not a standalone Java program. With the data above, the reader knows the storage component fell short of the 100 MiB threshold because only 40 MiB remains, rather than merely receiving a DOWN label.

## 2. Choose Status by Meaning, Not by Information Volume

| Creation/status-setting call | Operation meaning | Usage in an example policy |
| --- | --- | --- |
| `Health.up()` or `builder.up()` | Set status to UP | Observation satisfies the defined criteria |
| `Health.down()` or `builder.down()` | Set status to DOWN | Required condition is not met |
| `Health.outOfService()` or `builder.outOfService()` | Set OUT_OF_SERVICE | Component deliberately stops serving during maintenance |
| `Health.unknown()` or `builder.unknown()` | Set UNKNOWN | Insufficient valid observations to conclude per policy |
| `Health.status(...)` or `builder.status(...)` | Set the specified status | Standard status or custom status with a defined meaning |

The methods above set the status value; deciding which status to choose is the responsibility of the evaluation code. The maintenance and invalid-observation examples in the table are illustrative application policies, not automatic inference rules of Builder. [Health.Builder methods](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.Builder.html).

### Pitfalls to Avoid Confusing

**Having details does not mean UP.** A result with rich diagnostic information can still be DOWN or UNKNOWN.

**Changing status does not automatically clear details.** If a Builder already contains a failure reason, calling `up()` does not automatically remove that reason. Reusing a Builder across multiple branches or multiple checks easily produces self-contradictory results.

**Adding a key named `status` does not change the real status.** For example, `withDetail("status", "DOWN")` only adds data inside details. To change the status, you must use a status method. Avoid keys that cause confusion with the enclosing structure.

**A default Builder is not UP.** In the practiced version, `new Health.Builder().build()` yields the UNKNOWN status. Every return path should select a status intentionally.

**Custom statuses require accompanying policies.** `Health.status("DEGRADED")` creates a result with that code, but does not automatically define its severity during aggregation or the desired HTTP code. You must design these policies when using custom statuses.

## 3. Which Details Actually Aid Diagnostics?

Good details explain the decision using bounded data with units and a clear link to the check.

| Operator's question | Detail that can be provided | Example |
| --- | --- | --- |
| Which component is this about? | Stable alias of the check target | `target: archive-store` |
| What check was performed? | Name of the check | `check: write-capacity` |
| Why does it have this status? | Reason code with a stable meaning | `reasonCode: LOW_CAPACITY` |
| What was the specific observation? | Measured or observed value | `freeMiB: 40` |
| What is the desired condition? | Threshold or reference criterion | `requiredMiB: 100` |
| How long did the check take? | Actually measured duration | `durationMillis: 18` |
| When was the result taken? | Check timestamp when needed | `checkedAt` in timezone-aware format |
| Was a cached result used? | Result age or data-source indicator | `observationAgeMillis` if actually cached |

Names like `target`, `check`, and `reasonCode` in this lesson are conventions chosen by the example, not mandatory Spring Boot fields.

### Before and After Comparison

Information that is too generic:

```json
{
  "status": "DOWN",
  "details": {
    "message": "Something is wrong"
  }
}
```

Information that can be cross-checked:

```json
{
  "status": "DOWN",
  "details": {
    "target": "archive-store",
    "check": "write-capacity",
    "reasonCode": "LOW_CAPACITY",
    "freeMiB": 40,
    "requiredMiB": 100
  }
}
```

The second response supports verifying capacity and the configured threshold. It does not claim to have identified every root cause, such as why capacity dropped rapidly.

### Keep Units and Data Types Consistent

Use numbers for numeric quantities:

```java
.withDetail("freeMiB", 40L)
.withDetail("requiredMiB", 100L)
```

Avoid combining numbers and units into a string that is hard to process automatically, such as `"about 40 MB left"`. Also distinguish MiB from MB: MiB uses 1,048,576 bytes, while MB uses 1,000,000 bytes. Field names and conversions must be consistent.

Do not add a hardcoded `durationMillis` just to make the response look complete. Only publish timing data if you actually measured the part of the work you intend to describe. When measuring intervals in Java, you can take the difference of `System.nanoTime()` and convert units.

## 4. Using `withDetail` and `withDetails` for Their Intended Purpose

`withDetail(key, value)` adds or replaces a value by key. `withDetails(map)` adds a set of details; duplicate keys are replaced by the values from the supplied map.

Code snippet example:

```java
Health health = Health.up()
        .withDetail("retryCount", 1)
        .withDetails(Map.of(
                "retryCount", 2,
                "reasonCode", "PROBE_OK"))
        .build();
```

The final value of `retryCount` is the number 2. `withDetails` does not clear all existing keys; other keys are preserved. Therefore, avoid having multiple layers of code write the same key while interpreting its meaning differently.

Some useful rules:

- Choose stable field names that accurately express their meaning.
- Use `String`, numbers, booleans, and small structures that serialize cleanly to JSON.
- For grouped data, only include maps/lists containing curated data.
- Avoid putting entire entities, service beans, requests, or connection objects into details.
- Do not pass `null` to `withDetail`; this method checks that both key and value are non-null in the practiced version. If no observation is available yet, omit the field and use an appropriate reason code.
- Do not publish a fake 0 in place of "not yet measured." Those two cases carry different diagnostic meanings.

The fact that the parameter type is `Object` does not mean every Java object is suitable to expose via an endpoint. A complex object may contain data that should not be exposed, circular references, or data that mutates after the result was created.

## 5. `withException` Does Not Automatically Switch Status to DOWN

These two snippets differ:

```java
Health noted = Health.up()
        .withException(new IllegalStateException("probe failed"))
        .build();

Health failed = Health.down(
        new IllegalStateException("probe failed")).build();
```

In Actuator 3.3.0:

- `noted` still has the UP status.
- `failed` has the DOWN status.
- Both can contain a detail with key `error` formed from the exception class name and its message.

`withException(...)` records error information, whereas `down(exception)` combines setting DOWN with recording error information. The `error` string is not the full stack trace. [Boot 3.3.0 Health and Builder implementation](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/Health.java).

This matters when writing:

```java
Health.Builder builder = Health.up();
```

If an error branch afterward only calls `withException(ex)`, the status can remain UP. You must set the status according to policy before returning the result.

### When to Use Curated Error Codes

Exception messages can contain hostnames, paths, or content from external systems. If that content is not controlled, you can build diagnostic results using a stable reason code.

The example below only illustrates how to represent an already-detected timeout; Builder does not create a timeout on its own:

```java
return Health.down()
        .withDetail("target", "archive-store")
        .withDetail("check", "write-probe")
        .withDetail("reasonCode", "PROBE_TIMEOUT")
        .withDetail("timeoutMillis", 200L)
        .build();
```

`timeoutMillis` should be the actual limit of the check, not a guessed number. Full error details can be written to logs with controlled access according to system policy.

## 6. Runnable Program Using the Real Actuator Library

The following example simulates capacity observation results and then uses `Health.Builder` directly. It does not measure real disk capacity and does not start a web server.

Evaluation rules in the example:

1. If in maintenance mode, return OUT_OF_SERVICE with reason MAINTENANCE.
2. If metrics are invalid, return UNKNOWN with reason INVALID_OBSERVATION.
3. If at least the required capacity remains, return UP.
4. If below threshold, return DOWN along with observed and threshold values.

In the first two branches, the example does not publish capacity numbers as if they were freshly verified valid observations.

### 6.1. Project Structure

Prepare JDK 21 and Gradle 8.5, then create:

```text
health-builder-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/HealthBuilderDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'health-builder-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-actuator'
}

application {
    mainClass = 'HealthBuilderDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

The BOM aligns dependency versions with Boot 3.3.0's release set. The `application` plugin is sufficient to run a console program using the Actuator API; this project does not configure a web application.

### 6.2. Complete Java Code

File `src/main/java/HealthBuilderDemo.java`:

```java
import java.util.Map;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public class HealthBuilderDemo {
    record CapacitySnapshot(
            long freeMiB,
            long requiredMiB,
            boolean maintenanceMode) {
    }

    static Health evaluate(CapacitySnapshot snapshot) {
        Health.Builder builder = new Health.Builder()
                .withDetail("target", "archive-store")
                .withDetail("check", "write-capacity");

        if (snapshot.maintenanceMode()) {
            return builder.outOfService()
                    .withDetail("reasonCode", "MAINTENANCE")
                    .build();
        }

        if (snapshot.freeMiB() < 0 || snapshot.requiredMiB() <= 0) {
            return builder.unknown()
                    .withDetail("reasonCode", "INVALID_OBSERVATION")
                    .build();
        }

        builder.withDetails(Map.of(
                "freeMiB", snapshot.freeMiB(),
                "requiredMiB", snapshot.requiredMiB()));

        if (snapshot.freeMiB() >= snapshot.requiredMiB()) {
            return builder.up()
                    .withDetail("reasonCode", "SUFFICIENT_CAPACITY")
                    .build();
        }

        return builder.down()
                .withDetail("reasonCode", "LOW_CAPACITY")
                .build();
    }

    static void report(String name, Health health) {
        Map<String, Object> details = health.getDetails();
        System.out.printf(
                "%s | status=%s | reason=%s | freeMiB=%s | requiredMiB=%s%n",
                name,
                health.getStatus().getCode(),
                details.get("reasonCode"),
                details.getOrDefault("freeMiB", "n/a"),
                details.getOrDefault("requiredMiB", "n/a"));
    }

    public static void main(String[] args) {
        HealthIndicator healthy =
                () -> evaluate(new CapacitySnapshot(250, 100, false));

        report("healthy", healthy.health());
        report("low-capacity",
                evaluate(new CapacitySnapshot(40, 100, false)));
        report("maintenance",
                evaluate(new CapacitySnapshot(250, 100, true)));
        report("invalid-observation",
                evaluate(new CapacitySnapshot(-1, 100, false)));

        Health noted = Health.up()
                .withException(new IllegalStateException("probe failed"))
                .build();
        Health failed = Health.down(
                new IllegalStateException("probe failed")).build();

        System.out.println("withException.status="
                + noted.getStatus().getCode());
        System.out.println("withException.error="
                + noted.getDetails().get("error"));
        System.out.println("downException.status="
                + failed.getStatus().getCode());
        System.out.println("emptyBuilder.status="
                + new Health.Builder().build().getStatus().getCode());

        Health merged = Health.up()
                .withDetail("retryCount", 1)
                .withDetails(Map.of("retryCount", 2))
                .build();
        System.out.println("merged.retryCount="
                + merged.getDetails().get("retryCount"));

        Health.Builder reused = Health.up().withDetail("attempt", 1);
        Health first = reused.build();
        reused.down().withDetail("attempt", 2);
        Health second = reused.build();

        System.out.println("reuse.first.status="
                + first.getStatus().getCode());
        System.out.println("reuse.first.attempt="
                + first.getDetails().get("attempt"));
        System.out.println("reuse.second.status="
                + second.getStatus().getCode());
    }
}
```

The program includes a `HealthIndicator`-typed variable to illustrate the contract of returning `Health` from an evaluation. In a Spring Boot application, the indicator must be registered as a bean if it is to be discovered by the health infrastructure.

### 6.3. Running the Program

In the project directory:

```shell
gradle -q run --console=plain
```

If the project already has a Gradle Wrapper, in PowerShell you can use:

```powershell
.\gradlew.bat -q run --console=plain
```

On Linux/macOS:

```shell
./gradlew -q run --console=plain
```

Gradle resolves dependencies and sets up the classpath for the program. If invoking `javac` or `java` directly, the learner must provide a classpath containing Actuator and the required libraries; the JDK alone is not enough to compile Spring imports.

Stdout of the program, excluding dependency download notices or Gradle messages:

```text
healthy | status=UP | reason=SUFFICIENT_CAPACITY | freeMiB=250 | requiredMiB=100
low-capacity | status=DOWN | reason=LOW_CAPACITY | freeMiB=40 | requiredMiB=100
maintenance | status=OUT_OF_SERVICE | reason=MAINTENANCE | freeMiB=n/a | requiredMiB=n/a
invalid-observation | status=UNKNOWN | reason=INVALID_OBSERVATION | freeMiB=n/a | requiredMiB=n/a
withException.status=UP
withException.error=java.lang.IllegalStateException: probe failed
downException.status=DOWN
emptyBuilder.status=UNKNOWN
merged.retryCount=2
reuse.first.status=UP
reuse.first.attempt=2
reuse.second.status=DOWN
```

### 6.4. Reading Results with Boundaries

**healthy:** 250 MiB available, 100 MiB required, so the policy chooses UP and records SUFFICIENT_CAPACITY.

**low-capacity:** 40 MiB available, 100 MiB required, so it chooses DOWN. The two numeric fields allow operators to verify the decision.

**maintenance:** policy prioritizes maintenance, choosing OUT_OF_SERVICE. `n/a` is merely how the console program displays a missing field; the code does not put the string `n/a` into the Health object.

**invalid-observation:** negative numbers are not treated as valid measurements, so it chooses UNKNOWN. The example does not treat it as a normal observation and report low capacity.

Subsequent lines verify independent behaviors: `withException` preserves the status, an empty Builder defaults to UNKNOWN, duplicate keys are replaced, and reusing a Builder carries risks.

## 7. Why Should a New Builder Be Created for Each Evaluation?

Builder is a mutable stateful object. An indicator is typically called repeatedly, and health requests may arrive concurrently. Storing a Builder in a shared field allows data from multiple evaluations to mix.

In the program in section 6, each call to evaluate creates a local Builder, evaluates the data, and returns the result immediately from the corresponding branch. Do not store the Builder in a shared field and do not continue modifying it after Health has been returned.

### Limitations to Know in the Practiced Version

The Javadoc describes Builder as creating an immutable `Health`. However, in the Boot 3.3.0 implementation, the details map in the result is wrapped in an unmodifiable view over the Builder's map directly, rather than copied separately.

Therefore, after creating `first`, modifying `reused` in the example causes `first.getDetails().get("attempt")` to read back 2, even though `first` retains its UP status. The program printed this behavior explicitly.

Do not interpret `build()` as a guarantee of deep-copying all data. After creating the result, stop mutating the Builder and avoid putting mutable objects into details. When upgrading library versions, re-verify if code relies on an implementation detail like the one above.

This is also why you should keep the Builder local to a single call, create small diagnostic data with stable values, and return the result immediately.

### When the Framework Supplies the Builder

If using `AbstractHealthIndicator`, the `doHealthCheck(Health.Builder builder)` method receives a Builder provided by the superclass. Update that Builder in each branch; the superclass manages producing the result. Do not replace the provided Builder with another Builder and abandon the result.

The superclass also has a mechanism for handling exceptions into DOWN; this must align with the application's check policy. [AbstractHealthIndicator in Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/AbstractHealthIndicator.html).

## 8. Creating Details and Being Allowed to View Details Are Two Separate Things

Builder can populate full information in `Health.getDetails()`, yet the HTTP response still depends on visibility configuration, health groups, and caller permissions.

Example configuration for a web application that already has Actuator and appropriate authentication:

```yaml
management:
  endpoint:
    health:
      show-components: when-authorized
      show-details: when-authorized
      roles:
        - ACTUATOR
```

This configuration does not automatically create accounts or assign roles. It must be coordinated with the application's security configuration. [Health information and visibility permissions in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

If an indicator is registered under the name `archiveStore` and the caller is authorized to view it, the component response may look like this:

```json
{
  "status": "DOWN",
  "components": {
    "archiveStore": {
      "status": "DOWN",
      "details": {
        "target": "archive-store",
        "check": "write-capacity",
        "reasonCode": "LOW_CAPACITY",
        "freeMiB": 40,
        "requiredMiB": 100
      }
    }
  }
}
```

This is an example response with components and details shown, assuming the aggregate status is DOWN. It is not stdout from the console program in section 6.

At the root endpoint, an indicator's details typically sit under `components.<component-name>.details`. Querying a component directly has a different structure. [HTTP structure of the health endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

Therefore, when a detail does not appear over HTTP, first distinguish: whether code did not produce that field, whether the field is at a different path, or whether the visibility policy is hiding it.

## 9. Keeping Details Useful Without Overexposing

The goal is enough information to determine the next verification step, not copying all internal state into the response.

### Prefer

- A check target alias instead of a full URL containing credentials.
- A stable reason code instead of an arbitrary message that is hard to compare.
- Observed values and thresholds in the same units.
- Measured durations with a clear scope.
- Information about the source and freshness of an observation when fresh data must be distinguished from cached results.

### Remove or Control

- Passwords, access tokens, API keys, and connection strings containing secrets.
- Request payloads, business records, or user data.
- Full stack traces and unfiltered error messages.
- Service objects, entities, or large structures merely because Builder accepts `Object`.
- Unobserved numbers filled in just to make the response look complete.

Do not assume that keys named `password` or `token` in custom health will be masked automatically. Curate data right when constructing details and verify the response intended for each caller group.

## 10. Verifying Diagnostic Content Branch by Branch

For a real check, verify both the status and the explanatory content.

| Branch | What to confirm |
| --- | --- |
| Condition met | UP accompanied by reason code and observation genuinely meeting the threshold |
| Condition not met | DOWN accompanied by observed value and unmet criterion |
| Maintenance | Status and reason accurately express the maintenance policy |
| Invalid observation | Does not turn "unknown" into valid numbers or a fake UP result |
| Timeout | Reason code and time limit match the check |
| Exception | Status is set correctly; exposed error data is controlled |
| Subsequent call after recovery | No stale error data retained from the previous call |
| Concurrent calls | No shared Builder or mutable diagnostic data |

A good result must be internally consistent. For instance, DOWN with `reasonCode=SUFFICIENT_CAPACITY` or UP containing only a severe error requires explanation, and is usually a sign that a branch changed status while retaining old details.

Additionally, the check must have appropriate cost and time bounds. Recording `timeoutMillis` in details does not automatically cause a blocked network operation to terminate after that duration; timeouts must be configured on the operation or client itself.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning only `Health.down().build()` for every failure | Hard to tell which condition failed | Add check, reason, and meaningful observations |
| Calling only `withException(ex)` on an UP Builder | May return UP along with error | Choose the failure status intentionally |
| Forgetting to choose a status | May return UNKNOWN unintentionally | Inspect every return path |
| Assuming `withDetails` wipes the old map | Retains information from another branch | Create a new Builder and manage keys explicitly |
| Reusing a Builder across multiple checks | Stale or mixed data | Keep the Builder scoped to a single evaluation |
| Using the string `"40"` without stating the unit | Hard to interpret and process automatically | Keep numeric types, include the unit in the field name |
| Returning unfiltered exception messages | May leak internal information | Use reason codes and access-controlled logs |
| Enabling `show-details` to "fix" missing fields | Code may not have created that field | Verify `Health` in code first, then check visibility permissions |
| Defining a custom status while omitting aggregation policy | Aggregate response may behave unexpectedly | Design severity ordering and HTTP mapping |

## 12. Practice

Change the input data in the program in section 6, then predict the status and details before running.

1. Use `freeMiB=100`, `requiredMiB=100`, not in maintenance. Verify the condition at the exact threshold.
2. Use `freeMiB=99`, `requiredMiB=100`. Confirm the reason code and the two numeric values.
3. Use `requiredMiB=0`. Explain why the example treats this configuration as an invalid observation.
4. Enable maintenance while setting negative capacity. Determine which branch takes precedence under the current order.
5. Change an error branch to only call `withException` after `Health.up()`. Observe the status and explain why that could violate policy.
6. Remove the intentional Builder reuse in main; keep local Builder creation inside `evaluate`.
7. Design three to five diagnostic fields for a connection check with a timeout. Specify which fields are observations, which are configuration, and which is the reason code.

Check the boundary cases:

- Exercise 1: UP with SUFFICIENT_CAPACITY because the example uses greater-than-or-equal.
- Exercise 2: DOWN with LOW_CAPACITY, preserving the number 99 and threshold 100.
- Exercise 3: UNKNOWN with INVALID_OBSERVATION per the example's contract.
- Exercise 4: OUT_OF_SERVICE with MAINTENANCE because the maintenance branch is evaluated first.
- Exercise 5: the status can remain UP if there is no operation changing the status.

When finalizing a `Health` result, read it as an incident responder: can you tell the component and check, can you cross-check the decision against observations, and do you know the bounds of the conclusion? Those questions turn details into diagnostic data rather than a set of fields added for appearances.
