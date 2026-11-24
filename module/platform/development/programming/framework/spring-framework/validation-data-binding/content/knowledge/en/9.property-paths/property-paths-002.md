# Element Indexing in Property Paths: items[0].name

When a form contains a **list of objects**, Spring Framework needs to know which element each input value belongs to and which property of that element it targets. Syntax like `items[0].name` is an **indexed property path**, used by Spring's JavaBean property access and data binding mechanisms.

For example, an order with two line items:

~~~text
items[0].name=Pen
items[0].quantity=3
items[1].name=Notebook
items[1].quantity=5
~~~

Spring can map these four name–value pairs onto an `OrderForm` object containing a `List<ItemForm>`. Each list element has `name` and `quantity` properties; the first element is selected with `[0]` and the second with `[1]`.

This lesson focuses on what the path `items[0].name` means, how the binder traverses nested objects and lists, automatic element expansion, indexed errors and validation, and measures to avoid accepting unwanted paths from requests.

## 1. Parsing the syntax items[0].name

The path has three parts:

~~~text
items[0].name
│    │   │
│    │   └── property name of the ItemForm object
│    └────── index 0, first element of the List/array
└────────── property items of the root object
~~~

If the root object is:

~~~java
public class OrderForm {
    private List<ItemForm> items;
    // getters and setters
}
~~~

and each element is:

~~~java
public class ItemForm {
    private String name;
    private Integer quantity;
    // getters and setters
}
~~~

then assigning the path `items[0].name` is equivalent in terms of **data target** to:

~~~java
order.getItems().get(0).setName("Pen");
~~~

However, when invoking the binder, Spring also handles type conversion, allowed field restrictions, intermediate object creation (if configuration supports it), and error collection; therefore binding should not be viewed as a plain Java setter call.

**Indices are 0-based** for `List` and arrays:

| Path | Target on the object |
|---|---|
| `items[0].name` | `items.get(0).getName()` |
| `items[0].quantity` | `items.get(0).getQuantity()` |
| `items[1].name` | `items.get(1).getName()` |
| `items[2].quantity` | `items.get(2).getQuantity()` |
| `items[0]` | The entire element at index 0 (when type and converter allow) |

The `.` character separates nested properties, while `[0]` selects an element in an indexable structure. For a Map, square brackets instead specify a **key**, such as `attributes[sku]` or `entries[ABC].value`; the collection type declared on the target determines how it is interpreted, not the string shape alone.

## 2. How Spring processes indexed paths

Spring's core mechanism is `BeanWrapper` (and the `PropertyAccessor` infrastructure), which can read/write simple, nested, and indexed JavaBean properties. `DataBinder` uses this mechanism during **property binding**; in Spring MVC, `WebDataBinder` commonly handles binding form/query parameters onto `@ModelAttribute`.

Typical flow for `items[1].quantity=5`:

1. Receive property name `items[1].quantity` and input value as string `"5"`.
2. Look up property `items` on `OrderForm`.
3. Access the element at index 1 in `List<ItemForm>`; when eligible, the binder auto-creates the needed elements.
4. Look up property `quantity` of the `ItemForm` at index 1.
5. Convert `"5"` into `Integer.valueOf(5)` via the type conversion infrastructure.
6. Invoke the setter or corresponding property access mechanism to assign the value.
7. If conversion/assignment fails with an error type the binder can collect, record an error in `BindingResult`, tagged with the full field name such as `items[1].quantity`.

~~~text
Form/query parameters
  "items[0].name"        = "Pen"
  "items[0].quantity"    = "3"
  "items[1].name"        = "Notebook"
  "items[1].quantity"    = "5"
             │
             ▼
           DataBinder
             │
             ▼
         OrderForm
             │
             └── items: List<ItemForm>
                    │
                    ├── [0] ItemForm
                    │       name     = "Pen"
                    │       quantity = 3
                    │
                    └── [1] ItemForm
                            name     = "Notebook"
                            quantity = 5
~~~

