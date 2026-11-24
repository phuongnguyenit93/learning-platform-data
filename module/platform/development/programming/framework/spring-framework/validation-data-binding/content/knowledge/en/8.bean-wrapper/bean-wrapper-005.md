# BeanWrapper: Reading or Setting Multiple Property Values in Spring Framework

> **Scope:** Spring Framework, `BeanWrapper` family. This article focuses on reading multiple properties by name, bulk writing via `PropertyValues`/`Map`, nested properties, type conversion, error behavior, and safe usage. Examples use Java 17 and Spring Framework 6.2.x.

## 1. The Problem and How BeanWrapper Solves It

Suppose an application has a `Customer` object with properties `name`, `age`, `active`, and `address.city`. Data from an external source includes:

```text
name         = "Linh"
age          = "28"
active       = "true"
address.city = "Da Nang"
```

You could manually call each setter after converting types. However, when a program processes configuration or a map containing many properties, you may not want to hardcode calls for each field. Spring provides **`BeanWrapper`**, an interface for working with JavaBeans via **property names**.

Two main needs:

- **Reading multiple values:** take a list of property names and call `getPropertyValue(name)` one by one, placing results into a controlled map. `BeanWrapper` does not have a `getPropertyValues()` method that is completely symmetric to the bulk-setter method.
- **Setting multiple values:** prepare a `Map` or `PropertyValues`, then call `setPropertyValues(...)`. Spring attempts to locate setters/property paths, convert types, and assign the values onto the wrapped object.

`BeanWrapper` operates **on an existing Java object**. It does not parse HTTP requests itself, does not check permissions itself, does not run full Bean Validation automatically, does not create transactions, and does not replace the business layer.

## 2. Important Interfaces and Classes

| Component | Role |
| --- | --- |
| `BeanWrapper` | Spring Beans interface for JavaBeans property access, resolving types, getters/setters, and nested paths. |
| `BeanWrapperImpl` | Common implementation when wrapping an instance and reading/writing properties by name. |
| `PropertyAccessor` | Defines `getPropertyValue`, `setPropertyValue`, `setPropertyValues`, and inspection methods. |
| `PropertyValues` | Collection of elements holding property names/values; standard input for bulk updates. |
| `MutablePropertyValues` | Implementation allowing property pairs to be added/modified before binding. |
| `PropertyValue` | Represents a single property name-and-value pair. |
| `PropertyBatchUpdateException` | Exception aggregating property access errors during a batch update for recoverable error types. |
| `PropertyDescriptor` | JavaBeans metadata: property name and read/write methods. |

Initialization:

```java
Customer customer = new Customer();
BeanWrapper wrapper = new BeanWrapperImpl(customer);
```

`BeanWrapperImpl(customer)` wraps `customer` itself. Writing properties through `wrapper` mutates that same instance.

### JavaBeans Properties Differ from Direct Fields

For property `name`, standard JavaBeans access relies on `getName()` and `setName(String)`. A `private` field without an appropriate setter is not automatically writable merely because Java reflection can see it.

`BeanWrapper` supports nested properties such as `address.city`. It also supports indexed/keyed access for appropriately declared collection/map objects.

## 3. Reading a Single Property with `getPropertyValue`

```java
Object a = wrapper.getPropertyValue("name");
Object b = wrapper.getPropertyValue("age");
Object c = wrapper.getPropertyValue("address.city");
```

Each call reads one property path. The result is typed as `Object` and may be `null`. If the target property is `int`, the returned value is boxed as an `Integer`. For nonexistent or unreadable properties, Spring can raise `InvalidPropertyException` or an appropriate subclass; if a getter throws an exception, a corresponding property access error may occur.

Before reading, you can query the wrapper:

```java
boolean readable = wrapper.isReadableProperty("name");
Class<?> type = wrapper.getPropertyType("age");
```

`isReadableProperty` asks whether a valid read path exists for the property. `getPropertyType` provides the determinable property type without reading its value. Pre-checking helps produce clearer error messages; in mutable/concurrent environments you must still handle errors occurring during actual access.

## 4. Reading Multiple Properties Using a List of Names

