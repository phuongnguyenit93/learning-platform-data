# ClockProvider for Temporal Constraints in Spring Framework (Jakarta Validation)

## 1. The problem: where does “now” come from?

When using `@Past`, `@PastOrPresent`, `@Future`, or `@FutureOrPresent` to validate dates and times, the program must have a reference for **present (now)**. If validators rely directly on the server clock, the same input might be valid when a test runs and invalid a few seconds later; deploying on a server in a different time zone can also cause **date-only** values to change results around midnight.

Jakarta Bean Validation solves this through **`jakarta.validation.ClockProvider`**: a contract that supplies a `java.time.Clock` for temporal constraints to determine “now”. Spring Framework integrates Jakarta Validation through `LocalValidatorFactoryBean`, making it possible to configure a shared clock source for Spring-managed validation operations.

Practical objectives:

- Understand how `ClockProvider` affects the four temporal annotations and past/present/future boundaries.
- Actively choose the reference timestamp and time zone for runtime environments, batch jobs, or tests.
- Write a Java 17 example running with a fixed clock to verify deterministic results.
- Connect `ClockProvider` to Spring's validator, while distinguishing application-wide configuration from per-`Validator` configuration.

The examples use the **`jakarta.validation.*`** package, matching Spring Framework 6 / Spring Boot 3 and Jakarta Validation 3.x. Spring 5 / Boot 2 projects use the older **`javax.validation.*`** namespace and must choose dependencies from the same generation; avoid mixing the two namespaces.

## 2. Constraints that use the “now” reference

| Annotation | Validity condition | Is a value equal to now valid? |
| --- | --- | --- |
| `@Past` | Value is in the past | No |
| `@PastOrPresent` | Value is in the past or present | Yes |
| `@Future` | Value is in the future | No |
| `@FutureOrPresent` | Value is in the future or present | Yes |

**Key point to understand:** “now” depends on the **data type** being validated.

- For `Instant`, the comparison reference is a point on the UTC timeline; for example `2030-06-15T10:00:00Z`.
- For `LocalDate`, “today” is the **calendar date** computed from the `Clock` and its time zone. Any moment within the same day is treated as the same day when comparing as `LocalDate`.
- For `LocalDateTime`, the value is a local date-time **without offset/zone information**; the provider uses the time zone in `Clock` to determine the corresponding local “now”.
- For `Year` or `YearMonth`, the comparison granularity is the year or month, respectively. For example, `@FutureOrPresent` on `Year` accepts the entire current year.
- For `OffsetDateTime` or `ZonedDateTime`, the value carries an offset/zone; consider using these types or `Instant` if the system needs to represent actual points in time across multiple time zones.

Standard temporal constraints can also be used on some legacy types such as `java.util.Date`, `Calendar`, and the `java.time` types supported by the specification. Do not assume an arbitrary custom date-time type is supported.

**`null` is considered valid** by these standard temporal constraints. If a field must have a value, combine it with `@NotNull`:

```java
@NotNull
@Future
private Instant startsAt;
```

The snippet above only illustrates declaring a field; if `startsAt == null`, `@NotNull` is the constraint that produces the error.

## 3. The `ClockProvider` contract and configuration levels

The standard API has a simple structure:

```java
package jakarta.validation;

public interface ClockProvider {
    java.time.Clock getClock();
}
```

`getClock()` must return a non-`null` `Clock`, and the implementation must be safe when accessed concurrently by multiple threads. `java.time.Clock` provides both the **current instant** and the **time zone**. The validator uses the returned clock to evaluate temporal constraints. A default Jakarta Validation implementation uses system time and the default time zone when needed.

Several clock options:

| How `Clock` is created | Meaning | Use case |
| --- | --- | --- |
| `Clock.systemDefaultZone()` | Real time, JVM default zone | Program only operates in one controlled zone |
| `Clock.systemUTC()` | Real time, UTC zone | Backend stores and compares instants in UTC |
| `Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"))` | Real time, Vietnam zone | Rules based on the calendar date of the Vietnam market |
| `Clock.fixed(instant, zone)` | An unchanging instant, in the chosen zone | Unit/integration tests, re-running batches by logical date |
| `Clock.offset(base, duration)` | Clock shifted relative to `base` | Testing business flows with simulated time |

