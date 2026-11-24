# Designing Pure and Thread-Safe Converters for Concurrent Execution in Spring

## 1. Why Must a Converter Be Pure and Thread-Safe?

In Spring, a **converter** transforms data from a source type to a target type. For instance, turning a product code string into a `ProductCode` value object, a numeric string into an `Integer`, or a date string following an input contract into a `LocalDate`. Converters are typically registered into `ConversionService` and reused across many parts of the application.

When a Spring web application runs, the same registered converter can be invoked by many near-simultaneous requests. If a converter stores state from a previous call in a mutable field, or uses a non-thread-safe object, requests can corrupt each other's data.

Dangerous example:

~~~java
public class UnsafeConverter implements Converter<String, String> {
    private String lastValue;

    @Override
    public String convert(String source) {
        lastValue = source;
        return lastValue.trim();
    }
}
~~~

In this example, two threads can write `lastValue` concurrently. Thread A writes request A's data, thread B overwrites it with request B's data, and A reads B's value. The outcome depends on execution scheduling; bugs can be rare and hard to reproduce.

A good converter typically exhibits these properties:

- **Stateless:** keeps no per-conversion data in mutable fields.
- **Pure in a practical sense:** output depends solely on the input and explicit rules; causes no side effects such as writing to a database, making HTTP calls, or updating shared state.
- **Deterministic:** identical input and configuration yield identical output.
- **Thread-safe:** multiple threads can invoke it concurrently without producing wrong results or corrupting shared state.
- **Clear error contract:** explicitly defines how null, empty strings, whitespace, malformed formats, and out-of-range values are handled.
- **Lightweight:** avoids I/O, long-held locks, or expensive work inside a simple type conversion.

These properties are related yet distinct. A stateless converter can still be unsafe if it uses an external mutable singleton. A thread-safe converter can still be impure if it emits events or writes logs. The goal is to design conversions that are short, predictable, and independent of request lifecycles.

## 2. Spring's Converter Contract

The standard SPI in Spring Core:

~~~java
package org.springframework.core.convert.converter;

public interface Converter<S, T> {
    T convert(S source);
}
~~~

`S` is the source type, `T` is the target type. The converter is registered in a `ConverterRegistry` or an appropriate `ConversionService`. Example:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToProductCode());

ProductCode code = service.convert("sku-a123", ProductCode.class);
~~~

This is an integration snippet with Spring Core, requiring the `spring-core` dependency and corresponding imports. With a conversion service configured and shared across the application, multiple execution threads can request conversions at the same time.

### 2.1. A Converter Is Not a Place to Store Request Data

Do not place the following information into mutable instance fields of a converter:

| State not to store | Why |
| --- | --- |
| Most recent input value | Another request can overwrite it |
| Current request's `Locale` | Locale belongs to each request's context |
| Current user / current tenant | Must never retain a previous request's identity |
| `BindingResult` / `WebDataBinder` | These objects are tied to a single binding pass |
| Shared mutable buffers | Multiple threads can modify them simultaneously |
| Custom mutable counters or caches | Require separate synchronization/thread-safety strategies, usually outside the converter |

Immutable data, constants, and immutable lookup structures are much better suited:

~~~java
private static final Set<String> ALLOWED =
        Set.of("NEW", "PAID", "CANCELLED");
~~~

`Set.of` creates an unmodifiable set. However, if the elements inside are mutable objects, the overall structure is not deeply immutable. Prefer immutable value objects and avoid sharing objects that can be mutated after being placed into a lookup structure.

### 2.2. Pure Conversion: Input → Output or Error

A converter can be considered practically pure when it:

- Reads input, validates it, and normalizes it per defined rules.
- Constructs a new value object or returns an immutable type.
- Does not mutate the input.
- Does not depend on time, network, database, randomness, or shared state.
- Does not modify shared configuration during conversion.
- Never produces results influenced by a preceding request.

Example:

