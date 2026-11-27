# Supported Value Types and Value Ranges

Spring Boot provides `RandomValuePropertySource` so applications can reference random values directly in configuration. This mechanism supports integers, long integers, UUIDs, and a string-formatted random value. For `random.int` and `random.long`, you can also bound the output domain using single-bound or two-bound syntax.

This is a Spring Boot utility, not a Spring Cloud-specific random generation API. Spring Cloud applications can still use these placeholders through `Environment` and Spring Boot's externalized configuration mechanism. They are useful for test data, temporary identifiers, and initialization values at application startup.

This lesson belongs to the **Random Values** chapter of the **SPRING_CLOUD_CORE** module. We will distinguish each type, read the lower/upper bound rules accurately, use placeholders in YAML and properties, bind to Java types, test value ranges, and recognize security limitations across Spring Boot versions.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the role of `RandomValuePropertySource` in Spring `Environment`.
- Identify the four documented placeholder groups: `random.int`, `random.long`, `random.uuid`, and `random.value`.
- Distinguish unbounded random numbers from numbers within a specified domain.
- Explain that the lower bound is inclusive and the upper bound is excluded from the domain.
- Use single-bound and two-bound syntax for both `int` and `long`.
- Write placeholders in `application.yml` and `application.properties`.
- Bind random values to `@Value` and `@ConfigurationProperties`.
- Verify data types and output ranges without relying on a fixed random number.
- Understand value generation timing, stability across restarts, and the effect of re-reading properties.
- Recognize the limitations of random values when used as IDs, passwords, or security keys.

## 2. Where Does RandomValuePropertySource Live?

`RandomValuePropertySource` is a special Spring Boot `PropertySource`. It handles properties whose names start with `random.`. Spring Boot adds this property source to `Environment` during startup environment preparation.

You can consume values through:

- Placeholders in configuration files, such as the `random.uuid` property.
- The `@Value` annotation.
- `Environment.getProperty(...)`.
- Binding to `@ConfigurationProperties` beans.

Basic flow:

~~~mermaid
flowchart TD
    A[application.yml or application.properties] --> B[Placeholder random.*]
    B --> C[Spring Environment]
    C --> D[RandomValuePropertySource]
    D --> E[Generate requested type]
    E --> F[Property placeholder resolution]
    F --> G[@Value / Binder / Environment]
    G --> H[Application bean]
~~~

Example:

~~~yaml
app:
  instance-id: "${random.uuid}"
  test-number: "${random.int}"
  sample-code: "${random.int[1000,9999]}"
~~~

Spring Boot resolves placeholders when configuration values are consumed. Beans receive the corresponding data type after the property resolver and conversion service process the value.

### 2.1. This Is Not a Static Property List

The `random.*` name is a special property namespace generated on demand. You do not need to declare each `random.int` or `random.uuid` key in configuration files before using it.

Each time `RandomValuePropertySource` is asked for a random property, it generates a result based on the suffix of the property name. Therefore, do not treat a UUID placeholder as a fixed-value variable that can be referenced everywhere at any time. If multiple components need the same ID, generate it once, store it in a bean or data store, and pass that generated value to those components.

### 2.2. Property Sources and Configuration Overrides

Random values are resolved within Spring Boot's `PropertySource` precedence hierarchy. Configuration sources with higher priority can provide an overriding value for a property. When diagnosing unexpected values, inspect `Environment` and the actual configuration sources rather than assuming every placeholder is regenerated.

## 3. Supported Value Types

Spring Boot documents four main value groups:

| Placeholder | Type/Result | Common Purpose |
| --- | --- | --- |
| `random.int` | Random `Integer` across the full `int` range | Test numbers, temporary numeric values |
| `random.long` | Random `Long` across the full `long` range | Large numeric values, test data |
| `random.uuid` | String-formatted UUID | Temporary IDs, startup correlation IDs |
| `random.value` | Random string | Initialization values or test data |

The two numeric groups can use range-bounding suffixes. UUID and value do not accept numeric range parameters.

### 3.1. random.int

`random.int` generates a Java `int`. The domain of `int` is:

~~~text
-2,147,483,648 to 2,147,483,647
~~~

When no bounds are specified, the value can be negative, zero, or positive. Do not assume `random.int` only produces positive numbers.

~~~yaml
app:
  random-int: "${random.int}"
