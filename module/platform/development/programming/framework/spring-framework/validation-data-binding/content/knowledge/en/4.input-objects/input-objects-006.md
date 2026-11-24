# Nested Objects, Lists, Arrays, and Maps in Input Data

> Scope: Spring Framework Data Binding (especially Spring MVC with `@ModelAttribute`), Java 17+. This lesson focuses on how Spring reads **property paths** to create or update an **object graph** from form/query data, handling collections, arrays, Maps, and the limits that must be controlled.

## 1. Why Can Input Data Contain Complex Structures?

An HTTP request using `application/x-www-form-urlencoded` can submit a set of `name=value` pairs. Field names do not have to be flat like `name` or `email`: Spring can interpret `customer.address.city`, `lines[0].sku`, `tags[1]`, and `options[theme]` to bind into Java structures inside a target object.

Example of an order containing a recipient, order lines, category tags, and an options Map:

```text
customer.name=Mai
customer.address.city=Hue
lines[0].sku=PEN
lines[0].quantity=2
lines[1].sku=BOOK
lines[1].quantity=3
tags[0]=gift
tags[1]=office
options[delivery]=express
```

This data can produce the following shape:

```text
OrderInput
├── customer : CustomerInput
│   ├── name = "Mai"
│   └── address : AddressInput
│       └── city = "Hue"
├── lines : List<LineInput>
│   ├── [0] { sku = "PEN", quantity = 2 }
│   └── [1] { sku = "BOOK", quantity = 3 }
├── tags : String[]
│   ├── [0] "gift"
│   └── [1] "office"
└── options : Map<String, String>
    └── ["delivery"] = "express"
```

Turning `"2"` into `int 2` or `"true"` into `Boolean.TRUE` is **type conversion**. Placing the result into `customer.address.city` or `lines[0].quantity` is **property binding**. When the target is newly constructed via a constructor, Spring also supports **constructor binding** for nested structures, `List`, arrays, and `Map`.

This data comes **from the client and is untrusted**. Property names, indices, and Map keys can all be forged by the client; never treat them as proof of access rights or valid element counts.

## 2. Property Path Naming Rules

Spring Core uses JavaBeans access mechanisms (typically via `BeanWrapper`) to interpret expressions such as:

| Field Name in Request | Java Target | Meaning |
| --- | --- | --- |
| `name` | `form.getName()` | Direct property |
| `customer.name` | `form.getCustomer().getName()` | Property of a nested object |
| `customer.address.city` | `form.getCustomer().getAddress().getCity()` | Multiple nesting levels |
| `lines[0]` | `form.getLines().get(0)` | First element of a list |
| `lines[1].quantity` | `form.getLines().get(1).getQuantity()` | Property of a list element |
| `tags[1]` | `form.getTags()[1]` | Second element of an array |
| `options[delivery]` | `form.getOptions().get("delivery")` | Map value by key |
| `details[sku-1].caption` | `form.getDetails().get("sku-1").getCaption()` | Object inside a Map |
| `options['theme.dark']` | `form.getOptions().get("theme.dark")` | Syntax for keys containing dots inside single quotes |

The `.` syntax navigates down into an object; `[index]` indexes (typically starting at `0`); `[key]` selects a Map key. Quote syntax expresses keys containing characters that could otherwise be confused with path structure. In real URLs/forms, `[`, `]`, quotes, and Unicode characters must be encoded according to HTTP rules; use an HTTP/form library rather than concatenating URL strings manually.

**Do not prefix the model attribute name out of habit.** With `@ModelAttribute("orderInput") OrderInput form`, standard fields are `customer.name` and `lines[0].sku`, not `orderInput.customer.name`. `orderInput` is the target object's name in Model/BindingResult, not automatically a property of the object itself.

Naming differs for **JSON**: `@RequestBody` receives JSON and deserializes it via `HttpMessageConverter`. JSON payloads use actual objects/arrays rather than form field name strings like `lines[0].sku`.

## 3. Nested Objects

### 3.1. Property Binding Traversing Multiple Levels

