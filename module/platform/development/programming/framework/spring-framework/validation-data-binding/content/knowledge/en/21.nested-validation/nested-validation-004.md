# Constraints on Map Keys and Values

> **Context:** Jakarta Bean Validation in Java 17+ and Spring Framework/Spring Boot 3.x, under the **nested validation** topic. The focus is placing constraints on individual **keys** and **values** of `Map<K, V>`, distinct from constraints applied to the Map itself, combining `@Valid` to validate inner beans and reading error paths accurately.

## 1. Three Different Validation Levels in a Map

A `Map<K, V>` has at least three levels that can be validated:

1. **The Map itself:** whether the `Map` variable is null, how many entries it has, etc.
2. **Each key K:** whether a key is null, blank, malformed, or an invalid object.
3. **Each value V:** whether a value is null, too small, malformed; if the value is a bean or collection, whether deeper validation is needed.

These three levels **do not automatically imply one another**.

```text
OrderRequest
   │
   └── items : Map<K, V>                       ← constraint on the entire Map
          │
          ├── key "PEN-01"                     ← constraint on type argument K
          └── value Item(name, quantity)      ← constraint on type argument V
                    │
                    ├── name                   ← constraint inside Item, requires cascade
                    └── quantity               ← constraint inside Item, requires cascade
```

Complete declaration example:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.Map;

public class CartRequest {
    @NotEmpty
    private Map<@NotBlank String, @NotNull @Valid Item> items;
}
```

This is an **illustrative code snippet**; to compile, you also need to define `Item` and the rest of the DTO. Meaning of each position:

- `@NotEmpty` **placed on field `items`**: the Map must be non-null and contain at least one entry.
- `@NotBlank` **placed before `String` in the first type argument**: each key must be a string with content (non-null, non-empty, not whitespace-only).
- `@NotNull` **placed before `Item` in the second type argument**: each value must not be null.
- `@Valid` **placed on the same `Item` type argument**: when a value is non-null, continue validating constraints inside each `Item` object.

From Bean Validation **2.0** onward (moving to the `jakarta.validation` namespace in Jakarta Validation 3.x), placing annotations on container **type arguments** like `Map<@NotBlank String, @Valid Item>` is the standard mechanism for validating individual container elements (*container element constraints*).

## 2. Syntax: Annotate the Right Position

### 2.1. Constraints on the Entire Map

```java
@NotNull
Map<String, Item> items;

@NotEmpty
Map<String, Item> requiredItems;
```

- `@NotNull` only forbids `items == null`; `Map.of()` (empty) is still valid.
- `@NotEmpty` forbids both null and an empty Map; an entry with an invalid key/value **still counts the Map as non-empty**.
- `@Size(min = 1, max = 20)` limits the number of entries; per specification `@Size` allows null, so if the Map must be present, combine it with `@NotNull` or use `@NotEmpty` with `@Size(max=20)`.
- `@NotBlank` **does not support** `Map`: it is for `CharSequence`, not containers.

### 2.2. Constraints on Keys (K)

```java
Map<@NotBlank String, Item> itemsBySku;

Map<@NotNull @Pattern(regexp = "[A-Z0-9-]+") String, Item>
        itemsByCode;
