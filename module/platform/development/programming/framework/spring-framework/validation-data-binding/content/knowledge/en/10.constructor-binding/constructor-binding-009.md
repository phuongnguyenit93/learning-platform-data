# Recursively Constructing Child Objects, Lists, Maps, and Arrays with Constructor Binding in Spring Framework

**Constructor binding** is how Spring Framework creates a Java object from input data by matching values to **constructor parameters**, converting types, and invoking the constructor. When a parameter is itself an object or complex container, Spring can continue constructing the inner values: **child objects, `List`, `Map`, and arrays**. That is the meaning of **recursive construction**.

This topic belongs to the **constructor binding** flow, using `DataBinder.construct(...)` (Spring Framework 6.1+) and Spring MVC's `@ModelAttribute` integration. Distinguish it from setter-based property binding and from `@RequestBody` JSON deserialization.

Examples and concepts use Java 17+ and Spring Framework 6.2.x. Payloads are described as request parameters, query parameters, or form-urlencoded inputs, where **field names** specify paths into the Java structure. Client-supplied data must always be validated for types, sizes, validity, and business permissions.

## 1. How Can a Single Request Build an Entire Object Tree?

Consider data from an order creation form:

```text
recipient.name=Lan
recipient.address.city=Ha Noi
items[0].sku=PEN
items[0].quantity=2
items[1].sku=BOOK
items[1].quantity=4
pickupPoints[office].city=Da Nang
pickupPoints[home].city=Hue
tags[0]=gift
tags[1]=urgent
```

We want to build immutable objects as follows:

```java
public record Address(String city) {}

public record Recipient(String name, Address address) {}

public record LineItem(String sku, int quantity) {}

public record OrderInput(
    Recipient recipient,
    List<LineItem> items,
    Map<String, Address> pickupPoints,
    String[] tags
) {}
```

These are **illustrative type declarations**; to save them as standalone Java files, each `public record` must reside in a file of the same name with `java.util.List`/`java.util.Map` imports. The complete runnable example in section 9 places the records inside one class.

After constructor binding succeeds, the desired structure is:

```text
OrderInput
├─ recipient: Recipient
│  ├─ name = "Lan"
│  └─ address: Address
│     └─ city = "Ha Noi"
├─ items: List<LineItem>
│  ├─ [0] LineItem(sku="PEN", quantity=2)
│  └─ [1] LineItem(sku="BOOK", quantity=4)
├─ pickupPoints: Map<String, Address>
│  ├─ "office" -> Address(city="Da Nang")
│  └─ "home"   -> Address(city="Hue")
└─ tags: String[]
   ├─ [0] "gift"
   └─ [1] "urgent"
```

In constructor binding, Spring **does not need an initial `OrderInput` instance** and does not require nested records to have no-arg constructors or setters. It must know the type structure, constructor parameter names, and corresponding values. Spring constructs each needed object in turn to pass as **arguments to the parent object's constructor**. If no matching data exists for an optional branch, that branch may be absent rather than created unconditionally.

## 2. Two Forms of Binding to Distinguish

| Aspect | Constructor binding | Property binding |
| --- | --- | --- |
| Root object | Newly constructed via data constructor | Usually an existing instance; may be created beforehand via no-arg constructor |
| Data target point | Constructor parameters, matched by name | JavaBean properties via configured setters or field access |
| Child objects | Can be recursively created via data constructors | Can follow nested paths and auto-grow if conditions allow |
| Records / immutable classes | Well suited | Cannot arbitrarily write immutable fields after creation |
| `List`, `Map`, arrays | Can be created from indexed keys or suitable conversion | Can assign/grow writable properties |
| Spring Core API | `DataBinder.construct(ValueResolver)` | `DataBinder.bind(PropertyValues)` |
| Primary risks | Constructor accepting too many parameters/oversized graph; missing data, conversion errors | Mass assignment via setters/fields, uncontrolled index/path growth |

