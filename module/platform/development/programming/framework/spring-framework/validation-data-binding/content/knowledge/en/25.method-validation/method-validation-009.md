# setAdaptConstraintViolations and Adapted Validation Results

## 1. Purpose of the Feature

In Spring Framework, method validation checks Jakarta Bean Validation constraints directly on **method parameters and return values**, especially public methods on Spring beans annotated with `@Validated` and invoked through a proxy. For example:

```java
@NotBlank
public String create(@NotBlank String code, @Min(1) int count) {
    return "created:" + code + ":" + count;
}
```

This declares two *preconditions* for parameters and one *postcondition* for the return value. With `MethodValidationPostProcessor` and a Jakarta Validation provider properly configured, Spring AOP can reject the call before running the method body if parameters are invalid, or catch an invalid result after the method body has run.

By default, when validation fails, the interceptor throws `jakarta.validation.ConstraintViolationException` carrying the provider's `ConstraintViolation<?>` instances. Starting in Spring Framework **6.1**, an alternative is available: configuring `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` adapts violations into **structured results following Spring's validation error model** and throws `org.springframework.validation.method.MethodValidationException`.

The goal is to handle errors by **method / parameter / nested property**, making it straightforward to use `MessageSource`, internationalization, standardized service error handling, and Spring Validation APIs. **Enabling this flag does not alter constraint rules, does not add validation to non-proxied beans, and does not automatically decide HTTP status codes.**

## 2. Comparing the Two Modes

| Aspect | Default: `false` | Adapted: `true` |
| --- | --- | --- |
| Where configured | `MethodValidationPostProcessor#setAdaptConstraintViolations(false)` or unset | `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` |
| Exception on failure | `jakarta.validation.ConstraintViolationException` | `org.springframework.validation.method.MethodValidationException` |
| Data representation | `Set<ConstraintViolation<?>>` from Bean Validation | `MethodValidationResult` and `ParameterValidationResult` entries |
| Error organization | Each violation carries its own metadata/path | Grouped by parameter or return value position, including nested errors |
| Error description source | `ConstraintViolation#getMessage()`, `getPropertyPath()`, `getConstraintDescriptor()` | `MessageSourceResolvable` with error codes, arguments, and default message |
| Errors when `@Valid` traverses a DTO | Violation with property path | `ParameterErrors` implementing `Errors`, with `FieldError` entries |
| Best fit | Code already built around Jakarta API or needing raw details | Integrating `MessageSource` and consistent Spring Validation handling |
| Catch contract | `catch (ConstraintViolationException ex)` | `catch (MethodValidationException ex)` |

**Neither mode is "more accurate" regarding constraints.** Both rely on the same Bean Validation provider. The primary difference is how violations are represented and which exception is thrown. If an application flips this flag, handlers and tests catching `ConstraintViolationException` must be updated for `MethodValidationException`.

## 3. Enabling the Flag in the Right Place in Spring

### 3.1. Plain Spring Framework: Registering the Post-Processor

In a Spring context with a Jakarta Bean Validation provider, you can declare:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

@Configuration
public class MethodValidationConfiguration {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        MethodValidationPostProcessor processor =
                new MethodValidationPostProcessor();
        processor.setAdaptConstraintViolations(true);
        return processor;
    }
}
```

This is a **configuration snippet to place inside a Spring application**, not a standalone runnable program. A `@Bean static` method registers the `BeanPostProcessor` early without instantiating the configuration class prematurely. The target service class still needs `@Validated` on the type and appropriate constraints. As Spring creates beans, `MethodValidationPostProcessor` attaches the AOP advisor to eligible beans.

### 3.2. Spring Boot: Avoiding Duplicate Post-Processors

Spring Boot can auto-configure method validation when it detects a Jakarta Validation provider, such as via `spring-boot-starter-validation`. To enable adaptation mode, you must **customize the `MethodValidationPostProcessor` that actually applies to your beans**, for instance by providing your own bean definition as above in line with your Boot version's auto-configuration rules.

Do not create multiple post-processors without knowing which bean processes your methods: advice may be applied twice or make diagnostics confusing. In applications customizing the validator/factory, preserve the intended provider and validation groups. This flag configures the **method-validation interceptor**, not `@Validated` or individual `@NotNull` annotations.

### 3.3. Infrastructure Prerequisites Still Apply

The flag only takes effect if:

1. A Jakarta Bean Validation provider (such as Hibernate Validator) and Spring Validation infrastructure are present.
2. The bean is Spring-managed and eligible via class-level `@Validated`.
3. Calls go through the Spring AOP proxy to an advisable method.
4. Constraints exist on parameters/return values or via `@Valid` cascades in the active context and group.

Calling `new MyService()`, self-invocation via `this.method()`, or calling non-advisable private/final methods will not magically gain method validation just because the flag is `true`.

## 4. Flow of Adapting ConstraintViolation to Spring Errors

Conceptually, when a method is invoked through a proxy:

```text
Caller
  │
  ▼
