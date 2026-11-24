# PropertyValue, PropertyValues, and MutablePropertyValues in Spring DataBinder

When you need to pass multiple **property name → value** pairs into a Java object, Spring Framework uses three types from the `org.springframework.beans` package:

- **`PropertyValue`**: describes **a single** proposed value to assign to a property, consisting of a name and a value.
- **`PropertyValues`**: an interface representing a **collection of `PropertyValue` items**, allowing iteration, lookup, existence checks, and comparison of supplied values.
- **`MutablePropertyValues`**: the common implementation of `PropertyValues`, allowing you to **add, replace, and remove** entries and pass directly into `DataBinder.bind(...)`.

In the data binding flow, they act as **containers for input data**. It is `DataBinder` and Spring's property-access/conversion system that decide which fields get assigned, how types are converted, and what errors occur. Creating `MutablePropertyValues` **does not automatically modify a JavaBean**.

## 1. The Big Picture

Suppose a form request has three parameters:

~~~http
POST /registrations
Content-Type: application/x-www-form-urlencoded

name=Lan&age=23&admin=true
~~~

To make it easy to visualize, you can picture the input part like this:

~~~text
                         name                initial value
                    ┌────────────────┬──────────────────────┐
                    │ "name"         │ "Lan"                │
PropertyValues ──── │ "age"          │ "23"                 │
                    │ "admin"        │ "true"               │
                    └────────────────┴──────────────────────┘
                           |
                           v
                 DataBinder + configuration
                 ├─ allowed fields
                 ├─ convert String → int
                 ├─ assign via setter
                 └─ BindingResult
                           |
                           v
                 RegistrationForm bean
                 name = "Lan", age = 23
                 admin = false (blocked)
~~~

This is a **conceptual diagram**, not a guarantee that HTTP always directly constructs a `MutablePropertyValues` in this exact way. In Spring MVC, `WebDataBinder` and request parameter argument resolvers coordinate that process. In plain Java, you can construct `MutablePropertyValues` yourself and call `DataBinder.bind(...)`.

**Two important boundaries:**

1. `PropertyValues` holds **proposed assignments**, including raw values like `"23"` as a `String`.
2. The target object is updated **only when binding is applied**; if a property requires `int`, the type converter converts `"23"` → `23`. `PropertyValue` itself does not guarantee type conversion has happened.

## 2. PropertyValue — A Single Name-and-Value Pair

A `PropertyValue` is created with:

~~~java
import org.springframework.beans.PropertyValue;

PropertyValue pv = new PropertyValue("age", "23");

System.out.println(pv.getName());                 // age
System.out.println(pv.getValue());                // 23 (still a String)
System.out.println(pv.getValue() instanceof String); // true
~~~

This is a **snippet**; to run it, place it inside a method with Spring `spring-beans` on the classpath. The two constructor parameters are:

| Component | Meaning | Example |
| --- | --- | --- |
| `name` | Target property name or property path | `"age"`, `"address.city"` |
| `value` | Value object to apply, possibly not yet converted | `"23"`, `Integer.valueOf(23)` |
| `getName()` | Returns the property name | `"age"` |
| `getValue()` | Returns the supplied raw value | `"23"` |

`PropertyValue` also has a copy constructor `new PropertyValue(existing)` and a constructor linking to a new value `new PropertyValue(existing, newValue)`, useful in internal mechanisms that need to track value origin.

Some advanced properties/methods such as `setOptional(boolean)`, `isOptional()`, `setConvertedValue(...)`, or `getConvertedValue()` serve property access and conversion internals. They do **not** mean calling `setOptional(true)` bypasses authorization or validation checks. Most application code only needs the constructor and the two getters.

**Do not confuse:** `new PropertyValue("age", "23")` does not call `setAge(...)` on any object. It only creates a value descriptor for another component to process later.

## 3. PropertyValues — Contract for a Collection of Values

`PropertyValues` is an **interface**, not a class you instantiate with `new PropertyValues()`. It extends `Iterable<PropertyValue>` and provides typical read/lookup operations:

| API | Result |
| --- | --- |
| `getPropertyValues()` | Array `PropertyValue[]` representing the contained entries |
| `getPropertyValue("age")` | The `PropertyValue` with the matching name, or `null` if not found |
| `contains("age")` | Checks whether an entry or handling info exists for that name |
| `isEmpty()` | Whether the collection of entries is empty |
| `iterator()`, `stream()` | Iterate/stream over the entries |
| `changesSince(old)` | Collection of values that are **new or changed** compared to the old snapshot |

Example:

~~~java
PropertyValues values = new MutablePropertyValues()
        .add("name", "Lan")
        .add("age", "23");

System.out.println(values.contains("age")); // true
System.out.println(values.isEmpty());       // false

for (PropertyValue pv : values) {
    System.out.println(pv.getName() + "=" + pv.getValue());
}
~~~

The statements above are a **snippet inside a method** with `PropertyValue`, `PropertyValues`, and `MutablePropertyValues` imported. In an implementation like `MutablePropertyValues`, each property name typically has one entry; adding the same name again replaces the corresponding value (or performs merge rules when configured).

**Note on the interface type:** typing a variable as `PropertyValues` keeps code dependent only on the read and lookup contract, but does not make the actual object immutable. If the underlying implementation is still `MutablePropertyValues` and another place holds the same reference, the data can be mutated. To keep an isolated snapshot, create `new MutablePropertyValues(original)`; even this constructor does not deep-copy nested objects inside the values.

## 4. MutablePropertyValues — Editable Collection of Values

`MutablePropertyValues` is the default/common implementation of `PropertyValues`. Ways to initialize it:

~~~java
MutablePropertyValues empty = new MutablePropertyValues();

MutablePropertyValues fromMap = new MutablePropertyValues(
        java.util.Map.of("name", "Lan", "age", "23"));

MutablePropertyValues copy = new MutablePropertyValues(fromMap);
~~~

You can add pairs one by one using the fluent API returning the holder itself:

~~~java
MutablePropertyValues pvs = new MutablePropertyValues()
        .add("name", "Lan")
        .add("age", "23")
        .add("active", "true");

pvs.addPropertyValue(new PropertyValue("city", "Hue"));
pvs.add("age", "24");             // replaces existing "age" entry
pvs.removePropertyValue("active");
~~~

| API | Usage |
| --- | --- |
| `add(String, Object)` | Adds/replaces a value and **returns `MutablePropertyValues`** for chaining |
| `addPropertyValue(PropertyValue)` | Adds/replaces using a pre-created `PropertyValue`; returns the holder |
| `addPropertyValue(String, Object)` | Two-parameter overload, **returns `void`** (not chainable); `add(...)` is usually cleaner |
| `addPropertyValues(Map<?, ?>)` | Loads multiple pairs from a map; keys must be `String` property names |
| `addPropertyValues(PropertyValues)` | Copies entries from another holder into this one |
| `removePropertyValue(String)` | Removes an entry by name |
| `getPropertyValue(String)`, `get(String)` | Returns the `PropertyValue` wrapper or raw value, respectively |
| `size()` | Current number of `PropertyValue` entries |
| `changesSince(PropertyValues)` | Retrieves only new/changed entries compared to a reference set |
| `getPropertyValueList()` | Direct access to the internal list; **do not modify the list directly** in normal code |

For example, `pvs.get("age")` returns the raw value `"24"`; `pvs.getPropertyValue("age")` returns the `PropertyValue` object to further read `getName()` and `getValue()`.

**Duplicate names issue:** adding `age` twice usually **does not create two independent age properties**; the existing entry is replaced or merged according to the corresponding `PropertyValue` rules. If you want multiple values for a single HTTP parameter, use an appropriate value type (e.g., array/list) and multi-value handling rather than assuming `MutablePropertyValues` preserves every occurrence of the same key.

### Copying vs. Sharing References

~~~java
MutablePropertyValues source = new MutablePropertyValues()
        .add("name", "Lan");

MutablePropertyValues copy = new MutablePropertyValues(source);
copy.add("name", "Minh");

