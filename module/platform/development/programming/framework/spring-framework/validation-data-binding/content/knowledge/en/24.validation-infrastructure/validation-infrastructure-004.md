# ValueExtractor for Custom Container Types in Spring Framework and Jakarta Validation

## 1. The problem to solve

Suppose an application has a custom wrapper type:

~~~java
public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }
}
~~~

You want to validate the **value inside** `Box<T>`, for example:

~~~java
private Box<@NotBlank String> referenceCode;
private Box<@Valid Customer> customer;
~~~

The `@NotBlank` and `@Valid` annotations are placed on the **type parameter** `T`. Jakarta Validation needs to know how to obtain `T` from `Box<T>`. For common containers such as `List`, `Iterable`, `Map`, and `Optional`, the provider usually includes default extractors. For your own `Box<T>`, you must supply a `ValueExtractor` and **register the extractor** with the same `ValidatorFactory` configuration the application uses.

**`ValueExtractor` only describes how to extract elements so validation can continue.** It is not a valid/invalid rule, does not replace `ConstraintValidator`, does not convert JSON into Java objects, and does not perform data binding. Whether a value is valid is still decided by `@NotBlank`, `@Min`, `@Valid`, or a specific constraint.

Desired results:

- `Box.of("A-01")` with `@NotBlank` on the element: valid.
- `Box.of("")` with `@NotBlank` on the element: produces a violation.
- `Box.of(new Customer(""))` with `@Valid` on the type parameter: cascades into `Customer.name` and catches `@NotBlank`.
- `Box` container is `null`: the extractor is not called; if the container itself must exist, place `@NotNull` on the `Box` property.

Distinguish the two validation layers clearly:

~~~java
@NotNull(message = "Data box must not be null")
private Box<@NotBlank(message = "Code must not be blank") String> referenceCode;
~~~

`@NotNull` validates the **`Box` object**, whereas `@NotBlank` validates the **`String` held by `Box`**. If you only write `@NotBlank Box<String>`, the constraint applies to the `Box` type by default and usually has no matching validator, unless explicit/implicit unwrapping is configured as shown later.

## 2. How does `ValueExtractor` work?

Jakarta Validation follows this high-level flow:

~~~text
Object with a property holding a container
  └── Box<@NotBlank String>
       ├── Provider selects the extractor for Box<T>
       ├── extractValues(box, receiver)
       │    └── receiver.value(null, box.getValue())
       └── Runs @NotBlank on the extracted String
              └── Produces ConstraintViolation (if invalid)
~~~

Main interface:

~~~java
package jakarta.validation.valueextraction;

public interface ValueExtractor<T> {
    void extractValues(T originalValue, ValueReceiver receiver);
}
~~~

*The snippet above is a simplified API signature for explanation, not a file to define yourself in the project.*

You implement `ValueExtractor<Container<...>>`; on the **type parameter being extracted**, place `@ExtractedValue`. Inside `extractValues`, call one of `ValueReceiver`'s methods to hand values to the validation engine. For a single-valued container like `Box<T>`, use `receiver.value(...)`.

### The four key methods of `ValueReceiver`

| Method | When to use | Path information received by the engine |
| --- | --- | --- |
| `value(nodeName, value)` | Single-value wrappers: `Box<T>`, `Optional`-like types | Value; no index/key |
| `iterableValue(nodeName, value)` | Multi-element collections without stable indices such as `Set` | Marks element as belonging to an iterable |
| `indexedValue(nodeName, index, value)` | Positional containers such as lists, arrays, or custom indexed collections | Marks iterable with index |
| `keyedValue(nodeName, key, value)` | Keyed containers, similar to maps | Marks iterable with key |

`nodeName` is the **container element node name** on `ConstraintViolation#getPropertyPath()`. Pass `null` to avoid adding an element node; for a single-value `Box<T>`, this attaches the violation directly to the property holding `Box`. If you pass `"<box element>"`, the path includes an extra node describing the container element. For multi-element containers, a node name along with index/key is very helpful to pinpoint which element failed.

