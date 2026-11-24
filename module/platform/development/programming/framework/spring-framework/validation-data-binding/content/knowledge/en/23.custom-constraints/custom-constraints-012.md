# Thread Safety and Avoiding Per-Invocation State in Validators

## 1. Why must custom validators be thread-safe?

In Jakarta Bean Validation, a `ConstraintValidator<A, T>` implementation executes the logic of a custom constraint. Basic structure:

~~~java
public final class MyConstraintValidator
        implements ConstraintValidator<MyConstraint, String> {

    @Override
    public void initialize(MyConstraint annotation) {
        // Prepare configuration from the annotation.
    }

    @Override
    public boolean isValid(String value,
                           ConstraintValidatorContext context) {
        // Validate data for the current invocation.
        return true;
    }
}
~~~

By API contract, **`isValid(...)` may be called concurrently from multiple threads on the same validator object**, and the implementation itself must guarantee thread safety. The Bean Validation provider (such as Hibernate Validator in Spring Boot) may **cache `ConstraintValidator` instances**. An instance's lifecycle is not defined as "one instance per request" or "a new instance per validation".

In a Spring MVC application, two HTTP requests handling the same DTO type can arrive simultaneously. If a validator stores request A's input in a field and request B overwrites that field, A may validate the wrong input or accidentally use B's data.

**Core rule:** `isValid` operates independently per invocation. Request data, temporary buffers, and emitted errors belong exclusively in **parameters or local variables**, never in shared mutable fields of the validator.

### A simple race condition

The snippet below is **deliberately buggy**, illustrating part of a validator body:

~~~java
// WRONG: currentCode is a field shared across invocations.
private String currentCode;

@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    currentCode = value; // Thread A and B can write to this field concurrently.
    return currentCode != null && currentCode.startsWith("PRD-");
}
~~~

Suppose A passes `"PRD-123"` and B passes `"BAD"`. Just after A assigns `currentCode`, B overwrites it with `"BAD"`; A reads it back and returns `false` even though A's input was valid. This is a timing-dependent data corruption bug that may never reproduce in a single-threaded test.

Fix by using the parameter directly:

~~~java
@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    return value == null || value.startsWith("PRD-");
}
~~~

Each invocation has its own `value`. `String` is immutable; no lock is needed.

## 2. `ConstraintValidator` lifecycle and two kinds of state

The Jakarta Validation contract has three key points:

1. `initialize(A annotation)` is called by the provider **before an instance is used for validation**. This is where constraint configuration—such as a regex or limit values—is read. Do not treat `initialize` as a per-request callback.
2. `isValid(T value, ConstraintValidatorContext context)` is called when a value needs checking; it **may execute concurrently** on one instance. It must not mutate the state of `value`.
3. Instance lifecycle is decided by the provider. The provider is allowed to reuse/cache instances; therefore correct code must not depend on instantiation counts, threads, or requests.

Classifying state during design:

| Data | Store in validator instance? | Reason |
| --- | --- | --- |
| Regex compiled from annotation | **Yes**, when assigned only in `initialize` and never modified afterward | `Pattern` is immutable, thread-safe, and suitable for sharing. |
| `min/max` numbers, flags, config rules | **Yes**, if configuration never changes after initialization | Read-only when `isValid` runs. |
| Request input/DTO/username/password | **No** | Easily overwritten by other threads and leaks data across requests. |
| `Matcher`, `StringBuilder`, temporary error lists | **No** | Mutable objects belonging to each invocation. |
| `ConstraintValidatorContext` or violation builder | **No** | Error-building context scoped to the current invocation. |
| Error counters, temporary maps, mutable caches | Only with a clear need and proper concurrency mechanism | Better delegated to a dedicated metrics/cache service. |
| Spring-injected dependencies | **Depends** on the dependency's thread safety and scope | Shared objects may carry their own state. |

A field is not automatically dangerous. The question is **whether it is mutated while `isValid` invocations run**. For example, `private Pattern pattern;` assigned once in `initialize` and read afterward is a valid design pattern. Conversely, `private String currentValue;` assigned on every `isValid` call is per-invocation state and must be eliminated.

Be cautious about "locking for safety" with `synchronized`. If temporary data can become a local variable, that is usually both simpler and better for concurrency.

## 3. `Pattern` can be shared, `Matcher` cannot

`java.util.regex.Pattern` is an **immutable and thread-safe** regex pattern. `Matcher` holds cursor position and matching state, so it is **not thread-safe**. Correct approach:

~~~java
private Pattern compiledPattern;

@Override
public void initialize(CodePattern constraint) {
    compiledPattern = Pattern.compile(constraint.regexp());
}

@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    if (value == null || value.isBlank()) {
        return true; // Let @NotBlank handle missing data.
    }
    Matcher localMatcher = compiledPattern.matcher(value);
    return localMatcher.matches();
}
~~~