System.out.println(source.get("name")); // Lan
System.out.println(copy.get("name"));   // Minh
~~~

The copy constructor creates independent `PropertyValue` wrappers; changing a property's value in the new holder does not mutate the wrapper in the old holder. However, if the value is **a mutable object**, both wrappers can still point to the same underlying object. This **is not a deep copy of the entire object graph**.

### changesSince Only Detects Additions and Modifications

~~~java
MutablePropertyValues oldValues = new MutablePropertyValues()
        .add("name", "Lan")
        .add("age", "23")
        .add("admin", "true");

MutablePropertyValues newValues = new MutablePropertyValues(oldValues)
        .add("name", "Minh");
newValues.removePropertyValue("admin");

PropertyValues changed = newValues.changesSince(oldValues);

System.out.println(changed.contains("name"));  // true
System.out.println(changed.contains("age"));   // false
System.out.println(changed.contains("admin")); // false
~~~

`changesSince` returns entries present in the new set that were **newly added or had their values changed**. It is not a two-way diff reporting removed keys as well. Therefore, `changed.contains("admin") == false` **does not prove** the `admin` key is still present; `admin` was removed from `newValues` but is not represented as a changed entry in the result set.

If you want a full audit of additions/edits/deletions, compare both sides: the old and new key sets, along with classifying changed values.

## 5. From PropertyValues to DataBinder: A Runnable Java 17 Example

This is a **plain Java example using Spring Framework libraries** to observe the full flow:

1. Build data as `MutablePropertyValues`; read via the `PropertyValues` interface.
2. Keep a snapshot before binding.
3. Create a `DataBinder` for a JavaBean with getters/setters.
4. Only allow binding the `name` and `age` fields; disallow `admin`.
5. Let Spring convert `"23"` into the JavaBean's `int` type.
6. Read `BindingResult` and compare data before/after.

### 5.1. Create the Maven Project

Create `pom.xml`, using **JDK 17+**. To keep the example reproducible, Spring dependencies are managed through a single artifact `spring-context` at Spring Framework version **6.2.19**; this is a concrete version for the example, not a claim about the latest release.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>property-values-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

In a **Spring Boot** project, you should generally use dependency management (Boot's BOM/parent) to select aligned Spring versions, avoiding hard-coding a standalone `spring-context` version separate from the Boot line. This lesson illustrates the standalone framework API and therefore pins a consistent version.

### 5.2. Source Code

Create the exact file `src/main/java/example/PropertyValuesDemo.java`:

~~~java
package example;

import java.util.Arrays;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.PropertyValue;
import org.springframework.beans.PropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class PropertyValuesDemo {

    public static class RegistrationForm {
        private String name;
        private int age;
        private boolean admin;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }

        public boolean isAdmin() {
            return admin;
        }

        public void setAdmin(boolean admin) {
            this.admin = admin;
        }
    }

    public static void main(String[] args) {
        MutablePropertyValues submitted = new MutablePropertyValues()
                .add("name", "Lan")
                .add("age", "23")
                .addPropertyValue(new PropertyValue("admin", "true"));

        // Use the interface for reading without depending on add/remove methods.
        PropertyValues original = new MutablePropertyValues(submitted);

        System.out.println("submitted.size=" + original.getPropertyValues().length);
        System.out.println("age.raw=" + original.getPropertyValue("age").getValue());

        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form, "registrationForm");

        // Only accept properties allowed to be assigned.
        binder.setAllowedFields("name", "age");

        // bind may modify the passed MutablePropertyValues:
        // pass a copy to preserve the submitted data.
        binder.bind(new MutablePropertyValues(submitted));

        BindingResult result = binder.getBindingResult();

        System.out.println("name=" + form.getName());
        System.out.println("age=" + form.getAge());
        System.out.println("admin=" + form.isAdmin());
        System.out.println("errors=" + result.getErrorCount());
        System.out.println("suppressed=" +
                Arrays.toString(result.getSuppressedFields()));
        System.out.println("submitted.still=" + submitted.size());

        // Edit the input descriptor set; does not touch form yet.
        MutablePropertyValues edited = new MutablePropertyValues(submitted);
        edited.add("name", "Minh");
        edited.removePropertyValue("admin");

        PropertyValues delta = edited.changesSince(original);
        System.out.println("delta.name=" + delta.contains("name"));
        System.out.println("delta.age=" + delta.contains("age"));
        System.out.println("delta.admin=" + delta.contains("admin"));
        System.out.println("form.name.afterEdit=" + form.getName());
    }
}
~~~