Spring AOP / MethodValidationInterceptor
  │
  ├── Before method body: validateParameters(...)
  │      ├── no violations → execute method
  │      └── violations found:
  │             ├── adapt=false → ConstraintViolationException
  │             └── adapt=true  → MethodValidationResult
  │                                → MethodValidationException
  │
  ├── Method body runs and returns
  │
  └── After method body: validateReturnValue(...)
         ├── no violations → return result to caller
         └── violations found: handle per the same flag configuration
```

When adapting, Spring uses a mechanism such as `MethodValidationAdapter` to map `ConstraintViolation` objects to Spring Validation's error model. Key types live in `org.springframework.validation.method`:

- **`MethodValidationResult`:** interface representing the result of one validation pass; provides target, method, whether the error is for parameters or the return value, error groups, and cross-parameter details.
- **`MethodValidationException`:** exception holding that result; exposes `MethodValidationResult` methods directly.
- **`ParameterValidationResult`:** groups direct errors for one parameter (or return-value position), with `MethodParameter` metadata, related argument value, and a list of `MessageSourceResolvable`.
- **`ParameterErrors`:** a subclass of `ParameterValidationResult` that also implements `org.springframework.validation.Errors`; used for nested property errors when cascading via `@Valid`.
- **`MessageSourceResolvable`:** carries prioritized error codes, arguments, and default message so a `MessageSource` can select a locale-specific message.
- **`FieldError`:** specific error on a property inside a nested object, such as `address.street`, accessible via `ParameterErrors#getFieldErrors()`.

Two failed constraints on the same parameter **do not necessarily produce two `ParameterValidationResult` entries**; they can appear as one result with two `MessageSourceResolvable` entries. When a parameter is a collection/array/map, the provider may produce separate results per invalid element, along with `getContainerIndex()` or `getContainerKey()`.

## 5. Inspecting the Result API: Which Methods to Use?

In **Spring Framework 6.2**, use these current APIs:

| API | What it is used for |
| --- | --- |
| `ex.getMethod()` | The validated method |
| `ex.getTarget()` | The target bean invoked by the advice |
| `ex.isForReturnValue()` | `false`: error in input; `true`: error in return value |
| `ex.getParameterValidationResults()` | List of results per parameter or return value |
| `ex.getValueResults()` | Direct validation errors on parameter values |
| `ex.getBeanResults()` | Nested bean validation errors as `ParameterErrors` |
| `ex.getCrossParameterValidationResults()` | Errors from constraints spanning multiple parameters (if any) |
| `ex.getAllErrors()` | Flattened list of errors as `MessageSourceResolvable` |
| `result.getMethodParameter()` | Parameter position metadata; index `-1` is typically used for return type |
| `result.getArgument()` | Associated parameter/return value; consider sensitive data before logging |
| `result.getResolvableErrors()` | Errors at that position |
| `result.getContainerIndex()/getContainerKey()` | Index/key when the error is inside a container |

**Version note:** `getParameterValidationResults()` was added in Spring Framework 6.2. The older `getAllValidationResults()` API is deprecated in 6.2; do not write new code against the deprecated name on 6.2+. On Spring 6.1, verify that version's method names before copying sample code.

Return errors are still represented with a `MethodParameter`, yet their semantics differ from input parameters. Use `isForReturnValue()` instead of guessing from parameter names or path strings.

## 6. Runnable Java 17 + Spring Framework 6.2.6 Example

This exercise uses plain Spring Framework without a web server. It creates a `@Validated` Spring bean, registers a single `MethodValidationPostProcessor` with `adapt=true`, and tests four cases:

1. Valid data.
2. Two direct parameter constraints failing together.
3. `@Valid` cascading into a record field.
4. A return-value constraint failing.