~~~java
public final class StringToProductCode
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        return new ProductCode(normalized);
    }
}
~~~

Given the same input string, the result is always the same normalized code. `Locale.ROOT` keeps the uppercasing rule independent of user locale or server settings.

However, pure does not mean every input must be accepted. Invalid input can throw a meaningful exception. A pure conversion can still fail according to its pre-defined contract.

## 3. Why Can a Spring Converter Be Invoked Concurrently?

In a Spring application, the conversion service or registry is typically configured at startup and then used by many components. A registered converter can be invoked by:

- Spring MVC when binding query parameters, path variables, or form fields.
- `DataBinder` / `WebDataBinder` when assigning properties.
- Other Spring components that use `ConversionService`.
- Application code calling `conversionService.convert(...)` directly.
- Multiple requests processed on different threads.

Do not rely on the assumption that “only one request calls the converter at a time”. Servlet containers routinely handle many requests in parallel, and the same singleton bean can be invoked from many threads.

Example of a converter registered as a bean:

~~~java
@Configuration
public class ConversionConfig {

    @Bean
    Converter<String, ProductCode> productCodeConverter() {
        return new StringToProductCode();
    }
}
~~~

This snippet illustrates a bean in the Spring container. When the converter is a singleton (the standard default bean scope), the exact same instance is reused. That **does not automatically make the converter thread-safe**; the implementation itself determines safety.

There is no need to create a new converter per request just to avoid race conditions. Eliminate mutable shared state and use thread-safe collaborators.

## 4. Complete Example: Immutable Converter Executed Concurrently

The example below uses Java 17+, Spring Core 6.2.12, and Gradle. The program builds a stateless converter, registers it once in `DefaultConversionService`, and then converts product codes concurrently across multiple threads. It verifies that every output still corresponds accurately to that task's input.

### 4.1. Defining the Value Object

File `src/main/java/ProductCode.java`:

~~~java
import java.util.Locale;
import java.util.Objects;

public record ProductCode(String value) {
    public ProductCode {
        Objects.requireNonNull(value, "value must not be null");

        if (!value.matches("SKU-[A-Z0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Product code must match SKU-[A-Z0-9]{4}");
        }
    }

