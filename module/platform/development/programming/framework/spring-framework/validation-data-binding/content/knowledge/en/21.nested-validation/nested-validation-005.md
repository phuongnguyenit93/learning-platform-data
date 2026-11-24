# Distinguishing Container Constraints from Element Constraints in Jakarta Bean Validation and Spring

## 1. The Core Problem: A List Existing Does Not Mean Its Elements Are Valid

In a Spring API, suppose a customer sends a list of product codes when creating an order. There are three distinct rules:

1. **The list must exist**: it must not be `null`.
2. **The list must have elements**: it must not be an empty list.
3. **Every code in the list must be valid**: it must not be `null`, empty, or whitespace-only.

These three rules **cannot replace one another**:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

class OrderRequest {
    @NotEmpty
    private List<@NotBlank String> productCodes;
}
```

In the example above:

- `@NotEmpty` placed **before the `List` type** validates the **container itself** `productCodes` (non-null and non-empty).
- `@NotBlank` placed **on the `String` type argument** validates **each element** extracted from the list.
- A list containing element `"   "` fails `@NotBlank`, even though the list itself has size greater than 0.
- Element validation only occurs when there is a container to iterate over; element constraints do not replace a constraint requiring the container to exist.

This belongs to **Jakarta Bean Validation**, using `jakarta.validation.*` APIs in Spring Framework 6 / Spring Boot 3. Legacy Spring ecosystems may use the `javax.validation.*` namespace. Choose a provider and namespace from the same generation.

### 1.1. Quick Comparison Table

| Declaration | What Does It Check? | `null` Container | Empty Container | `null` Element |
| --- | --- | --- | --- | --- |
| `@NotNull List<String> xs` | List must be non-null | Violation | Passes | Passes |
| `@NotEmpty List<String> xs` | List is non-null and has at least one element | Violation | Violation | Passes |
| `List<@NotNull String> xs` | Each element is non-null | Not rejected by this constraint | Passes | Violation if null element exists |
| `List<@NotBlank String> xs` | Each string has non-whitespace content | Not rejected by this constraint | Passes | Violation if null element exists |
| `@NotEmpty List<@NotBlank String> xs` | List has elements **and** each string is non-blank | Violation | Violation | Violation if null element exists |

**`@NotNull` and `@NotEmpty` placed on a list do not automatically validate element contents.** Conversely, placing `@NotBlank` inside `<...>` alone does not ensure the user must supply a list. These annotations operate at **the position** where they are declared.

## 2. Container Constraints: Validating the List, Set, Map, Array, or Optional Itself

A **container-level constraint** is a constraint applied to the data-holding object itself. For example:

```java
@NotNull
private List<String> tags;

@NotEmpty
private List<String> productCodes;

@Size(min = 1, max = 5)
private Set<String> categories;

