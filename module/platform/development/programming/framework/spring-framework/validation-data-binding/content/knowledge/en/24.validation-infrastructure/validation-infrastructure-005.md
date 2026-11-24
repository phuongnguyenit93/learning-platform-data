# @ExtractedValue, @UnwrapByDefault, and Unwrapping Strategies in Jakarta Validation

## 1. Goal and real-world problem

In Spring Framework applications, Bean Validation (Jakarta Validation) typically validates DTO properties using `@NotBlank`, `@Min`, `@Valid`, and so on. However, business values do not always sit directly inside a `String` or `int`: they may be wrapped in `OptionalInt`, `List<T>`, `Map<K, V>`, or a custom type such as `Box<T>`.

Suppose `Box<String>` holds a customer code. There are three completely different things we might want to verify:

- **Does the container itself exist?** `box != null`: checks the `Box` object.
- **Is the inner value valid?** `box.value()` must be non-blank or match a format: checks the *wrapped value*.
- **Do the inner object's properties satisfy their rules?** `Box<Address>` holds an `Address` whose fields are constrained: *cascaded validation*.

Jakarta Validation provides a **value extraction** mechanism to retrieve values from a container before validation. Three central components:

1. `@ExtractedValue` marks the **extracted element/data type** in the `ValueExtractor` signature.
2. `@UnwrapByDefault` sets the **default policy**: constraints placed on the container will be applied to the extracted value when a matching extractor applies.
3. `Unwrapping.Unwrap` and `Unwrapping.Skip` are **payloads at the constraint declaration site** to request unwrapping or keep the wrapper for that specific constraint.

After this article, you will be able to write and register a `ValueExtractor`, choose the right validation target, distinguish container-element constraints from unwrapping, read error paths, and integrate this mechanism into Spring MVC.

## 2. Separating container, element, and unwrapping

Consider these declarations:

```java
@NotNull
private List<@NotBlank String> names;

@Size(min = 2)
private List<String> tags;

private List<@Valid Address> addresses;
```

- `@NotNull` outside `List` checks that the **list reference** is non-`null`. It does not validate individual elements by itself.
- `List<@NotBlank String>` validates **each string in the list** thanks to the built-in extractor for `List`.
- `@Size(min = 2)` placed on `List` checks the **number of elements in the list**. Do not assume it means the length of each `String`.
- `List<@Valid Address>` performs recursive validation on each `Address` object thanks to container value extraction. `@Valid` marks cascading, not a constraint with `message` or `payload`.

With a custom container:

```java
Box<@NotBlank String> code;
```

`@NotBlank` is placed **on the type argument** `String`. The provider needs an extractor for `Box` to pull `String` out. This differs from:

```java
@NotBlank
Box<String> code;
```

In the second example, the constraint is placed **on the object of type `Box`**. The provider must decide whether to validate `Box` or unwrap `Box` to validate `String`. The default policy or unwrapping payload answers that question.

**Root principle:** Having a `ValueExtractor` does not automatically mean every constraint placed on the container is applied to the inner value. The extractor tells *how to get the value*; the unwrapping policy decides *where to apply the constraint*.

## 3. Foundational API: `ValueExtractor` and `@ExtractedValue`

Both live in the `jakarta.validation.valueextraction` package. An extractor implements:

```java
public interface ValueExtractor<T> {
    void extractValues(T originalValue, ValueReceiver receiver);
}
```

Here `T` is the **container type**. Inside `extractValues()`, the extractor calls methods on `ValueReceiver` to hand the values to be validated to the provider. For a generic container:

```java
public record Box<T>(T value) {}

public final class BoxExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {

    @Override
    public void extractValues(Box<?> box, ValueReceiver receiver) {
        receiver.value(null, box.value());
    }
}
```

*These two declarations illustrate the API and are not a standalone program; a full runnable example appears in section 6.*

Key semantics:

