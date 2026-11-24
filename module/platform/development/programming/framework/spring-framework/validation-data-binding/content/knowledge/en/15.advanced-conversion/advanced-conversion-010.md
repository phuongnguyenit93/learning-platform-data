# Controlling Cost, Side Effects, and Errors in Custom Spring Converters

A custom `Converter<S, T>` often looks tiny: take a source-typed value, normalize or parse it, and return the target type. Yet a converter can be invoked in the binding flow of many requests, many fields, and many threads. A seemingly simple conversion can become a CPU hotspot, allocate excessive temporary objects, repeatedly read files or query a database, mutate shared state, or throw exceptions improperly.

When designing a converter, four dimensions must be controlled:

1. **Execution cost**: CPU complexity, memory allocation, repeated parsing, lookups, and I/O.
2. **Side effects**: database writes, sending messages, mutating shared objects, reading clocks/external systems, and non-determinism.
3. **Conversion errors**: distinguishing invalid input, missing converters, infrastructure failures, and programming bugs; preserving field details during binding.
4. **Operability**: thread safety, logging, metrics, testing, and meaningful benchmarking.

A good rule of thumb is that a converter should only perform a **small, deterministic, testable, and idempotent-safe** mapping. Business workflows that persist data, call external services, or make authorization decisions belong in the service/domain layer rather than hidden inside a converter.

## 1. Where Do Converters Sit in the Processing Flow?

`Converter<S, T>` is Spring Core's strongly typed SPI:

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

`ConversionService` locates a converter matching the source and target types, then calls `convert(...)`. During property binding, `DataBinder` or `WebDataBinder` uses the conversion service to convert input values before assigning them to JavaBean properties.

```text
HTTP / PropertyValues / Java values
                 |
                 v
            DataBinder
                 |
                 v
       ConversionService
                 |
          lookup converter
                 |
                 v
         Converter<S, T>
          |           |
       success   conversion error
          |           |
          v           v
       setter     BindingResult / exception
          |
          v
      Java object
```

A converter can be invoked directly via `conversionService.convert(...)`, indirectly when `DataBinder` binds request parameters, multiple times within a single request when multiple properties/collection elements need conversion, or concurrently across many threads if the conversion service is shared.

**Do not assume a converter runs only once per HTTP request.** Call count depends on the number of values needing conversion and input structure. Collections/arrays can trigger element-by-element conversion; controllers or services can also call `convert` explicitly multiple times.

## 2. Converter Cost: Looking Beyond One Line of Code

Conversion cost is not limited to time spent inside `convert`:

| Cost Component | Example | Signal |
| --- | --- | --- |
| CPU | Complex regex, date/multi-format parsing, searching | Latency grows with invocation count or input length |
| Memory | Intermediate strings, matchers, temporary objects, new collections | Rising allocation rate and GC pressure |
| Lookup | Scanning large catalogs or re-parsing metadata every call | Latency grows as dataset/search scope grows |
| I/O | Reading files, HTTP calls, database queries | High latency, coupling to network/external services |
| Lock/contention | Synchronized caches or mutable singletons | Throughput drops under multithreading |
| Logging/telemetry | Logging full payloads or stack traces for every bad input | Log CPU/I/O overhead and data-exposure risk |

A `String → Integer` converter usually performs simple parsing. Yet if a `String → Customer` converter loads records from a database, each form can trigger a query per field or element. When a binder processes a list of 500 customer codes, 500 sequential queries become an N+1 bottleneck.

**Principle:** converters should transform representations and validate basic syntax; if current business state must be fetched, consider doing so after binding in the service layer with batch lookups, transactions, and explicit caching policies.

## 3. Writing Small, Stateless, Deterministic Converters

Example of a converter turning a product code string into a value object:

```java
public record ProductCode(String value) {
}

public final class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
            throw new IllegalArgumentException("Invalid product code");
        }

        return new ProductCode(normalized);
    }
}
```

This is an illustrative example; it requires importing `java.util.Locale` and Spring `Converter`. Good properties: no database reads/writes; no HTTP, file system, or broker calls; does not mutate input; does not depend on call order; output depends solely on input and defined rules; holds no per-request state in converter instances.

