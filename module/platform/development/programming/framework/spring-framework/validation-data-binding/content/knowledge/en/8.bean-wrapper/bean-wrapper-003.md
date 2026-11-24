# PropertyDescriptor and Getter/Setter Metadata in Spring BeanWrapper

## 1. What Problem Does PropertyDescriptor Solve?

Suppose a form submits `name=Lan`, `active=true` to a Java object. Spring needs to know which method reads the property named `name`, which method writes it, what its data type is, and whether an input string can be converted to that type. Looking only at the list of fields via reflection is not enough: in JavaBeans, a **property** is typically described via **getters/setters** and may not have a field of the same name.

`java.beans.PropertyDescriptor` is an object that describes a property according to JavaBeans conventions. It tells you:

- **Property name** via `getName()`, for example `"name"`.
- **Property type** via `getPropertyType()`, for example `String.class` or `boolean.class`.
- **Read method** via `getReadMethod()`: the recognized getter method, or `null` if the property is not readable.
- **Write method** via `getWriteMethod()`: the recognized setter method, or `null` if the property is not writable.
- Other JavaBeans metadata such as `isBound()`, `isConstrained()`, display name, and editor information, if present.

In Spring, `org.springframework.beans.BeanWrapper` is the interface for manipulating and inspecting properties on an object. `BeanWrapperImpl` is the standard implementation. `BeanWrapper.getPropertyDescriptors()` returns the property descriptors; `getPropertyDescriptor(name)` retrieves the descriptor for a specific property.

**Distinguishing four roles:**

| Component | Responsibility |
| --- | --- |
| Field, such as `private String name` | Storage location in the class, if the class uses a field for storage |
| Getter/setter, such as `getName()` and `setName(String)` | Data access contract following JavaBeans conventions |
| `PropertyDescriptor` | Metadata describing a property's name, type, getter, and setter |
| `BeanWrapper` | Reads/writes actual properties on an object, looks up descriptors, checks readability/writability, and supports type conversion |

`PropertyDescriptor` only **describes** a property. It does not store the value of `name` itself and does not invoke setters to bind an HTTP request. Calling `wrapper.setPropertyValue("name", "Lan")` is an operation through `BeanWrapper`, and request binding is coordinated by a component such as `DataBinder`.

## 2. JavaBeans Conventions: From Method Names to Property Names

For a regular property named `firstName`:

```java
public class Person {
    private String firstName;

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }
}
```

JavaBeans introspection recognizes property `firstName` of type `String`, with getter `getFirstName` and setter `setFirstName`. For a primitive `boolean` property, the getter can take the form `isActive()`:

```java
public class Switch {
    private boolean active;

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

The property has name `active`, type `boolean`, read method `isActive`, and write method `setActive`.

The key point to grasp is that **a property is not synonymous with a field**:

- A class may simply declare `private String secret` without getters/setters. In JavaBeans-based property access, that field does not automatically become a bindable property.
- A computed getter such as `getDisplayName()` can create a read-only property even if no `displayName` field exists.
- A setter `setSecret(String)` without a getter can create a write-only property.
- Property names are derived from method naming rules, not by scanning every private field.
- For immutable types, records, or constructor binding, object construction can differ from traditional property binding; do not assume every constructor argument automatically has a setter.

### 2.1. Read-Write, Read-Only, and Write-Only Properties

| Form | Java method | Read method | Write method | Typical capability |
| --- | --- | --- | --- | --- |
| Read and write | `getName()`, `setName(String)` | Present | Present | Readable/writable |
| Read-only | `getId()` | Present | `null` | Readable, not assignable via property setter |
| Write-only | `setPassword(String)` | `null` | Present | Assignable, not readable via property getter |
| Boolean | `isEnabled()`, `setEnabled(boolean)` | Present | Present | Readable/writable |
| Field only | `private String code` | Not automatically recognized by getter/setter introspection | Not automatically recognized | Not accessed by property binding merely because the field exists |

That is the standard JavaBeans model. Some frameworks have direct field access strategies, use annotations, constructors, or custom accessor methods. You must identify **which access strategy is in use** before concluding that a property cannot be set by any means.

### 2.2. Why Do Getters/Setters Need Proper Signatures?

By standard conventions:

- A getter `getX()` takes no parameters and returns a value; the `isX()` form is commonly used for `boolean`.
- A setter `setX(T value)` takes a single value of a type compatible with the property. Traditional JavaBeans conventions use return type `void`.
- If a class has multiple setters with the same name taking different types, write-method selection may depend on the introspection algorithm and the getter's type; avoid ambiguous setter overloads in forms/DTOs.
- Fluent methods like `name()`/`name(String)` do not automatically follow standard `getX`/`setX` naming. Some configurations/frameworks may support them, but do not assume standard JavaBeans `PropertyDescriptor` will treat them as setters.
- JavaBeans applies capitalization/decapitalization rules to property names; names with multiple uppercase letters such as `URL` can yield unintuitive property names. Verify with actual introspection rather than guessing manually.

## 3. PropertyDescriptor APIs to Know

`PropertyDescriptor` is a JDK class in the `java.beans` package:

```java
import java.beans.PropertyDescriptor;
import java.lang.reflect.Method;

