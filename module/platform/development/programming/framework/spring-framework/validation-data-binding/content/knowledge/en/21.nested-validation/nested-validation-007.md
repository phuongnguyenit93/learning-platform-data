# Optional, Unwrapping, and Validating Contained Values in Spring Bean Validation

## 1. The Problem: Validate the Wrapper Object or the Inner Value?

In Java 17+, `Optional<T>` represents a value that **may or may not be present**. With Jakarta Bean Validation (commonly used alongside Spring Framework), the following three questions are distinct:

1. Is the variable holding `Optional` non-`null`?
2. Does `Optional` contain an inner value?
3. If a value is present, is that value valid, and if it is a Java bean, are its nested properties validated?

For example, `Optional.empty()` is **a non-null `Optional` object that holds no value**; this differs from `Optional<String> nickname = null`. Also distinguish `Optional.of("   ")`: a `String` element is present, but its content is all whitespace.

Jakarta Validation provides **value extractors** for `Optional`, `OptionalInt`, `OptionalLong`, and `OptionalDouble`. Thanks to extractors, constraints can apply to the **wrapped element**, even though the element is not a standalone JavaBean field. However, **not every constraint placed directly on the wrapper automatically forwards to the element**.

In Spring, `LocalValidatorFactoryBean` typically bridges Spring with the Bean Validation provider (such as Hibernate Validator). The rules below are enforced when a validation pass actually occurs: `jakarta.validation.Validator.validate(bean)`, `@Valid`/`@Validated` at supported MVC entry points, or the corresponding Spring validation method. Annotations sitting alone do not cause data to validate itself.

**Key takeaway:** *Constraints on the wrapper, constraints on the type argument, and `@Valid` cascading are three different things.*

## 2. `Optional` and the Concept of an Absent Value

| Java Data | Wrapper Exists? | Element Present? | Element Observed via Extractor |
| --- | --- | --- | --- |
| `Optional.of("Alice")` | Yes | Yes | `"Alice"` |
| `Optional.of("   ")` | Yes | Yes | `"   "` |
| `Optional.empty()` | Yes | No | `null` per built-in extractor contract |
| `Optional.ofNullable(null)` | Yes | No | `null` |
| `Optional<String> value = null` | No | Cannot call `isPresent()` | Extractor is not invoked for null container |
| `OptionalInt.of(3)` | Yes | Yes | `Integer.valueOf(3)` |
| `OptionalInt.empty()` | Yes | No | `null` |

Jakarta Validation specifies that the `Optional<T>` extractor passes the contained value to `ValueReceiver.value(null, originalValue.orElse(null))`. A node name of `null` means `ConstraintViolation.propertyPath` typically does not add a separate node for the `Optional` class: if `Optional<@NotBlank String> nickname` fails, the path is usually `nickname`, not `nickname.value`.

**Subtle consequence:** `Optional<@NotNull String>` can flag `Optional.empty()` as a violation, because the extractor yields `null` for an absent element. Meanwhile, `@NotNull Optional<String>` checks the *wrapper object* itself; `Optional.empty()` is still a non-null object and is accepted.

## 3. Constraints on the Wrapper vs. Constraints on the Inner Value

### Validating the `Optional` Object

```java
@NotNull
private Optional<String> nickname;
```

`@NotNull` sits before the field type and validates the wrapper. It blocks `nickname == null` but **does not require** `nickname.isPresent()` to return `true`.

### Validating the Wrapped Element

```java
private Optional<@NotBlank String> nickname;
```

`@NotBlank` sits inside the generic angle brackets, directly on **`String`**. It requires the string to be non-null, non-empty, and not whitespace-only. With `Optional.empty()`, the extractor supplies `null`, so the `@NotBlank` constraint fails.

### Requiring Both Non-Null Wrapper and Valid Content

```java
@NotNull
private Optional<@NotBlank String> nickname;
```

The two annotation positions create two independent rules: `@NotNull` on the wrapper, `@NotBlank` on the extracted `String`. Because `Optional` should be initialized to `Optional.empty()` rather than `null`, many applications just choose a consistent initialization convention and test the binding flow.

### Example of Wrong Annotation Placement

```java
@NotBlank
private Optional<String> nickname; // Wrong placement for validating String
```

