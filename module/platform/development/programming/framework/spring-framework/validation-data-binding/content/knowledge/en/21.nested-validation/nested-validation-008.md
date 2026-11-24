# Error Paths with Field Names, Indices, and Keys in Bean Validation

## 1. Goal: An Error Is More Than Just a Message

When validating complex DTOs in Spring, an invalid field does not always live directly on the root object. It may sit inside a child bean, the third element of a `List`, or the value of a `Map` under key `"home"`. Therefore, besides `message`, every `ConstraintViolation<T>` in Jakarta Bean Validation carries an **error path** accessible via `getPropertyPath()`.

Example of an order with data:

```text
OrderForm
├── customer
│   └── name = ""                          <- error on child field
├── items
│   ├── [0] -> Item(sku = "A-01")
│   └── [1] -> Item(sku = "")               <- error on List element at index 1
└── addresses
    ├── ["home"] -> Address(zip = "12x")    <- error in Map at key home
    └── ["work"] -> Address(zip = "12345")
```

Paths commonly seen with Hibernate Validator:

```text
customer.name
items[1].sku
addresses[home].zip
```

They contain three key components:

- **Field/property name**: `customer`, `name`, `items`, `sku`, `addresses`, `zip`.
- **Index**: `[1]` indicates the `List` element at position 1, zero-based.
- **Key**: `[home]` indicates the value in the `Map` corresponding to key `"home"`.

However, the strings above are **human-readable representations**. Jakarta Validation does not require every provider to format `Path.toString()` with the exact same syntax. The true standard API is **`jakarta.validation.Path` with `Path.Node` instances**, holding metadata for name, node kind, index, and key.

Lesson goals:

1. Understand error paths generated when validating nested objects via `@Valid`.
2. Distinguish `node.getName()`, `node.isInIterable()`, `node.getIndex()`, and `node.getKey()`; understand why `null` does not always mean "no key."
3. Distinguish paths for constraints on bean fields from constraints placed on **container elements**, including `<list element>`, `<map key>`, and `<map value>`.
4. Extract structured metadata to map errors to input fields in Spring MVC/APIs, rather than relying solely on string manipulation.
5. Run Java 17+ with Hibernate Validator and compare nested `ConstraintViolation`s against Spring `FieldError`s.
6. Write stable path tests without conflating Bean Validation, data binding, and JSON serialization.

## 2. `getPropertyPath()` Returns `Path`, Not Just `String`

Given `jakarta.validation.ConstraintViolation<T>`:

```java
Path path = violation.getPropertyPath();
String readable = path.toString();
```

This is a **snippet** inside a method that has `violation`; import `jakarta.validation.Path`. `Path` implements `Iterable<Path.Node>`, so its nodes can be traversed sequentially.

Core API:

```java
for (Path.Node node : path) {
    String name = node.getName();
    ElementKind kind = node.getKind();
    boolean inIterable = node.isInIterable();
    Integer index = node.getIndex();
    Object key = node.getKey();
}
```

Also import `jakarta.validation.ElementKind`. Each node describes one step along the path from the validated object to the violation location:

| `Path.Node` Method | Meaning | Key Notes |
| --- | --- | --- |
| `getName()` | Property/method/parameter name, or container node name set by value extractor | May be `null` for a bean node |
| `getKind()` | Node kind, e.g., `PROPERTY`, `BEAN`, `CONTAINER_ELEMENT` | Same name with different node kinds has different meanings |
| `isInIterable()` | Is the node inside a container like `List`, array, `Iterable`, `Map`? | Can be `true` even when both index and key are `null` |
| `getIndex()` | `Integer` index if the node is inside an indexed structure | `null` for Map, Set, or nodes without a numeric position |
| `getKey()` | `Object` key if the node is inside a key-addressed container | Not necessarily `String`; may be `Enum`, `Integer`, or `null` |
| `toString()` | Human-readable representation of node/path | Not a stable parse/serialize contract |

`Path.Node` also provides `as(Class<...>)` to narrow to a specific node interface matching `getKind()`; for `Path.ContainerElementNode`, you can read `getContainerClass()` and `getTypeArgumentIndex()`.

**Most important rule:** use `Path` for structural inspection; use `path.toString()` for display/logging where appropriate, **never** as a strict machine format or a substitute for JSON Pointer.

## 3. Field Names: Paths in Nested Beans

Suppose the model is:

```java
public class OrderForm {
    @Valid
    private Customer customer;
}

public class Customer {
    @NotBlank(message = "Customer name required")
    private String name;
}
```

This code is illustrative only; import `jakarta.validation.Valid` and `jakarta.validation.constraints.NotBlank`, and add constructors/getters/setters per your application. When calling `validator.validate(order)` with `customer.name = ""`, the path is typically:

```text
customer.name
```

The two `Path.Node` instances are:

```text
node 0: kind=PROPERTY, name=customer, inIterable=false
node 1: kind=PROPERTY, name=name,     inIterable=false
```

`customer` is a property of the root, and `name` is a property of the child. Paths are computed **from the validated root**. If you only call `validator.validate(customer)`, the path becomes `name` because the root is now `Customer`.

For a violation on `Customer.name` to appear when validating `OrderForm`, the `customer` property must have `@Valid` to cascade. `@NotBlank` inside the child by itself **does not** force the validator to cross a reference lacking `@Valid`.

If a child further contains `@Valid Address address` and `Address.zip` is invalid, the path may be `customer.address.zip`: each cascade edge adds path context.

### 3.1. Class-Level Errors Do Not Necessarily Have a Field Name

A **class-level** constraint checks a relationship across multiple properties, e.g., "end date must be after start date." If validated at the root, the default path may be an empty string with a `BEAN` node. If that bean is a child `customer`, the class-level error may attach to the child bean path rather than `customer.someField`.

A custom `ConstraintValidator` can use `ConstraintValidatorContext` and `.addPropertyNode("end")` to attach the error to a specific property. In that case, the path changes according to the builder calls used. Do not assume every violation has a `PROPERTY` leaf with a non-`null` name.

## 4. Indices: Errors on `List` or Array Elements

Model containing a list of child objects:

```java
public class OrderForm {
    private List<@Valid Item> items;
}

public class Item {
    @NotBlank
    private String sku;
}
```

The snippets above are illustrative structural code; they require `java.util.List`, `jakarta.validation.Valid`, and `NotBlank`. Bean Validation 2.0+/Jakarta Validation 3.0 supports annotations **on type arguments** to cascade into each element.

If `items` has two elements, the first is valid, and `items.get(1).sku = ""`, Hibernate Validator typically renders:

```text
items[1].sku
```

The path contains index = 1 of the invalid element, zero-based, **not** the 1-based position shown to users in a UI. Under cascaded validation, the `PROPERTY` node named `sku` can record:

```text
node: name=sku
kind=PROPERTY
isInIterable=true
getIndex()=1
getKey()=null
```

Notable detail: the index **does not necessarily attach to the node named `items`**. The specification attaches container context to the node following the traversed relationship; inspect all `Path.Node` elements rather than looking only at the first node.

### 4.1. Constraints on **`String` Elements** vs. Constraints Inside Beans

Compare:

```java
private List<@Valid Item> items;
private List<@NotBlank String> tags;
```

- `@Valid` enters the `Item` object to check `Item.sku`. The path can be `items[1].sku`.
- `@NotBlank` on a **container element** checks each `String` directly. When `tags.get(0) = ""`, Hibernate Validator may return:

```text
tags[0].<list element>
```

In the second case, the leaf node can be `CONTAINER_ELEMENT`, named `<list element>`, with `index = 0`; there is no `sku` property because the error sits directly on the `String` element.

`<list element>` is a **default node name supplied by the value extractor**, **not a Java field name**. When building an API response, decide whether to map the error to `tags[0]` or preserve "List element violation" as metadata.

### 4.2. `Iterable` and `Set` Do Not Necessarily Have an Index

A `Set<@NotBlank String>` or `Iterable` does not provide indexed element addressing like `List`. The provider may set `isInIterable() == true` while `getIndex() == null` and `getKey() == null`; rendering may contain `[]` or a container element node.

Do not infer "the first element" from iteration order over a `Set`: `Set` order is not a stable addressing contract. If the UI needs to bind an error to a control, usually use an indexed list or an application-managed business ID.

### 4.3. When Indices Change

`items[2].sku` is the position in the validated object **at the time of validation**. If the UI subsequently adds/removes/reorders rows, the old index may point to a different item. Therefore:
- Tie errors to the exact data/request snapshot.
- Do not treat indices as durable entity IDs.
- You can send an application-managed row ID alongside if business logic needs stable identification; avoid mutating `Path` directly as a mutable structure.

## 5. Keys: Errors on `Map` Values

Suppose shipping addresses are stored by label:

```java
public class OrderForm {
    private Map<String, @Valid Address> addresses;
}

public class Address {
    @NotBlank
    private String zip;
}
```

This code is illustrative structure; it requires `java.util.Map`, `@Valid`, and `@NotBlank`. When `addresses.get("home").zip = ""`, Hibernate Validator typically produces the path:

```text
addresses[home].zip
```

`home` is the **key** in the Map, not a sequence number. The leaf node is property `zip` of the child bean, and can expose:

```text
node: name=zip
kind=PROPERTY
isInIterable=true
getIndex()=null
getKey()="home"
```

Unlike `List`, `Map` addresses elements by key, not index. Even if the UI displays entries in order, `getIndex()` is not the right way to locate a Map value.

**`getKey()` returns `Object`.** If a Map uses `Map<Integer, Address>`, the key can be an integer; if `Map<Enum, Address>`, the key is an enum. Calling `String.valueOf(key)` can lose type information, create colliding string representations, or include special characters. For public APIs, define key encoding rules for each Map type supported by the application.

### 5.1. Map Value Errors vs. Map Key Errors

Distinguish at least three scenarios:

```java
private Map<String, @Valid Address> addresses;
private Map<@NotBlank String, @Positive Integer> quantities;
```

The second snippet validates Map **keys** and **values** directly using container-element constraints.

| Scenario | Error Type | Typical Hibernate Validator Path |
| --- | --- | --- |
| `addresses["home"].zip` blank | Constraint on field of cascaded child bean | `addresses[home].zip` |
| `quantities["home"] = -1` | `@Positive` constraint on **Map value** | `quantities[home].<map value>` |
| `quantities[""] = 1` | `@NotBlank` constraint on **Map key** | May include `<map key>` node and type argument marker `<K>` |
| `quantities[null] = 1` with `Map<@NotNull String, ...>` | Constraint on **null Map key** | Null key; path can still be `CONTAINER_ELEMENT` inside Map |

`<map value>` and `<map key>` are **container element node names**, not properties on objects held by the Map. Actual rendered patterns depend on the provider; for example, Hibernate Validator may use representations like `quantities[home].<map value>` or `quantities<K>[].<map key>` when the key is null.

**Subtle point:** `getKey() == null` does not necessarily mean the node is not inside a Map. A **null Map key** itself can be the offending key while `isInIterable() == true`. Therefore inspect `isInIterable`, node kind, container structure, and value extractor rules, not just `key != null`.

### 5.2. Nested Containers: `Map<String, List<@Valid Item>>`

An object graph can combine multiple levels:

```java
private Map<String, List<@Valid Item>> itemsBySection;
```

For example, if `itemsBySection.get("summer").get(2).sku` fails, the path carries **both key `summer` and index `2`**. Jakarta Validation represents each step with nodes. With nested containers, the provider may insert `CONTAINER_ELEMENT` nodes such as `<map value>` or `<list element>` to represent hops through containers.

Do not try to guess a single rigid string like `itemsBySection[summer][2].sku`; across implementations and value contexts, extra container nodes can appear. **Iterate over nodes** to collect keys and indices in order, then map them to public field names defined by your application.

## 6. Node Kind Determines How to Interpret the Path

`ElementKind` tells you what a node represents. Common values:

| `ElementKind` | When Encountered | `getName()` May Be |
| --- | --- | --- |
| `PROPERTY` | Constraint on field/getter or traversal step through a property | `customer`, `items`, `sku` |
| `CONTAINER_ELEMENT` | Constraint on List/Map/Optional element or nested container | `<list element>`, `<map key>`, `<map value>` |
| `BEAN` | Class-level constraint on a bean | `null` |
| `METHOD` | Method validated via executable validation | Method name |
| `PARAMETER` | Method/constructor parameter | Name provided by `ParameterNameProvider` |
| `RETURN_VALUE` | Return value of method/constructor | `<return value>` |
| `CROSS_PARAMETER` | Cross-parameter constraint | `<cross-parameter>` |
| `CONSTRUCTOR` | Validated constructor | Constructor name per spec |

This lesson focuses on `PROPERTY`, `CONTAINER_ELEMENT`, and `BEAN` on DTOs, though you may encounter `METHOD`/`PARAMETER` when validating service parameters. Method-style paths can start with a method node rather than a form field.

When `kind == ElementKind.CONTAINER_ELEMENT`, if more precise metadata is needed:

```java
Path.ContainerElementNode element =
        node.as(Path.ContainerElementNode.class);
Class<?> containerType = element.getContainerClass();
Integer argumentPosition = element.getTypeArgumentIndex();
```

This is a **snippet inside a node loop**; only call `node.as(...)` after verifying the matching kind. In Java generics, `List<E>` has type argument index `0`; `Map<K, V>` has index `0` for key and `1` for value. This metadata API is especially helpful when both Map keys and Map values carry constraints, or nested containers make paths ambiguous.

## 7. Standalone Java 17+ Example: Field Names, Indices, and Keys

