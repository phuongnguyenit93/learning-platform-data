# BeanWrapper: getPropertyValue and setPropertyValue

`BeanWrapper` is Spring Framework's API for **reading and writing properties of a Java object by string name or path**. The two most commonly used methods are:

```java
Object value = wrapper.getPropertyValue("propertyName");
wrapper.setPropertyValue("propertyName", newValue);
```

In this guide, a "property" is an attribute recognized by JavaBeans introspection, typically via a `getX()/setX(...)` pair or `isX()` for booleans. It does not necessarily correspond to a directly accessed field. `getPropertyValue` retrieves the current value; `setPropertyValue` goes through the property access mechanism, supporting nested paths, lists/Maps, and type conversion within its configured scope.

The goal is to use these two APIs properly, understand **how they locate getters/setters and traverse the object graph**, distinguish read/write errors, and know when to use `BeanWrapper` directly versus delegating to Spring's `DataBinder`.

## 1. Context: Property, Target, and Wrapper

Suppose we have a JavaBean:

```java
public class Customer {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

The snippet above is a class definition, without `main`. Under JavaBeans conventions, the `name` property typically has:

- **getter** `getName()` for reading;
- **setter** `setName(String)` for writing;
- **property type** `String`;
- a `Customer` instance as the **target** of operations.

You do not have to hardcode `customer.getName()` at the call site; when the property name is determined at runtime (for example from configuration, mapping, or metadata), you can use:

```java
Customer customer = new Customer();
BeanWrapper wrapper = PropertyAccessorFactory.forBeanPropertyAccess(customer);

wrapper.setPropertyValue("name", "An");
Object value = wrapper.getPropertyValue("name");
```

This API usage snippet requires importing `org.springframework.beans.BeanWrapper` and `org.springframework.beans.PropertyAccessorFactory`.

```text
target: Customer instance
             |
             v
BeanWrapper(target)
     |                     |
     | getPropertyValue    | setPropertyValue
     v                     v
 find getter            find setter
     |                     |
     v                     v
 get value              convert type if needed
                           |
                           v
                       assign to target
```

**Key point:** the wrapper manages access to **the exact instance** passed in. With `setPropertyValue`, values inside the target can change immediately. The wrapper does not automatically copy the target, does not store snapshots by default, has no transaction mechanism, and does not perform business validation on its own.

## 2. Creating BeanWrapper Properly

Spring provides the `BeanWrapper` interface and the common `BeanWrapperImpl` implementation. Two typical ways to create one:

```java
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.PropertyAccessorFactory;

Customer customer = new Customer();

// Approach 1: obtain via factory, keeping calling code dependent on the interface.
BeanWrapper viaFactory =
        PropertyAccessorFactory.forBeanPropertyAccess(customer);

