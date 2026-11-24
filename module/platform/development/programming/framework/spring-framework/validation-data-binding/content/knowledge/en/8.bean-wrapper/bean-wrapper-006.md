# isReadableProperty and isWritableProperty in Spring BeanWrapper

`BeanWrapper` is an interface in `org.springframework.beans` that helps Spring **read, write, convert, and inspect JavaBean properties**. Two particularly useful methods when working with dynamic property names are:

- `isReadableProperty(String propertyName)`: checks whether a property can be **read** via the property accessor mechanism.
- `isWritableProperty(String propertyName)`: checks whether a property can be **written** via the property accessor mechanism.

Both return `boolean`. For a typical nonexistent property name, the result is `false`. They can check **nested paths** such as `"address.city"` and, under suitable conditions, indexed or keyed elements such as `"items[0].name"`.

These two methods answer a question about **accessibility via the BeanWrapper mechanism**; they do not mean the value is valid, that access is authorized, that the setter is guaranteed to succeed, or that the object has been bound from an HTTP request.

## 1. At What Layer Does BeanWrapper Operate?

In Java, a `private` field is not automatically a JavaBeans property readable/writable through `BeanWrapperImpl`. Properties are normally described by accessors named according to conventions:

~~~java
public String getName() { ... }        // reads property "name"
public void setName(String value) { ... } // writes property "name"
public boolean isActive() { ... }      // reads boolean property "active"
public void setActive(boolean v) { ... } // writes boolean property "active"
~~~

`BeanWrapperImpl` uses property introspection to discover this information. It is commonly used internally by **Spring BeanFactory** and **DataBinder**, although applications can also instantiate it directly:

~~~java
Person person = new Person();
BeanWrapper wrapper = new BeanWrapperImpl(person);
boolean canRead = wrapper.isReadableProperty("name");
boolean canWrite = wrapper.isWritableProperty("name");
~~~

This is an **excerpt**: it requires a `Person` class and Spring imports; a complete example is in section 4.

Distinguishing closely related components:

| Component | Role |
| --- | --- |
| `PropertyAccessor` | Root interface defining property read, write, type lookup, and readability/writability checks |
| `BeanWrapper` | Interface specialized for **JavaBeans properties**, extending access and type conversion mechanisms |
| `BeanWrapperImpl` | Common implementation of `BeanWrapper` |
| `PropertyAccessorFactory.forBeanPropertyAccess(bean)` | Factory returning a `BeanWrapper` for a bean |
| `PropertyAccessorFactory.forDirectFieldAccess(bean)` | Creates an accessor using **direct fields**; read/write rules differ from JavaBeans getters/setters |
| `DataBinder` | Coordinates binding input data into an object, managing allowed/disallowed fields, binding errors, and validation |

`isReadableProperty` and `isWritableProperty` are declared on `PropertyAccessor`, so they appear on `BeanWrapper` and compatible implementations. For the goal of learning **BeanWrapper**, we use `BeanWrapperImpl` and JavaBeans rules.

## 2. Exact Meaning of the Two Methods

Signatures:

~~~java
boolean isReadableProperty(String propertyName);
boolean isWritableProperty(String propertyName);
~~~

`propertyName` is a property name or path such as `"name"` or `"address.city"`. The return value indicates whether the current accessor mechanism **is capable of** reading or writing the corresponding property.

- `isReadableProperty("name") == true` typically indicates the accessor can retrieve the value, e.g., via `getName()`.
- `isWritableProperty("name") == true` typically indicates the accessor can assign the value, e.g., via `setName(...)`.
- A property may be read-only, write-only, read-and-write, or unrecognized.
- The results of the two methods are **independent**: `readable == true` does not imply `writable == true`, and vice versa.

For ordinary JavaBeans, the following table predicts the outcome:

| Public declarations on the bean | Readable? | Writable? | Explanation |
| --- | :---: | :---: | --- |
| `getName()` and `setName(String)` | `true` | `true` | Full two-way read/write |
| Only `getId()` | `true` | `false` | Read-only property |
| Only `setToken(String)` | `false` | `true` | Write-only property |
| `isActive()` and `setActive(boolean)` | `true` | `true` | JavaBeans boolean getter |
| Only `private String note;` declared | `false` | `false` | No JavaBeans accessors |
| No property `"missing"` | `false` | `false` | Name does not exist |

**Common misconception:** `false` from `isWritableProperty` only says it cannot be written via the active accessor mechanism. It **does not mean the object is immutable in every case**; the object could be modified by constructors, other methods, reflection, or direct-field access. Likewise, `true` does not mean an HTTP user is allowed to modify that property.

### Property Names Are JavaBeans Names, Not Necessarily Field Names

~~~java
private String displayName;

public String getDisplayName() {
    return displayName;
}

public void setDisplayName(String displayName) {
    this.displayName = displayName;
}
~~~

The name to check is `"displayName"`, not `"getDisplayName"`, `"setDisplayName"`, or `"DisplayName"`. BeanWrapper uses **JavaBeans property naming rules**. For classes with unusual accessor names, inspect `PropertyDescriptor` instead of guessing names.

For Java `record`s or immutable DTOs, **constructor binding** may be more appropriate instead of trying to perform setter-based property binding. Do not use `isWritableProperty(...) == false` to conclude that every way of constructing/binding that object is impossible.

## 3. Why Check Before Reading or Writing?

There are three practical situations:

1. **Property names come from configuration or an approved mapping:** before calling `getPropertyValue(name)` or `setPropertyValue(name, value)`, check whether the property name is supported by the current bean.
2. **Building internal tools:** when building a metadata viewer, mapper, or form editor, you need to distinguish read-only display fields from editable fields.
3. **Nested paths:** when traversing `"address.city"`, you need to know whether the accessor can navigate through the object graph components and read/write the target.

Checking pattern:

~~~java
if (wrapper.isReadableProperty(propertyName)) {
    Object current = wrapper.getPropertyValue(propertyName);
    // Process current according to the application's purpose.
}

if (wrapper.isWritableProperty(propertyName)) {
    wrapper.setPropertyValue(propertyName, proposedValue);
}
~~~

This is an **excerpt**, assuming `wrapper` and `propertyName` are already initialized. In practice you still need exception handling because getters or setters can throw, type conversion can fail, or nested objects can be inaccessible.

Especially: if `propertyName` comes from a client, being "writable" **must not be used as an authorization rule**. Only perform binding on server-approved properties, ideally via DTOs containing strictly the fields to accept.

## 4. Complete Runnable Java 17+ Example

We create a JavaBean `Person` with four property styles:

- `name` has getter and setter → read/write;
- `id` has only a getter → read-only;
- `token` has only a setter → write-only;
- `active` has a boolean getter and setter → read/write;
- `address.city` is a nested path to another JavaBean;
- `missing` does not exist → neither readable nor writable.

The program prints check results, attempts to read/write valid properties, and catches exceptions when attempting unsupported operations.

### 4.1. Creating the Maven Project

Use Maven with **JDK 17+**. The `pom.xml` file below selects Spring Framework `6.2.19` to demonstrate the API. This is a pinned version for the example, not an instruction to automatically pull "the latest Spring version".

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>bean-wrapper-access-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
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

`spring-beans` contains `BeanWrapperImpl` and pulls in the necessary Spring dependencies. In a Spring Boot project, usually let Boot's BOM/parent manage the `spring-beans` version to avoid Spring module version mismatches.

### 4.2. Java Source Code

Create file **`src/main/java/example/BeanWrapperAccessDemo.java`**:

~~~java
package example;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.NotReadablePropertyException;
import org.springframework.beans.NotWritablePropertyException;

public class BeanWrapperAccessDemo {