```

In the **first** type argument of `Map<K, V>`, `@NotBlank` rejects null/empty/whitespace-only keys; `@Pattern` checks string format but **allows null by itself**, so you can combine `@NotNull` if keys must be non-null. When keys are DTOs/beans, `@Valid` can be placed on type argument K to cascade into key beans, provided a supporting value extractor is available.

### 2.3. Constraints on Values (V)

```java
Map<String, @NotNull Integer> scores;
Map<String, @Positive Integer> stockLevels;
Map<String, @NotBlank String> displayLabels;
Map<String, @NotNull @Valid Item> items;
```

In the **second** type argument:

- `@NotNull` checks that the value is non-null.
- `@Positive` checks that a number is positive; a null value **passes `@Positive` alone**, so add `@NotNull` if null is unacceptable.
- `@NotBlank` is for values that are `CharSequence`.
- `@Valid` performs **cascaded validation** on the bean inside the value; if `Item.name` has `@NotBlank` but `@Valid` is missing on the value, constraints inside `Item` will not run automatically just because the Map has other constraints.

**Do not write** `@NotNull Map<String, Item> items` and assume it forbids all null values. An outer `@NotNull` only checks the Map itself, not individual entries.

### 2.4. Comparison Table of Declaration Positions

| Declaration | What Is Checked | What Is Not Checked by Default |
| --- | --- | --- |
| `@NotNull Map<K,V> map` | Map reference itself is non-null | Entry count, keys, values |
| `@NotEmpty Map<K,V> map` | Map is non-null, has ≥1 entry | Key/value contents |
| `Map<@NotBlank String,V>` | Each key is non-blank text | Empty Map and values |
| `Map<K,@NotNull V>` | Each value is non-null | Empty Map and keys |
| `Map<K,@Valid V>` | Constraints inside value bean | Null values and empty Map, unless other constraints are combined |
| `Map<@Valid KeyBean,@Valid ValueBean>` | Cascades into both key and value objects | Whether Map must have entries |
| `@NotEmpty Map<@NotBlank String,@NotNull @Valid V>` | Non-empty Map, valid keys, non-null and deeply valid values | Business rules not expressed by declared constraints |

## 3. Under the Hood: Map ValueExtractors

Bean Validation cannot inspect individual keys/values using only Map-level constraints. For *container element constraints*, the validation provider uses the `ValueExtractor` mechanism:

```text
Validator.validate(request)
        │
        ▼
Read constraints on field items : Map<K,V>
        │
        ├── @NotEmpty: checks the Map itself
        │
        ├── MapKeyExtractor   → key 1, key 2, ...   → constraint on K
        │
        └── MapValueExtractor → val 1, val 2, ...   → constraint on V
                                                          │
                                                          └── @Valid → child bean
```

Per Jakarta Validation, compliant providers include **built-in value extractors** for keys and values of `java.util.Map`, so you do not need to write extractors when using standard `Map` types. The key extractor uses a node name like `<map key>` and the value extractor uses `<map value>`. When building violation paths, the framework can also record the entry key on the corresponding node.

Each constraint on type argument K/V is matched by the provider to the appropriate extractor. Using a **custom container** without a matching extractor, or registering conflicting extractors, can cause a configuration error like `ConstraintDeclarationException` instead of a data violation. Only write a custom `ValueExtractor` when you genuinely need to support containers outside standard types and understand extractor resolution rules.

**Note:** Built-in Map key/value extraction does not turn a Map into a database constraint or a tool for checking whole-entry-set invariants. For example, uniqueness of **values** across entries, relationships between keys and values, or requiring a specific set of keys usually requires a custom constraint or separate business logic.

## 4. Runnable Java 17+ Example: Map, Keys, Values, and Child Beans

The example uses Jakarta Bean Validation with Hibernate Validator (brought onto the classpath by Spring Boot 3.3.5's starter). The program needs no web server and **does not create a Spring ApplicationContext**.

Structure:

```text
map-validation-demo/
├── pom.xml
└── src/main/java/demo/MapValidationDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>map-validation-demo</artifactId>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/MapValidationDemo.java`:**

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class MapValidationDemo {

    // Child bean: validated deeply if @Valid is on the value type.
    static final class Item {
        @NotBlank
        private final String name;

        @Positive
        private final int quantity;

        Item(String name, int quantity) {
            this.name = name;
            this.quantity = quantity;
        }
    }

    static final class Catalog {
        @NotEmpty
        private final Map<@NotBlank String, @NotNull @Valid Item> items;

        Catalog(Map<String, Item> items) {
            this.items = items;
        }
    }

    // Nested container: Map value is List<String>.
    static final class TagGroups {
        @NotEmpty
        private final Map<
                @NotBlank String,
                @NotEmpty List<@NotBlank String>> tags;

        TagGroups(Map<String, List<String>> tags) {
            this.tags = tags;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            show(validator, "catalog.nullMap", new Catalog(null));
            show(validator, "catalog.emptyMap",
                    new Catalog(Map.of()));
            show(validator, "catalog.invalidKey",
                    new Catalog(Map.of(" ", new Item("Pen", 2))));

            // Map.of() forbids null; use LinkedHashMap to test null value.
            Map<String, Item> withNullValue = new LinkedHashMap<>();
            withNullValue.put("PEN-01", null);
            show(validator, "catalog.nullValue",
                    new Catalog(withNullValue));

            show(validator, "catalog.invalidItem",
                    new Catalog(Map.of("PEN-01", new Item(" ", 0))));
            show(validator, "catalog.valid",
                    new Catalog(Map.of("PEN-01", new Item("Pen", 2))));

            show(validator, "tags.emptyList",
                    new TagGroups(Map.of("color", List.of())));
            show(validator, "tags.blankElement",
                    new TagGroups(Map.of("color", List.of(" "))));
            show(validator, "tags.valid",
                    new TagGroups(Map.of("color", List.of("red"))));
        }
    }

    private static void show(Validator validator,
                             String label, Object bean) {
        // Print constraint names instead of message/path: output does not
        // depend on locale, Map order, or provider path rendering.
        List<String> failures = validator.validate(bean).stream()
                .map(v -> v.getConstraintDescriptor()
                        .getAnnotation()
                        .annotationType()
                        .getSimpleName())
                .sorted()
                .toList();

        System.out.println(label + " -> " + failures);
    }
}
```