`BeanWrapper` does not automatically return a map of all properties via a method named `getPropertyValues()`. The clearest approach is to choose the fields to retrieve and iterate:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

List<String> selected = List.of(
        "name", "age", "active", "address.city");

Map<String, Object> values = new LinkedHashMap<>();
for (String path : selected) {
    values.put(path, wrapper.getPropertyValue(path));
}
```

`LinkedHashMap` has two benefits: it preserves the name list order and permits `null` values. Do not use `Map.of(...)` if any property may be `null`.

If property names come from a client, **do not pass that list directly to the wrapper**. Filter the list against an allowlist, because a JavaBean can contain private information that the client is not authorized to read.

### Reading Properties Listed via Metadata

When handling a JavaBean whose structure is unknown at compile time, you can use `getPropertyDescriptors()`:

```java
import java.beans.PropertyDescriptor;
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Object> snapshot = new LinkedHashMap<>();
for (PropertyDescriptor descriptor
        : wrapper.getPropertyDescriptors()) {

    String property = descriptor.getName();
    if (!"class".equals(property)
            && wrapper.isReadableProperty(property)) {
        snapshot.put(property, wrapper.getPropertyValue(property));
    }
}
```

This is merely an introspection technique. **Do not treat every getter as a public field safe to return in JSON or logs**: getters may be sensitive, expensive to compute, have side effects, or return large object graphs. `PropertyDescriptor` also does not guarantee business ordering. In production APIs, prefer explicit field lists or output DTOs.

**Note on consistency:** looping to read multiple properties performs sequential operations, not an atomic snapshot. If other threads modify the same bean, a map may contain values read at different instants. For a consistent snapshot, use an immutable snapshot/copy or appropriate synchronization.

## 5. Setting Individual Properties with `setPropertyValue`

```java
wrapper.setPropertyValue("name", "Linh");
wrapper.setPropertyValue("age", "28");
wrapper.setPropertyValue("active", "true");
```

On a suitable JavaBean with appropriate property editors/converters, Spring can convert `"28"` to `int 28` and `"true"` to `boolean true`.

An overload takes a `PropertyValue`:

```java
import org.springframework.beans.PropertyValue;

wrapper.setPropertyValue(
        new PropertyValue("name", "Linh"));
```

Both approaches handle one field at a time. When you need to write multiple fields in a single API call, use `setPropertyValues(...)`.

## 6. Setting Multiple Properties with `MutablePropertyValues`

```java
import org.springframework.beans.MutablePropertyValues;

MutablePropertyValues updates = new MutablePropertyValues();
updates.add("name", "Linh");
updates.add("age", "28");
updates.add("active", "true");
updates.add("address.city", "Da Nang");

wrapper.setPropertyValues(updates);
```

`MutablePropertyValues` holds name/value items. When `setPropertyValues` is called, the wrapper applies the set of values to the target; property paths use JavaBean property names (`name`, `age`, `address.city`), not local variable names or MVC model attribute names.

You can also pass a map directly:

```java
Map<String, Object> updates = new LinkedHashMap<>();
updates.put("name", "An");
updates.put("age", "30");

wrapper.setPropertyValues(updates);
```

| API | Meaning |
| --- | --- |
| `setPropertyValue("name", value)` | Single property. |
| `setPropertyValue(new PropertyValue(name, value))` | Single packaged property. |
| `setPropertyValues(Map<?, ?>)` | Convenient bulk update from a map. |
| `setPropertyValues(PropertyValues)` | Bulk update using the `PropertyValues` structure preferred by the API. |
| `setPropertyValues(pvs, ignoreUnknown)` | Adds a policy to ignore unknown property names. |
| `setPropertyValues(pvs, ignoreUnknown, ignoreInvalid)` | Adds a policy for inaccessible property paths. |

Both `Map` and `MutablePropertyValues` can update multiple fields. Choose `PropertyValues` when integrating with other Spring APIs that accept `PropertyValues`, or when you want fine-grained control over each `PropertyValue`. Choose a map when the data source is already a map, while always filtering allowed keys.

## 7. Runnable Java 17 Example with Maven

The following example uses Spring Beans, without needing Spring MVC or booting Spring Boot. Create:

```text
beanwrapper-bulk-demo/
  pom.xml
  src/main/java/demo/BeanWrapperBulkDemo.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>beanwrapper-bulk-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/java/demo/BeanWrapperBulkDemo.java`

```java
package demo;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;

