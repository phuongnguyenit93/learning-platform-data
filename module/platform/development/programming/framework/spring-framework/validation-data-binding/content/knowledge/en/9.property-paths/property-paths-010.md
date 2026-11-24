# Limiting Depth, Indices, and Element Counts from Untrusted Data

In Spring Framework, a form parameter name can be a **property path**, not just a single flat field name. For example, `customer.name` navigates into a nested object, while `items[2].quantity` accesses the third element of a list. Whenever a request sender controls the path, the application must treat **both the parameter name and its value as untrusted data**.

A path like `items[999999].quantity` can cause binding to try expanding a huge collection if unbounded; a deeply nested path can trigger deep traversal or many object instantiations; thousands of parameters can inflate parsing, conversion, and validation costs. Beyond resource risks, a path like `account.admin` also creates a **mass assignment** risk if the target exposes writable properties not meant for users.

This lesson distinguishes **path depth**, **element index**, **collection element count**, and **input volume/size**, and applies appropriate defensive layers across `BeanWrapper`, `DataBinder`, and Spring MVC. Examples use Java 17+ and Spring Framework 6.2.x.

## 1. Property paths: a single string can traverse many objects

Spring supports path forms following JavaBeans conventions:

| Path | Meaning | What to control |
| --- | --- | --- |
| `name` | Property on the main target | Is this property name allowed to bind? |
| `profile.address.city` | Traverses two intermediate objects | Depth and intermediate object instantiation |
| `items[0].quantity` | Property of element at index 0 | Is this index within the accepted set? |
| `items[150].quantity` | Element at index 150 | Should auto-grow run? Maximum allocation limit? |
| `attributes[channel]` | Map value at key `channel` | Is this key allowed? How many entries can the Map grow to? |
| `sections[0].lines[1].price` | Multi-level collections | Cap depth, per-level indices, and total objects simultaneously |

Property binding flow can be visualized as:

```text
HTTP/form input:
  "items[1].quantity" -> "3"
                  |
                  v
             WebDataBinder
                  |
          check allowedFields
                  |
         parse property path
                  |
      target.getItems() -> index 1
                  |
     (may auto-grow collection)
                  |
    item.setQuantity(convert("3"))
                  |
             BindingResult
```

**The value `"3"` is data, yet the name `"items[1].quantity"` is also data.** Restricting the type of `quantity` or adding `@Min(1)` is not enough to control which objects get instantiated and which fields get modified during binding.

For a UI-backed request, valid form parameters are usually known in advance. The server can enforce a rule: permit only `customer`, `items[0..2].sku`, and `items[0..2].quantity`. Any path outside that scope is rejected even if the target has getters/setters for it.

## 2. Four distinct limit dimensions to separate

**Depth** is how many object/collection levels a path can traverse. For example, `customer.name` has one nesting hop, whereas `order.buyer.address.country.code` has several. Depth matters whenever dynamic paths or dynamically constructed object graphs are accepted.

**Index** is a specific position like `items[2]`. A large index can create sparse gaps, trigger auto-grow, or access out of bounds; it must be checked per collection, not just by total string length.

**Element count** is the actual collection size accepted by business rules. Index limits are part of this, yet do not cover Map entry counts, pre-existing elements, nested sublists, or JSON items.

**Input size** covers parameter counts, repeated values per name, request byte size, and string/JSON payload size. Binder limits do not stop the servlet container or JSON parser from spending resources **before the binder is even invoked**.

Example policy for a hypothetical order form:

| Control dimension | Example application policy | Where to enforce? |
| --- | --- | --- |
| Allowed paths | `customer`, `items[0..2].sku`, `items[0..2].quantity` | Allowlist / input name check |
| Depth | No path deeper than 2 levels like `items[i].quantity` | Schema/allowlist or dedicated path parser |
| Index | Only 0, 1, 2 for `items` | Per-index allowlist + auto-grow config |
| Element count | At most 3 items | Binding limits + validation contract |
| Parameter count | At most 7 form parameter names | HTTP layer and request inspection |
| Body size | Appropriate for form type and expected load | Server/gateway/web container |
| Strings and values | `sku` within an appropriate max length | Parsing/validation before business processing |