The standard **`Optional<T>` extractor is not annotated with `@UnwrapByDefault`**. Without explicitly requesting unwrapping, a constraint placed on the wrapper resolves against the `Optional` type. Standard `@NotBlank` has a validator for `CharSequence`, not for `Optional`, so the provider typically throws `UnexpectedTypeException` (e.g., Hibernate Validator message HV000030).

**Preferred fix:** use `Optional<@NotBlank String>`. Reading the declaration immediately shows that the constraint targets the inner element; no provider customization or custom validator is needed when using standard `Optional`.

## 4. Truth Table: Null, Empty, Whitespace String, and Valid String

Consider three distinct declarations:

- A: `@NotNull Optional<String> value`
- B: `Optional<@NotNull String> value`
- C: `Optional<@NotBlank String> value`

| Wrapper Value | A: non-null wrapper | B: non-null element | C: non-blank element |
| --- | --- | --- | --- |
| `Optional.of("ok")` | Passes | Passes | Passes |
| `Optional.of("  ")` | Passes | Passes | **Error** |
| `Optional.of("")` | Passes | Passes | **Error** |
| `Optional.empty()` | Passes | **Error** | **Error** |
| `null` | **Error** | Element not checked | Element not checked |

When the wrapper is `null`, the built-in extractor is not called; if you want an explicit error for a null wrapper, add a constraint on the **wrapper**. Conversely, if a field is *genuinely optional*, **do not** place `@NotNull` or `@NotBlank` on the element unless business rules treat `Optional.empty()` as an error.

Example of an optional field that, if present, may be at most 30 characters long:

```java
private Optional<@Size(max = 30) String> displayName =
        Optional.empty();
```

`@Size` permits `null`, so `Optional.empty()` **passes**, `Optional.of("")` also passes a max-only rule, and `Optional.of("...")` exceeding 30 characters fails. This is the "skip if omitted; cap length if provided" design.

If business logic requires *rejecting whitespace-only strings while still allowing absence*, you can use a custom `String` constraint that accepts `null` and rejects blank strings, or normalize input first and apply clear rules. `@NotBlank` inherently rejects `null`, so it cannot directly express "empty optional allowed, blank string disallowed."

## 5. Cascading `@Valid`: Validating a Java Bean Inside `Optional`

Suppose you have:

```java
public class Address {
    @NotBlank
    private String city;
}
```

When a DTO has the field:

```java
private Optional<@Valid Address> deliveryAddress;
```

`@Valid` placed on the type argument indicates that **if an `Address` is present**, Bean Validation continues into that object and checks `Address.city`. Examples:

- `Optional.of(new Address("Hanoi"))`: `city` constraint passes.
- `Optional.of(new Address(""))`: cascading detects the `city` violation.
- `Optional.empty()`: the element reported by the extractor is null; **cascading skips null**, so no error is generated by `@Valid`.
- `deliveryAddress == null`: no element to cascade into; to require the wrapper to exist, add `@NotNull` outside the wrapper.

If the goal is **address must be present and valid**, use:

```java
@NotNull
private Optional<@NotNull @Valid Address> deliveryAddress;
```

The outer constraint requires the wrapper to be non-null; the inner `@NotNull` requires the element to be present; `@Valid` traverses into `Address`'s properties. In practice, for a field that must always have a value, a direct `@NotNull @Valid Address deliveryAddress` field (without `Optional`) is usually easier to bind and read.

**Do not place `@Valid` on both the wrapper and the type argument** of the same container. The specification recommends choosing only one location to avoid duplicate cascade checks; for generic containers, placing it on the type argument makes intent clearer.

`@Valid` is a **cascade marker, not a requiredness constraint**. It does not replace `@NotNull` and does not run automatically unless an actual Bean Validation pass executes.

## 6. The Value Extractor Mechanism Under the Hood

Jakarta Validation 2.0+ (`jakarta.validation.*` namespace on Spring Framework 6+/Boot 3+) supports **container element constraints** via `ValueExtractor<T>`.

Example implementation illustrating the semantics of the built-in `Optional` extractor:

```java
import java.util.Optional;

import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.ValueExtractor;

public final class OptionalExtractorExample
        implements ValueExtractor<Optional<@ExtractedValue ?>> {

    @Override
    public void extractValues(
            Optional<?> originalValue, ValueReceiver receiver) {
        receiver.value(null, originalValue.orElse(null));
    }
}
```

This is **illustrative code showing how an extractor works**. **Do not re-register this extractor in a normal application**, because the Jakarta Validation provider already supplies the standard extractor for `Optional`, and duplicate registration can cause conflicts.