The properties have getters/setters, so `DataBinder` can operate according to JavaBeans conventions. The `age` field of primitive type `int` receives the input string `"23"` through Spring's appropriate type converter. The `admin` field **has a setter**, but is blocked by `setAllowedFields("name", "age")`.

### 5.3. Compile and Run

Directory structure:

~~~text
property-values-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── PropertyValuesDemo.java
~~~

In the directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.PropertyValuesDemo
~~~

With JDK 17 or higher installed and Maven able to download dependencies, the **12 lines printed by the program** are:

~~~text
submitted.size=3
age.raw=23
name=Lan
age=23
admin=false
errors=0
suppressed=[admin]
submitted.still=3
delta.name=true
delta.age=false
delta.admin=false
form.name.afterEdit=Lan
~~~

The output lines above are from `System.out.println`; Maven logs or other messages are not counted as program output. No plain `javac` classpath is given because Spring is an external library outside the JDK; Maven handles downloading and linking the jars to compile/run.

### 5.4. Explaining Each Output Line

- `submitted.size=3`: the holder contains three `PropertyValue` entries. Each entry only describes an input name and value.
- `age.raw=23`: the characters `23` look like a number, but the value from the holder is still a `String`; `PropertyValue#getValue()` does not automatically convert it to `int`.
- `name=Lan` and `age=23`: `DataBinder.bind(...)` invoked the appropriate setters, converted types, and assigned them onto the JavaBean.
- `admin=false`: even though `submitted` contained `"admin"="true"` and the form has `setAdmin(...)`, the allowlist rule prevented assigning that field. Because a primitive boolean defaults to `false`, it stays `false`.
- `errors=0`: there are no type-binding or required-field errors in this example. **A suppressed field does not automatically increment `getErrorCount()`**; inspect `getSuppressedFields()` separately.
- `suppressed=[admin]`: rejected field names are recorded so the application can log, audit, or reject the request when needed.
- `submitted.still=3`: because a **copy** was passed to the binder, the original `submitted` dataset still contains all three entries.
- `delta.name=true`, `delta.age=false`: when changing the name and keeping the age unchanged, `changesSince` identifies only `name` as the changed entry.
- `delta.admin=false`: `admin` was removed from `edited`; `changesSince` does not create an entry representing a deletion.
- `form.name.afterEdit=Lan`: editing `edited` only edits the holder and does not automatically update `form`. To apply the edited values, you must bind or use a property assignment mechanism again with appropriate input controls.

This is the most important distinction between **preparing data for binding** and **assigning data onto an object**.

## 6. Why Does the Binder Accept PropertyValues, Not Just MutablePropertyValues?

The signature of `DataBinder` is:

~~~java
public void bind(PropertyValues pvs)
~~~

This allows callers to pass **any appropriate implementation** of the `PropertyValues` interface rather than forcing them to choose the concrete `MutablePropertyValues` class. Inside this method, Spring performs actions such as filtering out disallowed fields, checking configured required fields, and applying properties onto the target object.

**Important regarding ownership/mutation:** the `DataBinder.bind(PropertyValues)` Javadoc notes that the binder may **modify directly** the passed object if it is a `MutablePropertyValues`, since doing so is more efficient. If the input is not mutable, Spring may create an internal mutable copy. Therefore:

~~~java
PropertyValues original = new MutablePropertyValues()
        .add("name", "Lan")
        .add("admin", "true");

DataBinder binder = new DataBinder(target, "target");
binder.setAllowedFields("name");