Consider the model `OrderInput.customer.address.city`. To bind `customer.address.city=Hue`, Spring must traverse `customer`, then `address`, and finally write the `city` property.

```java
public class AddressInput {
    private String city;

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
}

public class CustomerInput {
    private AddressInput address;

    public AddressInput getAddress() { return address; }
    public void setAddress(AddressInput address) { this.address = address; }
}

public class OrderInput {
    private CustomerInput customer;

    public CustomerInput getCustomer() { return customer; }
    public void setCustomer(CustomerInput customer) { this.customer = customer; }
}
```

These are illustrative classes; when stored separately, each public class requires a matching filename and Java rules apply. For mutable JavaBeans, `DataBinder` enables `autoGrowNestedPaths` by default: if `customer` or `address` is `null`, the binder **can** create the corresponding object via suitable instantiation and proceed to set `city`. This requires the nested type to be instantiable and the property path to be accessible/writable.

You can proactively initialize the object in the constructor/field for explicit intent:

```java
private CustomerInput customer = new CustomerInput();
```

Auto-growing nested objects is **not a guarantee** that Spring can always instantiate interfaces, abstract classes, classes lacking a suitable constructor, or immutable objects via setters. When a path cannot be accessed, check the specific error type and DTO design.

### 3.2. Do Not Confuse Auto-Grow with Constructor Binding

- **Property binding:** uses getters/setters or configured field access mode, and can auto-instantiate `null` child elements while traversing property paths.
- **Constructor binding:** as of Spring Framework 6.1+, creates new objects by matching constructor parameter names, converting values, and **recursively creating child objects**. For nested records, setters are not needed for each field. This can include `List`, arrays, and `Map`.

Example record design for nested data (type declarations, not a standalone program):

```java
public record AddressInput(String city) {}
public record CustomerInput(String name, AddressInput address) {}
public record OrderInput(CustomerInput customer) {}
```

The keys `customer.name` and `customer.address.city` allow Spring to construct `CustomerInput` and `AddressInput` via suitable data constructors in the `@ModelAttribute` flow. For regular Java classes, ensure constructor parameter names are available at runtime (e.g., compiled with `-parameters`); records retain component names naturally.

## 4. `List<T>`: Element Indices and Objects Inside Lists

A `List<LineInput>` represents an ordered, indexed collection of elements:

```java
public class LineInput {
    private String sku;
    private int quantity;

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public int getQuantity() { return quantity; }
    public void setQuantity(int quantity) { this.quantity = quantity; }
}

public class OrderInput {
    private List<LineInput> lines = new ArrayList<>();

    public List<LineInput> getLines() { return lines; }
    public void setLines(List<LineInput> lines) { this.lines = lines; }
}
```

Include `import java.util.List;` and `import java.util.ArrayList;` if separating these classes into Java files. From the form:

```text
lines[0].sku=PEN
lines[0].quantity=2
lines[1].sku=BOOK
lines[1].quantity=3
```

When binding succeeds, `lines.size() == 2`; `lines.get(0).getSku()` is `"PEN"`, and `lines.get(1).getQuantity()` is `3`.

Key points to grasp:

1. Indices **start at 0**. `lines[1]` is the second line, not a line with business ID `1`.
2. `lines[0].quantity` needs a clear element type (typically `List<LineInput>`); if declared as a raw `List`, Spring lacks generic type info to infer the element type during instantiation/conversion.
3. With property binding and `autoGrowNestedPaths=true`, Spring can grow the List and instantiate elements to handle new indices. Instantiating new items still depends on the item type and instantiability.
4. Sparse indices like `lines[5].sku` can grow the List up to six positions, leaving intermediate positions without complete business data. Validate line count, index continuity, and empty elements if business rules require it.
5. `Set` lacks stable positional semantics like `List`. Do not rely on `set[0]` to map ordered forms; use `List` for ordered inputs or identifying keys in a Map.
6. When users add, remove, or reorder rows in the UI, synchronize field names accordingly. Submitting stale non-contiguous indices can misalign the object graph and error locations relative to what appears on screen.
7. Never let the client turn `lines[0].id` or `lines[0].price` into an update to persisted records. IDs, prices, and edit permissions must be verified on the server.