Meaning of the two arguments to `receiver.value(...)`:

1. **`nodeName` = null**: does not add an extra container element node to the property path. For a single-value wrapper, element errors typically attach directly to the wrapper's property name.
2. **`element = originalValue.orElse(null)`**: passes the unwrapped value to the constraint/cascade processor; `Optional.empty()` becomes `null`.

Inside the provider, extractors are selected based on the container type and the type argument index bearing the constraint. For nested containers, the provider chains multiple extractors in order:

```text
OrderForm
  |
  +-- List<Optional<@NotBlank String>> codes
          |
          +-- List extractor: extracts elements [0], [1], ...
                       |
                       +-- Optional extractor: extracts String or null
                                     |
                                     +-- @NotBlank validates String
```

That is why `List<Optional<@NotBlank String>>` can validate two levels deep without manual loops. A custom wrapper without an extractor generally needs its own `ValueExtractor` implementation.

## 7. `@UnwrapByDefault`, Implicit Unwrapping, and Explicit Unwrapping

**Unwrapping** means instructing Bean Validation to apply a constraint to the **wrapped element** rather than directly to the wrapper object itself. Three cases must be distinguished:

| Case | Mechanism | Example |
| --- | --- | --- |
| Constraint placed directly on type argument | Extractor selected by annotation position | `Optional<@NotBlank String>` |
| Constraint placed on wrapper whose extractor carries `@UnwrapByDefault` | **Implicit unwrapping** | `@Min(1) OptionalInt count` |
| Constraint placed on wrapper using payload `Unwrapping.Unwrap` | **Explicit unwrapping** | `@NotBlank(payload = Unwrapping.Unwrap.class) Optional<String> code` |

The specification requires the built-in extractors for `OptionalInt`, `OptionalLong`, and `OptionalDouble` to carry `@UnwrapByDefault`. Therefore:

```java
@Min(1)
private OptionalInt count;
```

`@Min` does not run on the `OptionalInt` class; the provider applies it to the `Integer` extracted by the extractor. `OptionalInt.of(0)` fails, and `OptionalInt.of(2)` passes. **`OptionalInt.empty()` is reported by the extractor as null, and `@Min` treats null as valid**, so `empty()` is not rejected by `@Min`.

With `OptionalDouble`, choose a constraint supporting `Double` such as `@Positive`; do not rely on `@Min` supporting `double` across all providers (the specification does not mandate floating-point support for `@Min`/`@Max`).

### Explicit Unwrap Using Payload

When you want to keep an annotation on the generic wrapper for structural compatibility, you can use:

```java
@NotBlank(payload = Unwrapping.Unwrap.class)
private Optional<String> code;
```

With the standard `Optional` extractor, `Unwrapping.Unwrap` instructs the provider to validate the inner `String` value. This is a Jakarta API (`jakarta.validation.valueextraction.Unwrapping`), not Java's `Optional.orElse(...)` or `jakarta.validation.Validator.unwrap(Class)`.

**Preference:** when writing new code, `Optional<@NotBlank String>` is clearer and needs no payload. Explicit unwrapping is useful when specifying the validation target of a declaration-level constraint.

### Preventing Unwrapping with `Unwrapping.Skip`

If an extractor is marked `@UnwrapByDefault`, you can force a constraint to validate the **wrapper** using:

```java
@NotNull(payload = Unwrapping.Skip.class)
private OptionalInt count;
```

This only checks whether the `count` variable is non-`null`. `OptionalInt.empty()` is a non-null wrapper and therefore **passes**. In contrast, **`@NotNull OptionalInt count`** (without Skip) **implicitly unwraps**, turning `OptionalInt.empty()` into `null` for `@NotNull` to evaluate and report an error.

**Do not use both** `Unwrapping.Unwrap` and `Unwrapping.Skip` on the same constraint: that is a conflicting configuration and may throw `ConstraintDeclarationException`.

## 8. Absent Values with `OptionalInt`, `OptionalLong`, `OptionalDouble`

These three specialized classes have no generic type argument:

```java
@Min(1)
private OptionalInt seats;

@Positive
private OptionalLong bytes;

@Positive
private OptionalDouble ratio;
```

Their extractors are annotated with `@ExtractedValue(type = Integer.class)`, `Long.class`, and `Double.class` respectively, along with `@UnwrapByDefault`. Thus, declaration-level numeric constraints can run on the extracted element.