**Rule:** call the appropriate `ValueReceiver` method for **each contained value**. Do not invoke `validator.validate(...)` inside the extractor, do not call `ConstraintValidator` manually, and do not mutate elements during extraction. Running constraints, cascading, groups, messages, and building paths belong to the validation engine.

## 3. Complete example: validating a `Box<T>` and cascading to a child object

Standalone example using **Java 17, Spring Boot 3.5.x, Jakarta Validation**. Spring Boot is used here to manage dependencies and tests; the test suite registers `BoxValueExtractor` directly so you can understand the mechanism before integrating Spring MVC.

File layout:

~~~text
pom.xml
src/main/java/com/example/validation/
  Box.java
  BoxValueExtractor.java
  Customer.java
  Submission.java
src/test/java/com/example/validation/
  BoxValueExtractorTest.java
~~~

### 3.1. Maven configuration

~~~xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>custom-container-validation</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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
</project>
~~~

`spring-boot-starter-validation` brings a Bean Validation provider (typically Hibernate Validator) onto the classpath. Adding only `jakarta.validation-api` without a provider is not enough to execute constraints. The project does not need to start a web server to run this test.

### 3.2. Container type `Box<T>`

~~~java
// src/main/java/com/example/validation/Box.java
package com.example.validation;

public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }
}
~~~

This container has exactly **one type parameter**, is not `Iterable`, and has no built-in extractor. The goal is to make annotations placed on `T` work.

### 3.3. Creating `ValueExtractor`

~~~java
// src/main/java/com/example/validation/BoxValueExtractor.java
package com.example.validation;

import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.ValueExtractor;

public final class BoxValueExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {

    @Override
    public void extractValues(Box<?> originalValue, ValueReceiver receiver) {
        receiver.value(null, originalValue.getValue());
    }
}
~~~

Part-by-part explanation:

1. `ValueExtractor<Box<@ExtractedValue ?>>` tells the provider that the extractor accepts `Box` and the extracted value resides at the **first type parameter** (`T`). This is an annotation of the **extractor declaration**, distinct from `@NotBlank`/`@Valid` in DTOs.
2. `originalValue` is the container passed in by the engine; per the Jakarta Validation contract, it is **never `null`** when this method is called.
3. `receiver.value(null, originalValue.getValue())` passes the value inside `Box` to the engine. The first `null` is the node name, **not the value being validated**.
4. If `Box` holds `null`, still pass `null` as the second argument so element constraints like `@NotBlank`/`@NotNull` handle it properly. Do not arbitrarily skip `null` elements.
5. This extractor does not need `@Component`, `@Bean`, or `@Validated` to take effect once **registered via Bean Validation configuration**. Merely declaring the class is not enough.

We deliberately omit `@UnwrapByDefault`: we want constraints on the **type argument** (`Box<@NotBlank String>`), rather than automatically redirecting every constraint placed on `Box` to `String`.

### 3.4. A child object to test cascading

~~~java
// src/main/java/com/example/validation/Customer.java
package com.example.validation;

import jakarta.validation.constraints.NotBlank;