The numbers above are **only examples of an API contract**, not defaults enforced by Spring across every application.

## 3. Understanding DataBinder auto-grow accurately

`org.springframework.validation.DataBinder` can traverse nested paths and auto-create values when needed for property binding. Key APIs:

```java
binder.setAutoGrowNestedPaths(true);
binder.setAutoGrowCollectionLimit(3);
```

On a standard `DataBinder` in Spring Framework 6.2:

- `setAutoGrowNestedPaths(boolean)` controls attempting to instantiate a value for a `null` nested path and auto-growing collection elements when accessing an index past existing elements. The default is normally `true`.
- `setAutoGrowCollectionLimit(int)` specifies the **maximum auto-expansion** for arrays/collections during property binding; the default is **256** (constant `DEFAULT_AUTO_GROW_COLLECTION_LIMIT`).
- Both settings apply to the setter/field-access property binding branch of `DataBinder`. Do not treat them as a universal cap for **constructor binding** via `construct(...)`.
- Auto-grow succeeds only when Spring can resolve the child type/instantiation path. Abstract types, missing constructors, unsuitable collections, or invalid paths can still fail.

For example, `items` starts with 0 elements and the request sends `items[2].quantity`. If auto-grow is enabled, the element type is instantiable, and the limit allows it, Spring can expand the list up to index 2. Change it to `items[999999].quantity` and it **must not** allocate one million elements; `setAutoGrowCollectionLimit(3)` caps auto-expansion in that branch.

**This limit does not mean "the list always has at most 3 elements."** If the list already received 20 elements elsewhere, the auto-grow limit does not truncate it to 3. Nor does it cap entry counts in every Map, total objects across multiple collections, or HTTP parameter counts.

Do not handle limit-exceeded errors by raising the default 256 to a huge number. Ask what business logic actually needs first: if the UI allows at most 3 rows, an auto-grow limit of 3 or lower makes sense; if importing tens of thousands of rows is needed, use a batch import workflow with dedicated quotas instead of form binding with arbitrary indices.

### How are BeanWrapper limits different?

`BeanWrapperImpl` can configure `setAutoGrowNestedPaths(...)` and `setAutoGrowCollectionLimit(...)` when accessing properties directly. Standard `DataBinder` uses this property access mechanism underneath and exposes corresponding configuration methods.

However, if code manually calls `beanWrapper.getPropertyValue(path)` or `setPropertyValue(path, value)`, no request security layer appears automatically. The caller must still validate path legality, authorization, and input source. Whenever property names are known at compile time, calling getters/setters directly is safer and easier to control than evaluating user-supplied paths.

## 4. Three path-control layers when binding HTTP data

### Layer 1: Design a tightly scoped target

Use a **DTO/command object** containing only data the form is permitted to accept. Avoid binding directly onto entities holding `id`, `ownerId`, `role`, `approved`, `price`, `admin`, or internal properties. Having a setter does not mean clients are allowed to change it.

For example, an address edit form only needs `street`, `city`, and `postalCode`. Checking whether the user is authorized to edit that address is the controller/service's responsibility, not `BeanWrapper`'s.

For immutable data, **constructor binding** can shrink the property-binding surface. Spring Framework 6.1+ provides `binder.setDeclarativeBinding(true)`: by default only declared values are used for constructor binding, while property binding runs only if `allowedFields` is set. This explicitly selects the binding source rather than capping request bytes, overall depth, or business permissions.

### Layer 2: Allowlist only truly permitted property paths

When property binding is needed, configure:

```java
binder.setAllowedFields(
        "customer",
        "items[0].sku", "items[0].quantity",
        "items[1].sku", "items[1].quantity",
        "items[2].sku", "items[2].quantity"
);
```

Under this contract:

- `items[1].quantity` is valid if target/type permits.
- `items[3].quantity` is **not in the allowlist**, even though its path syntax is valid.
- `items[1].price` is invalid even if the class has `setPrice(...)`.
- `account.admin` is invalid even if the object graph contains that property.
- `items[0].details.owner.role` is invalid because the path goes deeper than the contract.