Converters must still be evaluated against realistic inputs: regexes running on huge strings still burn CPU; `trim()` and `toUpperCase()` allocate new strings. Enforce input length bounds at trusted boundaries if a field can receive large payloads.

### 3.1. Avoid Mutating Source Objects

Do not write converters that mutate a source collection or object in place and return a partially modified reference:

```java
// Avoid: mutating object state owned by the caller.
source.removeIf(String::isBlank);
return source;
```

A good converter returns a new target object or a normalized immutable value object. If a mutable source is referenced in multiple places, mutating it makes behavior order-dependent and can introduce bugs when multiple layers share the reference.

### 3.2. Do Not Store Per-Request Data in Fields

Converters can be shared by the registry. Avoid fields like `currentTenant`, `currentUser`, `lastInput`, or mutable non-thread-safe formatters. Instead, pass needed metadata via source/target descriptors if the SPI supports it, or move tenant/user-dependent logic into services where request context is managed explicitly.

## 4. Side Effects: What Belongs and Does Not Belong in a Converter?

*Side effects* are changes to state outside the returned result, such as writing to a database, sending email, updating a cache, publishing events, writing files, or mutating a shared object.

| Action in Converter | Assessment | Reason |
| --- | --- | --- |
| Trim/parse/normalize input | Usually appropriate | Pure representation transformation |
| Check code syntax | Usually appropriate | Deterministic from input |
| Create immutable value object | Appropriate | Does not alter external systems |
| Query database to find entity | Reconsider; usually belongs in service | Introduces I/O, N+1, state coupling |
| Save entity or increment balance | Inappropriate | Repeated conversion calls can repeat business operations |
| Send email/message or call API | Inappropriate | Retries/rebinding can cause duplicate actions |
| Mutate shared cache | High risk | Requires synchronization, eviction, and ownership |
| Log full payloads | Avoid | Increases I/O and risks exposing sensitive data |

Suppose a converter receives `"C-100"` and queries the database for the customer. A controller may bind the same field in multiple processing flows; tests may also invoke the converter repeatedly. If the converter also marks the customer as “accessed”, sends a notification, or updates state, a type conversion could inadvertently execute business actions multiple times.

Framework converter invocations do not guarantee *exactly once* semantics. Never use conversion calls as transaction boundaries or event triggers.

### Separating Conversion from Business Lookup

```text
Request containing customerCode
        |
        v
Converter: String -> CustomerId
        |
        v
DTO containing CustomerId
        |
        v
Application Service
        |
        +-- batch load customer
        +-- check permissions and status
        +-- execute business logic inside transaction
```

The converter only parses the code and constructs `CustomerId`. The service queries the repository, checks customer existence, user permissions, and allowed update status. This allows conversion to be tested without a database, while the service optimizes batch queries and manages transactions properly.

If product requirements genuinely demand turning an ID into an entity during binding, consider custom argument resolvers, application services, or abstractions with explicit caching/batching semantics; do not hide query chains inside an application-wide converter.

## 5. Thread Safety and Shared Lifecycle

Spring describes `ConversionService` as a **stateless** object designed to be initialized at application startup and shared across threads. Converters registered in the service must therefore also be thread-safe.

### 5.1. Unsafe Code Patterns

```java
public final class BadDateConverter
        implements Converter<String, Date> {

    private final SimpleDateFormat format =
            new SimpleDateFormat("yyyy-MM-dd");

    @Override
    public Date convert(String source) {
        try {
            return format.parse(source);
        } catch (ParseException ex) {
            throw new IllegalArgumentException(ex);
        }
    }
}
```

`SimpleDateFormat` is mutable and not thread-safe. If a singleton converter is used concurrently by multiple requests, the formatter can produce corrupt results or hard-to-reproduce errors.

Instead, choose immutable/thread-safe APIs:

```java
public final class StringToLocalDateConverter
        implements Converter<String, LocalDate> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ISO_LOCAL_DATE;

    @Override
    public LocalDate convert(String source) {
        return LocalDate.parse(source, FORMAT);
    }
}
```

Requires importing `java.time.LocalDate` and `java.time.format.DateTimeFormatter`. For custom formats, instantiate immutable formatters once at initialization rather than parsing the pattern on every call.

### 5.2. What If Caching Is Needed?