Run in the directory containing `pom.xml` (requires Maven and Java 17+):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.MapValidationDemo
```

**Program output** (excluding external Maven/provider logs):

```text
catalog.nullMap -> [NotEmpty]
catalog.emptyMap -> [NotEmpty]
catalog.invalidKey -> [NotBlank]
catalog.nullValue -> [NotNull]
catalog.invalidItem -> [NotBlank, Positive]
catalog.valid -> []
tags.emptyList -> [NotEmpty]
tags.blankElement -> [NotBlank]
tags.valid -> []
```

Explanation of each case:

1. `catalog.nullMap`: null Map → only `@NotEmpty` on the Map field reports an error; there are no entries to check keys/values.
2. `catalog.emptyMap`: real but empty Map → still fails `@NotEmpty`; no keys/values to check.
3. `catalog.invalidKey`: Map has one entry so `@NotEmpty` passes; key `" "` violates `@NotBlank`; value has valid data.
4. `catalog.nullValue`: Map contains a valid key with a null value. `@NotNull` on V reports an error; `@Valid` skips cascading into null.
5. `catalog.invalidItem`: valid key, non-null value, but `Item` bean contains `name = " "` and `quantity = 0`; via `@Valid` it produces two errors, `@NotBlank` and `@Positive`.
6. `catalog.valid`: all three levels are valid.
7. `tags.emptyList`: Map is non-empty and key is valid, but the value List is empty so `@NotEmpty` on type argument V reports an error.
8. `tags.blankElement`: value List has one element so it passes `@NotEmpty`, but element `" "` violates `@NotBlank`.
9. `tags.valid`: valid key, List has elements, and each element is valid.

The output is produced by **sorting constraint type names**, without printing messages or paths containing keys: this keeps the example consistent across different providers/locales. When debugging a real application, you still need `ConstraintViolation#getPropertyPath()` to pinpoint exact errors.

### 4.1. Testing a Null Key as Well

Java's `Map.of(...)` does not allow creating null keys or values: Java throws `NullPointerException` **before** Bean Validation is invoked. If you need to test the null-key case, use a Map implementation that permits null such as `HashMap`/`LinkedHashMap`:

```java
Map<String, Item> withNullKey = new LinkedHashMap<>();
withNullKey.put(null, new Item("Pen", 2));
show(validator, "catalog.nullKey", new Catalog(withNullKey));
```

This is an illustrative snippet **placed inside `main` while `validator` is in scope**. The corresponding program output will be:

```text
catalog.nullKey -> [NotBlank]
```

Because `@NotBlank` on the key rejects null. Which Map implementation is used and whether null keys are allowed is a property of the Map implementation; **not** a limitation imposed by Bean Validation itself.

## 5. Maps with Bean Keys: Cascading into Keys and Values

Since Bean Validation 2.0+, `@Valid` can be placed on **both type arguments**:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.Map;