// Approach 2: instantiate the implementation directly if specific configuration is needed.
BeanWrapperImpl viaConstructor = new BeanWrapperImpl(customer);
```

The snippet above requires the `Customer` class from section 1. Both wrappers target JavaBean property access. When there are no special requirements, `PropertyAccessorFactory.forBeanPropertyAccess(target)` expresses intent clearly; when custom configuration is needed, `BeanWrapperImpl` can be used.

For comparison, Spring also provides `PropertyAccessorFactory.forDirectFieldAccess(target)` for direct field access. **Direct field access and BeanWrapper property access are not synonymous**. For a regular JavaBean, reading/writing via getters/setters can trigger logic inside those methods; direct field access behaves differently and does not follow the same getter/setter contract.

| Access method | Goes through getter/setter? | Suitable when |
| --- | --- | --- |
| `BeanWrapper` / `BeanWrapperImpl` | Via JavaBeans property descriptors | Objects with public property APIs, mutable forms/beans |
| `DirectFieldAccessor` (from factory) | Uses field access | Object types or cases requiring direct field read/write |
| Calling `customer.getName()/setName(...)` | Yes, type-checked at compile time | Property is known in source code |
| Hand-written reflection | Depends on implementation | Specialized mechanism needed and ready to handle metadata/errors manually |

Do not replace every getter/setter call with a property name string. When the property name is known at compile time, calling methods directly is simpler, easier to refactor, and benefits from compile-time type checking.

## 3. getPropertyValue(String): Reading a Value by Property Name

Syntax:

```java
Object value = wrapper.getPropertyValue("name");
```

`getPropertyValue` takes a **property name/path** and returns `Object`. When a property is `int`, the returned value may be a boxed `Integer`. Callers must cast to the right type or use type metadata provided by the wrapper.

Example:

```java
String name = (String) wrapper.getPropertyValue("name");
int age = (Integer) wrapper.getPropertyValue("age");
```

The snippet above assumes the target has properties `name: String` and `age: int`. For properties that can be `null`, check before unboxing; assigning `(Integer) null` to `int` causes a `NullPointerException` during unboxing.

### When Is a Property Readable?

A property is readable when Spring identifies an appropriate read path, typically an invocable getter. Having a setter does not guarantee readability. Use:

```java
if (wrapper.isReadableProperty("name")) {
    Object value = wrapper.getPropertyValue("name");
}
```

When a property does not exist or has no appropriate getter, `getPropertyValue` can throw `NotReadablePropertyException` (under `BeansException`); do not assume the result will be `null`. **A nonexistent property** is different from **a valid property whose current value is null**.

### Getters Can Execute Code

If `getName()` computes a value, writes logs, calls a service, or throws an exception, `getPropertyValue("name")` can trigger that behavior. `BeanWrapper` does not bypass getter side effects. Therefore, reading a property repeatedly in a large loop can be expensive or produce unexpected behavior if the getter is not pure.

## 4. setPropertyValue(String, Object): Writing via Property Access

Syntax:

```java
wrapper.setPropertyValue("name", "Binh");
wrapper.setPropertyValue("age", 20);
```

Spring locates the target property and performs the appropriate assignment. When the target is a mutable JavaBean, the corresponding setter is normally invoked:

```java
customer.setName("Binh");
```

Compared to calling setters directly, `setPropertyValue` is useful when **property names are dynamic**: read from mappings, configuration, or a workflow carrying a list of properties to update. However, because names and values are runtime data, path and type conversion errors are usually caught only at runtime.

Cases to distinguish:

- **Writable property:** has a setter (or another suitable property access mechanism), so it can be written.
- **Read-only property:** has a getter without a setter; readable, but writing can throw `NotWritablePropertyException`.
- **Write-only property:** has a setter without a getter; writable, not readable.
- **Nonexistent property:** cannot resolve a suitable member, so property access errors may be thrown.
- **Property with validating setter:** the setter itself can reject input and throw an exception; the wrapper does not "fix" setter logic.

Check before writing:

```java
if (!wrapper.isWritableProperty("name")) {
    throw new IllegalArgumentException("Property is not writable");
}
wrapper.setPropertyValue("name", "Binh");
```

This checks metadata-level accessibility, **not security or data validation**. If the property name is sent by a client, do not rely solely on `isWritableProperty` to decide what may be modified; use an explicit allowlist and application-level authorization.

### Reading Back to Confirm Changes

```java
wrapper.setPropertyValue("name", "Mai");
Object after = wrapper.getPropertyValue("name");
```

If the setter transforms input (e.g., `trim`), `after` may differ from the exact string passed in. The value after setting should be confirmed via the getter if business rules require it, rather than assuming the setter preserves every character.

## 5. Property Path Forms: Simple, Nested, Indexed, and Map

`BeanWrapper` supports complex **property paths**:

| Path | Meaning | Java type example |
| --- | --- | --- |
| `customerName` | Direct property on target | `String customerName` |
| `shipping.city` | `city` property of bean inside `shipping` | `Address shipping` |
| `lines[0].quantity` | `quantity` property of element 0 | `List<Line> lines` |
| `labels[channel]` | Map value at key `channel` | `Map<String,String> labels` |
| `codes[1]` | Element at index 1 in supported array/list | `String[] codes` |

Read examples:

```java
Object city = wrapper.getPropertyValue("shipping.city");
Object quantity = wrapper.getPropertyValue("lines[0].quantity");
Object label = wrapper.getPropertyValue("labels[channel]");
```

Write examples:

```java
wrapper.setPropertyValue("shipping.city", "Da Nang");
wrapper.setPropertyValue("lines[0].quantity", 4);
wrapper.setPropertyValue("labels[channel]", "mobile");
```

**A dot is not merely a string containing a field name.** Spring must traverse through the `shipping` object to reach `city`. If `shipping == null` and auto-creation of nested objects is disabled or cannot proceed, the operation can throw `NullValueInNestedPathException`.

**Indices must be valid.** `lines[0]` is the first element; do not assume the list has that index or that every object can be auto-created. Spring can auto-grow certain collections when configured, but you must account for limits, element types, constructors, and data safety.

**Map keys must be handled semantically.** For `Map<String,String> labels`, `labels[channel]` accesses key `"channel"`. Special keys containing syntax characters may need dedicated path handling; for untrusted input, restrict allowed keys/properties rather than concatenating arbitrary strings.

## 6. Complete Java 17+ Example: Reading and Writing All Four Property Forms

This is a console program using Spring Framework **6.2.12**. It demonstrates `getPropertyValue` and `setPropertyValue` on a simple property, nested bean, `List`, and `Map`, while using introspection to check readability/writability and property types.

Maven structure:

```text
beanwrapper-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── BeanWrapperDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>beanwrapper-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
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