This example pins **Hibernate Validator 8.0.2.Final** (Jakarta Bean Validation provider) and **Spring Framework 6.2.14** to observe actual paths along with conversion to `BindingResult`. The code avoids depending on `Set<ConstraintViolation<?>>` order by sorting by path.

Three errors:
- `customer.name` blank → path has only field names.
- `lines.get(0).sku` blank → path has List index `0`.
- `offers.get("primary").sku` blank → path has Map key `"primary"`.

### 7.1. Create `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>validation-property-paths</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
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

### 7.2. Create `src/main/java/demo/PropertyPathDemo.java`

```java
package demo;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Path;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.beanvalidation.SpringValidatorAdapter;

public final class PropertyPathDemo {

    public static final class Customer {
        @NotBlank(message = "Name is required")
        private String name;

        public Customer(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    public static final class Item {
        @NotBlank(message = "SKU is required")
        private String sku;

        public Item(String sku) {
            this.sku = sku;
        }

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }
    }

    public static final class Order {
        @Valid
        private Customer customer;

        private List<@Valid Item> lines;

        private Map<String, @Valid Item> offers;

        public Order(Customer customer,
                     List<Item> lines,
                     Map<String, Item> offers) {
            this.customer = customer;
            this.lines = lines;
            this.offers = offers;
        }

        public Customer getCustomer() {
            return customer;
        }

        public void setCustomer(Customer customer) {
            this.customer = customer;
        }

        public List<Item> getLines() {
            return lines;
        }

        public void setLines(List<Item> lines) {
            this.lines = lines;
        }

        public Map<String, Item> getOffers() {
            return offers;
        }

        public void setOffers(Map<String, Item> offers) {
            this.offers = offers;
        }
    }

    private static void require(boolean condition, String explanation) {
        if (!condition) {
            throw new AssertionError(explanation);
        }
    }

    private static Integer indexOf(Path path) {
        for (Path.Node node : path) {
            if (node.getIndex() != null) {
                return node.getIndex();
            }
        }
        return null;
    }

    private static Object keyOf(Path path) {
        for (Path.Node node : path) {
            if (node.getKey() != null) {
                return node.getKey();
            }
        }
        return null;
    }

    public static void main(String[] args) {
        Order invalid = new Order(
                new Customer(" "),
                List.of(new Item("")),
                Map.of("primary", new Item(" ")));

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            Set<ConstraintViolation<Order>> found =
                    validator.validate(invalid);

            List<ConstraintViolation<Order>> errors =
                    new ArrayList<>(found);
            errors.sort(Comparator.comparing(
                    v -> v.getPropertyPath().toString()));

            require(errors.size() == 3, "Expected exactly three errors");

            for (ConstraintViolation<Order> error : errors) {
                Path path = error.getPropertyPath();
                Integer index = indexOf(path);
                Object key = keyOf(path);
                System.out.println(
                        path
                        + " | index=" + (index == null ? "-" : index)
                        + " | key=" + (key == null ? "-" : key)
                        + " | message=" + error.getMessage());
            }
            System.out.println("violations=" + errors.size());

            // Spring converts violations to FieldError.
            BeanPropertyBindingResult bindingResult =
                    new BeanPropertyBindingResult(invalid, "order");
            new SpringValidatorAdapter(validator)
                    .validate(invalid, bindingResult);

            boolean listFieldPresent =
                    bindingResult.getFieldError("lines[0].sku") != null;
            boolean mapFieldPresent =
                    bindingResult.getFieldError("offers[primary].sku") != null;

            require(bindingResult.getFieldErrorCount() == 3,
                    "Spring must have three field errors");
            require(listFieldPresent, "Missing list field error");
            require(mapFieldPresent, "Missing map field error");

            System.out.println(
                    "springFieldErrors=" + bindingResult.getFieldErrorCount());
            System.out.println("springListField=" + listFieldPresent);
            System.out.println("springMapField=" + mapFieldPresent);

            Order valid = new Order(
                    new Customer("Mai"),
                    List.of(new Item("SKU-001")),
                    Map.of("primary", new Item("SKU-002")));
            require(validator.validate(valid).isEmpty(),
                    "Expected no violations on valid order");
            System.out.println("validViolations=0");
            System.out.println("CHECKS: PASS");
        }
    }
}
```

Path checks use `Path.Node` to extract index/key **instead of parsing path strings**. Specifically when looking up `FieldError` in Spring, the example uses the field names built by the Spring adapter and rendered by Hibernate Validator in the pinned version. Test against your project's actual converter/binder configuration.

### 7.3. Run the Program

