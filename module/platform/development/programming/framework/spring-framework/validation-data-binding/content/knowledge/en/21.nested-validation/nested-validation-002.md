# Cascaded Validation Through `List`, Arrays, and `Map` in Jakarta Bean Validation

## 1. Why Is Cascaded Validation Needed?

A request often contains more than simple fields like `name` or `quantity`. It can contain **lists of objects**, **arrays**, **Maps mapping keys to objects**, or **multi-level nested structures**. For instance, an order has a `List<OrderLine>`, where each line must have a valid product SKU and quantity.

If you place `@NotBlank` and `@Min` on `OrderLine` and only validate the parent object, the rules on the child objects **do not necessarily run automatically**. Jakarta Bean Validation uses the **`@Valid`** (`jakarta.validation.Valid`) annotation to mark relationships that must be traversed deeper (*cascaded validation*).

The goal of this lesson is to distinguish three different tasks:

1. Validating the **container itself** (is the list null/empty?): `@NotNull`, `@NotEmpty`, `@Size`.
2. Validating **element values** (is an element null, is a string blank...?): annotations directly on the **type argument** such as `List<@NotNull Item>` or `Map<@NotBlank String, ...>`.
3. Validating **constraints inside element objects**: `List<@Valid Item>`, arrays marked with `@Valid`, or `Map<K, @Valid Item>`.

These three purposes can work together, but they do not replace one another. `@Valid` by itself is **not** a constraint that checks `null`, length, size, or character validity.

Running example throughout the lesson:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class OrderLine {
    @NotBlank
    private String sku;

    @Min(1)
    private int quantity;

    // Constructor/getter/setter depending on data model and binding strategy
}
```

This is a model declaration snippet for explanation; a standalone runnable Java 17 program is in Section 6.

## 2. The `@Valid` Principle: Traversing from Parent to Child

Consider the parent object:

```java
import jakarta.validation.Valid;
import java.util.List;

public class Order {
    private List<@Valid OrderLine> lines;
}
```

When the Jakarta provider executes `validator.validate(order)`, it checks `Order`'s constraints, then follows `@Valid` relationships to each actual `OrderLine` and continues checking their `@NotBlank` and `@Min` constraints.

Mental flow:

```text
validator.validate(order)
          |
          v
      Order.lines
          |
          v
  List<@Valid OrderLine>
          |
          +--> OrderLine[0] --> sku / quantity
          |
          +--> OrderLine[1] --> sku / quantity
          |
          +--> ...
```

Key points to understand:

- **Every non-null element** extracted from a cascade-marked container is validated against the constraints of its runtime type (including applicable subclasses).
- `@Valid` can continue deeper through other objects containing `@Valid` relationships — this is **object graph** validation, not just single-level validation.
- **Null references are skipped during cascading.** If an element is required to exist, add `@NotNull`.
- The Jakarta provider must prevent infinite loops in graphs with reference cycles. This does not mean every check of the same object along different branches is merged into a single result.
- Spring MVC is not required to use this mechanism: it is part of the **Jakarta Validation provider**. Spring typically invokes it through an adapter when handling requests.

Since Jakarta Bean Validation 2.0, `@Valid` can be placed directly **on the type argument** of a container, such as `List<@Valid OrderLine>`. This is clearer and easier to read in new code.

## 3. Cascading Through `List` and `Iterable`

### 3.1. List of Objects

To validate constraints inside each line:

```java
private List<@Valid OrderLine> lines;
```

To reject a null/empty list, reject null elements, and validate element objects:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

@NotEmpty
private List<@NotNull @Valid OrderLine> lines;
```

Each annotation has its own position and meaning:

| Declaration | Condition Checked |
| --- | --- |
| `@NotNull List<OrderLine>` | Container is non-null, but may be empty |
| `@NotEmpty List<OrderLine>` | Container is non-null and has at least one element |
| `@Size(min=1,max=10) List<OrderLine>` | Container size is within range |
| `List<@NotNull OrderLine>` | Each element must be non-null |
| `List<@Valid OrderLine>` | Cascades into constraints on each non-null element object |
| `@NotEmpty List<@NotNull @Valid OrderLine>` | Combines all three requirements |

