# Testing Time-Dependent Validation with ClockProvider or a Fixed Clock in Spring Validation

## 1. Problem: a test that passes today but fails tomorrow

Consider a DTO for scheduling a booking:

```java
public record BookingRequest(
        @Future Instant startsAt) {
}
```

This is a fragment requiring imports for `jakarta.validation.constraints.Future` and `java.time.Instant`. Today a test passing `startsAt=2030-01-15T12:00:00Z` might pass, yet once real time passes that date, the exact same input will fail. Another test using `LocalDate.now()` to build fixtures can flake around midnight, especially on CI running in a different time zone than a developer's machine.

Common causes of flaky time-based tests include:

- Calling `Instant.now()`, `LocalDate.now()`, or `System.currentTimeMillis()` directly inside logic or assertions.
- Real time advancing while the test prepares the request, validation runs, and the service executes.
- `@Future`/`@Past` comparing against Jakarta Validation's clock while the business service checks a different clock.
- The JVM using different default time zones across local machines, CI, and deployment environments.
- Testing exact boundary times such as "today", "in the future", or "at least 30 minutes before start" without clarifying whether the boundary is inclusive or exclusive.
- Two checks in different layers calling `now()` at slightly different instants, producing irreproducible failures.
- A library configuring a custom temporal tolerance or ClockProvider while tests only swap Spring's `Clock` bean.
- Test code mutating the JVM-wide default time zone, affecting tests running in parallel.

**Solution:** introduce "now" into the system as an explicit dependency. For Jakarta temporal constraints, use `jakarta.validation.ClockProvider`; for business code, inject `java.time.Clock`. In tests, create `Clock.fixed(...)` and ensure both the validator and the service use that clock.

This lesson belongs to the **Testing** section of the **Spring Framework — validation-data-binding** module, using Java 17+, Jakarta Validation 3, Spring Framework 6, and Spring Boot 3.x. Examples include unit tests, MockMvc integration tests, UTC dates, and boundary verification.

## 2. Three concepts to distinguish

| Concept | API | Role |
| --- | --- | --- |
| Java clock | `java.time.Clock` | Provides current instant and time zone; used in business logic and tests |
| Jakarta Validation clock | `jakarta.validation.ClockProvider` | Supplies a `Clock` to temporal constraints such as `@Past` and `@Future` |
| Validator initialization | `jakarta.validation.Configuration#clockProvider(...)` or Boot customizer | Binds the ClockProvider to the `ValidatorFactory` actually used for validation |

### 2.1. java.time.Clock

`Clock` is Java's built-in abstraction, offering factory methods:

```java
Clock realClock = Clock.systemUTC();

Clock frozenClock = Clock.fixed(
        Instant.parse("2030-01-15T12:00:00Z"),
        ZoneOffset.UTC
);

Instant now = frozenClock.instant();
LocalDate today = LocalDate.now(frozenClock);
```

This is a Java fragment requiring `java.time.*` imports.

- `Clock.systemUTC()` reads system time in the UTC zone.
- `Clock.systemDefaultZone()` reads system time in the JVM's default zone.
- `Clock.fixed(instant, zone)` always returns the exact same instant, ideal for deterministic testing.
- `Clock.offset(baseClock, duration)` shifts the base clock's time; if the base is a system clock, time **still advances**, so it is not frozen.
- `Clock.tick(baseClock, duration)` truncates time to a tick duration; if the base advances, this is **not** a fixed clock either.

In tests requiring identical values across multiple calls, use `Clock.fixed`.

### 2.2. Jakarta ClockProvider

`ClockProvider` is the interface:

```java
@FunctionalInterface
public interface ClockProvider {
    Clock getClock();
}
```

This is an **abbreviated signature** to explain the API, not code you need to declare; the real interface is `jakarta.validation.ClockProvider`. It supplies a `Clock` to temporal validators. Implementations must be **thread-safe** because the validator factory/validator is used concurrently, and `getClock()` must never return null.

The Jakarta Bean Validation default uses the system clock with the default time zone. When tests do not override it, annotations evaluate against real current time, depending on the run date and environment.

### 2.3. Four common temporal annotations

| Constraint | Condition against reference time | Boundary |
| --- | --- | --- |
| `@Past` | Value is **before** now | Strict, excludes now |
| `@PastOrPresent` | Value is before **or at** now | Inclusive |
| `@Future` | Value is **after** now | Strict, excludes now |
| `@FutureOrPresent` | Value is after **or at** now | Inclusive |

These annotations support standard temporal types such as `Instant`, `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime`, and `YearMonth` (exact scope defined by the Jakarta Validation spec).

**Key point:** the notion of "present" depends on the data type. For `LocalDate`, **all of today** counts as present; for `YearMonth`, all of the current month counts as present. Do not interpret `@Future LocalDate` as "any time later today"; it requires **a date after today** in the ClockProvider's zone.

### 2.4. Null is not a temporal error

In Bean Validation, temporal constraints generally treat `null` as valid to separate presence checks from temporal conditions. If input is required, combine them:

```java
@NotNull
@Future
private Instant startsAt;
```

This is a field fragment requiring `jakarta.validation.constraints.NotNull` and `Future`. With `@Future` alone, a null value may **produce no violation**. Never use a test asserting "missing field is rejected" as proof that `@Future` implies `@NotNull`.

## 3. Where does ClockProvider get "now" in the Spring MVC pipeline?

For a JSON request:

```text
POST /bookings
Content-Type: application/json
            |
            v
HttpMessageConverter (Jackson) creates BookingRequest
            |
            v
@Valid / Spring MVC validation adapter
            |
            v
Jakarta Validator from ValidatorFactory
            |
            +-- ClockProvider.getClock()
            |
            +-- @Future / @Past / @FutureOrPresent
            |
            v
MethodArgumentNotValidException if constraints fail
            |
            v
RestControllerAdvice converts to HTTP 400
```