| Data | Constraint | Result |
| --- | --- | --- |
| `OptionalInt.of(0)` | `@Min(1)` | Violation |
| `OptionalInt.of(3)` | `@Min(1)` | Passes |
| `OptionalInt.empty()` | `@Min(1)` | Passes due to null element |
| `OptionalInt.empty()` | `@NotNull` | Violation after implicit unwrap |
| `OptionalInt.empty()` | `@NotNull(payload=Unwrapping.Skip.class)` | Passes because wrapper is non-null |
| `OptionalLong.of(-1)` | `@Positive` | Violation |
| `OptionalDouble.of(0.5)` | `@Positive` | Passes |

Using `OptionalDouble` does not eliminate floating-point precision risks; for currency or high-precision decimal rules, choose `BigDecimal` and design nullable/optional semantics explicitly.

## 9. Runnable Example: Java 17 + Spring Boot + Bean Validation

The following example demonstrates the rules with **a complete program**: validating wrappers, elements, cascading, and `OptionalInt`, while also illustrating explicit unwrapping and misplaced `@NotBlank`. It uses Spring Boot 3.5.8 (a released version) to pin the version in this learning example, Maven, and JDK 17+.

Structure:

```text
optional-validation-demo/
├── pom.xml
└── src/main/java/demo/OptionalValidationDemo.java
```

### File `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>optional-validation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

### File `src/main/java/demo/OptionalValidationDemo.java`

```java
package demo;

import java.util.Comparator;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.UnexpectedTypeException;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.Valid;
import jakarta.validation.valueextraction.Unwrapping;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OptionalValidationDemo {

    public static void main(String[] args) {
        SpringApplication.run(OptionalValidationDemo.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(jakarta.validation.Validator validator) {
        return args -> {
            Profile good = new Profile(
                    Optional.empty(),
                    Optional.of("Mai"),
                    Optional.of(new Address("Ha Noi")),
                    OptionalInt.of(2));
            print("Good", validator.validate(good));

            Profile absent = new Profile(
                    Optional.empty(),
                    Optional.empty(),
                    Optional.empty(),
                    OptionalInt.empty());
            print("Absent", validator.validate(absent));

            Profile invalid = new Profile(
                    Optional.empty(),
                    Optional.of("   "),
                    Optional.of(new Address("")),
                    OptionalInt.of(0));
            print("Invalid", validator.validate(invalid));

            Profile nullWrapper = new Profile(
                    null,
                    Optional.of("Mai"),
                    Optional.empty(),
                    OptionalInt.of(2));
            print("Null wrapper", validator.validate(nullWrapper));

            print("OptionalInt required",
                    validator.validate(
                            new PrimitiveRequired(OptionalInt.empty())));

            print("Explicit unwrap",
                    validator.validate(
                            new ExplicitUnwrap(Optional.of(" "))));

            try {
                validator.validate(new IncorrectPlacement());
            } catch (UnexpectedTypeException ex) {
                System.out.println("Wrong placement: "
                        + ex.getClass().getSimpleName());
            }
        };
    }

    static void print(
            String title,
            Set<? extends ConstraintViolation<?>> violations) {

        String paths = violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(", "));
        System.out.println(title + ": " + violations.size()
                + (paths.isEmpty() ? "" : " [" + paths + "]"));
    }

    public static final class Profile {
        @NotNull
        private final Optional<String> wrapper;

        private final Optional<@NotBlank String> nickname;

        private final Optional<@Valid Address> address;

        @Min(1)
        private final OptionalInt seats;

        public Profile(Optional<String> wrapper,
                       Optional<String> nickname,
                       Optional<Address> address,
                       OptionalInt seats) {
            this.wrapper = wrapper;
            this.nickname = nickname;
            this.address = address;
            this.seats = seats;
        }
    }

    public static final class Address {
        @NotBlank
        private final String city;

        public Address(String city) {
            this.city = city;
        }
    }

    public static final class PrimitiveRequired {
        // OptionalInt is implicitly unwrapped due to @UnwrapByDefault.
        @NotNull
        private final OptionalInt count;

        public PrimitiveRequired(OptionalInt count) {
            this.count = count;
        }
    }

    public static final class ExplicitUnwrap {
        @NotBlank(payload = Unwrapping.Unwrap.class)
        private final Optional<String> code;

        public ExplicitUnwrap(Optional<String> code) {
            this.code = code;
        }
    }

    public static final class IncorrectPlacement {
        // No @UnwrapByDefault on Optional<T>.
        @NotBlank
        private final Optional<String> code = Optional.of("ok");
    }
}
```