Using JDK 17+ and Maven:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.PropertyPathDemo
```

Expected lines printed by the program, excluding library startup logs:

```text
customer.name | index=- | key=- | message=Name is required
lines[0].sku | index=0 | key=- | message=SKU is required
offers[primary].sku | index=- | key=primary | message=SKU is required
violations=3
springFieldErrors=3
springListField=true
springMapField=true
validViolations=0
CHECKS: PASS
```

How to read it:
1. `customer.name` shows two property names, **with no** index or key.
2. `lines[0].sku` has property `lines`, an element at index `0`, and offending property `sku`.
3. `offers[primary].sku` has property `offers`, entry at key `"primary"`, and offending property `sku`.
4. All three errors are `@NotBlank` triggered after the respective `@Valid` edges.
5. `SpringValidatorAdapter` converts the same Bean Validation violations into `FieldError`s so views/controllers can look them up by path.
6. The valid object has zero violations. Results are sorted by path before printing, so stdout order is deterministic for the configured example.

**Portability limitation:** The syntax of `Path.toString()` in stdout reflects Hibernate Validator 8.x and the paths in this example; the standard Jakarta Validation API recommends **traversing nodes** when structured processing is needed. Other providers or complex nested containers may render differently. Re-run tests when upgrading implementations.

## 8. Traversing `Path.Node` in Detail to Build Error Locations

The snippet below illustrates extracting an **intermediate list of segments** from a `ConstraintViolation`; depending on your API contract, those segments can be converted into a typed DTO. This is a **method you can place inside a Java class** when `jakarta.validation.Path`, `java.util.List`, and `java.util.ArrayList` are available:

```java
static List<String> describePath(Path path) {
    List<String> parts = new ArrayList<>();

    for (Path.Node node : path) {
        String type = node.getKind().name();
        String name = node.getName() == null
                ? "<bean>" : node.getName();

        String location = "kind=" + type + ",name=" + name;
        if (node.isInIterable()) {
            location += ",iterable=true";

            if (node.getIndex() != null) {
                location += ",index=" + node.getIndex();
            }
            if (node.getKey() != null) {
                location += ",key=" + node.getKey();
            }
        }
        parts.add(location);
    }
    return parts;
}
```

**Notes on the snippet:**
- This uses `String.valueOf` implicitly via string concatenation, suitable only for debugging controlled keys; public APIs must encode keys safely.
- If both `getIndex()` and `getKey()` are null while `isInIterable()` is still `true`, metadata still indicates the node **resides inside an iterable**, such as a `Set` or a Map entry with a null key.
- A `CONTAINER_ELEMENT` node named `<list element>` must not be turned into an object property named `"list element"`.
- With very large data or keys with complex `toString()`, do not log entire paths/keys without size limits and data-masking policies.

### 8.1. When Do You Need `as(Path.ContainerElementNode.class)`?

When the error is a constraint on a generic element such as:

```java
private List<@NotBlank String> tags;
private Map<@NotBlank String, @Positive Integer> quantities;
```

the snippet below sits inside a `Path.Node` loop:

```java
if (node.getKind() == ElementKind.CONTAINER_ELEMENT) {
    Path.ContainerElementNode element =
            node.as(Path.ContainerElementNode.class);

    Class<?> containerClass = element.getContainerClass();
    Integer argumentIndex = element.getTypeArgumentIndex();
    // List<E>: argumentIndex is usually 0
    // Map<K, V>: 0 for key, 1 for value.
}
```

Requires importing `jakarta.validation.ElementKind`; type argument metadata helps disambiguate when paths have multiple container segments. This gives much stronger information than looking for square brackets in text.

### 8.2. Cases Where Paths Cannot Be Mechanically "Translated" to Field Names

- Class-level constraints may have an empty path or a `BEAN` leaf.
- Cross-parameter violations have method nodes and `<cross-parameter>`.
- Return value validation has `<return value>`.
- Constraints on Map **keys** are not properties inside the **value** bean.
- `Optional<@NotNull ...>` may act as a transparent container with no element name shown in the path.
- `List<@NotBlank String>` may produce `<list element>` instead of an object field path.
- Keys containing dots, `]`, slashes, quotes, or Unicode make `split(".")`/bracket regexes unreliable.
- A property named `"items"` in JSON may use a different name in the Java DTO due to `@JsonProperty`, naming strategies, or manual mapping.

If the public API needs exact locations, define an explicit **mapping contract** from nodes to client field paths, with tested escaping/encoding rules.

## 9. Spring MVC: From `ConstraintViolation` to `BindingResult`

In Spring Framework, combining `@Valid` and `BindingResult` typically looks like:

```java
@PostMapping("/orders")
public String submit(
        @Valid @ModelAttribute("order") OrderForm order,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "orders/form";
    }
    return "orders/success";
}
```

This is a **Spring Web MVC controller snippet**, requiring `jakarta.validation.Valid`, `org.springframework.web.bind.annotation.PostMapping`, `ModelAttribute`, and `org.springframework.validation.BindingResult`.

Two-tier annotation relationship:

```text
@Valid @ModelAttribute OrderForm -> triggers root validation on request
    @Valid Customer customer    -> descends from root to Customer
    List<@Valid Item> items     -> descends into each Item in List
    Map<String, @Valid Item>    -> descends into each Item value in Map