Only if validation succeeds does the controller call the service. The service may enforce its own rule such as "bookings must be made at least 30 minutes before start time". If the service calls `Instant.now()` directly, **ClockProvider does not control that value**; you must inject `Clock` into the service.

### One Clock for both places

Desired design:

```text
                Clock bean
                 /      \
                v        v
       ClockProvider   BookingService
             |             |
             v             v
       @Future/@Past   lead-time rule
```

In tests, swap the `Clock` bean with `Clock.fixed(...)`; both the validator and the service receive the exact same time source. In production, a `Clock.systemUTC()` bean provides real time.

**Note on scope:** configuring ClockProvider on a `ValidatorFactory` affects only validators obtained from that factory. It does not alter `Clock.systemUTC()`, `Instant.now()`, another `ValidatorFactory`, database `CURRENT_TIMESTAMP`, or external systems.

## 4. Comparisons must define exact boundaries

Pick a fixed instant:

```text
Reference now = 2030-01-15T12:00:00Z
Zone = UTC
Today = 2030-01-15
```

Expected results, **when no temporal tolerance is configured**:

| Constraint and type | Input | Result |
| --- | --- | --- |
| `@Future Instant` | `2030-01-15T11:59:59Z` | Invalid |
| `@Future Instant` | `2030-01-15T12:00:00Z` | Invalid: equals now |
| `@Future Instant` | `2030-01-15T12:00:01Z` | Valid |
| `@Past Instant` | `2030-01-15T11:59:59Z` | Valid |
| `@Past Instant` | `2030-01-15T12:00:00Z` | Invalid: equals now |
| `@PastOrPresent Instant` | `2030-01-15T12:00:00Z` | Valid |
| `@FutureOrPresent Instant` | `2030-01-15T12:00:00Z` | Valid |
| `@Future LocalDate` | `2030-01-15` | Invalid: today |
| `@Future LocalDate` | `2030-01-16` | Valid |
| `@Past LocalDate` | `2030-01-14` | Valid |
| `@Past LocalDate` | `2030-01-15` | Invalid |
| `@FutureOrPresent LocalDate` | `2030-01-15` | Valid |
| `@PastOrPresent YearMonth` | `2030-01` | Valid |

The date **2030-01-15** here is simply a fixture for this lesson, not today's real date. Fixing this timestamp keeps tests from expiring.

### @Future is not an "at least 30 minutes ahead" rule

With `@Future`, a timestamp one second after `now` is valid. Business rules may require booking at least 30 minutes ahead:

```java
Instant deadline = clock.instant().plus(Duration.ofMinutes(30));

if (request.startsAt().isBefore(deadline)) {
    throw new BookingTooSoonException();
}
```

This is a service fragment. It allows **exactly 30 minutes** and rejects anything less than 30 minutes. If the requirement is **strictly more than 30 minutes**, replace `isBefore(deadline)` with `!isAfter(deadline)`. State the boundary's equality semantics explicitly rather than leaving off-by-one ambiguity to natural-language phrasing.

## 5. Configuring ClockProvider when testing Jakarta Validator directly

No Spring context is needed to test a plain constraint:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2030-01-15T12:00:00Z"),
        ZoneOffset.UTC
);

try (ValidatorFactory factory = Validation
        .byDefaultProvider()
        .configure()
        .clockProvider(() -> fixed)
        .buildValidatorFactory()) {

    Validator validator = factory.getValidator();
    // validator.validate(dto)
}
```

This is a fragment requiring `java.time.*` and `jakarta.validation.*` imports. Jakarta's `Configuration#clockProvider(...)` accepts a `ClockProvider`. The factory is closed after the test to release resources.

**Why is this better than sleep?** It does not depend on machine speed, CI speed, scheduling, or midnight rollovers. Tests can check inputs immediately before, equal to, and immediately after the reference instant.

### Do not confuse the two Validator types

- `jakarta.validation.Validator` has `validate(...)` returning `Set<ConstraintViolation<T>>`.
- `org.springframework.validation.Validator` uses `supports(...)` and `validate(Object, Errors)`.
- `LocalValidatorFactoryBean` in Spring integrates both Jakarta validation and the Spring validation adapter.

When building `Validation.buildDefaultValidatorFactory()` manually, do not assume it replaces the validator used by MVC inside the application context. That is a separate factory; to make MockMvc use a fixed clock, configure Spring MVC's factory/validator.

## 6. Spring Boot integration: ValidationConfigurationCustomizer

Spring Boot 3.x provides `org.springframework.boot.autoconfigure.validation.ValidationConfigurationCustomizer`. When a Bean Validation provider and Boot auto-configuration are active, this bean lets you customize `jakarta.validation.Configuration<?>` before building the `ValidatorFactory`.

Conceptual example:

```java
@Bean
ValidationConfigurationCustomizer useClock(Clock clock) {
    return config -> config.clockProvider(() -> clock);
}
```

If the app registers a single `Clock` bean and the validator is auto-configured normally by Boot, built-in temporal constraints will use the injected clock.

**Major testing benefit:** simply replace the `Clock` bean with a fixed version in the test context; `ValidationConfigurationCustomizer` references that same Clock bean, and the service receives it via constructor injection too.

**Important limitations:**

- The customizer affects the factory created by **Boot validation auto-configuration**. If the app declares an independent `LocalValidatorFactoryBean` bypassing Boot auto-config, configure the clock on that factory directly.
- `@WebMvcTest` has its own test slice and bean scanning; do not assume every production `@Configuration` and `Clock` bean is automatically imported. Test wiring explicitly.
- `MockMvcBuilders.standaloneSetup(...)` does not load the Boot application context; pass a customized validator to standalone setup when needed.
- If an app defines multiple `ValidatorFactory` beans, a single customizer will not automatically govern all of them.
- A customizer placed in a **test-only profile** must never leak into production.

### Configuring LocalValidatorFactoryBean directly