Contents of `src/main/java/BeanWrapperDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.PropertyAccessorFactory;

public class BeanWrapperDemo {
    public static class Address {
        private String city;

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }

    public static class Line {
        private String sku;
        private int quantity;

        public String getSku() { return sku; }
        public void setSku(String sku) { this.sku = sku; }

        public int getQuantity() { return quantity; }
        public void setQuantity(int quantity) { this.quantity = quantity; }
    }

    public static class Checkout {
        private String customer = "An";
        private int count = 1;
        private Address shipping = new Address();
        private List<Line> lines = new ArrayList<>();
        private Map<String, String> labels = new LinkedHashMap<>();

        public Checkout() {
            shipping.setCity("Hue");

            Line first = new Line();
            first.setSku("BK1");
            first.setQuantity(1);
            lines.add(first);

            labels.put("channel", "web");
        }

        public String getCustomer() { return customer; }
        public void setCustomer(String customer) { this.customer = customer; }

        public int getCount() { return count; }
        public void setCount(int count) { this.count = count; }

        public Address getShipping() { return shipping; }
        public void setShipping(Address shipping) { this.shipping = shipping; }

        public List<Line> getLines() { return lines; }
        public void setLines(List<Line> lines) { this.lines = lines; }

        public Map<String, String> getLabels() { return labels; }
        public void setLabels(Map<String, String> labels) { this.labels = labels; }
    }

    public static void main(String[] args) {
        Checkout checkout = new Checkout();
        BeanWrapper wrapper =
                PropertyAccessorFactory.forBeanPropertyAccess(checkout);

        System.out.println("read.customer=" +
                wrapper.getPropertyValue("customer"));
        System.out.println("read.city=" +
                wrapper.getPropertyValue("shipping.city"));
        System.out.println("read.line=" +
                wrapper.getPropertyValue("lines[0].quantity"));
        System.out.println("read.label=" +
                wrapper.getPropertyValue("labels[channel]"));

        System.out.println("readable=" +
                wrapper.isReadableProperty("customer"));
        System.out.println("writable=" +
                wrapper.isWritableProperty("customer"));
        System.out.println("count.type=" +
                wrapper.getPropertyType("count").getSimpleName());

        wrapper.setPropertyValue("customer", "Binh");
        wrapper.setPropertyValue("count", "3");
        wrapper.setPropertyValue("shipping.city", "Da Nang");
        wrapper.setPropertyValue("lines[0].quantity", 2);
        wrapper.setPropertyValue("labels[channel]", "mobile");

        System.out.println("after.customer=" + checkout.getCustomer());
        System.out.println("after.count=" + checkout.getCount());
        System.out.println("after.city=" +
                checkout.getShipping().getCity());
        System.out.println("after.line=" +
                checkout.getLines().get(0).getQuantity());
        System.out.println("after.label=" +
                checkout.getLabels().get("channel"));
    }
}
```

Run from the `beanwrapper-demo` directory with JDK 17+ and Maven (the first run needs to download dependencies):

```bash
mvn -q compile exec:java -Dexec.mainClass=BeanWrapperDemo
```

Standard output from the `System.out.println` statements in the example:

```text
read.customer=An
read.city=Hue
read.line=1
read.label=web
readable=true
writable=true
count.type=int
after.customer=Binh
after.count=3
after.city=Da Nang
after.line=2
after.label=mobile
```

**Explanation of each operation:**

