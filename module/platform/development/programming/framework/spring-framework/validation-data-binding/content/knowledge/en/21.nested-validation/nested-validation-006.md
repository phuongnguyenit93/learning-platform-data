# Handling Null Elements and Null Child Objects in Nested Validation

> **Module:** Spring Framework – validation-data-binding  
> **Parent Topic:** Nested Validation  
> **Scope:** Jakarta Validation/Bean Validation and Spring MVC; distinguishing `null` child objects, `null` containers, `null` elements, empty containers, `@Valid`, and requiredness constraints.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why `@Valid` **does not by itself forbid** a child object from being `null`.
2. Use `@NotNull @Valid` to both require a child object's presence and validate constraints **inside** that object.
3. Distinguish four states: **null container**, **empty container**, **null element**, and **non-null element with invalid internal data**.
4. Correctly write `List<@NotNull @Valid Child>`, `List<@NotBlank String>`, and `Map<@NotBlank String, @NotNull @Valid Child>`.
5. Understand that `@NotNull`, `@NotEmpty`, `@Size`, `@NotBlank`, and `@Valid` have distinct responsibilities.
6. Read `ConstraintViolation#getPropertyPath()` in nested validation and avoid false assumptions about path names on collections/maps.
7. Trigger validation in Spring MVC and distinguish deserialization/binding errors from constraint violations.
8. Test various null scenarios with a deterministic Java 17+ program, independent of timing or `Set` iteration order.

## 2. Root Principle: `@Valid` Is Cascading, Not Non-Null

`jakarta.validation.Valid` is a **deep-validation** (cascaded validation) directive. When a Jakarta Validation provider is validating a parent object and encounters an association annotated with `@Valid`:

- If the association points to a **non-null object**, the provider continues and evaluates constraints on the child object.
- If the association is **null**, the provider **skips cascading** to the child object and does not produce an error from `@Valid` alone.
- If the association holds a container such as `List` or `Map`, the provider can cascade into **existing child elements**, whereas null references are not beans to traverse.
- The provider tracks the object-graph traversal path to prevent infinite loops from cyclic associations.

This is a rule of the Jakarta Validation specification, not a quirk specific to Spring or Hibernate Validator.

~~~text
validate(Order)
    |
    +-- customer: @Valid
    |       |
    |       +-- customer != null --> validate(Customer)
    |       |
    |       +-- customer == null --> skip cascade, do not report error by itself
    |
    +-- delivery: @NotNull @Valid
            |
            +-- delivery == null --> @NotNull reports violation
            |                      @Valid still does not cascade
            |
            +-- delivery != null --> @NotNull passes
                                   @Valid validates Delivery.*
~~~

Key point: **Presence** and **internal validity** are two independent requirements.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

class Purchase {
    @Valid
    private Customer optionalCustomer;

    @NotNull
    @Valid
    private Address requiredDeliveryAddress;
}
~~~

The snippet above is an **illustrative DTO fragment**, not a standalone class with `main`.

- `optionalCustomer == null`: no error from `@Valid`; if non-null, `Customer`'s constraints are evaluated.
- `requiredDeliveryAddress == null`: error from `@NotNull`. `@Valid` does not invoke the validator for a null object.
- `requiredDeliveryAddress != null`: `@NotNull` passes; constraints inside `Address` can still fail.

If a child object **must not be absent**, you usually must declare **both `@NotNull` and `@Valid`**. `@NotNull` alone does not check inner fields; `@Valid` alone does not require the object to exist.

## 3. State Table to Remember

Suppose class `Address` is:

~~~java
import jakarta.validation.constraints.NotBlank;

public record Address(@NotBlank String city) {}
~~~

And the parent object has field `@Valid Address address`.

| `address` | Result with `@Valid` Only | Reason |
| --- | --- | --- |
| `null` | No violations | No child bean to cascade into |
| `new Address("Ha Noi")` | No violations | Cascade runs; `city` is valid |
| `new Address("")` | One violation on `city` | `@NotBlank` fails |
| `new Address(null)` | One violation on `city` | `@NotBlank` rejects null |

If the parent changes to `@NotNull @Valid Address address`, only the `address == null` case changes to **one violation on `address`**. When the child object exists, its internal contents are still checked via `@Valid`.