    public static class Address {
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class Person {
        private String name;
        private final String id = "U-001";
        private String token;
        private boolean active;
        private Address address = new Address();

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        // Getter only: readable = true, writable = false.
        public String getId() {
            return id;
        }

        // Setter only: readable = false, writable = true.
        public void setToken(String token) {
            this.token = token;
        }

        // Regular method, not a getter for "token".
        public boolean hasToken() {
            return token != null;
        }

        public boolean isActive() {
            return active;
        }

        public void setActive(boolean active) {
            this.active = active;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    private static void inspect(BeanWrapper wrapper, String name) {
        System.out.println(
                name
                + ": read=" + wrapper.isReadableProperty(name)
                + ", write=" + wrapper.isWritableProperty(name));
    }

    public static void main(String[] args) {
        Person person = new Person();
        BeanWrapper wrapper = new BeanWrapperImpl(person);

        inspect(wrapper, "name");
        inspect(wrapper, "id");
        inspect(wrapper, "token");
        inspect(wrapper, "active");
        inspect(wrapper, "address.city");
        inspect(wrapper, "missing");

        // Assign only properties explicitly permitted by the program.
        wrapper.setPropertyValue("name", "Lan");
        wrapper.setPropertyValue("active", "true");
        wrapper.setPropertyValue("address.city", "Hue");
        wrapper.setPropertyValue("token", "internal-token");

        System.out.println("name=" + wrapper.getPropertyValue("name"));
        System.out.println("id=" + wrapper.getPropertyValue("id"));
        System.out.println("active=" + wrapper.getPropertyValue("active"));
        System.out.println("city=" + wrapper.getPropertyValue("address.city"));
        System.out.println("tokenAssigned=" + person.hasToken());

        try {
            wrapper.getPropertyValue("token");
        } catch (NotReadablePropertyException ex) {
            System.out.println("readToken=NotReadablePropertyException");
        }

        try {
            wrapper.setPropertyValue("id", "U-999");
        } catch (NotWritablePropertyException ex) {
            System.out.println("writeId=NotWritablePropertyException");
        }
    }
}
~~~

In this class both `Person` and `Address` are JavaBeans with public methods. `Address` is already initialized inside `Person`, so the `address.city` path has a valid intermediate object. No HTTP server is needed; the example uses `BeanWrapperImpl` directly.

### 4.3. Run Commands and Stdout

Project structure:

~~~text
bean-wrapper-access-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── BeanWrapperAccessDemo.java
~~~

In the directory containing `pom.xml`, check Java/Maven and run:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.BeanWrapperAccessDemo
~~~

**Lines printed by the program** in the configuration above:

~~~text
name: read=true, write=true
id: read=true, write=false
token: read=false, write=true
active: read=true, write=true
address.city: read=true, write=true
missing: read=false, write=false
name=Lan
id=U-001
active=true
city=Hue
tokenAssigned=true
readToken=NotReadablePropertyException
writeId=NotWritablePropertyException
~~~

The command may also print Maven messages or other environment warnings; the block above describes the output produced by the `System.out.println` statements in the program. There is no plain `javac` command because the example needs Spring libraries on the classpath; Maven downloads dependencies and compiles using the configured Java version.

### 4.4. Analyzing the Results

- `name` has both `getName` and `setName`, so both read and write are `true`.
- `id` has `getId` but no `setId`, so reading returns `"U-001"` and writing is rejected by `BeanWrapperImpl`.
- `token` has `setToken` but no `getToken`, so it can be written but not read directly via property `token`. The application-defined `hasToken()` method confirms the setter ran; it does not turn `token` into a readable property.
- `active` uses `isActive()` for the boolean type. The value passed to the setter through `BeanWrapper` is the string `"true"` and is converted to `boolean true`.
- `address.city` goes through `getAddress()` and `Address`'s accessors; it can be read/written because the child object is initialized and has getters/setters for `city`.
- `missing` has no matching descriptor, so both results are `false`.
- `NotReadablePropertyException` and `NotWritablePropertyException` show what happens when attempting prohibited operations. Merely checking `isReadableProperty` or `isWritableProperty` **does not throw an exception in the simple cases above**; exceptions arise when calling `getPropertyValue` or `setPropertyValue`, respectively.

## 5. How Does BeanWrapper Determine Properties?

### 5.1. JavaBeans Convention

The BeanWrapper mechanism relies on property accessors and JavaBean metadata, rather than simply reading every field directly by name. Example:

~~~java
public class Profile {
    private String email;

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

This class snippet only illustrates metadata; in Java 17 it is valid when saved as `Profile.java`. The property is `email`. If only the `private String email` field is kept and both getter/setter are removed, standard `BeanWrapperImpl` cannot read/write that property, even though code inside the class can access the field directly.

For booleans, `isEnabled()` and `getEnabled()` can both be recognized under JavaBeans conventions (depending on return type and context). When getter/setter names mismatch or overloads cause ambiguity, inspect the actual bean model and `PropertyDescriptor`.

### 5.2. PropertyDescriptor and Type Metadata

`BeanWrapper` also lets you inspect metadata:

~~~java
BeanWrapper wrapper = new BeanWrapperImpl(new Person());

for (java.beans.PropertyDescriptor descriptor
        : wrapper.getPropertyDescriptors()) {
    System.out.println(descriptor.getName());
    System.out.println(descriptor.getReadMethod());
    System.out.println(descriptor.getWriteMethod());
}
~~~

This is an **excerpt**: `Person` is defined in the complete example. A `PropertyDescriptor` typically lists:

- Property name (`getName()`).
- Read method (`getReadMethod()`) if present.
- Write method (`getWriteMethod()`) if present.
- Inferred Java type (`getPropertyType()`).

To get the type of a specific property path, use `wrapper.getPropertyType("address.city")` or `wrapper.getPropertyTypeDescriptor("address.city")` as needed. Return types and type resolution for indexed/mapped elements depend on the actual structure.

**Do not infer from a descriptor that the setter will certainly succeed:** a setter can reject values, throw exceptions, or require valid state. Metadata is only a signal of API-level accessibility, not a replacement for actual execution and testing.

### 5.3. PropertyAccessorFactory and Direct Field Access

Two options:

~~~java
import org.springframework.beans.PropertyAccessor;
import org.springframework.beans.PropertyAccessorFactory;

PropertyAccessor beanAccess =
        PropertyAccessorFactory.forBeanPropertyAccess(person);

PropertyAccessor fieldAccess =
        PropertyAccessorFactory.forDirectFieldAccess(person);
~~~

This is an **excerpt**; `person` is an existing object.

- `forBeanPropertyAccess` uses JavaBeans getter/setter behavior similar to `BeanWrapperImpl`.
- `forDirectFieldAccess` accesses fields directly and does not require matching accessors. A field without getters/setters can be read/written according to this accessor's reflection rules, though final fields and Java/module system restrictions must be considered.

Do not swap `BeanWrapperImpl` for direct-field access arbitrarily just to make a property "writable". The two mechanisms have different encapsulation boundaries.

## 6. Nested Property Paths

`isReadableProperty` and `isWritableProperty` can accept multi-level paths:

~~~java
wrapper.isReadableProperty("address.city");
wrapper.isWritableProperty("address.city");

wrapper.isReadableProperty("contacts[0].phone");
wrapper.isWritableProperty("attributes[key]");
~~~

The first two lines correspond to the `Person` class in the example; the last two merely illustrate **path syntax** and do not belong to the `Person` model built earlier.

For the path `"address.city"`, Spring needs to:

1. Locate `address` on the root object and navigate to the child object.
2. Locate `city` on the child object.
3. Check whether the target property is readable/writable given the accessor and current state.

If `address == null`, the path may fail to resolve or be affected by **auto-grow nested paths** configuration. Some access operations can cause nested structures to be instantiated when auto-grow is enabled and the child type is instantiable. Therefore, **do not assume checking a property path is always side-effect-free** under all configurations.

For `contacts[0].phone`, element index `0` must also exist or be validly auto-grown within the collection growth limit, and the element type must be determinable. For `attributes[key]`, accessibility depends on the corresponding map/property. Results can vary with the object graph and configuration, not only the outermost class's getter/setter names.

**Practical recommendation:** for complex property paths, write tests against the real model covering `null` child objects, empty lists, and out-of-bounds indices. Avoid using auto-grow as an implicit permission mechanism for user data.

## 7. Comparison with getPropertyValue and setPropertyValue

The four APIs have distinct responsibilities:

| API | Effect | Important note |
| --- | --- | --- |
| `isReadableProperty(name)` | Asks whether the property is readable | Returns `boolean`, does not return the value |
| `isWritableProperty(name)` | Asks whether the property is writable | Returns `boolean`, performs no assignment |
| `getPropertyValue(name)` | Reads the **current value** | Can fail if unreadable or if the getter fails |
| `setPropertyValue(name, value)` | Assigns a **new value**, possibly converting types | Can fail if non-writable, unconvertible, or if the setter fails |

Example:

~~~java
if (wrapper.isReadableProperty("name")) {
    Object current = wrapper.getPropertyValue("name");
    System.out.println(current);
}

if (wrapper.isWritableProperty("name")) {
    wrapper.setPropertyValue("name", "Minh");
}
~~~

This excerpt is valid when placed inside a method with a corresponding `wrapper` variable.

### When Do You Still Need to Catch Exceptions?

A `true` result only reflects metadata/path accessibility **at the moment of the check**. The subsequent operation can still fail when:

- A getter/setter throws an exception due to a business condition.
- The value cannot be converted to the target type, e.g., `"abc"` for a setter taking `int`.
- An intermediate object in a nested path is `null` or was modified between the check and the use.
- Java/module reflection access levels prohibit the operation.
- A proxy or dynamic bean changes state and behavior.

When `getPropertyValue` or `setPropertyValue` is invalid, Spring may throw exceptions such as `NotReadablePropertyException`, `NotWritablePropertyException`, `TypeMismatchException`, or other `BeansException` subclasses depending on the error. Do not build logic assuming "true guarantees no error can occur".

On the other hand, `isReadableProperty("missing")` returning `false` is generally safer than trying `getPropertyValue("missing")` and using exceptions for probing. For nested paths, you still need to handle path-resolution errors if they occur.

## 8. Integration with DataBinder: Metadata Check vs. Binding Permission

In Spring MVC, `@ModelAttribute` is usually populated with request data via `WebDataBinder`, while the underlying `DataBinder` builds on property access. Crucially: **writable according to BeanWrapper does not mean allowed to be bound from a client**.

Look at the following example (part of a method, requiring the declared `Person` class):

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

Person person = new Person();
DataBinder binder = new DataBinder(person, "person");
binder.setAllowedFields("name", "active");

// Client also sends an unauthorized field.
MutablePropertyValues input = new MutablePropertyValues()
        .add("name", "Lan")
        .add("active", "true")
        .add("address.city", "Somewhere");

binder.bind(input);

System.out.println(person.getName());                 // Lan
System.out.println(person.isActive());                // true
System.out.println(person.getAddress().getCity());    // null
System.out.println(binder.getBindingResult()
        .getSuppressedFields().length);                // 1
~~~

This is an **illustrative excerpt**, not a standalone class. Even though `BeanWrapperImpl` would consider `address.city` writable, `DataBinder`'s **allowlist** excluded that field from assignment. Suppressed fields should be inspected if the application needs to log or reject out-of-contract data.

**Safety rule:** only bind into request DTOs containing strictly the required fields, use allowed fields for property binding, and continue verifying action authorization in services. `isWritableProperty` only states accessor capability, **not a security control against mass assignment**.

To check whether data is valid, use `Validator`/Jakarta Validation and `BindingResult`. The `isReadableProperty` and `isWritableProperty` methods **do not perform Bean Validation**.

## 9. Common Mistakes

### Mistake 1 — confusing private field names with bean properties

~~~java
public class Example {
    private String title;
}
~~~

With standard `BeanWrapperImpl`, `title` does not become a readable/writable JavaBeans property just by having a field. Add appropriate accessors if that access belongs to the class's API design, or deliberately choose direct-field access when there is a clear technical reason.

### Mistake 2 — assuming having a getter always implies having a setter

For example, `getId()` may exist solely to display a system-generated ID, with no `setId(...)`. `isReadableProperty("id")` can be `true` while `isWritableProperty("id")` is `false`. This can be used to build read-only internal views, though the UI still needs its own permission policies.

### Mistake 3 — using isWritableProperty for security filtering

A property having a setter does not mean users are allowed to set it. Fields like `isAdmin`, `price`, `role`, or `ownerId` may still have setters for internal logic. Use DTOs, allowlists, and explicit authorization checks.

### Mistake 4 — thinking isReadableProperty already reads the content

`isReadableProperty("name")` only returns `true/false`, not the user's name. You must call `getPropertyValue("name")` when you need the value, and handle getter exceptions appropriately.

### Mistake 5 — assuming every nested path is valid

`"address.city"` depends on the `address` object; `"items[5].name"` also depends on the collection and index bounds. Check the object graph and configuration; do not guess from text paths.

### Mistake 6 — misunderstanding boolean conventions

Getter `isActive()` usually maps to property `active`. However, a regular method like `hasToken()` is not a JavaBeans getter for property `token`. Naming and return types must follow introspection rules.

### Mistake 7 — using BeanWrapper for every data model

Immutable DTOs/records may not provide setters. Spring has a separate constructor binding mechanism; do not add setters to immutable objects just to make `isWritableProperty` return `true`.

### Mistake 8 — ignoring type conversion errors

`isWritableProperty("age") == true` does not prove the string `"not-a-number"` can be assigned to `int age`. When calling `setPropertyValue(...)`, handle conversion failures; with `DataBinder`, inspect `BindingResult`.

## 10. Self-Check Questions

1. A JavaBean has only `getOrderId()` and no `setOrderId(...)`. What will the two methods return when queried for `"orderId"`?
2. If a class declares only `private String token` and `setToken(String)`, can `token` be read via `BeanWrapper#getPropertyValue`?
3. Why can `isWritableProperty("address.city")` depend on the current state of `address`?
4. If `isWritableProperty("role")` returns `true` yet `role` must not be submitted by clients, which component should block it in Spring MVC?
5. How do `isReadableProperty("name")` and `getPropertyValue("name")` differ?
6. Does a `record` DTO without setters necessarily fail to be constructed from a request? Explain the difference between property binding and constructor binding.
7. Even when getters/setters exist, in what situations can read/write operations still fail?

**Takeaway:** `BeanWrapper.isReadableProperty(name)` and `isWritableProperty(name)` are probes for property **read** and **write** capability under Spring's access mechanism. They are very useful when building dynamic tooling/mappers, yet the results are only metadata/accessibility; actual operations require `getPropertyValue`/`setPropertyValue`, and external data must still pass through security, conversion, and validation rules.

## Official References

- Spring Framework Reference — Data Binding, Property Binding with BeanWrapper: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework Javadoc — PropertyAccessor: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/PropertyAccessor.html
- Spring Framework Javadoc — BeanWrapper: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/BeanWrapper.html
- Spring Framework Javadoc — BeanWrapperImpl: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/BeanWrapperImpl.html
- Spring Framework Javadoc — DataBinder: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Javadoc — PropertyAccessorFactory: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/PropertyAccessorFactory.html