~~~

When bound to Java:

~~~java
@Value("${app.random-int}")
private int randomInt;
~~~

### 3.2. random.long

`random.long` generates a Java `long` across the full signed 64-bit range:

~~~text
-9,223,372,036,854,775,808
to
 9,223,372,036,854,775,807
~~~

~~~yaml
app:
  random-long: "${random.long}"
~~~

Corresponding Java type:

~~~java
@Value("${app.random-long}")
private long randomLong;
~~~

Choose `long` when the property needs a larger numeric range than `int`. If business logic requires a specific range, use the bounded syntax rather than taking the full range and manually adjusting the result.

### 3.3. random.uuid

`random.uuid` generates a UUID and returns it in standard string form. A typical UUID has the format:

~~~text
xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
~~~

Characters represent hex digits; UUID v4 has version nibble `4` and variant nibble per UUID rules.

~~~yaml
app:
  instance-id: "${random.uuid}"
  correlation-seed: "${random.uuid}"
~~~

In Java:

~~~java
@Value("${app.instance-id}")
private UUID instanceId;
~~~

Spring can convert a UUID string to `java.util.UUID` during binding. If explicit control is needed, accept a `String` and call `UUID.fromString(...)`.

UUID is suitable for identifiers requiring a very low collision probability. It is not a monotonically increasing sequence number and should not be used in place of a dedicated secret key.

### 3.4. random.value

`random.value` generates a string-formatted random value. In the Spring Boot 4.1.2 implementation, this mechanism generates 16 random bytes and formats them as 32 lowercase hexadecimal characters.

~~~yaml
app:
  sample-token: "${random.value}"
~~~

The exact output format should be verified against the running Spring Boot version. Do not write code that depends on a fixed length or character set if the application must run across different release trains.

## 4. Range-Bound Syntax for int and long

`random.int` and `random.long` support two bounding forms:

1. Single bound: `random.int(10)`.
2. Two bounds: `random.int[1024,65536]`.

The opening and closing characters can be any characters accepted by the parser syntax; the documentation commonly uses parentheses or square brackets for readability. Regardless of which characters are used, the lower/upper bound rules are the same.

### 4.1. Single Bound: from 0 to Upper Bound

For the placeholder `random.int(10)`, `10` is the exclusive upper bound. The result lies in the range:

~~~text
[0, 10) = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
~~~

Similarly:

~~~yaml
app:
  retry-sample: "${random.int(5)}"
  worker-sample: "${random.long(100000)}"
~~~

`random.int(5)` can only produce `0` through `4`. `random.long(100000)` produces a `long` from `0` through `99999`.

### 4.2. Two Bounds: min Inclusive, max Exclusive

For the placeholder `random.int[1024,65536]`, `1024` is the inclusive lower bound; `65536` is the exclusive upper bound. The output range:

~~~text
[1024, 65536)
~~~

This means the smallest possible value is `1024` and the largest is `65535`.

~~~yaml
app:
  port-candidate: "${random.int[10000,20000]}"
  batch-size: "${random.int[20,101]}"
  long-sequence-sample: "${random.long[10000000000,20000000000]}"
~~~

| Property | Output Range |
| --- | --- |
| `port-candidate` | `10000` to `19999` |
| `batch-size` | `20` to `100` |
| `long-sequence-sample` | `10000000000` to `19999999999` |

### 4.3. Negative Bounds and Ranges Containing Negative Numbers

Both bounds can be negative as long as the lower bound is less than the upper bound:

~~~yaml
app:
  signed-offset: "${random.int[-10,11]}"
  signed-long-offset: "${random.long(-5000000000,5000000001)}"
~~~

`signed-offset` can take values from `-10` to `10`. `signed-long-offset` can take values from `-5000000000` to `5000000000`.

The essential condition is `min < max`. If both bounds are equal or the lower bound is greater than the upper bound, the range is invalid and value generation will fail.

### 4.4. Equivalent Syntax with properties

~~~properties
app.random-int=${random.int}
app.random-long=${random.long}
app.random-uuid=${random.uuid}
app.random-value=${random.value}
app.number-under-ten=${random.int(10)}
app.number-in-range=${random.int[1024,65536]}
app.negative-range=${random.int[-10,11]}
~~~

In YAML, wrap placeholders in double quotes so the parser handles brackets and commas consistently:

~~~yaml
app:
  number-under-ten: "${random.int(10)}"
  number-in-range: "${random.int[1024,65536]}"
~~~

## 5. Summary Table of Syntax and Value Ranges

| Syntax | Type | Lower Bound | Upper Bound | Range |
| --- | --- | ---: | ---: | --- |
| `random.int` | int | Minimum int value | Maximum int value | Full int range |
| `random.int(10)` | int | 0 | 10 | `[0,10)` |
| `random.int[10,20]` | int | 10 | 20 | `[10,20)` |
| `random.long` | long | Minimum long value | Maximum long value | Full long range |
| `random.long(100)` | long | 0 | 100 | `[0,100)` |
| `random.long[1000,2000]` | long | 1000 | 2000 | `[1000,2000)` |
| `random.uuid` | String/UUID | Not applicable | Not applicable | UUID |
| `random.value` | String | Not applicable | Not applicable | Random string |

The notation `[min,max)` means `min` is inclusive and `max` is exclusive. The range `[10,20)` contains exactly 10 integer values.

## 6. Using Random Values in Spring Configuration

### 6.1. Complete YAML Configuration

~~~yaml
app:
  runtime:
    instance-id: "${random.uuid}"
    startup-number: "${random.int}"
    startup-counter: "${random.long}"
    test-code: "${random.int[100000,999999]}"
    sample-value: "${random.value}"
    retry-count: "${random.int(5)}"
~~~

This example shows multiple types declared together. Values are resolved when properties are consumed during startup or when a component queries them.

### 6.2. Combining Prefixes and Suffixes

You can combine a random value with a fixed string:

~~~yaml
app:
  instance-name: "worker-${random.int[100,1000]}"
  request-seed: "req-${random.uuid}"
  temporary-code: "TMP-${random.int[100000,1000000]}"
~~~

The placeholder is replaced with the random result while the rest of the string is preserved.

### 6.3. Providing a Default Value for a Business Property

You can use a random placeholder as a default value inside another placeholder:

~~~yaml
app:
  instance-id: "${APP_INSTANCE_ID:${random.uuid}}"
~~~

If a configuration source provides `APP_INSTANCE_ID`, the provided value is used. Otherwise, Spring Boot resolves the random UUID fallback.

This is a way to combine externalized configuration with default values. If the ID must remain stable across restarts, supply the ID from the deployment platform or persist the generated ID; do not rely on a random fallback.

## 7. Binding to Java with @Value and @ConfigurationProperties

### 7.1. Using @Value

~~~java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StartupValues {

    @Value("${app.runtime.instance-id}")
    private UUID instanceId;

    @Value("${app.runtime.startup-number}")
    private int startupNumber;

    @Value("${app.runtime.startup-counter}")
    private long startupCounter;

    @Value("${app.runtime.test-code}")
    private int testCode;

    public UUID getInstanceId() {
        return instanceId;
    }

    public int getStartupNumber() {
        return startupNumber;
    }

    public long getStartupCounter() {
        return startupCounter;
    }

    public int getTestCode() {
        return testCode;
    }
}
~~~

Spring converts property results to the target type when conversion is supported. If a numeric placeholder falls outside the range of the target Java type, binding can fail.

### 7.2. Using @ConfigurationProperties

When there are multiple related values, group them into a configuration object:

~~~java
package com.example.demo.config;

import java.util.UUID;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.runtime")
public record RuntimeProperties(
        UUID instanceId,
        int startupNumber,
        long startupCounter,
        int testCode,
        String sampleValue,
        int retryCount) {
}
~~~

Register configuration properties via scanning:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
~~~

With the YAML from the previous section, Spring Boot resolves placeholders and binds values into the record. This is configuration created when the application context starts; the record does not regenerate values each time a getter is called.

### 7.3. Querying Environment Directly

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RandomValueReader {

    private final Environment environment;

    public RandomValueReader(Environment environment) {
        this.environment = environment;
    }

    public int nextSample() {
        return environment.getProperty(
                "random.int[10,20]", Integer.class);
    }
}
~~~

This snippet illustrates reading a random property by name. Each call to the property source can produce a new result. If the same result is needed across multiple operations, store the returned value in a variable or bean instead of calling `getProperty` multiple times.

## 8. Generation Timing and Value Stability

