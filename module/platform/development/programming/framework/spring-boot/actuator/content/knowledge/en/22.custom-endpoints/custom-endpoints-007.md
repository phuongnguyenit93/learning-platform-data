# Type Conversion with ApplicationConversionService and @EndpointConverter

## 1. Why Does an Endpoint Need a Type Conversion Step?

An operations tool might send a request:

```text
GET /actuator/conversionpreview?attempts=3&enabled=true&backoff=250ms&range=2..4
```

On the request side, query values are strings. However, the Java method wants to receive:

- `int attempts` to work with numbers.
- `boolean enabled` to represent an on/off choice.
- `Duration backoff` to represent a duration with units.
- `WorkerRange range` to represent a worker range with structure and validity constraints.

If every operation received `String` and manually split strings, parsed numbers, and caught errors, input-handling logic would be duplicated. **Type conversion** centralizes value interpretation into a common mechanism before invoking the operation.

Spring Boot Actuator uses an `ApplicationConversionService` along with `Converter` or `GenericConverter` beans annotated with `@EndpointConverter` to convert HTTP/JMX inputs to the required parameter types. This contract is described in [Spring Boot 3.3: Input Type Conversion](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.input-type-conversion).

### Components to Distinguish

| Component | Role |
| --- | --- |
| `ConversionService` | API for requesting conversion of a value to a target type |
| `ApplicationConversionService` | Configures converters/formatters suited to many Spring Boot data types |
| `Converter<S, T>` | Rule converting one source type S to one target type T |
| `GenericConverter` | More flexible rule that can declare multiple type pairs and use type descriptors |
| `@EndpointConverter` | Qualifier for Actuator to select converter beans for operation inputs |
| JSON deserialization | Step of reading JSON text into initial data, distinct from parameter converters |

This lesson uses Java 21 and Spring Boot 3.3.0 to build a standalone runnable example.

## 2. Where Does Conversion Happen?

For an operation exposed over HTTP, you can picture:

```text
HTTP Request
    -> match operation and collect arguments by name
    -> read query/path or top-level fields of JSON body
    -> convert each argument to the required Java type
    -> invoke operation
    -> convert result to HTTP response
```

The type conversion step does not select the URL or HTTP method. Nor is it the step that serializes the result object to JSON.

In a JSON body such as:

```json
{
  "attempts": 3,
  "enabled": true,
  "backoff": "250ms",
  "range": "2..4"
}
```

numbers and booleans may already be represented as appropriate Java values by the JSON reader. `backoff` and `range` still need to be interpreted as `Duration` and `WorkerRange`.

Therefore, do not assume that **every** input to a converter is a string just because the request came over HTTP. Declare the exact type pairs that the converter actually supports.

If a required parameter is missing or a value cannot be converted to the required type, the operation is not invoked and a web endpoint returns 400. In JMX, errors are not represented as HTTP statuses; check the response mechanism of the protocol in use.

Parameter names are a separate part of the mapping process. Java code must be compiled with `-parameters` so the framework can read argument names. A correct converter cannot fix errors caused by missing parameter names or misspelled field names.

## 3. Use Built-In Capabilities Before Writing a New Converter

`ApplicationConversionService` is a specialization of `FormattingConversionService`, configured with Spring Boot's converters and formatters. It can be instantiated directly and also provides methods for registering converters into a registry. See the [ApplicationConversionService API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/ApplicationConversionService.html).

In this example:

| Input | Target Type | Result |
| --- | --- | --- |
| `"3"` | Integer/int | 3 |
| `"true"` | Boolean/boolean | true |
| `"250ms"` | Duration | 250 milliseconds |
| `"PT2S"` | Duration | 2 seconds |
| `"2..4"` | WorkerRange | Needs the example's custom converter |

When passing durations, use explicit units or formats like `250ms`, `2s`, or `PT2S`. Avoid relying on a unitless number that parties might interpret differently.

Do not rewrite a string-to-number converter just to accept `attempts=3`. Add a converter when you have a value type or input format that the existing mechanism does not express according to the desired contract.

### Being Convertible Does Not Mean Business-Valid

`"-1"` can convert to an integer. The type-conversion mechanism does not automatically know that the application only permits retry counts in the range 1..5.