@NotEmpty
private Map<String, Integer> quantities;
```

These are illustrative fields and do not form a standalone runnable Java class.

### 2.1. Meanings of Common Constraints

- `@NotNull`: the container **is not `null`**, though it may be empty.
- `@NotEmpty`: the container **is not `null` and not empty**; applicable to provider-supported types such as `Collection`, `Map`, arrays, and `CharSequence`.
- `@Size(min, max)`: checks size/length within the specified bounds; **`null` is still valid** under the standard `@Size` contract. If `null` is unacceptable, add `@NotNull` or `@NotEmpty` as appropriate.
- `@Valid`: **is not a constraint checking whether a container exists**; it is a **cascade** signal to related objects when the type/traversal path applies.

For example, `@NotEmpty List<String>` requires size greater than 0. The list `[null]` has one element and therefore **satisfies `@NotEmpty`**. If null elements are disallowed, add `List<@NotNull String>`.

### 2.2. Difference Between `@Size(min = 1)` and `@NotEmpty`

For `List`:

| Input | `@Size(min=1)` | `@NotEmpty` |
| --- | --- | --- |
| `null` | Passes | Violation |
| `List.of()` | Violation | Violation |
| List with one `null` element | Passes | Passes |
| List with one valid element | Passes | Passes |

If you want a container to **exist and have at least one element**, `@NotEmpty` is the concise way to express it. If you want both min and max bounds, combine `@NotNull @Size(min=1, max=20)`. Do not stack every annotation you can think of; express the data contract clearly.

### 2.3. Type Limitations

Do not put `@NotEmpty` on a DTO like `Address` or `Optional<String>` expecting the provider to infer "emptiness"; valid target types depend on defined constraint validators. Standard `@NotEmpty` is not a generic checker for every type with an `isEmpty()` method.

For `Optional<String>`, distinguish **whether the Optional object is null** from **whether the value inside Optional is present/valid**. Later sections explain how to place constraints on type arguments.

## 3. Element Constraints: Constraints Placed in the Type Argument

A **container element constraint** places a constraint directly on the container's element type via `TYPE_USE`:

```java
List<@NotNull String> names;
List<@NotBlank String> namesWithText;
List<@Positive Integer> quantities;
Set<@Email String> recipients;
Map<@NotBlank String, @Positive Integer> stockByCode;
```

These are illustrative type declarations; to compile, place them inside a class and import the annotations.

When the bean is validated, the provider uses a **value extractor** to retrieve elements inside the container and evaluates constraints attached to the type argument. For standard container types such as `List`, `Iterable`, `Map`, and `Optional`, compliant providers like Hibernate Validator already include the necessary extractors.

- `List<@NotNull String>`: each element must be non-null. The string `""` still passes.
- `List<@NotBlank String>`: each element must be non-null, not `""`, and not all whitespace.
- `List<@Positive Integer>`: negative numbers or 0 violate the constraint; `null` elements are still accepted by `@Positive`, so add `@NotNull` to forbid null.
- `Map<@NotBlank String, @Positive Integer>`: **keys** are validated with `@NotBlank`, **values** with `@Positive`; the two positions have independent rules.

Crucially: **you do not need to add `@Valid` just to trigger built-in container element constraints**. For instance, `List<@NotBlank String>` is executed by the provider whenever Bean Validation validates properties on the bean. `@Valid` is for **descending into fields of child beans**, not an on/off switch for `@NotBlank` on `String`.

### 3.1. Why Write `@NotNull List<@NotNull String>`?

The two annotations share a name but have different scopes:

```java
@NotNull
private List<@NotNull String> codes;
```

This corresponds to two separate conditions:

1. `codes != null`;
2. for **every** element `codes[i]`, `codes[i] != null`.

It still **does not require the list to be non-empty** and does not require strings to have characters. To be stricter:

```java
@NotEmpty
private List<@NotBlank String> codes;
```

Then both the container and each string must satisfy the chosen rules.

### 3.2. Distinguish Constraint Names from Annotation Placement

`@NotNull List<String>` is not synonymous with `List<@NotNull String>`:

- The first applies to the **`List`**;
- The second applies to each **`String` inside the `List`**.

Likewise, do not treat `@NotEmpty List<String>` and `List<@NotEmpty String>` as equivalent: the former requires the list to have elements; the latter checks that each `String` is non-empty (while an empty list still passes). When reading source code, look at **whether the annotation sits before or inside `<...>`**.

### 3.3. A Data Table with Concrete Examples

Suppose a property is declared:

```java
@NotEmpty
private List<@NotBlank String> names;
```

| Value of `names` | Container Error | Element Error |
| --- | --- | --- |
| `null` | `@NotEmpty` | Elements not traversed |
| `[]` | `@NotEmpty` | No elements to check |
| `[null]` | None | `@NotBlank` at element 0 |
| `[""]` | None | `@NotBlank` at element 0 |
| `["   "]` | None | `@NotBlank` at element 0 |
| `["Alice"]` | None | None |
| `["Alice", ""]` | None | `@NotBlank` at element 1 |

The returned error set is `Set<ConstraintViolation<T>>`. Iteration order is not guaranteed; each failed constraint can produce a violation. For UIs, paths may include element indices/keys depending on container structure and provider.

## 4. @Valid: Nested Validation Differs from Simple Element Constraints

In Bean Validation, `@Valid` directs validation to **continue into the object graph**, such as an `OrderLine` element having a `sku` field with `@NotBlank`.

```java
class OrderLine {
    @NotBlank
    String sku;
}