In Spring Framework 6.x, `LocalValidatorFactoryBean#setConfigurationInitializer(...)` lets you hook into Bean Validation Configuration:

```java
LocalValidatorFactoryBean factory =
        new LocalValidatorFactoryBean();

factory.setConfigurationInitializer(
        config -> config.clockProvider(() -> fixedClock));

factory.afterPropertiesSet();
// factory.validate(dto) or use as a Spring Validator.
factory.destroy();
```

This is a fragment assuming `fixedClock` already exists, not a complete production bean. When managing the lifecycle manually, call destroy/close. Inside a Spring context, bean lifecycle is normally managed by the container.

**Avoid creating two competing ValidatorFactory beans:** if you declare a custom bean, verify Spring MVC actually uses it. Direct factory tests passing while MVC uses a default factory prove nothing about parity.

## 7. Runnable project: Spring MVC booking with one clock for validation and service

We will build a small Maven application using:

- `Clock.systemUTC()` in production.
- `ValidationConfigurationCustomizer` to expose the Clock as a `ClockProvider` for Jakarta temporal validation.
- `@Valid @RequestBody` with `@Future`, `@FutureOrPresent`, `@Past`, and `@NotNull`.
- A business rule: bookings must be made **at least 30 minutes** ahead.
- `@SpringBootTest + @AutoConfigureMockMvc` swapping Clock for `Clock.fixed(...)` in the test context.
- A separate unit test building a `ValidatorFactory` from Jakarta Configuration and ClockProvider to verify boundaries.
- Error responses returning stable codes for validation and business errors without copying raw exceptions.

**Intentional simplifications:** no database, real schedule store, authentication, or seat availability checks. A 201 response in the demo only confirms clock-based constraint/lead-time evaluation. Production code needs transactions, availability/business concurrency, and authorization separately.

### 7.1. Directory structure

```text
clock-validation-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ClockValidationApplication.java
    │   ├── ClockConfiguration.java
    │   ├── BookingRequest.java
    │   ├── BookingService.java
    │   ├── BookingController.java
    │   └── ApiErrorAdvice.java
    └── test/java/demo/
        ├── TemporalConstraintUnitTest.java
        └── BookingMvcTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>clock-validation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

The Spring Boot parent manages versions of Spring MVC, Jackson Java Time, and Hibernate Validator. `spring-boot-starter-validation` must be declared to include the Bean Validation implementation.

### 7.3. src/main/java/demo/ClockValidationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ClockValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ClockValidationApplication.class, args);
    }
}
```

### 7.4. src/main/java/demo/ClockConfiguration.java

```java
package demo;

import java.time.Clock;

import org.springframework.boot.autoconfigure.validation
        .ValidationConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean
    public Clock applicationClock() {
        // Choose UTC intentionally to avoid depending on JVM timezone.
        return Clock.systemUTC();
    }

    @Bean
    public ValidationConfigurationCustomizer
            validationClockCustomizer(Clock clock) {
        // Jakarta ClockProvider is a functional interface.
        return configuration ->
                configuration.clockProvider(() -> clock);
    }
}
```

This is the **production configuration**, scanned automatically because it shares package `demo`. The `ValidationConfigurationCustomizer` import can be placed on a single line in an IDE (breaking between the qualified package and class name here is valid Java lexical whitespace after a dot). If your code formatter dislikes that style, combine it into a single import line.

Configuration wiring path:

1. Boot creates the `Clock applicationClock` bean returning real UTC time.
2. Boot creates `ValidationConfigurationCustomizer`, receiving Clock via DI.
3. Boot uses the customizer to register `ClockProvider` on the Bean Validation factory used by Spring MVC.
4. `BookingService` is also injected with that same Clock.
5. In tests, a `@Primary` fixed `Clock` overrides the production Clock.

Never use `TimeZone.setDefault(...)` or alter the global JVM timezone for tests, as those changes can affect other tests.

### 7.5. src/main/java/demo/BookingRequest.java

```java
package demo;

import java.time.Instant;
import java.time.LocalDate;

import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Past;

public record BookingRequest(

        @NotBlank
        String guestName,

        @NotNull
        @Future
        Instant startsAt,

        @NotNull
        @FutureOrPresent
        LocalDate checkInDate,

        @NotNull
        @Past
        LocalDate birthDate
) {
}
```

Three temporal conditions:

- `@Future Instant startsAt`: start instant must be **after** the ClockProvider instant.
- `@FutureOrPresent LocalDate checkInDate`: check-in date must not be before **today in the ClockProvider's zone**.
- `@Past LocalDate birthDate`: birth date must be before **today**, excluding today.
- `@NotNull` is added to each required field because temporal constraints do not require a field to be non-null.
- `@NotBlank` requires `guestName` to have non-whitespace text.

In a real application, you might not need both `startsAt` and `checkInDate` on the same request; the example keeps both to contrast Instant and LocalDate in tests. If a system requires the date to agree with the Instant and hotel timezone, add dedicated **cross-field business validation**.

### 7.6. src/main/java/demo/BookingService.java

```java
package demo;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.stereotype.Service;

@Service
public class BookingService {

    private final Clock clock;

    public BookingService(Clock clock) {
        this.clock = clock;
    }

    public record Receipt(
            String status,
            Instant acceptedAt,
            Instant startsAt) {
    }

    public static final class BookingTooSoon
            extends RuntimeException {
    }

    public Receipt book(BookingRequest request) {
        Instant now = clock.instant();

        Instant earliest =
                now.plus(Duration.ofMinutes(30));

        // Allow exactly 30 minutes; reject only earlier.
        if (request.startsAt().isBefore(earliest)) {
            throw new BookingTooSoon();
        }

        return new Receipt(
                "ACCEPTED",
                now,
                request.startsAt()
        );
    }
}
```

**This is business validation, not `@Future`.** If `startsAt=2030-01-15T12:00:01Z` with the clock frozen at `12:00:00Z`, Jakarta `@Future` passes, while BookingService rejects it because 30 minutes have not elapsed.