### 8.1. Values Are Not Fixed Configuration

A random value is generated when the property source handles a property read request. A value bound to a bean field or constructor is typically retained in that bean instance after binding. However, if a component continues reading `Environment` directly, the next read can receive a new random result.

~~~java
int first = environment.getProperty("random.int", Integer.class);
int second = environment.getProperty("random.int", Integer.class);
~~~

Do not assume `first` and `second` are equal. If business logic requires a single shared value:

~~~java
int startupSeed = environment.getProperty(
        "random.int[1000,2000]", Integer.class);

processA(startupSeed);
processB(startupSeed);
~~~

### 8.2. Across New Restarts

Random values are not durably persisted data. When the application restarts and the property is resolved again, the result may differ. This is useful for temporary data, but unsuitable for IDs that must remain constant for long-term references by other systems, encryption keys that must reuse the same key after restarts, passwords shared across multiple replicas, or values that must be reproduced identically during replays.

If stability is required, generate the value outside the application, store it in a database/secret manager/config store, and inject it as a regular property.

### 8.3. Spring Cloud Refresh and Random Values

Spring Cloud Context can refresh configuration sources and rebind beans. However, do not treat `random.*` as a stable ID source or a lifecycle-managed secret store. If a bean is rebound or a placeholder is re-resolved, the random value may be regenerated depending on the read path and bean lifecycle. For IDs or keys that must remain stable, store the value in a durable configuration source before refreshing.

## 9. Verifying Value Ranges and Writing Tests

Do not write tests expecting a random property to return one specific hardcoded number. Tests should verify the type, value range, and UUID format.

### 9.1. Unit Test Checking Bounds

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.env.RandomValuePropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class RandomRangeTest {

    @Test
    void generatesIntegerWithinInclusiveExclusiveRange() {
        StandardEnvironment environment = new StandardEnvironment();
        RandomValuePropertySource.addToEnvironment(environment);

        for (int i = 0; i < 100; i++) {
            Integer value = environment.getProperty(
                    "random.int[10,20]", Integer.class);

            assertThat(value).isNotNull();
            assertThat(value).isBetween(10, 19);
        }
    }
}
~~~

The test uses a loop to check the bounds, not statistical distribution. You cannot prove randomness quality with a few dozen samples; testing here only verifies the bound contract.

### 9.2. Checking UUID and random.value

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.boot.env.RandomValuePropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class RandomFormatTest {

    @Test
    void createsUuidAndRandomString() {
        StandardEnvironment environment = new StandardEnvironment();
        RandomValuePropertySource.addToEnvironment(environment);

        String uuid = environment.getProperty("random.uuid");
        String value = environment.getProperty("random.value");

        assertThat(UUID.fromString(uuid)).isNotNull();
        assertThat(value).isNotBlank();
    }
}
~~~

If you want to verify the exact length/charset of `random.value`, write tests tied to the specific Spring Boot version and verified implementation. Do not turn an implementation detail into a compatibility contract across all release trains.

### 9.3. Checking YAML Configuration When Running the Application

In applications with Actuator, the `/actuator/env` endpoint can help diagnose property sources and resolved values. This endpoint can expose sensitive configuration data; expose it only within a management network and apply appropriate sanitization and authorization. In tests, prefer inspecting configuration beans or `Environment` directly instead of enabling management endpoints.

## 10. Common Errors When Specifying Ranges

| Syntax | Issue | What to Understand |
| --- | --- | --- |
| `random.int(0)` | Single-parameter upper bound must be greater than 0 | Empty range, cannot generate a value |
| `random.int[10,10]` | Lower bound equals upper bound | Empty range |
| `random.int[20,10]` | Lower bound greater than upper bound | Invalid range |
| `random.int[10]` | Valid | `[0,10)` |
| `random.int[-5,5]` | Valid | `[-5,5)` |
| `random.long[100,200]` | Valid | `[100,200)` |
| `random.uuid[10,20]` | Not a supported range syntax for UUID | Do not use ranges with UUID |

For single-bound syntax, the bound value must be positive. For two-bound syntax, the lower bound must be less than the upper bound. Numbers must also be parseable into the target type; values exceeding the `int` or `long` range will cause parsing errors.

### 10.1. Confusing Upper Bound Inclusivity

A common mistake is thinking `random.int[1,100]` can return `100`. In fact, the range is `[1,100)`, so the largest possible result is `99`.