Input analysis:

- `lines = null`: `@NotEmpty` is violated; `@Valid` cannot descend into a null reference.
- `lines = []`: `@NotEmpty` is violated; no elements to cascade into.
- `lines = [null]`: container is **not empty**; `@NotNull` on the type argument is violated, while `@Valid` skips the null element.
- `lines = [OrderLine(sku="",quantity=0)]`: `@NotNull` on the element passes; cascades via `@Valid` and finds two constraint violations on `OrderLine`.
- `lines = [OrderLine(sku="A1",quantity=2)]`: all checks pass.

### 3.2. Element Constraints Do Not Need `@Valid` If Checking Only the Value Itself

Example:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

private List<@NotBlank @Email String> emails;
```

`@NotBlank` and `@Email` are **container-element constraints** placed directly on `String`. The provider handles them via a **value extractor** for the supported container. They **do not need `@Valid`** because they validate the `String` element itself rather than cascading into fields inside another bean.

Conversely, merely declaring:

```java
private List<OrderLine> lines;
```

will **not automatically descend** to check `@NotBlank` and `@Min` inside `OrderLine` when you only call `validator.validate(order)`.

### 3.3. `List`, `Set`, `Iterable`, and Error Locations

Commonly supported containers include `List`, `Set`, and `Iterable` implementations. A provider may record an **index** for elements in a `List`, whereas for a `Set` or `Iterable` without guaranteed ordering/indexing, the error path may not have a stable index.

Therefore, when designing APIs:

- Use `ConstraintViolation.getPropertyPath()` to read the path.
- Use `Path.Node.isInIterable()`, `getIndex()`, and `getKey()` to retrieve the corresponding metadata if needed.
- Do not assume `path.toString()` is identical across every provider or version.
- If the UI needs to preserve errors per stable row in a list being sorted/deleted, consider using a **business identifier** of the row alongside the path rather than treating the index as a permanent ID.

## 4. Cascading Through Arrays (`T[]`)

Object arrays are also supported in object graph validation. Clear and idiomatic declaration:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public class WarehouseBatch {

    @NotNull
    @Valid
    private OrderLine[] lines;
}
```

Placing `@Valid` on an object-array field allows the provider to descend into **each `OrderLine` in the array**. For example, with `lines = new OrderLine[] { new OrderLine("", 0) }`, validating `WarehouseBatch` lets the provider detect `sku` and `quantity` errors in the first element.

Distinctions:

- `@NotNull` on an **array** only requires the array itself to be non-null; it does not require every slot to contain an object.
- `@Valid` traverses into **non-null** element objects, but does not by itself report an error for a null slot.
- An empty array still satisfies `@NotNull`; to require elements, use `@NotEmpty` or `@Size(min = 1)`.
- For form/API data where null elements are disallowed, constrain elements using type-use syntax/provider capabilities or an additional tested rule; do not confuse `@NotNull` on the array field with `@NotNull` on each element.
- Primitive arrays like `int[]` do not hold bean objects to cascade into fields; element value constraints typically belong to another category rather than `@Valid` into a bean.

Regarding JSON payloads: when Jackson converts a JSON array into `OrderLine[]`, validation occurs **after deserialization**. If the JSON contains a structurally invalid element causing deserialization to fail, that is not necessarily a `ConstraintViolation`. If element objects are constructed successfully but violate `@NotBlank` or `@Min`, errors appear during Bean Validation.

**Should you choose arrays or `List`?** In new DTOs, `List<@NotNull @Valid OrderLine>` usually expresses element constraints more cleanly and works better with collections. Arrays remain valid when a Java/JSON contract requires them or when working with legacy APIs. Choose based on data types and contracts, not a misconception that arrays cannot cascade.

## 5. Cascading Through `Map`: Validating Keys and Values

`Map<K,V>` has two distinct type argument positions, so annotations must be placed in the right spot.

