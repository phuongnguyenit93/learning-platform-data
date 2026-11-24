# autoGrowCollectionLimit and Access-Mode Scope in Spring DataBinder

## 1. The problem: a request index can inflate a collection

Spring supports **property paths** such as `customer.name`, `lines[0].sku`, and `lines[3].quantity`. When a `DataBinder` binds data onto a JavaBean, it can auto-create nested objects or expand lists/arrays to reach the referenced element. This feature is handy when a form submits multiple order lines; it can also cause the application to allocate many unexpected objects if the sender controls the index.

For example, a form submits:

~~~text
lines[2].sku=SKU-003
~~~

If `lines` does not initially exist and configuration permits auto-growth, Spring can create the list, grow it long enough to have a third slot (index 2), instantiate the nested element, and set `sku`. A single input field can cause multiple elements or objects to be allocated.

An input like `lines[1000000].sku=X` poses a resource risk if the application tries to allocate too many elements. `DataBinder.setAutoGrowCollectionLimit(int)` is a mechanism to cap **collection auto-expansion via indexed paths** in the access modes supported by the Spring version.

**Distinguish this from the start:** `setAutoGrowCollectionLimit` differs from `setAutoGrowNestedPaths`. One configures the **collection auto-growth threshold**; the other enables/disables **auto-creating nested paths on null and expanding elements via indexed paths**. Both differ from HTTP request size limits or `@Size` validation.

## 2. Two core settings and default values

| `DataBinder` setting | Default | Meaning |
| --- | --- | --- |
| `setAutoGrowNestedPaths(boolean)` | `true` on a standard `DataBinder` | When permitted, tries to instantiate objects at null segments of a path; also allows auto-expanding collection elements when accessing indices beyond the current size |
| `setAutoGrowCollectionLimit(int)` | `256` | Index threshold for **array/collection auto-growth** in supported modes; does not mean every collection in the app is capped at 256 elements |
| `getAutoGrowCollectionLimit()` | Returns the configured value | Inspects the binder setting, yet **does not by itself prove** the same cap is enforced across every access mode |

Example:

~~~java
DataBinder binder = new DataBinder(orderForm, "orderForm");
binder.setAutoGrowNestedPaths(true);
binder.setAutoGrowCollectionLimit(32);
~~~

This is an **illustrative** snippet where `orderForm` is an existing object. Under standard usage, configure these properties **before creating/initializing BindingResult or starting to bind**, so the accessor is set up with the desired configuration.

### 2.1. Zero-based indexing and growth condition

Suppose `List<Line> lines` starts empty and the limit is **4**:

| Input path | Expected result with auto-grow bean-property binding |
| --- | --- |
| `lines[0].sku` | Can expand up to 1 element |
| `lines[2].sku` | Can expand up to 3 elements |
| `lines[3].sku` | Can expand up to 4 elements |
| `lines[4].sku` | Cannot **auto-expand** from an empty list to index 4 because `4` is not less than limit `4` |

Because indexing starts at 0, a limit of 4 corresponds to **a maximum auto-growable index of 3**. The exact rule is: within the corresponding auto-growth logic, expansion happens only when **`index < autoGrowCollectionLimit`** and all other conditions allow it.

Do not conclude `lines[4]` is always rejected: if the list **already holds** at least 5 elements, writing to an existing index does not require auto-growth. Therefore `autoGrowCollectionLimit` is **not** an absolute element-count cap for every list and does not replace order-line count rules.

### 2.2. What happens when the limit is exceeded?

For a standard `List` or array needing auto-growth, Spring will not allocate elements beyond the configured threshold in flows enforcing that threshold. Accessing a non-existent index can fail with a path/property exception (such as `InvalidPropertyException`), rather than always turning into a `FieldError` readable via `BindingResult.hasErrors()`.

Do not write code assuming "an over-limit index always returns HTTP 400 and records a `FieldError`." Handling depends on error location, container type, binding mode, Spring version, and MVC/exception handler setup. For web inputs, **control incoming request structure** and design error responses intentionally.

## 3. Relationship to property paths and autoGrowNestedPaths

A path can contain multiple segments:

~~~text
order.customer.address.city
order.lines[2].sku
order.lines[2].options[1].label
~~~