**Very important point:** Spring MVC by default can perform **both** forms of binding for eligible model attributes. Using a record or parameterized constructor handles instantiation, but does not automatically define property-binding behavior for all target types. To enforce declarative constructor binding, configure `setDeclarativeBinding(true)` on the binder; property binding then runs only if `allowedFields` is declared.

Do not treat `@RequestBody` as synonymous: `@RequestBody` is typically deserialized by an `HttpMessageConverter` (e.g., Jackson for JSON), which has different object creation mechanisms and field names from `@ModelAttribute` form parameters.

## 3. How Does Spring Select Constructors and Resolve Parameter Names?

### 3.1. Conditions for Instantiation

According to Spring documentation, the target class should have one public data constructor or a single parameterized non-public constructor. If a class has multiple constructors, the default constructor (if present) may be chosen. To avoid ambiguity, DTOs should have one clear primary constructor; records are ideal examples.

```java
public record ProductLine(String sku, int quantity) {}
```

For the record above, the constructor corresponds to the two components `sku` and `quantity`. Spring looks up those names in the input data and converts `"2"` to `int` before invoking the constructor.

For a hand-written Java class:

```java
public final class ProductLine {
    private final String sku;
    private final int quantity;

    public ProductLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String sku() { return sku; }
    public int quantity() { return quantity; }
}
```

In a standard Java project, compile with constructor parameter name metadata (e.g., `javac -parameters` or Maven compiler `<parameters>true</parameters>`) so Spring knows the names `sku` and `quantity`. Some classes also support alternative metadata such as `@ConstructorProperties`. Without parameter names, Spring cannot infer parameter names from field semantics.

### 3.2. Recursive Processing Flow

Conceptual model:

```text
DataBinder(target=null, objectName="orderInput")
    |
    +-- setTargetType(OrderInput)
    |
    +-- construct(ValueResolver)
            |
            +-- Determine data constructor of OrderInput
            |
            +-- Resolve parameter "recipient" -> Recipient
            |       +-- "recipient.name" -> String
            |       +-- "recipient.address" -> Address
            |                +-- "recipient.address.city" -> String
            |                +-- new Address(city)
            |       +-- new Recipient(name, address)
            |
            +-- Resolve parameter "items" -> List<LineItem>
            |       +-- "items[0].sku", "items[0].quantity"
            |       +-- new LineItem(...)
            |       +-- "items[1].sku", "items[1].quantity"
            |       +-- new LineItem(...)
            |       +-- collect items into List
            |
            +-- Resolve "pickupPoints" -> Map<String, Address>
            |       +-- key "office" -> new Address(...)
            |       +-- key "home" -> new Address(...)
            |
            +-- Resolve "tags" -> String[]
            |       +-- "tags[0]" -> "gift"
            |       +-- "tags[1]" -> "urgent"
            |
            +-- new OrderInput(recipient, items, pickupPoints, tags)
    |
    +-- getTarget() / getBindingResult()
```

This flow explains **object creation dependencies**, not detailed reflection source code or a guarantee that every step executes in this exact order across all Spring versions. The core idea is that to invoke the parent constructor, Spring must prepare each argument; complex arguments are constructed from child path names.

### 3.3. Role of `DataBinder.ValueResolver`

For constructor binding outside the web layer, `DataBinder.construct(...)` takes a `ValueResolver` with two responsibilities:

```java
Object resolveValue(String name, Class<?> type);
Set<String> getNames();
```

- `resolveValue(name, type)` returns the raw value for the requested name, e.g., `"items[0].quantity"` → `"2"`. Returns `null` if no value exists for that exact name.
- `getNames()` provides the set of all field names. Spring can tell that even without a direct value at `"recipient"`, child paths like `"recipient.address.city"` exist, and thus decide whether to build the nested structure.
- `type` is the target type the resolver can use during resolution; simple implementations can return raw strings and let `DataBinder` convert them.
- This is an interface **for looking up input data**, not a place to write constructor-invocation logic for each class.

