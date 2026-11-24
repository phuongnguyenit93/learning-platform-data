# @Past, @PastOrPresent, @Future, and @FutureOrPresent in Jakarta Validation

> **Module:** Spring Framework – validation-data-binding  
> **Parent Topic:** Standard Constraints  
> **Scope:** The four standard temporal constraints in `jakarta.validation.constraints`, how they compare against "present", supported data types, `ClockProvider`, Spring MVC integration, and deterministic testing.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the exact meaning of `@Past`, `@PastOrPresent`, `@Future`, and `@FutureOrPresent` and their differences at the **present boundary**.
- Choose the right constraint for birth dates, end dates, effective start dates, appointments, and deadlines.
- Understand why `LocalDate` is compared by **day**, whereas `Instant` is compared by **instant in time**, with "now" determined by `ClockProvider`.
- Avoid confusing validation of **temporal values** with parsing date strings into Java types.
- Test `null` values, different timezones, boundary-adjacent cases, and data that expires during processing.
- Write a deterministic Java 17+ test example using a fixed clock, and use these constraints in Spring MVC.

## 2. Concept: Four Constraints Based on Relation to the Present

The annotations reside in package:

```java
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.PastOrPresent;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.FutureOrPresent;
```

All four are **Jakarta Validation constraints**, not Spring-specific annotations. The provider (typically Hibernate Validator in Spring Boot) performs the comparison; the annotation itself only supplies metadata for the validator to evaluate when triggered.

| Annotation | Condition for Non-Null Value | Includes Present? | Common Use Cases |
| --- | --- | --- | --- |
| `@Past` | Value is **before** present | No | Event occurred before today, completed timestamp |
| `@PastOrPresent` | Value is **before or equal to** present | Yes | Birth date cannot be after today, recorded date up to now |
| `@Future` | Value is **after** present | No | Job execution time must be in the future, appointment must start after now |
| `@FutureOrPresent` | Value is **after or equal to** present | Yes | Effective date starting today, due date no earlier than today |

Visual model with `now` as the reference point:

```text
Time:       past     ----------  NOW  ----------  future

@Past                  < NOW
@PastOrPresent        <= NOW
@Future                 > NOW
@FutureOrPresent       >= NOW

Special case for null: all 4 constraints treat it as valid.
```

The symbols `<`, `<=`, `>`, `>=` here describe temporal relationships, **not that every Java type directly invokes numeric operators**. The provider uses the validator matching the data type.

### 2.1. Present Is Not Always a Single Nanosecond

Suppose the reference clock is at **2026-11-05 15:00:00** in `Asia/Ho_Chi_Minh`:

| Value Type | Value Considered Present | Interpretation |
| --- | --- | --- |
| `LocalDate` | `2026-11-05` | The entire **day** of Nov 5 is considered today |
| `YearMonth` | `2026-11` | The **entire month** of November is the current month |
| `Year` | `2026` | The **entire year** 2026 is the current year |
| `LocalDateTime` | `2026-11-05T15:00:00` | Compares down to local date and time per the reference clock |
| `Instant` | `2026-11-05T08:00:00Z` | Compares instants on the UTC timeline |

Therefore, `@Future LocalDate` **does not accept today**, even though hours remain in the day; `@FutureOrPresent LocalDate` **accepts today**. For `@Future Instant`, the instant must be **strictly later** than the check instant, not merely on a different day.

In the specification, the meaning of "present" is defined **relative to the data type**; this is why choosing the right Java type up front is essential.

## 3. Boundary Differences: With and Without `OrPresent`

Example `LocalDate` values when `today = 2026-11-05`:

| Value | `@Past` | `@PastOrPresent` | `@Future` | `@FutureOrPresent` |
| --- | --- | --- | --- | --- |
| `2026-11-04` | Pass | Pass | Fail | Fail |
| `2026-11-05` | Fail | Pass | Fail | Pass |
| `2026-11-06` | Fail | Fail | Pass | Pass |
| `null` | Pass | Pass | Pass | Pass |

Getting `OrPresent` wrong can alter business behavior:

- A `LocalDate` birth date can be today: use `@PastOrPresent`.
- An effective start date allowing activation **today**: use `@FutureOrPresent`.
- An appointment that must be scheduled for **tomorrow onward**: use `@Future LocalDate`.
- An appointment that must be after **the current moment** later the same day: use `@Future Instant`, `OffsetDateTime`, or a type with clear instant semantics; `LocalDate` lacks sufficient precision.