The service avoids static `Instant.now()`, so the same injected Clock bean governs both validation and business logic. This also keeps timezone-shift, near-boundary, and retry tests reproducible.

In production, a service method runs **after** MVC validation has already checked the input; real time advances between the two steps. That is real-world behavior to handle by contract (e.g., lead-time margin, persisting the committed deadline in a transaction), rather than pretending both checks always read the exact same instant. A fixed Clock helps test logic, while other integration tests should verify live runtime behavior where appropriate.

### 7.7. src/main/java/demo/BookingController.java

```java
package demo;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookingController {

    private final BookingService service;

    public BookingController(BookingService service) {
        this.service = service;
    }

    @PostMapping("/bookings")
    public ResponseEntity<BookingService.Receipt> create(
            @Valid @RequestBody BookingRequest request) {

        BookingService.Receipt receipt =
                service.book(request);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(receipt);
    }
}
```

The controller does not call `LocalDate.now()` or `Instant.now()`. It simply receives the DTO, triggers Bean Validation, and delegates business logic to the service. Constraint failures are handled via `MethodArgumentNotValidException` in Spring MVC; undecodable JSON requests are handled separately by the HTTP message converter.

### 7.8. src/main/java/demo/ApiErrorAdvice.java

```java
package demo;

import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    public record ApiError(
            String code,
            String message,
            List<String> fields) {
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<String> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return new ResponseEntity<>(
                new ApiError(
                        "TEMPORAL_INPUT_INVALID",
                        "Request has invalid fields",
                        fields
                ),
                headers,
                status
        );
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return new ResponseEntity<>(
                new ApiError(
                        "UNREADABLE_BODY",
                        "Request body cannot be decoded",
                        List.of()
                ),
                headers,
                status
        );
    }

    @ExceptionHandler(BookingService.BookingTooSoon.class)
    public ResponseEntity<ApiError> tooSoon() {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "BOOKING_TOO_SOON",
                        "Book at least 30 minutes ahead",
                        List.of("startsAt")
                ));
    }
}
```

Three **distinct** error types:

- `TEMPORAL_INPUT_INVALID`: one or more constraints on `BookingRequest` failed, HTTP 400.
- `UNREADABLE_BODY`: JSON has syntax/type errors that Jackson cannot deserialize, HTTP 400.
- `BOOKING_TOO_SOON`: request passed `@Future` but failed the service's lead-time rule, HTTP 409 per demo contract.

Do not copy raw `FieldError#getRejectedValue()`, Java exceptions, or stack traces into the response. Production apps can emit per-field codes like `START_MUST_BE_FUTURE` and `DATE_MUST_NOT_BE_PAST` with localized messages via `MessageSource`. The key lesson point is that ClockProvider affects **validation outcomes**, not status/code mapping itself.

## 8. ClockProvider unit tests: @Past and @Future with deterministic boundaries

### 8.1. src/test/java/demo/TemporalConstraintUnitTest.java

```java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.PastOrPresent;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TemporalConstraintUnitTest {

    private static final Instant NOW =
            Instant.parse("2030-01-15T12:00:00Z");

    private static final Clock FIXED =
            Clock.fixed(NOW, ZoneOffset.UTC);

    record Probe(
            @Past Instant occurredAt,
            @Future Instant dueAt,
            @FutureOrPresent LocalDate checkInDate,
            @PastOrPresent LocalDate historicalDay) {
    }

    private Set<String> invalidFields(Probe probe) {
        try (ValidatorFactory factory = Validation
                .byDefaultProvider()
                .configure()
                .clockProvider(() -> FIXED)
                .buildValidatorFactory()) {

            return factory.getValidator()
                    .validate(probe)
                    .stream()
                    .map(violation ->
                            violation.getPropertyPath().toString())
                    .collect(Collectors.toSet());
        }
    }

    @Test
    void exactNowFailsStrictPastAndFuture() {
        Probe probe = new Probe(
                NOW,
                NOW,
                LocalDate.of(2030, 1, 15),
                LocalDate.of(2030, 1, 15));

        assertEquals(
                Set.of("occurredAt", "dueAt"),
                invalidFields(probe));
    }

    @Test
    void strictPastAndFutureAcceptOneSecondDistance() {
        Probe probe = new Probe(
                NOW.minusSeconds(1),
                NOW.plusSeconds(1),
                LocalDate.of(2030, 1, 15),
                LocalDate.of(2030, 1, 15));

        assertTrue(invalidFields(probe).isEmpty());
    }

    @Test
    void futureOrPresentDateAcceptsToday() {
        Probe probe = new Probe(
                NOW.minusSeconds(1),
                NOW.plusSeconds(1),
                LocalDate.of(2030, 1, 15),
                LocalDate.of(2030, 1, 14));

        assertTrue(invalidFields(probe).isEmpty());
    }

    @Test
    void yesterdayFailsFutureOrPresentDate() {
        Probe probe = new Probe(
                NOW.minusSeconds(1),
                NOW.plusSeconds(1),
                LocalDate.of(2030, 1, 14),
                LocalDate.of(2030, 1, 14));

        assertEquals(
                Set.of("checkInDate"),
                invalidFields(probe));
    }

    @Test
    void tomorrowFailsPastOrPresentDate() {
        Probe probe = new Probe(
                NOW.minusSeconds(1),
                NOW.plusSeconds(1),
                LocalDate.of(2030, 1, 15),
                LocalDate.of(2030, 1, 16));

        assertEquals(
                Set.of("historicalDay"),
                invalidFields(probe));
    }

    @Test
    void nullIsValidForTemporalConstraintAlone() {
        Probe probe = new Probe(null, null, null, null);
        assertTrue(invalidFields(probe).isEmpty());
    }

    @Test
    void identicalInstantCanBeDifferentCalendarDay() {
        Instant nearMidnight =
                Instant.parse("2030-01-15T23:30:00Z");

        Clock utc = Clock.fixed(
                nearMidnight, ZoneOffset.UTC);
        Clock hcm = Clock.fixed(
                nearMidnight,
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(
                LocalDate.of(2030, 1, 15),
                LocalDate.now(utc));

        assertEquals(
                LocalDate.of(2030, 1, 16),
                LocalDate.now(hcm));
    }
}
```