class OrderBatch {
    @NotEmpty
    List<@NotNull @Valid OrderLine> lines;
}
```

There are three layers:

1. `@NotEmpty` checks whether `lines` is null/empty.
2. `@NotNull` checks whether **each `OrderLine` element** is non-null.
3. `@Valid` requests **cascading into each existing `OrderLine` bean** to evaluate constraints on `sku` and other fields.

### 4.1. Which Cases Produce Errors?

| Value of `lines` | Result |
| --- | --- |
| `null` | `@NotEmpty` violation; no elements to cascade |
| `[]` | `@NotEmpty` violation |
| `[null]` | Container passes; element `@NotNull` violation; `@Valid` skips null |
| `[OrderLine(sku="")]` | Both container and element exist; nested `@NotBlank` on `sku` violated |
| `[OrderLine(sku="A01")]` | No corresponding violation |

**`@Valid` itself does not require elements to be non-null.** Therefore `List<@Valid OrderLine>` is not equivalent to `List<@NotNull @Valid OrderLine>`. Add `@NotNull` in the right spot when a null element is invalid data.

### 4.2. Without @Valid, Deep Validation Does Not Run Automatically

Suppose you write:

```java
@NotEmpty
List<OrderLine> lines;
```

Bean Validation will verify `lines` is non-empty, but will not automatically validate `OrderLine.sku`. If `lines` holds client-constructed `OrderLine` instances whose internal constraints must be checked, add `@Valid` at the appropriate cascade position:

```java
@NotEmpty
List<@Valid OrderLine> lines;
```

Since Jakarta Bean Validation 2.0, placing `@Valid` directly on the **type argument** is the clearest expression, especially with nested generics and `Map` keys/values. You may see the older form `@Valid List<OrderLine> lines` for cascading container elements in supported containers; avoid placing `@Valid` **on both the container and the type argument of the same cascade path**, as the specification recommends choosing one location to avoid duplicate validation.

### 4.3. Element Constraints and Cascading Are Not the Same

`List<@NotNull OrderLine>` only asks whether elements are null; it does not run `@NotBlank` on `sku`.

`List<@Valid OrderLine>` runs constraints inside `OrderLine`; it does not forbid null elements by itself.

`List<@NotNull @Valid OrderLine>` does both.

`@NotEmpty List<@NotNull @Valid OrderLine>` adds the container element count requirement.

These are four distinct scopes and must be chosen according to your data contract.

## 5. Map: Keys, Values, and the Map Itself Can Be Constrained

`Map<K,V>` is a container with **two type arguments**. Example:

```java
class Address {
    @NotBlank String street;
}