For scalar lists like `List<Integer> quantities`, `quantities[0]=4` and `quantities[1]=8` are converted to integers. Sending comma-separated strings like `quantities=4,8` can be supported when an appropriate converter is present; do not assume every collection or complex object type supports a CSV string.

## 5. Arrays: `String[]`, `int[]`, and Growth Limits

An array is an ordered structure with a fixed length for **a single array instance**. Property binding can allocate a larger array when needed to resolve an index and then update the bean's array property if the path permits. Example:

```java
public class TagForm {
    private String[] tags = new String[0];

    public String[] getTags() { return tags; }
    public void setTags(String[] tags) { this.tags = tags; }
}
```

With `tags[0]=gift` and `tags[1]=office`, `Arrays.toString(form.getTags())` is expected to return `"[gift, office]"` if the binder permits both fields and no errors occur.

Several differences compared to `List`:

| Property | `List<T>` | `T[]` |
| --- | --- | --- |
| Container type | Interface/implementation such as `ArrayList` | JVM array |
| Manual element addition | `add`/`set` via List API | Must allocate a new array to change length |
| Input name | `lines[0].sku` | `tags[0]` |
| Generic / element type | Should declare `List<LineInput>` | Element type is carried by `String[]` or `int[]` |
| Auto-grow in property binding | Can grow List within limits | Can allocate larger array and reassign property within limits |

Forms like `tags[0]`, `tags[1]` differ from repeating multiple inputs with the same name `tags` or passing `tags=gift,office`. Behavior of the latter depends on conversion, collection type, and binding setup; test with the exact payload form you use.

`int[]` accepts numeric values, e.g., `scores[0]=10`. Sending `scores[0]=abc` must cause the binder to report a type-conversion error rather than silently treating `abc` as a valid number.

## 6. Map: Keys Are Not Positional Indices

`Map<K,V>` maps a **key** to a **value**. Fields:

```text
options[delivery]=express
options[language]=vi
limits[booking]=5
flags[featured]=true
```

can bind onto properties such as:

```java
private Map<String, String> options = new LinkedHashMap<>();
private Map<String, Integer> limits = new HashMap<>();
private Map<String, Boolean> flags = new HashMap<>();
```

Thanks to generics, the binder has type information to convert `"5"` to `Integer` and `"true"` to `Boolean`. If the **key** itself is not `String` (e.g., `Map<Long, String>`), conversion must also convert the key; an appropriate converter/editor is required.

### 6.1. Maps Whose Values Are Nested Objects

With `Map<String, DetailInput> details` and class `DetailInput` having a `caption` setter, `details[SKU-A].caption=Note` can bind to `details.get("SKU-A").getCaption()`. If the entry does not yet exist, auto-creation depends on the element type, how the Map is initialized, binder settings, and the active binding mechanism. Initialize the Map, declare explicit generics, and verify with tests. Do not assume Map is bounded identically to List auto-grow limits.

**Map keys and List indices are different:** `details[7]` with `Map<String, DetailInput>` normally uses the key `"7"`, whereas `lines[7]` is the eighth position. Do not treat `details[7]` as the eighth position in the Map.

### 6.2. Keys Containing Special Characters

For keys containing dots such as `theme.dark`, use quoted key syntax inside brackets: `options['theme.dark']`. For keys containing quotes or brackets, choose syntax and input encoding compatible with your framework version; test real cases and never manually concatenate untrusted path strings.

`Map` does not necessarily preserve order. If the UI must display insertion order, choose `LinkedHashMap` in the data layer; if business logic requires a **positional list of rows**, use `List`. Do not rely on `HashMap` iteration order to identify the "first" record.

### 6.3. Maps and Dynamic Key Data

Inputs like `metadata[role]=ADMIN` or `prices[item-1]=0` demonstrate that clients can invent **arbitrary keys**. Even when the `metadata` property name is allowed, collection limits do not automatically restrict key count, key length, value format, or permission to modify sensitive keys. Whitelist keys per business rules or validate every entry, limit entry counts at the request/application layer, and strip disallowed data before processing.