Caching conversion outputs can reduce cost when conversions are expensive and inputs repeat, yet caching adds state and management overhead:

- Bound cache size and eviction to prevent unbounded memory growth.
- Check whether keys must include tenant, locale, version, and required context.
- Handle stale data and invalidation.
- Ensure thread safety while avoiding coarse locks that degrade throughput.
- Never cache permission-dependent results if the key lacks security context.
- If negative-caching errors, set clear TTL and policies.

Before adding a cache, measure whether the bottleneck is truly the converter or an underlying lookup. Caching inside a converter can mask an N+1 design instead of fixing it at the right layer.

## 6. Separating Converter Lookup Cost from Converter Execution

`GenericConversionService` can cache converter lookups by source/target type and metadata. However, **caching converter lookup does not mean caching conversion results**.

```java
for (int i = 0; i < 1_000; i++) {
    service.convert("AB-123", ProductCode.class);
}
```

Even though the registry does not re-search for the converter from scratch on every call, `convert` still executes to build/obtain the target value on each invocation. If the converter reads a file or queries a database internally, that cost still repeats.

Additionally:

- `canConvert(String.class, Target.class)` indicates the registry has a conversion path between the two types.
- For collections/maps, outer convertibility can still be `true` while a single element fails conversion, causing `convert` to fail.
- Results can depend on `TypeDescriptor`, generic element types, annotations, or `ConditionalConverter`.
- `canConvert` does not guarantee every concrete value is valid.

When measuring performance, separate service/registry initialization time, converter lookup/preparation, converter execution on valid inputs, invalid input handling, allocation/GC, and I/O (ideally eliminating I/O from converters).

## 7. CPU and Memory Cost: Patterns to Avoid

### 7.1. Repeatedly Compiling Regexes

If a pattern is complex and the converter is called at high volume, avoid recompiling the pattern on every call:

```java
// Suboptimal: compiles pattern on every convert.
boolean valid = Pattern.compile("[A-Z]{2}-[0-9]{3}")
        .matcher(source)
        .matches();
```

You can create `Pattern` once:

```java
private static final Pattern CODE =
        Pattern.compile("[A-Z]{2}-[0-9]{3}");

public ProductCode convert(String source) {
    if (!CODE.matcher(source).matches()) {
        throw new IllegalArgumentException("Invalid code");
    }
    return new ProductCode(source);
}
```

`Pattern` is immutable and shareable; a `Matcher` is created per check. This is a small optimization grounded in real cost, not an invitation to turn every converter into complex code.

### 7.2. Duplicate Normalization Across Layers

Avoid trimming/uppercasing/parsing the same code in the converter, controller, service, and repository. Decide which layer owns normalization and preserve that invariant. If the `ProductCode` value object enforces canonical form, downstream layers do not need to re-normalize.

### 7.3. Avoid Building Oversized Object Graphs

A converter turning one line of input into a multi-level entity graph can trigger heavy allocations, lazy loading, or bidirectional relationships. Conversion should return compact value objects; loading entities and business graphs belongs in repositories/services.

### 7.4. Bound Input Sizes

Regexes can run very slowly on adversarial strings if an expression suffers catastrophic backtracking. For client inputs:
- Bound lengths at the request boundary.
- Prefer simple regexes with stable structure.
- Test long inputs and near-match failing cases.
- Do not parse unbounded large payloads inside converters.

## 8. Designing Diagnosable Conversion Errors

By Spring's contract, `Converter.convert(S)` receives a non-null source; when unable to convert, it may throw an unchecked exception. `IllegalArgumentException` is a common way to signal an invalid source value. Spring wraps the error appropriately inside the conversion mechanism, typically as `ConversionFailedException` carrying source/target types and cause.

| Error Kind | Example | Meaning |
| --- | --- | --- |
| Missing converter | `String` to an unregistered target type | `ConverterNotFoundException` |
| Converter exists, invalid input | `"abc"` to strictly formatted `ProductCode` | `ConversionFailedException` with cause such as `IllegalArgumentException` |
| Bug in converter logic | Wrong null assumption, bug, or internal dependency failure | Handle according to root cause |
| Field binding failure | Cannot convert property `code` | Can become a `FieldError` with code `typeMismatch` |
| Validation failure after bind | `@NotBlank` or business constraint violated | Validation error, distinct from conversion error |