Spring supports wildcards in `allowedFields`, such as `items[*].quantity`. This is convenient when indices vary, yet **wildcards themselves do not cap indices or element counts**; combine them with an appropriate auto-grow limit and boundary checks on indices/keys. For small forms with fixed slots, enumerating exact paths is easier to verify than wildcards.

There is `setDisallowedFields(...)`, though denylisting easily misses new or nested fields. For untrusted input, prefer **allowedFields** or a constructor/DTO structure declaring only genuinely needed inputs.

### Layer 3: Cap auto-grow and input size

```java
binder.setAutoGrowCollectionLimit(3);
binder.setAutoGrowNestedPaths(true);
```

Pick a collection limit close to actual needs and pair it with **parameter/body limits at the HTTP layer**. If the form's object graph is already pre-initialized, consider `setAutoGrowNestedPaths(false)` and test binding carefully: turning auto-grow off stops creating null nodes, yet does not block paths traversing already-existing nodes.

These control layers complement one another. The allowlist blocks unwanted properties before touching the collection; the auto-grow limit prevents excessive allocation for paths to non-existent indices; the HTTP layer cuts parsing overhead before binding.

## 5. Runnable Java 17+ example: capping indices with allowlist and auto-grow

This example builds a form with a list of line items. Requirement: at most three slots `items[0]`, `items[1]`, `items[2]`, allowing only `customer`, `sku`, and `quantity`. We **intentionally** include an `admin` field on the form to observe an unwanted request being blocked by `allowedFields`; in a real app, omit sensitive fields from the DTO altogether.

Create the Maven structure:

```text
safe-path-binding/
├── pom.xml
└── src/main/java/SafePathBindingDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>safe-path-binding</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/SafePathBindingDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class SafePathBindingDemo {

    public static class Item {
        private String sku;
        private int quantity;

        public Item() {}

        public String getSku() { return sku; }
        public void setSku(String sku) { this.sku = sku; }

        public int getQuantity() { return quantity; }
        public void setQuantity(int quantity) { this.quantity = quantity; }
    }

    public static class OrderForm {
        private String customer;
        private List<Item> items = new ArrayList<>();
        // Used solely to demonstrate that the allowlist blocks sensitive fields.
        private boolean admin;

        public OrderForm() {}

        public String getCustomer() { return customer; }
        public void setCustomer(String customer) { this.customer = customer; }

        public List<Item> getItems() { return items; }
        public void setItems(List<Item> items) { this.items = items; }

        public boolean isAdmin() { return admin; }
        public void setAdmin(boolean admin) { this.admin = admin; }
    }

    private static DataBinder newBinder(OrderForm target) {
        DataBinder binder = new DataBinder(target, "order");
        binder.setAutoGrowNestedPaths(true);
        binder.setAutoGrowCollectionLimit(3);

        // Accept only paths belonging to the form contract.
        binder.setAllowedFields(
                "customer",
                "items[0].sku", "items[0].quantity",
                "items[1].sku", "items[1].quantity",
                "items[2].sku", "items[2].quantity"
        );
        binder.setDeclarativeBinding(true);
        return binder;
    }

    public static void main(String[] args) {
        OrderForm normal = new OrderForm();
        DataBinder normalBinder = newBinder(normal);

        MutablePropertyValues validInput = new MutablePropertyValues();
        validInput.add("customer", "An");
        validInput.add("items[1].sku", "BK-2");
        validInput.add("items[1].quantity", "2");
        normalBinder.bind(validInput);

        BindingResult normalResult = normalBinder.getBindingResult();
        System.out.println("customer=" + normal.getCustomer());
        System.out.println("items.size=" + normal.getItems().size());
        System.out.println("item1.sku=" + normal.getItems().get(1).getSku());
        System.out.println("item1.quantity=" +
                normal.getItems().get(1).getQuantity());
        System.out.println("normal.errors=" + normalResult.getErrorCount());

        // Another request attempting to access a huge index and an internal field.
        OrderForm attempted = new OrderForm();
        DataBinder attemptedBinder = newBinder(attempted);

        MutablePropertyValues untrustedInput = new MutablePropertyValues();
        untrustedInput.add("items[999999].quantity", "20");
        untrustedInput.add("admin", "true");
        attemptedBinder.bind(untrustedInput);

        BindingResult attemptedResult = attemptedBinder.getBindingResult();
        List<String> suppressed =
                Arrays.asList(attemptedResult.getSuppressedFields());

        System.out.println("suppressed.index=" +
                suppressed.contains("items[999999].quantity"));
        System.out.println("suppressed.admin=" +
                suppressed.contains("admin"));
        System.out.println("attempted.items.size=" +
                attempted.getItems().size());
        System.out.println("attempted.admin=" + attempted.isAdmin());
        System.out.println("attempted.errors=" +
                attemptedResult.getErrorCount());
    }
}
```