    public static ProductCode fromInput(String raw) {
        Objects.requireNonNull(raw, "raw must not be null");
        return new ProductCode(
                raw.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

The record generates accessors and equality based on its component. The `value` field is final; there is no setter. The factory method normalizes strings according to a clear rule before creating the code.

The class also validates format inside the compact constructor. This protects the invariant even if someone calls `new ProductCode("bad")` directly without going through the converter.

### 4.2. Writing a Stateless Converter

File `src/main/java/StringToProductCode.java`:

~~~java
import java.util.Objects;
import org.springframework.core.convert.converter.Converter;

public final class StringToProductCode
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        Objects.requireNonNull(source, "source must not be null");
        return ProductCode.fromInput(source);
    }
}
~~~

The converter has no instance fields. Each call only reads the `source` argument and returns a new value object. `Objects.requireNonNull` makes null failures explicit; in normal Spring flows, `ConversionService` has its own null-handling rules, yet code calling the converter directly still needs a clear contract.

No `synchronized` keyword is needed because there is no mutable shared state. Adding locks to a stateless converter only introduces overhead without solving any problem.

### 4.3. Running Multiple Concurrent Tasks

File `src/main/java/ConcurrentConversionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.core.convert.support.DefaultConversionService;

public final class ConcurrentConversionDemo {

    public static void main(String[] args) throws Exception {
        DefaultConversionService service =
                new DefaultConversionService();
        service.addConverter(new StringToProductCode());

        int taskCount = 1_000;
        ExecutorService executor =
                Executors.newFixedThreadPool(8);

        try {
            List<Callable<String>> tasks = new ArrayList<>();

            for (int i = 0; i < taskCount; i++) {
                final int number = i;

                tasks.add(() -> {
                    String input = String.format(" sku-%04d ", number);
                    ProductCode converted =
                            service.convert(input, ProductCode.class);

                    String expected =
                            String.format("SKU-%04d", number);

                    if (!expected.equals(converted.value())) {
                        throw new IllegalStateException(
                                "Expected " + expected
                                        + " but got " + converted.value());
                    }

                    return converted.value();
                });
            }

            List<Future<String>> results =
                    executor.invokeAll(tasks);

            for (Future<String> result : results) {
                result.get();
            }

            System.out.println("tasks=" + results.size());
            System.out.println("allConversionsCorrect=true");
            System.out.println("first=" + results.get(0).get());
            System.out.println("last="
                    + results.get(results.size() - 1).get());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'concurrent-converter-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-core:6.2.12'
}

application {
    mainClass = 'ConcurrentConversionDemo'
}
~~~

Run with JDK 17+:

~~~bash
gradle -q run
~~~

If a Gradle Wrapper is present, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows. When downloading dependencies, the machine must have access to Maven Central.

Exact stdout from the program:

~~~text
tasks=1000
allConversionsCorrect=true
first=SKU-0000
last=SKU-0999
~~~

`invokeAll` returns the list of Futures in the order of the submitted task list, not thread completion order. Therefore `first` and `last` are still task 0 and task 999 even though tasks may run concurrently or finish in a different order.

This example is a useful small stress check for catching shared-state bugs; it is **not a formal proof** that every system is free of race conditions. For higher confidence, test with varied inputs, more threads, longer loops, edge cases, and every collaborator the converter actually uses.

## 5. Unsafe Converter Patterns and How to Fix Them

### 5.1. Pitfall 1: Holding the Latest Value in a Field

Unsafe:

~~~java
public class LastValueConverter
        implements Converter<String, ProductCode> {

    private String normalized;

    @Override
    public ProductCode convert(String source) {
        normalized = source.trim().toUpperCase(Locale.ROOT);
        return new ProductCode(normalized);
    }
}
~~~

Two threads can write `normalized` simultaneously. One thread may return a code built from the other thread's input. This is a race condition and a cross-request data leakage bug.

Fix with a local variable:

~~~java
@Override
public ProductCode convert(String source) {
    String normalized =
            source.trim().toUpperCase(Locale.ROOT);
    return new ProductCode(normalized);
}
~~~

Local variables live on each invocation's stack frame and are therefore never shared across conversions. That does not automatically make every object referenced by a local variable thread-safe; if it references an external shared mutable object, that still needs evaluation.

### 5.2. Pitfall 2: Using a Shared SimpleDateFormat

`SimpleDateFormat` is mutable and unsafe when multiple threads share a single instance. The following pattern is dangerous:

~~~java
public class UnsafeDateConverter {
    private final SimpleDateFormat format =
            new SimpleDateFormat("yyyy-MM-dd");

    public Date parse(String value) throws ParseException {
        return format.parse(value);
    }
}
~~~

One thread can mutate internal state while another thread is parsing. Outcomes can be exceptions, wrong dates, or erratic behavior.

Prefer `java.time.format.DateTimeFormatter`, which is immutable and thread-safe:

~~~java
private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.ISO_LOCAL_DATE;

public LocalDate parse(String value) {
    return LocalDate.parse(value, FORMAT);
}
~~~

This snippet uses the Java Time API. `DateTimeFormatter` can be safely shared across threads. For custom patterns, construct the formatter once via its factory and keep it immutable; never mutate a formatter per request.

### 5.3. Pitfall 3: Storing Request Locale in a Singleton

Unsafe:

~~~java
public class LocaleAwareConverter
        implements Converter<String, BigDecimal> {

    private Locale currentLocale;

    public void setCurrentLocale(Locale locale) {
        this.currentLocale = locale;
    }

    @Override
    public BigDecimal convert(String source) {
        NumberFormat format =
                NumberFormat.getNumberInstance(currentLocale);
        try {
            return new BigDecimal(
                    format.parse(source).toString());
        } catch (ParseException ex) {
            throw new IllegalArgumentException(ex);
        }
    }
}
~~~

`currentLocale` can be overwritten by another request. User A using `vi_VN` and user B using `en_US` concurrently can cause A to parse under B's locale.

If a conversion rule is **locale-dependent**, `Formatter<T>` is usually a better fit than `Converter<S,T>` because `Formatter` receives `Locale` directly in `parse(String, Locale)` and `print(T, Locale)`. Do not inject locale into a singleton converter via per-request setters.

If the API format is fixed, declare a fixed contract (for instance, ISO dates or numbers with a decimal dot) and use the appropriate parser. Do not read the system default locale on each conversion if identical inputs must produce consistent results across environments.

### 5.4. Pitfall 4: Using an Unsynchronized Shared Mutable Cache

Example:

~~~java
private final Map<String, ProductCode> cache = new HashMap<>();
~~~

A mutable `HashMap` is not designed for concurrent reads and writes across threads. If caching is genuinely needed, pick a proper thread-safe cache solution and determine:

- Does the key include every factor that changes the outcome?
- Are size limits or TTL needed?
- Is it acceptable for multiple threads to recompute the same key simultaneously?
- Could the cache hold sensitive data?
- How will updates, eviction, and performance monitoring work?
- Could cache failures alter conversion semantics?

Even so, a converter is usually the wrong place to add a cache. Converting a short string into a value object is typically cheap; caching adds complexity, memory footprint, and shared state. Only add caching after profiling proves it is necessary.

### 5.5. Pitfall 5: Calling a Repository or HTTP Client Inside convert

A converter like:

~~~java
Product product = productRepository.findByCode(source);
~~~

turns type conversion into an external-system access operation. This leads to:

- Database/network latency during request binding.
- Difficulty distinguishing parsing errors from infrastructure failures.
- Repeated queries when a form has multiple fields or validation paths.
- Difficulty controlling transactions, authorization, and tenancy.
- Conversion results depending on system state at call time.
- Difficulty testing concurrently and reproducing bugs.

A converter is suited for parsing/normalizing a **representation value** into a Java type. Looking up entities by ID/code belongs in the service or application layer. Once a key/value object is converted, the controller/service calls the repository in an explicit step and handles not-found according to business rules.

## 6. Distinguishing Converter, Formatter, and PropertyEditor

| Component | Characteristics | Choose when |
| --- | --- | --- |
| `Converter<S,T>` | One-way, explicit source and target types | Domain type conversion / pure locale-independent parsing |
| `ConverterFactory<S,R>` | Creates converters for a family of target types | Multiple related target types sharing one source type |
| `GenericConverter` | Converts based on type pairs and `TypeDescriptor` | Rules depending on generics or annotations |
| `Formatter<T>` | Parse and print, accepts `Locale` | Display data formatted by language/region |
| `PropertyEditor` | Legacy JavaBeans API, stateful with text representation | Only when legacy compatibility is needed; avoid sharing instances |

`Converter` is usually simple and holds no locale. `Formatter` passes locale into every parse/print call, avoiding storing request locale on the instance. `PropertyEditor` typically holds internal state (such as a text value), so do not create a shared singleton editor across requests; binders create and manage editors in the appropriate scope.

Choose an SPI based on semantics rather than forcing one `Converter` to serve every need. For example, parsing product codes with fixed rules makes a sensible converter; parsing dates in a user's locale is usually a better formatter.

## 7. Rules for Null, Empty, Whitespace, and Errors

A pure converter must have an explicit input contract. Do not treat all boundary cases as identical arbitrarily.

| Input | Questions to decide |
| --- | --- |
| `null` | Does the caller/conversion service handle null beforehand? Does calling the converter directly throw NPE or allow null? |
| `""` | Is empty a missing value, or an invalid value? |
| `"   "` | Should it trim? After trimming, is it treated as empty? |
| Letter casing | Should it canonicalize? Is the rule locale-sensitive? |
| Unicode characters | Normalize Unicode or restrict to ASCII only? |
| Out-of-range values | Which parse/validation error is thrown? |
| Leading zeros | Preserve them? For instance, does identifier `"0007"` differ from `"7"`? |

Do not trim every string mechanically. For product codes, trimming may be desired. For passwords, tokens, or signed values, trimming can alter valid data. For codes with leading zeros, do not convert through integers because that loses information.

### 7.1. Meaningful Exceptions

A converter can throw `IllegalArgumentException` or an appropriate exception when input is invalid; `ConversionService`/binders handle it depending on the call path. In Spring MVC, binding conversion failures are usually represented as binding errors; a controller can receive `BindingResult` for a matching `@ModelAttribute`.

Write error messages clear enough for developers without placing secret data into the message. Never catch all exceptions and return null:

~~~java
// Avoid: hides invalid input errors and creates an unclear state
try {
    return parse(source);
} catch (RuntimeException ex) {
    return null;
}
~~~

Returning null can cause the system to misinterpret invalid input as an omitted field. Preserve the distinction between “no value” and “unparseable value”.

## 8. Registration in Spring MVC and Spring Boot

### 8.1. Registering via WebMvcConfigurer

Integration example in an MVC application:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCode());
    }
}
~~~

`addFormatters` is used by Spring MVC to register converters/formatters into MVC's conversion service. Converters should be fully initialized before registration. Never mutate registry configuration while requests are actively using the conversion service.

In a Spring Boot MVC application, you can configure via `WebMvcConfigurer` without replacing all MVC auto-configuration. If declaring your own `ConversionService` or overriding MVC too broadly, verify you do not lose default formatters/converters or other Boot configuration.

### 8.2. Registering a Converter as a Bean

In certain configurations, a converter can be declared as a Spring bean and discovered/registered by the corresponding configuration mechanism. Do not rely on the mere presence of a `Converter`-typed bean to automatically register it in every Spring conversion path unless your application's configuration documentation confirms it. For MVC, the explicit approach is registering via `WebMvcConfigurer`'s `FormatterRegistry`.

If you need to inject dependencies into a converter, create the bean via configuration:

~~~java
@Bean
StringToProductCode stringToProductCode() {
    return new StringToProductCode();
}
~~~

The pure converter example above needs no dependencies. If a converter requires immutable configuration, inject it through the constructor and keep fields final; never use setters to mutate state after the bean is shared.

### 8.3. Scope Is Not a Cure for Stateful Design

Replacing a singleton converter with prototype/request scope solely to avoid race conditions is usually a poor solution:

- It can complicate integration and mismatch the lifecycle expected by the conversion service.
- A new scope does not eliminate mutable state in shared collaborators.
- Continuously instantiating objects does not fix side effects or request-dependent logic.
- A stateless converter can be shared efficiently and is easier to test.

Choose scopes based on genuine object requirements. For value-converting converters, stateless design is almost always the right starting point.

## 9. Things Not to Do Inside convert()

**Do not read SecurityContext and store the user in a field.** If conversion depends on principal/tenant, pass that context explicitly in the appropriate business layer. ThreadLocal contexts must also have proper lifecycle management; never store them on the converter instance.

**Do not update the database.** Turning an ID string into a typed ID is conversion; finding the entity and checking permissions is business logic.

**Do not call external APIs.** Network timeouts must not be disguised as parse errors.

**Do not emit events or mutate global state.** Side effects make retries/tests unpredictable; perform them in the application service.

**Do not swallow errors and return a default value.** For example, parsing an invalid string into 0 can make data look valid yet carry the wrong meaning.

**Do not use mutable singleton helpers.** Audit every object the converter calls: parsers, formatters, collections, caches, and third-party libraries.

**Do not log raw input indiscriminately.** Inputs may contain passwords, tokens, PII, or extremely long strings. If observability is needed, log the error kind and safe, bounded metadata.

## 10. Testing Converters Across Multiple Layers

### 10.1. Unit Tests for Semantics

Verify:

- Valid strings produce the right value object.
- Whitespace and case normalization match the contract.
- Malformed input fails as expected.
- Null/empty are handled per contract.
- Repeated calls with the same input return equal results.
- No side effects or input mutations occur.

JUnit Jupiter example (placed in `src/test/java/StringToProductCodeTest.java`):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class StringToProductCodeTest {

    private final StringToProductCode converter =
            new StringToProductCode();

    @Test
    void normalizesValidCode() {
        ProductCode actual = converter.convert(" sku-a123 ");
        assertEquals(new ProductCode("SKU-A123"), actual);
    }

    @Test
    void rejectsInvalidCode() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("not-a-sku"));
    }

    @Test
    void isDeterministicForSameInput() {
        ProductCode first = converter.convert("sku-b456");
        ProductCode second = converter.convert("sku-b456");
        assertEquals(first, second);
    }
}
~~~

Add JUnit Jupiter dependencies and the test platform plugin to the Gradle file if you want to run these unit tests. The example above illustrates assertions; keep it in the matching package or import the project's actual classes.

### 10.2. Testing Concurrency Safety

Do not test a converter only once. Share **the exact same instance** across multiple tasks, pass varied inputs, and assert matching outputs. This exposes bugs such as shared fields, mutable parsers, or unsafe caches.

You can expand the demo test:

- Increase task counts and loop iterations.
- Use inputs with varied characters and boundaries.
- Run the tests repeatedly on CI.
- Verify exceptions propagate back to callers via `Future`.
- Ensure the executor is shut down in `finally`.
- Do not assert task completion order if the program does not control scheduling.

Concurrency tests can still miss rare race conditions; combine code inspection, elimination of mutable state, and stress testing.

### 10.3. Integration Tests with ConversionService

Create a conversion service matching your application's configuration, register the converter once, and verify:

~~~java
DefaultConversionService conversions =
        new DefaultConversionService();
conversions.addConverter(new StringToProductCode());

ProductCode result =
        conversions.convert("sku-c789", ProductCode.class);
~~~

Test both direct converter calls and calls through the conversion service, since the wrapper may handle null or select converters by type descriptor.

### 10.4. Spring MVC Tests

Use `MockMvc` or real requests to test:

- Valid query/form parameters.
- Invalid parameters and `BindingResult`.
- Locale/formatting when using a `Formatter`.
- Concurrent requests hitting the same endpoint.
- Whether converter behavior is affected by request ordering.
- Whether exception handlers respond per contract.

MVC tests uncover converters registered in the wrong registry, overridden converters, or behavior differing from direct invocation. Do not replace integration tests with pure unit tests when changing framework configuration.

## 11. Designing for Locale- or Tenant-Aware Values

A pure converter should have stable output when the contract is fixed. Yet some representations genuinely require context, such as currency or display dates:

- Locale-formatted display data: use `Formatter<T>`, which receives `Locale` as a parameter, or format at the presentation layer.
- Monetary data: keep amount and currency as explicit types; never assume a `BigDecimal` carries its currency implicitly.
- Tenant: if the same string means different things per tenant, request-layer conversion may need explicit metadata. Avoid storing tenant into a mutable converter field.
- Time zone: use `ZoneId`/`OffsetDateTime` per contract; never let the server's timezone silently dictate parsing.

Example of an immutable formatter using `DateTimeFormatter`:

~~~java
public final class LocalDateFormatter implements Formatter<LocalDate> {

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE);
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return DateTimeFormatter.ISO_LOCAL_DATE.format(value);
    }
}
~~~

The example intentionally uses ISO formatting so it is locale-independent, even though the SPI accepts a locale. If you want localized patterns, construct or obtain a formatter from the passed locale on each call; never store the current locale in a field. `DateTimeFormatter` is immutable and thread-safe.

## 12. Choosing Between Stateful and Stateless

| Scenario | Recommendation |
| --- | --- |
| Parsing ID codes with a fixed regex | Stateless converter |
| Mapping enum strings to enums | Stateless converter or built-in conversion |
| Parsing ISO dates | Built-in formatter/conversion or immutable formatter |
| Parsing dates per request locale | Formatter using the locale parameter |
| Needing a DB lookup | Move to the service layer after parsing the key |
| Expensive lookup caching | Cache in service/repository layer with explicit policy |
| Needing tenant/user context | Pass context explicitly at the right layer; do not store on converter |
| Needing per-request mutable state | Tie to the request/binder, never to a singleton converter |

Not every converter is mathematically pure. Still, most input data conversions can be written as stateless functions. The fewer external dependencies a converter has, the easier it is to test and reuse, and the less likely it is to introduce race conditions.

## 13. Pre-Merge Review Checklist for a Converter

1. Are any instance fields mutable? If so, why are they needed and who synchronizes them?
2. Does the result depend solely on current input or also on a previous request's value?
3. Does it use `SimpleDateFormat`, `HashMap`, or any shared mutable helper?
4. Does it store Locale, user, tenant, request, binder, or `BindingResult`?
5. Does it call a database, HTTP endpoint, filesystem, or emit events?
6. Does it return an immutable type or an object sharing no mutable state?
7. Are null, empty, whitespace, invalid formats, and overflows covered by a clear contract?
8. Do exceptions preserve accurate semantics rather than being swallowed into null/defaults?
9. Is it tested with multiple inputs and the same instance across multiple threads?
10. Is the converter registered in the right conversion service/formatter registry?
11. Is `Formatter` used instead of `Converter` when locale is part of the contract?
12. Should conversion be replaced with a service lookup because logic goes beyond parsing/normalizing?
13. Does it log raw input or sensitive data?
14. Was performance checked via profiling before adding any cache or lock?

If you cannot clearly answer any question about shared state or side effects, revisit the design before placing the converter into a shared registry.

## 14. Common Errors and Fixes

**Results are intermittently right and wrong under high traffic.** Look for mutable instance fields, shared buffers, parsers, or caches; rewrite with local variables or immutable helpers, then add concurrency tests.

**Adding synchronized hurts throughput.** Locks can mask race conditions while preserving an unnecessarily stateful design. If the converter only parses input, eliminate shared state so no locks are needed.

**Direct converter calls pass while MVC tests fail.** Verify the converter is registered in the right `FormatterRegistry`/`ConversionService`; check whether the request goes through MVC binding or a JSON message converter.

**User A's locale leaks to User B.** Never hold locale in a field; use `Formatter` with its locale parameter or enforce an explicit format contract.

**Bad input turns into null.** Do not swallow exceptions. Keep absent input distinct from malformed input; return appropriate binding errors.

**Converter queries the database and occasionally times out.** Only parse the ID inside the converter; look up the entity in the service and handle not-found/authorization separately.

**Cache serves stale data.** Review cache policy, invalidation, and consistency; consider removing the cache if conversion itself is cheap.

**Concurrency tests pass yet production still fails.** Tests are not absolute proof. Inspect all collaborators to confirm zero mutable shared state, and verify the exact integration path and versions.

## 15. Official Documentation

- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework – Core Conversion SPI Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/Converter.html)
- [Spring Framework – ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework – ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
- [Spring Framework – Formatter SPI](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Java – DateTimeFormatter API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java – SimpleDateFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html)
- [Java Concurrency Utilities](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)

**Design principle:** treat a shared converter as a component that can receive many concurrent calls. Keep instances stateless, use local variables and immutable structures, accept context such as `Locale` via parameters when appropriate, and delegate I/O and business lookups to the service layer. That is the simplest way to keep converters deterministic, easy to test, and safe under concurrent request handling.