1. `PropertyAccessorFactory.forBeanPropertyAccess(checkout)` creates a wrapper pointing to the same `Checkout` instance.
2. `getPropertyValue("customer")` reads the direct property (via `getCustomer()`).
3. `getPropertyValue("shipping.city")` goes through getter `getShipping()` and then `getCity()`.
4. `getPropertyValue("lines[0].quantity")` gets the first element of `lines` and then reads its quantity.
5. `getPropertyValue("labels[channel]")` retrieves the value for key `channel` in the Map.
6. `isReadableProperty` and `isWritableProperty` check JavaBeans accessibility; `getPropertyType("count")` returns `int.class`.
7. `setPropertyValue("customer","Binh")` replaces the property value.
8. `setPropertyValue("count","3")` illustrates the common String-to-`int` conversion supported by Spring BeanWrapper.
9. The remaining set calls update the nested bean, list element, and Map entry; reading directly from `checkout` afterward confirms the wrapper updated the original target.

**Why use `String "3"` for `int count`?** It makes property type conversion visible. Spring provides property editors/type conversion mechanisms for common cases such as numeric strings to numeric types. If `"abc"` is passed for `int`, assignment can fail with `TypeMismatchException`; `setPropertyValue` does not return `false` or a `BindingResult` object.

**Verification scope:** this is a complete program with declared dependencies, unlike standalone API snippets in the article. Output is derived from the logic above and the getters/setters; when moving to another environment or changing converters/editors, run it to verify.

## 7. Knowing Types and Access Rights Upfront: Useful Introspection

Before reading/writing a dynamic property name, you can inspect what the wrapper has recognized:

```java
boolean canRead = wrapper.isReadableProperty("customer");
boolean canWrite = wrapper.isWritableProperty("customer");
Class<?> type = wrapper.getPropertyType("count");
```

`wrapper.getPropertyType(...)` returns the property type if determinable, or may return `null` when it cannot be resolved. For primitive `int`, `type.getSimpleName()` is `"int"`. For `List<Line>`, the base property type is `List`; to determine the generic element type or nested properties, rely on appropriate type descriptors/metadata rather than guessing from `List.class`.

A simple checking pattern:

```java
String path = "shipping.city";

if (!wrapper.isReadableProperty(path)) {
    throw new IllegalArgumentException("Cannot read: " + path);
}

Object value = wrapper.getPropertyValue(path);
```

This snippet is used in a context with `wrapper`. **Note:** checking beforehand does not guarantee the operation will always succeed; the getter can still throw, a nested target can change, or an object graph can be modified between calls.

### Read-Only and Write-Only Properties

```java
public class ExampleBean {
    private String token;

    public void setToken(String token) { this.token = token; }

    public String getMaskedToken() {
        return token == null ? "" : "****";
    }
}
```

This is an illustrative class definition. `token` has a setter without `getToken()`, so it is typically a **write-only property**; `maskedToken` has a getter without `setMaskedToken(...)`, so it is typically a **read-only property**. The wrapper can write `token` and read `maskedToken`; it cannot perform both directions by default for each property.

This example only explains accessibility. Real designs must avoid keeping sensitive tokens/passwords longer than necessary; do not use `BeanWrapper` as a security mechanism.

## 8. Nested Nulls, Auto-Grow, and Access Limits

With a target where `shipping == null`:

```java
wrapper.setPropertyValue("shipping.city", "Hue");
```

Without a way to instantiate the intermediate `Address`, Spring can throw `NullValueInNestedPathException`. When intentionally desired, BeanWrapper implementations support **auto-grow nested paths**:

```java
import org.springframework.beans.BeanWrapperImpl;

// Checkout and Address from the section 6 example.
Checkout form = new Checkout();
form.setShipping(null);

BeanWrapperImpl wrapper = new BeanWrapperImpl(form);
wrapper.setAutoGrowNestedPaths(true);
wrapper.setPropertyValue("shipping.city", "Hue");

System.out.println(form.getShipping().getCity()); // Hue
```

This snippet is self-contained in terms of call flow but requires the `Checkout` and `Address` classes from the full example. `Address` has a default no-arg constructor and a public setter, so nested instantiation succeeds under permitted conditions. If the child type is an interface/abstract class, lacks an appropriate constructor, or has no write path, auto-grow will not necessarily succeed.