public final class BeanWrapperBulkDemo {

    public static final class Address {
        private String city;

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }

    public static final class Customer {
        private String name;
        private int age;
        private boolean active;
        private Address address = new Address();

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }

        public int getAge() { return age; }
        public void setAge(int age) { this.age = age; }

        public boolean isActive() { return active; }
        public void setActive(boolean active) { this.active = active; }

        public Address getAddress() { return address; }
        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static void main(String[] args) {
        Customer customer = new Customer();
        BeanWrapper wrapper = new BeanWrapperImpl(customer);

        MutablePropertyValues changes = new MutablePropertyValues();
        changes.add("name", "Linh");
        changes.add("age", "28");
        changes.add("active", "true");
        changes.add("address.city", "Da Nang");

        // Set four values in a single call.
        wrapper.setPropertyValues(changes);

        // Read back those same four properties by name.
        List<String> keys = List.of(
                "name", "age", "active", "address.city");
        Map<String, Object> snapshot = new LinkedHashMap<>();
        for (String key : keys) {
            snapshot.put(key, wrapper.getPropertyValue(key));
        }

        System.out.println("sameObject="
                + (wrapper.getWrappedInstance() == customer));
        snapshot.forEach((key, value) ->
                System.out.println(key + "=" + value));
        System.out.println("ageType="
                + wrapper.getPropertyType("age").getSimpleName());
        System.out.println("cityWritable="
                + wrapper.isWritableProperty("address.city"));
    }
}
```

In the `beanwrapper-bulk-demo` directory, run with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BeanWrapperBulkDemo
```