The **seven unit tests** above require no Spring context:

1. Equal to `now` is rejected by both `@Past` and `@Future`.
2. A one-second offset satisfies the strict constraints.
3. `@FutureOrPresent LocalDate` accepts today.
4. Yesterday fails `@FutureOrPresent`.
5. Tomorrow fails `@PastOrPresent`.
6. Standalone temporal constraints accept null; add `@NotNull` when required.
7. One instant maps to different calendar days in UTC vs `Asia/Ho_Chi_Minh`.

All tests use `2030-01-15T12:00:00Z` or another explicitly declared instant; no sleeps, real system clock, system timezone mutations, or reliance on CI time.

**Boundary QA note:** the example uses ±1 second instead of ±1 nanosecond to avoid inadvertently coupling tests to a temporal type or provider's precision. If nanosecond precision matters to your app, add precision tests matching your actual data types, DB columns, and serializers.

## 9. MockMvc proving Spring actually uses the fixed Clock

The unit tests in section 8 build their own ValidatorFactory, so they **do not prove** Bean Validation in MVC uses that configuration. This section boots a real Spring Boot test context, swaps the Clock bean, and sends HTTP-like requests via `MockMvc`.

### 9.1. src/test/java/demo/BookingMvcTest.java

```java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(BookingMvcTest.FixedClockConfig.class)
class BookingMvcTest {

    private static final Instant NOW =
            Instant.parse("2030-01-15T12:00:00Z");

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfig {

        @Bean
        @Primary
        Clock fixedTestClock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }

    @Autowired
    MockMvc mvc;

    @Autowired
    Clock clock;

    private ResultActions submit(
            String startsAt, String checkIn, String birth)
            throws Exception {

        String body = """
                {
                  "guestName": "Lan",
                  "startsAt": "%s",
                  "checkInDate": "%s",
                  "birthDate": "%s"
                }
                """.formatted(startsAt, checkIn, birth);

        return mvc.perform(post("/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body));
    }

    @Test
    void contextInjectsExactlyTheFixedClock() {
        org.junit.jupiter.api.Assertions.assertEquals(
                NOW, clock.instant());
    }

    @Test
    void futureTimeAndTodayDateAreAccepted()
            throws Exception {
        submit("2030-01-15T13:00:00Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status")
                        .value("ACCEPTED"))
                .andExpect(jsonPath("$.acceptedAt")
                        .value("2030-01-15T12:00:00Z"));
    }

    @Test
    void strictFutureRejectsExactNow()
            throws Exception {
        submit("2030-01-15T12:00:00Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("TEMPORAL_INPUT_INVALID"))
                .andExpect(jsonPath("$.fields",
                        hasItem("startsAt")));
    }

    @Test
    void strictFutureRejectsOneSecondBefore()
            throws Exception {
        submit("2030-01-15T11:59:59Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("startsAt")));
    }

    @Test
    void futureOrPresentRejectsYesterday()
            throws Exception {
        submit("2030-01-15T13:00:00Z",
                "2030-01-14", "2000-01-01")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("checkInDate")));
    }

    @Test
    void strictPastRejectsBirthDateToday()
            throws Exception {
        submit("2030-01-15T13:00:00Z",
                "2030-01-15", "2030-01-15")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("birthDate")));
    }

    @Test
    void shortLeadTimePassesFutureButFailsBusiness()
            throws Exception {
        submit("2030-01-15T12:00:01Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code")
                        .value("BOOKING_TOO_SOON"));
    }

    @Test
    void exactlyThirtyMinutesIsAllowed()
            throws Exception {
        submit("2030-01-15T12:30:00Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.startsAt")
                        .value("2030-01-15T12:30:00Z"));
    }

    @Test
    void oneSecondBeforeThirtyMinutesFails()
            throws Exception {
        submit("2030-01-15T12:29:59Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code")
                        .value("BOOKING_TOO_SOON"));
    }

    @Test
    void malformedInstantDoesNotBecomeTemporalViolation()
            throws Exception {
        submit("not-a-time",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }

    @Test
    void missingDateFailsNotNull()
            throws Exception {
        mvc.perform(post("/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "guestName": "Lan",
                              "startsAt": "2030-01-15T13:00:00Z",
                              "birthDate": "2000-01-01"
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("checkInDate")));
    }
}
```

The **eleven tests** in the Spring context prove:

- The `Clock` bean returns the exact fixed instant.
- Jakarta `@Future` is genuinely governed by the ClockProvider registered via Boot's customizer.
- `@FutureOrPresent` and `@Past` use the UTC date.
- JSON parsing failures are separate from Bean Validation failures.
- The service uses the same Clock to check the 30-minute rule.
- The exact 30-minute boundary is accepted; one second earlier is rejected.
- A missing required `LocalDate` is caught by `@NotNull`.

### Why not just change the default TimeZone?

Calling `TimeZone.setDefault(TimeZone.getTimeZone("UTC"))` in a test mutates **JVM-wide state**. It does not freeze time; the default `ClockProvider` still runs on live time. When tests run in parallel, global state can cause divergent behavior. Overriding the Spring context's Clock bean is cleanly scoped.

### Is @DirtiesContext needed?

In this example, tests use an immutable fixed-clock bean in a context with explicit `@Import` configuration. No bean state is mutated across methods, so `@DirtiesContext` is normally unnecessary.

If a suite **mutates a Clock bean at runtime** to "time travel" between test methods, you must manage resets, test isolation, parallel execution, and Spring context caching. Prefer a fixed clock per test class/context or build a separate factory for cases needing multiple timestamps.

## 10. Running the project and observing results