### 5.1. Validating Map Values

```java
import jakarta.validation.Valid;
import java.util.Map;

private Map<String, @Valid OrderLine> linesByCode;
```

When validating the parent bean, the provider iterates through **the map values** and checks constraints inside each `OrderLine`. A map with key `"paper"` and value `OrderLine("", 0)` will produce violations for that value object.

To require values to be non-null and valid beans:

```java
private Map<String, @NotNull @Valid OrderLine> linesByCode;
```

With a map containing `"paper" -> null`, `@Valid` skips null; `@NotNull` on the value is what enforces presence.

### 5.2. Validating Map Keys

Jakarta Validation also provides a **built-in value extractor for Map keys**, so constraints or `@Valid` can be placed on the **key type**:

```java
import jakarta.validation.constraints.NotBlank;
import java.util.Map;

private Map<@NotBlank String, @Valid OrderLine> linesByCode;
```

When a key is `" "` or `""`, `@NotBlank` on the key detects a violation. When a value has a constraint violation, `@Valid` on the value detects it separately.

If the key is a bean with fields:

```java
private Map<@Valid ProductKey, @Valid OrderLine> linesByKey;
```

then both the **key object** and the **value object** are cascaded; `ProductKey` must define its own constraints. With Java Maps using mutable keys, be very careful if hash/equality depends on fields that might change after insertion into the map; this is a collection design issue not solved by Bean Validation.

### 5.3. Comparing Configurations

| Declaration | Checks |
| --- | --- |
| `@NotEmpty Map<String,OrderLine>` | Map is non-null and non-empty; does not automatically cascade values |
| `Map<@NotBlank String,OrderLine>` | String value of each key |
| `Map<String,@NotNull OrderLine>` | Each value is non-null |
| `Map<String,@Valid OrderLine>` | Bean constraints of each value |
| `Map<@Valid ProductKey,@Valid OrderLine>` | Constraints on both key and value beans |
| `@NotEmpty Map<@NotBlank String,@NotNull @Valid OrderLine>` | Non-empty map, non-blank keys, present and valid values |

**Compatibility detail with legacy code:** prior to Bean Validation 2.0, you might see `@Valid` placed on the **Map field**:

```java
@Valid
private Map<String, OrderLine> linesByCode;
```

This legacy style cascades into Map **values**, not automatically into keys. For new code, place `@Valid` on the type arguments (`Map<@Valid Key, @Valid Value>`) to clearly express traversal direction. Do not place `@Valid` on both the container and its own type argument thinking "more is better": the specification advises avoiding duplicate cascade configurations.

### 5.4. Reading the Path of a Map Violation

Suppose the key is `"paper"` and the value is `OrderLine(quantity=0)`. The error path may be represented by the provider similarly to:

```text
linesByCode[paper].quantity
```

For constraints applied to the **key itself** such as `@NotBlank`, there may be a container element node named `<map key>`; for constraints on the **value itself**, there may be a `<map value>` node. The exact `toString()` representation of specific nodes varies by provider, so do not parse this string as a strict protocol format.

The specification provides structured fields on path nodes:

```java
for (jakarta.validation.Path.Node node : violation.getPropertyPath()) {
    if (node.isInIterable()) {
        Integer index = node.getIndex(); // Populated for List/array when available
        Object key = node.getKey();      // Populated for Map when available
    }
}
```

This is an illustrative snippet inside a loop over `ConstraintViolation<?> violation`; it is not a standalone Java program. `index` or `key` may be null depending on the node and container type.

## 6. Standalone Java 17 Example: List, Array, Map, and Map Nested with List

The example uses Hibernate Validator 8 (a Jakarta Validation provider). It deliberately creates distinct errors across four structures to observe **cascade scope**. To keep stdout independent of `Set<ConstraintViolation<?>>` iteration order, the program prints only the sorted names of violated constraint annotations.

Create a Gradle project:

```text
cascade-containers/
├── settings.gradle
├── build.gradle
└── src/main/java/ContainerCascadeDemo.java
```