public class Index {
    private Map<
            @NotNull @Valid CategoryKey,
            @NotNull @Valid ProductInfo> entries;
}
```

This is a structural example; `CategoryKey` and `ProductInfo` must be defined in a real project. Meaning:

- `@Valid` on K descends into constraints of the `CategoryKey` object.
- `@Valid` on V descends into constraints of the `ProductInfo` object.
- `@NotNull` on K/V blocks null keys/values; `@Valid` by itself does not make null invalid.
- Constraints are applied when an `Index` object passes through Bean Validation and the provider has the corresponding extractors.

**Important note on using objects as Map keys:** Java Maps rely on `equals()`/`hashCode()` to manage keys; mutable keys can break lookup after insertion into a Map. Bean Validation **does not** fix this issue. If a key is an object, design an immutable value object with equality/hash rules aligned with business logic.

### 5.1. Distinguishing `@Valid Map<K,V>` and `Map<K,@Valid V>`

In Jakarta Validation, the traditional usage:

```java
@Valid
private Map<String, ProductInfo> products;
```

typically **cascades into the Map's values**, rather than checking constraints on each key. Since Bean Validation 2.0, the more explicit syntax is:

```java
private Map<String, @Valid ProductInfo> products;
```

and if keys are also needed:

```java
private Map<@Valid CategoryKey, @Valid ProductInfo> products;
```

Do not put `@Valid` **both on the container and on the corresponding type argument** just "to be sure": the specification advises against this because elements may be validated repeatedly. Choose the position intentionally; in new code, prefer annotating the exact type argument that needs cascading.

### 5.2. `@Valid` Is Not a Non-Null Constraint

Compare:

```java
Map<String, @Valid ProductInfo> a;
Map<String, @NotNull @Valid ProductInfo> b;
```

If a value is null (and the Map implementation allows it), `a` **reports no error from `@Valid`**; `b` violates `@NotNull`. If the value is non-null but has an invalid inner field, both can detect `ProductInfo`'s constraints. Do not use `@Valid` in place of `@NotNull`/`@NotEmpty`.

## 6. Maps Nesting Collections or Other Maps

When a Map value is a container, annotations must be placed **at the right level**:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;

public class BatchRequest {
    @NotEmpty
    private Map<
            @NotBlank String,
            @NotEmpty List<@NotNull @Valid LineItem>> linesByStore;
}
```

This is an illustrative snippet, requiring a `LineItem` class with constraints and the rest of the DTO. The rules are:

- The Map must be non-null and have at least one entry.
- Each store-name key must be non-blank text.
- Each value List must be non-null and have at least one element (due to `@NotEmpty` on the List).
- Each `LineItem` element must be non-null (due to `@NotNull` on the List element).
- Each non-null `LineItem` is deeply validated (due to `@Valid` on the List element).

Adding another Map level:

```java
Map<
    @NotBlank String,
    @NotEmpty Map<@NotBlank String, @Positive Integer>>
    inventoryByWarehouse;
```

This example validates outer Map keys (warehouse ID), non-empty inner Maps, non-blank inner Map keys (SKU), and positive quantities in the inner Map. **`@Positive` allows null values** per specification; if non-null is required, add `@NotNull` to the `Integer` type.

With multi-level nested containers, the provider uses a chain of matching extractors to descend to each element. You cannot just put `@Valid` on the outermost object and expect constraints at every level to be inferred automatically if they are not declared on the type arguments.

## 7. Reading `ConstraintViolation`: Key Errors vs. Value Errors

When using Maps, printing only `violation.getMessage()` is often insufficient. Useful details include:

- `getPropertyPath()`: path from the root bean to the field, Map entry, and potentially to a child bean field.
- `getConstraintDescriptor().getAnnotation().annotationType()`: which constraint was violated.
- `getInvalidValue()`: which value was deemed invalid (be careful with sensitive data).
- `Path.Node`: node metadata, `getKind()`, `isInIterable()`, `getKey()`/`getIndex()`, `getContainerClass()`, and `getTypeArgumentIndex()` when applicable.

For a Map with keys like `"PEN-01"`, error paths are rendered by the provider roughly as:

```text
items[PEN-01].<map key>
items[PEN-01].<map value>
items[PEN-01].name
items[PEN-01].quantity
```