Requires JDK 17+ and Maven. In the directory containing `pom.xml`:

```bash
mvn -q clean test
```

**Expected:** 7 unit tests + 11 MockMvc integration tests = **18 tests** pass, Maven exit code 0 when dependencies and environment are valid. This expectation is derived from the code, **not a result of a Maven build actually executed here**; run tests locally or in CI to confirm.

Start the server with a real-time clock (UTC):

```bash
mvn spring-boot:run
```

A live request needs `startsAt` more than 30 minutes in the future. If using a POSIX shell with a compatible `date` command, you can compute the timestamp dynamically; never hardcode a 2030 date in production requests assuming it will always remain in the future.

**Checking responses via MockMvc** is safer for this lesson because tests freeze time and do not depend on the run date. Expected response under the fixed test clock:

```json
{
  "status": "ACCEPTED",
  "acceptedAt": "2030-01-15T12:00:00Z",
  "startsAt": "2030-01-15T13:00:00Z"
}
```

Response when `startsAt` equals `now`:

```json
{
  "code": "TEMPORAL_INPUT_INVALID",
  "message": "Request has invalid fields",
  "fields": ["startsAt"]
}
```

Response when `startsAt=2030-01-15T12:00:01Z`:

```json
{
  "code": "BOOKING_TOO_SOON",
  "message": "Book at least 30 minutes ahead",
  "fields": ["startsAt"]
}
```

**Do not assert raw Hibernate Validator messages** if the API does not own them. `@Future` messages may be translated by `MessageSource` or change across providers/versions; tests should verify field name + stable application code + HTTP status.

## 11. Time zones: Instant, LocalDate, and LocalDateTime differ

### 11.1. Instant represents a global point in time

`Instant.parse("2030-01-15T12:00:00Z")` represents a specific instant on the timeline. Changing the clock's zone while keeping the instant leaves `clock.instant()` unchanged:

```java
Instant t = Instant.parse("2030-01-15T23:30:00Z");

Clock utc = Clock.fixed(t, ZoneOffset.UTC);
Clock hcm = Clock.fixed(
        t, ZoneId.of("Asia/Ho_Chi_Minh"));

assert utc.instant().equals(hcm.instant());
```

This is a Java fragment. Time zones affect local date/time interpretation rather than altering the instant.

### 11.2. LocalDate depends on the Clock's zone

For instant `2030-01-15T23:30:00Z`:

```text
UTC:                 2030-01-15 23:30
Asia/Ho_Chi_Minh:    2030-01-16 06:30
```

Thus `LocalDate.now(Clock.fixed(t, UTC))` is Jan 15, while in `Asia/Ho_Chi_Minh` it is Jan 16. With `@FutureOrPresent LocalDate checkInDate`, `2030-01-15` can be "today" in UTC yet **already yesterday** in Ho Chi Minh City.

Applications must define the reference zone for business rules:

- Global systems based on absolute instants: UTC usually fits.
- Hotel check-in: **the hotel's timezone** is usually more appropriate than the server or browser timezone.
- Business days in a country: zone/cutoff defined by business policy.
- Multi-tenant apps with different zones: a single **global** UTC ClockProvider cannot automatically represent "today" for every tenant in one request context.

### 11.3. LocalDateTime carries no time zone/offset

`LocalDateTime.parse("2030-01-15T12:00:00")` represents a calendar date/time **without** specifying a zone. Do not treat it as equivalent to `Instant.parse("2030-01-15T12:00:00Z")`. A `LocalDateTime` requires applying a zone under explicit rules to determine an instant.

If an API accepts global appointment times, usually prefer `Instant` or `OffsetDateTime`. If business logic needs local wall-clock time at a venue, use `LocalDateTime + ZoneId` with explicit rules for DST gaps/overlaps. Tests must cover transition dates in DST regions; UTC does not have DST in the same way.

### 11.4. Do not mutate system-default timezone to "make tests green"

If unit tests depend on the CI machine's timezone, inject `Clock.fixed(..., ZoneId.of(...))` with an explicit `ZoneId`. Mutating the entire JVM environment can accidentally alter behavior in other tests or third-party libraries.

## 12. DST, leap days, and boundaries worth testing

Today's date is not the only edge case:

| Case | Example | Expected test behavior |
| --- | --- | --- |
| Exact "now" | `@Future Instant = now` | Fails |
| One second after now | `@Future Instant = now+1s` | Passes |
| Today | `@FutureOrPresent LocalDate` | Passes |
| Yesterday | `@FutureOrPresent LocalDate` | Fails |
| End-of-day rollover | 23:59:59 → 00:00:00 | Rolls date in the right zone |
| Leap day | 2028-02-29 | Does not shift to a wrong date |
| Month-end 31st | 01-31 → 02-01 | Accurate LocalDate/YearMonth |
| DST spring-forward | Non-existent local hour in a zone | Intentional gap handling |
| DST fall-back | Local hour occurring twice | Intentional overlap/offset handling |
| Leap second | ISO time within Java's supported range | Do not fabricate `:60` as valid input |
| Clock skew between nodes | Service A/B differ by seconds | Tolerance policy and trusted time source |

### Example handling a day by ZoneId

```java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDate targetDay = LocalDate.of(2030, 3, 31);

// Convert day boundaries using the real zone.
Instant dayStart = targetDay.atStartOfDay(zone).toInstant();
Instant nextDayStart = targetDay.plusDays(1)
        .atStartOfDay(zone).toInstant();

Duration dayLength =
        Duration.between(dayStart, nextDayStart);
```

This is a fragment. Some calendar days in DST zones do **not last 24 hours**. Never compute the next day boundary as "start of day + Duration.ofHours(24)" when business logic operates on local calendar days.

Exact DST transition dates vary by zone and year; tests must use a zone/year confirmed against the active tzdb rather than guessing transition dates from memory.

## 13. Custom ConstraintValidator reading ClockProvider properly