To assign `order.lines[2].sku`, the binder must traverse `order`, `lines`, the third element, and then `sku`. With `setAutoGrowNestedPaths(true)`, the accessor can attempt to create missing segments, depending on type resolution and object instantiation.

To do so, the model typically needs:

- An actual existing target object (unless executing constructor binding under its own mechanism).
- Clearly declared nested property types, e.g., `List<OrderLine>` instead of a raw `List` lacking element type information.
- An element type with a suitable instantiation path (e.g., an accessible no-arg constructor); not arbitrary abstract types or interfaces that Spring cannot guess how to instantiate.
- A valid access path under the chosen **bean-property** or **direct-field** mode.
- A collection suitable for expansion; immutable lists (`List.of(...)`), fixed-size lists, or non-instantiable elements can fail.

When `setAutoGrowNestedPaths(false)` is set, accessing `null` segments or out-of-bounds indexed paths generally does not auto-create/expand. **Do not** interpret `setAutoGrowCollectionLimit(256)` as forcing auto-grow on: a non-zero limit does not re-enable a disabled nested-path flag.

### 3.1. Nested-object growth and collection growth are two operations

Suppose:

~~~java
public class OrderForm {
    private Address shippingAddress;
    private List<OrderLine> lines;
    // suitable getters/setters
}
~~~

- `shippingAddress.city=Hanoi` can cause `shippingAddress` to be instantiated, which is **nested object instantiation**, not indexed collection growth.
- `lines[3].sku=S4` can cause `lines` to be created, grown to fit, and the fourth element instantiated.
- `lines[3].options[2].label=Gift` can create multiple levels and elements; each auto-growth cap **does not automatically become a cap on total objects or path depth**.

In other words, `autoGrowCollectionLimit` controls **one form of collection expansion**, not a universal ceiling on all nested property path processing costs.

## 4. Scope by access mode: bean property vs. direct field

This is the most important point of the lesson. The same `DataBinder` has two access paths:

~~~java
binder.initBeanPropertyAccess(); // Default: JavaBean getters/setters.
binder.initDirectFieldAccess();  // Alternative: operate directly on fields.
~~~

These two calls are **two mutually exclusive alternatives**, not commands to run sequentially for a single bind.

### 4.1. Bean-property access (default)

- Uses `BeanWrapper` and getter/setter conventions to read/write properties.
- `setAutoGrowNestedPaths(true)` can expand eligible paths.
- `setAutoGrowCollectionLimit(n)` caps **array/list auto-growth** in this property binding flow.
- This is the best mode for learning and verifying the limit on a JavaBean form model.

~~~java
DataBinder binder = new DataBinder(new OrderForm(), "orderForm");
binder.setAutoGrowCollectionLimit(4);
binder.bind(propertyValues);
~~~

This snippet illustrates usage assuming `OrderForm` and `propertyValues` exist. Section 6 provides the complete example.

### 4.2. Direct-field access

- `initDirectFieldAccess()` uses `DirectFieldAccessor`, reading/writing fields directly rather than through JavaBean getters/setters.
- Auto-grow nested paths are supported in direct-field access across many Spring versions.
- **However, supporting auto-grow does not mean the index limit is implemented identically to bean-property access in every version.**

According to Spring source code and release notes:

| Version line | `setAutoGrowNestedPaths` with direct field | `setAutoGrowCollectionLimit` with direct field |
| --- | --- | --- |
| Spring 6.2.x and Spring 7.0.x | Supports auto-grow for eligible paths | **Do not treat the DataBinder limit as an effective cap for direct-field auto-growth**; implementations in these lines primarily enforce the cap in bean-property binding |
| Spring 7.1 and later | Supported | Spring extends `autoGrowCollectionLimit` enforcement to **field injection/direct-field binding**; verify exact API/version behavior in deployment |

Documentation note: some older Javadocs briefly phrased it as "setter/field injection," leading readers to assume both modes behaved identically. Clarifying notes in Spring 7.1 source state the scope covered **setter injection**, and **only from 7.1 onward extended to field injection**. Therefore on Spring 6.2/7.0, inspect implementation behavior and write regression tests for your actual configuration rather than relying solely on `getAutoGrowCollectionLimit()`.