Specifically, `@NotBlank` rejects `null`, empty strings, and whitespace-only strings. Do not assume "every constraint ignores null": many constraints only check a value when present (e.g., `@Size`, `@Pattern`, `@Positive`), whereas `@NotNull`, `@NotEmpty`, and `@NotBlank` are designed to detect missing/empty data.

## 4. Null Containers, Empty Containers, and Null Elements

With a list of addresses, there are **three distinct levels**:

~~~text
Order
  |
  +-- stops: List<Address>           [list reference]
        |
        +-- stops[0]: Address         [element 0]
        |     |
        |     +-- city: String        [field in element 0]
        |
        +-- stops[1]: Address         [element 1]
              |
              +-- city: String
~~~

A different null value can appear at each level.

### 4.1. `null` List

~~~java
@NotNull
private List<@Valid Address> stops;
~~~

If `stops == null`, `@NotNull` reports an error on **property `stops`**; there are no elements to cascade into. Without `@NotNull`, `@Valid` on the type argument alone does not turn a null list into an error.

### 4.2. Empty List

~~~java
@NotNull
private List<@Valid Address> stops;
~~~

If `stops = List.of()`, `@NotNull` **passes**, because the list exists. `@Valid` has no elements to check and produces no errors. If business logic requires **at least one element**, use `@NotEmpty` or `@Size(min = 1)` on the list itself.

### 4.3. Null Element

~~~java
@NotNull
private List<@Valid Address> stops;
~~~

If `stops = [null, Address("Ha Noi")]`, the null element is **skipped during cascading**; `@Valid` on the type argument alone does not require elements to exist. To reject null elements:

~~~java
@NotNull
private List<@NotNull @Valid Address> stops;
~~~

Then:

- Outer `@NotNull`: the list must be non-null.
- `@NotNull` **inside `<...>`**: **each element** must be non-null.
- `@Valid` **inside `<...>`**: non-null elements are cascaded to check fields of `Address`.

This is the most important pattern in the lesson.

### 4.4. Non-Null Element with Null Field

~~~java
List<Address> stops = java.util.Arrays.asList(
        new Address(null),
        new Address("Da Nang"));
~~~

`@NotNull` on the element **does not** catch an error on the first element, because `new Address(null)` **is a non-null Address object**. The `city == null` error only appears when `@Valid` cascades to `Address.city` and evaluates `@NotBlank`.

Summary by level:

| State | `@NotNull List<@Valid Address>` | `@NotNull List<@NotNull @Valid Address>` | `@NotEmpty List<@NotNull @Valid Address>` |
| --- | --- | --- | --- |
| `null` list | Error on list | Error on list | Error on list |
| `[]` list | Valid | Valid | Error: empty |
| `[null]` | No error from cascade | Error at element | Error at element; list non-empty |
| `[Address("")]` | `city` field error | `city` field error | `city` field error |
| `[Address("Hue")]` | Valid | Valid | Valid |

This table considers **only the listed annotations**. Adding other rules on elements or classes can increase the total violation count.

## 5. Distinguishing Null and Size Constraints

| Constraint | Null | Empty | Meaning |
| --- | --- | --- | --- |
| `@NotNull` on list | Invalid | Valid | List must exist |
| `@NotEmpty` on list | Invalid | Invalid | List must have at least one element |
| `@Size(min = 1)` on list | **Valid** | Invalid | Checks size when list is present |
| `@NotNull` on string | Invalid | Empty string valid | Forbids null only |
| `@NotEmpty` on string | Invalid | Invalid | Forbids null and length-0 string; `" "` still passes |
| `@NotBlank` on string | Invalid | Invalid | Forbids null, empty string, and whitespace-only string |
| `@Valid` on association | Skips cascade if null | Empty concept does not directly apply | Directive to descend when object exists |

Some useful DTO patterns:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class ShipmentRequest {
    @NotNull
    @Valid
    private Address destination;

    @NotEmpty
    private List<@NotNull @Valid Address> stops;

    @NotNull
    @Size(min = 2, max = 5)
    private List<@NotBlank String> labels;
}
~~~

This is a **DTO fragment**; classes/imports are shown in an illustrative context.