Three important shared attributes of all four annotations are `message`, `groups`, and `payload`. There is no `zone`, `timezone`, `pattern`, or `inclusive` attribute on the annotations directly; to customize the reference time source, use `ClockProvider`.

## 4. Declaring on DTOs for the Right Purpose

### 4.1. Birth Date and Effective Date

```java
import java.time.LocalDate;

import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PastOrPresent;

public record CustomerRegistration(
        @NotNull
        @PastOrPresent
        LocalDate birthDate,

        @NotNull
        @FutureOrPresent
        LocalDate validFrom) {
}
```

This is an **illustrative DTO**, not a standalone application.

- `birthDate` is required and cannot be after today; today is still valid.
- `validFrom` is required and cannot be before today; today is valid.
- `@NotNull` is crucial because `@PastOrPresent` and `@FutureOrPresent` **do not forbid null on their own**.

When requiring a user's birth date to be at least one day in the past, replace `@PastOrPresent` with `@Past`. However, to check **at least 18 years old**, `@Past` is nowhere near enough: you need an age-calculation rule based on `LocalDate` and the current date in the business timezone.

### 4.2. Instants with Hours, Minutes, and Timezone

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.Past;

public record MeetingRequest(
        @Future Instant beginsAt,
        @Past OffsetDateTime recordedAt) {
}
```

When representing an absolute point in time, `Instant` is usually the simplest choice: it is unambiguous across client timezones. `OffsetDateTime` carries a local time offset; if you also need region names and DST rules, consider `ZonedDateTime`.

The code above only declares constraints. It does not replace checking whether participants' schedules overlap, whether meeting duration is valid, or whether the user has permission to book.

### 4.3. Standard Supported Types

According to Jakarta Validation, the four constraints support these type families:

| Type Family | Examples | Selection Notes |
| --- | --- | --- |
| Legacy | `java.util.Date`, `Calendar` | Instant semantics; `Calendar` carries timezone; be careful with date-only inputs |
| Instants | `Instant`, `OffsetDateTime`, `ZonedDateTime` | Ideal when comparing an instant on the timeline |
| Local date/time | `LocalDate`, `LocalDateTime`, `LocalTime` | Carry no offset; depend on `ClockProvider`'s timezone to determine "now" |
| Other calendar granularities | `Year`, `YearMonth`, `MonthDay` | "Present" matches that granularity, not always an instant |
| Non-ISO calendars | `HijrahDate`, `JapaneseDate`, `MinguoDate`, `ThaiBuddhistDate` | When genuinely using those calendar systems |

**Do not** put these four constraints directly on a `String` containing a date, a `Long` timestamp, or another numeric type expecting the provider to parse it automatically. If a constraint has no validator supporting the declared type, validation can throw `UnexpectedTypeException` (a `ConstraintDeclarationException`/validation error from incompatible types) instead of returning a normal data violation.

Example to avoid:

```java
@Future
private String scheduledAt; // Not a supported temporal type.
```

The right way is to convert the input string into the appropriate temporal type **first**, and then validate.

## 5. Where Does "Now" Come From? `ClockProvider`

Jakarta Validation does not expect each validator to hardcode calls to `LocalDate.now()` or `Instant.now()`. Temporal validators obtain the current reference time from **`jakarta.validation.ClockProvider`** attached to the `ValidatorFactory` or `Validator`.

```java
import java.time.Clock;
import jakarta.validation.ClockProvider;

public final class FixedClockProvider implements ClockProvider {

    private final Clock clock;