### 6.1. Structure

```text
adapted-method-validation/
├── pom.xml
└── src/main/java/demo/AdaptedValidationDemo.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>adapted-method-validation</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.6</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-aop</artifactId>
      <version>6.2.6</version>
    </dependency>
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
    </plugins>
  </build>
</project>
```

`spring-context` supplies ApplicationContext and Spring Validation, `spring-aop` supplies proxy infrastructure, Hibernate Validator is the Jakarta Validation provider, and `jakarta.el` supports message interpolation. The project uses Java 17 and does not depend on Spring Boot auto-configuration.

### 6.3. `AdaptedValidationDemo.java`

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.context.MessageSourceResolvable;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.FieldError;
import org.springframework.validation.annotation.Validated;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;
import org.springframework.validation.method.MethodValidationException;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Supplier;

@Configuration(proxyBeanMethods = false)
public class AdaptedValidationDemo {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        MethodValidationPostProcessor processor =
                new MethodValidationPostProcessor();
        processor.setAdaptConstraintViolations(true);
        processor.setProxyTargetClass(true);
        return processor;
    }

    @Bean
    CheckoutService checkoutService() {
        return new CheckoutService();
    }

    public record Address(@NotBlank String street) {
    }

    @Validated
    public static class CheckoutService {

        @NotBlank
        public String issue(@NotBlank String code, @Min(1) int count) {
            return "issued:" + code + ":" + count;
        }

        public String ship(@Valid Address address) {
            return "sent:" + address.street();
        }

        @NotBlank
        public String brokenReceipt(@NotBlank String code) {
            return "";
        }
    }

    private static String lastCode(MessageSourceResolvable error) {
        String[] codes = error.getCodes();
        return (codes == null || codes.length == 0)
                ? "UNKNOWN" : codes[codes.length - 1];
    }

    private static String describe(MethodValidationException exception) {
        List<String> lines = new ArrayList<>();

        for (ParameterValidationResult result
                : exception.getParameterValidationResults()) {

            int index = result.getMethodParameter().getParameterIndex();
            String place = index < 0 ? "return" : "arg" + index;

            for (MessageSourceResolvable error : result.getResolvableErrors()) {
                if (result instanceof ParameterErrors
                        && error instanceof FieldError fieldError) {
                    lines.add(place + "/field:" + fieldError.getField()
                            + "/" + lastCode(error));
                } else {
                    lines.add(place + "/value/" + lastCode(error));
                }
            }
        }

        Collections.sort(lines);
        return "return=" + exception.isForReturnValue()
                + "; " + String.join(", ", lines);
    }

    private static void run(String label, Supplier<String> action) {
        try {
            System.out.println(label + " => " + action.get());
        } catch (MethodValidationException exception) {
            System.out.println(label + " => " + describe(exception));
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AdaptedValidationDemo.class)) {

            // Obtain reference via Spring: methods are invoked through the AOP proxy.
            CheckoutService service = context.getBean(CheckoutService.class);

            run("VALID", () -> service.issue("A1", 2));
            run("BAD_INPUT", () -> service.issue("", 0));
            run("BAD_NESTED", () -> service.ship(new Address("")));
            run("BAD_RETURN", () -> service.brokenReceipt("A1"));
        }
    }
}
```

### 6.4. Run Command and Output

In the directory containing `pom.xml`, with Java 17+ and Maven 3.x installed, run:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.AdaptedValidationDemo
```

Lines **printed by the program itself** look like (excluding Maven, Spring, or Hibernate Validator logs if the environment configures logging):

```text
VALID => issued:A1:2
BAD_INPUT => return=false; arg0/value/NotBlank, arg1/value/Min
BAD_NESTED => return=false; arg0/field:street/NotBlank
BAD_RETURN => return=true; return/value/NotBlank
```

Explanation:

- **VALID:** both preconditions and postcondition pass; no exception.
- **BAD_INPUT:** parameter 0 is blank, parameter 1 is 0. Spring returns adapted errors per position; `isForReturnValue()` is `false`. The `issue` method never runs.
- **BAD_NESTED:** `Address.street=""` violates `@NotBlank`. Because the `Address` parameter has `@Valid`, the result uses `ParameterErrors` and `FieldError` with field `street`.
- **BAD_RETURN:** input is valid; `brokenReceipt` runs and returns an empty string, violating `@NotBlank` on the return value; `isForReturnValue()` is `true`.
- The code prints the **last error code** (`NotBlank`, `Min`) and sorts results, rather than depending on compiler parameter names or locale-sensitive messages. Positions `arg0`, `arg1` come from `MethodParameter#getParameterIndex()`.

