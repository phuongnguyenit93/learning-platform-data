# BindingResult When Conversion or Instantiation Fails

## 1. The Big Picture

**Constructor binding** in Spring Framework creates a new object by taking input data, resolving constructor parameters, converting each value's type, and invoking the constructor. Spring `DataBinder` provides the `construct(DataBinder.ValueResolver)` API for this process (Spring Framework 6.1+).

Key insight: **parameter conversion errors** and **constructor execution errors** do not necessarily follow the same handling path.

- When a parameter like `age` expects `Integer` but the input is `"abc"`, type conversion can produce a `typeMismatch` error, recorded in `BindingResult` as a `FieldError`.
- When all parameters convert cleanly but the constructor itself throws `IllegalArgumentException` due to an invariant, Spring may throw `BeanInstantiationException`. Do not assume this exception is always turned into a `FieldError`.
- When a parameter is omitted, its value may be treated as `null` or handled according to parameter type/constructor policy; it does **not automatically** generate property binding's `required` error.
- When `BindingResult` contains errors, the target object **might** have been created or **might not** have been created. Always check `hasErrors()`, and never treat `getTarget() != null` as a certificate of valid data.
- When running in Spring MVC, errors can be passed to a `BindingResult` parameter right after `@ModelAttribute`, or routed to an exception handler by the framework. Do not equate all of these cases with Jackson exceptions when parsing `@RequestBody`.

This lesson focuses on the **"Constructor Binding"** context, meaning instantiating objects from untrusted data before passing them into business logic; do not confuse it with Java constructor dependency injection into Spring Beans.

### Objectives

After studying this lesson, you will be able to create a `DataBinder` with a null initial target; write your own `ValueResolver`; analyze `BindingResult` when type conversion fails; distinguish constructor-thrown exceptions; handle scenarios with or without a target, field errors, rejected values, and object errors; and design appropriate tests for controllers/CLIs.

## 2. Processing Flow and When Errors Form

Overview path:

~~~text
Input (query/form/map)
    |
    v
DataBinder(null, "input")
    |  setTargetType(ResolvableType.forClass(Input.class))
    v
construct(ValueResolver)
    |
    +--> find constructor and parameter names
    |
    +--> look up each value by name / nested path
    |
    +--> convertIfNecessary(value, parameterType)
    |       |
    |       +--> success -> store converted value
    |       |
    |       +--> TypeMismatchException
    |               |
    |               +--> BindingResult / FieldError ("typeMismatch")
    |
    +--> attempt to create target from arguments (depends on recorded errors and constructor kind)
            |
            +--> creation succeeds -> target may exist
            |
            +--> constructor fails -> target may not exist
                         |
                         +--> BeanInstantiationException thrown in some situations
                         +--> error may be recorded in BindingResult in special cases
                              (e.g., Kotlin nullability handling)

After construct:
    +--> check getBindingResult().hasErrors() and error details
    +--> use target in business logic only when there are no errors and target is valid
~~~

Core point in the Java API:

~~~java
DataBinder binder = new DataBinder(null, "input");
binder.setTargetType(ResolvableType.forClass(Input.class));
binder.construct(valueResolver);

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Read FieldError/ObjectError; do not pass object to business logic yet.
}
~~~

This is a **code fragment** from an application that already has the `Input` class, `valueResolver`, Spring dependencies, and imports for `DataBinder`, `ResolvableType`, `BindingResult`; the complete standalone runnable program is in section 6.

**Three preconditions before `construct(...)`:** the binder has no target yet, the target type has been declared via `setTargetType(...)`, and `ValueResolver` knows how to return values by parameter name. Without these preconditions, a configuration or programming error can arise before any useful binding result exists.

## 3. How Spring Finds Constructors and Parameters

Spring favors an appropriate constructor for data creation:

1. For a type with one suitable data constructor, Spring reads its parameters and looks up input values with matching names.
2. For a type with a suitable default/no-arg constructor, the framework may use standard JavaBean instantiation; properties must then be bound separately via setters if the caller permits.
3. For Java records, the canonical constructor and component names provide a natural model for constructor binding.
4. For regular classes, ensure **constructor parameter names exist in metadata** (e.g., compile with `-parameters` or use `@ConstructorProperties` when appropriate) and avoid ambiguous multiple constructors.
5. Spring MVC/WebFlux supports `@BindParam` to map request names differing from constructor parameter names, while a standalone `DataBinder` can configure `DataBinder.NameResolver`.