- `destination`: required delivery object, child fields must be valid.
- `stops`: list required to be **non-empty**, and every element must be a non-null object with valid fields. `@NotEmpty` already forbids a null **list**, so adding `@NotNull` outside the list is not required if you only want presence/non-emptiness.
- `labels`: list must exist and contain 2 to 5 elements; each element is a non-null, non-empty/non-blank string. `@Size(min=2)` does not forbid a null list by itself, because that constraint treats null as valid.

Do not accidentally put both `@NotNull` and `@NotEmpty` on the same list just "to be safe." When the list is null, both can report errors, resulting in redundant messages. Pick the constraint that expresses the business rule most clearly.

## 6. Constraints on Type Arguments (Container Element Constraints)

Since Bean Validation 2.0 / Jakarta Validation, constraints can be declared directly on type arguments:

~~~java
List<@NotNull Address> addresses;
List<@NotBlank String> names;
List<@NotNull @Valid Address> mandatoryAddresses;
Map<@NotBlank String, @NotNull @Valid Address> addressByCode;
~~~

These are **illustrative type declarations**, not a standalone program. They clearly express intent:

- `List<@NotNull Address>`: each element must not be null; **does not automatically validate fields of `Address`**.
- `List<@NotBlank String>`: each name is non-null and has non-whitespace characters; no `@Valid` needed because `String` is not a nested bean needing cascading.
- `List<@NotNull @Valid Address>`: both forbids null elements and descends into child objects.
- `Map<@NotBlank String, @NotNull @Valid Address>`: keys must be valid strings; values non-null; existing values cascade into `Address`.

Place annotations **at the right level**:

~~~java
@NotEmpty                     // on container
List<@NotNull @Valid Address> stops;
//    ^^^^^^^ ^^^^^^
//    on element: required + cascade
~~~

Declaring at the type argument expresses intent more accurately than the legacy `@Valid List<Address>` style, especially with nested containers. Hibernate Validator recommends placing `@Valid` on type arguments for modern collections/maps.

### 6.1. Multi-Level Lists

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public class RoutePlan {
    @NotEmpty
    private List<@NotEmpty List<@NotNull @Valid Address>> routes;
}
~~~

The outer level must exist and have routes; **each route list** must exist and be non-empty; **each Address** in a route must be non-null and valid. These type-use annotations require the provider to support value extraction for those containers; standard `List` is supported by Hibernate Validator.

Because `@NotEmpty` on a list treats null as a violation, placing it on the **element list** also protects against a null sub-route. Using only `@Size(min=1)` on the sub-route would allow null through (unless `@NotNull` is added).

### 6.2. `Map`: Null Key and Null Value Are Two Different Cases

~~~java
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public class Directory {
    @NotEmpty
    private Map<@NotBlank String,
                @NotNull @Valid Address> addresses;
}
~~~

Read carefully:

- `@NotEmpty` outside `Map`: map must not be null/empty.
- `@NotBlank String`: each key must not be null, empty, or whitespace-only.
- `@NotNull @Valid Address`: each value must not be null and must have valid properties.
- A null key or null value **differs** from a null map.
- A valid key does not prove a valid value, and vice versa.

If you write `Map<String, @Valid Address>`, a null value is skipped during cascading; add `@NotNull` on the value type argument when you need to reject it.

### 6.3. Arrays, Iterables, and Custom Containers

`@Valid` also applies to array and `Iterable` associations depending on provider support; standard containers have built-in `ValueExtractor`s to locate elements and positions. For custom containers like `Box<T>`, the provider may need a dedicated `ValueExtractor`, otherwise element constraint metadata may not execute as expected or may cause configuration errors. Check provider documentation before arbitrarily placing type-use constraints on any generic class.

For optional-semantics containers like `Optional<T>`, distinguish:
- **Null Optional variable** (no wrapper).
- **`Optional.empty()`** (wrapper exists but holds no value).
- **`Optional.of(value)`** (wrapper holds a value).

`Optional.empty()` is not equivalent in Java to a null wrapper variable, and how element constraints are extracted depends on the value extractor per specification/provider. Do not assume `@Valid` on an `Optional` requires an element to exist; declare and test requiredness rules according to your data model.

## 7. Java 17+ Program Verifying with Hibernate Validator

This section is a **runnable lab**, demonstrating seven cases: null optional child, null required child, null element, blank child property, null collection, empty collection, and valid data.

### 7.1. Create the Maven Project

Structure:

~~~text
null-cascade-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── nullcascade/
                    └── NullCascadeDemo.java