In Spring MVC, the framework already supplies a suitable resolver for HTTP data. When calling `DataBinder` directly, the application developer supplies the resolver as in the complete example below.

## 4. Field Naming Rules for Objects, Lists, Maps, and Arrays

| Submitted data | Target constructor argument | Meaning |
| --- | --- | --- |
| `recipient.name=Lan` | `recipient.name` | Parameter `name` of object `Recipient` |
| `recipient.address.city=Ha Noi` | `recipient.address.city` | Nested `Address(city)` constructor inside `Recipient` |
| `items[0].sku=PEN` | `items` of type `List<LineItem>` | List element at index 0, parameter `sku` |
| `items[1].quantity=4` | `items` of type `List<LineItem>` | Second element, parameter `quantity` converted to integer |
| `tags[0]=gift` | `tags` of type `String[]` | Array element at index 0 |
| `pickupPoints[office].city=Da Nang` | `pickupPoints` of type `Map<String, Address>` | Value object for entry key `office` |
| `settings[locale]=vi` | `settings` of type `Map<String, String>` | Map entry with key `locale` and value `vi` |

Rules to remember:

1. **Dots** in field names navigate object hierarchy: `recipient.address.city`.
2. **Square brackets with numbers** denote indices in a `List` or array: `items[0]`, `tags[1]`. Indices usually start at 0.
3. **Square brackets with keys** denote a `Map` entry: `settings[locale]`. A `Map` is not an index-ordered List.
4. The name before brackets must match the **constructor parameter**, including case sensitivity.
5. Do not prepend `orderInput.` to field names when an argument is annotated `@ModelAttribute("orderInput")`; that is the Spring MVC model attribute name, not a property inside the object.
6. When forms are sent over URL/HTTP, `[` and `]` characters must follow HTTP encoding rules; use form-building libraries instead of manual string concatenation.
7. For Map keys with special characters, paths need syntax supported by the parser (such as quoted keys where applicable). Avoid constructing property paths from untrusted keys.

## 5. Creating Child Objects via Constructors

Example:

```java
public record Address(String city, String postalCode) {}

public record Recipient(String name, Address address) {}
```

Input:

```text
recipient.name=Lan
recipient.address.city=Ha Noi
recipient.address.postalCode=10000
```

Because `Recipient` requires `Address` in its constructor, Spring processes `Address`'s fields to construct `new Address("Ha Noi", "10000")`, then passes it when constructing `Recipient`. Neither `Recipient.setAddress(...)` nor `Address.setCity(...)` is needed.

**Why can it construct recursively?** Spring sees `Recipient` is an object type with a data constructor and fields prefixed with `recipient.`; when resolving the `address` parameter, values prefixed with `recipient.address.` tell it how to construct that object. This mechanism relies on resolving constructors/parameter names, type conversion, and Spring recognizing the type as an object to construct rather than a scalar.

If the request only has:

```text
recipient.name=Lan
```

do not assume `Address` will definitely be created with all-null fields. When child names are absent, Spring may treat the child argument as missing; when some child names exist while required fields are missing, the object may be created with missing values or the binder may record errors depending on type/constructor. DTO design and validation must clarify which fields are required.

**Excessive nesting** can make graphs hard to validate, hard to reason about, and costly to process. Keep input DTOs at a reasonable depth and bound payloads at the application edge.

## 6. Creating a `List` from Indexed Input

### 6.1. List of Records

With `List<LineItem> items` and:

```text
items[0].sku=PEN
items[0].quantity=2
items[1].sku=BOOK
items[1].quantity=4
```

Spring detects the `items` container parameter and indices 0, 1 from `ValueResolver`'s name set, and can construct `LineItem` elements via their constructors. The string `"4"` is converted to `int 4` using available conversion.

There is no requirement for `LineItem` to have setters or a no-arg constructor when constructor binding uses a suitable data constructor.

### 6.2. List of Primitives/Scalars