Example data-receiving class:

~~~java
public record CreatePerson(String name, Integer age) {}
~~~

Given `name=Lan&age=20`, Spring can find `name` and `age`, convert the string `"20"` to `Integer 20`, and invoke the canonical constructor.

If the client sends `personAge=20` instead of `age=20`, you cannot expect Spring to guess the field name. Especially when data has nested paths like `address.city`, the resolver must know those names; child values can be used to build nested objects via their constructors. For collections/lists/maps, Spring 6.2 supports both convertible strings and indexed keys in constructor binding.

**Do not confuse missing names with wrong types:** omitting `age` can yield `null` for `Integer`; whereas `age="abc"` is a present value that fails conversion to `Integer`. Those are two distinct problems and error codes.

## 4. What Does BindingResult Store When Conversion Fails?

`BindingResult` extends `Errors` and collects field-level and object-level error information in Spring:

| API | Meaning |
| --- | --- |
| `binder.getBindingResult()` | Accesses the result associated with the binder |
| `result.hasErrors()` | One or more errors have been registered |
| `result.getErrorCount()` | Total number of `FieldError` and `ObjectError` entries |
| `result.hasFieldErrors("age")` | Whether a specific field has errors |
| `result.getFieldError("age")` | First error for field `age`, or null |
| `result.getFieldErrors()` | List of field-level errors |
| `result.getGlobalErrors()` | Object-level errors (not tied to a specific field) |
| `fieldError.getField()` | Name of the failing field, potentially nested like `address.zip` |
| `fieldError.getCode()` | Primary error code; typically `typeMismatch` when conversion fails |
| `fieldError.getRejectedValue()` | Rejected input value, useful for selective redisplay |
| `fieldError.isBindingFailure()` | Indicates the error occurred during binding/conversion rather than normal constraint validation |
| `result.getObjectName()` | Bound object name, e.g., `input` |
| `result.getTarget()` | Target wrapped by the specific result; may be null |
| `binder.getTarget()` | Target held by the binder after attempting `construct`; may be null |

A `FieldError` is an `ObjectError` with extra field metadata. The `typeMismatch` code is usually expanded by `DefaultMessageCodesResolver` into multiple specific codes for `MessageSource` lookup. Avoid relying on the exact text of `getDefaultMessage()` or `toString()` to identify error types, since messages depend on locale, resolvers, and formatter/converter configuration.

Safe error-reading example:

~~~java
BindingResult result = binder.getBindingResult();

for (FieldError error : result.getFieldErrors()) {
    String field = error.getField();
    String code = error.getCode();
    boolean conversionOrBinding = error.isBindingFailure();
    Object rejected = error.getRejectedValue();

    // Build a structured response by field/code;
    // avoid logging or returning raw sensitive data.
}
~~~

This is a **code fragment** needing `BindingResult`/`FieldError` imports. For inputs containing passwords or tokens, `rejected` can hold secrets. Expose rejected values only when the contract and security policy explicitly permit it.

### An Often-Overlooked Point: When There Is No Target Yet

Constructor binding differs from normal property binding in that **the target starts as null**. If target creation does not complete, Spring can still retain constructor argument values for error reporting. `BindingResult.recordFieldValue(...)` is designed to record field values when an object cannot be built; `getFieldValue(...)` can return the recorded value or the corresponding rejected value. However, do not treat `getFieldValue(...)` as a lossless copy of the entire request; if raw requests are needed for auditing or retries, capture validated info at the boundary with separate security controls.

**Important:** do not assume `binder.getTarget()` and `result.getTarget()` are identical at every moment during a failed constructor binding pass; `BindingResult` can be created before the target finishes building. Check `result.hasErrors()` first before deciding whether the target may be used.

## 5. Distinguishing Failure Categories