Similarly, `Duration` representing a duration does not mean that duration fits timeout limits, resources, or system policies.

Separate three concerns:

1. **Representation:** can the value be parsed into the required type?
2. **Value type invariants:** does this object satisfy its own invariants?
3. **Operation rules:** given the caller and current state, is that value permitted?

A converter fits the first two parts when they belong to the stable meaning of the value type. The third part usually belongs to application handling logic and access policies.

## 4. Designing a Small, Clear Converter

We choose a contract representing a worker range:

```text
first..last
```

For example, `2..4` means workers 2 through 4. The sample `WorkerRange` type requires:

```text
1 <= first <= last <= 32
```

This is an input value with a single-string representation, not a requirement to bind an arbitrary JSON tree into a DTO.

### 4.1. Converter<S, T>

A converter declares clearly:

```java
implements Converter<String, WorkerRange>
```

Its workflow:

1. Normalize outer whitespace per the sample's policy.
2. Check the `first..last` syntax.
3. Parse the two parts into integers.
4. Construct `WorkerRange`, letting the constructor check invariants.

When the string is invalid, the converter throws `IllegalArgumentException`. The conversion mechanism wraps conversion failures; Actuator handles argument-mapping errors as 400 before invoking the operation.

Per [Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html), a converter should be thread-safe and may report invalid source values with an appropriate exception. In this sample, the converter holds no per-request state in fields and performs no I/O.

Do not put database queries, network calls, authorization checks, or job starts inside `convert()`. A conversion step should produce a clear result from its input without side effects.

### 4.2. When Is GenericConverter Needed?

`Converter<S, T>` fits when only one clear source–target type pair is needed. `GenericConverter` is useful when multiple type pairs are needed or `TypeDescriptor` must be read.

Do not use `GenericConverter` for every converter just to be “more flexible”. It increases responsibility for declaring type pairs and checking source/target types. Nor should you declare an overly broad converter such as from any `Object` to a custom type when the real contract only accepts strings.

## 5. Bean Registration and Qualifier Are Two Different Things

Example of proper registration for Actuator:

```java
@Bean
@EndpointConverter
WorkerRangeConverter endpointWorkerRangeConverter() {
    return new WorkerRangeConverter();
}
```

- `@Bean` creates an object managed by Spring.
- `@EndpointConverter` marks the object so the endpoint conversion mechanism selects it.
- `WorkerRangeConverter` implements `Converter<String, WorkerRange>`, providing the actual conversion rule.

Placing `@EndpointConverter` on an unregistered class does not create a bean automatically. Conversely, having an ordinary converter bean does not guarantee Actuator will use it for operations.

The sample uses a concrete class instead of a lambda expression so the source and target types are explicitly visible in the class declaration. When registering a converter, preserve enough type information for the discovery mechanism.

**Qualifiers are not an absolute isolation mechanism.** They only tell Actuator which converters to pick per Actuator's contract. Another system may have its own bean-collection rules; this issue is explained further in section 9.

## 6. Runnable Example Application

The application only previews values after conversion. It does not submit jobs, modify real worker configuration, or check permissions to manage an actual worker pool.

### 6.1. Project Structure and Dependencies

```text
endpoint-conversion-demo/
├── pom.xml
└── src/main/
    ├── java/example/endpointconversion/EndpointConversionApplication.java
    └── resources/application.properties
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>endpoint-conversion-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

The sample uses Maven and JDK 21; the compiler configuration from the Spring Boot starter parent preserves parameter names needed by operations. When adding components to an application that already has a build, check the `-parameters` flag in the existing configuration instead of replacing the entire build with this sample.

### 6.2. Java Code

File `src/main/java/example/endpointconversion/EndpointConversionApplication.java`:

```java
package example.endpointconversion;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.EndpointConverter;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.context.annotation.Bean;
import org.springframework.core.convert.converter.Converter;