A `List<Integer> scores` parameter can accept keys:

```text
scores[0]=10
scores[1]=20
scores[2]=30
```

Each element must be converted from string to `Integer`. Generic `List<Integer>` lets the framework know the element type; declaring a raw `List` loses type information, which can hinder conversion and element construction.

Distinguish three ways of submitting data:

- Multiple indexed keys: `scores[0]=10`, `scores[1]=20`.
- A single value containing a list: `scores=10,20`, when an appropriate converter/editor exists for the target type.
- Multiple values under the same name `scores`, if the HTTP value resolver and conversion support that scenario.

Spring supports constructor binding of collections from **a single suitable string** or from **indexed keys**; that does not mean arbitrary complex record/Map structures can be parsed from a CSV string.

### 6.3. Sparse, Duplicate, or Oversized Indices

With `items[2].sku=BOOK` while indices 0 and 1 are missing, do not assume constructor binding automatically creates exactly one element corresponding to index 2 and compacts the List to size 1. Indexed inputs can yield empty slots or unexpected handling depending on version/configuration. The UI should emit contiguous indices when an ordered List is needed; the server must validate list size and every item.

Indices like `items[999999]` can cause memory/CPU pressure if processed unboundedly. Do not rely solely on `setAutoGrowCollectionLimit(...)` as a universal cap for all constructor binding: Javadoc and behavior can differ across branches/versions. Enforce request limits at the web server/gateway, line-item count rules, maximum index bounds, and post-creation validation. List indices are **not** persisted IDs; business IDs must be re-validated.

## 7. Creating a `Map` with Keys and Object Values

With `Map<String, Address> pickupPoints`:

```text
pickupPoints[office].city=Da Nang
pickupPoints[home].city=Hue
```

Constructor binding can construct `Address` objects under each `Map` entry and pass that Map to `OrderInput`'s constructor.

- `office` and `home` are **keys**, not positional indices.
- Both the `String` key type and `Address` value type must be clearly declared via generics for binding to work as expected.
- With `Map<String, Integer> stock`, a key `stock[pen]=12` requires converting `"12"` → `Integer 12`.
- With `Map<Long, String>`, besides the value, the key `"42"` also needs conversion to `Long`; exact support depends on converters/type metadata.
- Do not rely on `HashMap` iteration order to identify the first or second entry; a `Map` expresses key-value associations, not positional list items.
- Do not assume Spring accepts arbitrary keys such as `metadata[role]`; **the application** must decide which keys belong to the input contract.

A Map holding nested objects can also take forms like `Map<String, List<LineItem>>`. This is a valid Java type combination; exact support for indexed paths, conversion, and nested construction should be tested against your application's Spring version. Do not claim arbitrary deeply nested generic shapes will automatically construct cleanly.

## 8. Creating Arrays in Constructor Binding

Example constructor parameter `String[] tags`:

```text
tags[0]=gift
tags[1]=urgent
```

Spring can create an array with the matching values and pass it into the constructor. A Java array has fixed length for **a single instance**, yet in constructor binding the array is **created** with the appropriate element count to serve as an argument; it does not require pre-allocating an empty array and growing it via setters.

With `int[] quantities`, raw values `"2"` and `"4"` must convert to integers. With `Address[] addresses`, names `addresses[0].city` and `addresses[1].city` can indicate records to build at each position. Conversion or constructor errors can occur if values are invalid.

Arrays often fit small, ordered inputs with fixed element types. `List<T>` is more flexible when forms add/remove rows and collection operations are needed. Both must cap element counts from clients.

## 9. Complete Example: Java 17 + Spring `DataBinder.construct`

This example genuinely uses **constructor binding**, calling neither setters nor `binder.bind(...)`. It demonstrates simultaneously:

1. `Recipient` and `Address` constructed from nested paths.
2. `List<LineItem>` built from indices 0 and 1.
3. `Map<String, Address>` built from keys `home`, `office` and nested values.
4. `String[]` receiving indexed elements.
5. Strings `"2"` and `"4"` converted to `int`.
6. `BindingResult` checked after `construct`.