~~~

File `pom.xml`: Java 17 project, Hibernate Validator 8.x (Jakarta Validation 3.0 implementation), Jakarta EL for default message interpolation.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>null-cascade-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
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
~~~

In real Spring Boot projects, use Boot's dependency management/BOM for versions rather than copying these pinned versions.

### 7.2. Class with `main`

Save at the exact path `src/main/java/example/nullcascade/NullCascadeDemo.java`:

~~~java
package example.nullcascade;

import java.util.Arrays;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public final class NullCascadeDemo {

    public record Address(
            @NotBlank String city) {}

    public record OptionalContact(
            @Valid Address contact) {}

    public record Order(
            @NotNull @Valid Address shipping,
            @NotNull List<@NotNull @Valid Address> stops,
            @NotEmpty List<@NotBlank String> labels) {}

    private static int errors(Validator validator, Object object) {
        return validator.validate(object).size();
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            OptionalContact optionalNull =
                    new OptionalContact(null);

            Order requiredNull = new Order(
                    null,
                    List.of(new Address("Da Nang")),
                    List.of("fast"));

            Order invalidElements = new Order(
                    new Address(""),
                    Arrays.asList(null, new Address(" ")),
                    Arrays.asList("fast", null, ""));

            Order nullCollections = new Order(
                    new Address("Ha Noi"),
                    null,
                    null);

            Order emptyCollections = new Order(
                    new Address("Ha Noi"),
                    List.of(),
                    List.of());

            Order valid = new Order(
                    new Address("Ha Noi"),
                    List.of(new Address("Hue")),
                    List.of("fast"));

            System.out.println(
                    "optional-null=" + errors(validator, optionalNull));
            System.out.println(
                    "required-null=" + errors(validator, requiredNull));
            System.out.println(
                    "invalid-elements=" + errors(validator, invalidElements));
            System.out.println(
                    "null-collections=" + errors(validator, nullCollections));
            System.out.println(
                    "empty-collections=" + errors(validator, emptyCollections));
            System.out.println(
                    "valid=" + errors(validator, valid));

            try {
                validator.validate((Order) null);
            } catch (IllegalArgumentException exception) {
                System.out.println(
                        "null-root=" + exception.getClass().getSimpleName());
            }
        }
    }
}
~~~

Run in the `null-cascade-demo` directory:

~~~bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.nullcascade.NullCascadeDemo
~~~

**Stdout printed by the program itself** (excluding Maven or provider logs):

~~~text
optional-null=0
required-null=1
invalid-elements=5
null-collections=2
empty-collections=1
valid=0
null-root=IllegalArgumentException
~~~

### 7.3. Explanation of Each Result

| Case | Total Violations | Source of Errors |
| --- | ---: | --- |
| `optionalNull` | 0 | `@Valid` skips `contact == null` |
| `requiredNull` | 1 | `shipping == null` violates `@NotNull`; cascade does not run |
| `invalidElements` | 5 | `shipping.city` blank (1); null `stops` element (1); `stops` child with blank `city` (1); `labels` has one null element (1) and one empty string (1) |
| `nullCollections` | 2 | `stops == null` violates `@NotNull`; `labels == null` violates `@NotEmpty` |
| `emptyCollections` | 1 | `stops=[]` is valid for `@NotNull` alone; `labels=[]` violates `@NotEmpty` |
| `valid` | 0 | All objects/containers/elements are valid |
| `validator.validate(null)` | Exception | Null **root object** is not the same case as a null **association** skipped during cascading |

The program only prints **violation counts**, without relying on `Set<ConstraintViolation<?>>` iteration order; counts are predictable and independent of error message locale.

**Important Java note:** `List.of(null)` does not allow null elements and throws `NullPointerException` **when constructing the list**, even before Bean Validation runs. In the example, `Arrays.asList(...)` is used to intentionally construct a list containing null elements. If a test fails right at `List.of(null)`, that is not caused by Jakarta Validation's `@NotNull`.

### 7.4. Can It Run with Plain `javac/java`?