**`settings.gradle`**:

```groovy
rootProject.name = 'cascade-containers'
```

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.hibernate.validator:hibernate-validator:8.0.6.Final'
    implementation 'org.glassfish.expressly:expressly:5.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ContainerCascadeDemo'
}
```

In Spring Boot 3+, you can use `spring-boot-starter-validation` and let the Boot BOM manage versions instead of pinning the provider as in this standalone project. `expressly` provides a Jakarta Expression Language implementation for message interpolation.

**`src/main/java/ContainerCascadeDemo.java`**:

```java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public class ContainerCascadeDemo {

    public static final class Item {
        @NotBlank
        private final String code;

        @Min(1)
        private final int quantity;

        public Item(String code, int quantity) {
            this.code = code;
            this.quantity = quantity;
        }
    }

    public static final class ListCase {
        @NotEmpty
        private final List<@NotNull @Valid Item> items;

        public ListCase(List<Item> items) {
            this.items = items;
        }
    }

    public static final class ArrayCase {
        @NotNull
        @Valid
        private final Item[] items;

        public ArrayCase(Item[] items) {
            this.items = items;
        }
    }

    public static final class MapCase {
        @NotEmpty
        private final Map<@NotBlank String, @NotNull @Valid Item> items;

        public MapCase(Map<String, Item> items) {
            this.items = items;
        }
    }

    public static final class NestedCase {
        private final Map<String, List<@Valid Item>> groups;

        public NestedCase(Map<String, List<Item>> groups) {
            this.groups = groups;
        }
    }

    private static String violationNames(
            Set<? extends ConstraintViolation<?>> violations) {
        return violations.stream()
                .map(v -> v.getConstraintDescriptor()
                        .getAnnotation()
                        .annotationType()
                        .getSimpleName())
                .sorted()
                .collect(Collectors.joining(","));
    }

    private static void show(String label, Object bean, Validator validator) {
        Set<ConstraintViolation<Object>> violations =
                validator.validate(bean);

        System.out.printf("%s: %d [%s]%n",
                label, violations.size(), violationNames(violations));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            // One element has blank code, one element is null.
            show("List",
                    new ListCase(Arrays.asList(new Item(" ", 2), null)),
                    validator);

            // Array: no code error, but quantity=0 violates @Min.
            show("Array",
                    new ArrayCase(new Item[]{new Item("A1", 0)}),
                    validator);

            // Map: blank key, one value with blank code, one null value.
            Map<String, Item> values = new LinkedHashMap<>();
            values.put(" ", new Item(" ", 2));
            values.put("missing", null);
            show("Map", new MapCase(values), validator);

            // Map nested with List: cascades through both container layers.
            Map<String, List<Item>> groups = new LinkedHashMap<>();
            groups.put("holiday", List.of(new Item(" ", 2)));
            show("Nested", new NestedCase(groups), validator);
        }
    }
}
```

Run in the project directory with Java 17+:

```bash
gradle run --quiet
```

If using Gradle Wrapper: Linux/macOS `./gradlew run --quiet`; Windows `gradlew.bat run --quiet`.

**Expected standard output**:

```text
List: 2 [NotBlank,NotNull]
Array: 1 [Min]
Map: 3 [NotBlank,NotBlank,NotNull]
Nested: 1 [NotBlank]
```

Result analysis:

1. **List:** `ListCase.items` is non-empty, so `@NotEmpty` passes. `Item(" ", 2)` triggers `@NotBlank` via `@Valid`; the null slot triggers `@NotNull` on the type argument, even though `@Valid` does not enter null.
2. **Array:** `Item[]` is non-null; `@Valid` on the array field descends into the element, and `quantity=0` violates `@Min(1)`.
3. **Map:** key `" "` violates `@NotBlank` on the key type. The value at that key is `Item(" ",2)` and violates `@NotBlank` on field `code`. The value at key `"missing"` is null, violating `@NotNull` on the value type. Total **3** violations.
4. **Nested:** `Map<String, List<@Valid Item>>` goes through the Map value extractor and then the List extractor to reach `Item`; blank code violates `@NotBlank`.

`ValidatorFactory` is closed via try-with-resources; this is a standalone Java program with no Spring `ApplicationContext`. The provider may write startup logs to stderr depending on configuration; the above describes the **program's standard output**.

To inspect individual error paths rather than just constraint names, replace the body of `show` with iteration:

```java
violations.stream()
        .map(v -> v.getPropertyPath() + " -> " + v.getMessage())
        .sorted()
        .forEach(System.out::println);