**Design consequence:** do not switch to `initDirectFieldAccess()` to bypass getters/setters on an object accepting untrusted data; doing so can skip setter-enforced invariants and weaken assumptions around auto-grow limits. Direct field access should only be used when the object model and trusted input flow are well understood.

### 4.3. Distinguishing access mode from binding mechanism

**Bean-property access** and **direct-field access** are two ways of setting properties during `bind(PropertyValues)`. **Constructor binding** (`construct(ValueResolver)`) is a separate mechanism that creates objects from constructor arguments, including collection parameters.

`setAutoGrowCollectionLimit` **does not apply** to constructor binding via `DataBinder.construct(...)` in the versions discussed. Constructor binding needs its own input limits: element counts, request sizes, nesting levels, DTO contracts, and intentional validation. Never assume "limit=32 is set" means `construct()` can never receive more than 32 elements.

### 4.4. Map keys and structures outside the limit's scope

`items[2]` is a **numeric index** on a list/array. `labels[priority]` can be a **Map key**. They share a similar path syntax yet differ in semantics.

~~~text
items[2].name
labels[priority]
translations[vi].title
~~~

`autoGrowCollectionLimit` does not limit the number of `Map` keys, nor does it limit the number of elements in a JSON array deserialized by Jackson. Applications accepting Maps or large JSON request bodies must impose appropriate quotas themselves. For custom collections, how `get(index)` or `add(...)` behaves also affects resource allocation.

## 5. Verifiable differences across a scenario matrix

Suppose fresh objects start with `List<OrderLine> lines` as null under Spring 7.0.9:

| Scenario | Configuration | Expectation |
| --- | --- | --- |
| Property binding, index 2 | `autoGrowNestedPaths=true`, limit 4 | Can create a 3-element list; sets `lines[2].sku` |
| Property binding, index 2 | limit 2 | Must not auto-grow to reach index 2; operation is not accepted as valid binding |
| Property binding, existing index | List has 10 elements, limit 2 | **Writing into** existing elements is not necessarily blocked by the low limit |
| Property binding, nested null | `autoGrowNestedPaths=false` | Does not auto-create null segments to proceed |
| Direct-field binding | Call `initDirectFieldAccess()` | Reads/writes fields directly; **do not assume** the same limit is enforced in Spring 7.0 |
| Constructor binding | Call `construct(...)` | `setAutoGrowCollectionLimit` does not cap constructor input size |
| `@RequestBody` JSON | Jackson deserializes JSON | Not governed by this DataBinder form/property binding limit |

**Never send requests with gigantic indices to "test" limits against a live service.** Use small thresholds and synthetic inputs in isolated unit tests to observe behavior without triggering unintended allocations.

## 6. Complete Java 17+ example: comparing property access and direct-field access

This example runs **without a servlet container or Spring Boot server**. It illustrates three points:

1. `BeanWrapper` inside `DataBinder` auto-expands the list for `lines[2].sku` when limit is 4.
2. When limit is 2, attempting to set index 2 does not produce a valid write. Because error reporting can vary by context, the example checks **actual state** and catches exceptions on the over-limit branch.
3. `initDirectFieldAccess()` can still populate elements at a small index without getters/setters on the root object. Do not run over-limit operations in direct-field mode because limit semantics change across versions.

The example uses `spring-context 7.0.9`, a release line containing public patches for a list auto-expansion CVE (section 8). In a Spring Boot project, prefer the project's BOM/Dependency Management rather than pinning Spring versions manually.

Structure:

~~~text
collection-growth-demo/
├── pom.xml
└── src/main/java/CollectionGrowthDemo.java
~~~

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>collection-growth-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. src/main/java/CollectionGrowthDemo.java

~~~java
import java.util.List;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

public class CollectionGrowthDemo {

    public static class OrderLine {
        private String sku;