If you need numbers from 1 through 100, set the upper bound to 101:

~~~yaml
app:
  percentage: "${random.int[1,101]}"
~~~

## 11. Security Limitations and CVE-2026-40975

Random values are a configuration utility, yet not every type is suitable as a secret. The quality of the random source also depends on the Spring Boot version.

### 11.1. Do Not Use int/long as Secrets

`random.int` only has 32 bits and `random.long` only has 64 bits. They have finite numeric domains that can be guessed or brute-forced in certain scenarios. Even if the underlying source is a cryptographic RNG, these numeric ranges remain unsuitable for passwords, API keys, or encryption keys.

Do not use:

~~~yaml
spring:
  security:
    user:
      password: "${random.int}"
app:
  signing-key: "${random.long}"
~~~

### 11.2. CVE-2026-40975 Affects random.value in Older Versions

Spring published `CVE-2026-40975` on April 23, 2026. Affected Spring Boot versions used a weak PRNG for `random.value`, making that value unsuitable as a secret. The advisory confirmed `random.uuid` is not affected; `random.int` and `random.long` should not be used as secrets in any version because their numeric space can be guessed.

In Spring Boot 4.1.2 source code, `RandomValuePropertySource` uses `SecureRandom` for its underlying generator. Upgrading to the corresponding patched release is the remediation recommended by the Spring advisory; do not manually replace the generator or patch this class inside your application.

Branches and patches announced by Spring:

| Spring Boot Branch | Affected Versions | Fixed Version |
| --- | --- | --- |
| 4.0.x | 4.0.0–4.0.5 | 4.0.6 |
| 3.5.x | 3.5.0–3.5.13 | 3.5.14 |
| 3.4.x | 3.4.0–3.4.15 | 3.4.16 (Enterprise Support) |
| 3.3.x | 3.3.0–3.3.18 | 3.3.19 (Enterprise Support) |
| 2.7.x | 2.7.0–2.7.32 | 2.7.33 (Enterprise Support) |

End-of-support versions must also be evaluated. Inspect your dependency tree to determine the exact runtime Spring Boot version, rather than looking solely at the Spring Cloud BOM version.

### 11.3. Recommendations for Real Secrets

- Use Vault, a cloud secret manager, KMS, or platform secret management mechanisms.
- Generate keys with appropriate cryptographic APIs when an application genuinely needs to generate key material itself.
- Do not persist generated secrets in logs, Actuator endpoints, or committed configuration files.
- If `random.value` is used in a sensitive context, use a patched version and evaluate the lifecycle, storage location, and sharing mechanism of the value.
- Do not use UUID as an encryption key merely because UUID is unaffected by this CVE.

`random.uuid` is better suited for identifiers. Encryption keys require cryptographic standards for length, algorithm, entropy source, storage, and rotation; do not substitute a configuration placeholder.

## 12. Complete Example: Generating Test Codes at Startup

Suppose a worker needs a dedicated ID per startup, a sample retry count from 1 to 5, and a six-digit test code.

Configuration:

~~~yaml
worker:
  startup:
    id: "${random.uuid}"
    retry-limit: "${random.int[1,6]}"
    test-code: "${random.int[100000,1000000]}"
~~~

Configuration bean:

~~~java
package com.example.worker;

import java.util.UUID;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker.startup")
public record WorkerStartupProperties(
        UUID id,
        int retryLimit,
        int testCode) {
}
~~~

Registration:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class WorkerApplication {

    public static void main(String[] args) {
        SpringApplication.run(WorkerApplication.class, args);
    }
}
~~~

Checking in a service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class WorkerService {

    private final WorkerStartupProperties properties;

    public WorkerService(WorkerStartupProperties properties) {
        this.properties = properties;
    }

    public void start() {
        System.out.println("workerId=" + properties.id());
        System.out.println("retryLimit=" + properties.retryLimit());
        System.out.println("testCode=" + properties.testCode());
    }
}
~~~

In production, avoid logging IDs or codes if they are used as credentials. The example above is for non-sensitive initialization data and illustrates how values are bound.