### 8.1. Invalid Input and System Failures Are Not the Same

If a user enters `"A?"` for a product code, that is predictable invalid input. The converter can throw `IllegalArgumentException("Invalid product code")`.

If a converter calls an external service and that service times out, that is an infrastructure failure. Ideally converters should not do I/O. If architecture forces a remote call, do not wrap every exception as “invalid code”: users would fruitlessly edit valid input while the downstream service is down.

### 8.2. Do Not Use Exceptions for Normal Control Flow

Do not try parsing one format, catching an exception, and trying dozens of formats per call when a clearer deterministic dispatch exists. Exceptions should represent a failed conversion, not a routine loop control mechanism. For multiple date formats, consider a `Formatter` with a bounded format list and explicit selection rules.

### 8.3. Do Not Leak Data in Exceptions

Error messages should not contain tokens, passwords, private addresses, or full payloads. An error can record the field path, error code, and masked value. Internal stack traces may be logged server-side when needed for investigation, yet never return raw stack traces to clients.

## 9. Binding and BindingResult: Keeping Errors on the Right Field

When a custom converter is invoked within `DataBinder`, conversion errors can typically be recorded in `BindingResult` as a `FieldError`. That lets controllers or views display errors bound to the corresponding input.

Spring MVC controller example (integration snippet; requires DTO class, imports, converter bean, and MVC configuration):

```java
@PostMapping("/products")
String submit(
        @Valid @ModelAttribute("form") ProductForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "products/form";
    }
    productService.create(form);
    return "products/success";
}
```

`BindingResult` must appear immediately after its corresponding `@ModelAttribute` parameter. If `code=bad-value` fails conversion, the controller receives the binding error and must not invoke the business service as though the form were valid.

Illustrative inspection:

```java
FieldError error = result.getFieldError("productCode");
if (error != null) {
    String code = error.getCode();
}
```

Error codes are generated by Spring's resolution strategy; for type conversion failures, `typeMismatch` is a common code. Do not rely on default messages or compare full exception message strings in business logic; use the field, error code, and appropriate message resources.

**Caution:** not all input sources use the same mechanism. `@RequestBody` JSON goes through `HttpMessageConverter` (usually Jackson), which can raise `HttpMessageNotReadableException`. Form binding with `@ModelAttribute` goes through `WebDataBinder`. Identify the input source before diagnosing.

## 10. Retries and Idempotency

Converters should not produce side effects because re-invocations can happen in tests, retries, rebinding, or when multiple fields need conversion. Suppose a converter both parses a code and emits a `ProductCodeParsed` event. If the same data is processed again, the event could fire multiple times.

If the system needs to emit events, do so after business state has been accepted and persisted, using an appropriate transaction/outbox mechanism. **Do not place message publishing inside converters.**

Similarly, converters depending on current time or DB state can return different outputs for the same input across invocations. That makes caching/testing/retries nondeterministic. Keep converters as pure as possible; nondeterministic dependencies belong in services with explicit contracts and tests.

## 11. Observing Performance Without Creating New Problems

You can measure timing and call counts with metrics, without logging full input values. A good observability plan:

- Counter of conversions by type pair or converter name.
- Timer/histogram for latency.
- Error rate by error code, without attaching raw user input to metric tags.
- CPU/allocation profiling when bottlenecks appear.
- Tracking external dependencies in services/repositories rather than lumping everything into conversion metrics.

**Avoid high cardinality:** do not place product codes, user IDs, tenant IDs, or raw field values in metric labels. Each distinct value can create a new time series, causing excessive resource consumption in the monitoring system.

Logging should be structured, at sensible levels, and redacted. For expected invalid input, field path + error code usually suffices; full stack traces for every invalid input can generate massive log volume.

## 12. Benchmarking Properly

Do not evaluate a converter using a single invocation and a single `System.nanoTime` measurement. The JVM has JIT compilation, warm-up, GC, CPU scheduling, and host noise. When serious benchmarking is needed, use **JMH**:

1. Create separate benchmarks for successful parsing, failed parsing, and boundary inputs.
2. Initialize `ConversionService`/registry outside the measured region if measuring conversion latency rather than startup.
3. Run sufficient warm-up rounds, measurement iterations, and forks.
4. Use diverse/realistic inputs to avoid benchmarking only one happy branch.
5. Measure throughput, average/sample time, and allocation rate where appropriate.
6. Compare the baseline against the new converter under the same environment, JDK, and dataset.
7. If a converter performs I/O, measure service/I/O separately; do not fold network benchmarks into parsing performance claims.

Microbenchmarks cannot fully represent HTTP request latency. Integration tests and production telemetry reveal end-to-end impact.

### Pre-Optimization Checklist

- Do metrics show the converter is actually a bottleneck?
- Is the cost in parsing, allocation, locking, or I/O?
- Is any operation duplicated in other controllers/services?
- Can I/O be moved out of the converter or batched in a service?
- Can formatters/patterns be constructed immutably once?
- Does the input have length and structural bounds?
- Does optimization preserve expected outputs and errors?

Never sacrifice correctness or security to shave off a few trivial allocations.

## 13. Runnable Java 17+ Example: Converter Error Recorded in BindingResult

The following example uses Spring Framework 6.2.x without needing Spring Boot or an HTTP server. It demonstrates a stateless converter, exceptions for invalid inputs, and `DataBinder` recording conversion errors in `BindingResult`. The program shows that direct conversion and binding are two distinct call sites.

### 13.1. Project Structure

```text
converter-cost-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/ConverterErrorDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'converter-cost-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'example.ConverterErrorDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Use JDK 17+ and a compatible Gradle version, with Maven Central access for initial dependency download. `spring-context` brings in Spring Core/Beans/Context modules needed for `ConversionService` and `DataBinder`.

### 13.2. Full Source Code

**`src/main/java/example/ConverterErrorDemo.java`**

```java
package example;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.ConfigurableConversionService;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

import java.util.Locale;

public class ConverterErrorDemo {

    public record ProductCode(String value) {
    }

    public static final class StringToProductCodeConverter
            implements Converter<String, ProductCode> {

        @Override
        public ProductCode convert(String source) {
            String normalized =
                    source.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException(
                        "Product code must match AA-123");
            }

            return new ProductCode(normalized);
        }
    }

    public static final class ProductForm {
        private ProductCode productCode;

        public ProductCode getProductCode() {
            return productCode;
        }

        public void setProductCode(ProductCode productCode) {
            this.productCode = productCode;
        }
    }

    public static void main(String[] args) {
        ConfigurableConversionService service =
                new DefaultFormattingConversionService();

        service.addConverter(new StringToProductCodeConverter());

        ProductCode valid =
                service.convert(" ab-123 ", ProductCode.class);
        System.out.println("valid=" + valid);

        ProductForm form = new ProductForm();
        DataBinder binder = new DataBinder(form, "productForm");
        binder.setConversionService(service);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("productCode", "bad-value");

        binder.bind(values);

        FieldError error =
                binder.getBindingResult().getFieldError("productCode");

        System.out.println("boundValue=" + form.getProductCode());
        System.out.println("hasError=" + (error != null));
        System.out.println("errorField="
                + (error != null ? error.getField() : "<none>"));
        System.out.println("errorCode="
                + (error != null ? error.getCode() : "<none>"));
    }
}
```

### 13.3. Running the Program and Stdout

From the project directory:

```bash
gradle -q run
```

If the Gradle wrapper is present, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows.

**Expected stdout:**

```text
valid=ProductCode[value=AB-123]
boundValue=null
hasError=true
errorField=productCode
errorCode=typeMismatch
```

Explanation:

- The converter trims and uppercases valid strings, creating an immutable value object.
- The input `bad-value` fails the rule, so the converter throws `IllegalArgumentException`.
- When passing through `DataBinder`, the error is recorded in `BindingResult` under field `productCode`.
- `boundValue=null` because the setter never received a `ProductCode` from the invalid input.
- `typeMismatch` is a standard binding error code; the exact message depends on the message code resolver and message bundle.

The converter writes no database records, logs no raw input, holds no request state, and depends on no other thread. That makes it easy to share and test.

## 14. Testing Converters: Results, Errors, and Determinism

A solid test suite should verify:

| Group | Input | Expected |
| --- | --- | --- |
| Basic valid | `"ab-123"` | `ProductCode("AB-123")` |
| With whitespace | `"  ab-123  "` | Same normalized value |
| Wrong format | `"abc"` | Invalid input exception |
| Wrong prefix | `"1A-123"` | Invalid input exception |
| Missing numeric part | `"AB-"` | Invalid input exception |
| Very long string | Input exceeding contract limit | Controlled rejection at boundary or converter |
| Repeated | Same input multiple times | Identical result, no side effects |
| Concurrent | Multiple threads sharing service | No cross-request state, no wrong results |
| Binding wrong type | Form submits invalid code | `BindingResult` contains error on the right field |

### Pure Unit Tests for Converters

```java
@Test
void normalizesProductCode() {
    var converter = new StringToProductCodeConverter();

    assertEquals(
            new ProductCode("AB-123"),
            converter.convert(" ab-123 "));
}