**This is property path syntax**, not JSONPath, database field names, general Spring Expression Language expressions, or a way to infer structure from an arbitrary string. `DataBinder` operates based on the target object's metadata, types, and configuration.

## 3. A suitable JavaBean model for binding lists

JavaBean example:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OrderForm {
    private List<ItemForm> items = new ArrayList<>();

    public List<ItemForm> getItems() {
        return items;
    }

    public void setItems(List<ItemForm> items) {
        this.items = items;
    }
}

public class ItemForm {
    private String name;
    private Integer quantity;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

The two classes above belong in **two separate Java files** if declared as top-level `public class`: `OrderForm.java` and `ItemForm.java`. The section below has a standalone program placing both types as nested classes so it can run from a single file.

Important conditions:

- The target must have a readable/writable `items` property under the chosen access mode. Standard JavaBean getters/setters work well with default property binding.
- The element type `ItemForm` needs enough information for Spring to create/access elements during auto-grow. A concrete class with a no-arg constructor is the convenient case; abstract classes, interfaces, or non-instantiable types may require different configuration.
- The generic declaration `List<ItemForm>` tells Spring the element type. A raw `List` or overly vague type makes type inference/instantiation harder.
- `Integer` can represent `null`, which is useful to distinguish an unentered or unconvertible field; `int` defaults to 0, making some missing-value situations hard to tell apart.
- Initializing `new ArrayList<>()` clarifies the initial state. If `items == null`, whether the list is auto-created depends on auto-grow configuration and type resolution.
- The binder should normally target a **dedicated input data object**, rather than directly receiving a JPA entity with many internal properties or sensitive relationships.

## 4. Runnable example: binding multiple elements with one type error

This example uses **Java 17+** and **Spring Framework 6.2.x**; the main file `IndexedBindingDemo.java` runs standalone as a program but needs Spring JARs on the classpath. Maven makes downloading compatible dependencies and executing easy.

Directory structure:

~~~text
indexed-binding-demo/
├── pom.xml
└── src/main/java/demo/IndexedBindingDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>indexed-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/IndexedBindingDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class IndexedBindingDemo {

    public static class OrderForm {
        private List<ItemForm> items = new ArrayList<>();

        public List<ItemForm> getItems() {
            return items;
        }

        public void setItems(List<ItemForm> items) {
            this.items = items;
        }
    }

    public static class ItemForm {
        private String name;
        private Integer quantity;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    public static void main(String[] args) {
        OrderForm order = new OrderForm();
        DataBinder binder = new DataBinder(order, "order");

        // Configure before binding; 10 is the maximum number of elements
        // the binder is allowed to auto-grow in this example.
        binder.setAutoGrowCollectionLimit(10);
        binder.setAllowedFields("items[*].name", "items[*].quantity");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("items[0].name", "Pen");
        input.add("items[0].quantity", "3");
        input.add("items[1].name", "Notebook");
        input.add("items[1].quantity", "abc");

        binder.bind(input);
        BindingResult result = binder.getBindingResult();

        System.out.println("items.size=" + order.getItems().size());
        System.out.println("items[0].name="
                + order.getItems().get(0).getName());
        System.out.println("items[0].quantity="
                + order.getItems().get(0).getQuantity());
        System.out.println("items[1].name="
                + order.getItems().get(1).getName());
        System.out.println("items[1].quantity="
                + order.getItems().get(1).getQuantity());

        FieldError error = result.getFieldError("items[1].quantity");
        if (error == null) {
            throw new AssertionError("Expected typeMismatch error");
        }

        System.out.println("error.field=" + error.getField());
        System.out.println("error.code=" + error.getCode());
        System.out.println("error.rejected=" + error.getRejectedValue());
        System.out.println("error.bindingFailure=" + error.isBindingFailure());
        System.out.println("field.type="
                + result.getFieldType("items[1].quantity").getName());
        System.out.println("hasErrors=" + result.hasErrors());
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.IndexedBindingDemo
~~~

Lines printed by the program:

~~~text
items.size=2
items[0].name=Pen
items[0].quantity=3
items[1].name=Notebook
items[1].quantity=null
error.field=items[1].quantity
error.code=typeMismatch
error.rejected=abc
error.bindingFailure=true
field.type=java.lang.Integer
hasErrors=true
~~~

**Why does it produce this output?**

1. The list starts empty, but `DataBinder` has auto-grow enabled in standard property binding mode. Paths to `[0]` and `[1]` cause Spring to instantiate two `ItemForm` objects.
2. `items[0].name` and `items[1].name` receive valid strings; `items[0].quantity="3"` converts to `Integer(3)`.
3. `items[1].quantity="abc"` cannot convert to `Integer`. The binder records a `FieldError` under the **exact full path** `items[1].quantity`. This field keeps its initial `null` value, while the other assigned fields retain their values.
4. `getRejectedValue()` returns `"abc"`; `getFieldType(...)` identifies the target type as `Integer.class`. These two pieces of information explain the error without turning the bad string into valid data.
5. `hasErrors() == true` means the application **must not proceed to save the order** as if the entire request were valid.

`DataBinder` in this example only performs binding and does not automatically run a validator. With Bean Validation in Spring MVC, errors such as `@NotBlank`, `@NotNull`, `@Min`, etc. can also appear after the binding step.

## 5. Auto-expanding lists: auto-grow nested paths

Spring supports **auto-grow nested paths** in property binding on a standard `DataBinder`. Given the path `items[2].name` on an empty list, the binder can expand the list up to the third element and create intermediate objects to reach property `name`.

Relevant configuration APIs:

~~~java
DataBinder binder = new DataBinder(order, "order");

binder.setAutoGrowNestedPaths(true);
binder.setAutoGrowCollectionLimit(20);
~~~

Explanation:

- `setAutoGrowNestedPaths(true)`: allows creating a default value for a `null` segment in a nested path, as well as auto-growing collection elements when accessing an index beyond the current size under supported conditions. The default on a standard `DataBinder` is `true`.
- `setAutoGrowCollectionLimit(20)`: caps how much an array/collection can auto-grow; choose this based on business rules. The default in Spring 6.x releases is 256, though you should not rely on the default as a pagination contract or product limit.
- Call configuration setters **before the binder initializes its internal binding infrastructure**, typically before `bind(...)` or `getBindingResult()`.
- Whether elements can be created also depends on list type, generic type, constructor, accessor, and initial state; this does not promise that every immutable collection, arbitrary interface, or complex entity can be auto-created.

For example, the path `items[3].name` can cause a `List` to hold four slots (indices 0–3), yet the intermediate elements are not guaranteed to hold valid data. **Do not equate "elements were created" with "the user filled in all four elements."** If an order should allow at most 20 contiguous rows, also validate size, missing elements, blank fields, and indexing policy.

### Large or unusual indices

Names such as:

~~~text
items[999999].name=...
items[-1].name=...
items[not-an-index].name=...
~~~

should not be treated as normal input for a `List`. An out-of-bounds index, invalid index, or unresolvable path can result in a property access exception or an HTTP error response depending on the binder and exception handling. **There is no guarantee that every index error becomes a `FieldError`** like `typeMismatch`.

Safe design includes:

- Setting `setAutoGrowCollectionLimit` to match the business row limit.
- Restricting fields with an allowlist, such as `items[*].name` and `items[*].quantity`; never allowing arbitrary binding to `items[*].id`, `items[*].ownerId`, or `items[*].approved` if they are server-managed fields.
- Limiting request size at the web/server layer; validating row count and index format in the API contract.
- Using simple DTO/input objects and lists with predictable index behavior; being cautious with custom collections that create elements on `get(index)`.
- Never using auto-grow as a substitute for validation: an expanded list can still be missing names, quantities, or contain invalid empty slots.

## 6. HTML forms sending indexed field names

Example of a form submitting two line items:

~~~html
<form action="/orders" method="post">
  <div>
    <input name="items[0].name" value="Pen">
    <input name="items[0].quantity" type="number" value="3">
  </div>
  <div>
    <input name="items[1].name" value="Notebook">
    <input name="items[1].quantity" type="number" value="5">
  </div>
  <button type="submit">Submit order</button>
</form>
~~~

This is an **HTML snippet illustrating parameter names**; a real application also needs a CSRF token if CSRF protection is enabled, error UI, validation, and an appropriate request submission policy.

Browsers send field names such as `items[0].name`; in `application/x-www-form-urlencoded`, bracket characters may be percent-encoded over HTTP. Once Spring MVC receives the decoded parameter names, `WebDataBinder` can use them as `@ModelAttribute` property paths.

When rendering dynamic forms, the application needs to generate explicit indexed `name` attributes for each row. A 5-element list **does not guarantee** contiguous indices 0–4 if the user deletes or inserts rows in the browser without renumbering.

For example, when deleting a middle row:

~~~text
items[0].name=Pen
items[2].name=Ruler
~~~

The server might have to deal with an auto-created element at `[1]` lacking data. Depending on the contract, the frontend should renumber sequentially as 0,1 or the backend should explicitly accept row IDs and define how missing rows are handled. Never rely on indices as durable record identities.

## 7. In Spring MVC with @ModelAttribute and BindingResult

An MVC controller for a list of items can receive a form structured like this:

~~~java
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class OrderController {

    @InitBinder("order")
    void initOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "items[*].name",
                "items[*].quantity");
        binder.setAutoGrowCollectionLimit(20);
    }

    @PostMapping("/orders")
    String submit(
            @Valid @ModelAttribute("order") OrderForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "orders/form";
        }

        // Only call the service here after business checks.
        return "orders/confirmation";
    }
}
~~~

This is **code intended for integration into a Spring MVC application**, using a compatible `OrderForm` from section 3, with corresponding view templates, web configuration, and services. It is not a standalone `javac` program.

Key points to understand:

- `@ModelAttribute("order")`: Spring creates/retrieves the form object and binds request data to properties, including `items[0].name`.
- `@InitBinder("order")`: configures the binder for the model attribute named `order`, restricting bindable fields and collection auto-growth.
- `@Valid`: triggers validation when an appropriate provider and annotations/constraints are present; it does not ensure list items are checked unless the DTO declares cascade validation.
- `BindingResult` must appear **immediately after** the model attribute parameter it describes so the method can handle binding/validation errors.
- When a quantity has the wrong type, the error typically uses the full path `items[1].quantity`, allowing the view to highlight the exact location.
- Successfully bound values on other rows may still be present in `form`; errors must be handled before saving.

**Scope:** The approach above is **property binding** for `@ModelAttribute`. With `@RequestBody` JSON, Jackson/HTTP message conversion handles creating objects from JSON and parse/deserialization errors through a different mechanism. A JSON array `{"items":[{"name":"Pen"}]}` does not carry literal `items[0].name` keys in the form-url-encoded sense, even though the resulting Java object has the same structure.

## 8. Per-element validation and indexed error names

A real form may need to ensure each row has a non-blank name and a positive quantity. Bean Validation uses cascade validation to traverse from the form into the elements.

Example **DTO additions for Spring MVC integration**, requiring the Jakarta Validation API and a provider (Spring Boot typically uses the validation starter):

~~~java
import java.util.ArrayList;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class OrderForm {
    @NotEmpty
    @Size(max = 20)
    @Valid
    private List<ItemForm> items = new ArrayList<>();

    public List<ItemForm> getItems() {
        return items;
    }

    public void setItems(List<ItemForm> items) {
        this.items = items;
    }
}

public class ItemForm {
    @NotBlank
    @Size(max = 100)
    private String name;