The example uses a non-`final` `public static` nested service class so it can be class-proxied. `MethodValidationPostProcessor` is declared as a `static @Bean` with `setProxyTargetClass(true)` to explicitly use class proxies. If you manually call `new CheckoutService()` instead of getting the bean from the context, methods still run without **being validated by this advice**.

### 6.5. If You Switch the Flag to `false`

In the example above, replace:

```java
processor.setAdaptConstraintViolations(true);
```

with:

```java
processor.setAdaptConstraintViolations(false);
```

Violations are still caught by the provider, yet `catch (MethodValidationException)` **no longer catches the error**. You must switch the handler to `ConstraintViolationException` if you want the program to keep printing those cases. This is an observable API difference, not an indication that `false` disabled method validation.

Example handler for default mode (standalone snippet, do not paste verbatim into the main program):

```java
catch (jakarta.validation.ConstraintViolationException ex) {
    List<String> codes = ex.getConstraintViolations().stream()
        .map(v -> v.getConstraintDescriptor()
                .getAnnotation().annotationType().getSimpleName())
        .sorted()
        .toList();
    System.out.println("ConstraintViolationException: " + codes);
}
```

## 7. Handling Adapted Results in Real Applications

### 7.1. Extracting Errors per Parameter

Instead of parsing `exception.getMessage()` strings, work with the structured API:

```java
// Handling snippet inside catch (MethodValidationException ex),
// with org.springframework.validation.method.* imported.
for (ParameterValidationResult result : ex.getParameterValidationResults()) {
    int parameterIndex = result.getMethodParameter().getParameterIndex();
    Object rejectedArgument = result.getArgument();

    for (MessageSourceResolvable error : result.getResolvableErrors()) {
        String[] codes = error.getCodes();
        String defaultMessage = error.getDefaultMessage();
        // Map codes/message to a business error per the application contract.
    }
}
```

This is an illustrative integration snippet, not a standalone runnable class. `rejectedArgument` and `FieldError#getRejectedValue()` may contain personal or secret data. **Do not log or return raw values to clients** unless permitted; usually only the field, error code, and curated message are needed.

If you only want to separate direct vs. nested errors:

```java
List<ParameterValidationResult> direct = ex.getValueResults();
List<ParameterErrors> nested = ex.getBeanResults();

for (ParameterErrors errors : nested) {
    for (FieldError field : errors.getFieldErrors()) {
        // field.getField(), field.getCode(), field.getDefaultMessage()
    }
}
```

Cross-parameter constraint errors can appear in `getCrossParameterValidationResults()` in Spring 6.2. Do not assume total error count always equals `getParameterValidationResults().size()`, because a single parameter can have multiple errors and cross-parameter errors also exist.

### 7.2. Resolving MessageSourceResolvable by Locale

Spring provides `MessageSource` to turn error codes and arguments into messages. For example, inside a handler with an injected `MessageSource messageSource`:

```java
// Snippet used inside an appropriate handler:
Locale locale = Locale.forLanguageTag("vi-VN");

for (ParameterValidationResult result : ex.getParameterValidationResults()) {
    for (MessageSourceResolvable error : result.getResolvableErrors()) {
        String text = messageSource.getMessage(error, locale);
        // Use the localized text per the application's context/UI.
    }
}
```

For direct constraints on parameters, Spring generates prioritized codes such as:

```text
Min.myService#approve.amount
Min.amount
Min.int
Min
```

For fields inside a `@Valid` DTO, codes may look like:

```text
NotBlank.address.street
NotBlank.street
NotBlank.java.lang.String
NotBlank
```

These are **illustrative shapes** of the code list: object/method prefixes and parameter names can vary by provider, compiler, and configuration. `MessageSource` searches the message bundle from most specific to most general. If none match, the corresponding default message can typically be used; exact fallback behavior depends on `MessageSource` configuration.

Example properties in `messages_vi.properties` using general codes:

```properties
NotBlank=Giá trị không được để trống
Min=Giá trị phải đạt mức tối thiểu
```