Run from the `safe-path-binding` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=SafePathBindingDemo
```

Expected output from `System.out.println` statements:

```text
customer=An
items.size=2
item1.sku=BK-2
item1.quantity=2
normal.errors=0
suppressed.index=true
suppressed.admin=true
attempted.items.size=0
attempted.admin=false
attempted.errors=0
```

**Output analysis:**

1. `items[1]` is valid and auto-grown: since `items` starts empty, Spring creates enough elements to reach index 1. `Item` is a public class with a no-arg constructor and matching setters.
2. `"2"` converts to `int 2` before invoking `setQuantity(...)`.
3. `items[999999].quantity` is outside the allowlist, so it is **suppressed**; the request never triggers expanding the collection to that index.
4. `admin=true` is also suppressed even though the demo target has `setAdmin(...)`. Real applications should omit sensitive fields from form DTOs altogether.
5. `attemptedResult.getSuppressedFields()` records field names dropped by the allowed/disallowed policy. `attemptedResult.getErrorCount()` stays 0: **suppressed fields do not become `FieldError`s by default!**

The example highlights two distinct controls: blocking unwanted paths and keeping the auto-grow limit small. To verify the auto-grow limit **without** the allowlist blocking first, write a separate test where an index matches an allowed pattern yet exceeds the limit; never use such unprotected binding on real data.

### Do not silently accept suppressed fields

An application can choose to return a client error when a request contains out-of-contract fields:

```java
BindingResult result = binder.getBindingResult();

if (result.getSuppressedFields().length > 0) {
    throw new IllegalArgumentException(
            "Request contains a property that is not allowed to be updated");
}
if (result.hasErrors()) {
    // Return structured binding/validation errors to the user.
}
```

This is **a handler fragment inside a program with a binder**, not standalone runnable code. In Spring MVC, translate it into a 4xx response with an appropriate error DTO. Avoid exposing raw paths or sensitive input values publicly if that leaks internal structure or data.

**Important:** when calling `bind(...)`, valid fields may already have been assigned before a suppressed field is inspected. If you must prevent any entity mutation when a request is rejected, **bind onto an isolated DTO** and transfer to domain/service objects only after all checks PASS. `DataBinder` does not roll back multiple setter calls.

## 6. Depth limits do not have a single global switch

`setAutoGrowCollectionLimit` caps **collection auto-growth**, not `setMaxPropertyPathDepth`. In common `DataBinder`/`BeanWrapper` APIs of Spring Framework 6.2, do not assume a built-in global setting automatically blocks any path deeper than N hops. The framework can traverse nested properties as deep as the object graph and access paths permit.

If a form needs only `customer` and `items[i].quantity`, an **exact full-path** allowlist naturally establishes a useful depth boundary. A path like `items[0].detail.owner.profile.secret` will not match.

When an application genuinely must allow dynamic schemas, design a **tested path parser/canonicalizer** enforcing all of the following together:

- List of allowed property/segment names.
- Maximum number of segments or nested-object hops.
- Every index must be a non-negative integer bounded below an appropriate length/quota.
- Maximum number of indexed collection levels and Map entries.
- Valid Map keys per contract, unable to expand object graphs arbitrarily.
- Maximum total path string length and maximum distinct paths per request.
- Reject alternative encodings/forms trying to bypass policy.

**Never build a security filter by calling `path.split("\\.")` and counting dots.** Paths can contain `[...]` syntax, Map keys, or special characters; counting dots miscounts indexed levels and can diverge from how Spring parses paths. For fixed-schema forms, an **exact path allowlist** is far more reliable than a custom parser.

Example policy permitting only these exact names:

```text
customer
items[0].sku
items[0].quantity
items[1].sku
items[1].quantity
items[2].sku
items[2].quantity
```

Regardless of path length or dot count, any name outside this set is rejected. When adding new fields, update the contract, tests, and policy together; avoid broad wildcards like `*` as a "quick fix."

## 7. Index limits and element-count limits are not the same thing

Suppose a collection auto-grows to index 2; the Java list normally has at least 3 slots (0, 1, 2). However, the number of genuinely meaningful business elements does not necessarily equal the list size: some elements may be blank/default-initialized objects created by auto-grow.

Distinguish:

- **Maximum allowed index:** with three slots, valid indices are 0, 1, 2. Never assume index 3 is valid just because "max count is 3."
- **Allocated element count:** auto-growing from an empty list to index 2 creates intermediate elements.
- **Business item count:** items with valid `sku` and `quantity`, possibly requiring no "holes" at index 0 or 1.
- **Total across collections:** three lines per group still lets a request sending hundreds of groups create huge item totals unless group count is capped too.
- **Map entry count:** Maps use keys, not integer indices in the same way; array/list auto-grow limits do not enforce at most 3 Map entries.

For instance, a request sending only `items[2].quantity=3` should not blindly be treated as an order with one valid item. A validator should require "no empty slots before entered items," or the server should build the list from a bounded input structure.

To enforce **business rules** on collections, Jakarta Bean Validation can use:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import java.util.List;

public class OrderForm {
    @Size(max = 3)
    @Valid
    private List<ItemForm> items;

    // Getters/setters when using property binding.
}
```