`ClockProvider` can be configured at the following scopes:

1. **`ValidatorFactory`:** sets the default for `Validator` instances obtained from that factory via `Configuration#clockProvider(...)`.
2. **Specific `Validator`:** overrides via `factory.usingContext().clockProvider(...).getValidator()`; other validators from the factory do not have their time source changed.
3. **Custom `ConstraintValidator`:** reads the same current reference via `ConstraintValidatorContext#getClockProvider()` instead of calling `LocalDate.now()` directly.

The same `ValidatorFactory` can produce multiple `Validator` instances with different `ClockProvider`s. However, **do not mutate a shared clock per HTTP request** inside a singleton without a design that is safe for concurrent requests.

### Distinguishing `ClockProvider` from other ways of getting time

`ClockProvider` **does not replace the entire JVM clock**. It does not automatically change the result of `Instant.now()`, `LocalDate.now()` in business code, `CURRENT_TIMESTAMP` in the database, Spring's scheduling mechanism, or timestamps issued by external systems. For consistency, inject the same `Clock` into business code that needs to compute “now”; Jakarta Validation gets its clock from the configured provider.

## 4. Standalone Java 17 example: fixing time and time zone

This example validates a reservation schedule where:

- `startsAt` must be a strictly future `Instant`;
- `bookedFor` can be today or a future date;
- `birthday` must be a date in the past;
- `finishedAt` can be the current moment or earlier.

We fix **now = 2030-06-15 10:00:00 UTC** and test the same input again with “tomorrow”, then change the zone to observe `LocalDate`.

Project structure:

```text
clock-provider-demo/
├── pom.xml
└── src/main/java/ClockProviderDemo.java
```

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>clock-provider-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>ClockProviderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`hibernate-validator` is a Jakarta Validation implementation; `jakarta.el` provides the default message interpolation foundation. The program does not need Spring to observe the exact behavior of the standard API.

### 4.2. `src/main/java/ClockProviderDemo.java`

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.PastOrPresent;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.stream.Collectors;

public class ClockProviderDemo {
    private static final Instant NOW =
            Instant.parse("2030-06-15T10:00:00Z");

    static final class Reservation {
        @Future
        Instant startsAt;

        @FutureOrPresent
        LocalDate bookedFor;

        @Past
        LocalDate birthday;

        @PastOrPresent
        Instant finishedAt;

        Reservation(Instant startsAt, LocalDate bookedFor,
                    LocalDate birthday, Instant finishedAt) {
            this.startsAt = startsAt;
            this.bookedFor = bookedFor;
            this.birthday = birthday;
            this.finishedAt = finishedAt;
        }
    }

    static final class DateOnly {
        @Future
        LocalDate date;

        DateOnly(LocalDate date) {
            this.date = date;
        }
    }