```

This is a replacement snippet **inside** the existing `show` method, not a standalone runnable file. Path output includes indices/keys, though the exact path string depends on the provider and constraint position.

## 7. Multi-Level Cascading: `Map<String, List<@Valid Item>>`

In large systems, data can contain multiple container layers:

```java
private Map<String, List<@Valid OrderLine>> linesByWarehouse;
```

How to read from left to right:

1. `linesByWarehouse` is a Map with `String` keys.
2. Each value is a `List<OrderLine>`.
3. `@Valid` sits on the List's type argument, so each `OrderLine` is cascaded.
4. If an `OrderLine` object has `@Valid` pointing to another object, validation continues deeper.

To constrain the containers as well, add constraints at each level:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

@NotEmpty
private Map<
        @NotBlank String,
        @NotEmpty List<@NotNull @Valid OrderLine>
        > linesByWarehouse;
```

The declaration above carries these meanings:

- The Map must have at least one entry.
- Keys must not be blank.
- Each value List must be non-null/non-empty (`@NotEmpty`).
- Each List element must be non-null (`@NotNull`) and cascaded (`@Valid`).

Constraints placed directly on type arguments such as `@NotEmpty List<...>` work via **value extractors**. The Jakarta specification defines value extractors for common Java containers; Hibernate Validator 8 adds support for several specialized types. For a custom container, you may need to register an appropriate `ValueExtractor`. If no valid extractor exists or ambiguity arises, the provider may throw `ConstraintDeclarationException`/`ValidationException` at runtime; do not assume every arbitrary generic wrapper cascades automatically.

### `Map` Containing Objects with Nested `List`

Another scenario:

```java
public class Shipment {
    @NotEmpty
    private Map<String, @Valid Warehouse> warehouses;
}

public class Warehouse {
    @NotEmpty
    private List<@Valid OrderLine> lines;
}
```

These are illustrative type/field snippets requiring imports, constructors, and other members before running. When validating `Shipment`, the provider enters each `Warehouse` via `@Valid`, then enters each `OrderLine` via the next `@Valid`. If `@Valid` is missing at the `Warehouse` level, cascading stops there even if lower levels declare full constraints.

The specification requires providers to avoid infinite loops in graphs with bidirectional relationships, such as `OrderLine` referencing back to `Shipment`. Even so, design validation relationships cleanly to avoid unnecessary checks or confusing duplicate errors.

## 8. Groups and Group Conversion During Cascading

Jakarta Validation has **groups** to select constraint sets. By default, `validator.validate(object)` uses the `jakarta.validation.groups.Default` group.

If `OrderLine` has a constraint belonging only to `PublishChecks` and the validator is running the `Default` group, that constraint will not run automatically just because `@Valid` is on the parent. Cascading proceeds with the active validation group unless **group conversion** is configured:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

private List<
        @Valid
        @ConvertGroup(from = Default.class, to = PublishChecks.class)
        OrderLine
        > lines;
```

This is an **advanced declaration example**, assuming `PublishChecks` is already defined, not a standalone program. `@ConvertGroup` on the cascade relationship converts the `Default` group to `PublishChecks` when entering each element. Only use this when creation/editing/publishing steps genuinely have different rules; overly complex group configurations can accidentally skip expected checks.

Group-related bugs often stem from constraints being placed only in `Default` or a custom group while the validation call path passes a different group. When you see "`@Valid` is present but no errors appear," check **groups** in addition to annotation placement and the provider.

## 9. Integrating with Spring MVC/Spring Boot

In Spring Framework 6+/Spring Boot 3+, use Jakarta annotations (`jakarta.validation.Valid`, `jakarta.validation.constraints.*`). Spring Web MVC can use the Jakarta adapter to run validation when binding a request into a command object.

Java 17 DTO example using `record`:

```java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record LineInput(
        @NotBlank String sku,
        @Min(1) int quantity
) {}