| Situation | Example | Common mechanism | Signs |
| --- | --- | --- | --- |
| Type conversion failure | `age="xyz"` for `Integer age` | `TypeMismatchException` during conversion caught by binder | `FieldError`, code `typeMismatch`, `isBindingFailure=true` |
| Converter logic rejection | Malformed date string | Converter/formatter cannot convert | Field error from conversion if Spring catches and records it |
| Missing nullable parameter | `age` omitted for `Integer age` | May use null; not inherently an error by itself | Depends on constructor/validation |
| Missing primitive parameter | `age` omitted for `int age` | Check default conversion and argument handling | Do not infer property binding's `required` error by default |
| Constructor throws exception | Constructor checks `name.isBlank()` and throws | May wrap/throw `BeanInstantiationException` | Exception instead of a routine `FieldError` |
| Invalid constructor config | No suitable constructor, missing parameter name metadata | Configuration or object creation failure | Exception requiring separate handling |
| Bean Validation constraint | `@NotBlank`, `@Min` on DTO | Requires validation to actually be triggered | `FieldError`/`ObjectError` with constraint code |
| Cross-field invariant | `startDate > endDate` | Custom validator or constructor guard | Object/field error **or** exception depending on where checked |
| Nested constructor binding | `address.zip="oops"` | Conversion of nested object parameter fails | Nested field path such as `address.zip` if recorded |

**Do not conflate these errors:**

- `TypeMismatchException` is a type-conversion layer exception.
- `FieldError` is **error descriptor data** recorded into `BindingResult`.
- `BeanInstantiationException` is an **object instantiation exception**, not automatically a `FieldError`.
- `BindException` can be thrown when code explicitly calls `DataBinder.close()` while `BindingResult` has errors; `close()` does not create conversion errors or run validation on its own.
- `MethodArgumentNotValidException` is commonly raised in Spring MVC when a handler argument fails binding/validation and is not captured locally by a controller's `BindingResult`.

### Why Are Constructor Errors Not Always typeMismatch?

Suppose `new Invoice("INV-1", -10)` calls a constructor with:

~~~java
public Invoice(String id, int amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("negative amount");
    }
    this.id = id;
    this.amount = amount;
}
~~~

This is a **class/method fragment**, not a complete program. The value `"-10"` converts to `int -10` just fine. The exception originates from **logic inside the constructor**, not conversion. For stable request error codes, declare constraints in the validation/adapter layer rather than parsing `BeanInstantiationException` messages.

## 6. Standalone Runnable Java 17 Example (Spring Framework 6.2)

This example uses the real `DataBinder.construct()` API, a `ValueResolver` reading from a `Map`, and a Java record as target. We verify three branches:

1. Successful conversion with zero errors.
2. Invalid type data producing a `FieldError` in `BindingResult`.
3. A constructor guard throwing an exception even though conversion succeeded.

We also add a missing-field case to show that a missing nullable field **does not automatically become a typeMismatch**.

No Spring Boot or HTTP server is needed. You need **JDK 17+ and Maven**. Create a new folder for the example and add `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>constructor-binding-errors-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create `src/main/java/ConstructorBindingErrorsDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