// Abbreviated signatures, not the full class contents:
String getName();
Class<?> getPropertyType();
Method getReadMethod();
Method getWriteMethod();
boolean isBound();
boolean isConstrained();
```

The two methods returning `Method` let you inspect getter/setter metadata:

```java
Method getter = descriptor.getReadMethod();
Method setter = descriptor.getWriteMethod();

String getterName = getter == null ? "-" : getter.getName();
String setterName = setter == null ? "-" : setter.getName();
```

Check for `null` before calling methods such as `getName()`, `getParameterTypes()`, or `invoke()` on `Method`. If the property is read-only, `getWriteMethod() == null`. If the property is write-only, `getReadMethod() == null`.

`getPropertyType()` returns a `Class<?>` representing the Java type. For generics such as `List<LineItem>`, `List.class` alone does not fully convey `LineItem`: `TypeDescriptor` or other generic metadata may be needed when implementing complex conversions. For specialized indexed properties, the property type might not be resolved in the usual way; do not assume it is always non-null in every case.

**Metadata is not equivalent to content checking.** A descriptor having setter `setAge(Integer)` does not mean `"abc"` can be converted to a number, or that age `-5` is valid. Conversion and validation are separate steps.

## 4. How BeanWrapper Retrieves and Uses PropertyDescriptor

Main APIs on `BeanWrapper`:

```java
// Signature excerpts for illustration, not a standalone program.
PropertyDescriptor[] getPropertyDescriptors();
PropertyDescriptor getPropertyDescriptor(String propertyName);
Object getWrappedInstance();
Class<?> getWrappedClass();

// Inherited from property access interfaces:
boolean isReadableProperty(String propertyName);
boolean isWritableProperty(String propertyName);
Object getPropertyValue(String propertyName);
void setPropertyValue(String propertyName, Object value);
Class<?> getPropertyType(String propertyName);
```

Choosing the API based on need:

- **Inspect all properties:** `getPropertyDescriptors()`, then read each descriptor's name/type/getter/setter.
- **Inspect one specific property:** `getPropertyDescriptor("name")`. If the property does not exist, Spring may throw `InvalidPropertyException`.
- **Check runtime accessors:** `isReadableProperty("name")` and `isWritableProperty("name")`, which are more convenient than comparing methods to `null` yourself.
- **Read/write values:** `getPropertyValue("name")`, `setPropertyValue("name", "Lan")`. These are actual operations on the object and can execute getters/setters.
- **Inspect the target:** `getWrappedInstance()` and `getWrappedClass()` tell you the object/class wrapped by the wrapper.

In typical code you can declare:

```java
Person person = new Person();
BeanWrapper wrapper = new BeanWrapperImpl(person);
PropertyDescriptor descriptor =
        wrapper.getPropertyDescriptor("firstName");