### 9.1. Project Structure

```text
constructor-graph-demo/
├── pom.xml
└── src/main/java/example/ConstructorGraphDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>constructor-graph-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
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
        <configuration>
          <mainClass>example.ConstructorGraphDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/example/ConstructorGraphDemo.java`:

```java
package example;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.core.ResolvableType;
import org.springframework.validation.DataBinder;

public class ConstructorGraphDemo {

    public record Address(String city) {}

    public record Recipient(String name, Address address) {}

    public record LineItem(String sku, int quantity) {}

    public record OrderInput(
        Recipient recipient,
        List<LineItem> items,
        Map<String, Address> pickupPoints,
        String[] tags
    ) {}

    public static void main(String[] args) {
        Map<String, Object> input = new LinkedHashMap<>();

        input.put("recipient.name", "Lan");
        input.put("recipient.address.city", "Ha Noi");

        input.put("items[0].sku", "PEN");
        input.put("items[0].quantity", "2");
        input.put("items[1].sku", "BOOK");
        input.put("items[1].quantity", "4");

        input.put("pickupPoints[office].city", "Da Nang");
        input.put("pickupPoints[home].city", "Hue");

        input.put("tags[0]", "gift");
        input.put("tags[1]", "urgent");

        DataBinder binder = new DataBinder(null, "orderInput");
        binder.setTargetType(ResolvableType.forClass(OrderInput.class));

        binder.construct(new DataBinder.ValueResolver() {
            @Override
            public Object resolveValue(String name, Class<?> targetType) {
                return input.get(name);
            }

            @Override
            public Set<String> getNames() {
                return input.keySet();
            }
        });

        if (binder.getBindingResult().hasErrors()) {
            throw new IllegalStateException(
                "Constructor binding failed: " + binder.getBindingResult()
            );
        }

        OrderInput order = (OrderInput) binder.getTarget();
        if (order == null) {
            throw new IllegalStateException("No target was constructed");
        }

        System.out.println(
            order.recipient().name() + " / "
                + order.recipient().address().city()
        );
        System.out.println("items=" + order.items().size());
        System.out.println(
            "item2=" + order.items().get(1).sku() + ":"
                + order.items().get(1).quantity()
        );
        System.out.println(
            "pickup=" + order.pickupPoints().get("office").city()
        );
        System.out.println("tags=" + Arrays.toString(order.tags()));
        System.out.println(
            "errors=" + binder.getBindingResult().hasErrors()
        );
    }
}
```

Run from the `constructor-graph-demo` directory:

```bash
mvn -q compile exec:java
```

Expected `stdout` when the binder constructs the object graph cleanly (excluding Maven logs if printed):

```text
Lan / Ha Noi
items=2
item2=BOOK:4
pickup=Da Nang
tags=[gift, urgent]
errors=false
```

**Output explanation:**

- Both `Recipient` and `Address` records are created from values prefixed with `recipient.`; `Lan / Ha Noi` is the data produced by recursive construction.
- `items.size() == 2`; the second element is `LineItem("BOOK", 4)`, showing Spring converted the string `"4"` into `int`.
- `pickupPoints.get("office").city()` reads the object constructed at map key `office`.
- `Arrays.toString(tags)` confirms the array received both indexed elements.
- `errors=false` shows that the values in this scenario are valid for constructors and conversion, **not replacing** business validation.

All nested records of `ConstructorGraphDemo` are `public` with clear data constructors and no setters. `ValueResolver.getNames()` returns all input names, enabling Spring to detect both nested and indexed paths. `spring-context` directly or transitively provides the Spring libraries needed for `DataBinder` and conversion.

If the example behaves differently on another Spring version, first inspect the actual version used, constructor metadata, path syntax, conversion, and `BindingResult`; do not switch to `bind(PropertyValues)` as that turns the lesson into property binding.