class ShippingRequest {
    @NotEmpty
    Map<@NotBlank String, @NotNull @Valid Address> addressesByLabel;
}
```

Rules at each level:

- `@NotEmpty` on `Map`: map is non-null and must contain at least one entry.
- `@NotBlank` on key: each label must have text, e.g., `"home"`, `"office"`; labels `""` or `null` fail.
- `@NotNull` on value: each `Address` must be non-null.
- `@Valid` on value: deeply validates `Address.street` with `@NotBlank`.

A `Map` with entry `("", new Address(""))` will have at least two logical issues: blank key and blank street. If the value is `null`, the missing object is caught by `@NotNull`, while `@Valid` cannot check fields on a nonexistent object.

### 5.1. Validating Only the Container Is Insufficient

`@NotEmpty Map<String,Address>` only requires an entry; blank keys, null values, and `Address` objects with invalid fields can still pass.

`Map<@NotBlank String,Address>` catches key errors, but does not ensure non-null values and does not cascade.

`Map<String,@Valid Address>` cascades into existing values, but does not catch null values or blank keys.

`Map<@NotBlank String,@NotNull @Valid Address>` combines key and value validation.

When the map itself must exist, add a container constraint such as `@NotEmpty`.

### 5.2. Error Paths and Map Keys

A violation can carry a path like `addressesByLabel[home].street` for the `street` field and a key/value element path for `TYPE_USE` constraints. Providers may display node names like `<map key>` or `<map value>`; do not hardcode exact path strings across all providers.

The structured data to use when needed is `Path.Node`, `isInIterable()`, `getKey()`, `getIndex()`, and node kind `ElementKind.CONTAINER_ELEMENT`. Do not assume every path has a numeric index: `List` typically has an index, `Map` typically has a key, and `Set` may not identify positions by a stable index.

**Security caution:** `Map` keys or `getInvalidValue()` may contain sensitive information. When converting violations into HTTP responses or logs, filter values, use safe error messages/codes, and do not expose raw personal data.

## 6. Multi-Level Nested Containers and Exact Per-Level Constraints

Generics can nest: `Map<String, List<Address>>`, `List<List<String>>`, or `Map<String, Optional<Address>>`. Constraints must be placed **on the exact container layer** you want to validate.

### 6.1. Map Containing List

```java
class BatchRequest {
    @NotEmpty
    Map<@NotBlank String, @NotEmpty List<@NotBlank String>> codesByGroup;
}
```

Analysis:

1. Outer `@NotEmpty` checks that `Map` is non-null and contains at least one group.
2. `@NotBlank String` in `Map` validates group names (keys).
3. `@NotEmpty List<...>` validates **each list value**: each group's list must be non-null and have elements.
4. `List<@NotBlank String>` validates each code inside each list.

For instance, `{"primary": ["A", "B"]}` passes this structure; `{"primary": []}` fails because the value is an empty list; `{"primary": [""]}` fails because an element is blank; `{"": ["A"]}` fails because the key is blank.

To cascade multi-level child objects:

```java
Map<String, List<@NotNull @Valid Address>> addressesByGroup;
```

This lets the provider use value extractors sequentially into `Map` then `List`, and then apply `@NotNull` and `@Valid` to each `Address`. There is no need to redundantly declare `@Valid` on every intermediate container when the type argument position already identifies the exact elements to cascade.

### 6.2. Optional: The Wrapper Differs from the Inner Value

Example:

```java
@NotNull
Optional<String> nickname;

Optional<@NotBlank String> displayName;
```

For `nickname`, `@NotNull` sits on the **Optional object**: an `Optional.empty()` is still a non-null object, so it satisfies `@NotNull`. If `nickname == null`, this constraint is violated.

For `displayName`, `@NotBlank` sits on the **value wrapped by Optional**. Hibernate Validator/Jakarta Bean Validation uses the `Optional` extractor to validate the inner value; `Optional.of(" ")` violates it, while `Optional.of("Alice")` passes. With `Optional.empty()`, the extracted value is treated as absent: a null-forbidding constraint like `@NotNull`/`@NotBlank` on the type argument can reject this case according to the corresponding extractor/constraint. If `displayName` itself is a `null` reference rather than an Optional object, do not assume the inner constraint checks wrapper presence; declare a separate container rule when needed.

Typically **there is no need to use `Optional` as a DTO or entity field**, especially with Jackson, JPA, and data binding. Many systems use regular nullable fields in DTOs and reserve `Optional` as a return type for query APIs. Only use `Optional` containers when data design and serialization/binding tooling support them consistently.

### 6.3. Groups and Group Conversion

Both container and element constraints accept the `groups` attribute. Example:

```java
interface Submit {}

class CreateRequest {
    @NotEmpty(groups = Submit.class)
    List<@NotBlank(groups = Submit.class) String> codes;
}
```

Only when validating with `Submit.class` (or an appropriate sequence/inheritance) are those group constraints executed; a default `validator.validate(bean)` call selects `Default` and may skip them.

When cascading `@Valid` into child beans, `@ConvertGroup` can be used at the cascade site to convert the parent group to a child group. This is a mechanism for **cascaded validation**, not a way to make a container's `@NotEmpty` turn into an element constraint.

## 7. Value Extractors: How Bean Validation Sees Elements

Why does Bean Validation understand `List<@NotNull String>` while potentially failing to understand an application-defined `Box<@NotNull String>`? Because the system uses **`ValueExtractor`** to extract elements from containers.

- Built-in supported containers: various `Iterable`/`List` forms, `Map` (both key and value), `Optional`, and several others depending on the provider.
- For a custom container `Box<T>`, a matching `ValueExtractor` for type argument `T` must exist and be registered with the provider.
- When multiple extractors match ambiguously, configuration may fail to resolve the extraction target and throw an exception.
- Extractors can supply indices/keys or node names for `ConstraintViolation#getPropertyPath()`.