```

This snippet pairs with the `Person` class in section 2 and is not a standalone runnable file. `BeanWrapperImpl` can convert input values using configured property editors and/or a `ConversionService`. However, **the descriptor only provides metadata**; the `String → Integer` conversion path, type mismatch errors, and formatter selection belong to the conversion/binding mechanism rather than `getWriteMethod()` itself.

## 5. Java 17 + Spring 6.2 Example: How Are Getters/Setters Recognized?

The complete example below illustrates four property forms:

- `name` has both getter and setter.
- `active` has boolean getter `isActive()` and setter.
- `id` has only a getter, requiring no `id` field because the getter can compute a value.
- `pin` has only a setter.
- `address.city` illustrates nested property access when the intermediate object is already initialized.

The program uses Spring Framework **6.2.14**, Java **17+**, and Maven; no web server or Spring application context is needed. Place the two files as follows:

```text
beanwrapper-descriptor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── DescriptorDemo.java
```

### 5.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>beanwrapper-descriptor-demo</artifactId>
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
                <configuration>
                    <mainClass>demo.DescriptorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The `spring-beans` dependency contains `BeanWrapper` and `BeanWrapperImpl`. The code uses JDK JavaBeans (`java.beans.PropertyDescriptor`), without needing Hibernate/JPA or a Bean Validation provider.

### 5.2. src/main/java/demo/DescriptorDemo.java

```java
package demo;

import java.beans.PropertyDescriptor;
import java.lang.reflect.Method;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.NotWritablePropertyException;

public final class DescriptorDemo {