Distinguish clearly:
- `NullCascadeDemo.java` is a complete Java 17 class with `main`, but it **depends on Jakarta Validation/Hibernate Validator libraries**. Running `javac NullCascadeDemo.java` from an empty directory without a classpath will report missing `jakarta.validation` packages.
- Maven above supplies the classpath and runs the example. If you download all dependency JARs yourself, you can also compile with `javac -cp ...` and run with `java -cp ...` with **all transitive dependencies**; never write a fake or incomplete classpath and claim it runs.

Below is a plain Java 17 example further confirming the difference between a null object, null list, and null element; however, it **does not execute Jakarta Validation**:

~~~java
import java.util.Arrays;
import java.util.List;

public class NullStructureCheck {
    public static void main(String[] args) {
        List<String> noList = null;
        List<String> emptyList = List.of();
        List<String> withNull = Arrays.asList(null, "ok");

        System.out.println(noList == null);
        System.out.println(emptyList.isEmpty());
        System.out.println(withNull.get(0) == null);
        System.out.println(withNull.size());
    }
}
~~~

Save `NullStructureCheck.java` and run:

~~~bash
javac NullStructureCheck.java
java NullStructureCheck
~~~

Exact stdout:

~~~text
true
true
true
2
~~~

This is a Java data-structure check, not a replacement for `Validator.validate(...)`.

## 8. Violation Paths for Objects and Containers

`ConstraintViolation#getPropertyPath()` indicates the error location in the object graph. When validating an `Order` with `Address shipping`, paths typically look like:

~~~text
shipping                (shipping field fails @NotNull)
shipping.city           (city field of shipping object)
stops[0].<list element> (constraint on null element, rendering depends on provider)
stops[1].city           (city field of object at index 1)
labels[2].<list element>
~~~

This is a **path-format illustration**, not guaranteed stdout from the Section 7 program. With list/map container-element constraints, internal node names and string rendering can vary by provider and version. The specification provides the `Path` model with nodes, index, key, container class, and type argument index to describe structure; do not write a parser depending solely on one example string.

When returning stable API errors:
- Extract paths from `getPropertyPath()`, inspecting nodes and indices/keys when needed.
- Build error codes such as `REQUIRED_ADDRESS`, `INVALID_CITY`, and `NULL_LIST_ELEMENT` per application conventions.
- Do not pass raw `getInvalidValue()` into logs or responses, as values may hold sensitive data.
- If outputting internationalized messages, message text may vary by locale/provider.

Simple example to print paths in a **deterministic order**, placed inside a project with `Validator` and bean:

~~~java
validator.validate(bean).stream()
        .map(v -> v.getPropertyPath() + " -> " + v.getMessage())
        .sorted()
        .forEach(System.out::println);
~~~

This is an illustrative fragment, not a standalone class. `sorted()` only stabilizes print ordering; it does not turn `Path` text into a fixed API format.

## 9. Integrating into Spring MVC / Spring Boot

In Spring Boot 3+ (Spring Framework 6+), use **`jakarta.validation.*`**, not the `javax.validation.*` namespace of older versions. A typical MVC application needs:

~~~xml
<!-- Dependencies in a Boot project with parent/BOM managing versions -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

This is only a dependency fragment, not a complete `pom.xml`. `starter-validation` adds the standard provider so Spring can execute Jakarta constraints.

### 9.1. Java 17+ Controller and DTO Example

In a Spring Boot 3.x project with the starters above, save `src/main/java/example/nullweb/NullWebApplication.java`:

~~~java
package example.nullweb;

import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class NullWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(NullWebApplication.class, args);
    }

    public record AddressRequest(
            @NotBlank String city) {}

    public record OrderRequest(
            @NotNull @Valid AddressRequest shipping,
            @NotEmpty List<@NotNull @Valid AddressRequest> stops) {}

    @RestController
    public static class OrdersController {

        @PostMapping("/orders")
        public Map<String, String> create(
                @Valid @RequestBody OrderRequest request) {
            return Map.of(
                    "status", "accepted",
                    "shippingCity", request.shipping().city());
        }
    }
}
~~~

Run the project (when the corresponding Maven wrapper is present):

~~~bash
./mvnw spring-boot:run
~~~

Or use `./gradlew bootRun` if the project uses Gradle wrapper. Commands cannot run from a directory containing only Java files and XML fragments; a properly configured Boot project is required.

Send a valid request:

~~~bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"shipping":{"city":"Ha Noi"},"stops":[{"city":"Hue"}]}'
~~~