- `Box<@ExtractedValue ?>` identifies the **first type argument** as the position from which the extractor reads values. For generic types, `@ExtractedValue` marks a type argument in the extractor's signature, **not** arbitrarily on DTO fields.
- Each extractor definition must have **exactly one** site marked with `@ExtractedValue`. For containers with two type parameters such as `Map<K,V>`, separate extractors are needed for keys and values.
- `receiver.value(null, box.value())` reports one extracted value. Passing `null` for `nodeName` prevents adding an intermediate node to the error path (ideal for transparent wrappers such as `Box`/`Optional`).
- `@ExtractedValue(type = SomeClass.class)` is for **non-generic** types, where there is no type argument from which to infer the inner value type. Do not use the `type` attribute on a generic container's type argument.
- The extractor performs **value retrieval**, without calling `validator.validate()` itself, creating `ConstraintViolation`s itself, or replacing individual constraint validators.

### 3.1. Choosing the right `ValueReceiver` method

| Method | When to use | Context data in the error path |
| --- | --- | --- |
| `value(nodeName, value)` | A single wrapped value, e.g. `Box<T>` | Node named `nodeName`, or no added node when `null` |
| `iterableValue(nodeName, value)` | Elements without explicit indices, e.g. `Set` | In-iterable flag |
| `indexedValue(nodeName, index, value)` | Positional elements, e.g. `List` | Index `index` |
| `keyedValue(nodeName, key, value)` | Keyed elements, e.g. `Map` | Key `key` |

For multi-element containers, **call the receiver for each value**, rather than passing the whole collection as a single value. For example, an extractor for a custom list can iterate:

```java
for (int i = 0; i < values.size(); i++) {
    receiver.indexedValue("<element>", i, values.get(i));
}
```

The snippet above is an illustrative body assuming `values` is a `List<?>` and `receiver` is valid. When indices/keys exist, preserve them so error-reporting APIs pinpoint the exact element. Do not use `receiver.value(null, collection)` if the goal is to validate each element.

## 4. `@UnwrapByDefault` and the two explicit payloads

`@UnwrapByDefault` is placed **on the `ValueExtractor` implementation class**, not on `Box`, DTO fields, or constraint annotations:

```java
@UnwrapByDefault
public final class BoxExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {
    @Override
    public void extractValues(Box<?> box, ValueReceiver receiver) {
        receiver.value(null, box.value());
    }
}
```

When the provider finds a matching extractor that unwraps by default as above, the declaration:

```java
@NotBlank
Box<String> customerCode;
```

applies `@NotBlank` to the wrapped `String`. This is **implicit unwrapping**. You no longer need to write `@NotBlank` inside the type argument if your API design intentionally validates the wrapped value via annotations placed on the wrapper.

An individual constraint can still skip or force unwrapping via payload:

```java
@NotBlank(payload = Unwrapping.Unwrap.class)
Box<String> code; // Force validating the inner String.

@NotNull(payload = Unwrapping.Skip.class)
Box<String> holder; // Validate the Box reference itself.
```

The two payloads are `jakarta.validation.valueextraction.Unwrapping.Unwrap` and `Unwrapping.Skip` (marker interfaces extending `Payload`), not global options; they apply **to the constraint declared with that payload**.

### 4.1. Decision table

| Where the constraint is placed | Extractor configuration | Meaning |
| --- | --- | --- |
| `Box<@NotBlank String> code` | Matching extractor exists | Validates the `String` element, regardless of `@UnwrapByDefault` |
| `@NotBlank Box<String> code` | Extractor has `@UnwrapByDefault` | Validates `String` by default |
| `@NotBlank Box<String> code` | Extractor lacks `@UnwrapByDefault` | Attempts to validate `Box`; usually throws `UnexpectedTypeException` because `@NotBlank` has no validator for `Box` |
| `@NotBlank(payload = Unwrapping.Unwrap.class) Box<String> code` | Extractor does not unwrap by default but can extract `String` | Forces validation of the `String` element |
| `@NotNull(payload = Unwrapping.Skip.class) Box<String> holder` | Extractor has `@UnwrapByDefault` | Forces validation of the **container reference** |
| `@Valid Box<Address> holder` or `Box<@Valid Address> holder` | Matching extractor exists for cascading | Includes the inner object in recursive validation; `@Valid` does not use Unwrap/Skip payloads |