A custom temporal constraint can obtain the clock from `ConstraintValidatorContext` instead of calling static `Instant.now()`:

```java
@Override
public boolean isValid(
        Instant value,
        ConstraintValidatorContext context) {

    if (value == null) {
        return true;
    }

    Clock clock = context.getClockProvider().getClock();
    Instant now = clock.instant();

    return value.isAfter(now);
}
```

This is a **fragment** of a `ConstraintValidator<MyFuture, Instant>` class not defined in the runnable project. It behaves like a simple strict-future constraint without group, payload, or annotation metadata support; do not create a custom annotation just to replace `@Future` when built-in constraints suffice.

**Design takeaway:** a custom temporal validator must use `context.getClockProvider().getClock()` to honor the test's reference timestamp. If it calls `Instant.now()` directly, unit tests with a fixed ClockProvider can still flake.

### Cases where plain constraints should not be used

A rule like "book at least 30 minutes ahead unless the caller is staff" depends on the actor, account tier, or availability state. While you can write a DI-backed custom constraint, when authorization, external I/O, or transactions are involved, a **service/domain rule** is usually clearer. Validation should focus on determinable input conditions, leaving business services to enforce invariants and access control.

## 14. ClockProvider and temporal validation tolerance

Jakarta's `ClockProvider` defines the reference instant; Hibernate Validator also supports **temporal validation tolerance** as a provider extension. It can accept a small deviation around boundaries to account for clock skew between systems.

Example fragment using Hibernate Validator's specific API:

```java
ValidatorFactory factory = Validation
        .byProvider(HibernateValidator.class)
        .configure()
        .temporalValidationTolerance(Duration.ofMillis(10))
        .clockProvider(() -> fixedClock)
        .buildValidatorFactory();
```

This snippet requires imports for `org.hibernate.validator.HibernateValidator`, `jakarta.validation.Validation`, `ValidatorFactory`, `java.time.Duration`, and an already-defined `fixedClock` variable. This is **not a portable API across all Jakarta Validation providers**; it belongs to Hibernate Validator.

**Points to watch:**

- Tolerance can change results for inputs **right near** a boundary, including values equal to or slightly before/after reference time depending on the constraint and semantics.
- If production enables tolerance while unit tests do not, the two environments fall out of sync.
- Tolerance is not a substitute for timezones, business lead-time rules, or database race-condition handling.
- Never add tolerance just to mask flaky tests. First use a fixed clock and define clear boundaries.

The runnable project in section 7 **does not enable tolerance** so strict/inclusive checks remain directly observable.

## 15. @WebMvcTest, MockMvc standalone, and clock configuration

### 15.1. @SpringBootTest

The runnable project uses:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Import(BookingMvcTest.FixedClockConfig.class)
class BookingMvcTest {
    // ...
}
```

The full context loads the application's `ClockConfiguration` and `ValidationConfigurationCustomizer`; the test adds a `@Primary` fixed-clock bean. Because both MVC and the service obtain Clock via Spring DI, this tests both **wiring** and behavior.

### 15.2. @WebMvcTest

An MVC slice may load only controllers, relevant web infrastructure, and a subset of auto-configuration. If production `ClockConfiguration` is not loaded in the slice, import it explicitly or provide a test validator configured with the ClockProvider:

```java
@WebMvcTest(BookingController.class)
@Import({
    ClockConfiguration.class,
    FixedClockTestConfig.class
})
class BookingSliceTest {
    // @MockitoBean BookingService service;
}
```

This is an **illustrative fragment**, outside the runnable project because `FixedClockTestConfig` is not declared here and dependency mocking would need completion. The point is that **test slices must not be assumed to auto-load every `@Configuration`** from the full application context. When mocking `BookingService`, the slice can test `@Future`/`@Past`, but does not prove the real service's 30-minute rule.

### 15.3. standaloneSetup

With `MockMvcBuilders.standaloneSetup(...)`, the infrastructure does not auto-load Spring Boot's validation customizer or production Clock bean. You can supply a customized `LocalValidatorFactoryBean`:

```java
LocalValidatorFactoryBean fixedValidator =
        new LocalValidatorFactoryBean();

fixedValidator.setConfigurationInitializer(
        c -> c.clockProvider(() -> fixedClock));
fixedValidator.afterPropertiesSet();

MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new BookingController(
                new BookingService(fixedClock)))
        .setValidator(fixedValidator)
        .build();