General codes can affect many fields. In large applications, prefer specific codes so messages stay clear and avoid unintended overrides. For `Min`, `getArguments()` carries constraint metadata; inspect argument order before writing templates with `{0}`, `{1}` placeholders. Do not assume error code lists or argument ordering are constant across all sites/versions.

### 7.3. Unwrapping ConstraintViolation When Truly Needed

Adapted results do not expose `ConstraintViolationException#getConstraintViolations()` at the exception level. However, starting in Spring Framework 6.2, `ParameterValidationResult` can unwrap the underlying source behind a `MessageSourceResolvable` via `unwrap(...)`:

```java
// Example for Spring Framework 6.2:
for (ParameterValidationResult result : ex.getParameterValidationResults()) {
    for (MessageSourceResolvable error : result.getResolvableErrors()) {
        jakarta.validation.ConstraintViolation<?> original =
            result.unwrap(error, jakarta.validation.ConstraintViolation.class);
        // Use original metadata when there is a legitimate reason.
    }
}
```

Call this only when you know the source came from Jakarta Bean Validation and the API/version supports it. Typically most client handlers only need `MessageSourceResolvable` and `FieldError`, avoiding coupling back to raw metadata.

## 8. Impact of Parameter Errors, Return Values, and @Valid

Evaluation timing:

| Violation location | Is method body called? | Could side effects have happened? | `isForReturnValue()` |
| --- | --- | --- | --- |
| Direct constraint on parameter | No | Not from the blocked method body | `false` |
| Nested field error via `@Valid` on parameter | No | Not from the blocked method body | `false` |
| Direct constraint on return value | Yes | May have occurred | `true` |
| Cascade via `@Valid` on return value | Yes | May have occurred | `true` |

When a return value is invalid, throwing `MethodValidationException` **does not automatically guarantee rollback**. If the method has `@Transactional`, inspect advisor ordering and rollback rules. If the method already performed external actions (sending messages, HTTP calls), postcondition validation cannot undo them either.

`@Valid` only directs cascading; it is not synonymous with `@NotNull`. If an object parameter is `null`, cascading into child properties does not happen; to forbid `null`, add `@NotNull` where appropriate.

## 9. Distinguishing from Spring MVC Method Validation

Since Spring Framework 6.1, Spring MVC has **built-in method validation** for controller handlers, which can throw `HandlerMethodValidationException`. That is a separate web-layer mechanism, even though it uses related structured validation result abstractions.

Distinguish clearly:

- **Spring service with class-level `@Validated` and AOP method validation:** `MethodValidationPostProcessor` chooses exception mode via `setAdaptConstraintViolations(...)`.
- **Spring MVC controller using built-in method validation:** the framework has its own handling path and exception types, commonly `HandlerMethodValidationException` for method-level failures; `@Valid @RequestBody` may also raise `MethodArgumentNotValidException` depending on signature and constraints.

Do not conclude that enabling `setAdaptConstraintViolations(true)` converts all MVC errors into `MethodValidationException`. In Spring MVC 6.1+, documentation recommends removing class-level `@Validated` on controllers when using built-in method validation instead of class-level AOP.

Because **service** exceptions can propagate through a controller, the application must define how to translate them into HTTP responses in `@ControllerAdvice` or at the API boundary. Avoid assuming "`MethodValidationException` = HTTP 400": return-value errors are usually server-side programming bugs, and parameter errors may come from internal callers or API clients depending on context.

## 10. Designing Exception Handlers and Error Contracts

A well-designed handler typically needs to:

1. Explicitly choose which exception classes it handles: `ConstraintViolationException` in raw mode, `MethodValidationException` in adapted mode, or MVC's built-in exceptions.
2. Use structured metadata: method name, parameter index, nested field, error code, and locale. Never parse exception message strings with regex.
3. Expose only error details appropriate for the caller. Avoid returning raw arguments, rejected values, or internal service details.
4. Distinguish input vs. postcondition failures via `isForReturnValue()`.
5. Keep response format stable with an application-owned error model instead of coupling response DTOs directly to framework exception objects.
6. When multiple constraints/groups fail, decide whether to return one error or all errors; sort them if clients or tests expect deterministic ordering.

Example public error model (illustrative snippet, excluding full handler):

```java
public record ApiValidationError(
        String location,
        String code,
        String message
) {}
```