**Stdout from the program** (excluding Maven's own logs if configured to display differently):

```text
sameObject=true
name=Linh
age=28
active=true
address.city=Da Nang
ageType=int
cityWritable=true
```

Points to observe:

1. `getWrappedInstance() == customer` is `true`: the wrapper operates on the exact instance passed in.
2. `age` and `active` have types `int`/`boolean`; the initial string values are converted to the target types.
3. `address.city` goes through `getAddress()` and the nested bean's `setCity(...)`.
4. `getPropertyValue(...)` returns the assigned values, and `LinkedHashMap` preserves print order.
5. `isWritableProperty("address.city")` verifies that the path exists and is writable.

**The program above requires the `spring-beans` dependency**; running plain `javac` without the Spring classpath will not compile. Other snippets in this guide mainly illustrate API usage within an application and assume `wrapper`/`pvs` variables are already declared.

## 8. Nested, Indexed, and Mapped Properties

`BeanWrapper` uses property paths:

| Path | Interpretation |
| --- | --- |
| `name` | Direct property. |
| `address.city` | `city` of nested bean `address`. |
| `addresses[0].city` | `city` of the first element of array/list `addresses`. |
| `phones[1]` | Element at index 1 of an index-supported ordered collection. |
| `attributes[department]` | Key `department` of a map property `attributes`. |

A path is valid only when the actual target has the matching structure/types. Using a nested path does not mean a JavaBean always has nested objects pre-populated.

### When a Nested Object Is Null

If `getAddress() == null`, reading or writing `address.city` can trigger `NullValueInNestedPathException`. For a plain property accessor, auto-grow nested paths is normally **disabled** by default.

You can configure:

```java
wrapper.setAutoGrowNestedPaths(true);
wrapper.setPropertyValue("address.city", "Hue");
```

The auto-grow mechanism can instantiate intermediate objects if their types and constructors support it. Not every path can be auto-created. With untrusted user data, do not arbitrarily enable auto-grow and accept arbitrary paths; it can expand the object graph unexpectedly.

The full example pre-initializes `new Address()`, so auto-grow is not needed.

## 9. Bulk Update Errors and Non-Atomicity

**This is the biggest difference from assuming "set multiple fields in one transaction":** `setPropertyValues(...)` does not guarantee all-or-nothing semantics.

Per the `PropertyAccessor` Javadoc, when a batch encounters recoverable errors such as conversion/type mismatch, Spring may continue updating other properties and then throw `PropertyBatchUpdateException` collecting the `PropertyAccessException`s. Fields that succeeded **may already be modified on the target**.

State example:

```text
Before: name="Old", age=18, active=false
Input:  name="New", age="abc", active="true"

name   -> may be assigned successfully
age    -> cannot convert to int
active -> may still be assigned

Result: batch reports errors, yet some fields already changed.
```

Error-handling snippet (illustrated inside a method that already has `wrapper` and `pvs`):

```java
import org.springframework.beans.PropertyAccessException;
import org.springframework.beans.PropertyBatchUpdateException;

try {
    wrapper.setPropertyValues(pvs);
} catch (PropertyBatchUpdateException ex) {
    for (PropertyAccessException error
            : ex.getPropertyAccessExceptions()) {
        System.out.println("Field: " + error.getPropertyName());
        System.out.println("Type: "
                + error.getClass().getSimpleName());
    }
    // Do not proceed to save the target as if the entire batch were valid.
}
```

Do not infer that **every kind of error** is collected in this exception. Nonexistent or non-writable properties can raise `InvalidPropertyException` / `NotWritablePropertyException` and halt the batch depending on the situation; getters/setters can throw other exceptions.

### When You Need All-or-Nothing

A safer workflow:

1. Check the allowed field list, parsing/conversion, and validation on a DTO or temporary copy.
2. If there are errors, return the result without modifying the original domain object.
3. If everything is valid, apply the changes to the domain according to the controlled use case.
4. For persisting multiple records, use proper DB transactions/locking. BeanWrapper itself cannot replace transactions.

Do not call `setPropertyValues` again on the same partially updated object without understanding its current state.

## 10. Overloads That Ignore Unknown/Invalid Fields

`PropertyAccessor` allows:

```java
wrapper.setPropertyValues(pvs);
wrapper.setPropertyValues(pvs, true);
wrapper.setPropertyValues(pvs, false, true);
wrapper.setPropertyValues(pvs, true, true);
```

In the three-parameter overload:

- Second parameter `ignoreUnknown`: allows ignoring property names not found on the bean.
- Third parameter `ignoreInvalid`: allows ignoring certain known property paths that cannot be accessed, such as a nested path missing an intermediate object, depending on implementation capabilities.

| Situation | Decision |
| --- | --- |
| `nmae` misspelled instead of `name` | Usually should fail to expose contract mismatches. |
| Optional field absent in an older DTO version | `ignoreUnknown` can be helpful if permitted by the contract. |
| Nested object `address` is `null` | Initialize explicitly or apply an appropriate ignore/auto-grow policy. |
| `age="xyz"` cannot convert type | Not an unknown property; handle as a conversion error. |
| Read-only field | Cannot be written merely because the property name exists. |

Do not abuse `ignoreUnknown=true` as a "accept whatever comes in" mechanism. It can hide typos, API version conflicts, and silently dropped data. Nor do the flags mean ignoring all errors or providing rollback.

## 11. Type Conversion When Writing Multiple Properties

`BeanWrapperImpl` has default property editors and can use a configured conversion service. With the JavaBean in the example, strings `"28"` and `"true"` are converted to `int` and `boolean`.

| Input | Target type | Expected behavior |
| --- | --- | --- |
| `"28"` | `int` | Converts to `28`. |
| `"false"` | `boolean` | Converts to `false`, not treated as missing. |
| `"abc"` | `int` | Reports type conversion error. |
| `"2026-11-02"` | `LocalDate` | Depends on configured converters/formatters; do not assume every format is always supported. |
| `"1,234.50"` | `BigDecimal` | Requires locale/format rules and a suitable converter. |

If a standard conversion service is needed:

```java
import org.springframework.core.convert.support.DefaultConversionService;

wrapper.setConversionService(new DefaultConversionService());
```

This snippet assumes `wrapper` has already been created. For specialized types, numbers, currencies, dates/times, or domain types, appropriate custom formatters/converters are required.

**Successful conversion does not mean a valid value.** `age="-5"` can convert to the number `-5`, yet business logic must still reject it if age must be non-negative. `BeanWrapper` does not automatically run Jakarta Bean Validation constraints.

## 12. Checking Readability, Writability, and Property Type

Three key APIs:

```java
boolean canRead = wrapper.isReadableProperty("name");
boolean canWrite = wrapper.isWritableProperty("age");
Class<?> type = wrapper.getPropertyType("age");
```

- `isReadableProperty(...)` confirms a property read path is supported by bean metadata.
- `isWritableProperty(...)` confirms a property write path is supported.
- `getPropertyType(...)` provides the determinable declared type.

A JavaBean with `getId()` and no `setId(...)` can be **readable, not writable**. A property with only a setter can be **writable, not readable**. Intermediate objects in nested paths must also be accounted for.

Do not use `isWritableProperty` as a substitute for authorization. "Has a setter" does not mean the user is allowed to update it. Likewise, `isReadableProperty` does not mean the property is safe to expose publicly.

## 13. Combining with DataBinder and Spring MVC

`BeanWrapper` is a low-level manipulation tool. `DataBinder` adds target binding coordination and accumulates errors in `BindingResult`:

| Task | BeanWrapper | DataBinder |
| --- | --- | --- |
| Read property by name | `getPropertyValue` | Not its primary direct API purpose. |
| Bulk write | `setPropertyValues` | `bind(PropertyValues)`. |
| Type conversion errors | Throws exceptions, may group into `PropertyBatchUpdateException`. | Records errors in `BindingResult` per binding rules. |
| Allow only specific fields | Filter keys before calling wrapper. | `setAllowedFields(...)`. |
| Validation | Must be organized separately. | Has APIs to set validators and call `validate()`; MVC has its own lifecycle. |

When the source is an HTTP request in Spring MVC, you should usually use `@ModelAttribute`/`@RequestBody`, DTOs, and framework-managed binding/validation. There is no need to manually create a BeanWrapper simply because a request has many fields.

If building a map→JavaBean mapping pipeline outside MVC (such as a config importer), `BeanWrapperImpl` fits well when you genuinely need runtime property lookup by name and flexible type conversion.

## 14. Security: Do Not Blindly Bind Every Field from Clients

This issue is commonly called **mass assignment**. If an object has fields such as `role`, `isAdmin`, `ownerId`, or `creditLimit` with setters, a client-supplied map can attempt to write them via `setPropertyValues(...)`.

Enforce an allowlist:

```java
import java.util.Set;
import org.springframework.beans.MutablePropertyValues;

// input: Map<String, ?> from a known source.
// wrapper: BeanWrapper wrapping an appropriate DTO.
Set<String> allowed =
        Set.of("name", "age", "address.city");
MutablePropertyValues accepted = new MutablePropertyValues();

for (var entry : input.entrySet()) {
    String field = entry.getKey();
    if (!allowed.contains(field)) {
        throw new IllegalArgumentException(
                "Unsupported property: " + field);
    }
    accepted.add(field, entry.getValue());
}
wrapper.setPropertyValues(accepted);
```

This snippet only illustrates the allowlist mechanism and must be placed in a context with `input` and `wrapper`. It does not replace validation, action authorization, nested path/index checks, or batch exception handling.

Measures to combine:

1. Use **input DTOs** containing strictly the allowed fields; avoid binding entities directly.
2. Validate against the allowed field list before building `PropertyValues`.
3. Do not allow clients to craft arbitrary deep property paths or array indices.
4. Bound input size and object graph depth.
5. After binding, validate values and enforce business rules.
6. Do not dump all properties via reflection into APIs or logs.

## 15. Bulk Reading/Writing with Partial Updates

In updates or PATCH operations, distinguish:

- **Absent key:** typically preserves the existing value.
- **Key present with `null`:** may mean clearing the field or invalid data.
- **Key present with `""`:** an empty string, not automatically equivalent to absent.
- **Key with value `0` or `false`:** may be a valid selection and must be preserved.

A `Map` passed to `setPropertyValues(...)` should contain only keys that are genuinely permitted to change. If default values were unintentionally pre-populated for all fields beforehand, binding can corrupt existing state.

If before-and-after comparison is needed, capture a snapshot of the values to compare **before writing**. Because the wrapper wraps the same mutable object, keeping a reference `Customer old = customer` and then mutating via the wrapper does not create a pre-update snapshot.

## 16. Testing and Common Design Mistakes

| Test case | Expectation |
| --- | --- |
| Reading `name` and `age` by list | Map contains exact names and values. |
| `setPropertyValues` from `MutablePropertyValues` | Valid fields are updated. |
| `setPropertyValues(Map)` | Equivalent result for the name-value pairs. |
| `age="28"` | Converts to `int 28`. |
| `age="abc"` | Type mismatch error; must not report success. |
| Batch with valid and invalid fields | Partial update may occur; check both exception and bean state. |
| Nested `address.city` when `address` exists | Reads/writes successfully. |
| Nested `address.city` when `address==null` | Verify auto-grow/exception behavior without assuming unconditional success. |
| Nonexistent property | Errors by default, or ignored when using `ignoreUnknown`. |
| Getter-only property | `isWritableProperty` is false; cannot be written. |
| Input contains `role` key outside allowlist | Must be rejected before binding. |
| Getter returns sensitive data | Must not be exposed via bulk-read APIs. |

Mistakes to avoid:

**Pitfall 1:** Expecting a `getPropertyValues()` method to fetch all fields. Loop `getPropertyValue(name)` or inspect metadata and filter instead.

**Pitfall 2:** Assuming `setPropertyValues(...)` updates atomically. There is no automatic rollback for JavaBeans.

**Pitfall 3:** Using a private field with no setter and thinking BeanWrapper can always write it. Understand JavaBeans property accessors.

**Pitfall 4:** Using `ignoreUnknown` to mask typos or data contract mismatches.

**Pitfall 5:** Binding client objects directly onto entities or privileged properties without field controls.

**Pitfall 6:** Forgetting that `address.city` requires the nested object to exist or an appropriate auto-grow policy.

**Pitfall 7:** Trusting automatic type conversion to cover every date/time, currency, and domain format.

**Pitfall 8:** Treating successful type conversion as successful business validation.

**Pitfall 9:** Sharing a mutable wrapper across multiple requests/threads to write to the same object without consistency mechanisms.

**Pitfall 10:** Applying property binding to records/immutable DTOs as if they had setters. For immutable objects, use an appropriate constructor mapping/binding mechanism.

## 17. Practical Checklist

1. Identify the JavaBean instance to manipulate and create `BeanWrapperImpl(target)`.
2. When **reading multiple values**, prepare a trusted list of property names; loop `getPropertyValue` and store in a `LinkedHashMap` if needed.
3. When **setting multiple values**, prepare `MutablePropertyValues` or a key-filtered `Map`.
4. Verify property names, writable/readable metadata, and nested paths.
5. Configure converters/formatters before writing if properties have specialized types.
6. Call `setPropertyValues` and handle errors that could leave the bean partially modified.
7. Validate results, apply business rules, and persist via an appropriate transaction if needed.
8. Only read/write fields that the user or data source is genuinely authorized to access.

**Takeaway:** `getPropertyValue(name)` reads **one** property; to read many, **iterate selectively**. `setPropertyValues(...)` sets **multiple** properties; it provides conversion and error reporting, **without guaranteeing all-or-nothing atomicity**.

## Official API References

- [Spring Framework Reference – Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework 6.2.14 – AbstractPropertyAccessor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/AbstractPropertyAccessor.html): `setPropertyValues` overloads and batch error behavior.
- [Spring Framework 6.0.23 – BeanWrapperImpl](https://docs.spring.io/spring-framework/docs/6.0.23/javadoc-api/org/springframework/beans/BeanWrapperImpl.html): implementation and constructors.
- [Spring Framework 6.2.14 – BeanWrapper](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapper.html): wrapper API and property metadata.