@Test
void rejectsInvalidCode() {
    var converter = new StringToProductCodeConverter();

    assertThrows(
            IllegalArgumentException.class,
            () -> converter.convert("bad-value"));
}
```

These are **illustrative JUnit tests**; JUnit 5 and imports for `org.junit.jupiter.api.Test` and assertions are required. Pure unit tests need neither an `ApplicationContext` nor a database connection.

### Testing Thread Safety

If a converter is stateless and uses only immutable/thread-safe APIs, you can test the same instance concurrently with varied inputs. Concurrency tests do not prove absolute absence of race conditions; review the code and dependencies, and use appropriate stress tests/profilers.

### Testing Side Effects

If a converter could touch a dependency (a sign the design should be revisited), use mocks/spies to verify interaction counts, ensuring a request does not accidentally persist entities or publish messages. Better yet, move interactions to an application service where idempotency, transactions, and retry semantics are controlled.

## 15. Review Checklist for a Custom Converter

Before placing a converter into a shared registry, ask:

**Inputs and outputs**
- Are the source/target types accurate and explicit?
- Are whitespace, null, empty values, and Unicode characters handled per contract?
- Are inputs bounded and expensive regexes avoided?

**Cost**
- Are patterns/metadata parsed repeatedly?
- Are unnecessary large objects/collections allocated?
- Is there any I/O or N+1 lookup?
- Do benchmarks/profiles justify any optimization?

**Side effects and concurrency**
- Does it write to a database, publish events, call APIs, or mutate caches?
- Are there any per-request mutable fields?
- Are thread-safe APIs used when the service is shared?
- Does it depend on time or external state so identical inputs yield different results?

**Errors and operations**
- Does invalid input raise an appropriate exception?
- Are infrastructure errors disguised as data validation errors?
- Do binding errors preserve the field path for display?
- Do logs/metrics avoid raw PII and high cardinality?
- Are there unit tests for valid/invalid/boundary/concurrency cases and binder integration tests?

A high-quality converter has clear, predictable behavior, hides no business workflows, and adds no unnecessary system cost.

## 16. Key Takeaways and Official References

- `ConversionService`/converters can be shared; converters must be stateless and thread-safe.
- Cost must be evaluated across CPU, allocation, GC, lookup, contention, I/O, and logging.
- Avoid database writes, event publishing, or remote API calls inside converters; convert to value objects and handle business work in services.
- `canConvert` reflects type-level capability, not a guarantee that every element or concrete value will convert successfully.
- Invalid inputs commonly use unchecked exceptions like `IllegalArgumentException`; Spring can wrap them into `ConversionFailedException`.
- In property binding, conversion failures typically map to a `FieldError` with code `typeMismatch`; controllers must check `BindingResult` before calling business logic.
- Benchmark with JMH and production telemetry; never draw conclusions from a single `System.nanoTime` call.
- Avoid logging raw input and high-cardinality metric tags.

References:

- [Spring Framework — Core Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): converter contract, stateless ConversionService, and configuration.
- [Spring Framework — ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html): `canConvert`, `convert`, and collection/map conversion.
- [Spring Framework — Converter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/Converter.html): contract and requirements for converters.
- [Spring Framework — GenericConversionService source](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/GenericConversionService.java): converter lookup, caching, and error translation.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): conversion in property binding and BindingResult.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): JVM benchmarking tool when reliable microbenchmarks are needed.