@SpringBootApplication
public class EndpointConversionApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointConversionApplication.class, args);
    }

    @Bean
    PreviewEndpoint previewEndpoint() {
        return new PreviewEndpoint();
    }

    @Bean
    @EndpointConverter
    @ConditionalOnProperty(name = "demo.endpoint-qualified",
            havingValue = "true", matchIfMissing = true)
    WorkerRangeConverter endpointWorkerRangeConverter() {
        return new WorkerRangeConverter();
    }

    @Bean
    @ConditionalOnProperty(name = "demo.endpoint-qualified",
            havingValue = "false")
    WorkerRangeConverter ordinaryWorkerRangeConverter() {
        return new WorkerRangeConverter();
    }

    public record WorkerRange(int first, int last) {
        public WorkerRange {
            if (first < 1 || last > 32 || first > last) {
                throw new IllegalArgumentException(
                        "Expected 1 <= first <= last <= 32");
            }
        }
    }

    public static class WorkerRangeConverter
            implements Converter<String, WorkerRange> {
        private static final Pattern FORMAT =
                Pattern.compile("([0-9]+)\\.\\.([0-9]+)");

        @Override
        public WorkerRange convert(String source) {
            var match = FORMAT.matcher(source.trim());
            if (!match.matches()) {
                throw new IllegalArgumentException(
                        "Expected first..last");
            }
            return new WorkerRange(
                    Integer.parseInt(match.group(1)),
                    Integer.parseInt(match.group(2)));
        }
    }

    public record Preview(int attempts, boolean enabled, long backoffMs,
            int firstWorker, int lastWorker) {
    }

    @Endpoint(id = "conversionpreview")
    public static class PreviewEndpoint {
        private final AtomicInteger calls = new AtomicInteger();

        @ReadOperation
        public Preview read(int attempts, boolean enabled,
                Duration backoff, WorkerRange range) {
            return preview(attempts, enabled, backoff, range);
        }

        @WriteOperation
        public Preview write(int attempts, boolean enabled,
                Duration backoff, WorkerRange range) {
            return preview(attempts, enabled, backoff, range);
        }

        private Preview preview(int attempts, boolean enabled,
                Duration backoff, WorkerRange range) {
            calls.incrementAndGet();
            return new Preview(attempts, enabled, backoff.toMillis(),
                    range.first(), range.last());
        }

        public int invocationCount() {
            return calls.get();
        }
    }
}
```

The two converter beans are placed under opposing conditions to serve the experiment:

| demo.endpoint-qualified | Bean Created | Has @EndpointConverter |
| --- | --- | --- |
| true or omitted | endpointWorkerRangeConverter | Yes |
| false | ordinaryWorkerRangeConverter | No |

Each run has only one converter bean from the sample. Changing the property and restarting lets you test the difference between “bean exists” and “bean is selected by Actuator”.

The `calls` counter is only used to check whether the operation was invoked. `invocationCount()` has no operation annotation, so it does not become an Actuator URL. It can be read from the bean in a test.

### 6.3. Configuration and Running

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,conversionpreview
demo.endpoint-qualified=true
```

The sample listens only on loopback and omits Spring Security to separate learning conversion from authentication configuration. In a real system, appropriate access policies must be applied to management endpoints.

Run from the directory containing `pom.xml`:

```shell
mvn spring-boot:run
```

## 7. Observing Conversion via Query and JSON

### 7.1. Query String: Converting Strings to Java Parameters

In PowerShell, wrap the entire URL in quotes so the `&` character is not misinterpreted by the shell:

```powershell
curl.exe -sS 'http://127.0.0.1:8080/actuator/conversionpreview?attempts=3&enabled=true&backoff=250ms&range=2..4'
```

Response 200 with body:

```json
{"attempts":3,"enabled":true,"backoffMs":250,"firstWorker":2,"lastWorker":4}
```

The operation received an integer, boolean, Duration, and WorkerRange. It did not need to call `Integer.parseInt` for `attempts` or split `range` inside the method body.

### 7.2. JSON Body: Not Every Value Needs the Same Converter

Send POST using PowerShell:

```powershell
$r = Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8080/actuator/conversionpreview' -ContentType 'application/json' -Body '{"attempts":3,"enabled":true,"backoff":"250ms","range":"2..4"}'
$r.StatusCode
$r.Content
```

Result:

```text
200
{"attempts":3,"enabled":true,"backoffMs":250,"firstWorker":2,"lastWorker":4}
```

Top-level properties are matched to operation arguments. `attempts` and `enabled` in JSON are already a number and a boolean; `range` is still a string, so it needs the corresponding converter. The POST operation in the sample only previews the result and does not execute a background job.