Each invocation creates its own `localMatcher`. The read-only `Pattern` object is shared safely.

Incorrect approach:

~~~java
// WRONG: mutable Matcher is held in a validator field.
private Matcher matcher;

@Override
public void initialize(CodePattern constraint) {
    matcher = Pattern.compile(constraint.regexp()).matcher("");
}

@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    return matcher.reset(value).matches();
}
~~~

Two threads can interleave between `reset(...)` and `matches()`, making A's result depend on B's input. Writing it on a single line does not make multiple operations on a mutable object atomic.

The same rule applies to dates and times: `java.time.format.DateTimeFormatter` is immutable and shareable; `java.text.SimpleDateFormat` is mutable and must not be kept as a shared validator field under concurrent calls. For collections, storing temporary state in `ArrayList`/`HashMap` fields is equally error-prone; create local collections instead.

## 4. Java 17+ example with Spring Boot: request-stateless validator

The example runs in a **Spring Boot 3+** project with Java 17+ and Jakarta Validation (`jakarta.validation.*`). If absent, add to `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Create **`src/main/java/com/example/validation/ConcurrentValidationApplication.java`**:

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@SpringBootApplication
public class ConcurrentValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConcurrentValidationApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(Validator validator) {
        return args -> {
            String[] codes = {
                    "PRD-AB-1234",
                    "PRD-ab-1234",
                    "INV-AB-1234"
            };
            for (String code : codes) {
                var violations = validator.validate(new Product(code));
                String result = violations.isEmpty()
                        ? "VALID"
                        : violations.iterator().next().getMessage();
                System.out.println(code + " -> " + result);
            }
        };
    }

    @Target(ElementType.FIELD)
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = CodePatternValidator.class)
    public @interface CodePattern {
        String regexp() default "PRD-[A-Z]{2}-[0-9]{4}";
        String message() default "Code must match PRD-AA-0000";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    public static final class CodePatternValidator
            implements ConstraintValidator<CodePattern, String> {

        // Annotation-level configuration: set during initialize.
        private Pattern compiledPattern;

        @Override
        public void initialize(CodePattern annotation) {
            compiledPattern = Pattern.compile(annotation.regexp());
        }

        @Override
        public boolean isValid(String value,
                               ConstraintValidatorContext context) {
            // Avoid duplicate errors with @NotBlank.
            if (value == null || value.isBlank()) {
                return true;
            }

            // Matcher belongs exclusively to the running invocation.
            Matcher matcher = compiledPattern.matcher(value);
            return matcher.matches();
        }
    }

    public static final class Product {
        @NotBlank
        @CodePattern
        private final String code;

        public Product(String code) {
            this.code = code;
        }

        public String getCode() {
            return code;
        }
    }
}
~~~

Run in a project configured with Maven and the Spring Boot plugin:

~~~bash
./mvnw spring-boot:run
~~~

Windows: `mvnw.cmd spring-boot:run`; or `mvn spring-boot:run` if Maven is installed. Alongside Spring Boot logs, the program prints:

~~~text
PRD-AB-1234 -> VALID
PRD-ab-1234 -> Code must match PRD-AA-0000
INV-AB-1234 -> Code must match PRD-AA-0000
~~~

Correctness of the example:

- The `@CodePattern` annotation configures the regex and message. It has the three standard constraint elements: `message`, `groups`, and `payload`.
- `initialize` compiles the regex once for the instance's constraint configuration. `compiledPattern` is never mutated by requests.
- `isValid` only reads the pattern; every input and `Matcher` is local. There are no mutable `lastCode` or `lastResult` fields.
- `@NotBlank` handles null/blank strings, while the regex constraint validates non-blank content. This is a deliberate choice to avoid two messages for the same missing-data error.
- `Validator#validate(...)` returns a `Set<ConstraintViolation<Product>>`; Set order is not guaranteed. For each non-empty input in the example there is at most one violation.
- Spring may reuse the validator across checks; logic remains accurate because no invocation state is held on the instance.

If a field has multiple annotations with different parameters, let the provider supply the right configuration when calling `initialize` for each constraint declaration. Do not use `static Pattern CURRENT_PATTERN` and overwrite it whenever a new annotation is encountered: one constraint's configuration would affect another.

## 5. `ConstraintValidatorContext` is per-invocation data

`ConstraintValidatorContext` is used to build custom error messages, construct error paths, and choose whether to keep the default violation. **Do not store `context` or builders in instance fields**, and do not use them after `isValid` returns.

Example replacing **only the `isValid` method** in `CodePatternValidator` above, creating a custom error using the annotation's own message:

~~~java
@Override
public boolean isValid(String value,
                       ConstraintValidatorContext context) {
    if (value == null || value.isBlank()) {
        return true;
    }

    Matcher matcher = compiledPattern.matcher(value);
    if (matcher.matches()) {
        return true;
    }

    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(
            context.getDefaultConstraintMessageTemplate())
            .addConstraintViolation();
    return false;
}
~~~

Notes:

1. `disableDefaultConstraintViolation()` only suppresses the default error; afterward, when returning `false`, you must complete at least one custom violation via `addConstraintViolation()`.
2. The builder must be created, used, and finalized entirely within the invocation. No `currentMessage` or `lastContext` field is needed.
3. In the example, the constraint sits on field `code`, so the violation automatically attaches at path `code`. For a class-level constraint comparing two fields, add `addPropertyNode("fieldName")` to attach it to the right field.

Illustration of the `isValid` body of a class-level constraint checking start/end dates on a DTO with `start()` and `end()` getters returning `LocalDate` (a logic snippet, not a complete program):

~~~java
@Override
public boolean isValid(PeriodRequest value,
                       ConstraintValidatorContext context) {
    if (value == null || value.start() == null
            || value.end() == null) {
        return true; // Field-level @NotNull handles missing data.
    }
    if (!value.start().isAfter(value.end())) {
        return true;
    }

    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(
            "End date cannot be before start date")
            .addPropertyNode("end")
            .addConstraintViolation();
    return false;
}
~~~

The error is attached to `end` on the exact DTO being validated. Each invocation is independent; there are no `lastStart`/`lastEnd`/`lastError` fields. In Spring MVC, if the DTO is checked with `@Valid @RequestBody` and a controller accepts `BindingResult`, field errors can be retrieved via `getFieldErrors()`. Do not store `BindingResult` inside the validator since that belongs to the request-handling layer.

## 6. Spring dependency injection, `ConstraintValidatorFactory`, and caching

Spring Boot normally integrates `jakarta.validation.Validator` and provides dependency injection for custom constraint validators. Even so, do not infer that a validator's lifecycle matches the HTTP request lifecycle or that every invocation gets a fresh object.

Distinguish:

- **`jakarta.validation.Validator`** is the validation API, with a thread-safe contract; it can be used to validate multiple beans across different threads.
- **`ConstraintValidator<A,T>`** is application-written logic. The provider is permitted to cache it and call `isValid` concurrently, so the implementation must also be thread-safe.
- **`ConstraintValidatorFactory`** supplies instances to the provider. Per Jakarta Validation, the factory **should not cache instances itself**, because `initialize` can configure the same validator class differently on different constraint declarations. Caching afterward is part of the provider's strategy.
- **Injected Spring services/repositories** have their own thread safety and scopes. A validator without shared mutable fields can still fail if it calls a non-thread-safe collaborator.

The safe way to design dependencies is to use stateless services or APIs with clear concurrency contracts. Never store `HttpServletRequest`, current user info, tenant ID, DTOs, or request transactions in validator fields. If contextual data is needed, obtain it from an appropriately scoped layer and avoid depending on state retained across calls.

**Caching and synchronization:** any genuinely necessary cache needs complete keys, lifecycle management, size/TTL bounds, and proper concurrency mechanisms; `ConcurrentHashMap` or a dedicated cache service can be used. Do not use a mutable `HashMap` field across concurrent requests. Add `synchronized` only when truly shared mutable data and a clear reason exist, instead of serializing every invocation.

**`ThreadLocal` is not request-local.** With thread pools, a thread can be reused for another request. If not cleared at the right time, `ThreadLocal` retains stale data; in async/reactive processing, a single request may switch threads. Avoid using `ThreadLocal` to hold `ConstraintValidatorContext`, inputs, or error lists. Local variables are direct and far easier to verify.

## 7. Testing validation across multiple threads

Single-threaded tests only verify basic business logic. To increase the chance of catching race conditions, call **the same `Validator`** from multiple threads with interleaved valid and invalid inputs. For the `ConcurrentValidationApplication` example, add the following dependency to `pom.xml` if the project lacks it:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create **`src/test/java/com/example/validation/ConcurrentValidationApplicationTest.java`**:

~~~java
package com.example.validation;