public final class Customer {
    @NotBlank(message = "Customer name must not be blank")
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

### 3.5. Placing constraints on elements inside `Box`

~~~java
// src/main/java/com/example/validation/Submission.java
package com.example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public final class Submission {
    @NotNull(message = "Code box must not be null")
    private final Box<
            @NotBlank(message = "Code must not be blank") String> code;

    private final Box<@Valid Customer> customer;

    public Submission(Box<String> code, Box<Customer> customer) {
        this.code = code;
        this.customer = customer;
    }

    public Box<String> getCode() {
        return code;
    }

    public Box<Customer> getCustomer() {
        return customer;
    }
}
~~~

There are three different rules:

- `@NotNull` placed **outside** `Box<...>`: validates the container property `code`.
- `@NotBlank` placed **inside** `Box<...>`: validates the `String` inside `code` after extraction.
- `@Valid` placed on `Customer` inside `Box<...>`: after extraction, validates constraints inside the `Customer` object.

`@Valid` does not itself mark `Box` valid or invalid; it requests **cascaded validation** on the inner value. The constructor and getters here serve the plain Java example; when receiving JSON/form data in Spring MVC, you also need to design the DTO to match deserialization/binding mechanisms.

### 3.6. Runnable test and expected output

~~~java
// src/test/java/com/example/validation/BoxValueExtractorTest.java
package com.example.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BoxValueExtractorTest {

    @Test
    void validatesContainerElementAndCascades() {
        try (ValidatorFactory factory = Validation.byDefaultProvider()
                .configure()
                .addValueExtractor(new BoxValueExtractor())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Submission form = new Submission(
                    new Box<>(""),
                    new Box<>(new Customer(""))
            );

            Set<ConstraintViolation<Submission>> violations =
                    validator.validate(form);

            Map<String, String> errors = violations.stream()
                    .collect(Collectors.toMap(
                            v -> v.getPropertyPath().toString(),
                            ConstraintViolation::getMessage
                    ));

            assertEquals(Map.of(
                    "code", "Code must not be blank",
                    "customer.name", "Customer name must not be blank"
            ), errors);

            assertTrue(validator.validate(new Submission(
                    new Box<>("ORD-01"),
                    new Box<>(new Customer("An"))
            )).isEmpty());
        }
    }

    @Test
    void distinguishesNullContainerFromNullElement() {
        try (ValidatorFactory factory = Validation.byDefaultProvider()
                .configure()
                .addValueExtractor(new BoxValueExtractor())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Set<ConstraintViolation<Submission>> nullContainer =
                    validator.validate(new Submission(
                            null, new Box<>(new Customer("An"))));

            assertEquals(1, nullContainer.size());
            assertEquals("code", nullContainer.iterator().next()
                    .getPropertyPath().toString());
            assertEquals("Code box must not be null",
                    nullContainer.iterator().next().getMessage());

            Set<ConstraintViolation<Submission>> nullElement =
                    validator.validate(new Submission(
                            new Box<>(null),
                            new Box<>(new Customer("An"))));

            assertEquals(1, nullElement.size());
            assertEquals("code", nullElement.iterator().next()
                    .getPropertyPath().toString());
            assertEquals("Code must not be blank",
                    nullElement.iterator().next().getMessage());
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn test
~~~

**Expected result:** Maven runs **2 tests** successfully, with no assertion failures. The first test finds the exact two property paths `code` and `customer.name`; the second test proves the difference between a `null` `Box` and a `Box` containing a `null` element. Test method names, counts, and log formats may vary by Maven/Surefire version, so only rely on the asserted conditions.

An important point is that `"code"`, rather than adding `"<box element>"`, appears because the extractor used `receiver.value(null, ...)`. This is intentional for single-value wrappers.

## 4. Registering the extractor so Spring uses the right `ValidatorFactory`

**Writing the extractor class does not make it active yet.** You must register it with the provider. Main approaches:

| Approach | Scope | When to use |
| --- | --- | --- |
| `Configuration#addValueExtractor(...)` | `ValidatorFactory` built from that configuration | Tests, manual bootstrap, explicit setup |
| Spring Boot `ValidationConfigurationCustomizer` | Validator factory auto-configured by Boot | Spring Boot 3.x applications |
| Java `ServiceLoader` | Factories reading registrations from classpath | Packaging libraries shared across projects |
| `META-INF/validation.xml` | Bean Validation config for the associated factory | Projects managing provider via XML |
| `ValidatorContext#addValueExtractor(...)` | `Validator` created from that context | Need adjustment scoped to a single validator |

### 4.1. Manual bootstrap

In the test above:

~~~java
ValidatorFactory factory = Validation.byDefaultProvider()
        .configure()
        .addValueExtractor(new BoxValueExtractor())
        .buildValidatorFactory();

try {
    Validator validator = factory.getValidator();
    // validator.validate(form);
} finally {
    factory.close();
}
~~~

This is the most direct way to prove the extractor works. `ValidatorFactory` should be reused across the application rather than created per request; tests can close the factory afterward. The same container type and type parameter should not have duplicate extractors registered in the same configuration.

### 4.2. Spring Boot 3.x: using `ValidationConfigurationCustomizer`

In an application with `spring-boot-starter-validation`, define a bean:

~~~java
// src/main/java/com/example/validation/ValidationConfig.java
package com.example.validation;

import org.springframework.boot.autoconfigure.validation.ValidationConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ValidationConfig {

    @Bean
    ValidationConfigurationCustomizer boxExtractorCustomizer() {
        return configuration ->
                configuration.addValueExtractor(new BoxValueExtractor());
    }
}
~~~

Spring Boot uses the customizer to build the default `LocalValidatorFactoryBean`, so `@Valid` on Spring MVC models, request DTOs, and injected `jakarta.validation.Validator` instances can use this extractor when they point to the Boot-managed validator.

**Version scope:** the import path `org.springframework.boot.autoconfigure.validation.ValidationConfigurationCustomizer` is for **Spring Boot 3.x**. Spring Boot 4 reorganized auto-configuration packages; when upgrading the framework, check the Javadoc for that exact version rather than copying old imports.

For Spring MVC to trigger validation, a controller can declare `@Valid @RequestBody Submission request` or `@Valid @ModelAttribute("submission") Submission form` depending on the payload type. Creating a `Submission` instance from a request **is a separate binding/deserialization concern**; the immutable class in the test example needs suitable constructor mapping or a DTO if used for real HTTP requests.

### 4.3. Registering via Java `ServiceLoader`

In a library distributing an extractor, create the file:

~~~text
src/main/resources/META-INF/services/jakarta.validation.valueextraction.ValueExtractor
~~~

Contents: **one line with the fully qualified class name**:

~~~text
com.example.validation.BoxValueExtractor
~~~

The class must have a constructor that `ServiceLoader` can instantiate (for example, a public no-arg constructor) and reside on the appropriate classpath/module path. Once packaged into a JAR, the provider can discover the registration via the service mechanism. Do not name the file `javax.validation.valueextraction.ValueExtractor` when using Jakarta Validation 3.x.

Use **one** primary registration method per extractor in a configuration to control precedence cleanly and avoid duplicate definitions. Hibernate Validator has a precedence order across built-in extractors, service loader, XML, factory configuration, and validator context; a custom extractor at a higher configuration level can override one for the same container/type parameter at a lower level.

## 5. Multi-element containers: paths, indices, and keys

`receiver.value(...)` is the natural choice for single-value wrappers. If you build a multi-element type, call `indexedValue`/`iterableValue`/`keyedValue` accurately according to its structure. This determines the ability to locate failing elements on `ConstraintViolation#getPropertyPath()`.

### 5.1. Positional container: `Slots<T>`

Suppose `Slots<T>` holds a list and you want to validate each slot:

~~~java
// Additional example; place in separate classes when used in a project
package com.example.validation;

import java.util.List;

public final class Slots<T> {
    private final List<T> elements;

    public Slots(List<T> elements) {
        this.elements = List.copyOf(elements);
    }

    public List<T> getElements() {
        return elements;
    }
}
~~~

~~~java
package com.example.validation;

import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.ValueExtractor;

public final class SlotsValueExtractor
        implements ValueExtractor<Slots<@ExtractedValue ?>> {

    @Override
    public void extractValues(Slots<?> originalValue, ValueReceiver receiver) {
        for (int i = 0; i < originalValue.getElements().size(); i++) {
            receiver.indexedValue(
                    "<slot>", i, originalValue.getElements().get(i));
        }
    }
}
~~~

After **registering `SlotsValueExtractor`**, a DTO can declare:

~~~java
private Slots<@NotBlank String> labels;
~~~

If an element fails, the engine can include the index along with the `"<slot>"` node in the property path, tracing back to `labels` and the corresponding slot. With the path API, read `Path.Node#isInIterable()`, `getIndex()`, or `getKey()` when structural inspection is needed; converting the path to a string is handled by the provider.

**Note:** `List.copyOf(elements)` in `Slots` **does not accept null elements**. If you need to demonstrate `@NotNull` validation on individual elements, choose a storage representation that allows nulls; do not rely on `List.copyOf` to construct a list containing null.

### 5.2. Unindexed containers and keyed containers

For a collection not positioned by index, use:

~~~java
for (Object element : customSet.elements()) {
    receiver.iterableValue("<element>", element);
}
~~~

For a keyed container, such as map entries:

~~~java
for (var entry : customMap.entries()) {
    receiver.keyedValue(
            "<value>", entry.getKey(), entry.getValue());
}
~~~

These two snippets are **illustrative bodies** of an `extractValues(...)` method; `customSet` and `customMap` represent your own container's API, not standard Java library classes. To make a runnable class, replace them with the real API of your container type.

If a type holds both keys and values with **two type parameters**, such as `PairMap<K,V>`, you may need **two separate extractors**, each marking exactly one type parameter with `@ExtractedValue`: one extractor for `K`, one for `V`. Do not mark two extracted type parameters in a single extractor declaration.

## 6. When to use `@UnwrapByDefault`?

There are two different syntaxes with different purposes:

~~~java
// Place constraint directly on the container element:
Box<@NotBlank String> code;

// Place constraint on the Box object itself, when unwrapping is not requested:
@NotNull
Box<String> box;
~~~

In the first case, the `ValueExtractor<Box<@ExtractedValue ?>>` extractor helps the validation engine obtain `String`. In the second case, `@NotNull` checks whether `box` is null, **without** unwrapping.

If you want a wrapper type to be “transparent” by default for constraints placed on the wrapper, you can annotate the extractor with `@UnwrapByDefault`:

~~~java
// Illustrates an alternative extractor only; do not register simultaneously
// with BoxValueExtractor from section 3 for the same Box<T>.
package com.example.validation;

import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.UnwrapByDefault;
import jakarta.validation.valueextraction.ValueExtractor;

@UnwrapByDefault
public final class UnwrappingBoxValueExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {

    @Override
    public void extractValues(Box<?> originalValue, ValueReceiver receiver) {
        receiver.value(null, originalValue.getValue());
    }
}
~~~

When an extractor of this kind is selected, constraint annotations placed **on the wrapper** can be applied automatically to the inner value:

~~~java
// With UnwrappingBoxValueExtractor registered:
@NotBlank
Box<String> code;
~~~

Do not choose implicit unwrapping just to make `Box<@NotBlank String>` work; container-element validation already solves that need. `@UnwrapByDefault` changes the **meaning** of certain constraints declared on the wrapper, especially `@NotNull`. When you need to validate the wrapper instead of the inner value, you can control this via payload `jakarta.validation.valueextraction.Unwrapping.Skip`; conversely, `Unwrapping.Unwrap` requests unwrapping on a specific constraint when an appropriate extractor exists.

Syntax example (used in a class with `import jakarta.validation.valueextraction.Unwrapping;`):

~~~java
@NotNull(payload = Unwrapping.Skip.class)
private Box<String> code;
~~~

We omit `@UnwrapByDefault` in the main example to preserve the clear distinction between `@NotNull Box<T>` and `Box<@NotBlank T>`. When designing a wrapper library used across multiple modules, the unwrapping choice should be clearly documented in the API docs.

## 7. How does `ValueExtractor` relate to Spring Validation and Data Binding?

In the Spring ecosystem, the following components are easily confused:

| Component | Function | Does it solve `Box<@NotBlank String>`? |
| --- | --- | --- |
| `Converter<S,T>` / `Formatter` | Converts strings/types during data binding | No, only handles type conversion |
| `DataBinder` / `WebDataBinder` | Binds request data to target object, records binding errors | Does not define Bean Validation extraction |
| `jakarta.validation.ConstraintValidator` | Executes a specific constraint rule | Does not automatically extract elements from arbitrary custom containers |
| `jakarta.validation.valueextraction.ValueExtractor` | Supplies container elements to Bean Validation | Yes, if registered properly |
| `LocalValidatorFactoryBean` | Spring adapter/factory for Jakarta Bean Validation | Uses extractors registered in configuration |
| `BindingResult` | Holds field errors and global errors after binding/validation | Can receive errors produced from element constraints |

Typical processing chain when Spring MVC validates a request:

~~~text
HTTP request
  -> Jackson / Spring DataBinder creates and populates the DTO
  -> @Valid / Validator is invoked by Spring
  -> Bean Validation locates container element constraints
  -> ValueExtractor retrieves each value inside the container
  -> ConstraintValidator validates the value
  -> ConstraintViolation carries the property path
  -> Spring maps it to corresponding field/global errors
~~~

When an application binds a DTO like `Submission` successfully, a violation on the element inside `code` with `nodeName=null` has path `code`; Spring typically maps this path to a `FieldError` for field `code`. For indexed or keyed containers, the path carries additional metadata so the UI/API can identify the exact position. The path shows where the error occurred; it does not tell Spring how to bind requests into `Box`.

Do not assume that merely adding `@Bean BoxValueExtractor` will make Spring automatically collect every `ValueExtractor` bean into the provider. In Spring Boot 3.x, the explicit framework-supported approach is a `ValidationConfigurationCustomizer` bean or an appropriate service loader/configuration.

## 8. Designing and handling tricky scenarios

### 8.1. Null semantics and empty containers

| State | Does `ValueExtractor` run? | Where constraints are needed |
| --- | --- | --- |
| `Box` is `null` | No | `@NotNull` on the container property if required |
| `Box` holds a `null` value | Yes, passes null element via receiver | `Box<@NotNull T>` or an appropriate constraint |
| `Box` holds `String=""` | Yes | `Box<@NotBlank String>` |
| `Slots` has no elements | No elements to receive; extractor may be called but passes no elements to receiver | `@Size` on the container if a matching validator exists, or a custom size constraint |
| `Slots` has multiple elements | Yes, receiver gets each element | Constraints on the type argument and `@Valid` if cascading is needed |

`ValueExtractor` **is not responsible** for evaluating the size, emptiness, or validity of the container as a whole. Those rules belong to container-level constraints or custom constraints. Do not apply `@NotBlank` to a custom type assuming it understands `Box`'s structure.

### 8.2. Multiple extractors and precedence

The provider selects an extractor based on **container type**, **type parameter**, and specificity. If two extractors at the same configuration level apply to the exact same type parameter of the same container, you may encounter definition/declaration errors or ambiguity during initialization/validation. To avoid this:

- Keep a clear strategy for each type parameter that needs extraction.
- Do not redundantly register equivalent extractors in the Spring customizer, service loader, and custom configurations without controlling order.
- Ensure the right factory is the one actually running validation. A test that builds its own `ValidatorFactory` will not inherit the application's Spring Boot configuration.
- If a container extends/implements multiple generic types, consider built-in provider extractor precedence and test validation against each declared property type.

### 8.3. Two type parameters, non-generic wrappers, and declaration limits

- For `Pair<L,R>`, mark at most **one** type parameter with `@ExtractedValue` in each extractor definition. When both need validation, typically create two separate extractors.
- For **non-generic** wrappers, you can declare `@ExtractedValue(type = SomeType.class)` on the container type use in `ValueExtractor` to describe the extracted element type. You cannot use `?` as a generic type argument if the container type has no type parameters.
- Place `@ExtractedValue` on the **exact type argument** carrying constraints; choosing the wrong position prevents the provider from finding the matching extractor.
- Do not use raw types or strip generic information from properties if you rely on constraints inside type parameters.

### 8.4. Performance and thread safety

An extractor can run many times across validation passes; keep implementations **lightweight and stateless**, only reading the container and calling the receiver. Do not call remote services, query databases, or mutate data inside `extractValues`. With large collections, validation time can scale with the number of elements traversed; enforce input size limits beforehand rather than asking validation to scan everything.

If a container allows concurrent modification, mutating while traversing can produce wrong paths/indices or throw exceptions. Keep inputs stable during validation and use immutable snapshots where appropriate. Stateless singleton extractors like `BoxValueExtractor` in the example are suitable for reuse across many requests.

## 9. Common mistakes and diagnostics

1. **Writing a `ValueExtractor` without registering it:** the provider has no extraction metadata for the custom type. Check factory configuration, Spring customizers, service loader, and dependencies.
2. **Misplacing `@ExtractedValue` or marking multiple type arguments:** the provider cannot unambiguously determine the extracted element type. Verify the signature `ValueExtractor<Box<@ExtractedValue ?>>`.
3. **Passing the container itself to the receiver:** `receiver.value(null, originalValue)` gives the `String` constraint the wrong type; pass `originalValue.getValue()`.
4. **Using `indexedValue` for single-value wrappers:** produces meaningless indexed paths. Use `value(null, ...)` for single-value wrappers.
5. **Skipping null elements with `if (value != null)`:** can prevent `Box<@NotNull String>` from reporting errors; only skip according to the container's true semantics.
6. **Placing constraints in the wrong spot:** `@NotNull Box<String>` validates the container, whereas `Box<@NotNull String>` validates the element; the two cases are different.
7. **Adding `@Valid` on a child object without an extractor:** cascading will not enter the custom type. Verify registration and place `@Valid` on the appropriate type argument.
8. **Expecting an extractor to fix data binding:** Jackson failing to instantiate `Box<T>` is a constructor/deserializer mapping issue, separate from Bean Validation.
9. **Using the wrong package for the extractor:** Spring Boot 3.x uses `jakarta.validation.*`; do not mix in `javax.validation.*` from legacy stacks.
10. **Ignoring property paths in tests:** only asserting `hasErrors()` does not prove errors attach to the right field/slot. Test `ConstraintViolation#getPropertyPath()` along with the violation message/type.
11. **Declaring two conflicting unwrap strategies:** understand `@UnwrapByDefault` and override configuration before adding it to a widely used wrapper.
12. **Confusing `@Component` with extractor registration:** component scanning and Jakarta Bean Validation bootstrapping are two separate mechanisms; use the factory managed by the application.

When debugging, start from a minimal `Box<@NotBlank String>` case, register `BoxValueExtractor` on a standalone factory, inspect the property path, and only then bring it into Spring. This isolates whether the issue lies in the extractor or integration configuration.

## 10. Implementation checklist

1. Identify the custom container kind: single-valued, multi-element indexed, unindexed iterable, or keyed map.
2. Place constraints on the right type argument (`Box<@NotBlank String>`, `Box<@Valid Customer>`).
3. Implement `ValueExtractor<Container<@ExtractedValue ?>>`, or an extractor matching the container's type parameters.
4. Call the right `ValueReceiver` method for each element; choose `nodeName=null` or a specific name according to property path needs.
5. Register the extractor with the **right `ValidatorFactory`**; on Boot 3.x use `ValidationConfigurationCustomizer` when appropriate.
6. Test valid values, invalid values, null container, null element, cascading, property paths, and index/key localization.
7. If using Spring MVC, confirm the DTO binds properly before evaluating validation errors; verify `BindingResult` on the expected field.
8. Only add `@UnwrapByDefault` when you intentionally want to change the semantics of constraints placed directly on the wrapper.

## References

- Jakarta Validation 3.1, `ValueExtractor.ValueReceiver`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/valueextraction/valueextractor.valuereceiver
- Jakarta Validation specification, value extractors and property path: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1
- Hibernate Validator Reference Guide, Chapter 7 (Value extraction): https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#chapter-valueextraction
- Spring Boot 3.5 Reference, Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 API, `ValidationConfigurationCustomizer`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/validation/ValidationConfigurationCustomizer.html