### 7.3. Why Doesn't a Nested JSON Object Work Automatically?

Replace `range` alone with:

```json
{
  "attempts": 3,
  "enabled": true,
  "backoff": "250ms",
  "range": {
    "first": 2,
    "last": 4
  }
}
```

With the same sample application, the response is 400 and the operation is not invoked.

The source here is a map structure after reading JSON, not the string `"2..4"`. A `String -> WorkerRange` converter is not responsible for converting arbitrary JSON structures into `WorkerRange`.

That is also why `@EndpointConverter` should not be treated as a Jackson deserializer or an arbitrary DTO-binding mechanism. If the contract genuinely requires a complex body, choose an appropriate intake mechanism rather than widening the converter excessively to mask the difference.

### 7.4. An Ordinary Converter Is Still a Bean, but Not Selected by Actuator

Change the property and restart:

```properties
demo.endpoint-qualified=false
```

The application still has a `WorkerRangeConverter` bean, but this bean is not annotated with `@EndpointConverter`.

Resend the valid query from section 7.1. With this sample, the result is 400 and the operation is not invoked, because Actuator has no registered rule to convert the string `2..4` to type `WorkerRange`.

The example's `WorkerRange` type has two integer components and no constructor taking a String or factory method interpreting a String. Thanks to that, the experiment does not rely on another automatic conversion mechanism that might accidentally make the request succeed.

Change back to `demo.endpoint-qualified=true` to continue the remaining tests.

## 8. Testing Conversion Errors and Distinguishing Them from Validation

### 8.1. Input Matrix

Keep the other parameters valid as in the baseline query:

| Change | Result in Sample | Operation Invoked? |
| --- | --- | --- |
| range=two-four | 400 | No |
| range=4..2 | 400 | No |
| backoff=soon | 400 | No |
| attempts=three | 400 | No |
| enabled=maybe | 400 | No |
| Omit range parameter | 400 | No |
| JSON range is nested object | 400 | No |
| attempts=-1 | 200 | Yes |

The two errors on `range` have different origins:

- `two-four` violates the representation syntax accepted by the converter.
- `4..2` can be split into two numbers, but violates `WorkerRange`'s invariant.

Both fail during the step of converting to the input object, before the operation runs.

Conversely, `attempts=-1` converts to an int. The preview response contains:

```json
{"attempts":-1,"enabled":true,"backoffMs":250,"firstWorker":2,"lastWorker":4}
```

The sample deliberately performs no retry business logic to highlight the boundary of conversion. A real operation using retry counts must check appropriate bounds before starting work; do not treat successful parsing as proof that the request is permitted to execute.

### 8.2. Do Not Use null to Hide Invalid Input

Do not catch all errors inside a converter and return `null` or a default range. Doing so hides the cause and can put the operation into a state different from what the caller requested.

A converter is also not the place to handle a missing required parameter. When an input is missing, the parameter-binding mechanism may finish before calling the converter. If optional parameters or default values are needed, design that explicitly in the operation contract.

Do not conflate empty strings, whitespace-only strings, omitted parameters, and JSON null. In the sample's converter, a whitespace-only string after `trim()` fails the format check and is rejected.

### 8.3. Testing with ConversionService Does Not Replace Endpoint Testing

The snippet below illustrates direct API usage in Java code that already has the sample's dependencies. Put it inside a method to try; this is not a standalone program with `main`:

```java
var conversion = new org.springframework.boot.convert.ApplicationConversionService();

Duration backoff = conversion.convert("250ms", Duration.class);
System.out.println(backoff.toMillis());

conversion.addConverter(
        new EndpointConversionApplication.WorkerRangeConverter());

var range = conversion.convert(
        "2..4", EndpointConversionApplication.WorkerRange.class);
System.out.println(range);
```

With `import java.time.Duration` and the same package as the sample, stdout is:

```text
250
WorkerRange[first=2, last=4]
```

If converting `4..2`, the conversion service throws `ConversionFailedException` wrapping the cause from conversion. HTTP 400 only appears when that error is adapted into a web response by the operation-mapping mechanism.

An `ApplicationConversionService` created manually with `new` does not automatically look up `@EndpointConverter` beans in the Spring context. The snippet above explicitly calls `addConverter` on the instance in use.