```

This is a **fragment** requiring the necessary imports and an existing `fixedClock` variable. When a test instantiates a validator manually, destroy it afterward to avoid leaking lifecycle resources.

**Parity risk:** standalone setup only proves the setup you wired yourself, not that the Boot app actually uses the same clock. Keep at least one full-context MockMvc test for time-critical constraints like expiration times, booking deadlines, and token expiry.

## 16. Common mistakes

### 16.1. Test reading LocalDate.now() for comparison

Incorrect:

```java
LocalDate expected = LocalDate.now();
```

Code running near midnight can compute `expected` from the old date while the validator runs after midnight and reads the new date. Use `LocalDate.now(fixedClock)` and a fixed ClockProvider.

### 16.2. Swapping the Clock bean while @Future still uses live time

You injected `Clock` into the service, but forgot to wire it to `ValidatorFactory` via `ValidationConfigurationCustomizer` or `LocalValidatorFactoryBean`. Service tests pass while MVC validation still uses the default ClockProvider. Verify with a **MockMvc request whose `startsAt` equals the exact fixed now**.

### 16.3. Test builds its own validator while MVC uses another bean

A unit test using `Validation.byDefaultProvider().configure().clockProvider(...)` passes; that only proves the factory you built. If MockMvc/the full app uses a different factory, the fixed provider is inactive. Integration tests must exercise the real MVC infrastructure.

### 16.4. Using Thread.sleep() to wait out a boundary

`Thread.sleep(...)` does not produce a deterministic clock, slows down tests, and flakes on CI. Use `Clock.fixed` to define distinct timestamps. Only tests of actual scheduling mechanisms require scheduler-compatible time/timer control.

### 16.5. Forgetting @NotNull

`@Past`/`@Future` accept null. If a request can omit the field and business rules require it, add `@NotNull`.

### 16.6. Using @Future when @FutureOrPresent is needed

For `LocalDate`, today does not satisfy `@Future`; if today is allowed, use `@FutureOrPresent`. If check-in is only allowed after a 14:00 local cutoff, write a **zone- and cutoff-aware domain rule**, not just a temporal annotation.

### 16.7. Treating LocalDateTime like Instant

`LocalDateTime` has no offset and does not identify a global instant without a `ZoneId`. Accept `Instant`/`OffsetDateTime` when the API needs an instant. If accepting local time, specify the zone and DST rules.

### 16.8. Mutating the JVM-wide timezone

`TimeZone.setDefault(...)` is global mutable state that can affect parallel tests. Inject a fixed Clock with an explicit `ZoneId`; never use a global mutation to "fix" a single test.

### 16.9. Using @Future to prove sufficient booking lead time

`@Future` only checks strictly against now; it does not cover 30-minute lead time, payment, availability, or permissions. Write separate domain rules and tests.

### 16.10. Skipping the exact equality boundary in tests

Testing only inputs days apart can miss exclusive/inclusive bugs. Always test **just before, equal to, and just after** the boundary.

### 16.11. Assuming DB CURRENT_TIMESTAMP is also frozen

Jakarta's ClockProvider does not alter database clocks. If queries compare against `CURRENT_TIMESTAMP` or triggers populate timestamps, use appropriate database test setup/dialects rather than extrapolating from Spring's Clock bean.

### 16.12. Sharing a mutable test clock across parallel tests

A `MutableClock` whose instant changes between tests can race under shared contexts. Prefer immutable `Clock.fixed`; if a mutable clock is required, ensure isolation and resets, or disable parallel execution for affected tests.

### 16.13. Clock.systemUTC() is still real time

`Clock.systemUTC()` selects the UTC zone, **it does not freeze time**. For determinism, use `Clock.fixed(...)`, not just a timezone change.

### 16.14. Ignoring time precision and serialization

`Instant` supports nanoseconds; database `TIMESTAMP` columns may store milliseconds/microseconds, and JSON serializers have formatting rules. Tests requiring exact nanosecond precision must understand the entire pipeline's precision. For a 30-minute boundary, ±1 second tests are clear enough.

## 17. QA checklist for time-based tests

- [ ] "Now" is defined intentionally as an instant + zone.
- [ ] Unit tests use `Clock.fixed(...)` with no real-time dependency.
- [ ] Jakarta Validator is configured with `ClockProvider` backed by the fixed Clock.
- [ ] Spring Boot MVC's factory uses `ValidationConfigurationCustomizer` or `LocalValidatorFactoryBean` properly.
- [ ] Services use injected `Clock` instead of static `Instant.now()` when logic must be deterministic.
- [ ] `@Past`/`@Future` are tested in the past, equal to now, and in the future.
- [ ] `@PastOrPresent`/`@FutureOrPresent` are tested on today's date.
- [ ] `@NotNull` is present on required temporal fields.
- [ ] `Instant` vs `LocalDate` is chosen to match real semantics.
- [ ] Tests cover UTC and a relevant local timezone.
- [ ] DST/gaps/overlaps are tested if the product serves DST regions.
- [ ] JSON decoding errors are distinguished from constraint errors.
- [ ] Business lead-time/eligibility rules are separated from `@Future`.
- [ ] Integration tests run through MockMvc, not only a standalone ValidatorFactory.
- [ ] Lead-time boundaries are tested right at, just before, and just after the cutoff.
- [ ] If Hibernate temporal tolerance is used, test config matches runtime.
- [ ] Global default timezone/JVM time mutations are avoided.
- [ ] Sleep is never used to work around flaky validation tests.
- [ ] ClockProvider is not assumed to control database or external service clocks.
- [ ] If multiple ValidatorFactory beans exist, verify which one MVC actually uses.

## 18. Conclusion

**Testing time with ClockProvider or a fixed clock** turns an unstable environmental factor—"now"—into a controllable input.

- `Clock.fixed(...)` supplies a consistent instant and zone, making boundary checks exact.
- `ClockProvider` is the official bridge for `@Past`, `@Future`, `@PastOrPresent`, and `@FutureOrPresent`.
- `ValidationConfigurationCustomizer` or `LocalValidatorFactoryBean` wires ClockProvider into Spring's Bean Validation factory.
- Injecting the same `Clock` into services keeps business rules like "book at least 30 minutes ahead" deterministic as well.
- Unit tests verify constraints in isolation; MockMvc integration tests prove the **real MVC configuration** uses the fixed clock, avoiding tests that pass while runtime uses a different clock.
- Time zones, `LocalDate`/`Instant`, null handling, tolerance, DST, and database clocks are boundaries that belong in the contract.

**Key message:** do not try to stabilize time-based tests by "picking a date far in the future" or "sleeping for a second". **Model the clock as a dependency**, freeze it in tests, and test all business boundaries.

## References

- [Jakarta Bean Validation 3.0 — ClockProvider API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ClockProvider.html)
- [Jakarta Bean Validation 3.0 — Temporal constraints, ClockProvider, and validation context](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Bean Validation 3.0 — Configuration#clockProvider](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Configuration.html)
- [Spring Boot 3.4 — Validation Configuration Customizer](https://docs.spring.io/spring-boot/3.4/reference/io/validation.html)
- [Spring Boot 3.4 — ValidationConfigurationCustomizer API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/validation/ValidationConfigurationCustomizer.html)
- [Spring Framework 6.2 — LocalValidatorFactoryBean API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework 6.2 — Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework — MVC @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Hibernate Validator 8 — ClockProvider and temporal validation tolerance](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
- [Java 17 — Clock API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)