import org.springframework.beans.BeanInstantiationException;
import org.springframework.core.ResolvableType;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class ConstructorBindingErrorsDemo {

    public record Input(String name, Integer age) {}

    public record StrictInput(String name, Integer age) {
        public StrictInput {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is required");
            }
        }
    }

    public static final class MapResolver
            implements DataBinder.ValueResolver {

        private final Map<String, String> input;

        public MapResolver(Map<String, String> input) {
            this.input = input;
        }

        @Override
        public Object resolveValue(String name, Class<?> targetType) {
            return input.get(name);
        }

        @Override
        public Set<String> getNames() {
            return input.keySet();
        }
    }

    private static DataBinder construct(
            Class<?> type, Map<String, String> values) {

        DataBinder binder = new DataBinder(null, "input");
        binder.setTargetType(ResolvableType.forClass(type));
        binder.setConversionService(new DefaultConversionService());
        binder.construct(new MapResolver(values));
        return binder;
    }

    public static void main(String[] args) {
        DataBinder valid = construct(
            Input.class, Map.of("name", "Lan", "age", "20"));

        System.out.println(
            "valid: errors=" + valid.getBindingResult().hasErrors());
        System.out.println(
            "valid: age=" + ((Input) valid.getTarget()).age());

        DataBinder bad = construct(
            Input.class, Map.of("name", "Lan", "age", "abc"));

        BindingResult result = bad.getBindingResult();
        FieldError ageError = result.getFieldError("age");

        System.out.println(
            "badAge: errors=" + result.hasErrors());
        System.out.println(
            "badAge: fieldError=" + (ageError != null));
        System.out.println(
            "badAge: typeMismatch=" +
            (ageError != null &&
                "typeMismatch".equals(ageError.getCode())));
        System.out.println(
            "badAge: rejected=" +
            (ageError != null ? ageError.getRejectedValue() : "<none>"));

        DataBinder missing = construct(
            Input.class, Map.of("name", "Lan"));

        System.out.println(
            "missing: errors=" + missing.getBindingResult().hasErrors());
        System.out.println(
            "missing: ageNull=" +
            (((Input) missing.getTarget()).age() == null));

        try {
            construct(
                StrictInput.class, Map.of("name", "", "age", "20"));
            System.out.println("guard: constructorFailure=false");
        } catch (BeanInstantiationException ex) {
            System.out.println("guard: constructorFailure=true");
        }
    }
}
~~~

Compile and run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ConstructorBindingErrorsDemo
~~~

**Program stdout**, excluding Maven environment messages:

~~~text
valid: errors=false
valid: age=20
badAge: errors=true
badAge: fieldError=true
badAge: typeMismatch=true
badAge: rejected=abc
missing: errors=false
missing: ageNull=true
guard: constructorFailure=true
~~~

### Output Analysis

**Valid case:** `age="20"` is converted to `Integer 20` by the conversion service. Record `Input("Lan", 20)` is instantiated; `BindingResult.hasErrors()` is false and the caller can use the target after checking any other application constraints.

**BadAge case:** the string `"abc"` cannot become `Integer`, so `DataBinder.construct()` records a field error for `age` with code `typeMismatch`, preserving the rejected value for user feedback. When a `FieldError` is present, code must not take a potentially constructed object into business logic. Do not rely on target presence instead of checking `hasErrors()`.

**Missing case:** because `age` is `Integer` (nullable) and the record has no guard/constraint against null, omitting the field does not produce a type mismatch in this example. If business rules require an age, declare/run appropriate validation.

**Guard case:** `age="20"` converts cleanly, and `name=""` is a valid String to the conversion service. `StrictInput`'s compact constructor itself throws `IllegalArgumentException`, which Spring surfaces as `BeanInstantiationException` in this branch. The program catches the exception explicitly instead of assuming a `FieldError` was generated.

**Example scope:** this code is designed and statically verified against the Spring 6.2 contract; when run in an application with custom converters, custom `BindingErrorProcessor`, Kotlin constructors, or non-default configuration, error details and handling paths may vary. Do not treat verbatim expected stdout as a cross-version API guarantee without running tests against your actual dependencies.

## 7. What If the Constructor Takes int Instead of Integer?

The example above intentionally uses `Integer`. `Integer` permits `null`, whereas primitive `int` cannot accept Java null in the same way. If `age` is omitted or conversion to `int` fails, the framework may record an error or fail when assembling arguments, depending on the pipeline and version.

Therefore:

- For **optional** input fields, represent that state with an appropriate wrapper/nullability and handle it in validation.
- For **required** fields, do not rely solely on `int` to signal "required"; enforce input requirements with constraints and structured errors.
- If you must distinguish **omitted field** from **explicit null**, a single `Integer` after binding may not retain presence metadata. Read raw input at the boundary when the contract distinguishes the two.
- Do not "fix" primitive errors by defaulting to `0` if `0` also has business meaning. Separate defaulting from validation.

### Do Not Confuse Property Binding's requiredFields

`binder.setRequiredFields("age")` applies to the **`bind(PropertyValues)`** path (property binding), not as a general way to make all constructor parameters required in `construct(ValueResolver)`. Constructor binding uses the parameters declared by the constructor, while presence/non-null/validity requirements must be designed separately via contracts and validation.

If a learner calls:

~~~java
binder.setRequiredFields("age");
binder.construct(valueResolver);
~~~

do not assume a `FieldError` with code `required` will appear just like `binder.bind(new MutablePropertyValues(...))`. The two APIs have different extension points and field-checking mechanisms.

## 8. When Target Is Null, BindingResult Is Still Useful

A common trap is thinking: "`getTarget() == null`, so there is no way to know what the user submitted." Spring provides mechanisms to retain errors even when object creation fails to complete.

Cases to distinguish:

1. **Binder has not called `construct()` yet:** target is null simply because it is uninitialized; that does not mean an error occurred.
2. **Constructor binding had conversion errors:** `BindingResult` can hold `FieldError` entries even without a completed object.
3. **Constructor accepted fallback arguments after an error:** a target might still be created, yet `BindingResult` contains errors; never treat that object as valid.
4. **Constructor threw an exception that Spring did not turn into an error:** `construct()` can exit with an exception; callers must handle that exception rather than always expecting an error list.
5. **Validation after target exists:** that is a separate phase; when `@Valid` or `binder.validate()` is triggered, constraints contribute validation errors.

For conversion errors, `FieldError.getRejectedValue()` is a more reliable source than trying to call getters on an incompletely constructed object. `BindingResult.recordFieldValue(...)` allows recording successfully converted fields for view/error reporting even when the target is null. Some APIs like `getModel()` can contain a null target alongside the binding result; callers must not treat the presence of a model key as proof of successful instantiation.

Error printing example:

~~~java
BindingResult errors = binder.getBindingResult();

if (errors.hasErrors()) {
    for (FieldError field : errors.getFieldErrors()) {
        System.out.printf(
            "%s: %s (%s)%n",
            field.getField(),
            field.getCode(),
            field.isBindingFailure() ? "binding" : "validation"
        );
    }
    // Do not call domain service with binder.getTarget().
}
~~~

This is a **code fragment**; import `BindingResult` and `FieldError`. In production logs, avoid writing rejected values of fields containing secrets to stdout or responses.

## 9. Constructor Argument Validation Differs from Instantiation Errors

Not all validity checks happen at the same step:

| Check type | When? | Typical outcome |
| --- | --- | --- |
| Converting `String` to `Integer`/date/enum | While resolving constructor arguments | Type mismatch error recorded if corresponding binding handling applies |
| Guard inside constructor | When constructor executes | May throw `BeanInstantiationException` via reflection |
| Constraints on record/component/field | When a Bean Validation provider is actually triggered | Constraint violations translated to validation errors per context |
| Custom Spring `Validator` | When calling `binder.validate()` or triggered by framework | `FieldError` / `ObjectError` in `BindingResult` |
| Business invariants needing DB | In service/domain after valid input | Domain error/transactional exception per architecture |

Example DTO using Jakarta Bean Validation, **declaration fragment** only:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreatePersonRequest(
    @NotBlank String name,
    @NotNull @Min(18) Integer age
) {}
~~~

Annotations do not run on their own when calling `new CreatePersonRequest(null, null)`; a provider and trigger point are needed (such as `@Valid` on a controller parameter or `Validator.validate(...)` called by the caller). When constructor binding already has errors, how Spring evaluates constructor arguments and constraints can depend on validation settings and version. Do not claim all constraint validation always executes after every conversion failure.

If the constructor itself has a throwing guard, `BeanInstantiationException` is likewise not a `@NotBlank` error automatically formatted as code `NotBlank`. For consistent field errors returned to clients, design validation and exception mapping explicitly.

## 10. Spring MVC: BindingResult Immediately After @ModelAttribute

In annotated Spring MVC controllers, a form/query request can be bound into a DTO via constructor. For binding/validation errors that the framework captures in `BindingResult`, the handler can inspect errors locally if declared in the right position:

~~~java
@PostMapping("/people")
ResponseEntity<?> create(
        @Valid @ModelAttribute("person") CreatePersonRequest request,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(
            result.getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getCode())
                .toList()
        );
    }
    return ResponseEntity.ok("created");
}
~~~