This table describes the case where there is a single matching extractor for the extraction site. If no extractor exists, the wrong extractor is chosen, or multiple equal candidates conflict, the provider may report a configuration/execution error. Do not use `Unwrapping.Unwrap` and `Unwrapping.Skip` together on the same constraint.

### 4.2. The easily misunderstood `@NotNull` case

With an extractor **annotated with `@UnwrapByDefault`**:

```java
@NotNull
Box<String> value; // Intended meaning: wrapped String is non-null.

@NotNull(payload = Unwrapping.Skip.class)
Box<String> holder; // Intended meaning: Box reference is non-null.
```

If `holder = new Box<>(null)`, the second constraint **passes** because the container exists. If you require *both the container and the inner data* to be non-null, declare two explicit rules at the two layers rather than treating a single `@NotNull` as checking everything. When the container is `null`, the extractor has no object to unwrap; a rule checking the wrapper's presence should be declared separately when business rules require it.

A similar caveat: `@Min` and `@Size` normally treat a **`null` extracted value** as valid. To forbid null/empty values, add `@NotNull`, `@NotBlank`, or another suitable constraint at the exact layer you want to check.

## 5. Generic and non-generic containers

### 5.1. Generic: `Box<T>`

`ValueExtractor<Box<@ExtractedValue ?>>` states clearly that type parameter `T` is what gets extracted. Hence annotations work in both declaration styles:

```java
Box<@NotBlank String> name;
Box<@Valid Address> address;
```

Here `Address` is a class with constraints on its fields/getters. The `@Valid` annotation in the type argument denotes cascading. If an extractor definition handles only one type argument position, the provider needs a corresponding extractor for each other position you want to validate.

### 5.2. Non-generic: `OptionalInt`

Since `OptionalInt` has no `<T>`, the extractor must declare the inner type explicitly:

```java
@UnwrapByDefault
public final class ExampleOptionalIntExtractor
        implements ValueExtractor<
                @ExtractedValue(type = Integer.class) OptionalInt> {

    @Override
    public void extractValues(OptionalInt original, ValueReceiver receiver) {
        receiver.value(
                null,
                original.isPresent() ? original.getAsInt() : null
        );
    }
}
```

This illustration assumes `java.util.OptionalInt` and the validation APIs are imported; **you do not need to re-register this extractor** when using Hibernate Validator, which has a built-in `OptionalInt` extractor. `type = Integer.class` supplies the post-unwrapping value type because `OptionalInt` has no type argument.

Example using the built-in extractor:

```java
@Min(5)
private OptionalInt minimum; // Targets the inner Integer by default.

@NotNull(payload = Unwrapping.Skip.class)
private OptionalInt holder;  // Checks the OptionalInt reference.
```

`OptionalInt.empty()` and `null` are two distinct states: an `OptionalInt` object can exist without holding an `int`. The built-in extractor converts the empty case into an extracted value of `null`. Because `@Min` permits `null`, do not rely on `@Min` alone to assert that `OptionalInt` has a value. The “must be present” requirement must be expressed by an appropriate constraint on the unwrapped value, such as `@NotNull` when default unwrapping is active.

## 6. Standalone runnable example with Java 17 and Hibernate Validator

This exercise uses **two generic wrappers**:

- `Box<T>`: extractor has `@UnwrapByDefault` to validate the wrapped value by default.
- `Parcel<T>`: extractor **does not** have `@UnwrapByDefault`, clearly showing `Unwrapping.Unwrap` forcing unwrapping.

Using Maven and Java 17+, structure:

```text
value-extraction-demo/
├── pom.xml
└── src/main/java/demo/
    └── ExtractionDemo.java
```

### 6.1. Dependency configuration

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>value-extraction-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.5.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Hibernate Validator brings in the Jakarta Validation API; `expressly` provides Jakarta Expression Language for message interpolation. In a Spring Boot application, you normally use `spring-boot-starter-validation` and the project's dependency management instead of copying these versions.

### 6.2. Program `ExtractionDemo.java`

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.UnwrapByDefault;
import jakarta.validation.valueextraction.Unwrapping;
import jakarta.validation.valueextraction.ValueExtractor;