        public OrderLine() {
        }

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }
    }

    public static class BeanOrder {
        private List<OrderLine> lines;

        public List<OrderLine> getLines() {
            return lines;
        }

        public void setLines(List<OrderLine> lines) {
            this.lines = lines;
        }
    }

    public static class FieldOrder {
        // No JavaBean getter/setter for "lines".
        private List<OrderLine> lines;

        public List<OrderLine> snapshot() {
            return lines;
        }
    }

    private static MutablePropertyValues input(
            String path, String value) {

        MutablePropertyValues values = new MutablePropertyValues();
        values.add(path, value);
        return values;
    }

    public static void main(String[] args) {
        DataBinder defaults = new DataBinder(new BeanOrder());
        System.out.println("default.limit="
                + defaults.getAutoGrowCollectionLimit());

        // Case 1: index 2 < limit 4, can create 3 elements.
        BeanOrder beanOrder = new BeanOrder();
        DataBinder beanBinder = new DataBinder(beanOrder, "beanOrder");
        beanBinder.setAutoGrowNestedPaths(true);
        beanBinder.setAutoGrowCollectionLimit(4);
        beanBinder.bind(input("lines[2].sku", "SKU-003"));

        System.out.println("bean.size=" + beanOrder.getLines().size());
        System.out.println("bean.third="
                + beanOrder.getLines().get(2).getSku());
        System.out.println("bean.errors="
                + beanBinder.getBindingResult().hasErrors());

        // Case 2: index 2 is not less than limit 2.
        BeanOrder limitedOrder = new BeanOrder();
        DataBinder limited = new DataBinder(limitedOrder, "limitedOrder");
        limited.setAutoGrowCollectionLimit(2);

        boolean overLimitWritten = false;
        try {
            limited.bind(input("lines[2].sku", "SHOULD-NOT-WRITE"));
            List<OrderLine> list = limitedOrder.getLines();
            overLimitWritten = list != null
                    && list.size() > 2
                    && list.get(2) != null
                    && "SHOULD-NOT-WRITE".equals(list.get(2).getSku())
                    && !limited.getBindingResult().hasErrors();
        } catch (RuntimeException ex) {
            // Exceeding the limit can fail property path access.
            // Do not rely on a single fixed exception class across all versions.
        }
        System.out.println("bean.overLimitWritten=" + overLimitWritten);

        // Case 3: direct field access with a small index.
        FieldOrder fieldOrder = new FieldOrder();
        DataBinder fieldBinder = new DataBinder(fieldOrder, "fieldOrder");
        fieldBinder.initDirectFieldAccess();
        fieldBinder.setAutoGrowNestedPaths(true);
        fieldBinder.setAutoGrowCollectionLimit(2);
        fieldBinder.bind(input("lines[1].sku", "FIELD-002"));

        System.out.println("field.size=" + fieldOrder.snapshot().size());
        System.out.println("field.second="
                + fieldOrder.snapshot().get(1).getSku());
        System.out.println("field.errors="
                + fieldBinder.getBindingResult().hasErrors());
    }
}
~~~

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=CollectionGrowthDemo
~~~

Expected output from `System.out.println(...)` calls (ignoring Maven logs):

~~~text
default.limit=256
bean.size=3
bean.third=SKU-003
bean.errors=false
bean.overLimitWritten=false
field.size=2
field.second=FIELD-002
field.errors=false
~~~

Explanation:

- `BeanOrder` has getters/setters for `lines`, so the default mode is bean-property access. Starting from a null list, Spring can create an `ArrayList<OrderLine>`, fill needed slots, and instantiate `OrderLine` to set `sku`.
- With limit 4, index 2 is small enough: `lines` has length 3 and the third slot's value is `SKU-003`.
- With limit 2, index 2 is outside **auto-grow** range for an empty list; the `try/catch` branch confirms no valid write occurred at that position. The example avoids claiming "always throws the exact same exception" or "always produces only a BindingResult error."
- `FieldOrder` has **no getter/setter** for `lines`, yet `initDirectFieldAccess()` lets the binder manipulate the field. Because the example uses index 1, it only demonstrates **binding capability in direct-field mode**; do not use this result to conclude direct-field limits always enforce identically to bean-property mode.
- `OrderLine` has an accessible no-arg constructor; generic `List<OrderLine>` tells Spring which element class to instantiate.

**Verification scope:** the program and stdout were reviewed against the API, though running Maven in an environment with matching dependencies is needed for execution evidence in that environment. The example intentionally avoids allocating large collections.

## 7. Applying in Spring MVC and WebDataBinder

When a controller handles `@ModelAttribute`, you can configure binder limits per form name via `@InitBinder`. The snippet below is **illustrative code inside an existing controller**, not a standalone Spring MVC application:

~~~java
@InitBinder("orderForm")
void configureOrderForm(WebDataBinder binder) {
    binder.setAutoGrowNestedPaths(true);
    binder.setAutoGrowCollectionLimit(32);
    binder.setAllowedFields(
            "customerName",
            "lines[*].sku",
            "lines[*].quantity"
    );
}
~~~

From this:

- Limit 32 governs **auto-expansion** of lists/arrays in that property binding flow, not total request fields, nested object counts, byte size, or already-existing items.
- `setAllowedFields(...)` is an allowlist of modifiable paths; `*` performs field-name pattern matching. It adds a mass-assignment boundary rather than replacing resource caps.
- `@InitBinder("orderForm")` applies to binders for the model attribute named `orderForm`. If other model attributes/controllers need separate rules, scope configurations accordingly.
- `@Valid @ModelAttribute("orderForm")` with `BindingResult` validates form constraints after binding when a matching validator exists; do not treat validation as the sole defense against resource consumption **happening before validation**.

The controller must handle errors properly, including cases where a path fails before the handler method runs. Never assume every failure turns into `BindingResult.hasErrors()` under every configuration.

### 7.1. With JSON @RequestBody

~~~java
@PostMapping("/orders")
ResponseEntity<?> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

This is an illustrative snippet. JSON arrays via `@RequestBody` are normally read by `HttpMessageConverter`/Jackson, **not** arrays expanded from a form field name `lines[999].sku` via `DataBinder.bind(PropertyValues)`. Hence `autoGrowCollectionLimit` does not cap how many elements Jackson deserializes in a request body.

Use request body limits, DTOs with maximum element counts, collection constraints (such as `@Size(max=32)`), and nested validation; add parser/proxy resource limits where appropriate. Remember validation runs **after** the payload is read/deserialized, so `@Size` is not a pre-parse memory ceiling.

### 7.2. What if the model has genuinely large valid lists?

Suppose a system legitimately supports up to 500 order lines. **Do not automatically set limit 500 or 1000** just because a form can contain many rows; that could allow large allocations from a single `lines[499].sku` field.

Prefer:

1. Designing an API receiving explicit collections with element-count and payload limits.
2. Capping batch sizes per operation to real needs; paginate or split into batches where appropriate.
3. Checking permissions and domain invariants in the service layer.
4. Raising `autoGrowCollectionLimit` only when business requirements demand it and resource costs are controlled.

## 8. Security: this limit matters, yet is not a silver bullet

### 8.1. Preventing allocation from sparse indices

A client can send very few bytes containing a huge index:

~~~text
lines[999999999].sku=ABC
~~~

If binding tried to allocate intermediate slots without limits, a tiny payload could trigger large memory consumption. The default limit of 256 exists to mitigate this risk in binding paths where it applies.

However:

- This limit does not block every container type (notably Map keys or specialized collections).
- It does not cap all nested-object branches, path depth, form field counts, or JSON arrays.
- Custom collections with non-standard `get(index)` behavior can allocate elements unexpectedly from the accessor's perspective.
- Direct-field mode has important version differences; do not extrapolate limits blindly.

When accepting external inputs, prefer DTOs with only allowed fields, path allowlists, request size/structure caps, collection count checks, and maintained framework versions.

### 8.2. CVE-2026-59282: the self-populating List case

On 20/08/2026, Spring disclosed **CVE-2026-59282**, a Denial of Service scenario when property binding processes a **List whose `get(index)` auto-populates elements**. After the auto-growth threshold prevented expansion in the accessor's own logic, nested property traversal continued by calling `list.get(index)`. On a standard List, out-of-bounds access throws `IndexOutOfBoundsException`; however, a self-populating List can allocate huge numbers of elements upon seeing a large index.

The risk conditions described by Spring include:

1. The application allows Spring binding using property paths from external data.
2. The target object contains a **self-populating List**.
3. The element type has child properties, causing the binder to traverse paths like `list[index].property`.

This is **not** a claim that every application using `ArrayList` is vulnerable to the CVE. It shows `autoGrowCollectionLimit` does not necessarily block allocations happening **inside a collection's own implementation**.

Per Spring's advisory, versions `7.0.0–7.0.8`, `6.2.0–6.2.19`, and several older lines are affected when all conditions hold. Listed patches include `7.0.9` (OSS) and `6.2.20` (Enterprise Support at disclosure time), along with corresponding support branches. When evaluating real systems, verify patches for your active version, avoid exposing self-populating Lists to client-controlled index paths, and never raise limits without controlling input.