// Create a copy whenever you need to preserve original.
binder.bind(new MutablePropertyValues(original));
~~~

This is a **snippet**, without `target` defined. In applications with multiple layers that want to audit requests, retain raw values, or reuse the same holder, you should **copy before binding** rather than relying on the binder to leave the input set untouched.

### When Do You Need Mutable vs. Just the Interface?

- **Preparing or editing data:** use `MutablePropertyValues` to build input from a map, add intentional defaults, or remove unwanted keys per policy.
- **A function that only reads data:** accept `PropertyValues` so it does not depend on mutation operations.
- **Passing to the binder:** it accepts `PropertyValues` per the API signature; if the holder is mutable and you need to preserve the source, create a copy yourself.

`PropertyValues` is not a validation annotation, nor is it `java.util.Properties`, `Environment`, or `PropertySource` used to load application configuration from `application.properties`. They share the word “property”, but one is **values assigned to a JavaBean during binding**, while the other is **the application's configuration source**.

## 7. Nested Properties and Multi-Value Cases

A `PropertyValue`'s name can be a **property path**, for example:

~~~java
MutablePropertyValues values = new MutablePropertyValues()
        .add("displayName", "Lan")
        .add("address.city", "Ha Noi")
        .add("items[0].quantity", "2");
~~~

This is a **snippet**, not a standalone example. To bind successfully, the target must have a compatible JavaBean structure:

- `displayName` is readable/writable.
- `address` has a suitable `city` property, either pre-initialized or able to be auto-grown by the binder under valid configuration.
- `items` is a collection/array whose element has a `quantity` property, accessible via the corresponding indexed path.

When a property path is missing or a nested object is inaccessible, behavior depends on settings such as `setAutoGrowNestedPaths` and `setIgnoreInvalidFields`; do not assume every nested path will be created automatically without error.

**For multi-value parameters**, such as `tag=java&tag=spring`, the HTTP source data may need to hold an array/list value rather than calling `add("tag", ...)` twice: `MutablePropertyValues` normally replaces the value by property name and does not carry the “append another value for the same key each time” semantics of a multimap.

## 8. Binding Errors, Conversion, and Validation

`PropertyValues` states **which values are proposed for assignment**, whereas `DataBinder` is where property access and type conversion errors can occur. For example:

~~~java
MutablePropertyValues pvs = new MutablePropertyValues()
        .add("age", "twenty-three");
DataBinder binder = new DataBinder(form, "registrationForm");
binder.setAllowedFields("age");
binder.bind(pvs);

BindingResult errors = binder.getBindingResult();
System.out.println(errors.hasFieldErrors("age")); // true
~~~

This is a **snippet** assuming a `form` bean variable containing `int age` as in section 5, not a standalone program. Because `"twenty-three"` cannot be converted into `int` via standard conversion, Spring records a `typeMismatch` field error in `BindingResult`.

Issues to keep distinct:

| Situation | Place/Type of Handling |
| --- | --- |
| `age="abc"` assigned to `int` | Type conversion error during **binding** |
| Field `admin` present while allowlist only permits `name, age` | **Suppressed field**, must be checked separately via `BindingResult#getSuppressedFields()` |
| Field does not exist on the bean | Depending on configuration, may be ignored (`ignoreUnknownFields` defaults to `true`) or cause an access error |
| `age=15` while business rules require 18+ | Additional **validation**, not automatically checked by `PropertyValues` alone |
| Child property is `null` in a property path | May require auto-grow or invalid-field handling configuration |
| Data outside the sender's permissions | **Authorization / controlling writable properties**, not decided by type conversion |

`DataBinder.bind(...)` **is not equivalent to** `DataBinder.validate()`. To check business constraints, you need to register a `Validator`/provider and invoke validation or let the configured Spring MVC pipeline handle it. When testing, verify independently: the bean's values after binding, `getErrorCount()`, `getFieldErrors()`, and `getSuppressedFields()`.

## 9. Security When Binding Untrusted External Data