import java.util.TreeSet;

public class ExtractionDemo {

    public record Box<T>(T value) {}
    public record Parcel<T>(T value) {}

    // Box is "unwrapped" by default.
    @UnwrapByDefault
    public static final class BoxExtractor
            implements ValueExtractor<Box<@ExtractedValue ?>> {

        @Override
        public void extractValues(Box<?> box, ValueReceiver receiver) {
            receiver.value(null, box.value());
        }
    }

    // Parcel still has an extractor, but does not automatically unwrap
    // constraints declared on Parcel itself.
    public static final class ParcelExtractor
            implements ValueExtractor<Parcel<@ExtractedValue ?>> {

        @Override
        public void extractValues(Parcel<?> parcel, ValueReceiver receiver) {
            receiver.value(null, parcel.value());
        }
    }

    public static final class Form {

        // Constraint is on Box, but is forwarded to String.
        @NotBlank(message = "code is blank")
        private final Box<String> code;

        // Force checking Box, ignoring @UnwrapByDefault.
        @NotNull(
            message = "container is null",
            payload = Unwrapping.Skip.class
        )
        private final Box<String> carrier;

        // Constraint is directly on the String type argument.
        private final Box<@Size(
            min = 3,
            message = "token too short"
        ) String> token;

        // Parcel does not unwrap by default; request unwrapping here.
        @NotBlank(
            message = "pin is blank",
            payload = Unwrapping.Unwrap.class
        )
        private final Parcel<String> pin;

        Form(Box<String> code,
             Box<String> carrier,
             Box<String> token,
             Parcel<String> pin) {
            this.code = code;
            this.carrier = carrier;
            this.token = token;
            this.pin = pin;
        }
    }

    private static void check(
            Validator validator, String label, Form form) {
        TreeSet<String> errors = new TreeSet<>();

        for (ConstraintViolation<Form> violation
                : validator.validate(form)) {
            errors.add(
                violation.getPropertyPath() + ": "
                    + violation.getMessage()
            );
        }

        System.out.println(label + " -> " + errors);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                 Validation.byDefaultProvider()
                     .configure()
                     .addValueExtractor(new BoxExtractor())
                     .addValueExtractor(new ParcelExtractor())
                     .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            check(validator, "invalid", new Form(
                new Box<>(""),
                new Box<>(null),
                new Box<>("AB"),
                new Parcel<>("")
            ));

            check(validator, "valid", new Form(
                new Box<>("OK"),
                new Box<>(null),
                new Box<>("GOOD"),
                new Parcel<>("123")
            ));

            check(validator, "missing-wrapper", new Form(
                new Box<>("OK"),
                null,
                new Box<>("GOOD"),
                new Parcel<>("123")
            ));
        }
    }
}
```

From the `value-extraction-demo` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ExtractionDemo
```

**Expected output from `System.out`** (ignoring standalone Maven/provider logs):

```text
invalid -> [code: code is blank, pin: pin is blank, token: token too short]
valid -> []
missing-wrapper -> [carrier: container is null]
```

Decoding each result:

1. In `invalid`, `code` wraps an empty string: `@UnwrapByDefault` makes `@NotBlank` act on the string, reporting `code is blank`.
2. `carrier = new Box<>(null)` is still a **non-null** container. Because of `Unwrapping.Skip`, `@NotNull` checks `Box` and does not report an error even though the inner value is null.
3. `token` wraps `"AB"` of length 2; `@Size(min = 3)` is on the type argument, so the provider uses the extractor to validate the element and reports `token too short`.
4. `pin` has an empty string. `ParcelExtractor` lacks `@UnwrapByDefault`, but `Unwrapping.Unwrap` forces validation of the inner value, reporting `pin is blank`.
5. The `missing-wrapper` case sets `carrier = null`, so `@NotNull(payload = Skip.class)` fails while the other fields are valid.

`TreeSet` sorts error strings so stdout is deterministic; the iteration order of the `ConstraintViolation` set returned by the provider is not guaranteed. `receiver.value(null, ...)` keeps property names simple like `code`/`pin`/`token` without adding a wrapper node to the path.