The unused `Comparator` import can be removed since the program only calls `sorted()` on the stream; Java permits unused imports, though in code review you would typically delete it. The `private final` fields are read by the provider using Bean Validation field-access; declaring getters for every field is not required to use field constraints.

Compile and run in the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Ignoring Spring Boot startup logs, the `System.out.println` lines produced by the program are:

```text
Good: 0
Absent: 1 [nickname]
Invalid: 3 [address.city, nickname, seats]
Null wrapper: 1 [wrapper]
OptionalInt required: 1 [count]
Explicit unwrap: 1 [code]
Wrong placement: UnexpectedTypeException
```

**Analysis of each result:**

1. **Good: 0** — `wrapper = Optional.empty()` is still non-null, so it passes `@NotNull` on the wrapper; `nickname` has a valid String; `address.city` is valid; `seats = 2` passes `@Min(1)`.
2. **Absent: 1 [nickname]** — the optional wrapper exists, but `Optional<@NotBlank String>` has a null element and fails. `address = Optional.empty()` produces no cascade violation, and `seats = OptionalInt.empty()` passes `@Min` because the value unwraps to null.
3. **Invalid: 3** — `nickname` is a whitespace string, the cascaded address has `city = ""`, and 0 seats fails `@Min(1)`. Paths are sorted for stable output.
4. **Null wrapper: 1** — `@NotNull` on `Optional<String> wrapper` rejects null without needing unwrapping.
5. **OptionalInt required: 1** — `@NotNull OptionalInt count` implicitly unwraps; `OptionalInt.empty()` is extracted as null and rejected.
6. **Explicit unwrap: 1** — `Unwrapping.Unwrap` forces `@NotBlank` to evaluate the `String` inside `Optional`; whitespace string is invalid.
7. **Wrong placement** — lacking explicit unwrapping or a type-use annotation, `@NotBlank` targets `Optional<String>` and the provider finds no suitable validator.

The example deliberately puts a mistyped annotation in a separate class to demonstrate `UnexpectedTypeException`. In production applications, **fix `IncorrectPlacement` to `Optional<@NotBlank String>` or use proper explicit unwrapping**; never keep an invalid class just to catch the exception at runtime.

## 10. `@NotNull` and `@Valid` in Multi-Level Nested Data

Container element constraints can be combined with one another:

```java
private List<Optional<@NotBlank String>> aliases;

private Map<@NotBlank String,
            Optional<@NotNull @Valid Address>> addressByCode;
```

You need to import `java.util.List` and `Map`. In the first declaration:

1. The `List` extractor retrieves each `Optional` element.
2. The `Optional` extractor retrieves the `String` or `null`.
3. `@NotBlank` evaluates the `String`.

In the second declaration:

1. The Map key extractor applies `@NotBlank` to each `String` key.
2. The Map value extractor retrieves the `Optional` in each entry.
3. The `Optional` extractor retrieves the `Address` or `null`.
4. `@NotNull` requires each `Optional` to hold an `Address`, and `@Valid` cascades into `Address`.

Note: with `List<Optional<@NotBlank String>>`, the List itself can be null or empty without necessarily violating anything; to require the List to have elements, add `@NotEmpty`/`@NotNull` on **the List**. If each `Optional` wrapper inside the List must be non-null, place `@NotNull` on the **`Optional` type argument**:

```java
@NotEmpty
private List<@NotNull Optional<@NotBlank String>> aliases;
```

Do not put `@NotBlank` on `List` or on `Optional` without unwrapping. Annotations must be placed on the exact **object to be validated**, and the provider must have extractors for all intermediate container layers.

## 11. Writing a Custom `ValueExtractor` for Your Own Wrapper

Suppose the application has a wrapper type like `Box<T>`:

```java
public record Box<T>(T value) {}
```

If you use `Box<@NotBlank String>` and the provider does not know how to extract `T`, Bean Validation cannot reach the value. You can write an extractor:

```java
import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.ValueExtractor;

public final class BoxValueExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {

    @Override
    public void extractValues(
            Box<?> container, ValueReceiver receiver) {
        receiver.value(null, container.value());
    }
}
```