In a standard Boot environment, this request can return HTTP **200** and JSON with two properties `status` and `shippingCity`. JSON key order is not guaranteed.

Request with null child object and null element:

~~~bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"shipping":null,"stops":[null,{"city":""}]}'
~~~

After Jackson constructs the DTO, **three** constraints can fail:
1. `shipping == null` violates `@NotNull` on the child.
2. The first element of `stops` is null, violating `@NotNull` **on the type argument**.
3. The second element is an object, but `city == ""` violates `@NotBlank` after `@Valid` cascades.

`@NotEmpty` on `stops` **passes** because the list has two elements, even though one element is null.

Request with an empty list:

~~~bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"shipping":{"city":"Ha Noi"},"stops":[]}'
~~~

The list exists but is empty, violating `@NotEmpty` on the container, not `@NotNull` on elements.

In a typical MVC setup, validation failure on `@Valid @RequestBody` causes Spring to return HTTP **400**, usually via `MethodArgumentNotValidException`; the exact error payload depends on `@ControllerAdvice`, Problem Details, and server configuration. **Do not** assume the API always returns one universal error JSON or a specific order of field errors.

### 9.2. How Does a Missing Field Differ from a Null Field in JSON?

Two requests:

~~~json
{"shipping":null,"stops":[]}
~~~

and:

~~~json
{"stops":[]}
~~~

usually both produce `shipping == null` for a record component/reference field in this example, **unless special Jackson configuration exists** for missing properties, required constructor parameters, default values, or null handling. `@NotNull` validation then rejects both.

However, do not treat them as identical in all applications:
- Jackson can be configured to **fail deserialization** immediately when a property is missing or null.
- Java primitive types (`int`, `boolean`) have different default-value semantics than object wrappers; pick the right type for "required."
- For PATCH, an **omitted** field and a field **explicitly sent as null to clear it** can carry different business meanings; these two cases cannot be distinguished solely with `@NotNull` on a standard DTO.
- Data from HTML forms and query parameters goes through `WebDataBinder`/`ConversionService`, not necessarily through the same Jackson processing path.

### 9.3. Binding First, Then Validation

~~~text
HTTP JSON
    |
    v
Jackson deserialize
    |
    +-- Malformed JSON syntax or unconvertible type -> request reading error
    |
    v
OrderRequest Java (may contain null)
    |
    v
@Valid / Jakarta Validator
    |
    +-- validate shipping @NotNull and cascade @Valid
    +-- validate stops @NotEmpty
    +-- validate @NotNull and @Valid on each stops element
    |
    v
If no errors -> controller runs
If errors    -> Spring handles validation errors
~~~

Errors caused by invalid JSON types (e.g., `"stops":"not-an-array"`) typically happen **before** Bean Validation. Therefore, you cannot expect every malformed payload to produce a `ConstraintViolation`.

## 10. `@Valid` on Parent, Container, and Type Argument

Three distinct forms:

~~~java
@Valid
private Address customer;

@Valid
private List<Address> contacts;

private List<@Valid Address> preferredContacts;
~~~

In modern Bean Validation:
- The first cascades from the parent object to `Address`.
- The second is the **container-level form** supported by providers to cascade into collection elements; this form is historical and less precise for multi-level containers.
- The third explicitly declares cascading on the **type argument**; this is the preferred choice for new collections/maps, especially when combined with `@NotNull` on elements.

**Forbidding null must be at the right level**:

~~~java
@NotNull                   // requires list to exist
private List<@Valid Address> contacts;

private List<@NotNull @Valid Address> contacts2;
//           ^^^^^^^ requires each element, does not forbid null list

@NotNull
private List<@NotNull @Valid Address> contacts3;
// ^^^^^^^ forbids null list
//               ^^^^^^^ forbids null element
~~~

When requiring a non-empty list, use `@NotEmpty` on the list; when requiring each element to exist, use `@NotNull` on the type argument. Neither can be replaced by `@Valid`.

## 11. Validation Groups and Cascading into Child Objects

Validation groups determine which constraints execute. If a constraint is declared only in a custom group, calling the validator with a different group will not automatically evaluate it.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.Default;

interface OnSubmit {}

class ShippingInfo {
    @NotNull(groups = OnSubmit.class)
    private String trackingCode;
}

class Dispatch {
    @Valid
    private ShippingInfo shipping;
}
~~~