### 6.3. Small variation to test yourself

Try **removing `@UnwrapByDefault`** from `BoxExtractor` while keeping `@NotBlank Box<String> code`: now `@NotBlank` targets `Box`; the standard provider has no `@NotBlank` validator for `Box` and usually throws `UnexpectedTypeException`. To fix it to mean "validate the string", either move the annotation to `Box<@NotBlank String>` or add `payload = Unwrapping.Unwrap.class` to `@NotBlank`.

Conversely, removing `payload = Unwrapping.Skip.class` from `carrier` causes `@NotNull` on that field to target the inner `String` value (because the extractor unwraps by default); for `new Box<>(null)`, the output of the example will change.

## 7. Registering `ValueExtractor` in Java and Spring

Writing the class that implements `ValueExtractor` is not enough. The provider must **know that the extractor exists**. There are several ways:

### 7.1. Programmatic registration via API

The example in section 6 uses:

```java
ValidatorFactory factory = Validation.byDefaultProvider()
    .configure()
    .addValueExtractor(new BoxExtractor())
    .addValueExtractor(new ParcelExtractor())
    .buildValidatorFactory();
```

This approach suits CLI programs, experiments, or manually managed `ValidatorFactory` instances. Each factory must be closed when no longer needed. If a Spring application has multiple `Validator`s, ensure they are configured consistently instead of creating an isolated factory inside a controller.

### 7.2. Registration via Java ServiceLoader

For shared libraries or Spring Boot applications, you can let the provider discover extractors via the resource:

```text
src/main/resources/META-INF/services/
    jakarta.validation.valueextraction.ValueExtractor
```

File contents (one class name per line, instantiable via a no-arg constructor):

```text
demo.ExtractionDemo$BoxExtractor
demo.ExtractionDemo$ParcelExtractor
```

Both names contain `$` because the example in section 6 declares the extractors as **nested static classes**. If in a real project you move the extractors to top-level classes, use the corresponding fully qualified names (e.g., `demo.BoxExtractor`). The classes must be public and have an accessible no-arg constructor. This is an **alternative** to calling `addValueExtractor(...)` in the demo program; avoid registering duplicates in the same factory unnecessarily.

Hibernate Validator also supports `META-INF/validation.xml` and `ValidatorContext#addValueExtractor(...)`. An extractor registered at the `ValidatorContext` level applies only to that `Validator`. When the same container and type parameter appear in multiple configuration sources, the precedence order is typically: built-in extractors, ServiceLoader, `validation.xml`, `Configuration.addValueExtractor`, and then `ValidatorContext.addValueExtractor`. Having two extractors with the same key at the **same configuration level** can be rejected due to ambiguous declarations.

### 7.3. Using it in Spring MVC

The example below is a snippet to **plug into a Spring Boot application with validation already configured**, not a standalone program replacing section 6. Suppose `Box` and `BoxExtractor` are on the classpath and the extractor is registered with the provider Spring uses:

```java
// DTO:
public record CreateRequest(
    Box<@NotBlank String> customerCode
) {}

// Controller:
@RestController
@RequestMapping("/requests")
public class RequestController {

    @PostMapping
    public ResponseEntity<Void> submit(
            @Valid @RequestBody CreateRequest request) {
        return ResponseEntity.noContent().build();
    }
}
```

You need the Spring MVC imports, `jakarta.validation.Valid`, and `jakarta.validation.constraints.NotBlank`. JSON payload matching the record-based `Box` from section 6:

```json
{
  "customerCode": {
    "value": ""
  }
}
```

When Spring deserializes the DTO and `@Valid` triggers validation, the provider sees the container element constraint `@NotBlank` inside `Box<...>`, invokes the custom extractor, and detects the empty string. When a request body validation fails in the standard MVC flow, Spring can return HTTP 400 via `MethodArgumentNotValidException`. Method validation or `BindingResult` handling takes different branches depending on the controller signature.