Here `location` might be `"arg0"` or `"arg0.street"` after mapping indexes/fields per your API contract. Avoid leaking internal class names or Java package paths into public contracts.

## 11. Testing and Diagnostics

Test suites should cover both **proxy routing** and **exception types**:

| Scenario | Adapt = `false` | Adapt = `true` |
| --- | --- | --- |
| Blank `@NotBlank` parameter | `ConstraintViolationException` | `MethodValidationException`, value result |
| Two parameters invalid together | Set of `ConstraintViolation` | Errors grouped by parameter position |
| `@Valid` DTO with invalid child field | Violation with property path | `ParameterErrors` with `FieldError` |
| Return value violates constraint | `ConstraintViolationException` | `MethodValidationException` with `isForReturnValue=true` |
| No constraints violated | Returns normally | Returns normally |
| Call via `this.inner()` | Inner method not advised by proxy | Same; flag does not fix self-invocation |
| JSON/HTTP binding error before service | Depends on web layer | Depends on web layer; unaffected by flag |

Integration tests through the Spring container are required to prove the flag and BeanPostProcessor actually take effect. Unit tests calling `new CheckoutService()` directly only test the method body, not AOP method validation.

When debugging:

- Verify a Bean Validation provider is present and the Spring version is 6.1 or newer.
- Verify the bean has `@Validated` on the class/type and constraints are on parameters or return values.
- Confirm the caller's reference is a Spring proxy, not an object instantiated with `new`.
- Check for duplicate post-processors, custom auto-configuration overrides, or a mismatched `ValidatorFactory`.
- On Spring 6.2, prefer `getParameterValidationResults()` and `getCrossParameterValidationResults()` where needed; avoid deprecated APIs.
- Do not use `getMessage()` to infer fields, error codes, or groups.
- For `ParameterErrors`, check `getFieldErrors()` when handling nested DTOs; for simple parameter values, the result may just be a `ParameterValidationResult`.
- Be careful when logging `getArgument()`, `FieldError#getRejectedValue()`, or full exceptions as they may hold sensitive data.

## 12. Common Misconceptions

**"Enabling the flag = enabling validation."** False. The flag only determines how violations are represented and which exception is thrown once method validation **is already active**.

**"Using `@Valid` always produces `ParameterErrors`."** Not necessarily. There must actually be nested errors; a valid `@Valid` parameter produces no error. Constraints directly on parameters produce value results; one signature can produce both kinds.

**"Using `MethodValidationException` loses all Jakarta information."** Not entirely. Spring preserves error codes, default messages, arguments, and provides `unwrap` on supported versions to retrieve the source of an adapted error. Still, do not assume the exception exposes the same direct API as `ConstraintViolationException`.

**"All adapted errors automatically become Vietnamese messages."** False. `MessageSourceResolvable` only supplies codes and arguments. Localized text requires configuring message bundles and resolving through `MessageSource` with the appropriate `Locale`.

**"`MethodValidationException` is thrown by every controller."** False. Spring MVC built-in method validation has its own pipeline; service AOP and MVC controllers must be distinguished.

**"Validating the result after the method runs means there are no side effects."** False. A postcondition check cannot automatically undo work already performed by the method body.

## 13. Key Takeaways

`setAdaptConstraintViolations(true)` on `MethodValidationPostProcessor` switches **method validation error reporting** from raw `ConstraintViolation` sets to `MethodValidationResult`/`ParameterValidationResult` entries inside `MethodValidationException`. That makes it easier to categorize direct parameter errors, nested field errors via `ParameterErrors`, return-value errors, and localizable messages via `MessageSourceResolvable`.

When applying it, configure the right post-processor, keep calls flowing through proxies, test both exception styles, and build a structured custom error contract that never leaks sensitive data.

## References

- Spring Framework 6.2 Reference — *Spring-driven Method Validation* and *Method Validation Exceptions*: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 Javadoc — `MethodValidationPostProcessor#setAdaptConstraintViolations`: https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
- Spring Framework 6.2 Javadoc — `MethodValidationResult`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/method/MethodValidationResult.html
- Spring Framework 6.2 Javadoc — `ParameterValidationResult` and `unwrap`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Framework 6.2 Javadoc — `ParameterErrors`: https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/validation/method/ParameterErrors.html
- Spring MVC Reference — *Validation*, distinguishing controller built-in vs. AOP: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html