For indexed properties, automatic collection growth must also be bounded and relies on the ability to infer/instantiate element types. Do not let client-controlled path strings freely request huge indices, as that can cause excessive memory consumption or unintended operations. For web binding, use DTOs, allowlists, and caps on the number of elements the application accepts.

### Immutable Objects / Records

```java
record Point(int x, int y) {}
```

A record has no setters for `x`/`y`, so it is not a natural target for `BeanWrapper.setPropertyValue("x", ...)`. Property reading may be supported depending on the introspection mechanism/version and accessor style, but **do not assume record components are writable JavaBean properties**.

When you want to bind into an immutable object, use **constructor binding** or instantiate a new instance via an appropriate constructor/builder. This is an object-creation concern and cannot be solved simply by calling `setPropertyValue` multiple times.

## 9. Type Conversion on Write and How to Configure It

`setPropertyValue` accepts `Object` while the target property has a specific type. Therefore the wrapper must check compatibility and may convert through Spring's mechanisms:

```text
input value: "3" (String)
          |
          v
setPropertyValue("count", "3")
          |
          v
PropertyDescriptor: count is int
          |
          v
TypeConverter / PropertyEditor / ConversionService (if configured)
          |
          v
setter setCount(3)
```

For example, `"3"` to `int` falls under common type conversions. Conversely, `"three"` to `int` cannot produce a valid number and can raise an error. For custom domain types, a `Converter` or `PropertyEditor` registered in the proper scope helps Spring understand how to convert; avoid scattering `instanceof` branches across calling layers.

Example applying `ConversionService` to a `BeanWrapperImpl`:

```java
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.core.convert.support.DefaultConversionService;

BeanWrapperImpl wrapper = new BeanWrapperImpl(target);
DefaultConversionService service = new DefaultConversionService();

wrapper.setConversionService(service);
wrapper.setPropertyValue("count", "3");
```

This is a **configuration illustration snippet**; `target` must be an instance with a numeric `count` property. `DefaultConversionService` contains many standard converters. For locale-aware formats such as `"1,5"` numbers or localized dates, `FormattingConversionService` and `Formatter` may be more appropriate; specify the locale and registration scope.

**Reading differs from writing:** `getPropertyValue` returns the property's existing value; it does not automatically format every value into UI display strings. To present numbers, dates, or currencies according to a `Locale`, use an appropriate formatter/View layer rather than overloading `getPropertyValue` semantics.

## 10. Property Access Errors: Identifying Instead of Swallowing Errors

Common error groups when using path-based APIs:

| Case | Common symptom/exception | How to handle |
| --- | --- | --- |
| Reading property with missing getter or nonexistent name | `NotReadablePropertyException` | Check path spelling and getter |
| Writing property with missing setter or non-writable | `NotWritablePropertyException` | Check setter/object design |
| Nested object is `null` | `NullValueInNestedPathException` | Initialize object or enable controlled auto-grow |
| Value type cannot be converted | `TypeMismatchException` or related conversion error | Check type, converter/editor, input |
| Out-of-bounds index or invalid path | `InvalidPropertyException` or other access error | Check collection, key, path, and limits |
| Getter/setter throws an exception | Exception wrapped/propagated by Spring depending on access branch | Inspect root cause in the accessor |
| Property modified concurrently | Inconsistent results | Avoid sharing unsynchronized mutable targets |

Specific exception types depend on the operation, path, and Spring version; the table is a **diagnostic guide**, not a promise of a single exception type for every case.

Purposeful handling example:

```java
import org.springframework.beans.NotWritablePropertyException;
import org.springframework.beans.TypeMismatchException;

try {
    wrapper.setPropertyValue("count", "abc");
} catch (NotWritablePropertyException ex) {
    // Property does not exist or lacks an appropriate write path.
} catch (TypeMismatchException ex) {
    // Value is incompatible and cannot be converted to the target type.
}
```

This snippet applies to an existing `wrapper`. In some configurations, errors may surface through related exception classes; recovery should rely on the root cause rather than only the exception name.

**Do not handle all errors with a catch-and-ignore block.** If a user entered invalid data, return an actionable error; if code used the wrong property path, fix the code and log appropriately. Swallowing errors leaves target state partially updated while the caller assumes success.

## 11. Writing Multiple Properties: Atomicity Is Not Guaranteed

`BeanWrapper` also supports `setPropertyValues(...)`, yet when invoking multiple setters, this is **not a transaction with rollback**:

```java
wrapper.setPropertyValue("customer", "Mai");
wrapper.setPropertyValue("count", "not-a-number");
```

The first call may have already changed `customer`; the second call can fail on type conversion. The target is then **partially modified**. Even when using `setPropertyValues(...)`, do not assume atomicity across multiple assignments.

For untrusted input or when business consistency is required:

1. Bind into an appropriate DTO, not directly into an actively managed entity.
2. Collect binding and validation errors.
3. Proceed to the service/domain layer only if the data is valid.
4. Design consistent transactions/state transitions at the appropriate business layer.

`BeanWrapper` provides property operations; it does not solve transactions, security, and consistency on its own.

## 12. How Does BeanWrapper Differ from DataBinder?

Spring's `DataBinder` builds on property access/conversion to manage binding input into a target, control allowed/disallowed fields, and place errors into `BindingResult`. `BeanWrapper` is closer to direct property reading/writing and usually **throws exceptions** on access/type conversion errors.

| Need | BeanWrapper | DataBinder |
| --- | --- | --- |
| Read dynamic property | `getPropertyValue(path)` | Not the primary API for reading individual properties |
| Write dynamic property | `setPropertyValue(path,value)` | `bind(PropertyValues)` |
| Nested/indexed paths | Yes, given a suitable object graph | Yes, per binding configuration |
| Convert types when needed | Has conversion/editor mechanism | Yes, via the binder |
| Collect binding errors as a result | Usually throws exceptions on direct calls | `getBindingResult()` |
| Invoke validators | Does not trigger validation automatically | `setValidator/addValidators`, then `validate()` |
| Restrict input fields | Caller protects paths/values manually | `setAllowedFields` for property binding |
| MVC controller integration | Usually the underlying mechanism | `WebDataBinder` is used by MVC |

A `DataBinder` snippet using the same idea:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

Checkout form = new Checkout();
DataBinder binder = new DataBinder(form, "checkout");
binder.setAllowedFields("customer", "count", "shipping.city");

MutablePropertyValues values = new MutablePropertyValues();
values.add("customer", "Mai");
values.add("count", "3");
values.add("shipping.city", "Da Nang");

binder.bind(values);
BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Handle binding errors instead of treating every exception as a system error.
}
```

This snippet is standalone in API usage but requires the `Checkout` class from section 6. To run business rules (e.g., `count > 0`), add an appropriate validator and call `binder.validate()` or use the MVC flow that triggers corresponding validation.

**Boundary to remember:** `@ModelAttribute` and `WebDataBinder` in Spring MVC serve form/query parameter binding; JSON `@RequestBody` typically goes through an HTTP message converter such as Jackson first. Do not treat `BeanWrapper.setPropertyValue` as the mandatory path for all JSON data in an application.

## 13. Safety When Property Names Come from Outside

A risky pattern:

```java
// Do not use for client-controlled property names.
wrapper.setPropertyValue(requestParameterName, requestParameterValue);
```

If the target has properties such as `admin`, `role`, `ownerId`, or `price`, client input can request writes to unintended fields. Even when `isWritableProperty` returns `true`, the caller **still needs business authorization** and an allowlist of permitted properties.

Minimum control when not using `DataBinder`:

```java
import java.util.Set;

Set<String> allowed = Set.of("customer", "count");
String path = requestParameterName;