This is a **handler method fragment**, not standalone runnable code; it requires Spring Web MVC imports, `jakarta.validation.Valid`, and the `CreatePersonRequest` class from earlier. `BindingResult` must come immediately after the corresponding argument. If the object cannot be instantiated because the constructor throws an exception outside the framework's error-accumulation path, the handler is not guaranteed to run to inspect `result`.

Without a `BindingResult` directly after `@ModelAttribute`, Spring MVC 6.2 typically reports argument bind/validation failures via `MethodArgumentNotValidException`. When method validation is triggered by constraints directly on parameters/methods, `HandlerMethodValidationException` can occur. Meanwhile, `@RequestBody` JSON errors go through HTTP message conversion/Jackson; JSON parse/type/constructor-deserialization errors can raise `HttpMessageNotReadableException` before Jakarta validation runs. These cases differ from manually invoking `DataBinder.construct(...)` in a standalone application.

### HTTP API Handling Guidelines

- Return an appropriate HTTP status (usually `400 Bad Request` for invalid input data).
- Map `FieldError` to readable field paths and error codes, e.g., `age: typeMismatch`.
- Never return raw stack traces or Java reflection exception messages to clients.
- Provide `@ControllerAdvice`/`ResponseEntityExceptionHandler` for errors not handled locally.
- Prevent business events, database writes, or domain mutations from running when `BindingResult.hasErrors()`.

An immutable record class with constructor guards is a strong way to express invariants, yet **it does not guarantee every guard failure becomes a JSON field error**. Decide at the HTTP boundary between domain exceptions and validation errors.

## 11. Nested Constructors, Collections, and Error Path Information

Constructor binding does not handle only flat fields. Example:

~~~java
public record Address(String city, Integer zip) {}

public record Registration(
    String name,
    Address address
) {}
~~~

If input uses paths `address.city=Hanoi` and `address.zip=oops`, Spring can construct `Address` via its nested constructor and record a conversion error with path `address.zip`. However, nested object creation depends on the resolver reporting present names and Spring's rules for detecting data for nested branches.

With a custom `ValueResolver`, both methods must stay consistent:

~~~java
public Object resolveValue(String name, Class<?> type) {
    return input.get(name);
}

public Set<String> getNames() {
    return input.keySet();
}
~~~

This is an **implementation fragment of `DataBinder.ValueResolver`**, where `input` is a `Map<String, ?>`. `getNames()` is especially useful so Spring knows which nested paths exist; never return fabricated names or names inconsistent with `resolveValue`.

Spring 6.2 also supports constructor parameters of list, map, and array types, including indexed/map-key paths. With untrusted data, bound size, depth, and field name meanings to prevent oversized requests. Field errors on nested paths should be safely encoded/displayed, avoiding treating client-sent paths as unrestricted object graph access.

## 12. Common Design Mistakes

1. **Reading target before checking errors.** The target might have been constructed despite errors in `BindingResult`, or remain null. Always check `hasErrors()` before using it.
2. **Assuming every failure is a `FieldError`.** Constructor guards can throw `BeanInstantiationException` instead of becoming field errors.
3. **Thinking `construct()` is the same as `bind(PropertyValues)`.** One resolves constructor arguments; the other assigns properties and uses `allowedFields/requiredFields` rules.
4. **Using `setRequiredFields(...)` to enforce required constructor parameters.** That API belongs to property binding; use proper validation for constructor binding.
5. **Assuming missing input is always `typeMismatch`.** A nullable `Integer` can receive null without producing an error in simple setups.
6. **Using `int` or default `0` instead of representing missing fields.** This easily masks genuinely missing input.
7. **Overlooking constructor parameter name metadata.** Without proper metadata or `@BindParam`, the resolver cannot find expected values.
8. **Catching only `BindException` thinking it covers all instantiation errors.** `BeanInstantiationException` and configuration errors follow other paths.
9. **Logging raw rejected values verbatim.** Input may contain passwords, tokens, access codes, or sensitive data.
10. **Depending on message code list ordering or exact exception strings.** Resolver config, locale, and versions can alter details.
11. **Permitting unintended property binding after constructor binding.** For mutable objects, use dedicated input DTOs; Spring MVC may run property binding afterward unless restricted.
12. **Confusing `@RequestBody` with `DataBinder` constructor binding.** Jackson deserialization and JSON parse errors have their own pipeline.
13. **Assuming `close()` invokes validators.** `close()` only checks existing error state; validation must be triggered separately.
14. **Assuming failing to build the object discards all user input errors.** `BindingResult` can retain `FieldError` entries and recorded field values.
15. **Relying on constructor-thrown exceptions to build user messages.** Design structured validation errors when stable per-field feedback is required.