## 7. Standalone Java 17 Example with `DataBinder`

The example below uses **Spring Core DataBinder**, without starting a web server. It demonstrates nested objects, a List, an array, a Map, type conversion, allowed-field restrictions, and suppressed fields together. Because it is a self-contained Java program, all helper classes live in one file.

Create the structure:

```text
nested-binding-demo/
├── pom.xml
└── src/main/java/example/NestedBindingDemo.java
```

Contents of `pom.xml` (example with Spring Framework 6.2.10, Java 17):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>nested-binding-demo</artifactId>
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
          <mainClass>example.NestedBindingDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Contents of `src/main/java/example/NestedBindingDemo.java`:

```java
package example;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

public class NestedBindingDemo {

    public static class Address {
        private String city;

        public Address() {}

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }

    public static class Line {
        private String sku;
        private int quantity;

        public Line() {}

        public String getSku() { return sku; }
        public void setSku(String sku) { this.sku = sku; }

        public int getQuantity() { return quantity; }
        public void setQuantity(int quantity) { this.quantity = quantity; }
    }

    public static class Form {
        private Address address;
        private List<Line> lines = new ArrayList<>();
        private String[] tags = new String[0];
        private Map<String, Integer> stock = new LinkedHashMap<>();

        public Form() {}

        public Address getAddress() { return address; }
        public void setAddress(Address address) { this.address = address; }

        public List<Line> getLines() { return lines; }
        public void setLines(List<Line> lines) { this.lines = lines; }

        public String[] getTags() { return tags; }
        public void setTags(String[] tags) { this.tags = tags; }

        public Map<String, Integer> getStock() { return stock; }
        public void setStock(Map<String, Integer> stock) { this.stock = stock; }
    }

    public static void main(String[] args) {
        Form form = new Form();
        DataBinder binder = new DataBinder(form, "form");

        // Limit List/array growth during property binding.
        binder.setAutoGrowCollectionLimit(8);

        // Allow binding only to expected paths.
        binder.setAllowedFields(
            "address.city",
            "lines[*].sku",
            "lines[*].quantity",
            "tags[*]",
            "stock[pen]"
        );

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("address.city", "Ha Noi");
        values.add("lines[0].sku", "PEN");
        values.add("lines[0].quantity", "2");
        values.add("lines[1].sku", "NOTE");
        values.add("lines[1].quantity", "4");
        values.add("tags[0]", "gift");
        values.add("tags[1]", "office");
        values.add("stock[pen]", "12");
        values.add("role", "ADMIN"); // Not in allowedFields.

        binder.bind(values);

        System.out.println(form.getAddress().getCity());
        System.out.println(form.getLines().size());
        System.out.println(
            form.getLines().get(1).getSku() + ":"
            + form.getLines().get(1).getQuantity()
        );
        System.out.println(Arrays.toString(form.getTags()));
        System.out.println(form.getStock().get("pen"));
        System.out.println(binder.getBindingResult().hasErrors());
        System.out.println(
            Arrays.toString(binder.getBindingResult().getSuppressedFields())
        );
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Expected standard output of the program, excluding Maven dependency download logs if printed:

```text
Ha Noi
2
NOTE:4
[gift, office]
12
false
[role]
```

Step-by-step explanation:

- `address` starts as `null` but is instantiated to receive `city`.
- The List starts empty; `lines[0]` and `lines[1]` are created and populated, with `"4"` converted to `int 4`.
- The `tags` array starts with length 0 and grows to hold two elements.
- `stock[pen]` is converted from `String` to `Integer` according to the declared Map type.
- `hasErrors()` returns `false` because the **bound** fields have valid types.
- `role` is excluded by the allowlist; `getSuppressedFields()` reports the blocked field. A suppressed field is not the same as a conversion error, and you should not rely on `hasErrors()` to conclude the request had no unlisted fields.

Note: this example uses a pre-created `Form` instance and calls `bind(PropertyValues)`, so it illustrates **property binding**. It does not test constructor binding for records; that is a separate path in the `DataBinder` API.

## 8. Wiring into a Spring MVC Controller

Suppose the application receives an HTML form with field `name` attributes as in section 2. A handler can declare:

```java
@PostMapping("/orders")
public String createOrder(
        @Valid @ModelAttribute("orderInput") OrderInput input,
        BindingResult result) {
    if (result.hasErrors()) {
        return "orders/new";
    }
    orderService.createOrder(input);
    return "redirect:/orders";
}
```

This is **integration code**, requiring `@Controller`, web/validation dependencies, the `OrderInput` DTO, service, and matching views. `BindingResult` must sit **immediately after** its model attribute. `@Valid` triggers validation when an appropriate provider/configuration is present; it does not enforce line-count limits, Map key whitelists, or business checks unless those constraints are declared.

Configure a binder per model attribute name:

```java
@InitBinder("orderInput")
void configureOrderBinder(WebDataBinder binder) {
    binder.setAutoGrowCollectionLimit(20);
    binder.setAllowedFields(
        "customer.name",
        "customer.address.city",
        "lines[*].sku",
        "lines[*].quantity",
        "tags[*]",
        "options[delivery]"
    );
}
```

This is an **illustrative configuration**: adjust fields and limits to match business rules. Spring supports the `*` wildcard in `allowedFields` patterns, including nested/indexed paths. `lines[*].sku` allows `lines[0].sku`, `lines[7].sku`, etc.; it does not validate line count or allow editing every field on Line. `options[delivery]` accepts only the `delivery` key, which is safer than allowing all keys via `options*` when the key set should be finite.

Create a dynamic HTML form:

```html
<form action="/orders" method="post">
  <input name="customer.name" value="Mai">
  <input name="customer.address.city" value="Hue">

  <input name="lines[0].sku" value="PEN">
  <input name="lines[0].quantity" value="2">

  <input name="lines[1].sku" value="BOOK">
  <input name="lines[1].quantity" value="3">

  <input name="tags[0]" value="gift">
  <input name="options[delivery]" value="express">
  <button type="submit">Create order</button>