    public static class Address {
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class Profile {
        private String name;
        private boolean active;
        private String pin;
        private Address address = new Address();

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public boolean isActive() {
            return active;
        }

        public void setActive(boolean active) {
            this.active = active;
        }

        // Read-only id property; no id field required.
        public String getId() {
            return "USR-7";
        }

        // Write-only pin property.
        public void setPin(String pin) {
            this.pin = pin;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    private static String methodName(Method method) {
        return method == null ? "-" : method.getName();
    }

    private static void describe(BeanWrapper wrapper, String property) {
        PropertyDescriptor pd = wrapper.getPropertyDescriptor(property);
        System.out.println(
                property
                + " | type=" + pd.getPropertyType().getSimpleName()
                + " | getter=" + methodName(pd.getReadMethod())
                + " | setter=" + methodName(pd.getWriteMethod())
                + " | readable=" + wrapper.isReadableProperty(property)
                + " | writable=" + wrapper.isWritableProperty(property));
    }

    public static void main(String[] args) {
        Profile profile = new Profile();
        BeanWrapper wrapper = new BeanWrapperImpl(profile);

        describe(wrapper, "name");
        describe(wrapper, "active");
        describe(wrapper, "id");
        describe(wrapper, "pin");

        wrapper.setPropertyValue("name", "Lan");
        wrapper.setPropertyValue("active", "true");
        wrapper.setPropertyValue("address.city", "Hue");

        System.out.println("name=" + wrapper.getPropertyValue("name"));
        System.out.println("active=" + wrapper.getPropertyValue("active"));
        System.out.println("city=" + wrapper.getPropertyValue("address.city"));

        PropertyDescriptor nested =
                wrapper.getPropertyDescriptor("address.city");
        System.out.println("cityType=" + nested.getPropertyType().getSimpleName());

        try {
            wrapper.setPropertyValue("id", "CHANGED");
        } catch (NotWritablePropertyException ex) {
            System.out.println("id write rejected");
        }

        System.out.println("wrappedSameInstance="
                + (wrapper.getWrappedInstance() == profile));
    }
}
```

### 5.3. Running and Reading Stdout

From the `beanwrapper-descriptor-demo` directory:

```bash
mvn -q compile exec:java
```

**Expected stdout from the `System.out.println` statements in `main`:**

```text
name | type=String | getter=getName | setter=setName | readable=true | writable=true
active | type=boolean | getter=isActive | setter=setActive | readable=true | writable=true
id | type=String | getter=getId | setter=- | readable=true | writable=false
pin | type=String | getter=- | setter=setPin | readable=false | writable=true
name=Lan
active=true
city=Hue
cityType=String
id write rejected
wrappedSameInstance=true
```

Line order is determined by the `describe` and `println` calls in the program; the example does not rely on the return order of `getPropertyDescriptors()`. Maven may print plugin diagnostics if the environment configures logging differently, but the lines above are the output printed by the program itself.

**Detailed explanation:**

1. `getPropertyDescriptor("name")` receives a `PropertyDescriptor` with read method `getName` and write method `setName`, even if those methods did not share the same name as the field.
2. `getPropertyDescriptor("active")` recognizes the boolean read method `isActive`. In Java, `getActive()` is not the only way to read a boolean property.
3. `getPropertyDescriptor("id")` still recognizes the property even without a dedicated field, because `getId()` returns a computed value. `getWriteMethod() == null` and `isWritableProperty("id") == false`.
4. `getPropertyDescriptor("pin")` recognizes a write-only property via `setPin(String)`; `getReadMethod() == null`. This is solely to illustrate metadata and does not mean raw Strings should store PINs in real applications.
5. `setPropertyValue("active", "true")` converts the string to boolean using `BeanWrapperImpl`'s default mechanism before invoking the setter. `PropertyDescriptor` itself does not parse strings.
6. `address.city` is a **nested property path**. Because `Profile.address` already holds an `Address`, the wrapper can locate and set `city`. `getPropertyDescriptor("address.city")` describes the `city` property on the nested object.
7. Writing to `id`, which only has a getter, throws `NotWritablePropertyException`. The example catches that exception type to confirm property-level write protection.
8. `getWrappedInstance() == profile` is `true` because the wrapper was created around that exact object.

## 6. Retrieving the PropertyDescriptor List and Selecting the Right Properties

When you need to inspect which properties a class has, use:

```java
for (PropertyDescriptor pd : wrapper.getPropertyDescriptors()) {
    String propertyName = pd.getName();
    Class<?> type = pd.getPropertyType();
    boolean hasGetter = pd.getReadMethod() != null;
    boolean hasSetter = pd.getWriteMethod() != null;

    // Inspect metadata; application selection must be defined separately.
}
```

This is an **illustrative snippet to add to code that has a `wrapper` variable**. The library may return more properties than you declared yourself, and descriptor ordering should not be treated as a contract. If you want to print a report in a deterministic order, filter names as required and sort them.

An example selecting properties for display (not yet a security policy):

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

List<String> readableNames = Arrays.stream(wrapper.getPropertyDescriptors())
        .filter(pd -> pd.getReadMethod() != null)
        .map(PropertyDescriptor::getName)
        .filter(name -> List.of("name", "active", "id").contains(name))
        .sorted(Comparator.naturalOrder())
        .toList();
```

This snippet illustrates the stream processing part; place it inside a method with `wrapper` and the corresponding imports. Filtering by an explicit list of names avoids exposing unintended properties. Still, map/serialize data according to the actual API contract rather than using every getter found by introspection as an automatic response field list.

### 6.1. How Do BeanUtils and Introspector Relate?

Alongside `BeanWrapper`, there are two common metadata lookup paths:

- JDK: `java.beans.Introspector.getBeanInfo(Profile.class)` returns a `BeanInfo` containing `PropertyDescriptor[]`. This is the underlying JavaBeans introspection mechanism.
- Spring: `org.springframework.beans.BeanUtils.getPropertyDescriptors(Profile.class)` and `BeanUtils.getPropertyDescriptor(Profile.class, "name")` look up descriptors by class.

`BeanWrapper` differs in that it is **bound to a specific instance** and also provides `getPropertyValue`/`setPropertyValue`, runtime readability/writability checks, and nested property paths.

Illustrative signatures:

```java
PropertyDescriptor[] fromClass =
        org.springframework.beans.BeanUtils.getPropertyDescriptors(Profile.class);

PropertyDescriptor one =
        org.springframework.beans.BeanUtils.getPropertyDescriptor(Profile.class, "name");
```

`BeanUtils.getPropertyDescriptor(...)` returns `null` if no descriptor is found, whereas `BeanWrapper.getPropertyDescriptor("unknown")` reports an invalid property per Spring's contract. Do not treat these two behaviors as interchangeable without checking.

### 6.2. Nested Property Paths and Indexed Properties

`BeanWrapper` supports property path syntax:

```text
name
address.city
orders[0].quantity
settings[theme]
```

These are examples of path syntax, **not implying that the `Profile` class in section 5 contains `orders` or `settings`**. Actual execution depends on target structure, generic types, getters/setters, auto-grow limits, and conversion mechanisms.

**Important:** `BeanWrapper.getPropertyDescriptor(String)` supports a nested path such as `address.city`, but the Javadoc specifies that it **does not accept indexed/mapped property paths** as direct arguments for descriptor lookup. When handling `orders[0].quantity`, rather than assuming `getPropertyDescriptor("orders[0].quantity")` will work, look up the element/property type appropriately, such as `getPropertyTypeDescriptor(path)` when a target and valid path exist, or introspection on the element class. For value reading/writing, `getPropertyValue(path)` and `setPropertyValue(path, value)` support richer property paths when the runtime structure permits.

If `address` is `null`, looking up or assigning a nested property may fail or require enabling auto-grow for nested paths; do not assume Spring creates all nested objects automatically just from `new BeanWrapperImpl(profile)`.

## 7. How Does PropertyDescriptor Participate in Spring Data Binding?

In MVC or outside the web layer, Spring can use `DataBinder` to bind data into an object. In JavaBean property binding mode, the binder relies on property accessor/BeanWrapper infrastructure to:

1. Receive a field path, such as `name`.
2. Determine whether the property exists and is writable.
3. Find the target type and appropriate conversion rules.
4. Assign the value via the setter or configured accessor.
5. Record type conversion errors, invalid properties, and binding metadata.

```text
Input source: "active" = "true"
              |
              v
        DataBinder / Spring MVC
              |
              v
       BeanWrapper / PropertyAccessor
              |
              +--> PropertyDescriptor("active")
              |      readMethod  = isActive()
              |      writeMethod = setActive(boolean)
              |      propertyType = boolean
              |
              +--> Conversion / PropertyEditor
              |      "true" -> boolean true
              |
              +--> setActive(true)
              v
        Profile.active = true
```

**The descriptor tells Spring where to access and what type to target; converters/formatters or editors handle value transformation; the binder coordinates binding and errors.** Do not attribute all type conversion, validation, and HTTP handling behavior to `PropertyDescriptor`.

An illustrative example permitting only two properties to be bound:

```java
// Illustration for DataBinder, requiring appropriate Spring imports.
// The Profile and Address classes can be taken from the program in section 5.
Profile profile = new Profile();

org.springframework.validation.DataBinder binder =
        new org.springframework.validation.DataBinder(profile, "profile");
binder.setAllowedFields("name", "active");

org.springframework.beans.MutablePropertyValues input =
        new org.springframework.beans.MutablePropertyValues();
input.add("name", "Lan");
input.add("active", "true");
input.add("id", "CHANGED");

binder.bind(input);

System.out.println(binder.getBindingResult().hasErrors());
System.out.println(
        java.util.Arrays.toString(
                binder.getBindingResult().getSuppressedFields()));
```

When run in a project with `spring-context` dependencies (`DataBinder` belongs to `spring-context`), this illustrates `id` being suppressed rather than assigned. This is a **separate snippet**, not part of the Maven program in section 5 which only declares `spring-beans`. The expected logical result is `hasErrors=false` and the suppressed fields list containing `id`. Suppressed fields do not automatically create a `FieldError`, so the application must handle that list according to its own policy.

### 7.1. Descriptors Are Not a List of Allowed Update Fields

Having a setter only proves **a property write path exists**. It does not mean users are allowed to change `role`, `balance`, or `status`. If HTTP requests are bound directly into an entity with many setters, clients can submit extra property names to cause **overposting/mass assignment**.

Appropriate design measures:

- Use a dedicated DTO/form object per operation containing only allowed input properties.
- With property binding, configure `setAllowedFields(...)` per the operation's requirements; also inspect `getSuppressedFields()` if requests containing out-of-contract fields must be rejected.
- Do not rely on a field being `private` when the class exposes a corresponding public setter.
- Map only validated and permitted values onto the business model; obtain sensitive IDs/statuses/roles/prices from server context.

The existence of `PropertyDescriptor.getWriteMethod()` **is not an authorization mechanism**. User input always requires input boundaries and separate permission checks.

## 8. When Can Getters/Setters Have Side Effects?

JavaBeans getters/setters are **real Java methods**, not cost-free field reads/writes. For example:

```java
public String getDisplayName() {
    auditLog.add("display name requested");
    return firstName + " " + lastName;
}
```

This is an **illustrative snippet, not a standalone class** (assuming `auditLog`, `firstName`, and `lastName` exist). Calling `wrapper.getPropertyValue("displayName")` can execute the getter and write to the log. Conversely, **merely calling `pd.getReadMethod()` to retrieve metadata does not execute the getter**.

Therefore:

- Do not invoke every getter on an untrusted object indiscriminately just to "inspect its structure".
- Getters should not perform expensive I/O or significant side effects if the class is widely used in binding, serialization, or mapping.
- Setters can normalize, reject, or mutate state; `setPropertyValue` executes the setter, so it can raise exceptions and cause side effects.
- In Spring, reading the old value for custom editors has its own configuration (`extractOldValueForEditor`). Do not assume every write must invoke the getter first.
- `isReadableProperty`/`isWritableProperty` and method metadata represent **access capability**; they do not guarantee invoking the getter/setter will succeed for all data and runtime states.

## 9. How Do PropertyDescriptor, Reflection, and TypeDescriptor Differ?

| Tool | Primary information | When to use |
| --- | --- | --- |
| `java.lang.reflect.Field` | Declared fields of a class, types, and modifiers | When you need field metadata or an explicit field-access mechanism |
| `java.lang.reflect.Method` | A specific method and signature | When you need to inspect/invoke getters, setters, or other methods |
| `java.beans.PropertyDescriptor` | JavaBeans property, read/write methods, property type | When you need standard property name, getter, and setter |
| `BeanWrapper` | Metadata + object property access + path support | When you need to read/write properties and resolve nested paths |
| `TypeDescriptor` (Spring) | Richer type metadata, potentially including generics and annotations | When conversion/formatting needs `List<Item>` or field annotations |
| `BeanUtils` (Spring) | Class-based utility/introspection helpers | When you only need descriptors for a type or property |

In particular, `PropertyDescriptor.getPropertyType()` typically returns only a single `Class<?>`. For example, a `List<Address> addresses` property returns the raw type `List.class`; Spring's `TypeDescriptor` can additionally carry the element type to support conversion. A `PropertyDescriptor` cannot replace all generic/annotation metadata.

### 9.1. Things That Cannot Be Inferred from a Setter Alone

A setter `setAmount(BigDecimal value)` does not tell you:

- How the string `"1.000,50"` should be parsed in `vi-VN` versus `en-US`.
- Whether the amount is allowed to be negative.
- Who has permission to write the amount.
- Whether `null` is valid for the use case.
- Whether the system persists a direct field, a JPA attribute, or another command.

You need `ConversionService`/`Formatter`, validation, authorization, and the corresponding business model. A descriptor is simply one link that helps Spring identify the property and its accessor methods.

## 10. Common Mistakes When Working with Getters, Setters, and BeanWrapper

| Situation | Cause | How to resolve |
| --- | --- | --- |
| `getPropertyDescriptor("foo")` not found | Property does not exist per introspection; typo or non-JavaBeans naming | Check getter/setter methods, casing, and actual property name |
| `private String name` exists yet `isWritableProperty("name") == false` | Field only, no recognized public setter | Add a convention-compliant setter if property binding is needed, or choose field/constructor binding |
| `getWriteMethod() == null` | Property is read-only or setter not recognized | Use constructor/factory for immutable objects, or add a valid setter if writing is truly needed |
| `getReadMethod() == null` | Property is write-only | Avoid calling `getPropertyValue` on it; design appropriate accessors |
| `setPropertyValue("age", "abc")` fails | Input cannot be converted to the target type | Fix input, register appropriate converter/formatter, handle binding errors |
| `address.city` fails | `address` is null or path getters/setters are unusable | Initialize nested objects or configure scoped auto-grow |
| Looking up descriptor for `items[0]` like a simple property | Descriptor API does not directly support indexed/mapped syntax | Distinguish property metadata from element paths; look up the appropriate type |
| Relying on `getPropertyDescriptors()` ordering | Introspection order is not a business contract | Filter/sort by an explicit list of names |
| Assuming a setter means the request is allowed to update it | Confusing metadata with authorization | Dedicated input DTO and server-side allowlist |
| Assuming the descriptor validates automatically | Metadata carries no business rules | Enable validation and check errors |
| Treating all accessors as side-effect-free | Getters/setters can execute arbitrary code | Design pure accessors or invoke in a controlled manner |

### Exceptions to Know

- `InvalidPropertyException`: property name/path is invalid in the access context.
- `NotReadablePropertyException`: attempted to read a non-readable property.
- `NotWritablePropertyException`: attempted to write a non-writable property.
- `TypeMismatchException`: value cannot be converted to the target type by the binding/conversion mechanism.
- Other errors may come from getters/setters or unavailable nested objects; the final exception type depends on the API and configuration.

Do not use `try/catch(Exception)` to silently swallow all errors. In MVC, handle input errors using `BindingResult` or an appropriate exception handler and return stable messages to users.

## 11. Knowledge Check

**Question 1.** A class only has `getFullName()` and no `setFullName(...)`. Can there be a `PropertyDescriptor` for `fullName`?

**Yes.** It is a read-only property, with write method `null`.

**Question 2.** `private String token` has a public setter `setToken(String)` and no getter. Since the field is private, can it still be bound via property access?

**Yes**, because the public setter provides a property write path; JavaBeans metadata can still describe a write-only property. HTTP access permissions must still be controlled separately.

**Question 3.** Does `PropertyDescriptor.getWriteMethod() != null` prove that input `"abc"` can be parsed into an `Integer`?

**No.** The setter may accept `Integer`, but string conversion is the responsibility of the conversion/binder layer and can fail.

**Question 4.** How do you inspect the getter of `name` without invoking the getter?

Call `wrapper.getPropertyDescriptor("name").getReadMethod()` and inspect the `Method` metadata. Calling `getReadMethod()` alone does not execute the getter.

**Question 5.** Which call is appropriate to ask whether a property is writable?

`wrapper.isWritableProperty("name")` or checking the write method via the descriptor. Actual writes can still fail due to conversion or business logic inside the setter.

**Question 6.** Why shouldn't every property with a setter be exposed as request input?

Because **technical writability differs from business update permission**; input DTOs and allowed fields are required to prevent mass assignment.

**Question 7.** Are `getPropertyDescriptor("address.city")` and `getPropertyDescriptor("orders[0].quantity")` the same?

No. The Javadoc of `BeanWrapper.getPropertyDescriptor` permits nested paths but excludes indexed/mapped property paths. For collection elements, use an appropriate metadata mechanism.

## 12. Practical Project Workflow

1. Identify the target object and access strategy: JavaBean setters, direct field access, constructor binding, or immutable types.
2. Use `BeanWrapper`/`BeanUtils` when you need to introspect property names, types, and accessor methods; prefer `getPropertyDescriptor(name)` for a known property.
3. Check `getReadMethod()`, `getWriteMethod()`, or `isReadableProperty()`/`isWritableProperty()`; handle `null`/nonexistent properties.
4. When actual reading/writing is needed, use `getPropertyValue()`/`setPropertyValue()` on a target with proper lifecycle management; handle exceptions.
5. For string inputs, configure appropriate conversion/formatting and validation instead of expecting `PropertyDescriptor` to handle those steps.
6. For HTTP requests, use field-restricted forms/DTOs, enforce permissions, and never trust properties as writable just because a setter exists.
7. Test edge cases: read-only properties, write-only properties, boolean getters, nested names, null nested objects, type mismatches, overloaded setters with the same name, and disallowed update fields.

**Key takeaway:** `PropertyDescriptor` tells you *which property*, *what type*, *which getter*, and *which setter*; `BeanWrapper` uses that information to *read/write the object*. Metadata makes Spring binding flexible, while conversion, validation, and authorization remain separate responsibilities.

## 13. Official References

- [Spring Framework — BeanWrapper (Javadoc 6.2.14)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapper.html): `getPropertyDescriptors()`, `getPropertyDescriptor(name)`, nested properties, read/write.
- [Spring Framework — BeanWrapperImpl (Javadoc 6.2.14)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapperImpl.html): BeanWrapper implementation and introspection.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): JavaBeans, property access, type conversion, and data binder.
- [Java SE 17 — java.beans.PropertyDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyDescriptor.html): getReadMethod, getWriteMethod, getPropertyType, and JavaBeans metadata.
- [Spring Framework — BeanUtils](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanUtils.html): class-based descriptor lookup utilities.
- [Spring Framework — TypeDescriptor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html): type metadata for conversion and generics.