**Separation of concerns:** Spring binding/Jackson builds the DTO data, Spring triggers validation, the Jakarta Validation provider selects the extractor and constraint, and Spring handles the resulting errors. `@UnwrapByDefault` does not replace `@Valid`, does not intervene in how JSON is bound, and does not automatically enable validation on an endpoint.

## 8. Cascaded validation and nested structures

`ValueExtractor` also participates in cascading. Suppose:

```java
public class Address {
    @NotBlank
    private String city;
}

// Declared in DTO:
private Box<@Valid Address> shippingAddress;
```

When validating the DTO, the provider extracts `Address` from `Box` and then applies `Address`'s constraints because of `@Valid`. `@UnwrapByDefault` is not required to use `Box<@Valid Address>`; what is needed is a matching extractor registered properly.

For multi-level structures:

```java
private List<Box<@Valid Address>> addresses;
```

The provider can step through each level: the built-in `List` extractor → the custom `Box` extractor → `Address` validation. The error path can carry property names, container nodes, and element indices depending on the `ValueReceiver` method. If you replace `receiver.value(null, ...)` with a non-null node name, the path adds that component.

**Do not confuse cascading with constraint unwrapping:** `@Valid` specifies traversing deeper into the object graph; `Unwrapping.Unwrap` and `Unwrapping.Skip` adjust constraints **that have a payload** placed on a container. You cannot use `@Valid(payload = ...)` because `@Valid` does not declare a `payload` attribute.

## 9. Resolution, performance, and limitations

### 9.1. How does the provider select an extractor?

Selection depends on the container type, the marked type argument position, and the validation context. For **container element constraints**, the specification uses the **declared type** to look up the extractor; for **cascaded validation**, the **runtime type** plays a role in resolution. When multiple extractors compete, the provider must find one sufficiently specific for the extraction site. Ambiguous choices can cause `ConstraintDeclarationException`, depending on the situation.

Design mistakes that commonly cause failures:
- Two extractors both accepting `Box<@ExtractedValue ?>` at the same registration level.
- Lacking an extractor for a custom container while declaring constraints on its type argument.
- Marking more than one `@ExtractedValue` in the same extractor definition.
- Using `@ExtractedValue(type = String.class)` on a type parameter of a generic container.
- One extractor targeting `Map<K,V>` trying to extract both K and V in the same definition; split into two extractors at the right positions.

### 9.2. Data and performance constraints

- Extraction is typically invoked whenever the provider needs to inspect the relevant elements/cascades. A large collection can incur many validation checks, so `extractValues()` should be a simple iteration with no DB queries or side effects.
- Do not assume the provider calls the extractor with a `null` container. Constraints checking container existence should be declared at the appropriate layer.
- Collection extractors must iterate elements in the right order/logical set; for `Map`, retrieve the true key/value and pass the real key to `keyedValue`.
- For DTOs received over HTTP, consider input collection sizes and enforce request limits at the binding/application layer; validation is not a substitute for payload size control.
- Custom extractors establish a shared mechanism for all relevant constraints; changing the `@UnwrapByDefault` policy affects many declaration sites, so test both wrapper and wrapped-value behavior.

## 10. Common errors and diagnostics

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Constraint on `Box<@NotBlank String>` does not run or reports missing extractor | Extractor is not registered or signature targets wrong type argument | Check `ValueExtractor<Box<@ExtractedValue ?>>` and register via factory/ServiceLoader |
| `@NotBlank Box<String>` throws `UnexpectedTypeException` | Constraint targets `Box` while validator only supports strings | Use `Box<@NotBlank String>`, `@UnwrapByDefault`, or `Unwrapping.Unwrap` as appropriate |
| `@NotNull Box<String>` does not distinguish inner vs outer null | Default unwrapping changes the inspected target | Use `Skip` to check the container reference, and a separate constraint for the element |
| `@Min` on `OptionalInt.empty()` reports no error | Extracted value is `null` and `@Min` does not forbid null | Add a presence constraint at the right layer |
| Creating an extractor with two `@ExtractedValue` | Invalid extractor signature | Each extractor has exactly one extracted site; split K/V if needed |
| Generic value extractor reports invalid definition | Setting `type = ...` on `@ExtractedValue` inside a type argument | Omit `type` for generics; use `@ExtractedValue(type=...)` only for non-generics |
| Error path lacks index/key | Used `receiver.value(...)` instead of indexed/keyed receiver | Choose `indexedValue`/`keyedValue` and pass the position/key |
| Spring MVC still accepts invalid data | Validation not triggered or extractor not registered with Spring's provider | Check starter, `@Valid`/`@Validated`, ServiceLoader, and which `Validator` runs |
| Fails only when adding `Skip` | Constraint's validator does not support the container type | Use a constraint suited to check the container; `Skip` does not create a new validator |