    // Sort property paths so stdout does not depend on
    // the iteration order of Set<ConstraintViolation<?>>.
    private static String invalidFields(Validator validator, Object bean) {
        return validator.validate(bean).stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        Clock fixedUtc = Clock.fixed(NOW, ZoneOffset.UTC);

        try (ValidatorFactory factory =
                 Validation.byDefaultProvider()
                         .configure()
                         .clockProvider(() -> fixedUtc)
                         .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Reservation valid = new Reservation(
                    NOW.plusSeconds(1),
                    LocalDate.of(2030, 6, 15),
                    LocalDate.of(2000, 1, 1),
                    NOW
            );

            Reservation invalid = new Reservation(
                    NOW,                             // @Future: equal to now
                    LocalDate.of(2030, 6, 14),      // yesterday
                    LocalDate.of(2030, 6, 15),      // @Past: equal to today
                    NOW.plusSeconds(1)               // @PastOrPresent: in the future
            );

            System.out.println("Valid: " + invalidFields(validator, valid));
            System.out.println("Invalid: " + invalidFields(validator, invalid));

            // Only this validator uses logical date 2030-06-16.
            Clock nextDayClock =
                    Clock.fixed(NOW.plusSeconds(24 * 60 * 60), ZoneOffset.UTC);
            Validator nextDayValidator = factory.usingContext()
                    .clockProvider(() -> nextDayClock)
                    .getValidator();
            System.out.println(
                    "Next day: " + invalidFields(nextDayValidator, valid)
            );

            // Same instant, two zones give two different calendar dates.
            Instant nearMidnight =
                    Instant.parse("2030-06-15T23:30:00Z");
            Clock utc = Clock.fixed(nearMidnight, ZoneOffset.UTC);
            Clock hcm = Clock.fixed(
                    nearMidnight, ZoneId.of("Asia/Ho_Chi_Minh")
            );
            DateOnly june16 = new DateOnly(LocalDate.of(2030, 6, 16));

            Validator utcValidator = factory.usingContext()
                    .clockProvider(() -> utc)
                    .getValidator();
            Validator hcmValidator = factory.usingContext()
                    .clockProvider(() -> hcm)
                    .getValidator();

            System.out.println(
                    "Date at UTC: " + invalidFields(utcValidator, june16)
            );
            System.out.println(
                    "Date at HCM: " + invalidFields(hcmValidator, june16)
            );
        }
    }
}
```

Run in the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Expected program stdout** (excluding Maven or provider logs if written to another stream):

```text
Valid: []
Invalid: [birthday, bookedFor, finishedAt, startsAt]
Next day: [bookedFor, startsAt]
Date at UTC: []
Date at HCM: [date]
```

**Line-by-line explanation:**

- `Valid: []`: all four fields satisfy the four constraints at exact reference `NOW`.
- `Invalid: [...]`: each field violates a boundary. `@Future` **does not accept** `startsAt == NOW`; `@Past` **does not accept** a birthday matching the current date; `@PastOrPresent` does not accept an instant after now.
- `Next day: [bookedFor, startsAt]`: the exact same `valid` object is no longer valid on two fields when the logical reference moves to June 16. The other conditions remain valid. Overriding `ValidatorContext` does not alter the factory's default validator.
- `Date at UTC: []`: at `2030-06-15T23:30:00Z`, the date in UTC is still **June 15**; **June 16** is in the future.
- `Date at HCM: [date]`: that same instant is **06:30 on June 16** in `Asia/Ho_Chi_Minh`; `@Future LocalDate` does not accept the current date itself.

The example outputs **sorted field names**, independent of the unguaranteed iteration order of the `ConstraintViolation` set. A fixed clock keeps tests independent of the machine date when run and particularly stable around date boundaries.

### Why choose both `Instant` and `LocalDate`?

`Instant` represents an absolute point in time, suitable for release schedules, UTC deadlines, token expiry, or transaction start times. `LocalDate` represents a calendar date, suitable for birthdays, booking dates, and business dates. When using `LocalDate`, business rules must specify **which region's date** applies (UTC, user, or branch); simply saying “today” without choosing a zone can cause bugs.

If the input is a plain `LocalTime`, future/past comparison may not match the intent of “tomorrow at 01:00”, because the data carries no date. Use `LocalDateTime` with an explicitly managed zone, `ZonedDateTime`, or `Instant` depending on the nature of the appointment.

## 5. Configuring `ClockProvider` in Spring Framework

Spring provides `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` to initialize the Jakarta Validation provider and expose `Validator` in the ApplicationContext. With Spring Framework 6.x, you can customize factory configuration using `setConfigurationInitializer(...)`.

The snippet below is **for a Spring application with Bean Validation support** (such as Spring Boot 3 with `spring-boot-starter-validation`), not a standalone Java program:

```java
import java.time.Clock;
import java.time.ZoneId;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class BeanValidationClockConfig {
    @Bean
    Clock applicationClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }

    @Bean
    LocalValidatorFactoryBean validator(Clock applicationClock) {
        LocalValidatorFactoryBean factory = new LocalValidatorFactoryBean();
        factory.setConfigurationInitializer(
                configuration -> configuration.clockProvider(
                        () -> applicationClock
                )
        );
        return factory;
    }
}
```

Here:

1. `applicationClock` is a bean that can be injected into business services to compute the current date consistently.
2. `LocalValidatorFactoryBean` passes the same clock into Jakarta Validation's temporal validators.
3. When Spring MVC uses this exact validator bean to process `@Valid @RequestBody` or other validation calls, `@Past` and `@Future` will reference the configured `ClockProvider`.
4. In test environments, you can replace the `Clock` bean with `Clock.fixed(...)` to simulate any date and point in time.

Example DTO in a Spring MVC application:

```java
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;