public record OrderInput(
        @NotEmpty List<@NotNull @Valid LineInput> lines
) {}
```

These are **illustrative type definitions**; in real Java code, place each public record in a file of the same name or omit `public` to share a package. With `record`, Jackson/Spring Boot needs record support configured for the version in use (Spring Boot 3+ typically includes this).

Illustrative controller:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @PostMapping("/orders")
    public ResponseEntity<String> create(@Valid @RequestBody OrderInput input) {
        return ResponseEntity.ok("accepted");
    }
}
```

The controller requires `@Valid` on the **parent object `OrderInput`**; from there, the Jakarta provider sees `List<@NotNull @Valid LineInput>` and descends into each element. If the request sends:

```json
{
  "lines": [
    {"sku": "A1", "quantity": 2},
    {"sku": "", "quantity": 0}
  ]
}
```

after successful deserialization, the second element violates both `@NotBlank` and `@Min`. With default configuration, Spring MVC typically returns HTTP 400 for object validation errors if not handled specially by a controller/exception handler; the commonly encountered exception is `MethodArgumentNotValidException` for command object validation.

Important point about **direct request containers**: a controller signature like `@Valid @RequestBody List<LineInput> lines` has different validation semantics from a command object `OrderInput` annotated with `@Valid`. According to Spring MVC documentation, automatic `@RequestBody` object validation focuses on **command objects, not direct Map/Collection containers**; method validation has its own rules. For predictable and testable behavior, you can use a wrapper DTO like `OrderInput`, or configure specific method validation for endpoints accepting containers directly.

If you want to handle errors directly in the controller, with an eligible model you can place `BindingResult` **immediately after** the `@Valid` parameter:

```java
@PostMapping("/orders")
public ResponseEntity<?> create(
        @Valid @RequestBody OrderInput input,
        org.springframework.validation.BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(errors.getFieldErrors()
                .stream()
                .map(e -> e.getField() + ": " + e.getCode())
                .toList());
    }
    return ResponseEntity.ok("accepted");
}
```

This is an **illustrative method snippet** requiring `@PostMapping`, `@RequestBody`, `@Valid`, `ResponseEntity`, and the corresponding classes/DTOs. Do not return raw rejected values or private data in error responses.

Spring MVC also distinguishes **binding/deserialization errors**, **object validation**, and **method validation** (which may involve `HandlerMethodValidationException` in modern versions). Unparseable JSON can be rejected **before** constraints on `List`/`Map` are checked. Test each branch if the API needs consistent error reporting.

## 10. Testing and Common Mistakes

### Minimum Test Matrix

| Input | Relevant Declaration | Expectation |
| --- | --- | --- |
| `null` on list field | `@NotEmpty List<...>` | Container violation |
| `[]` | `@NotEmpty List<...>` | Container violation |
| `[null]` | `List<@NotNull @Valid Item>` | Element `@NotNull` violation |
| `[Item(code="",quantity=0)]` | `List<@Valid Item>` | Violations of constraints inside `Item` |
| `new Item[]{Item("A",0)}` | `@Valid Item[]` | `@Min` violation inside element |
| `Map` with key `""` | `Map<@NotBlank String,...>` | Key violation |
| `Map` with value `null` | `Map<K,@NotNull @Valid Item>` | Value `@NotNull` violation |
| `Map` with value `Item("",2)` | `Map<K,@Valid Item>` | `@NotBlank` violation on value bean |
| `Map<K,List<Item>>` missing all `@Valid` | No cascade annotation on item | Does not automatically run constraints inside `Item` |
| `Map<K,List<@Valid Item>>` | Cascade on nested type argument | Checks each `Item` in each `List` |
| Parent → child → parent cycle | `@Valid` on relationships | Provider must prevent infinite loops |