## 13. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Placeholder remains as `random.int` | Property was not resolved in the current source/read path or placeholder was escaped | Check configuration files, quotes, and how the property is consumed |
| Value falls outside expected range | Upper bound misread as inclusive | Remember max is exclusive; use max = desired value + 1 |
| Startup fails with range | Invalid bounds or number out of type range | Check `min < max`, positive bound in single-bound syntax, and int/long limits |
| Binding to UUID fails | Value is not a valid UUID or property was overridden | Check property sources and call `UUID.fromString()` in tests |
| Two reads yield two different results | Property source generates a value when read | Store the result in a bean/variable if reuse is needed |
| Value changes after restart | Random values are not persisted durably | Use an ID/secret stored in an external store if stability is required |
| `random.value` used as secret on older Boot | Version may be affected by CVE-2026-40975 | Check Boot version and upgrade to a patched release |
| Cannot use int/long as a key | Numeric domain is insufficient for cryptographic purposes | Use a secret manager or appropriate key generation API |

### 13.1. Diagnostic Procedure

1. Identify the full placeholder and expected type.
2. Check brackets, number of bounds, and the `min`/`max` relationship.
3. Check whether the value is overridden by a higher-precedence configuration source.
4. Check the target type in `@Value` or `@ConfigurationProperties`.
5. Call `Environment.getProperty()` in tests to verify type and range.
6. Check the runtime Spring Boot version if the value is used in a security context.

## 14. Practice Exercises

### Exercise 1 — Type Classification

Declare four properties: an unbounded `int`, an unbounded `long`, a UUID, and a string-formatted random value. Bind them to a Java bean and verify their data types.

### Exercise 2 — Range Verification

Create three properties: `random.int(10)`, `random.int[10,20]`, and `random.long[-100,100]`. Read each value 100 times in a test and verify every result falls within its corresponding range.

### Exercise 3 — Fixing Off-by-One

A requirement calls for generating a percentage from 1 to 100. Write the correct placeholder and explain why the upper bound must be 101.

### Exercise 4 — Stability Across Multiple Reads

Read `random.uuid` twice from `Environment` and compare. Then read it once, store it in a bean field, and use that field in two methods. Explain the difference between re-reading the property and reusing a stored value.

### Exercise 5 — Security Assessment

Check a Spring Boot version in the affected list for CVE-2026-40975. Identify the corresponding patch version and explain why `random.int`/`random.long` are not options for generating secrets.

**Completion criteria:** you can choose the right random type, calculate `[min,max)` ranges accurately, bind to Java, test bounds, and identify when a secret manager must be used instead of a random placeholder.

## 15. Summary

Spring Boot provides `RandomValuePropertySource` to resolve `random.*` placeholders in `Environment`. The four common groups are `int`, `long`, `uuid`, and `value`. The two numeric types support unbounded domains, single-bound syntax `[0,n)`, and two-bound syntax `[min,max)`. The lower bound is inclusive, and the upper bound is exclusive.

Values can be used in YAML, properties, `@Value`, `Environment`, and `@ConfigurationProperties`. Values are generated when the property source handles a request; if you need to reuse the same result multiple times or require stability across restarts, store and manage that value in an appropriate place.

Do not use `int` or `long` as secrets. For `random.value`, check your Spring Boot version due to CVE-2026-40975 affecting older branches; upgrade to a patched release and use a secret manager/KMS for secrets with long-term value.

## References

- [Spring Boot — Externalized Configuration, Configuring Random Values](https://docs.spring.io/spring-boot/reference/features/external-config.html): examples of `random.int`, `random.long`, `random.uuid`, `random.value`, and range rules.
- [RandomValuePropertySource API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/RandomValuePropertySource.html): supported types and numeric range syntax.
- [RandomValuePropertySource source, Spring Boot 4.1.2](https://github.com/spring-projects/spring-boot/blob/v4.1.2/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/env/RandomValuePropertySource.java): implementation of value generation, range handling, and random bytes formatting.
- [Spring Security Advisory — CVE-2026-40975](https://spring.io/security/cve-2026-40975/): affected Spring Boot versions, fixes, and notes on using random values as secrets.
- [Spring Boot 4.0.6 release announcement](https://spring.io/blog/2026/04/23/spring-boot-4-0-6-available-now/): confirmation of the release fixing CVE-2026-40975.

Always verify the actual runtime Spring Boot version and the Spring Cloud BOM compatibility matrix. Range syntax is stable in Spring Boot documentation, while `random.value` formatting details and security guarantees depend on the version.