This is an **illustrative fragment**.

- Validating `Dispatch` with `Default`: cascades into the child object if non-null, but `trackingCode`'s constraint belongs to `OnSubmit` so it does not run automatically.
- Validating `Dispatch` with `OnSubmit`: cascades with the active group, and `trackingCode` is checked.
- If `shipping == null`: cascading is skipped **in both groups**.
- To require `shipping` under `OnSubmit`: declare `@NotNull(groups=OnSubmit.class)` directly on the association.
- To convert from the parent's group to another group on the child bean: use `@ConvertGroup` together with `@Valid` per Jakarta Validation.

In Spring, `@Validated(OnSubmit.class)` at the endpoint can select the group; `@Valid` remains the standard annotation for cascading. If a field has `@NotNull` without specifying `groups`, the constraint belongs to `Default` and will not run automatically when only an independent `OnSubmit` group is selected (unless appropriate group inheritance/sequences are designed).

**Takeaway:** When you suspect "`@NotNull` is not working," beyond checking whether the annotation is at the right level, check **which group is active** and whether validation is actually triggered.

## 12. Why Might Constraints on a Child Object Not Run?

Common causes:

1. **Null association:** `@Valid` skips it. To forbid null, add `@NotNull` on the association.
2. **Missing `@Valid`:** the provider only checks constraints declared on the parent object; it does not automatically scan every child bean.
3. **Mismatched group:** the child constraint belongs to a different group and is not selected.
4. **Object already checked along the traversal path of a cycle:** the provider prevents infinite loops; this is a specification safety mechanism.
5. **Custom container missing `ValueExtractor`:** elements cannot be extracted properly.
6. **Spring has not triggered validation:** missing `@Valid`/`@Validated` at the integration point, or missing provider dependency.
7. **Data never reached DTO:** JSON deserialization/binding failed before validation.
8. **Annotation placed on the wrong level:** `@NotNull List<@Valid Child>` only forbids a null list, not null elements.

Specifically, do not conclude that if a child constraint does not run then "Hibernate Validator is broken"; trace each step of the object graph.

## 13. NullPointerException vs. Constraint Violation

Constructing a list with `List.of(null)` causes a Java error right at creation time, whereas creating a list with null using `Arrays.asList(...)` to test validation is valid. Similarly:

~~~java
Order order = new Order(null, null, null);
String city = order.shipping().city(); // NullPointerException
~~~

The snippet above is an **illustrative fragment**, with `Order` being the record from Section 7. `NullPointerException` happens because a method is called on a null reference; it is not a response from `Validator.validate(order)`. Validation **does not automatically fix** objects or make every reference safe; it detects violations when invoked. In MVC controllers, avoid accessing required fields before validation or before checking errors.

Another note: a custom `ConstraintValidator` that does not check for null may throw `NullPointerException` inside `isValid`. When writing custom validators, explicitly define whether null is allowed (commonly letting format constraints allow null and using `@NotNull` separately); do not rely on exception side effects to report data errors.

## 14. Testing Checklist for Null Scenarios

For the `Order` model (shipping required, stops list required, each Address in stops required, labels non-empty), the test suite should include:

| Input | Expected |
| --- | --- |
| `shipping == null` | Error on shipping due to `@NotNull` |
| `shipping.city == null` | Error at child's city after cascade |
| `shipping.city == " "` | Child `@NotBlank` error |
| `stops == null` | Container error due to `@NotNull` |
| `stops == []` | Valid for `@NotNull`, as empty is not forbidden |
| `stops == [null]` | Element error due to `@NotNull` on type argument |
| `stops == [Address("")]` | `child.city` error due to `@Valid` |
| `labels == null` | `@NotEmpty` error |
| `labels == []` | `@NotEmpty` error |
| `labels == [null]` | `@NotBlank` element error |
| `labels == [" "]` | `@NotBlank` element error |
| All valid objects | Zero violations |
| Root object passed directly to `Validator.validate(null)` | `IllegalArgumentException`, distinct from a null child property |

Additionally, test HTTP payloads:
- Missing fields vs. explicitly sent `null` when special deserialization policies exist.
- Wrong JSON types and unbindable errors.
- Multi-level nested DTOs as well as `Map` keys/values.
- Validation groups other than `Default`.
- HTTP status codes and error structures from `@ControllerAdvice` if the API has a specific contract.