if (!allowed.contains(path)) {
    throw new IllegalArgumentException("Field is not allowed to be updated");
}
wrapper.setPropertyValue(path, requestParameterValue);
```

This is an illustrative snippet: `requestParameterName` and `requestParameterValue` must be supplied by the caller, and the allowlist above matches only the corresponding contract. For nested paths, control **the entire path**, not just its prefix (allowing `shipping` does not mean permitting `shipping.internalFlag`).

In web applications, prefer DTOs/command objects containing only required input fields, restrict binding, and check permissions in the service layer. `BeanWrapper` is an access utility; it does not authenticate callers or determine which properties are business-valid.

## 14. When Should You Use getPropertyValue and setPropertyValue?

**Reasonable cases:**

- Mapping/transformation systems with a controlled property schema that need runtime reading/writing by name.
- Configuration tools or adapters reading bean metadata to display state, with proper allowlists.
- Framework infrastructure, binders, dynamic forms, or components needing nested property access.
- Tests/utilities inspecting JavaBean state without hardcoding every getter.

**Cases usually not needed:**

- Business logic where properties are known at compile time: call getters/setters directly.
- Updating immutable domain objects: use constructors/builders.
- Returning HTTP JSON: use a serializer with an explicit contract rather than accessing arbitrary properties.
- Writing request data into entities with sensitive fields: use DTOs, controlled binding, and services.

## 15. Checklist When Debugging Both Methods

| Symptom | Diagnostic question | Fix |
| --- | --- | --- |
| `getPropertyValue("x")` throws | Does `getX()/isX()` exist? Is the path right? | Check `isReadableProperty` and JavaBean conventions |
| `setPropertyValue("x",...)` fails to write | Is there a suitable setter? | Check `isWritableProperty` and setter |
| `shipping.city` fails | Is `shipping` initialized? | Initialize the object or enable auto-grow when reasonable |
| `lines[0].quantity` fails | Does the list have element 0? Does the element type have getters/setters? | Prepare the collection and enforce index limits |
| Assigning string to numeric type fails | Is conversion available for the target type? Is the string valid? | Check property type and converter/editor |
| Setter has unwanted effects | What logic is inside the getter/setter? | Read the implementation; avoid accidental repeated calls |
| Writing multiple fields leaves partial data | Was atomicity assumed? | Bind/validate on a DTO; perform controlled business updates |
| Record components cannot be set | Are there setters? | Use constructor binding or instantiate a new instance |
| Client can update disallowed fields | Are there an allowlist and permission checks? | Restrict field paths/DTOs and enforce authorization |

A practical workflow when troubleshooting errors:

1. Verify the **target instance** and actual runtime class being wrapped.
2. Print the intended **property path** (only when it contains no sensitive data).
3. Check `isReadableProperty`/`isWritableProperty` and `getPropertyType`.
4. Check that nested objects/lists/maps have the right structure.
5. For `setPropertyValue`, check the source type and conversion mechanism.
6. If the setter is invoked yet state is unexpected, inspect the setter's logic.
7. For user-supplied data, verify the allowlist and how actionable errors are returned.

## 16. Self-Check

**Question 1.** `getPropertyValue("name")` returns an `Object` that may be `null`. How do you distinguish a valid property whose value is null from an unreadable property?  
Use `isReadableProperty("name")` and check access errors; `null` is a valid value, whereas an invalid path can raise an exception.

**Question 2.** A JavaBean has `getCode()` but no `setCode(...)`. Can `code` be read and written?  
Usually readable, not writable; `isWritableProperty("code")` reflects the writable state.

**Question 3.** Given `lines` as a `List<Line>` containing a first element, what path should be used to update that element's `quantity`?  
`lines[0].quantity`. An item at index 0 and an appropriate write path for property `quantity` are required.

**Question 4.** Why can `setPropertyValue("count", "3")` succeed even though the setter takes `int`?  
BeanWrapper supports type conversion; valid numeric strings can be converted to `int` before calling the setter. That does not mean every string can be converted.

**Question 5.** `setPropertyValue("customer","Mai")` succeeds, and then setting `count` fails. Does Spring automatically roll back `customer`?  
No. `BeanWrapper` does not provide transactions over sets of property operations.

**Question 6.** Can `isWritableProperty` be used as a data-update permission check?  
No. It is metadata about JavaBean accessibility; update permissions must be decided by contract/authorization.

**Question 7.** When should you choose `DataBinder` instead of calling dozens of `setPropertyValue` calls?  
When you need to bind user input into a DTO, restrict fields, handle conversion errors centrally via `BindingResult`, and run validators according to the application workflow.

**Takeaway:** `getPropertyValue` **reads** via property paths; `setPropertyValue` **writes** via property paths and can convert types. Both calls operate on **the current target**, can traverse **nested/indexed/Map paths**, are subject to runtime access errors, and **do not replace validation, authorization, or transactions**.

## Official References

- [Spring Framework — BeanWrapper and JavaBeans API](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html)
- [Spring Framework — BeanWrapper interface (Javadoc 6.2)](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/BeanWrapper.html)
- [Spring Framework — PropertyAccessor interface (Javadoc 6.2)](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/PropertyAccessor.html)
- [Spring Framework — BeanWrapperImpl (Javadoc 6.2)](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework — PropertyAccessorFactory (Javadoc 6.2)](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/PropertyAccessorFactory.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