## 13. Recommended Test Cases

| Case | Input | What to verify |
| --- | --- | --- |
| Valid | `name=Lan&age=20` | No errors; target has exact type and converted values |
| Wrong type | `age=abc` | `BindingResult.hasErrors()` true; field `age` has `typeMismatch` |
| Nullable missing | `age` omitted | Outcome matches contract, not confused with conversion error |
| Blank required | `name=""` | Constraint validation or guard reflects the expected branch |
| Constructor throws | Guard throws `IllegalArgumentException` | Catch/map `BeanInstantiationException` when applicable |
| Nested wrong type | `address.zip=oops` | Error preserves exact nested parameter path |
| Conversion succeeds, domain invalid | `age=-2` | Distinguish conversion errors from business/constraint errors |
| Multiple conversion failures | Multiple fields invalid | Check FieldError count and paths, do not assume only one error |
| Name mismatch | Wrong alias submitted | Verify `@BindParam` or `NameResolver` behavior |
| Sensitive rejected value | Failing secret field submitted | Response/logs do not leak raw value |
| Validator not invoked | After construct without calling validation | Do not assume constructor-binding means Bean Validation ran |
| Controller path | With/without `BindingResult` right after `@ModelAttribute` | Verify error handling and HTTP status |
| JSON body path | Wrong JSON type with `@RequestBody` | Verify message conversion exception is not misattributed to DataBinder |

Do not test only `getTarget() == null`; tests must verify **error codes**, **field paths**, **rejected values when allowed**, **distinguishing conversion errors from constructor exceptions**, **whether the object is actually valid**, and how callers respond.

## 14. Safe Handling Checklist in Services and Controllers

1. Accept input via explicit DTOs/commands; never expose entities or privileged fields directly.
2. With constructor binding, verify argument names, nested paths, and conversion services; pin Spring versions when reproducibility is needed.
3. Call `construct(...)` within a boundary that properly handles instantiation exceptions.
4. Once `construct(...)` completes, retrieve `BindingResult` and check `hasErrors()` **before** using the target.
5. On conversion errors, report fields and error codes; never invoke domain logic with invalid data.
6. If constructors throw exceptions, separate config/programming bugs from input errors; never return stack traces or secrets to clients.
7. Trigger Bean Validation/custom validators when required; do not assume they run automatically on every binder call.
8. When consistent HTTP errors are needed, map `MethodArgumentNotValidException`/`HandlerMethodValidationException` and other exceptions according to their real types.
9. After input is valid, enforce service/domain rules and appropriate transactions; the binder does not guarantee all invariants are satisfied.
10. Write tests covering success, type mismatch, missing values, constructor guards, nested paths, and rejected-value security.

### Final Decision Diagram

~~~text
construct(ValueResolver)
        |
        +-- throws exception? ----- YES ---> Classify instantiation/config exception
        |                                    Do not blindly force into FieldError
        |
        NO
        |
        v
BindingResult result = binder.getBindingResult()
        |
        +-- result.hasErrors()? ---- YES ---> Iterate FieldError/ObjectError
        |                                     Return errors, do not pass target to domain
        |
        NO
        |
        v
target = binder.getTarget()
        |
        +-- target == null? ------- YES ---> No valid object: handle explicitly
        |
        NO
        |
        v
Validation/authorization/domain checks per contract
        |
        v
Execute business logic
~~~

**Takeaway:** `BindingResult` is the structured error store for a binding pass; `BeanInstantiationException` is one possible instantiation failure mode. Use both the binding result **and** proper exception classification, rather than collapsing every case into "failed to create object" or "definitely a typeMismatch".

## Official Documentation

- [Spring Framework 6.2 — Data Binding / Constructor Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — DataBinder.ValueResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — Spring MVC @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