    @NotNull
    @Min(1)
    @Max(1000)
    private Integer quantity;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

The two `public class` definitions here belong in **two separate Java files**. The `@Valid` annotation on the list property requests cascading into each `ItemForm`; `@NotBlank`, `@NotNull`, `@Min`, `@Max` define per-row rules. Placing `@Size(max = 20)` is a business check **after binding**, not a replacement for `setAutoGrowCollectionLimit(20)` to cap expansion while processing property paths.

Example of two cases:

- `items[1].quantity=abc`: type conversion error, typically with code `typeMismatch`, `FieldError.getField()` as `items[1].quantity`, and `isBindingFailure()` as `true`.
- `items[1].quantity=0`: converts to `Integer(0)` successfully, but `@Min(1)` rejects it. The validation error can be recorded under the same path `items[1].quantity` with a code like `Min`.

To read and display errors:

~~~java
if (errors.hasErrors()) {
    for (var fieldError : errors.getFieldErrors()) {
        String path = fieldError.getField();
        String code = fieldError.getCode();

        // path can be "items[1].quantity".
        // Translate code into a user-friendly and safe message.
    }
}
~~~

Do not assume every error belongs to `items[*]`: `BindingResult` can also contain an overall error from `@NotEmpty` on `items`, errors on other fields, or an `ObjectError`. When all errors are needed, inspect `getAllErrors()` and distinguish field errors from object-level errors.

## 9. Reading errors and values by exact path

For an error on the second element, pass the **exact full path**:

~~~java
String field = "items[1].quantity";

boolean invalid = result.hasFieldErrors(field);
var error = result.getFieldError(field);

if (error != null) {
    Object rejected = error.getRejectedValue();
    boolean bindingFailed = error.isBindingFailure();
}

Class<?> expectedType = result.getFieldType(field);
Object displayValue = result.getFieldValue(field);
~~~

APIs in the example:

| API | Meaning |
|---|---|
| `hasFieldErrors("items[1].quantity")` | Whether an error is recorded for the quantity field at index 1 |
| `getFieldError("items[1].quantity")` | First error for that field, may be `null` |
| `getFieldErrors("items[1].quantity")` | All errors associated with that field |
| `getFieldType("items[1].quantity")` | Target Java property type if resolvable (in the example: `Integer.class`) |
| `getFieldValue("items[1].quantity")` | Value for error reporting/display; on binding failure this can be the rejected string |
| `FieldError.getRejectedValue()` | The value rejected by that specific error, e.g., `"abc"` |
| `FieldError.isBindingFailure()` | Distinguishes binding failures from validation errors in many standard cases |

For an unconvertible quantity, `order.getItems().get(1).getQuantity()` may be `null` or the previous value, while `getFieldValue("items[1].quantity")` still reflects the rejected input for re-rendering the form. Never inspect the target value and conclude the user submitted `null`.

**If an index does not actually exist**, calling property access by path may fail to read, return an undefined result, or throw an exception depending on implementation and form state. Do not use field-value lookup APIs to probe arbitrary unbounded indices from a request. For collected errors, iterate directly over `getFieldErrors()`.

## 10. Related property path forms

| Example | Access form | Notes |
|---|---|---|
| `customer.name` | Nested property | No index; `customer` must be readable/creatable |
| `items[0].name` | Property of the first `List`/array element | Index 0 is the first element |
| `items[1].quantity` | Property of the second element | May need conversion to a number |
| `items[0].options[2].code` | Nested path with two index levels | Requires both collections and intermediate objects to be usable |
| `attributes[locale]` | Map value by key `locale` | Does not mean the `locale`-th element |
| `matrix[1][2]` | Multi-indexed access | Depends on data types and accessors |
| `items[*].name` | Wildcard pattern when configuring `allowedFields` | **Not** a property path targeting a specific element for assignment |

The last point is especially important: `items[*].name` in `setAllowedFields` is a **pattern permitting multiple field names** such as `items[0].name` and `items[19].name`; it does not mean Spring will automatically bind a single value onto all elements. For a submitted value, the key must still carry a concrete index.

In Spring MVC declarations, source data may also arrive in an `items` property of JSON, or a constructor-bound record containing `List<Item>`. These approaches can produce the same Java outcome but have **different mapping mechanisms, error rules, and input controls**. Do not equate every technique with `DataBinder.bind(PropertyValues)`.

## 11. Dynamic indices: adding, deleting, reordering, and element identity

When the user adds a new row, the frontend might generate names:

~~~text
items[2].name=Eraser
items[2].quantity=2
~~~

if rows with indices 0 and 1 already exist. On deletion, frontends typically renumber contiguously before submitting. If not renumbered, clear server-side rules are needed for gaps.

**An index only describes a position in the request**, not a business ID. If a saved order has its own `orderLineId`, index `[1]` can change whenever the user drags and reorders rows. The server should never rely solely on `[1]` to determine which record the user is authorized to modify, delete, or own.

For updates with identities:

- Accept a list of DTOs containing only the fields the client is allowed to supply.
- If the client must send row IDs, verify each ID belongs to the current order and that the user is authorized to act on it.
- Define semantics for missing rows, added rows, deleted rows, and new ordering.
- Check for duplicate IDs, duplicate positions, or row counts exceeding business limits.
- Choose between full-list replacement and partial updates via an explicit API contract; avoid binding input directly into JPA relationships without reconciling records.

Similarly, if a request only contains `items[4].name`, the binder may have to create slots 0–4 depending on configuration. Validate the resulting list and enforce an index policy, rather than treating it as five validly completed rows.

## 12. Security and resource limits of indexed binding

Indexed property paths are useful, yet they also allow clients to request deep traversal into a data structure. Risks must be controlled right at the input boundary.

### 12.1. Mass assignment via nested paths

Suppose an entity has server-controlled `items[0].priceApproved` or `items[0].ownerId`. If the entity is used directly as the form object, a client can try sending:

~~~text
items[0].name=Pen
items[0].ownerId=999
items[0].approved=true
~~~

Use a request DTO containing only allowed fields, plus `allowedFields` for property binding:

~~~java
binder.setAllowedFields("items[*].name", "items[*].quantity");
~~~

Fields excluded by the allowlist can be inspected via `BindingResult.getSuppressedFields()`; they **do not necessarily** produce a regular `FieldError`. If policy requires rejecting requests containing forbidden fields, handle suppressed fields explicitly.

### 12.2. Excessive collection growth

A name like `items[1000000].name` can lead to high memory consumption or property access errors if unbounded. Configure a small auto-grow limit fitting business needs, while also limiting request size and validating row count. Do not assume `setAutoGrowCollectionLimit` alone handles every custom collection or constructor-binding case differently from property binding.

### 12.3. Very deep paths or special collections

Complex nested property paths like `items[0].components[0].parts[0]...` increase resolution cost and error risk on unexpected data. Design shallow, purpose-built form DTOs; do not allow arbitrary deep traversal into sensitive domain objects. Keep track of security patches for data binding in the Spring version you use.

### 12.4. Validation and authorization are two different things

`@NotBlank` on `items[0].name` only checks value quality; it does not prove the caller is allowed to edit an existing item. The service must verify permissions on the resource and each element whenever data involves ownership, transactions, or assets.

## 13. Common mistakes and fixes

**Missing suitable getters/setters.** The binder cannot read/write `items` or `name` in JavaBean mode. Check types, accessors, and whether direct field access is enabled; do not assume private fields bind automatically via property access.

**List with a non-instantiable element type.** With `List<ItemInterface>` or an abstract type, auto-grow may not know which concrete element to instantiate. Choose a concrete DTO, pre-initialize elements, or design a suitable binding approach.

**Mistaking `items[1]` for the first element.** Index 1 is the second element. Check how `name` attributes are generated on the form.

**Gaps in indices.** A client sends `items[0]` and `items[3]`, leaving intermediate elements with missing data or errors. Renumber or explicitly check for gaps per contract.

**Setting `setAutoGrowCollectionLimit` too late.** Set it before binding and before the binder creates its result/property access infrastructure; never change configuration mid-request.

**Expecting `getFieldError("quantity")` to catch errors on every element.** Errors on `items[1].quantity` carry the full field name. Iterate `getFieldErrors()` or query the exact path; do not drop the collection name and index.

**Assuming invalid index errors always become FieldErrors.** An invalid property path or out-of-bounds index can throw an exception. Control inputs and handle HTTP errors consistently.

**Using `items[*].name` as a request parameter.** `*` is only a wildcard in allowlist patterns; data parameters need an actual index like `items[0].name`.

**Forgetting cascade validation.** With `@Valid` only on the controller without requesting validation of each `ItemForm`, item-level constraints may never run. Place `@Valid` on the list/element according to the bean structure and Bean Validation provider in use.

**Believing successful binding means valid data.** A quantity of `0` can convert successfully yet still violate `@Min(1)`; check both binding and validation before saving.

## 14. Essential test cases

With `DataBinder` and Spring MVC, test the following scenarios:

| Test | Expected result |
|---|---|
| Form with valid `items[0].name` and `items[0].quantity` | Creates first element, assigns correct name and number |
| `items[1].name` on an initially empty list | Auto-grows when configuration allows and element type is instantiable |
| `items[1].quantity=abc` | `FieldError` attached to `items[1].quantity`, rejected `abc`, other valid fields bound |
| `items[0].quantity=0`, with `@Min(1)` | Binding succeeds, but validation rejects it |
| `items[0].name` blank, with `@NotBlank` | Validation pinpoints the field at index 0 |
| Index exceeding auto-grow limit | Rejected/exception as appropriate; does not allocate huge element count |
| Sending `items[0].ownerId` in a restricted form | Field is not assigned; may be recorded in suppressed fields |
| Sending gapped indices `[0]`, `[3]` | Missing-data elements detected per contract |
| Sending rows exceeding quota | Request rejected per documented limit |
| Reordering saved rows | Request index is never treated as stable entity ID |
| Form with errors | Service is not called to save or cause side effects |

For `MockMvc`, pass parameters with the exact syntax:

~~~java
mockMvc.perform(post("/orders")
        .param("items[0].name", "Pen")
        .param("items[0].quantity", "3")
        .param("items[1].name", "Notebook")
        .param("items[1].quantity", "abc"))
    .andExpect(model().attributeHasFieldErrors(
            "order", "items[1].quantity"));
~~~

This `MockMvc` snippet is an **illustration inside an already configured Spring MVC test**, requiring static imports `post`, `model`, and corresponding controller/view setup. It does not run standalone with `javac` like the program in section 4.

## 15. Takeaways

- `items[0].name` is an **indexed property path**: navigate to property `items`, get element at index 0, then access property `name`.
- For `List` and arrays, indices are 0-based; for `Map`, the content inside `[...]` is a key and must be interpreted according to the target type.
- Spring `DataBinder`/`WebDataBinder` can use these paths to bind form/query inputs onto lists of JavaBeans, perform type conversion, and collect errors under full field names.
- Auto-grow makes dynamic forms convenient but requires **size limits, property allowlists, dedicated DTOs, and validation**.
- Errors or validation failures on `items[1].quantity` should be displayed on the right element. An error on one row neither proves the whole list valid nor invalidates every other bound value.
- **An index is a position in the payload, not a durable identity for a data row**; for updates, the backend must verify permissions and the real identity of each element.

### Official documentation for further reading

- Spring Framework Reference: Data Binding; sections Property Binding with BeanWrapper and Setting and Getting Basic and Nested Properties.
- Spring Framework Reference: Spring MVC Data Binding; sections Allowed Fields and Model Design.
- Spring Framework Javadoc: `DataBinder`, `BeanWrapper`, `BindingResult`, `FieldError`.
- Spring Framework Reference: Validation and Handling Form Submission in Spring MVC.