Source: https://spring.io/security/cve-2026-59282/

### 8.3. Application-level test checklist

| Check | Expectation |
| --- | --- |
| Bind `lines[0].sku` or `lines[limit-1].sku` on an empty list, auto-grow on | Works for compatible access modes and class models |
| Bind `lines[limit].sku` on an empty list, bean-property mode | Does not auto-expand to index equal to limit |
| Bind a valid index on an already populated list | Do not mistake the limit for an absolute list-size cap |
| Bind nested path when `autoGrowNestedPaths=false` | Does not auto-create null nodes |
| Switch between `initBeanPropertyAccess` and `initDirectFieldAccess` | Test separately; do not assume config parity across Spring versions |
| Constructor binding and JSON requests | Enforce element counts explicitly without relying on property-binding limits |
| Client sends disallowed fields | Does not mutate properties outside allowlist/DTO |
| Self-populating List | Avoid exposing such structures to client-controlled index paths; run patched versions |

## 9. Common misinterpretations

1. **"The default limit of 256 means every list can hold at most 256 elements."** False: it is a threshold for **auto-grow** on eligible binding paths, not a domain object invariant.
2. **"A limit of 32 allows index 32."** An auto-growable index must be **strictly less than** 32 if the element does not exist yet. Index 31 is the 32nd position.
3. **"Setting `autoGrowCollectionLimit` turns auto-grow on."** You must also consider `autoGrowNestedPaths` and actual object instantiation rules.
4. **"Nested path objects and auto-growing lists share one total limit."** The collection limit does not cap total tree depth or total instantiated objects across the whole object graph.
5. **"Direct-field access and bean-property access always share the same limit."** False on Spring lines prior to 7.1; read the exact API docs and test.
6. **"Constructor binding obeys this limit."** `construct(ValueResolver)` does not use the auto-growth threshold of `bind(PropertyValues)`.
7. **"JSON @RequestBody also obeys this limit."** Jackson reads JSON on a separate path; cap requests/bodies/lists independently.
8. **"Exceeding the limit always produces a FieldError and HTTP 400."** Property access exceptions can occur before errors enter BindingResult; design handlers explicitly.
9. **"Set a huge limit to prevent errors."** A single sparse field can trigger substantial allocation; design APIs and sensible caps first.
10. **"Bypassing setters with direct-field access is safer."** Direct fields can bypass setter validation/invariants; use only in well-understood, trusted contexts.
11. **"Using @Size is enough to stop DoS."** Validation usually runs after binding/deserialization; cap resources starting at the ingestion layer.
12. **"Only standard Lists with large indices need care."** Standard Lists usually reject out-of-range access, whereas custom self-populating Lists can behave differently; apply patches and verify collection behavior.

## 10. Self-check questions

- With limit 5 and an empty list, how do `lines[4].sku` and `lines[5].sku` differ?
- Why does limit 5 not prevent setting `lines[8].sku` if the list already has 10 elements?
- When does `setAutoGrowNestedPaths(false)` affect `customer.address.city` and `lines[2].sku`?
- Why is checking your exact Spring version critical when working with `initDirectFieldAccess()`?
- Why are `DataBinder.construct(...)` and `@RequestBody` JSON not protected by the property-binding auto-growth limit?
- Why can a self-populating List bypass a developer's expectations even when the binder sets a low limit?
- At which layers would you enforce request/body limits, field allowlists, and collection validation to prevent one field index from causing huge allocations?

You can change the limit to 3 or 5 in the Java 17+ example, test small indices 0, 1, 2, 3, and observe **post-bind size**, **field values**, and **errors/exceptions**. A few small values suffice to prove the rule without trying indices in the millions.

## References

- Spring Framework 6.2 DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 7.0 DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework BeanWrapper/property paths: https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html
- Spring source DataBinder: https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/validation/DataBinder.java
- Spring source AbstractNestablePropertyAccessor: https://github.com/spring-projects/spring-framework/blob/main/spring-beans/src/main/java/org/springframework/beans/AbstractNestablePropertyAccessor.java
- Spring security advisory CVE-2026-59282: https://spring.io/security/cve-2026-59282/