**This is an illustrative reading guide, not guaranteed stdout for every provider/constraint type.** Node segments, bracket notation, and `Path.toString()` formatting should be verified against your specific provider. Crucially, errors **on the key** and **on the value** are not at the same location; when a stable API error schema is needed, translate from `Path.Node` into an application error structure rather than copying raw `toString()` strings as a long-term contract.

Example extracting metadata to distinguish them:

```java
for (var violation : validator.validate(request)) {
    String constraint = violation.getConstraintDescriptor()
            .getAnnotation()
            .annotationType()
            .getSimpleName();

    System.out.println(constraint
            + " at " + violation.getPropertyPath());
}
```

This is an illustrative snippet placed inside a scope with appropriate `validator` and `request`; output depends on data/provider. In real applications, you can iterate over `violation.getPropertyPath()` node by node (`Path.Node`) and read `Node#getKey()`/`getKind()` to construct messages tied to specific fields/entries.

**Security:** Map keys can be emails, secret tokens, or user data. Putting raw keys or `getInvalidValue()` into logs/API responses risks data exposure. Filter/mask sensitive data before logging.

## 8. Enabling Validation in Spring MVC

### 8.1. DTO for JSON Requests

In Spring Boot 3.x, `spring-boot-starter-validation` provides the Jakarta Validation provider. With Spring Web MVC, `@Valid` on a `@RequestBody` argument typically triggers validation after Jackson deserializes JSON into the DTO.

The snippets below are examples **to add to a Spring Boot 3 application with web MVC and validation**, not a standalone Java file:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

public record CreateCatalogRequest(
    @NotEmpty Map<
        @NotBlank String,
        @NotNull @Valid CatalogItem> items
) {}

public record CatalogItem(
    @NotBlank String name,
    @Positive int quantity
) {}