```

`@Valid` on the controller parameter initiates validation in the MVC flow; `@Valid` on fields/type arguments controls cascading into children. With a direct Jakarta Validation `Validator.validate(order)` call, the root is already validated by the call itself, requiring no annotation on the local variable.

When Spring MVC infrastructure is properly configured, nested errors populate `BindingResult`:

```java
FieldError firstItemError =
        errors.getFieldError("items[1].sku");
FieldError homeZipError =
        errors.getFieldError("addresses[home].zip");
```

This snippet assumes `BindingResult errors` is already present; `FieldError` is `org.springframework.validation.FieldError`. These field paths **can** match `ConstraintViolation.getPropertyPath().toString()`, but do not treat that correspondence as an absolute rule across all providers, container elements, or binding errors.

### 9.1. How Do Jakarta Paths and Spring Field Paths Differ?

| Jakarta Bean Validation | Spring Validation/Binding | Notes |
| --- | --- | --- |
| `ConstraintViolation.getPropertyPath()` | `FieldError.getField()` | Jakarta returns `Path` with node metadata; Spring returns `String` field name |
| `getInvalidValue()` | `FieldError.getRejectedValue()` | Rejected value may differ for raw input/type conversion cases |
| `getMessage()` | `FieldError.getDefaultMessage()` | Usually processed message, may be resolved further via `MessageSource` |
| `getMessageTemplate()` | No direct corresponding getter on `FieldError` | Spring provides error codes/arguments; not Jakarta templates |
| Node index/key | Property access path of `BeanWrapper`/binder or field path converted by adapter | Must test with nested List/Map and special keys |
| Bean-level violation | `ObjectError` | Does not necessarily map to `FieldError` |

Spring can produce a `FieldError` without any `ConstraintViolation`, for instance when a user submits `"abc"` for an `Integer qty` field and data binding produces a `typeMismatch` error. Jakarta Validation operates on the already-constructed Java object; it is not an arbitrary string parser.

### 9.2. Binding into List/Map Has Its Own Additional Rules

The field paths Spring uses in forms, such as `items[1].quantity`, are property access paths driven by `DataBinder`/`BeanWrapper`. Before Bean Validation runs, the binder must:
- Convert input strings to target property types.
- Locate the corresponding List element or Map entry.
- Have suitable collections/maps and child objects to update fields.

Depending on configuration, the binder can auto-grow collections up to a limit (`autoGrowCollectionLimit`), auto-create nested paths, or reject invalid keys/indices. **That is binding behavior**, not part of the Jakarta `Path` specification.

From a security standpoint, do not let clients arbitrarily bind every nested property of a domain entity. Use dedicated input DTOs, restrict writable fields, depth, collection sizes, converters, and sensitive fields before applying validation.

### 9.3. With `@RequestBody` JSON

The JSON HTTP body is parsed/deserialized (usually via Jackson) before validation. If the JSON is unreadable, the error may be `HttpMessageNotReadableException` with no `ConstraintViolation`. Once deserialized, if `items[1].sku` is blank, Bean Validation can produce a violation with an index.

`getPropertyPath().toString()` itself is **not** a JSON Pointer. If an API uses JSON Pointers like `/items/1/sku`, transform deliberately from path nodes and Java↔JSON mappings (e.g., `@JsonProperty`, naming strategies). Characters `~` and `/` in JSON Pointer must be escaped per RFC 6901; Map keys containing `/` cannot simply be concatenated into a JSON Pointer.

## 10. Designing API Responses with Errors by Field, Index, and Key

An **application-designed** response might look like:

```json
{
  "errors": [
    {
      "location": {
        "property": "items",
        "index": 1,
        "childProperty": "sku"
      },
      "code": "SKU_REQUIRED",
      "message": "Product code must not be blank"
    },
    {
      "location": {
        "property": "addresses",
        "key": "home",
        "childProperty": "zip"
      },
      "code": "ZIP_INVALID",
      "message": "Postal code is invalid"
    }
  ]
}
```

This is **not** a default payload of Spring MVC or Jakarta Validation. The advantage of a structured `location` is distinguishing `index: 1` (Integer) from `key: "1"` (String), while avoiding having to parse a string full of brackets.

Implementation principles:

1. **Stable error codes:** use domain/API-managed `code` values rather than translated messages as IDs.
2. **Control public field names:** Java property paths do not necessarily match client field names.
3. **Preserve key/index types:** keep indices numeric, and preserve key types or encode them per API schema.
4. **Do not leak data:** `getInvalidValue()` may hold passwords/tokens/PII; omit it from default responses.
5. **Limit length/path depth:** client-influenced paths or Map keys can grow huge; enforce bounds and test them.
6. **Place errors appropriately:** class-level errors should have an object-level/`null` `location` rather than fabricating a field name.
7. **Do not build unchecked property access from paths:** never use untrusted input to dynamically read/write internal properties.

### 10.1. Keys Containing Dots or Square Brackets

For example, a Map key is `"a.b"` or `"main]backup"`. A readable path string might look like `addresses[a.b].zip` or another provider-specific form. If you use `split("\\.")`, the dot inside the **key** is mistaken for a property boundary.

The right solution is to read `Path.Node.getKey()` when present, then encode the key per API rules. For Maps with custom object keys, you may need a consistent **key serializer**; do not assume `Object.toString()` is safe or unique.

### 10.2. Linking Errors to Rows in Dynamic UIs

A form allowing rows to be added/removed may change List order between requests. If the server returns `items[2].sku` for data submitted at that moment, the UI should render against **the submitted snapshot**, not attach the index to a reordered item. For complex forms, sending an application-managed row ID can help display errors accurately, though `Path.getIndex()` itself does not generate a business ID.

## 11. Testing Structured Paths and Real Behavior

| Case | Configuration/Data | Expectation |
| --- | --- | --- |
| Root field | `@NotBlank String name` blank | Path has one `PROPERTY` node named `name` |
| Child field | `@Valid Customer`, `customer.name` blank | Path contains `customer` then `name` |
| Missing `@Valid` | Child invalid but parent does not cascade | No child violation from validating parent |
| `List<@Valid Item>` | Item at index 0 invalid | Has `isInIterable=true`, `getIndex()==0` on appropriate node |
| `List<@NotBlank String>` | Element at index 1 blank | Has `CONTAINER_ELEMENT` node such as `<list element>` |
| `Set<@NotBlank String>` | One element invalid | `isInIterable=true` even though index/key may be null |
| `Map<String, @Valid Address>` | Value at key `"home"` invalid | `getKey()` matches `"home"` |
| `Map<@NotBlank String, Integer>` | Blank key | Leaf may be `<map key>`; not a field of value |
| `Map<String, @Positive Integer>` | Negative value | Leaf may be `<map value>` |
| Map with null key | Null key violates `@NotNull` | Distinguish `isInIterable=true` and `getKey()==null` |
| Nested Map→List | `Map<String,List<@Valid Item>>` | Has both key and index metadata across nodes |
| Key containing dot | `"a.b"` | Do not manually split path on dots |
| Non-String key | `Map<Integer, Item>` | Do not confuse numeric key with List index |
| Class-level constraint | Two inconsistent fields | Path may be `BEAN` node / no leaf field |
| Method parameter | Constraint on parameter | Path has `METHOD`, `PARAMETER` nodes and configured names |
| Conversion error | `"x"` bound to `Integer` | Spring `typeMismatch`, not necessarily a Jakarta violation |
| JSON mapping | `@JsonProperty("items")` or naming strategy | Java path is not automatically a JSON Pointer |
| UI reorders items | Dynamic form changes indices | Index ties to validation snapshot, not ID |
| Locale | English/Vietnamese message | Path metadata is not translated message text |
| Sensitive | Map key contains token/PII | Do not arbitrarily log/return raw key or invalid value |

To test **actual structure** rather than a hardcoded path string:

```java
boolean hasIndexZero = violations.stream()
        .anyMatch(v -> {
            for (Path.Node node : v.getPropertyPath()) {
                if (Integer.valueOf(0).equals(node.getIndex())) {
                    return true;
                }
            }
            return false;
        });