Example declaring a custom container:

```java
public final class Box<T> {
    private final T item;
    public Box(T item) { this.item = item; }
    public T getItem() { return item; }
}
```

To use `Box<@NotBlank String>` and have the validator understand it, a corresponding extractor is required, for example:

```java
import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.ValueExtractor;

public class BoxValueExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {

    @Override
    public void extractValues(
            Box<?> original, ValueExtractor.ValueReceiver receiver) {
        receiver.value(null, original.getItem());
    }
}
```

This is illustrative code that needs to be placed in properly named Java files in a project; it is not part of the standalone program in Section 8. To use it, configure the provider to register `BoxValueExtractor` (for example via `configuration.addValueExtractor(new BoxValueExtractor())` or an appropriate service loading/container registration mechanism). Without an extractor for a custom container, Bean Validation has no standard way to know which elements to validate.

**Note:** do not confuse value extraction with `@Valid`: the extractor **locates elements**; `TYPE_USE` constraints check those values; `@Valid` specifies whether to continue running constraints inside child beans. The three mechanisms have distinct responsibilities.

## 8. Complete Java 17+ Example: Container and Elements Producing Violations Independently

This example uses Jakarta Bean Validation 3.x with Hibernate Validator 8.x, without needing Spring running to understand the semantics. Model:

- `@NotEmpty List<@NotNull @Valid Line> lines`: container must be non-empty; elements non-null; nested `Line.sku` must have content.
- `@NotNull List<@NotBlank String> tags`: container must exist, may be empty; each tag non-blank.
- `Map<@NotBlank String, @NotNull @Valid Line> byCode`: validates keys, values, and nested beans; the map is **not** required to exist since there is no container annotation.

### 8.1. pom.xml

Create any Maven project directory, then create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>container-element-demo</artifactId>
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
    </dependencies>
</project>
```

This dependency pulls in the Jakarta Validation API and related transitive dependencies. To run the CLI example without configuring Jakarta Expression Language separately, the program selects Hibernate Validator's `ParameterMessageInterpolator`. This is a provider-specific API, not a portable Jakarta API; applications using EL message expressions must configure an appropriate EL implementation.

### 8.2. File ContainerElementDemo.java

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ContainerElementDemo {

    public static final class Line {
        @NotBlank
        private final String sku;

        public Line(String sku) {
            this.sku = sku;
        }
    }

    public static final class Checkout {
        @NotEmpty
        private final List<@NotNull @Valid Line> lines;

        @NotNull
        private final List<@NotBlank String> tags;

        private final Map<@NotBlank String, @NotNull @Valid Line> byCode;

        public Checkout(
                List<Line> lines,
                List<String> tags,
                Map<String, Line> byCode) {
            this.lines = lines;
            this.tags = tags;
            this.byCode = byCode;
        }
    }

    private static void report(
            String label, Set<? extends ConstraintViolation<?>> errors) {
        System.out.println(label + " -> " + errors.size());
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Checkout valid = new Checkout(
                    List.of(new Line("SKU-1")),
                    List.of("sale"),
                    Map.of("main", new Line("SKU-2")));

            List<Line> linesWithErrors = Arrays.asList(
                    new Line(""), null);
            List<String> tagsWithErrors = Arrays.asList(
                    " ", null);

            Map<String, Line> mapWithErrors = new LinkedHashMap<>();
            mapWithErrors.put("", new Line(""));

            Checkout invalid = new Checkout(
                    linesWithErrors, tagsWithErrors, mapWithErrors);

            Checkout emptyContainers = new Checkout(
                    List.of(), List.of(), Map.of());

            Checkout nullContainers = new Checkout(
                    null, null, null);

            report("valid", validator.validate(valid));
            report("invalid", validator.validate(invalid));
            report("empty containers", validator.validate(emptyContainers));
            report("null containers", validator.validate(nullContainers));
        }
    }
}
```

### 8.3. Run Commands