If data comes from user requests, feeding every key in `MutablePropertyValues` onto an entity with setters can cause **mass assignment**: a client intentionally sends extra `isAdmin=true`, `role=ADMIN`, or `ownerId=...` parameters outside the fields exposed by the UI.

Security principles:

1. **Only accept properties allowed to be edited.** Prefer use-case-specific DTOs containing only permitted fields; for property binding with setters, use `DataBinder#setAllowedFields(...)` when appropriate.
2. **Do not bind directly onto entities containing sensitive state** just because they have setters. Transfer validated data from DTOs to domain objects in the service layer according to business rules.
3. **Do not confuse suppressed fields with binding errors.** Blocked fields may not make `hasErrors()` return `true`; check `getSuppressedFields()` if security policy requires rejecting requests containing disallowed keys.
4. **Limit size, nested paths, and collection growth** when handling external data; avoid allowing excessively deep object graphs or unbounded collection growth.
5. **Do not rely on holder-editing APIs to bypass access checks.** Removing a key in `MutablePropertyValues` before calling the binder is data preparation; actual permissions must be enforced server-side.

When using constructor binding for immutable DTOs, the field selection mechanism differs from setter/property binding. `setAllowedFields(...)` primarily controls **property binding** via `bind(PropertyValues)`; do not treat it as a universal filter for all object instantiation mechanisms or authorization checks.

## 10. Common Misconceptions

- **“`PropertyValue` invokes the setter itself.”** False: it is a value descriptor object; an accessor/binder assigns it onto the target.
- **“`PropertyValues` is a mutable class.”** False: it is an interface. `MutablePropertyValues` provides concrete add/remove operations.
- **“`getValue()` always returns the converted value.”** False: it can still be the string `"23"` even if the target property is `int`.
- **“`new MutablePropertyValues(source)` deep-copies all nested objects inside.”** False: the wrappers are independent, but mutable objects held as values can still share references.
- **“`changesSince` reports deleted entries too.”** False: the API returns new/changed entries in the new set and does not synthesize deletion records.
- **“Calling `add("x", ...)` twice creates two records for the same name.”** False: it usually replaces/merges by name; it is not a multimap.
- **“`DataBinder.bind(...)` never mutates the input holder.”** False for `MutablePropertyValues`: the binder may filter/modify the input set. Copy it if you need the original data.
- **“`hasErrors() == false` means the request sent no forbidden fields.”** False: suppressed fields do not necessarily produce a `FieldError`.
- **“Once binding finishes, business validation has already run.”** False: a configured validator/provider or validation pipeline is required.
- **“`application.properties` is also the `PropertyValues` being used here.”** False: configuration properties and property values used for bean binding are two different APIs.

## 11. Practice Questions

1. Among `PropertyValue`, `PropertyValues`, and `MutablePropertyValues`, which represents **a single** pair, which is an **interface**, and which supports adding/removing?
2. If `age="23"` in `PropertyValues` while the bean has `int age`, which component is responsible for the conversion?
3. Why should you call `binder.bind(new MutablePropertyValues(original))` when `original` is still needed for auditing?
4. If `newValues` removes the `admin` key, why is `changesSince(oldValues)` not a complete way to list deleted keys?
5. With `setAllowedFields("name", "age")`, if an `admin` field with a setter is submitted, what should you inspect besides `getErrorCount()`?
6. If code only needs to iterate over input entries, why is declaring the parameter as `PropertyValues` a better choice than requiring `MutablePropertyValues` specifically?

**Remember:** `PropertyValue` is a **name–value** entry; `PropertyValues` is the **collection contract**; `MutablePropertyValues` is the **editable container**. They prepare the data, while `DataBinder` controls assignment and type conversion into the bean. Always keep raw data, binding permissions, binding results, and business validation clearly separated.

## Official References

- Spring Framework Javadoc — PropertyValue: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/PropertyValue.html
- Spring Framework Javadoc — PropertyValues: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/PropertyValues.html
- Spring Framework Javadoc — MutablePropertyValues: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/MutablePropertyValues.html
- Spring Framework Javadoc — DataBinder: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Reference — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html