## 10. Usage in Spring MVC with `@ModelAttribute`

In Spring MVC, the framework creates `WebDataBinder` and supplies a request-backed `ValueResolver`; handlers normally do not call `construct` themselves. Example:

```java
@RestController
class OrderController {

    @InitBinder("orderInput")
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @PostMapping(
        path = "/orders",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    String create(
        @Valid @ModelAttribute("orderInput") OrderInput form,
        BindingResult errors
    ) {
        if (errors.hasErrors()) {
            return "INVALID";
        }
        return form.recipient().name() + " / "
            + form.items().size();
    }
}
```

This is **integration code**, assuming the `OrderInput`/`Recipient`/`LineItem`/`Address` records are accessible in the controller and web, imports, and validator are configured. A form request with key names like those in section 1 can be bound by Spring through the records' data constructors.

Points to distinguish:

- `@ModelAttribute("orderInput")` sets the **model attribute name** for the binder to look up/create the target. Child parameter names remain `recipient.name`, `items[0].sku`, etc.
- `@InitBinder("orderInput")` applies only to the binder for that matching attribute.
- `setDeclarativeBinding(true)` allows constructor binding while restricting setter/property binding to declared `allowedFields`. This prevents accidentally writing fields with setters outside the designed DTO.
- `@Valid` needs a Jakarta Bean Validation provider and proper constraints to validate contents. It does not inherently check item counts, depth, or access permissions.
- `BindingResult` must be placed **immediately after** the `@ModelAttribute` parameter if the handler handles binding/validation errors itself. Severe instantiation or configuration errors can still raise exceptions.
- For REST controllers accepting JSON, use `@RequestBody` and appropriate JSON configuration: that is a separate deserialization flow.

### 10.1. Renaming Constructor Parameters with `@BindParam`

If an HTML form sends `recipient.postal-code=10000` while the Java constructor parameter is `postalCode`, you can use the annotation:

```java
public record Recipient(
    String name,
    @BindParam("postal-code") String postalCode
) {}
```

When this type is used inside a parent object having parameter `recipient`, the input path becomes `recipient.postal-code`. This is **an alternative `Recipient` record design**, which cannot be pasted alongside the section 9 demo declaring `Recipient(name, Address address)`. `@BindParam` lives in `org.springframework.web.bind.annotation.BindParam` in Spring MVC/WebFlux; standalone core `DataBinder` outside the web layer can configure `setNameResolver(...)` to support custom naming. Do not assume every `ValueResolver` automatically knows aliases without a matching `NameResolver`.

## 11. Handling Conversion Errors, Missing Data, and Validation

### 11.1. Type Conversion Errors on Child Elements

Example:

```text
items[0].sku=PEN
items[0].quantity=abc
```

`LineItem.quantity` is `int`. No valid conversion exists from `"abc"` to `int`, so the binder can register an error for path `items[0].quantity`, typically with a code like `typeMismatch`. Inspect `getBindingResult().getFieldErrors()` to retrieve errors collected by the binder.

Do not claim `getTarget()` will always be non-null after any conversion error. Spring documentation only guarantees the target is set when construction succeeds; configuration or constructor errors can also prevent target creation. In endpoints, never invoke services on a missing or invalid target.

### 11.2. Validation Must Cascade Through the Model

An input DTO declaring constraints, for example:

```java
public record Address(
    @NotBlank String city
) {}

public record LineItem(
    @NotBlank String sku,
    @Min(1) int quantity
) {}

public record OrderInput(
    @Valid Recipient recipient,
    @NotEmpty @Size(max = 20) List<@Valid LineItem> items,
    @Size(max = 5) Map<String, @Valid Address> pickupPoints,
    @Size(max = 5) String[] tags
) {}
```

This is an **annotation-illustration fragment**, needing `jakarta.validation.Valid` and `jakarta.validation.constraints.*` imports, a compatible `Recipient` class, and a Bean Validation provider at runtime. `@Valid` on objects/elements enables cascading into nested objects; placing `@Valid` solely on the controller parameter will not always validate inner fields when cascade points are unmarked.