Requires JDK 17+ and Maven. Run in the directory containing `pom.xml` and `ContainerElementDemo.java`.

Bash (Linux/macOS):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" ContainerElementDemo.java
java -cp ".:$CP" ContainerElementDemo
```

PowerShell (Windows):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content -Raw classpath.txt).Trim()
javac -encoding UTF-8 -cp $cp ContainerElementDemo.java
java -cp ".;$cp" ContainerElementDemo
```

Expected stdout (excluding any extra provider/Maven logs or warnings printed by the environment):

```text
valid -> 0
invalid -> 6
empty containers -> 1
null containers -> 2
```

Explanation of each case:

- **`valid -> 0`:** all containers and every element/nested bean satisfy their constraints.
- **`invalid -> 6`:** `lines` has a `Line(sku="")` bean causing one `@NotBlank` error and a null element causing one `@NotNull` error; `tags` has a whitespace string and a null element causing two `@NotBlank` errors; `byCode` has a blank key causing one `@NotBlank` error and a `Line(sku="")` bean causing one nested `@NotBlank` error. Total `2 + 2 + 2 = 6`.
- **`empty containers -> 1`:** `lines=[]` violates `@NotEmpty`; `tags=[]` is valid because `@NotNull` does not require elements; `byCode={}` is valid because there is no container constraint.
- **`null containers -> 2`:** `lines=null` violates `@NotEmpty`, `tags=null` violates `@NotNull`; `byCode=null` has no constraint applied to the map itself, so it is not rejected by this constraint set alone.

To observe exact error locations, you can print `violation.getPropertyPath()`, `violation.getConstraintDescriptor().getAnnotation().annotationType().getSimpleName()`, and iterate through `Path.Node` instances. Do not assert that element path representations are identical across all providers, and do not rely on `Set` ordering.

### 8.4. Why Doesn't Everything Need @Valid?

`@NotBlank` in `List<@NotBlank String>` is already a `TYPE_USE` constraint, so the validator extracts each `String` element and checks it directly. It **does not need `@Valid`**.

`Line.sku`, on the other hand, is a **property of a child bean**: it requires `@Valid` on the `Line` type argument or an equivalent cascade path to enter `Line`. Before running the example, remember `@Valid` does not forbid null, so `@NotNull` on the element and `@Valid` are commonly combined.

### 8.5. Practice Extensions

Change one line at a time to observe the difference yourself:

1. Remove `@NotEmpty` on `lines`: `emptyContainers` changes from one error to zero errors, while element errors in `invalid` remain.
2. Remove `@NotNull` on the `Line` type argument in `lines`: null elements are no longer caught directly; `@Valid` still skips null.
3. Remove `@Valid` on `Line`: `sku` content will not be traversed solely via `@NotNull` and `@NotEmpty`.
4. Add `@NotEmpty` onto `byCode`: empty or null maps are also rejected.
5. Replace `@NotNull List<@NotBlank String> tags` with `@NotEmpty List<@NotBlank String> tags`: `tags=[]` becomes invalid.

These changes help clearly distinguish **container constraints**, **element constraints**, and **cascaded validation**.

## 9. Connecting to Spring MVC and Data Binding

In Spring MVC, JSON/form data can bind into a DTO and then be checked by Bean Validation when the controller declares `@Valid` or `@Validated` on the appropriate parameter. This is where picking the right constraint layer becomes critical: the request has a list, the list has elements, and each element has fields.