These two snippets **illustrate separate standalone files**; if saved as Java sources, put `Box.java` and `BoxValueExtractor.java` in the same package. `@ExtractedValue` identifies the **single type argument** being extracted; for typical generic wrappers, use an unbounded wildcard `?` at the marked position. Do not attach `@ExtractedValue` to multiple type arguments in a single extractor.

Register it in Spring via `LocalValidatorFactoryBean` before bootstrapping the provider, e.g., in a Spring Framework/Boot configuration that manages the application's bean validator:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfig {
    @Bean
    LocalValidatorFactoryBean validator() {
        LocalValidatorFactoryBean factory =
                new LocalValidatorFactoryBean();
        factory.setConfigurationInitializer(
                configuration -> configuration.addValueExtractor(
                        new BoxValueExtractor()));
        return factory;
    }
}
```

This is an **illustrative configuration class, not a program with `main`**; ensure `Box`/`BoxValueExtractor` are in the right packages/imports and only one validator configuration is active for MVC/service flows. `setConfigurationInitializer(...)` is Spring `LocalValidatorFactoryBean`'s API for customizing `jakarta.validation.Configuration<?>` before the provider builds the factory.

Extractors can also be registered via `META-INF/services/jakarta.validation.valueextraction.ValueExtractor`, `validation.xml`, or `Configuration.addValueExtractor(...)` per Jakarta Validation precedence rules. An extractor should be registered deliberately; duplicate extractors for the same type/type-argument pair or multiple matching extractors can cause declaration/resolution errors.

**When should you use `@UnwrapByDefault` on a custom extractor?** Only when you want constraints placed at the **declaration level on `Box` itself** to automatically forward to value `T`. Without it, callers can still write `Box<@NotBlank String>` with the constraint on the type argument. Adding `@UnwrapByDefault` requires care because it can make `@NotNull Box<T>` validate the element instead of the wrapper, creating subtle differences.

## 12. Identifying the Right Exception Type

| Error | Typical Meaning | How to Handle |
| --- | --- | --- |
| `UnexpectedTypeException` | No matching `ConstraintValidator` for the validated type | Fix annotation/type placement or request unwrapping explicitly |
| `ConstraintDeclarationException` | Invalid constraint/extractor declaration or resolution | Check type arguments, unwrap configuration, ambiguity |
| `ValueExtractorDefinitionException` | Malformed extractor implementation | Check `@ExtractedValue` and generic wildcard |
| `ValueExtractorDeclarationException` | Invalid extractor configuration/registration, e.g., duplicate extractors | Check service loader, XML, or API registrations |
| `ConstraintViolation` | Validator found, but value fails rule | Fix input data or business contract |
| `MethodArgumentNotValidException` (Spring MVC) | MVC validated DTO and found binding/validation errors | Read `BindingResult` and return appropriate errors |

Common mistake example:

```java
@NotBlank
Optional<String> code;
```

If the provider does not implicitly unwrap generic `Optional`, `@NotBlank` targets `Optional` and throws `UnexpectedTypeException`. Fix:

```java
Optional<@NotBlank String> code;
```

When a custom extractor for `Box` is missing or two extractors match simultaneously, the error usually happens during **extractor resolution**, not necessarily `UnexpectedTypeException`. Inspect the exact exception class, property path, and stack trace; do not lump every error together as "null value."

## 13. Spring MVC: Binding Optional and Bean Validation Are Two Separate Steps

In Spring MVC, `@RequestParam Optional<String> keyword` is an **optional parameter binding** mechanism. It does not automatically run `@NotBlank` on the inner `String` in all configurations. Bean Validation requires a trigger such as `@Valid`/`@Validated` in a supported MVC flow, or an explicit validation call.

Illustrative DTO using type-use constraints:

```java
public class SearchFilter {
    @NotNull
    private Optional<@Size(max = 40) String> keyword =
            Optional.empty();