Similarly, `canConvert(String.class, WorkerRange.class)` returning true only indicates a conversion path exists between the two types, not that every string is valid. Specific values must still be tested.

## 9. Actuator Scope, MVC, and Application Configuration

An application can have multiple conversion mechanisms side by side:

| Data Intake Point | Mechanism to Inspect |
| --- | --- |
| Actuator operation arguments | `ApplicationConversionService` and converters selected via `@EndpointConverter` |
| Spring MVC controller inputs | `ConversionService`/formatters and MVC configuration |
| `@ConfigurationProperties` properties | Configuration binding mechanism and `@ConfigurationPropertiesBinding` when a custom converter is needed |
| JSON body or JSON output | `HttpMessageConverter`/Jackson and JSON handling contract |

Do not assume adding a converter in one place configures all the others properly.

At the same time, one should not claim that a bean with `@EndpointConverter` can only ever be used by Actuator. Spring Boot's Spring MVC auto-configuration can register `Converter`/`GenericConverter`/`Formatter` beans into MVC according to its own rules. The Actuator qualifier does not automatically forbid that mechanism. See [Spring MVC auto-configuration and conversion service](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html#web.servlet.spring-mvc.auto-configuration).

For configuration properties, `@ConfigurationPropertiesBinding` is a different qualifier serving configuration binding; it is not an alias for `@EndpointConverter`. See [Properties Conversion](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion).

Therefore, when a converter works in a controller but an endpoint still reports 400, check whether Actuator actually selected the converter. Conversely, a successful Actuator request is not enough to prove configuration binding or JSON DTOs are configured as intended.

Do not replace the application's entire conversion service just to fix one endpoint input format. First identify the right type pair, the right registration location, and the right converter discovery mechanism.

## 10. Common Errors and How to Verify

| Error | Symptom | How to Check |
| --- | --- | --- |
| Converter class exists but is not a bean | Custom rule absent in application | Check `@Bean` or appropriate component registration |
| Bean exists but lacks `@EndpointConverter` | Actuator operation still cannot convert custom type | Check the qualifier of the bean Actuator selects |
| Lost parameter names | Input values not mapped properly | Check `-parameters` and field/query names |
| Passing nested object to scalar parameter | 400 even though object has reasonable-looking fields | Check source type after JSON parsing |
| Converter stores request data in fields | Data may mix under concurrent requests | Keep converters stateless per request |
| Using successful parse instead of validation | Out-of-policy numbers or durations continue through | Check bounds in value type or operation logic |
| Performing I/O inside `convert()` | Unpredictable latency and side effects during binding | Separate conversion from execution |
| Logging or returning full raw inputs and errors | May expose unnecessary information | Describe errors only per appropriate diagnostic contract |

A meaningful test suite for the sample should include:

1. Direct converter tests: valid syntax, invalid syntax, wrong order, boundaries 1 and 32.
2. Operation over HTTP: query and JSON scalar produce the same result.
3. Input errors: 400 response and invocation counter does not increment.
4. Bean discovery: an ordinary converter exists but does not substitute for a qualified converter.
5. Distinguishing validation: negative numbers parse but do not automatically satisfy business rules.

Testing the converter directly proves the conversion algorithm. Testing the endpoint additionally proves argument collection, converter selection, and preventing the operation from running when inputs cannot be mapped.

## 11. Reinforcement Exercises

1. Add test cases for `1..32`, `0..3`, `2..33`, and outer whitespace ` 2..4 `. Explain which layer accepts or rejects each case.
2. Change the input representation to `2-4` while keeping the `WorkerRange` type. Identify which parts must change and which do not need to change.
3. Add a retry limit of 1..5 for a real operation. Explain why this limit does not appear automatically when the parameter is declared as `int`.
4. Create one test that registers only an ordinary converter bean and one test that registers it with the right qualifier, then compare whether the operation gets invoked.
5. Explain why a `String -> WorkerRange` converter is not a mechanism for binding a JSON object `{"first":2,"last":4}` into a parameter.
6. If another source–target type pair is needed, evaluate whether to create a separate converter or use `GenericConverter`; do not widen to every `Object` without a clear contract.

A good answer identifies source data, target type, representation rules, where the converter is registered, and the boundary between conversion and execution.