This is an illustrative model snippet requiring `ItemForm` and a validation provider. `@Size(max = 3)` checks the resulting list after binding/construction, and `@Valid` validates nested elements when triggered. **It does not stop allocations from happening before validation**. Thus `@Size` complements auto-grow and request limits rather than replacing them.

### Total element count matters with multiple nested collections

Suppose a payload allows 50 groups with 50 items each. Even though each list's index is below 50, total elements can reach 2,500. As depth rises, allocation, conversion, and validation costs grow rapidly with total node count.

Therefore, alongside per-list max indices, define quotas for **total items per request**, group count, children per group, body bytes, and string lengths. Enforce quotas before materializing a huge graph, or during parsing where supported, rather than waiting until the service layer after objects are built.

## 8. Capping parameter counts and body size at the HTTP boundary

`DataBinder` runs after a request has already passed through parts of the HTTP stack. With form encoding like `application/x-www-form-urlencoded`, the servlet container may parse parameter names/values before a Spring controller sees them. Even if `setAllowedFields` drops 10,000 unknown paths, the server may already have spent CPU and memory parsing them.

For HTTP APIs, policies should include:

1. Cap **request body size** (at reverse proxy, gateway, container, or server layer).
2. Cap **parseable parameter count** and, where applicable, repeated values per parameter name.
3. Cap field/path lengths and input object entry counts.
4. Configure request timeouts and concurrency limits suited to application capacity.
5. Reject over-quota requests early with appropriate responses (typically 4xx, e.g., 413 when body size is exceeded).
6. Use sanitized telemetry/logs to observe quota rejections without logging raw sensitive payloads.

Exact HTTP configuration property names differ across **Servlet containers** (Tomcat, Jetty, Undertow), **Spring Boot versions**, reverse proxies, and deployment setups. Read the docs for your actual stack before setting values. Avoid assuming one universal Boot property limits every request type.

**Do not forget duplicate parameter names:** a `Map<String, String>` in demo code loses information if a key appears multiple times. The HTTP layer can receive multiple values per name; policies must consider value counts and selection/merging behavior, not just `map.size()`.

## 9. Configuring in Spring MVC with @InitBinder