Recognizing key exception types:
- `ValueExtractorDefinitionException`: invalid **extractor definition**, such as not declaring `@ExtractedValue` properly.
- `ValueExtractorDeclarationException`: conflicting **extractor declaration/registration**, such as duplicate extractors for the same container/type parameter.
- `ConstraintDeclarationException`: invalid constraint/container declaration or resolution.
- `UnexpectedTypeException`: no validator found for the **actual type targeted by the constraint** (for example, `@NotBlank` targeting `Box`).

Do not handle these configuration errors by catching exceptions and skipping validation. Fix the extractor signature, annotation placement, and registration before deploying.

## 11. Recommended testing strategy

When writing a shared wrapper, test at least these **independent axes**, not just a single valid input:

| Scenario | Expected result to verify |
| --- | --- |
| Container with valid data | No violations |
| Container with invalid data | Constraint on wrapped value catches the error |
| Container holding `null` inside | Element constraint handles null per its contract |
| Container reference itself is `null` | Wrapper-level constraint responds properly |
| Outer constraint + `@UnwrapByDefault` | Unwraps by default |
| Outer constraint + `Unwrapping.Skip` | Validates the container |
| Outer constraint + `Unwrapping.Unwrap` | Forces element validation even when extractor does not unwrap by default |
| Constraint on type argument | Works even without `@UnwrapByDefault` |
| `Box<@Valid Address>` | Cascades to `Address` constraints |
| Two potentially overlapping extractors | Configuration is unambiguous and errors are caught early |

In tests, besides `getMessage()`, verify `getPropertyPath()` and `getInvalidValue()` on `ConstraintViolation`. Depending on the receiver node name, property paths can differ; test the path whenever it is part of the error API contract returned to clients.

## 12. Reinforcement exercises

1. Remove `@UnwrapByDefault` from `BoxExtractor` in section 6, then replace `@NotBlank Box<String> code` with `Box<@NotBlank String> code`. Predict `invalid` before and after running.
2. Add fields `@NotNull Box<String> mandatoryValue` and `@NotNull(payload = Unwrapping.Skip.class) Box<String> mandatoryContainer`. Compare when both are `new Box<>(null)` and when both are `null`.
3. Write a `ValueExtractor` for a custom multi-element container, calling `indexedValue("<item>", index, value)`; test constraints on the type argument and observe the property path.
4. Put `@Valid` on an object inside `Box`, test valid data and an empty inner field; verify cascading needs no `Unwrapping.Unwrap`.
5. Switch extractor registration from `Configuration.addValueExtractor` to ServiceLoader, keep the same test cases, and verify the provider uses the right extractor when running in Spring.

**Key takeaway:** `@ExtractedValue` states *what to extract*; `ValueReceiver` states *in what structure to pass those values to the validator*; `@UnwrapByDefault` states *whether constraints on the wrapper should target the inside by default*; `Unwrapping.Unwrap/Skip` states *a per-constraint override*.

## 13. References

- [Jakarta Bean Validation 3.0 specification — Value extraction and implicit unwrapping](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#valueextractordefinition)
- [Jakarta Validation API — `ExtractedValue`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valueextraction/extractedvalue)
- [Jakarta Validation API — `UnwrapByDefault`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valueextraction/unwrapbydefault)
- [Jakarta Validation API — `Unwrapping`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valueextraction/unwrapping)
- [Hibernate Validator 8 Reference Guide — Value extraction](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-valueextraction)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)