import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ConcurrentValidationApplicationTest {

    @Autowired
    Validator validator;

    @Test
    void validatesIndependentInputsAcrossThreads() throws Exception {
        int total = 400;
        var start = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(8);

        try {
            List<Future<Boolean>> results = new ArrayList<>();

            for (int i = 0; i < total; i++) {
                final int index = i;

                results.add(pool.submit(() -> {
                    start.await();
                    boolean expectedValid = index % 2 == 0;
                    String code = expectedValid
                            ? "PRD-AB-1234"
                            : "PRD-ab-1234";

                    var violations = validator.validate(
                            new ConcurrentValidationApplication.Product(code));

                    if (expectedValid) {
                        return violations.isEmpty();
                    }

                    return violations.size() == 1
                            && "code".equals(
                                    violations.iterator().next()
                                            .getPropertyPath().toString());
                }));
            }

            // Release waiting workers simultaneously.
            start.countDown();

            for (Future<Boolean> result : results) {
                assertTrue(result.get(10, TimeUnit.SECONDS));
            }
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Run with `./mvnw test`, or `mvnw.cmd test` on Windows. The test submits 400 tasks across an 8-thread pool; half have valid data and half violate `@CodePattern`. `CountDownLatch` helps waiting threads start close together; `Future#get` brings each task's result/exception back to the test thread for assertion. The test checks that each invocation's outcome belongs strictly to that invocation's data.

**Understand test limitations:** a passing test does not prove race conditions are impossible; it only shows no bug appeared in the interleavings that actually occurred. Combine testing with ownership reviews of every mutable object, boundary-case testing, and auditing shared dependencies.

Additional cases worth testing:

| Case | Expectation |
| --- | --- |
| Two different valid inputs in parallel | Both valid, no cross-field misreads. |
| Valid input interleaved with invalid input | Results match their own inputs and property paths. |
| `null` and blank simultaneously | Only `@NotBlank` reports missing data, no duplicate regex errors. |
| Two annotations sharing a validator class with different configs | No rule configuration bleeding across constraints. |
| Class-level constraint creating multiple field errors | Each error path belongs to the right DTO. |
| Validator with dependencies/caching | No user data leaks or inconsistent results. |

## 8. Common bugs and fixes

1. **Storing current values in fields** like `lastInput`, `currentUser`, `currentDto`: can be overwritten by another request. **Fix:** use parameters and local variables.
2. **Sharing `Matcher`** across invocations: matchers are mutable and not thread-safe. **Fix:** share `Pattern`, create a new `Matcher` per invocation.
3. **Accumulating errors in `ArrayList`/`HashMap` fields**: causes both races and stale errors from prior requests. **Fix:** use local collections or build custom violations on the current call's context.
4. **Storing `ConstraintValidatorContext`/builders as fields**: one call may use another call's context. **Fix:** build errors completely inside `isValid`.
5. **Reassigning patterns/rules in `isValid`**: request A's config affects request B. **Fix:** set rules in `initialize`, then read only.
6. **Assuming `initialize` runs before every request**: providers may reuse instances. **Fix:** treat it as instance initialization.
7. **Using shared `SimpleDateFormat` or mutable parsers**: parser state mutates concurrently. **Fix:** use immutable formatters like `DateTimeFormatter` or local parsers.
8. **Using `ThreadLocal` as request-scoped storage**: thread pools can retain old values. **Fix:** avoid per-request state in validators.
9. **Using a non-thread-safe collaborator**: a stateless validator still breaks if it calls an unsafe stateful service. **Fix:** audit the dependency graph and concurrency contracts.
10. **Mutating the DTO during validation**: violates the contract and risks racing with business layers. **Fix:** read-only checks; do not normalize by mutating inside `isValid`.
11. **Ignoring null/blank cases**: can produce overlapping errors or `NullPointerException`. **Fix:** define each constraint's responsibility clearly; use `@NotNull`/`@NotBlank` for missing data.
12. **Running only single-threaded tests**: fails to trigger races. **Fix:** combine multithreaded tests with state ownership reviews.

## 9. Checklist before shipping a validator to production

- [ ] All validator fields are immutable configuration set in `initialize` or shared dependencies with thread-safe contracts.
- [ ] `isValid` never writes to fields to store inputs, errors, contexts, builders, or per-call temporaries.
- [ ] For regexes, `Pattern` is shared; `Matcher` is created locally.
- [ ] Neither `value` nor its child objects are mutated during validation.
- [ ] Custom errors call `addConstraintViolation()` completely and never retain context past the invocation.
- [ ] Never rely on one-instance-per-request, `ConstraintViolation` Set order, or `ThreadLocal` to identify requests.
- [ ] Reviewed thread safety of dependencies, caches, parsers, and external data reads.
- [ ] Tested valid/invalid/missing data, property paths, and concurrent invocations.

**Takeaway:** The provider may invoke `isValid` concurrently on the same `ConstraintValidator`. Keeping **configuration immutable after initialization** and **invocation data in parameters/local variables** makes validation accurate, safe, and scalable in Spring applications.

## References

- Jakarta Validation API 3.1 — `ConstraintValidator` (thread safety, `initialize`): https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.1.1/jakarta/validation/ConstraintValidator.html
- Jakarta Bean Validation specification 3.0 — lifecycle and caching: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.pdf
- Hibernate Validator Reference Guide — custom constraints, `ConstraintValidatorFactory`: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/
- JDK 17 — `Pattern` (thread-safe): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
- JDK 17 — `Matcher` (non-thread-safe): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html