@RestController
public class CatalogController {
    @PostMapping("/catalog")
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateCatalogRequest request) {
        // Business processing when standard validation succeeds.
        return ResponseEntity.noContent().build();
    }
}
```

Valid JSON example:

```json
{
  "items": {
    "PEN-01": { "name": "Blue pen", "quantity": 2 },
    "BOOK-02": { "name": "Notebook", "quantity": 5 }
  }
}
```

Some invalid requests and expected violation categories:

| Request/value after deserialization | Violation |
| --- | --- |
| `"items": {}` | `@NotEmpty` on Map |
| `"items": {" ": {"name": "Pen", "quantity": 1}}` | `@NotBlank` on key |
| `"items": {"PEN-01": null}` | `@NotNull` on value |
| `"items": {"PEN-01": {"name": " ", "quantity": 0}}` | `@NotBlank`, `@Positive` inside `CatalogItem` via cascade |
| `"items": {"PEN-01": {"name": "Pen", "quantity": 1}}` | Valid per defined constraints |

The HTTP error response structure depends on `@ControllerAdvice`, `BindingResult`, and Spring configuration; in standard Spring MVC handling, unhandled validation errors on `@Valid @RequestBody` result in HTTP 400. **Unparseable JSON can cause the message converter to fail before Bean Validation runs.**

### 8.2. Do Not Confuse JSON Maps with Key Constraints

A normal JSON object has **string property names**. Jackson usually converts those property names into keys of `Map<String, ...>`; if using `Map<Integer, ...>` or custom object keys, key conversion may require a dedicated key deserializer/configuration. That is **Jackson's** job, not `@NotNull`/`@Pattern` or `@Valid`.

A JSON object also cannot normally represent a null key the way Java `HashMap` can. Thus, null-key cases in Jakarta Validation unit tests do not necessarily have a direct equivalent path in JSON requests.

If JSON contains **duplicate key names**, Jackson or the parser may overwrite earlier entries, keep later ones, or enforce duplicate detection mode. Once in a Java Map, a given key appears only once; Bean Validation cannot "recover" lost duplicate keys. Configure the parser if duplicate JSON field names must be rejected.

### 8.3. `@Valid` at the HTTP Boundary vs. `@Valid` Inside the Map

Both positions matter:

- `@Valid @RequestBody CreateCatalogRequest request`: tells MVC to validate the root DTO after binding.
- `Map<String, @Valid CatalogItem> items`: tells the provider to **cascade** from the DTO to each `CatalogItem` value.

If `@Valid` is missing at the boundary and no other trigger exists, constraints in the DTO may not be evaluated. If `@Valid` is present only at the boundary but the value type lacks `@Valid`, constraints inside `CatalogItem` may **not be deeply validated**, even though constraints directly on key/value type arguments can still be evaluated.

Similarly, using `@Validated` and method validation follow their own trigger rules. Test where the provider is actually invoked rather than assuming placing annotations is sufficient.

## 9. Special Cases to Understand Clearly

### 9.1. `null`, Empty Map, and Null Values Are Not the Same

| Data | `@NotEmpty` on Map | `@NotBlank` on Key | `@NotNull` on Value |
| --- | --- | --- | --- |
| `map == null` | Violation | No keys to check | No values to check |
| `Map.of()` | Violation | No keys to check | No values to check |
| Map with key `"ok"`, null value | Valid per size | Valid | Violation |
| Map with key `""`, valid value | Valid per size | Violation | Valid |
| Map with one valid entry | Valid | Valid | Valid |

`@NotNull`/`@NotBlank` on type arguments check **existing entries**; they do not require the container to have entries. Therefore, if the map must not be empty, also place `@NotEmpty` on the Map.

### 9.2. Constraints on the Map Do Not Replace Element Constraints

```java
@NotEmpty
Map<String, String> labels;
```

A Map with `{"a": ""}` satisfies `@NotEmpty` because it has one entry. To require non-blank values:

```java
@NotEmpty
Map<@NotBlank String, @NotBlank String> labels;
```

And if you only require non-null values while allowing empty strings:

```java
@NotEmpty
Map<String, @NotNull String> labels;
```

Choose based on the contract, not "whichever annotation looks strongest."

### 9.3. `@Valid` Handles Child Objects, Not Aggregate Relationships

`@Valid` follows the bean graph and declared constraints. It does **not** automatically verify that total item quantity matches a budget, SKU keys match `Item.sku`, all values in the Map are unique, or a `"PRIMARY"` key must exist. Aggregate rules like these may require:

- Business validation methods when the service receives the validated DTO.
- A class-level custom constraint (`@ValidCatalog`) with `ConstraintValidator<CatalogConstraint, CatalogRequest>`.
- An immutable API/domain model enforcing invariants in constructors/factories and re-checking on changes.
- Appropriate database constraints if rules must be protected across multiple write paths.

Do not try to force every cross-entry rule into `@NotBlank` on keys or `@NotNull` on values.

### 9.4. Pay Attention to Constraint Type Support

- `@NotBlank` applies to `CharSequence`; do not place it on a Map or bean.
- `@Positive` applies to appropriate numeric types; do not place it on `String` expecting it to parse numbers.
- `@NotEmpty` applies to `CharSequence`, `Collection`, `Map`, and arrays; usable on Map fields or `List`/`Map` values.
- `@Valid` is a cascade marker, not a non-null constraint.
- `@Pattern` on `String`/`CharSequence` allows null per specification; combine with `@NotNull` or `@NotBlank` if needed.
- With Java 17/Spring Boot 3.x, import `jakarta.validation.*`. Spring Boot 2.x projects typically use `javax.validation.*`; mixing namespaces does not mean a newer provider will recognize legacy constraints as expected.

### 9.5. Validation Groups and Nested Validation Groups

Container element constraints and cascaded validation participate in validation groups just like field constraints. If your business logic distinguishes `Create` and `Update` groups, calling `validator.validate(dto, Create.class)` or configuring `@Validated(Create.class)` at supported points determines which constraints are evaluated. When cascading into another bean, groups can propagate or convert via `@ConvertGroup`. Do not blame missing group configuration on a lack of Map key/value support.

### 9.6. Do Not Rely on Map or Violation Set Ordering

`Map` iteration order varies by implementation; `Validator.validate` returns an unordered `Set<ConstraintViolation<T>>`. In tests:

- Sort violations by field, constraint type, or business error code.
- Compare **sets** of paths/types/codes instead of relying on output order.
- When keys hold sensitive data, avoid dumping raw keys into logs.

## 10. Common Pitfalls and Fixes

| Misconception or Error | Consequence | Correct Approach |
| --- | --- | --- |
| Using only `@NotEmpty Map<K,V>` and assuming entries are valid | Keys/values can be invalid or null | Place constraints on K/V |
| Using `@NotNull Map<K,V>` to forbid null values | Only forbids the Map itself being null | `Map<K,@NotNull V>` |
| Putting `@NotBlank` on the whole Map | Constraint does not support Map type | `@NotBlank` on `String` key/value |
| Using `Map<String,@Valid V>` thinking null values are forbidden | `@Valid` skips null | Add `@NotNull` to V |
| Forgetting `@Valid` on value bean | Constraints inside value bean are not cascaded | `Map<K,@Valid V>` |
| Using `@Valid` only on Map and expecting key beans to cascade | Traditional behavior mainly traverses values | `Map<@Valid Key,@Valid Value>` when both are needed |
| Putting `@Valid` on both Map and value type | May validate elements twice or confuse readers | Place `@Valid` on the type argument needing cascade |
| Using `Map.of(key, null)` to test validation | Java throws `NullPointerException` before validator | Use `LinkedHashMap` when null test data is needed |
| Value List has at least one element, but the element is blank | `@NotEmpty List` does not catch blank elements | `List<@NotBlank String>` |
| Omitting `@NotEmpty` on Map because keys are constrained | Empty Map produces no key violation | Add `@NotEmpty` on the container |
| Relying on `Map` to catch duplicate JSON keys | Duplicates may be overwritten during parsing | Configure JSON duplicate detection |
| Comparing exact `Path.toString()` across all providers in tests | Brittle against path formatting differences | Use `Path.Node` and business error schema |
| Missing Jakarta Validation provider or Spring trigger | Annotations do not run as expected | Include starter/provider and `@Valid`/`@Validated` properly |
| Placing constraints on custom container type arguments without an extractor | Metadata error/`ConstraintDeclarationException` | Define/register an appropriate `ValueExtractor` |
| Assuming validation replaces all business/database rules | Cross-entry rules or non-boundary writes can still break | Enforce checks in service/domain/database layers |

## 11. Pre-Implementation Checklist

**Data Model**

- [ ] Can the Map be `null`? Is an empty Map allowed?
- [ ] Must each key be non-null/non-blank/formatted?
- [ ] Must each value be non-null or satisfy a numeric/string constraint?
- [ ] If the value is a bean, is `@Valid` placed on type argument V?
- [ ] If the key is a bean, does type argument K need `@Valid`?
- [ ] If V is a nested `List`/`Map`, is each level annotated properly?
- [ ] Are there cross-key/value or cross-entry rules requiring a custom constraint?

**Spring and Input Data**

- [ ] Is a Jakarta-namespace Bean Validation provider present along with appropriate `@Valid`/`@Validated` triggers?
- [ ] Are Jackson deserialization errors distinguished from Bean Validation errors?
- [ ] Have normal JSON Map keys, blank keys, null values, and invalid value beans been tested?
- [ ] If business rules forbid duplicate JSON fields, is the parser configured to detect them?
- [ ] Does the error response provide enough info to identify the key/value without leaking sensitive data?

**Testing**

- [ ] Have null Map, empty Map, invalid key, null value, invalid child bean, and valid Map been tested?
- [ ] Have values with empty collections and collections containing invalid elements been tested?
- [ ] Do tests avoid relying on Map/Set iteration order or message localization?
- [ ] If using validation groups, has the group actually selected at the boundary been tested?

**Conclusion:** Map constraints operate at two completely different scopes: `@NotEmpty Map<K,V>` checks **the container itself**, while `Map<@... K,@... V>` checks **each key and each value**. Placing `@Valid` on the right type argument drives validation deeper into child objects. Combining these layers cleanly catches invalid data in Spring nested DTOs without confusing containers, entries, and inner beans.

### Official References

- [Jakarta Bean Validation 3.0 — Section 4, Value Extractor Definition; Section 5.5, Container Element Constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Bean Validation 3.0 — `@NotEmpty`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotEmpty.html)
- [Jakarta Bean Validation 3.0 — `@NotNull`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotNull.html)
- [Hibernate Validator 8 — Reference Guide, Container Element Constraints and Cascaded Validation](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