    private Optional<@Positive Integer> minPrice =
            Optional.empty();
}
```

This is an illustrative class. Binding/deserialization must first construct the proper `Optional` types, and then an entry point must execute Bean Validation. For JSON `@RequestBody`, Jackson must support `Optional` (e.g., `jackson-datatype-jdk8` module and appropriate object mapper configuration); **Jackson only converts JSON to the DTO, while Bean Validation runs afterward when requested by the framework**. Do not treat `Optional.empty()`, a missing JSON field, and JSON `null` as identical across every `ObjectMapper`: behavior depends on deserialization configuration and constructors/setters used.

Illustrative controller:

```java
@PostMapping("/search")
public ResponseEntity<?> search(
        @Valid @RequestBody SearchFilter filter,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(errors.getFieldErrors().stream()
                        .map(e -> e.getField() + ": "
                                + e.getDefaultMessage())
                        .toList());
    }

    return ResponseEntity.ok().build();
}
```

This is an **illustrative controller method**, requiring Spring MVC/HTTP imports and `jakarta.validation.Valid` inside a real controller. `BindingResult` must immediately follow the validated parameter in supported signatures. The provider must have the matching extractor; Spring's standard `LocalValidatorFactoryBean` does not require you to manually register an extractor for `Optional`.

**Design note:** Java `Optional` is primarily intended for **method return types** to express presence/absence of a result. For DTOs bound from JSON/forms, `Optional` fields are not always the simplest choice; you can use nullable fields with clear constraints and convert to `Optional` at the service boundary. Choose based on your data contract and actual Jackson/conversion behavior.

## 14. Groups, Cascaded Validation, and Null Semantics

Groups still apply when constraints reside inside generic containers:

```java
public interface OnCreate {}