When testing, verify **error count, constraint types, and field paths**, and distinguish **container** errors from **element** errors. Do not rely on `Set<ConstraintViolation<?>>` iteration order. For Spring MVC, include HTTP tests sending valid requests, requests with invalid elements, and syntactically invalid JSON requests.

### Mistakes to Avoid

1. **Writing only `List<Item>` and expecting `Item` to be validated.** You need `@Valid` at the right relationship.
2. **Using `@Valid` to forbid null.** Cascading skips null; add `@NotNull` in the proper spot.
3. **Thinking `@NotEmpty` validates each child object.** It only checks whether the container is non-null and non-empty.
4. **Putting `@NotNull` on `List` and thinking every element must be non-null.** Use `List<@NotNull Item>` if you want to constrain elements.
5. **Conflating Map keys and Map values.** `Map<@NotBlank String, @Valid Item>` has two rules on opposite sides.
6. **Using legacy `@Valid Map<K,V>` and expecting keys to cascade too.** Place `@Valid` on the key type when the key is a bean needing validation.
7. **Missing `@Valid` on one link in a multi-level bean chain.** Cascading can stop at that level.
8. **Placing `@Valid` on both the container and element unintentionally.** This can create duplicate configuration; prefer explicit type arguments for generic containers.
9. **Treating `getPropertyPath().toString()` as a fixed protocol format.** Inspect nodes and `index/key` metadata, and test against the actual provider.
10. **Confusing Spring MVC validation invocation with plain-Java Jakarta API.** You need the proper Jakarta provider and Spring integration; JSON conversion runs before validation.
11. **Ignoring groups.** Constraints in another group may not run even when `@Valid` is on the cascade relationship.
12. **Assuming every generic container is automatically supported.** Custom containers may require a `ValueExtractor`.
13. **Exposing raw invalid data to clients/logs.** Violations contain paths, messages, and sometimes sensitive invalid values.
14. **Skipping tests for null elements and empty containers.** These are the most critical boundaries of `@Valid` and `@NotNull`/`@NotEmpty`.

### Knowledge Self-Check

1. Why doesn't `@NotEmpty List<@Valid Item>` block `[null]`? **The list has one element so it is not empty; `@Valid` skips null elements.** To block it, add `@NotNull` on the type argument.
2. To validate key objects in a Map, where should `@Valid` be placed? **On the key type argument**, e.g., `Map<@Valid ProductKey, ...>`.
3. Why doesn't `List<@NotBlank String>` need `@Valid`? **The constraint applies directly to the `String` element**, without descending into another bean object.
4. With `Map<String,List<@Valid Item>>`, how many container layers does the provider traverse to reach `Item`? **Map value then List element**; it uses the corresponding value extractors.
5. If `@Valid` is present but a specific constraint does not run, what should you check? **Annotation type and placement, provider, null values, validation groups, validation invocation path, and intermediate cascade edges.**
6. If a controller directly accepts `List<Item>` from JSON, can you assume the same behavior as a wrapper DTO with `@Valid`? **You should not assume so**; check Spring MVC's validation rules and the actual endpoint configuration.

## 11. References

- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): Object graph validation, container-element constraints, and value extractors sections.
- [Hibernate Validator 8.0 — Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/): validating List/Map, cascaded validation of containers, nested container elements, property paths.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta provider and Spring `LocalValidatorFactoryBean`.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): object validation, `@Valid`/`@Validated`, method validation, and MVC errors.
- [Jakarta Validation 3.0 — `@Valid` Javadoc](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Valid.html): how to mark cascade relationships.

**Key takeaway:** to validate constraints on objects **inside** a List, array, or Map, declare `@Valid` in the right place. To validate the **container or element values**, use `@NotEmpty`, `@NotNull`, `@Size`, `@NotBlank`, etc. at the appropriate level. For Maps, consider **keys and values** independently and remember to handle nested containers.