```

This is a **test snippet** with existing `violations` and `import jakarta.validation.Path`. If an object has multiple collections, also verify the sequence of `PROPERTY` nodes (`items`) and `CONTAINER_ELEMENT`/leaf property nodes instead of merely asserting index `0` exists anywhere.

### 11.1. Verifying Paths Containing Both Key and Index

For `Map<String, List<@Valid Item>>`, do not only assert `Path.toString()` against a guessed pattern. You can:
- Iterate each `Path.Node` in order.
- Check `getKind()`, `getName()`, and `isInIterable()`.
- Find key `"summer"` on one node, and index `2` on the appropriate subsequent node.
- Verify leaf property `sku`.
- Use `ContainerElementNode.getTypeArgumentIndex()` metadata when multiple generic levels exist.

If framework-specific integration tests are needed, add separate tests for `FieldError.getField()` or the client JSON payload. Portable tests (node metadata) and UI tests (display strings) serve **different purposes**.

## 12. Common Mistakes and Fixes

**1. Treating `getPropertyPath()` as always a `String`.** It returns `Path`. `toString()` helps with logging, but to obtain index/key and container type you must traverse `Path.Node`.

**2. Extracting indices with regex `\\[(\\d+)\\]`.** A Map key might be `"123"`, easily mistaken for index 123. Use `getIndex()` and `getKey()` to preserve semantics.

**3. Assuming `getIndex() == null && getKey() == null` means the node is not in a container.** For `Set`, non-indexed `Iterable`, or a Map with a null key, `isInIterable()` can still be `true`.

**4. Attaching the index to the wrong node.** Container metadata may live on the child node (`sku`/`CONTAINER_ELEMENT`), not the property node named `items`; inspect the whole path.

**5. Thinking `<map value>` is a Java field.** It is a value extractor node name. In responses, express "Map value at key X is invalid" rather than looking for a literal `<map value>` property on the DTO.

**6. Forgetting `@Valid` on parent edges.** Without cascading, a validator starting at the root will not descend into children even if children have constraints. `@Valid` neither creates constraints nor rejects null; use `@NotNull` if the reference is required.

**7. Believing every Spring `FieldError` comes from Jakarta Validation.** `typeMismatch` can occur before Bean Validation, especially when Lists/Maps hold numbers or unbindable nested DTOs.

**8. Using `Set` while expecting `items[0]`.** `Set` has no standard index ordering, so paths cannot promise display positions. Use a collection or ID suited to UI needs.

**9. Splicing Map keys into JSON Pointers or HTML input names without escaping.** Keys can contain `/`, `~`, `.`, `]`, whitespace, or Unicode; apply target protocol serialization/escaping rules.

**10. Using internal paths as unchecked accessors.** Paths and keys can be user-influenced; never use them as authority to read/write arbitrary domain object properties.

**11. Failing to check root instance and validation groups.** Validating a child directly yields a different path than validating from the parent. `@Validated` with different groups can alter the violation set and cascaded edges.

**12. Attaching validation messages to keys/paths and logging sensitive values.** Map paths may contain emails, tokens, or IDs. Apply masking, size limits, and separate error codes from message text.

**13. Mixing Jakarta and javax packages.** Spring Framework 6+ uses the `jakarta.validation.*` ecosystem; older Spring Framework 5.x typically uses `javax.validation.*`. Choose a consistent API/provider rather than changing half the namespaces.

## 13. Workflow for Applying This in a Spring Endpoint

1. **Identify the DTO** and where validation starts: `@Valid @ModelAttribute`, `@Valid @RequestBody`, or direct `Validator.validate(...)`.
2. **Mark cascading** on each edge that must be traversed: `@Valid` on child beans, `List<@Valid Item>`, or `Map<String, @Valid Item>`.
3. **Specify required/nullable** independently with `@NotNull`, `@NotBlank`, `@NotEmpty`, or explicit contracts.
4. **Verify data binding** for indices/keys; restrict writable fields, collection auto-growth, and converters.
5. **Extract violations** via `getPropertyPath()` and nodes; avoid relying on parsing `Path.toString()` as a mandatory format.
6. **Map to public locations**: field, List index, Map key, container-element kind; escape and bound data.
7. **Separate messages** (`getMessage()`), business error codes, and debug metadata; do not expose `getInvalidValue()` by default.
8. **Run realistic tests** for nested properties, Lists, Maps, keys with special characters, Set/null, data conversion, JSON property naming, and UI reordering.
9. **Keep API responses stable** while remaining free to swap Jakarta Validation providers or upgrade Spring/Jackson.

## 14. Official Documentation

- Jakarta Bean Validation 3.0 Specification — `ConstraintViolation`, `Path` and `Node` model, cascade/container elements: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation API 3.0 — `Path`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Path.html
- Jakarta Validation API 3.0 — `Path.Node`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Path.Node.html
- Jakarta Validation API 3.0 — `Path.ContainerElementNode`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Path.ContainerElementNode.html
- Jakarta Validation API 3.0 — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolation.html
- Hibernate Validator 8 — Reference Guide, nested and container element constraints: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework 6.2 — Bean Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — `SpringValidatorAdapter`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html
- Spring Framework 6.2 — `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework 6.2 — `FieldError`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/FieldError.html