Distinguish:

| Issue | Appropriate measure |
| --- | --- |
| `items[0].quantity=abc` | Type conversion; binding error |
| `items[0].quantity=-2` | Converts to a number, but needs `@Min(1)` or business validator |
| Empty `items` | `@NotEmpty` if at least one item is required |
| `items` has more than 20 elements | `@Size(max=20)` plus input/index limits before allocation |
| `pickupPoints` contains an unexpected key | Key allowlist / dedicated application-layer validator |
| Blank `recipient.address.city` | Field constraint + `@Valid` cascade |
| `items[0].sku` references a product not owned by the account | Authorization and service checks |

Constraints are checked after the object is bound; they do not automatically limit how many request keys the parser accepts beforehand.

### 11.3. Missing Fields Do Not Equal Conversion Errors

If `recipient.address.city` is omitted, there is no string to convert. Spring may build the object with missing data or treat the argument as missing depending on types and constructor selection rules. To require a city, add `@NotBlank`/`@NotNull` constraints per data type and ensure cascade validation; do not expect the binder to enforce every business rule on its own.

With primitive `int`, missing values can be hard to distinguish from `0` after some processing paths; in input DTOs, consider `Integer` with `@NotNull` when distinguishing missing input from `0` matters.

## 12. Safety and Limits When Constructing Complex Graphs

Constructor binding reduces the risk of unchecked setter binding, yet clients can still supply huge numbers of keys targeting constructor arguments that the DTO accepts. Treat graph sizes and Map key names as untrusted input.

Principles:

1. **Create dedicated input DTOs.** Declare only constructor parameters permitted from clients; avoid putting `role`, `unitPrice`, `approved`, `ownerId`, or `creditLimit` into DTOs just because domain entities have them.
2. **Bound element counts before binding.** Cap total request bytes/parameters, field name lengths, field counts, maximum indices, and nested path depth. Do not rely solely on post-bind `@Size` instead of pre-bind allocation limits.
3. **Allowlist Map keys.** If only `office` and `home` are valid, reject `pickupPoints[admin]` or non-conforming keys. Validate key counts, key types, and key lengths.
4. **Never use List indices as business IDs.** `items[2]` is only a client-sent position; it does not prove a database row has ID 2 or that the user may edit it.
5. **Validate all nested records.** Cascading `@Valid`, element constraints, and cross-field validators must be applied per contract.
6. **Check errors before side effects.** Persist or update only after binding, validation, and authorization all pass.
7. **Enable property binding only when genuinely needed.** `setDeclarativeBinding(true)` or a strict allowlist prevents external data from hitting setters after object construction.
8. **Do not treat `setAllowedFields(...)` as a constructor argument allowlist.** That API mainly applies to property binding; the constructor/DTO design itself determines which parameters constructor binding accepts.
9. **Do not assume property-binding auto-grow limits protect every constructor-binding branch.** Verify your version's contract and enforce limits at request/application boundaries.
10. **Test abnormal inputs.** Try negative indices, huge indices, sparse indices, unknown Map keys, nested objects with missing fields, empty arrays, wrong-typed elements, and oversized requests.

When clients need to update an existing entity, a safe strategy is to accept an immutable DTO via constructor binding, verify permissions/state, and apply permitted changes via a service or entity business method. Never let forms dictate arbitrary fields of persisted objects.

## 13. Design Mistakes and How to Diagnose Them

### 13.1. Spring Cannot Resolve Constructor Parameters

**Symptom:** child objects are empty/missing or errors occur during construction despite reasonable request keys.

**Check:** Do record component names match the keys? Do regular Java classes retain parameter metadata (`-parameters`)? Are constructors ambiguous? Is there a matching `@BindParam`/`NameResolver` when HTML names differ from Java names?

### 13.2. Confusing `items.quantity` with `items[0].quantity`