public class CreateProfile {
    private Optional<@NotBlank(groups = OnCreate.class) String> name;
}
```

Calling `validator.validate(profile, OnCreate.class)` validates the `OnCreate`-group `@NotBlank` on the extracted `String`. Calling only `validator.validate(profile)` (default group) may skip constraints belonging to other groups. Ensure `name` is non-null or add a constraint on the wrapper if the application needs to reject a null wrapper.

For `Optional<@Valid Address>`, cascading applies the active group according to Bean Validation rules. If a group switch is needed at the container boundary, Jakarta supports `@ConvertGroup` on the cascaded element subject to specification restrictions. Do not assume `@Valid` makes every constraint group on `Address` run.

**Null policies worth writing into tests:**

- Require the wrapper? `@NotNull Optional<T>`.
- Require an element? `Optional<@NotNull T>` (when the container's extractor turns absence into null).
- Optional element, but length-capped if present? `Optional<@Size(max=40) String>`.
- Require a non-blank element? `Optional<@NotBlank String>`.
- Validate bean only when present? `Optional<@Valid Address>`.
- Both require bean presence and cascade? `Optional<@NotNull @Valid Address>`, combined with outer `@NotNull` on the wrapper when needed.

Putting rules in the right positions lets the model clearly distinguish *missing*, *null*, *empty String*, and *invalid nested object*.

## 15. Testing Edge Cases That Commonly Go Wrong

1. `Optional.empty()` with `Optional<@NotNull String>` → produces a violation.
2. `Optional.empty()` with `Optional<@Size(max=10) String>` → no violation because `@Size` accepts null.
3. `Optional.of(" ")` with `Optional<@NotBlank String>` → produces a violation.
4. `null` wrapper with `@NotNull Optional<String>` → produces a violation.
5. `Optional.empty()` with `Optional<@Valid Address>` → no cascade violation.
6. `Optional.of(Address(city=""))` with `Optional<@Valid Address>` → violation on `city`.
7. `OptionalInt.empty()` with `@Min(1)` → normally no violation per spec, as the extracted number is null.
8. `OptionalInt.empty()` with `@NotNull` → violation due to implicit unwrap.
9. `OptionalInt.empty()` with `@NotNull(payload=Unwrapping.Skip.class)` → no violation if wrapper is non-null.
10. `@NotBlank Optional<String>` without explicit unwrap → catch `UnexpectedTypeException` and fix the declaration.
11. `List<Optional<@NotBlank String>>` → test second element as `Optional.of("")`; verify path may include index.
12. Custom `Box<T>` → test with/without extractor and whether `@UnwrapByDefault` changes `@NotNull` semantics.
13. MVC JSON → test missing field, `null`, empty string, whitespace string, and valid string requests.
14. Method/DTO validation → test properly through a Spring-managed entry point or direct `jakarta.validation.Validator` call; do not assume annotations run automatically just because an object was instantiated.

**For stable tests**, check the set of property paths/constraint types rather than the first element in `Set<ConstraintViolation<?>>`, since order is not guaranteed. Some providers emit richer paths for lists/maps with nodes like `<list element>`, `<map key>`, and `<map value>`; align tests with the contract you need to guarantee and the provider you use.

## 16. Common Design Mistakes and Fixes

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| `@NotBlank Optional<String>` causes HV000030 | Constraint targets wrapper that does not unwrap by default | Change to `Optional<@NotBlank String>` |
| `@NotNull Optional<String>` misses `Optional.empty()` | `@NotNull` only checks wrapper | If element is required, use `Optional<@NotNull String>` |
| `Optional<@Valid Address>` reports no error when empty | Cascade does not treat null as a violation | Add `@NotNull` to the type argument |
| `Optional<@Size(max=10) String>` reports no error when absent | `@Size` treats null as valid | Combine with inner `@NotNull` if presence is required |
| `@Min(1) OptionalInt` allows empty | Implicit unwrap yields null and `@Min` allows null | Add `@NotNull` with unwrap semantics if required |
| Using `Unwrapping.Skip` thinking it requires content | Skip forces the rule onto the wrapper | Use `@NotNull`/element constraint depending on intent |
| Custom `Box` is not validated | Missing or misregistered `ValueExtractor` | Declare `ValueExtractor<Box<@ExtractedValue ?>>` and register once |
| Duplicate or invalid extractor | `ValueExtractor` configuration error | Audit service loader, `validation.xml`, API registration |
| Spring MVC reports no errors | Validation not triggered or DTO not bound as expected | Check `@Valid`, validator bean, Jackson JDK8 module, run real tests |
| `Optional` field is null after deserialization | Setter/constructor/deserializer config does not initialize as expected | Normalize input, design clear DTO contract, test absent/null |
| Cascade runs twice | `@Valid` placed on both wrapper and type argument | Use only one intended cascade position |
| API and database treat missingness differently | Mixing "absent", "null", and "clear field" | Clearly define PATCH/PUT and update policies |

Never fix annotation placement errors by catching and ignoring `ValidationException`; doing so can silently turn programming bugs into unvalidated data.

## 17. Self-Check Questions

**1. Is `Optional.empty()` rejected by `@NotNull Optional<String>`?**  
No, because the wrapper is non-null. To require an element, put the constraint on the type argument.

**2. Does `Optional<@NotNull String>` reject `Optional.empty()`?**  
Yes. The built-in extractor translates absence into a `null` element; `@NotNull` on the element fails.

**3. Are `@NotBlank Optional<String>` and `Optional<@NotBlank String>` equivalent?**  
No. The first targets the wrapper and does not implicitly unwrap under the standard generic extractor; the second targets `String`.

**4. What type does `@Min(1) OptionalInt.of(0)` validate against?**  
The extracted value as `Integer`, thanks to `@UnwrapByDefault` on the `OptionalInt` extractor.

**5. Does `@Min(1) OptionalInt.empty()` reject empty?**  
Not under standard rules, because the extractor yields null and `@Min` accepts null. Add `@NotNull` with unwrap semantics to require a number.

**6. Does `Optional<@Valid Address>` require an address to exist?**  
No. `@Valid` only cascades when an object is present. `@NotNull` on the type argument is what requires presence.

**7. When do you need to write a custom `ValueExtractor`?**  
When using a custom container such as `Box<T>` for which the provider lacks an extractor on the type argument to validate.

**8. Is `Unwrapping.Unwrap` the same as `validator.unwrap(...)`?**  
No. `Unwrapping.Unwrap` is a payload controlling how constraints apply to elements; `Validator.unwrap(Class)` is the API for accessing provider-specific types/features.

**9. Are all `Optional` JSON fields always handled the same way by Jackson?**  
No. Inspect the Jackson JDK 8 module and deserializer settings; Bean Validation is a separate step after the DTO is constructed.

**Key takeaway:** *Place constraints at the exact position to be checked; understand what the extractor does with `Optional.empty()`; rely on implicit unwrapping only when the extractor declares it; use `@Valid` to cascade, and constraints to require presence.*

## Official References

- Jakarta Validation 3.1 specification — Container element constraints / implicit unwrapping / value extractors: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation API — ValueExtractor: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/valueextraction/ValueExtractor.html
- Jakarta Validation API — Unwrapping: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/valueextraction/Unwrapping.html
- Jakarta Validation API — UnwrapByDefault: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/valueextraction/UnwrapByDefault.html
- Hibernate Validator documentation — Container element constraints and value extraction: https://hibernate.org/validator/documentation/
- Spring Framework Reference — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework API — LocalValidatorFactoryBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Framework Reference — MVC validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