    public FixedClockProvider(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Clock getClock() {
        return clock;
    }
}
```

This is an **illustrative class fragment**; the complete Java 17 program in Section 7 uses the lambda `() -> fixedClock` instead of a separate class.

- **Default:** the provider uses the JVM system time and default timezone when converting to local date/time.
- **Custom configuration:** can supply `Clock.fixed(...)`, `Clock.offset(...)`, or `Clock.system(ZoneId...)` as needed.
- **Testing:** a fixed clock prevents results from shifting with real date/time during CI runs.
- **Multi-timezone apps:** the clock's timezone affects how "today" is interpreted for `LocalDate`, `LocalDateTime`, or `LocalTime`; define an explicit timezone policy.
- **Custom constraints:** you can read `context.getClockProvider().getClock()` inside a custom `ConstraintValidator` to stay synchronized with the same time source.

Keep two concerns separate: `ClockProvider` determines the **comparison reference point**, while `@DateTimeFormat` and `@JsonFormat` determine **string representation** in different processing paths.

### 5.1. Example of Timezone Affecting the Current Date

The same instant `2026-11-05T23:30:00Z`:

```text
UTC                 = 2026-11-05, 23:30
Asia/Ho_Chi_Minh    = 2026-11-06, 06:30
```

If the value is `LocalDate.of(2026, 11, 5)`:

- With a UTC clock, it is **today**, passing `@PastOrPresent` and `@FutureOrPresent`.
- With an `Asia/Ho_Chi_Minh` clock, it is **yesterday**, passing `@Past` and failing `@FutureOrPresent`.

If the type is `Instant`, the same point in time keeps its timeline order regardless of timezone changes. Decide "today according to which region?" at the application boundary rather than relying on whichever timezone a server happens to have.

## 6. Equality Boundaries and Null Values

### 6.1. Checking When Equal to Present

With a fixed clock:

```java
Instant now = fixedClock.instant();
```

For that exact `now` instant:

- `@Past` **fails**, because it is not before the reference point.
- `@PastOrPresent` **passes**, because it equals the reference point.
- `@Future` **fails**, because it is not after the reference point.
- `@FutureOrPresent` **passes**, because it equals the reference point.

In a running app, creating `Instant.now()` first and calling the validator a few milliseconds later means that value is already in the past. Thus, **do not** use live requests expecting an exact equality comparison against a continuously advancing "now". To test boundary operators, fix the clock for both test input and validator.

### 6.2. All Four Constraints Accept `null`

This is a standard rule:

```java
import java.time.LocalDate;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.NotNull;

public record OptionalAndRequiredDates(
        @Future LocalDate optionalDeadline,
        @NotNull @Future LocalDate mandatoryDeadline) {}
```

- `optionalDeadline = null` is valid under `@Future`.
- `mandatoryDeadline = null` is rejected by `@NotNull`, though `@Future` reports no error.
- If a JSON request omits a field and Jackson sets it to null, whether that field errors depends on `@NotNull` and the corresponding deserialization setup.

Every temporal constraint can be combined with `groups` for context-specific use. However, groups do not replace `@NotNull`, nor do they make annotations run automatically upon object creation.

## 7. Runnable Java 17+ Program: Verifying All Four Constraints

The following example uses **Jakarta Validation API + Hibernate Validator**. Output is completely deterministic because `ValidatorFactory` is configured with `Clock.fixed`, anchored at **2026-11-05T08:00:00Z**, equivalent to **15:00 in Asia/Ho_Chi_Minh**.

### 7.1. Structure

```text
temporal-validation/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── temporal/
                    └── TemporalValidationDemo.java
```

File `pom.xml` for Java 17 and Hibernate Validator 8 (implementing Jakarta Validation 3.0):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>temporal-validation</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.hibernate.validator</groupId>
      <artifactId>hibernate-validator</artifactId>
      <version>8.0.1.Final</version>
    </dependency>
    <dependency>
      <groupId>org.glassfish</groupId>
      <artifactId>jakarta.el</artifactId>
      <version>4.0.2</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

The provider supplies standard validators; the EL dependency handles default message interpolation. In an existing Spring Boot project, let Boot's BOM manage library versions instead of copying pinned versions.

File `src/main/java/example/temporal/TemporalValidationDemo.java`:

```java
package example.temporal;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.PastOrPresent;

public final class TemporalValidationDemo {

    public record DateValues(
            @Past LocalDate beforeToday,
            @PastOrPresent LocalDate throughToday,
            @Future LocalDate afterToday,
            @FutureOrPresent LocalDate fromToday) {}

    public record InstantValues(
            @Past Instant strictlyBefore,
            @PastOrPresent Instant atOrBefore,
            @Future Instant strictlyAfter,
            @FutureOrPresent Instant atOrAfter) {}

    public record RequiredDeadline(
            @NotNull @Future LocalDate deadline) {}