The snippet below shows applying the policy directly to model attribute `order`:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("order")
void initOrderBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAutoGrowNestedPaths(true);
    binder.setAutoGrowCollectionLimit(3);

    binder.setAllowedFields(
            "customer",
            "items[0].sku", "items[0].quantity",
            "items[1].sku", "items[1].quantity",
            "items[2].sku", "items[2].quantity"
    );
}
```

This is a **method belonging to an appropriately scoped Spring MVC controller or controller advice**, not a standalone program. `@InitBinder("order")` applies settings to the model attribute named `order`. The controller signature can look like:

```java
@PostMapping("/orders")
String submit(
        @Valid @ModelAttribute("order") OrderForm order,
        BindingResult errors) {

    if (errors.getSuppressedFields().length > 0) {
        // Reject requests containing out-of-contract fields.
        return "bad-request";
    }
    if (errors.hasErrors()) {
        return "order-form";
    }

    // After input is valid, pass the DTO to the business service.
    return "order-success";
}
```

This is an **illustrative integration snippet**; an app needs Spring MVC and Jakarta Validation imports, an `OrderForm` definition, templates/views, and proper HTTP status handling. `return "bad-request"` in the example is just a view name: to return a true **HTTP 400**, set status via an appropriate MVC mechanism such as `ResponseStatusException(HttpStatus.BAD_REQUEST)` or `ResponseEntity` in an API controller.

**`BindingResult` must immediately follow its model attribute parameter**. If the target contains other disallowed fields, `allowedFields` blocks them during property binding. With constructor binding, design DTOs/constructors declaring only needed values; `DataBinder`'s `autoGrowCollectionLimit` does not automatically become a constructor-binding quota. Processing is truly safe only when every layer of the input pipeline is checked.

When using `@ControllerAdvice` for shared configuration, remember every form in scope may have a different contract. Never apply one broad allowed-fields list across all controllers if each form expects different paths.

## 10. Constructor binding and @RequestBody JSON take different paths

Paths like `items[2].quantity` typically relate to **form/query parameter property binding**, yet Spring also supports **constructor binding** onto immutable objects and **JSON deserialization** via HTTP message converters. Each mechanism must be controlled in the right place.

| Entry path | Typical mechanism | Limits to verify |
| --- | --- | --- |
| `@ModelAttribute` mutable DTO | `WebDataBinder` property binding | `allowedFields`, auto-grow, input count/size, DTO |
| `@ModelAttribute` immutable DTO/record | Constructor binding | Constructor schema, value count, indexed args, separate input/collection quotas |
| `@RequestBody` JSON | HTTP message converter (usually Jackson) | Body size, parser/deserializer constraints, DTO shape, collection size, validation |
| Application code calling `BeanWrapper` | Direct property access | Caller must validate path/index/permissions before calling |

JSON example:

```json
{
  "customer": "An",
  "items": [
    {"sku": "BK-2", "quantity": 2}
  ]
}
```

With `@RequestBody`, Jackson normally builds `items` from a JSON array, **not** via `WebDataBinder.setAutoGrowCollectionLimit(3)` from the form example. If JSON contains an oversized or deeply nested array, configure read/deserializer/body limits on the JSON stack plus DTO constraints. A validator checking `@Size(max=3)` after deserialization does not stop earlier steps from allocating a huge array.

Constructor binding with indexed parameters can also build lists/nested objects, yet you should not assume the property-binding auto-grow limit acts as an automatic quota there. Design input contracts and test limits matching how real data enters your app.

## 11. Distinguishing rejected, suppressed, and runtime errors

When inspecting an invalid request, distinguish three groups:

| Phenomenon | Example | Where to observe |
| --- | --- | --- |
| **Suppressed field** | `admin=true` or `items[999999].quantity=2` blocked by allowlist | `BindingResult.getSuppressedFields()` |
| **Binding/conversion error** | `items[0].quantity=abc` cannot convert to `int` | `BindingResult.getFieldErrors()`, typically code `typeMismatch` |
| **Rule validation error** | `quantity=0` fails `@Min(1)` or custom validator | `BindingResult` after validation is triggered |

In some cases where a path/collection exceeds access capability, exceptions related to `InvalidPropertyException`, `NullValueInNestedPathException`, or other access errors can arise depending on execution path. Never build a security policy assuming "every huge index becomes a FieldError for the controller to handle." **Reject upfront with schema/allowlist and HTTP limits**, then handle relevant exception types cleanly.

**`getSuppressedFields()` is not `hasErrors()`.** A request with suppressed fields can still report `hasErrors() == false`. If policy requires detecting abnormal inputs, check suppressed fields explicitly.

**User-facing error messages do not need to expose sensitive raw paths.** Use stable codes such as `INVALID_FIELD`, `INPUT_TOO_LARGE`, or `INVALID_INDEX`; server-side logs should record only metadata needed for analysis safely.

## 12. Limits that binder settings do not replace

### 12.1. @Valid and @Size run after data is bound

`@Valid`, `@Validated`, `@Size`, and `@Min` verify whether data is **valid by business rules**. Yet in property binding, conversion/auto-grow normally runs before validation executes. Checking `list.size() <= 3` afterward remains valuable for the contract, though it does not stop allocations upfront.

### 12.2. setAutoGrowNestedPaths(false) is not a max depth

Disabling auto-grow stops Spring from instantiating a nested object when a path reaches a `null` object. It **does not** stop traversing a deep graph if all intermediate objects are already initialized and properties are writable.

### 12.3. setAutoGrowCollectionLimit is not a max collection size

It caps **collection auto-expansion during property binding**, not final quotas for pre-existing lists, Maps, JSON, HTTP parameter counts, or total elements across nested graphs.

### 12.4. allowedFields does not protect the HTTP parsing step

An out-of-allowlist path is dropped during binding, yet already consumed resources when received and parsed. Cap parameter counts and request sizes at an appropriate boundary.

### 12.5. BindingResult does not replace authorization

A valid path and valid value can still be unauthorized for the caller under business rules. Authorization belongs in the service/security layer and may depend on the current user and resource.

### 12.6. Broad wildcards can break the contract

`items[*].quantity` permits field names with many different indices at the matching layer. If at most 3 slots are wanted, enforce explicit index bounds rather than relying on wildcards to self-limit. A wildcard like `*` can accidentally permit unintended fields.

## 13. Boundary test suite to have

For a form with at most three `items` slots, test both valid and rejected cases:

| Request | Expectation with section 5 allowlisted form binding |
| --- | --- |
| `items[0].sku=BK-1` | Path permitted; still requires data validation |
| `items[2].quantity=3` | Permitted; within the three slots |
| `items[3].quantity=3` | Suppressed because outside allowlist |
| `items[999999].quantity=3` | Suppressed; does not auto-grow to this index |
| `items[-1].quantity=3` | Outside allowlist; suppressed |
| `items[0].secret=true` | Suppressed because property is not declared |
| `customer=An` | Permitted |
| `admin=true` | Suppressed even though demo has a setter |
| `items[1].quantity=abc` | Path permitted, yet conversion can record a binding error |
| `items[0].details.owner.role=admin` | Suppressed because path is deeper than contract |
| Thousands of arbitrary fields | Must be blocked at HTTP limits / request checks; do not rely solely on binder |
| JSON array with thousands of elements | Needs separate body/parser constraints; form binder settings are insufficient |

When testing large index values or deep paths, only use resource-capped tests in controlled environments; avoid sending huge requests that impact shared systems. Unit tests can verify policy with synthetic path lists without allocating gigantic collections.

In particular, tests must assert both **post-bind target state** and `BindingResult`. Asserting `hasErrors()==false` alone is insufficient: requests with suppressed fields can still return false. For requests policy should reject, assert `getSuppressedFields()` contains the dropped name and the controller never invokes the business service.

## 14. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Allowing arbitrary request paths | Mass assignment, uncontrolled graph | Small DTO + exact allowedFields |
| Using only `setAutoGrowCollectionLimit(3)` | Does not cap Maps, path counts, depth, or pre-existing lists | Add quotas per dimension |
| Raising limit to millions to "support many rows" | Risk of abnormal allocations | Choose batch import workflow, explicit quotas |
| Using only `@Size(max=3)` | Runs after objects are already allocated | Cap at HTTP layer and during binding |
| Counting only dots in paths | Misses `[index]` levels and Map keys | Exact allowlist or contract-driven path parser |
| Using overly broad `items[*].*` | Exposes unintended fields and arbitrary indices | Concrete path allowlist or strict index parsing |
| Treating suppressed fields as validation errors | Fails to detect abnormal requests | Check `getSuppressedFields()` separately |
| Binding directly onto JPA entities | Can mutate internal fields before validation | Bind to DTO, apply to service only after PASS |
| Relying on auto-grow limit for JSON | Config does not apply to Jackson deserialization | Use JSON body/parser quotas and validation |
| Not capping HTTP parameter count | Container already parsed huge input before binder | Configure container/gateway appropriately |
| Sharing mutable target across requests | State bleed, concurrency bugs | Create target/binder per request; never cache form state |
| Returning raw BindingResult or logging sensitive values | Leaks input and internal structure | Standardize error codes, sanitize logging |

## 15. Checklist for configuring a safe form

1. **Define the contract:** which fields are allowed, their types, max path depth, max rows/entries, and max request size.
2. **Design the DTO:** omit all properties outside the form from the target; prefer constructor binding when suitable.
3. **Register an allowlist** when using property binding; for fixed indices, list exact paths.
4. **Cap auto-grow:** set `setAutoGrowCollectionLimit(n)` to the required slot count, never unbounded.
5. **Choose nested policy:** enable auto-grow nested paths only when intermediate instantiation is genuinely wanted.
6. **Cap at the HTTP layer:** body bytes, parameter counts, and other stack-specific quotas.
7. **Use validation for business rules:** `@Size`, `@Min`, custom validators, list contiguity, and total item checks.
8. **Read both suppressed fields and errors:** separate out-of-contract fields from conversion and validation errors.
9. **Call services only after PASS:** map DTO to domain with proper authorization and transactions.
10. **Test boundaries:** index 0, last valid index, index right past limit, huge index, overly deep path, extra parameters, oversized JSON array.
11. **Monitor resources:** rejected requests, parse/bind timing, exceptions, and appropriate rate limits.

## 16. Self-check

**1. Does `setAutoGrowCollectionLimit(3)` ensure every list on the object always has at most three elements?**  
No. It caps array/collection auto-expansion during property binding. Pre-existing lists, Maps, JSON, or total elements across lists require separate quotas.

**2. `items[999999].quantity` appears in a form whose allowlist only includes `items[0..2]`. What happens?**  
The path is absent from allowed fields and is suppressed before property access runs. If the app should reject abnormal requests, check `BindingResult.getSuppressedFields()`.

**3. Does `@Size(max=3)` stop a huge list from being created during HTTP parsing?**  
No. It validates data size after binding/deserialization. Enforce limits before and during input processing.

**4. Does setting `setAutoGrowNestedPaths(false)` reject every deep path?**  
No. It prevents auto-creating null nodes; paths through already-existing objects remain reachable.

**5. Is `allowedFields("items[*].quantity")` enough to block huge indices?**  
Not yet. Wildcard matching does not bound integer indices. Add index/auto-grow/HTTP quotas and tests.

**6. Why cap request body size and parameter count outside `DataBinder`?**  
Because parsing can happen before the binder filters fields. The binder cannot undo resource cost already incurred in the HTTP stack.

**7. Should a request with suppressed fields yet `hasErrors()==false` be treated as valid?**  
Policy-dependent, though APIs requiring strict schemas must reject via `getSuppressedFields()`. Suppressed fields are not automatically counted as validation errors.

**8. Does the form auto-grow limit apply to Jackson `@RequestBody` JSON?**  
Do not assume so. JSON flows through a different message converter; enforce structural, size, and parser/DTO constraints separately.

**Key takeaway:** securing property binding requires controlling **which paths are allowed**, **which depths and indices are allowed**, **how many nodes can be instantiated**, and **how much input enters from HTTP**. `setAutoGrowCollectionLimit` is an important resource-protection layer, yet DTO contracts, allowlists, request caps, and validation together form a complete defense.

## Official references

- [Spring Framework 6.2 — Data Binding and BeanWrapper](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — @InitBinder and Safe Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — Spring MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