Illustrative DTO for a JSON API:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public class CreateOrderRequest {

    @NotEmpty
    private List<@NotNull @Valid LineRequest> lines;

    public List<LineRequest> getLines() {
        return lines;
    }

    public void setLines(List<LineRequest> lines) {
        this.lines = lines;
    }

    public static class LineRequest {
        @NotBlank
        private String sku;

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }
    }
}
```

This is an integration DTO (separate file `CreateOrderRequest.java`), not part of the standalone program in Section 8. Each order line must have a non-blank `sku`, each line element must be non-null, and the list must be non-empty.

Illustrative controller inside a `@RestController` with corresponding Spring imports:

```java
@PostMapping("/orders")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateOrderRequest request,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        var codes = bindingResult.getFieldErrors().stream()
                .map(e -> e.getField() + ":" + e.getCode())
                .toList();
        return ResponseEntity.badRequest().body(codes);
    }

    return ResponseEntity.ok().build();
}
```

Processing flow to understand:

1. `HttpMessageConverter`/Jackson deserializes JSON into the DTO; malformed JSON or type mismatches can fail **before** Bean Validation is invoked.
2. When `@Valid` on the parameter is handled by Spring via the appropriate MVC mechanism, the validator checks the root DTO, container constraints, elements, and then cascades along `@Valid` type arguments.
3. `BindingResult`, if placed immediately after the corresponding DTO, can capture field errors. Field paths may include indices like `lines[0].sku` or container element markers.
4. Once validation passes, the service must still check whether the SKU exists, is sellable, has sufficient stock, permissions, and business limits. Bean Validation only enforces the rules it is configured with.

**Do not confuse `@Valid` on the controller with `@Valid` on a type argument.** The first signals Spring/MVC to validate the incoming object; the second specifies the cascade path into beans held inside the container. You must consider both **the trigger point** and **the traversal path**.

### 9.1. Do Form Binding and JSON Differ?

They can differ during data construction:

- JSON `{"lines": null}` or an omitted field usually produces `lines == null` (depending on deserializer/constructor/defaults), so `@NotEmpty` catches it.
- JSON `{"lines": []}` produces an empty list, which `@NotEmpty` also catches.
- JSON `{"lines": [null]}` produces a list with one null element; container `@NotEmpty` passes, while element `@NotNull` fails.
- JSON `{"lines": [{"sku": ""}]}` has a non-null element; nested `@NotBlank` on `sku` fails if cascading is active.

With form parameters like `lines[0].sku`, Spring's binder/auto-growing collections and binding configuration affect element creation and index handling, differing from Jackson JSON deserialization. Test the actual HTTP path rather than only calling standalone `Validator` and assuming JSON/forms always yield the same object graph.

### 9.2. Validation Groups in Spring

Spring's `@Validated(SomeGroup.class)` can select a group for the DTO. Both container and type-argument constraints accept `groups`; if validating only the `Create` group while constraints belong to `Default`, they will not run automatically unless an appropriate sequence/inheritance/conversion is declared.

When cascading into child beans, group propagation or `@ConvertGroup` can make the child bean's active group differ from the container's group. Test group policies per Create/Update operation, especially with optional/partial updates and nested containers.

### 9.3. Protecting Against Malicious Input

`@NotEmpty` only requires at least one element; it **does not block huge lists**. Use `@Size(max=...)` or API-level element caps, configure JSON/form payload size limits, and check total nested object counts to prevent CPU/memory abuse.

`TYPE_USE` constraints can evaluate every element; deep nesting combined with large payloads incurs significant validation cost. Do not let validation checks substitute for request size limits, rate limits, database constraints, or authorization.

## 10. Common Traps

| Common Mistake | Why Is It Wrong? | How to Fix |
| --- | --- | --- |
| Assuming `@NotEmpty List<String>` checks non-blank Strings | Only checks list size | Add `List<@NotBlank String>` |
| Assuming `List<@NotNull String>` requires the list to have elements | Constraint is only on each element | Add `@NotEmpty` to the list |
| Assuming `List<@Valid Address>` forbids null elements | Cascade skips null references | Use `List<@NotNull @Valid Address>` |
| Assuming `@NotNull List<@Valid Address>` forbids empty lists | `@NotNull` only forbids a null container | Add `@NotEmpty` or `@Size(min=1)` |
| Container has child objects, but inner fields report no errors | Missing `@Valid` cascade | Place `@Valid` on the type argument / valid cascade path |
| Putting `@Valid` on both List and type argument on the same path | May configure redundant cascading | Pick one position, preferring the type argument |
| `Map<@NotBlank String,Address>` still allows null Address | Key constraint does not check values | Add `@NotNull` on the value type argument |
| Only `@Valid` on Map value, yet empty map still passes | Cascade does not require map entries | Add a container constraint if needed |
| `@Size(min=1) List<?>` still accepts null | `@Size` permits null | Combine with `@NotNull` or `@NotEmpty` |
| Custom container `Box<@NotBlank String>` does not work | Missing matching `ValueExtractor` | Register a custom `ValueExtractor` and test |
| Annotations present, yet HTTP returns no validation errors | Validation not triggered by Spring, missing provider, or wrong namespace | Add provider and `@Valid`/`@Validated` in the right place |
| JSON with null elements causes unexpected binding errors | Deserialization/type construction happens before validation | Separate JSON reading errors from constraint violations |
| Calling `validateProperty` expecting nested `@Valid` to run | This API does not perform cascading | Use `validate(rootBean)` when object graph checks are needed |
| Counting errors while ignoring index/key | List/map errors have specific locations | Read `Path.Node`, attach errors to the right element |
| Assuming Bean Validation checks DB relationships/ownership | Constraints only enforce declared rules | Check business rules in service/transaction |
| Logging full violations including user input | May leak sensitive data | Log error codes/paths, mask raw values |

### 10.1. Distinguishing from Class-Level/Cross-Field Constraints

Neither container-level nor element-level constraints suffice for rules spanning **multiple** elements. For example, "product code list must have no duplicates" or "total quantity across all lines must not exceed the limit" requires collection/bean-level or business validation. `@NotEmpty` and `@NotNull` do not detect duplicates or compute sums.

You can write a custom constraint applying to the list, a class-level constraint on the DTO, or validate in the service. Do not try to use per-element regexes to express rules that depend on other elements.

### 10.2. Required Tests

Write explicit tests for at least the following cases:

1. Container null, empty, single-element, multi-element.
2. Null element, empty string, whitespace string, child object with invalid fields.
3. Valid `List` with invalid nested bean: error only appears when proper cascading is configured.
4. `Map` with invalid key, null value, value with invalid fields.
5. Multi-level nested generics: empty inner list, invalid deeply nested element.
6. `Optional.empty()`, `Optional.of(...)` if business data genuinely uses `Optional`.
7. Default validation group and custom groups; when using `@ConvertGroup`, test the cascade path.
8. `getPropertyPath()`, indices/keys, and mapping errors to UI.
9. JSON/form input with type mismatches, missing properties, huge containers, and payload limits.
10. Schema/provider upgrades: ensure value extractors and constraint metadata work as expected.

**Do not assert the iteration order of `Set<ConstraintViolation<?>>`.** For stable tests, sort by path/constraint or assert sets of keys regardless of order.

## 11. Three-Level Constraint Selection Process

When designing a container property:

1. **May the container object itself be null?** If not, place `@NotNull` or a stronger constraint like `@NotEmpty` on the property itself.
2. **May the container be empty?** If not, choose `@NotEmpty` or `@Size(min=1)` plus an appropriate non-null condition.
3. **What rules must each element follow?** Place constraints inside the type argument, e.g., `List<@NotBlank String>` or `Map<@NotBlank String,@Positive Integer>`.
4. **May elements be null?** If not, place `@NotNull` on the type argument (many constraints like `@NotBlank` already forbid null).
5. **Are elements beans with inner field constraints?** Add `@Valid` on the type argument to cascade into child beans.
6. **Does the container have multiple levels?** Place constraints at **every level needing control**; do not put an annotation on an outer Map when you intend to forbid an empty inner List.
7. **Are there groups or custom containers?** Identify the active groups, cascade paths, and `ValueExtractor`, and test on your actual provider.
8. **Does data come from Spring MVC?** Ensure validation is triggered after binding, errors are handled accurately, and business rules are checked independently.

**One-sentence takeaway:** **container** constraints ask "does the box exist and have enough elements?"; **container element** constraints ask "is each item inside the box valid?"; `@Valid` asks "should we continue checking properties of the object inside?". A safe API usually combines all three instead of picking one and assuming the other two are guaranteed.

### References

- Jakarta Bean Validation 3.0 Specification — Container element constraints, cascaded validation, value extraction: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Hibernate Validator 8 Reference Guide — Container element constraints and Value extraction: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Jakarta Validation API — `@Valid`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valid
- Jakarta Validation API — `@NotEmpty`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/notempty
- Spring Framework — Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring MVC — `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