</form>
```

This is an example of **field names**, omitting CSRF configuration, full page markup, add/remove row UI, or user authentication. In a real application, keep CSRF/authorization mechanisms and server-side validation. Never rely on HTML `disabled` or JavaScript as a security boundary; clients can submit arbitrary field names.

## 9. Constructor Binding with Nested Objects and Containers

When designing immutable DTOs/records, constructor binding resolves constructor parameters by name and constructs the graph instead of calling setters. Spring Framework supports constructor parameters of nested object, `List`, array, and `Map` types; values can come from indexed keys like `lines[0].sku` or `options[delivery]`. For certain scalar types, comma-separated strings can be converted into lists/arrays when an appropriate converter exists.

Data-type example (not a standalone program):

```java
public record AddressInput(String city) {}

public record LineInput(String sku, int quantity) {}

public record OrderInput(
    AddressInput address,
    List<LineInput> lines,
    String[] tags,
    Map<String, String> options
) {}
```

With parameter `@ModelAttribute("orderInput") OrderInput input`, a request can contain:

```text
address.city=Hue
lines[0].sku=PEN
lines[0].quantity=2
lines[1].sku=BOOK
lines[1].quantity=3
tags[0]=gift
options[delivery]=express
```

Key difference: Spring constructs `OrderInput` via its constructor while also instantiating nested `AddressInput` and `LineInput`. Records have no setters for property binding to mutate after construction. You do not need to simulate `autoGrowNestedPaths` with setters in this case.

From Spring 6.1+, you can configure `binder.setDeclarativeBinding(true)` so constructor binding continues to work while property binding runs only when `allowedFields` is specified. This helps for models that have both constructors and setters; however, **it does not mean every client-submitted nested structure is automatically safe**. Every constructor argument accepted by the DTO must still be checked for length, element count, Map keys, authorization, and business rules.

Note that `setAutoGrowCollectionLimit` primarily governs **auto-growing arrays/lists in property binding** and should not be treated as a general limit for Maps or constructor binding. When using constructor binding with large collections, enforce limits at the request, DTO/validation, and application layers accordingly.

## 10. Validation and Errors in Nested Structures

### 10.1. Element Validation Requires Cascading

With Jakarta Bean Validation, for example:

```java
public class OrderInput {
    @Valid
    @NotNull
    private CustomerInput customer;