    private static String invalidFields(Validator validator, Object value) {
        return validator.validate(value).stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-11-05T08:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        try (ValidatorFactory factory = Validation.byDefaultProvider()
                .configure()
                .clockProvider(() -> fixedClock)
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            LocalDate today = LocalDate.now(fixedClock);
            LocalDate yesterday = today.minusDays(1);
            LocalDate tomorrow = today.plusDays(1);
            Instant now = fixedClock.instant();

            DateValues valid = new DateValues(
                    yesterday, today, tomorrow, today);
            DateValues invalid = new DateValues(
                    today, tomorrow, today, yesterday);

            InstantValues exactBoundary = new InstantValues(
                    now, now, now, now);
            DateValues allNulls = new DateValues(
                    null, null, null, null);

            System.out.println("today=" + today);
            System.out.println("valid-date-count="
                    + validator.validate(valid).size());
            System.out.println("invalid-date-fields="
                    + invalidFields(validator, invalid));
            System.out.println("instant-boundary-fields="
                    + invalidFields(validator, exactBoundary));
            System.out.println("all-null-count="
                    + validator.validate(allNulls).size());
            System.out.println("required-null-count="
                    + validator.validate(new RequiredDeadline(null)).size());
        }
    }
}
```

Run in directory `temporal-validation`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.temporal.TemporalValidationDemo
```

**Program stdout lines** (excluding Maven/provider logs):

```text
today=2026-11-05
valid-date-count=0
invalid-date-fields=afterToday,beforeToday,fromToday,throughToday
instant-boundary-fields=strictlyAfter,strictlyBefore
all-null-count=0
required-null-count=1
```

Result analysis:

1. The clock's local date is `2026-11-05`, because 08:00Z corresponds to 15:00 in Vietnam.
2. In `valid`: yesterday passes `@Past`, today passes `@PastOrPresent`, tomorrow passes `@Future`, today passes `@FutureOrPresent`.
3. In `invalid`: every field is intentionally placed on the wrong side of the boundary; the program **sorts field names** because `Set<ConstraintViolation>` does not guarantee order.
4. For `InstantValues` where all four fields equal `now`, **only** `strictlyBefore` and `strictlyAfter` violate; the two `OrPresent` constraints allow equality.
5. When all fields are null, the four temporal constraints emit no violations.
6. `@NotNull @Future` on `deadline=null` produces exactly one violation from `@NotNull`; `@Future` is not treated as failing.
7. `try-with-resources` closes `ValidatorFactory` after use. In Spring Boot, factory lifecycle is normally managed by the framework.

**Note:** This example demonstrates direct Jakarta Validation behavior without depending on what year the server is running in. `ClockProvider` is supplied when building the factory; if you only use `LocalDate.now(fixedClock)` to prepare inputs while the validator uses the system clock, results may differ.

## 8. Verifying the Nature of "Today" in Plain Java

You can run the following example with just JDK 17+, without Maven or Jakarta Validation. Its purpose is to **verify the time basis** used by the provider, not to replace running the program in Section 7.

File `ClockBoundaryCheck.java`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class ClockBoundaryCheck {
    public static void main(String[] args) {
        Instant sameInstant = Instant.parse("2026-11-05T23:30:00Z");
        Clock utc = Clock.fixed(sameInstant, ZoneId.of("UTC"));
        Clock hcm = Clock.fixed(
                sameInstant, ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println(LocalDate.now(utc));
        System.out.println(LocalDate.now(hcm));
        System.out.println(sameInstant);
    }
}
```

```bash
javac ClockBoundaryCheck.java
java ClockBoundaryCheck
```

Stdout:

```text
2026-11-05
2026-11-06
2026-11-05T23:30:00Z
```

The two local dates differ due to timezone, while `Instant` stays unchanged. When defining "today", decide which timezone is used for validation and display across the system.

## 9. Integrating into Spring MVC / Spring Boot

In Spring Boot 3.x (Spring Framework 6.x), annotations use the `jakarta.validation` namespace. A typical MVC project needs:

```xml
<!-- Dependency fragment in a pom.xml already using Spring Boot BOM/parent -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

`starter-validation` provides the components for Spring to trigger Jakarta Validation via the provider. Having only `starter-web` is not always sufficient. When using `@Valid` on a request DTO, the framework checks constraints after data has been converted into Java types.

### 9.1. Complete Controller and DTO Example

In a Java 17+ Spring Boot 3.x project with both starters above, place `src/main/java/example/temporalweb/TemporalWebApplication.java`:

```java
package example.temporalweb;

import java.time.LocalDate;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PastOrPresent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TemporalWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(TemporalWebApplication.class, args);
    }

    public record AccountDates(
            @NotNull
            @PastOrPresent
            LocalDate birthDate,

            @NotNull
            @FutureOrPresent
            LocalDate activeFrom) {}

    @RestController
    @RequestMapping("/accounts")
    public static class AccountController {

        @PostMapping("/dates")
        public Map<String, String> create(
                @Valid @RequestBody AccountDates request) {
            return Map.of(
                    "birthDate", request.birthDate().toString(),
                    "activeFrom", request.activeFrom().toString());
        }
    }
}
```

Place the class in the specified package/path and start the server using your project's build tool:

```bash
./mvnw spring-boot:run
```

Or, for a Gradle project:

```bash
./gradlew bootRun
```

**Note:** The wrapper commands above only exist if the project actually includes the corresponding wrapper; this example must be placed inside a configured Spring Boot project.

Illustrative HTTP requests, **assuming execution occurs in November 2026** and the validator timezone is consistent:

```bash
curl -i -X POST http://localhost:8080/accounts/dates -H "Content-Type: application/json" -d '{"birthDate":"2000-01-01","activeFrom":"2030-01-01"}'
curl -i -X POST http://localhost:8080/accounts/dates -H "Content-Type: application/json" -d '{"birthDate":"2030-01-01","activeFrom":"2000-01-01"}'
```

- The first request is valid, returning HTTP **200** with JSON containing `birthDate` and `activeFrom` (key order is not guaranteed).
- The second request violates `@PastOrPresent` on `birthDate` and `@FutureOrPresent` on `activeFrom`, typically returning HTTP **400** before the controller body executes.
- The exact HTTP error payload depends on Spring Boot configuration, `@ControllerAdvice`, Problem Details, and active handlers. Do not assume error JSON always has one fixed structure.

### 9.2. Two Distinct Steps: Parse First, Then Validate

```text
JSON request
  |
  v
Jackson HttpMessageConverter -> Java LocalDate
  |                                |
  | Syntax/type error              v
  +-- 400 from deserialization   Jakarta Validator / @Valid
                                   |
                                   | @PastOrPresent / @FutureOrPresent
                                   v
                            Controller executes
```

For instance, input `"birthDate":"not-a-date"` can fail **deserialization** before constraints are evaluated. Input `"birthDate":"2030-01-01"` is syntactically valid as a date, yet **fails the temporal constraint** when the current year is 2026.

`@DateTimeFormat` controls string formatting/binding from query/path/form inputs in Spring; JSON `@RequestBody` is typically handled by Jackson (configurable via `@JsonFormat`). The four `@Past*`/`@Future*` annotations do not define string patterns. Nor does annotating a DTO cause `new AccountDates(...)` to throw automatically: validation must be executed.

If you need to return errors with `field`, `code`, and `message`, choose an appropriate `MethodArgumentNotValidException`/error response handler for your app. Do not expose sensitive data or depend on the provider's default message order.

## 10. Configuring Business Timezone in Spring Boot

For multi-server apps or multi-timezone users, "today according to which region?" for `LocalDate` should be explicitly decided. In Spring Boot **3.x**, you can configure `ClockProvider` for Bean Validation via a `ValidationConfigurationCustomizer` bean.

Snippet placed in a project `@Configuration` class:

```java
import java.time.Clock;
import java.time.ZoneId;

import org.springframework.boot.autoconfigure.validation.ValidationConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TemporalValidationConfig {

    @Bean
    ValidationConfigurationCustomizer validationClock() {
        Clock clock = Clock.system(
                ZoneId.of("Asia/Ho_Chi_Minh"));
        return configuration ->
                configuration.clockProvider(() -> clock);
    }
}
```

This is a **configuration class for a Spring Boot 3.x project**, not a standalone app. Spring Boot applies customizers when auto-configuring `ValidatorFactory`. For tests, you can swap the Clock with a test bean/configuration supplying `Clock.fixed(...)`.

**Key takeaway:** This clock configuration serves **temporal validation**. It does not automatically change Jackson serialization timezone, JVM default timezone, JDBC timezone, or how timestamps are stored in the database. Those mechanisms must be controlled separately if required by the problem.

In plain Spring Framework applications (without Boot conveniences), `LocalValidatorFactoryBean#setConfigurationInitializer(...)` allows customizing Jakarta Validation configuration, including `clockProvider`. Do not arbitrarily register multiple parallel `ValidatorFactory` beans assuming MVC will pick the exact one you want; verify actual application context wiring.

## 11. Which Temporal Type Fits Each Business Constraint?

### 11.1. Birth Date

```java
@NotNull
@PastOrPresent
private LocalDate birthDate;
```

If being born today is acceptable, `@PastOrPresent` makes sense. However, "old enough" requires comparing age from birth date and current date; "at most 120 years old" is also not guaranteed by this annotation.

### 11.2. Task Execution Time

```java
@NotNull
@Future
private Instant scheduledAt;
```

If a job must run after the current moment, `@Future` is suitable for filtering input. However, there is a **time gap** between validation and execution. A timestamp valid when the request arrived may already be in the past when the job is enqueued or committed. Therefore, the scheduler also needs policies for passed deadlines, re-checks at execution time, and appropriate retries.

### 11.3. Contract Effective Date

```java
@NotNull
@FutureOrPresent
private LocalDate effectiveFrom;
```

If a contract can take effect **today**, `@FutureOrPresent` fits. If it can only start tomorrow, choose `@Future LocalDate`. Yet if the rule is "from 09:00 today onward", you need a type containing both time and timezone; `LocalDate` does not distinguish 08:59 from 09:01.

### 11.4. Completed Record

```java
@Past
private Instant completedAt;
```

If `completedAt` can equal the processing instant, `@PastOrPresent` is semantically more accurate. If the field is optional while unfinished, allowing null is intentional; if required when closing a transaction, add `@NotNull` on the closing DTO or use an appropriate validation group.

### 11.5. Relationship Between Two Timestamps

The built-in constraints compare **each value against now**, not two fields against each other:

```java
@FutureOrPresent LocalDate startDate;
@FutureOrPresent LocalDate endDate;
```

Both fields above can be on or after today and still have `endDate < startDate`. To enforce `startDate <= endDate`, add a class-level constraint, custom validator, or service-layer check. Do not put `@Future` on `endDate` and conclude `endDate` is guaranteed to follow `startDate`.

## 12. Precision and Near-Present Edge Cases

### 12.1. `LocalDate` Differs from `Instant`

Suppose present is `2026-11-05T15:00+07:00`:

- `@Future LocalDate.of(2026,11,5)` **fails** because that is the current day.
- `@Future Instant.parse("2026-11-05T09:00:00Z")` **passes** because that corresponds to 16:00 in Vietnam, later than 15:00.
- `@PastOrPresent LocalDate.of(2026,11,5)` **passes** because today is allowed.
- `@PastOrPresent Instant.parse("2026-11-05T09:00:00Z")` **fails** because that is 16:00, later than 15:00.

All comparisons assume the same fixed 15:00 clock in the given timezone.

### 12.2. `LocalTime` and `LocalDateTime` Have Limitations

`LocalTime` **has no date**. If you want to check an appointment **tomorrow** at 08:00, `@Future LocalTime` alone can evaluate incorrectly because it compares only against **today's current time**. For real appointments, use `LocalDateTime` with a defined timezone context, or better yet `Instant`/`OffsetDateTime` when requests represent absolute instants.

`LocalDateTime` also **carries no zone/offset**. The same value `2026-11-05T10:00` in Tokyo and Hanoi represents two different instants when mapped to their respective zones. Do not assume a `LocalDateTime` can be compared globally without specifying the business timezone.

### 12.3. Daylight Saving Time (DST)

Regions like `Europe/Paris` have clock-change days; some local times do not exist or occur twice. `ZonedDateTime` carries zone rules, while `Instant` removes ambiguity for an absolute point in time. Do not convert client date/time into `LocalDateTime` and drop the zone when scheduling across countries.

### 12.4. Clock Skew and Processing Time

In distributed systems, client and server clocks can drift by milliseconds or seconds. A `@Future` constraint on a timestamp very close to the present may reject it even though the client considered it in the future. Options to handle this:

- Clearly define the server as the authoritative time source for validation.
- Design APIs with a safety margin, e.g., requiring scheduled execution time to be at least 30 seconds ahead if business rules need it.
- Base rules on server request receipt time; re-check during scheduling/dispatch.
- Hibernate Validator offers a **temporal validation tolerance** setting (`temporalValidationTolerance(Duration)`) for small drifts. This is a **Hibernate Validator extension**, not a standard attribute of the four annotations; only use it when you understand its effects and test it.

Do not invent an arbitrary tolerance window and call it the standard semantics of `@FutureOrPresent` or `@PastOrPresent`. If a rule requires "at most 5 minutes late" or "must be 24 hours ahead", it is usually better to write a validator or service rule expressing it directly.

## 13. Validation Groups, Cascading, and Trigger Mechanisms

Every Jakarta Validation constraint has `groups` and defaults to `Default`. Example:

```java
import java.time.LocalDate;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;

interface Submit {}

public record PublishRequest(
        @NotNull LocalDate preparedOn,
        @Future(groups = Submit.class) LocalDate publicationDate) {}
```

The declarations above are an **illustrative fragment**, not a standalone runnable Java class. With `@Validated(Submit.class)` at a Spring validation trigger, `@Future` in group `Submit` is evaluated; `@NotNull` on `preparedOn` in `Default` alone **does not run automatically** (unless group inheritance/sequences are designed accordingly). If you want both, use `@Validated({Default.class, Submit.class})` or an explicitly defined group structure.

When a DTO contains a child bean carrying temporal constraints:

```java
class Booking {
    @jakarta.validation.Valid
    private Schedule schedule;
}

class Schedule {
    @jakarta.validation.constraints.Future
    private java.time.Instant startsAt;
}
```

`@Valid` on the association field is a **cascade** directive so the provider descends into validating the child bean. Placing `@Future` on `Schedule.startsAt` alone will not run it if the validator only inspects `Booking` without cascading.

In Spring MVC:
- `@Valid @RequestBody Dto` or `@Validated @RequestBody Dto` usually triggers DTO validation after deserialization.
- `@Validated(Group.class)` selects groups when an endpoint needs stage-specific rules.
- `@ModelAttribute` paired with `BindingResult` placed **immediately after** the parameter handles binding/validation errors inside the controller.
- Constraints directly on handler parameters can trigger Spring MVC 6.1+'s **built-in method validation**; exceptions can differ from typical `@RequestBody` errors. Do not claim all temporal errors share a single exception class.

Validation only executes when the appropriate integration is enabled. Instantiating a DTO with `new` does not automatically check annotations.

## 14. Boundary Testing and Minimum Test Cases

When writing tests for temporal constraints, use a fixed clock and cover at least these cases:

| Scenario | What to Verify |
| --- | --- |
| Before `now` | `@Past`, `@PastOrPresent` pass; both future constraints fail |
| Equal to `now` | Both strict constraints fail; both `OrPresent` constraints pass |
| After `now` | `@Future`, `@FutureOrPresent` pass; both past constraints fail |
| `null` value | All four temporal constraints pass; `@NotNull` enforces requiredness |
| Month-end and leap years | Parse and validate `2024-02-29`, `2026-02-29` (nonexistent date) at the right stage |
| Two timezones | Same instant yields different local dates when crossing midnight |
| Proper temporal type | `LocalDate`, `Instant`, or `OffsetDateTime` matches the request contract |
| Wrong type/format in HTTP | Separate parse/binding errors from constraint errors |
| Groups and nested beans | Right group, `@Valid` cascade, without missing `Default` |
| Concurrency rules | Valid at validation time, possibly expired by DB write/job run time |

**Do not write tests relying on real `LocalDate.now()`** to assert yesterday/today/tomorrow against hardcoded date literals; tests will break over time or across CI timezones. When testing via Spring MVC, use a test configuration providing a fixed clock and ensure it is wired into the **ValidatorFactory used by MVC**.

## 15. Common Mistakes and Fixes

1. **Confusing strict with inclusive.** `@Past`/`@Future` reject values equal to the present. If today is valid, check `@PastOrPresent`/`@FutureOrPresent`.
2. **Using `@Future LocalDate` for an appointment a few hours away today.** Today is not in the future for `LocalDate`; use a time-bearing type and timezone rules.
3. **Leaving fields nullable assuming annotations forbid null.** All four constraints allow null; combine `@NotNull` when required.
4. **Putting temporal constraints on strings.** Deserialize/bind to a temporal type; type mismatch can raise a validator configuration exception rather than a normal data violation.
5. **Forgetting to standardize timezone.** Servers in different zones can see different "today" values for the same instant.
6. **Assuming `LocalDateTime` is a UTC instant.** It carries no zone/offset; pick a type with matching semantics.
7. **Testing exact equality with `Instant.now()` without fixing the clock.** "Now" advances between input construction and validation; use `Clock.fixed`.
8. **Putting `@Past` on birth date and accidentally forbidding being born today.** Choose the condition by business requirement, not annotation name.
9. **Assuming `@Future` guarantees a timestamp stays in the future until job execution.** It is a point-in-time validation check; separate execution policies are needed.
10. **Using `@FutureOrPresent` to assert two dates are ordered.** It only compares each date to now, not two fields against each other.
11. **Confusing `@DateTimeFormat`/`@JsonFormat` with temporal validation.** Formatting defines how strings parse/print; the four constraints define temporal ordering.
12. **Catching a single HTTP exception for all errors.** Parse errors, Bean Validation, and method validation take different paths.
13. **Building error codes from default messages.** Use application-defined stable codes/fields; messages may be internationalized.
14. **Relying on `@Future` as the sole safety check at the DB layer.** Temporal validity and state can change between steps; database constraints/transactions are still needed.

## 16. Practice Exercises and Answers

**Exercise 1.** A birthday form accepts `LocalDate` and allows today's date, but not tomorrow. Which constraint is needed?

**Answer:** `@PastOrPresent`. If the field is required, add `@NotNull`.

**Exercise 2.** A scheduling system uses `Instant`; execution time must be strictly after the current instant, never equal. Which to choose?

**Answer:** `@Future`. Also add a policy for time elapsing while queued.

**Exercise 3.** A contract only accepts start dates from **today onward** and stores `LocalDate`. Which annotation fits?

**Answer:** `@FutureOrPresent`; if required, combine with `@NotNull`.

**Exercise 4.** Given reference `2026-11-05` and `LocalDate.of(2026,11,5)`, what are the results of the four constraints?

**Answer:** `@Past` fails; `@PastOrPresent` passes; `@Future` fails; `@FutureOrPresent` passes.

**Exercise 5.** Why can the same instant 23:30Z be today in UTC yet tomorrow in Asia/Ho_Chi_Minh?

**Answer:** Because `LocalDate` depends on the timezone converting an instant to a date, and the validator's clock carries a zone. `Instant` does not change.

**Exercise 6.** Given `@Future LocalDate deadline`, is null valid? If the API requires a deadline, what should you do?

**Answer:** Null is valid under `@Future`; add `@NotNull` to make it required.

**Exercise 7.** Both `startDate` and `endDate` carry `@FutureOrPresent`. Does this guarantee `startDate <= endDate`?

**Answer:** No; both constraints only compare against now. A rule checking the relationship between them is required.

**Exercise 8.** A test for `@Past Instant` using `Instant.now()` fails flakily. How do you test reliably?

**Answer:** Use a `Clock.fixed` for both validator and test data, checking before/equal/after the fixed instant.

**Exercise 9.** A client sends `"2026-13-40"` to a `LocalDate` field. Is this a `@Future` constraint violation?

**Answer:** No. The invalid date string cannot deserialize into `LocalDate`; the error occurs during parsing before constraints are evaluated.

**Exercise 10.** You need to enforce "contract cannot start before 09:00 tomorrow in Hanoi". Can you use `@FutureOrPresent LocalDate` alone?

**Answer:** No. You must construct a `ZonedDateTime`/`Instant` threshold in the business timezone and compare with a specific rule; the four constraints only compare against "now", not an arbitrary threshold like that.

## 17. Implementation Takeaways

- `@Past` and `@Future` **exclude the present**; `@PastOrPresent` and `@FutureOrPresent` **include the present** per data-type semantics.
- All four constraints **accept null**. Use `@NotNull` if the field is required.
- `ClockProvider` is the source of "now"; for `LocalDate`, the zone determines the current day.
- Use `LocalDate` for **pure dates**, and `Instant`/offset-or-zone-bearing types for **instants in time**. You cannot express a specific future point in time with `LocalTime` alone.
- Parse/binding errors are a separate stage from constraint errors; Spring MVC needs `@Valid`/`@Validated` to trigger validation.
- Fixed clocks enable reliable boundary tests; deadline re-checks at execution time and two-field comparisons require separate design.

### Official References

- Jakarta Validation 3.1 – `@Past`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Past
- Jakarta Validation 3.1 – `@PastOrPresent`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/PastOrPresent
- Jakarta Validation 3.1 – `@Future`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Future
- Jakarta Validation 3.1 – `@FutureOrPresent`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/FutureOrPresent
- Jakarta Validation 3.1 – `ClockProvider`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/ClockProvider
- Jakarta Validation – specification, temporal validation: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Hibernate Validator 8 – ClockProvider and temporal tolerance: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring MVC – Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot 3.3 – `ValidationConfigurationCustomizer`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/validation/ValidationConfigurationCustomizer.html