A List holds multiple items; `items.quantity` does not identify which item. Use proper indexed paths like `items[0].quantity` and `items[1].quantity`. If the container is a `Map`, use keys like `pickupPoints[office].city`.

### 13.3. Declaring Containers Without Generics

Raw `List` or raw `Map` loses element/key/value type information. For nested graphs, declare `List<LineItem>`, `Map<String, Address>`, or `Address[]` so Spring knows what types to convert or construct.

### 13.4. Calling `bind(...)` Instead of `construct(...)`

`binder.bind(new MutablePropertyValues(...))` performs property binding on a target rather than reconstructing the constructor graph in section 9. If your goal is testing recursive constructor binding, use `new DataBinder(null, name)`, `setTargetType(...)`, and `construct(...)`. Inspect `getBindingResult()` and `getTarget()` afterward.

### 13.5. Assuming Records Validate Themselves

Records eliminate setters and help form field-reference-immutable objects, but they do not automatically enforce `@NotBlank`, `@Size`, Map key limits, or authorization. Moreover, a record holding a `List`, `Map`, or array can still hold a reference to a mutable container. For deep immutability, consider copying/guarding containers and validating in constructors, while avoiding exposing raw mutable inputs.

### 13.6. Assuming Nested Construction Always Invokes Every Constructor

Child data without matching keys can be treated as missing; you cannot predict which objects get built without knowing the constructors, resolvers, converters, and inputs. Write tests focused on missing fields, nested paths, and the exact container types used in production.

### 13.7. Allowing Large Indices Without Limits

Inputs like `items[1000000].sku` can trigger excessive allocation/parsing or errors. Enforce caps at the HTTP layer and validate indices and field counts before instantiation; do not treat property-binding limits as universal protection.

## 14. Self-Check Exercises

**Exercise 1 — Reading path names.** Given `record Customer(Address address)` and `record Address(String city)`. With `customer.address.city=Hue` and the parent object constructor having parameter `customer`, describe the objects to construct.

**Answer:** prepare `city="Hue"`, construct `Address("Hue")`, use it to construct `Customer(address)`, and then pass `Customer` into the parent object's constructor. No setters are needed.

**Exercise 2 — Distinguishing index from key.** Given `List<LineItem> items` and `Map<String, Address> stops`. How does `items[2].sku` differ from `stops[2].city`?

**Answer:** in `items[2].sku`, `2` denotes the third position of the List; in `stops[2].city`, for `Map<String, Address>`, `2` is interpreted as the string key `"2"`. Indices/keys never authenticate business IDs.

**Exercise 3 — Predicting conversion.** Given `record LineItem(String sku, int quantity)` and input `items[0].quantity=abc`. Can we rely on Spring creating a valid `LineItem(..., quantity=0)`?

**Answer:** no. `"abc"` does not convert to an integer; inspect binding/conversion errors and do not use the target on error. Return an appropriate error response and avoid persisting data.

**Exercise 4 — Finding a contract flaw.** An API uses `record AdminUpdate(String displayName, String role, Map<String,String> metadata)` for regular users and updates the entity from all fields. Where is the risk?

**Answer:** constructor binding still accepts `role` as a legitimate input and can accept keys like `metadata[privileged]`; use a DTO with only permitted fields, allowlist Map keys, and enforce authorization in the service layer.

## Official Documentation

- [Spring Framework Reference — Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): constructor binding via `DataBinder.construct`, recursive nested objects, indexed `List`, `Map`, and arrays.
- [Spring MVC — `@ModelAttribute` method arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): request-based constructor binding, `@BindParam`, `BindingResult`.
- [Spring MVC — Data Binding and model design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): `declarativeBinding`, property binding, and safety principles.
- [Spring Framework Javadoc — DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): `construct`, `setTargetType`, `setDeclarativeBinding`, error handling.
- [Spring Framework Javadoc — DataBinder.ValueResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html): `resolveValue` and `getNames`.