    @NotEmpty
    @Size(max = 20)
    private List<@Valid LineInput> lines;

    @Size(max = 10)
    private String[] tags;

    @Size(max = 5)
    private Map<String, String> options;

    // Getters/setters and initializers declared per DTO design.
}

public class LineInput {
    @NotBlank
    private String sku;

    @Positive
    private int quantity;

    // Corresponding getters/setters.
}
```

This is a **constraint illustration**, not a complete file; it requires importing `jakarta.validation.Valid`, `jakarta.validation.constraints.*`, a Bean Validation provider, and the related classes. `@Valid` on nested objects or List element type parameters triggers **cascading** into elements; putting `@Valid` only on the root parameter is insufficient if the DTO does not declare proper cascade annotations. `@Size(max=20)` bounds the bound collection's size, but does not replace payload/index controls before binding allocates elements.

### 10.2. FieldError Carries Full Paths

Suppose a client sends:

```text
customer.address.city=Hue
lines[0].sku=PEN
lines[0].quantity=abc
```

Spring cannot convert `"abc"` into `int`. When the binding mechanism records the error, `BindingResult` can hold field path `lines[0].quantity` with a `typeMismatch` error; validator errors can also carry paths such as `customer.address.city` or `lines[1].sku`.

```java
for (FieldError error : result.getFieldErrors()) {
    System.out.println(error.getField() + ": " + error.getCode());
}
```

This is a **handler snippet**, assuming `BindingResult result` and `import org.springframework.validation.FieldError`. Do not assert a fixed error count, order, or exact message text, as these depend on binding/validation and message resolver configuration. For nested collections, returning accurate error paths lets the UI attach errors to the exact row and field.

Errors can occur before the full object graph is constructed, or when accessing an invalid path. `BindingResult` collects errors that can be recorded; severe instantiation or configuration failures can still throw exceptions. Do not assume every nested error turns into a valid object with `hasErrors=true`.

### 10.3. Distinguishing Binding Errors from Business Errors

| Scenario | Layer to Handle It |
| --- | --- |
| `lines[0].quantity=abc` cannot convert to `int` | Binding/type conversion, return field error |
| `lines[0].quantity=-3` converts successfully but is invalid | Bean Validation with `@Positive` or custom validator |
| `lines` has 10,000 elements or huge index | Request/binder limits and size checks |
| `options[admin]=true` is a disallowed key | Allowlist + key validation |
| `lines[0].productId` refers to a product the user cannot order | Server-side authorization/business logic |
| `lines[0].price=0` attempts to override selling price | Never bind prices from client; look up authoritative price on server |

## 11. Limits and Input Safety

Once a bean exposes nested paths, Lists, or Maps, clients may try sending fields absent from the UI:

```text
lines[999999].sku=PEN
customer.role=ADMIN
options[internalMode]=enabled
customer.address.otherSensitiveField=value
```

Controls to combine:

1. **Use dedicated input DTOs.** Never bind directly onto domain entities containing fields like `role`, `price`, `approved`, `ownerId`, or `balance`.
2. **Restrict property binding.** `setAllowedFields(...)` must list safe paths; wildcards should be narrow and deliberate. With `setDeclarativeBinding(true)`, property binding occurs only when `allowedFields` is declared.
3. **Limit List/array growth.** `WebDataBinder.setAutoGrowCollectionLimit(n)` controls auto-grow in setter/property binding; `DataBinder`'s default is 256. Lower it when forms only need a few items. It is **not** a total request quota, not a Map size limit, and does not govern constructor binding.
4. **Limit payload depth and complexity.** Do not let clients construct unbounded object graphs via nested paths. Depending on Spring version there may be additional depth settings; keeping DTOs shallow, restricting allowed field paths, and enforcing request limits at the gateway/server remain essential.
5. **Restrict Map keys.** Permit only supported keys; check key count, key/value lengths, format, and semantics. Never assume `Map<String, String>` filters out unexpected keys on its own.
6. **Validate the graph after binding.** Use `@NotNull`, `@Size`, `@Valid`, per-element constraints, and business validators. Distinguish validation from conversion; never call the service when binding has failed.
7. **Never trust client indices/IDs.** Indices only organize input positions. Persisted record identifiers must be looked up again and checked for ownership and permissions on the server.
8. **Avoid treating suppressed data as valid.** `getSuppressedFields()` reports fields rejected by the allowlist; decide whether to reject the whole request or log/monitor anomalies per application policy.
9. **Test abnormal payloads.** Test negative/huge indices, sparse indices, duplicate keys, unknown Map keys, nested nulls, wrong element types, missing elements, and oversized requests.

With Maps holding object values or Lists backed by custom classes, unexpected allocations can also occur when accessing indices/keys. Prefer standard collection types, apply security patches for your Spring version, and enforce appropriate request limits.

## 12. Checklist and Self-Check Exercises

### Implementation Quick Check

- Does the model have suitable getters/setters (property binding) or a suitable data constructor (constructor binding)?
- Do field names use `address.city`, `lines[0].sku`, `tags[1]`, and `options[key]` matching the DTO structure accurately?
- Are List/Map element types declared with clear generics for conversion?
- Can `null` nested objects or elements be instantiated when needed? Are constructors/accessors available?
- Are Map keys and List indices clearly separated when handling business IDs?
- Are List/array growth, Map key count, payload length, and object graph depth bounded?
- Does the allowlist block sensitive fields at every nesting level?
- Are nested `@Valid` and collection/element constraints configured?
- When a type-conversion error occurs at `lines[1].quantity`, does the UI show it on the right row and stop business execution?

### Exercise 1 — Reading an Object Graph

Given `CatalogForm` with `List<ProductInput> products`, `Map<String, String> settings`, and `CustomerInput customer`. Input:

```text
products[0].sku=ABC
products[1].sku=XYZ
settings[locale]=vi
customer.address.city=Da Nang
```

Describe the three paths and their values. **Answer:** `products.get(0).getSku() = "ABC"`, `products.get(1).getSku() = "XYZ"`; `settings.get("locale") = "vi"`; `customer.getAddress().getCity() = "Da Nang"` (assuming binding succeeds and the DTO structures are instantiable).

### Exercise 2 — Finding the Design Flaw

An endpoint to edit a shopping cart binds directly onto `CartEntity` containing `List<CartLine> lines`; `CartLine` has `productId`, `quantity`, `unitPrice`, and `sellerId`. The form only displays quantity, yet the endpoint configures no allowlist. **Problem:** a client can try binding `lines[0].unitPrice`/`sellerId`. **Fix:** accept an input DTO containing only the necessary product reference and quantity, restrict field paths, verify ownership/price in the service, and validate line count and quantity.

### Exercise 3 — Index Trap

A form has three product rows and submits `lines[0]` and `lines[2]` without `lines[1]`. Question: can you assume the list has exactly two elements? **No.** Under property binding with auto-grow, path index 2 can make the container span three slots, including an intermediate slot without full business data. Enforce contiguous indices/normalization in the UI and validate post-bind data; never rely on counting request keys as the number of received items.

## Official References

- [Spring Framework — Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): nested property paths, `BeanWrapper`, constructor and property binding.
- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): DTO design, `allowedFields`, `declarativeBinding`, and safety.
- [Spring MVC — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): input sources, constructor binding, `BindingResult`, and validation.
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): Bean Validation, errors, and method validation mechanisms.
- [Spring Framework Javadoc — `DataBinder`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): `autoGrowNestedPaths`, `autoGrowCollectionLimit`, `setAllowedFields`, and `getBindingResult`.