public record CreateReservationRequest(
        @NotNull @Future Instant startsAt
) {}
```

A controller can accept `@Valid @RequestBody CreateReservationRequest`. When `startsAt` is not in the future according to the configured clock, Jakarta Validation creates a `ConstraintViolation`; Spring MVC typically turns this `@Valid @RequestBody` error into HTTP 400 through its default validation handling mechanism. The error JSON shape depends on the project's exception handler configuration.

**Note on configuration paths:** if the project explicitly declares multiple validators, a custom MVC `WebMvcConfigurer#getValidator()`, or per-binder validators, you must verify which instance is actually being used. Merely having a `Clock` bean or a `ClockProvider` bean in the context **does not automatically prove** that every validator is configured to use it; the code above passes the provider into the factory explicitly.

### When do you need to override an individual `Validator`?

A batch reprocessing transactions from June 15 might need to treat “today” as June 15 even though the server has moved on to June 17. In this case, use `factory.usingContext().clockProvider(...)` as in the standalone example to create a dedicated validator with the appropriate logical date for the job. Avoid mutating application-wide clock state when handling concurrent requests from multiple tenants or time zones.

## 6. Using `ClockProvider` in custom temporal constraints

Not every temporal rule has a built-in annotation. Suppose you need a delivery date **no earlier than two days from today**. Inside the `ConstraintValidator` of a custom annotation, you must obtain the clock from the context to respect the same test and production configuration.

The following snippet is **the body of a `ConstraintValidator<YourConstraint, LocalDate>`**, not a standalone class:

```java
@Override
public boolean isValid(
        LocalDate deliveryDate,
        ConstraintValidatorContext context) {

    if (deliveryDate == null) {
        return true; // Use @NotNull separately if the field is required.
    }

    Clock clock = context.getClockProvider().getClock();
    LocalDate today = LocalDate.now(clock);
    LocalDate earliestAllowed = today.plusDays(2);

    return !deliveryDate.isBefore(earliestAllowed);
}
```

Required imports: `java.time.Clock`, `java.time.LocalDate`, and `jakarta.validation.ConstraintValidatorContext`. In custom validators, calling `LocalDate.now()` **with no arguments** bypasses `ClockProvider`, causing the same test to potentially use two different time references. If the rule is “48 hours” rather than “two calendar days”, compare `Instant`/`Duration` with duration semantics instead of using `LocalDate.plusDays(2)`.

## 7. Distinguishing clock, zone, duration, and tolerance

### 7.1. Instant stays the same while calendar date can differ

A UTC instant represented by `2030-06-15T23:30:00Z` corresponds to 06:30 on June 16 in Vietnam. With `@Future` on `Instant`, the two zones do not change the compared instant itself. With `@Future` on `LocalDate`, the current value **depends on the zone**, so the results can differ as shown in the example.

When building multi-country APIs, specify whether “today” belongs to the user, branch, or organization. Do not assume the server's zone matches the business meaning.

### 7.2. Difference between a day and a 24-hour span

`LocalDate.plusDays(1)` is the **next calendar day**. In zones with daylight saving time, a calendar day can be 23 or 25 hours long. Meanwhile, `Instant.plus(Duration.ofHours(24))` always adds 24 absolute hours. Choose the right data type: “before the next business day” is a calendar rule; “expires after 24 hours” is a duration rule.

### 7.3. Tolerance when servers have clock skew