Do not test by comparing iteration order of `Set<ConstraintViolation>`; sets do not guarantee order. In JSON responses as well, do not assert key/field error positions unless the API guarantees them.

## 15. Self-Practice Exercises

**Q1.** A field `@Valid Address address` has `address == null`. Does it create a violation?

**A:** No. `@Valid` skips null references. If an address is required, use `@NotNull @Valid Address address`.

**Q2.** `@NotNull List<@Valid Address> stops` has `stops=[null]`. Does it pass?

**A:** With the listed annotations, yes: the list is non-null, and the null element is skipped during cascading. Add `@NotNull` to the **type argument** to catch null elements.

**Q3.** `@NotEmpty List<@NotNull @Valid Address> stops` has an empty list. Which error occurs?

**A:** `@NotEmpty` violation on the list. There are no elements to evaluate `@NotNull` or cascade into.

**Q4.** `List<@NotNull Address>` contains `Address(null)`, and `Address.city` has `@NotBlank`. Is the city error caught?

**A:** No, unless `@Valid` is in the cascade chain. `@NotNull` on the element only checks whether the element object itself is null; `Address(null)` is non-null. Add `@Valid` to descend into `city`.

**Q5.** Distinguish three declarations: `@NotNull List<Address>`, `List<@NotNull Address>`, `@NotEmpty List<@NotNull Address>`.

**A:** The first forbids a null list; the second forbids null elements when the list exists; the third forbids a null/empty list **and** forbids null elements.

**Q6.** Why can't `List.of(null)` be used to test Bean Validation on null elements?

**A:** Java throws `NullPointerException` when creating an immutable list via `List.of`; Jakarta Validation hasn't even run yet. Use `Arrays.asList(null, ...)` or a list that permits nulls.

**Q7.** Why can a `Map<@NotBlank String, @Valid Address>` with a null key fail even when the value is non-null?

**A:** Because `@NotBlank` is on the **key** and rejects null. However, if the value is null, `@Valid` on the value will skip it; to forbid null values, add `@NotNull` on the value type argument.

**Q8.** A DTO has `@NotNull(groups=Create.class) @Valid Child child`. The endpoint selects only `Update.class`. Is `child == null` guaranteed to error?

**A:** No, if the two groups are independent: `@NotNull` belongs to `Create` and does not run in `Update`, while `@Valid` skips null. Select the right group or declare the constraint for `Update`.

**Q9.** The client sends JSON with `"stops":"abc"` instead of an array. Is this a null element error?

**A:** No. That is a deserialization/type mismatch issue before Jakarta Validation checks container elements.

**Q10.** Why can a parent object still receive an error on a child address even though the parent field itself has no `@NotNull` constraint?

**A:** Because `@Valid` cascades to **non-null** child objects. When the child exists, the child's constraints are checked and can fail; making a child optional does not mean that if it is provided, its internal data is allowed to be invalid.

## 16. Summary

- `@Valid` means **cascade validation when the object exists**. It **does not forbid null by itself**.
- `@NotNull @Valid Child` combines **requiring the child** and **validating the child's contents**.
- Null container, empty container, and null element are three **different** cases.
- `@NotNull List<@NotNull @Valid Child>`: forbids null list, forbids null elements, and cascades valid children. Add `@NotEmpty` on the list when empty lists must also be forbidden.
- `@Size(min=1)` treats a null list as valid; `@NotEmpty` does not. `@NotBlank` is suited for strings that must not be null/empty/blank.
- With `Map`, place constraints at the right **key** or **value** position.
- Distinguish Bean Validation errors from Java `NullPointerException`, JSON deserialization errors, and business validation errors.
- In Spring MVC, annotations are only evaluated when validation is triggered by `@Valid`/`@Validated` and an appropriate provider is present.
- Test null, empty, blank, group, and multi-level object cases separately; do not rely on violation order.

### Official Technical Sources

- Jakarta Validation 3.0 Specification – Object graph validation, null references are ignored: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation API – `@Valid`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valid
- Jakarta Validation API – `@NotNull`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/notnull
- Jakarta Validation API – `@NotEmpty`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/notempty
- Hibernate Validator 8 Reference Guide – Cascaded validation and container element constraints: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework – Validation and Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC – Validation of request data: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