In distributed systems, requests arriving a few milliseconds late and clock skew can cause boundary comparisons to fail. Hibernate Validator provides a **temporal validation tolerance** extension (for example, the `temporalValidationTolerance(Duration.ofMillis(...))` API or `hibernate.validator.temporal_validation_tolerance` property) to configure tolerance for temporal constraints. This is a **Hibernate Validator provider feature**, not a property of the standard `ClockProvider` interface, and it does not replace clock synchronization or defining exact business boundaries.

## 8. Testing critical edge cases

A test suite for temporal DTOs or validators should cover:

| Scenario | What to verify |
| --- | --- |
| Value one small unit before reference | `@Past` is valid; `@Future` is invalid |
| Value **equal to** reference | Constraints with `OrPresent` are valid; strict constraints are invalid |
| Value one small unit after reference | `@Future` is valid; `@Past` is invalid |
| `null` | Temporal constraint creates no error; `@NotNull` creates an error if present |
| Timestamp near 00:00 UTC | `LocalDate` result is determined by the business zone |
| Calculations across DST | Calendar days and 24-hour spans are handled by the right data type |
| Reprocess job by logical date | Dedicated validator uses the right clock even when the server is on another day |
| Multiple threads / concurrent requests | Provider does not change state or leak clocks across requests |

Stable testing approach: use `Clock.fixed(Instant.parse("..."), ZoneId.of("..."))`; construct boundary data using `plusSeconds(1)` / `minusSeconds(1)` or `plusDays(1)` depending on the type. Do not write tests with `Instant.now()` expecting a subsequent check to see the same “now”: the system clock keeps ticking and boundaries can drift between two calls.

### Common design mistakes

1. **Not configuring a zone when validating dates:** `LocalDate` may differ from business “today”.
2. **Calling `LocalDate.now()` in a custom validator:** ignores the test's simulated clock.
3. **Using `@Future` for a timestamp allowed to be “right now”:** `@Future` is strict; consider `@FutureOrPresent`.
4. **Forgetting `@NotNull`:** an input missing the date/time still passes temporal constraints.
5. **Registering a `Clock` bean and assuming the validator uses it automatically:** you must configure the `ClockProvider` of the executing factory/validator.
6. **Mutating a global singleton per request:** can cause incorrect results across threads; use a dedicated context or explicit data/zone design.
7. **Using `LocalTime` for a schedule that has a date:** lacking date information can make “future” contextually wrong.
8. **Using `Clock.fixed` in production unintentionally:** date and time stop advancing; most real data will eventually fail temporal conditions.
9. **Mixing Jakarta and javax APIs:** an annotation using the wrong namespace may not be processed as expected by the current stack.
10. **Confusing the validation clock with the database clock:** the two systems may use different clock references, causing races on operations near deadlines.

## 9. Checklist for applying in a Spring project

- [ ] Choose the right semantics: absolute instant, calendar date, month/year, or duration.
- [ ] Specify the exact zone for date-based rules.
- [ ] Pick `@Past` / `@PastOrPresent` / `@Future` / `@FutureOrPresent` with the right boundary.
- [ ] Use `@NotNull` if the input is required.
- [ ] Supply the clock to `LocalValidatorFactoryBean` via `setConfigurationInitializer`, or configure `ValidatorFactory` appropriately outside Spring.
- [ ] Inject `Clock` for business logic that computes “now” and obtain the clock from context in custom `ConstraintValidator`s.
- [ ] Test with a fixed clock, covering equal-to-reference boundaries, near midnight, different zones, and batch logical dates.
- [ ] Verify that HTTP/API endpoints actually use the configured validator.

**Core principle:** `ClockProvider` makes “present” in Jakarta Validation a controlled dependency. By explicitly choosing `Clock`/zone, wiring the right Spring validator, and testing with a fixed clock, temporal constraints produce explainable and reproducible results.

## References

- [Jakarta Validation Specification 3.1 — Temporal constraint validators and ClockProvider](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html)
- [Jakarta Validation API 3.1 — ClockProvider](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/ClockProvider.html)
- [Spring Framework 6.2 — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework — Java Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Hibernate Validator — Reference Guide, ClockProvider and temporal validation tolerance](https://docs.hibernate.org/stable/validator/reference/en-US/html_single/)
