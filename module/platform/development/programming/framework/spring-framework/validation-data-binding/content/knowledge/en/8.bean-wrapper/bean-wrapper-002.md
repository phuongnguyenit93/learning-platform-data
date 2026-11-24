# BeanWrapperImpl and the Wrapped Object in Spring Framework

## 1. What Is BeanWrapperImpl?

In Spring Framework, `BeanWrapper` is the interface for accessing, reading, and writing **JavaBean properties** by name instead of calling each getter/setter directly in source code. `BeanWrapperImpl` is the default implementation of this interface, located in the `org.springframework.beans` package.

A `BeanWrapperImpl` **wraps** a specific Java object and works with that object's properties. From a developer's perspective:

```text
        BeanWrapperImpl (metadata/property access mechanism)
                     |
         holds a reference to the object
                     |
                     v
            Person (JavaBean)
            ├── name: String
            ├── age: Integer
            └── address: Address
                      └── city: String
```

Example:

```java
Person person = new Person();
BeanWrapperImpl wrapper = new BeanWrapperImpl(person);

wrapper.setPropertyValue("name", "Lan");
Object value = wrapper.getPropertyValue("name");
```

In the illustration above, `person` must be a class with suitable setters/getters; the wrapper uses the property name `"name"` to interact with **the same `person` object**. `value` receives `"Lan"` if the property works normally.

The wrapped object (target object) is the instance passed to the constructor or attached via `setWrappedInstance(...)`. It is not a copy, a new DTO, an AOP proxy, or a bean automatically created by Spring IoC just because `new BeanWrapperImpl(person)` was called.

### Four Key Points

1. **The wrapper has target state:** each wrapper references a specific object; the target can be switched when needed.
2. **Reads/writes operate on the target object:** calling `setPropertyValue(...)` actually mutates the instance's properties via the JavaBean mechanism.
3. **The wrapper uses class metadata:** property names, data types, readability/writability, and conversion behavior are inferred from JavaBeans introspection, not merely from `private` field names.
4. **The wrapper is an infrastructure tool:** `DataBinder` and Spring's bean creation/configuration mechanisms typically use it indirectly; ordinary applications do not necessarily need to interact with it directly.

## 2. Relationship Between Interface and Implementation

`BeanWrapper` belongs to `org.springframework.beans` and extends the capabilities of `ConfigurablePropertyAccessor`: property access, type conversion, metadata inspection, and registering converters when needed.

`BeanWrapperImpl` extends `AbstractNestablePropertyAccessor` and implements `BeanWrapper`. Part of its practical API:

| API | Meaning |
| --- | --- |
| `new BeanWrapperImpl(object)` | Creates a wrapper around an existing instance |
| `new BeanWrapperImpl(SomeClass.class)` | Creates an instance of the class and wraps it |
| `new BeanWrapperImpl()` | Creates a wrapper with no target yet; a target must be set before access |
| `getWrappedInstance()` | Returns the exact object the wrapper is wrapping |
| `getWrappedClass()` | Returns the `Class<?>` of the wrapped object |
| `setWrappedInstance(other)` | Switches the target to another instance |
| `getPropertyValue("name")` | Reads a property value |
| `setPropertyValue("name", value)` | Writes a property value |
| `isReadableProperty("name")` | Whether the property can be read via an accessor |
| `isWritableProperty("name")` | Whether the property can be written via an accessor |
| `getPropertyDescriptor("name")` | Retrieves the JavaBeans `PropertyDescriptor` metadata |
| `getPropertyDescriptors()` | Retrieves all property descriptors of the bean |
| `setAutoGrowNestedPaths(true)` | Enables auto-creation of nested paths under supported conditions |
| `setConversionService(service)` | Attaches a `ConversionService` for type conversion |
| `registerCustomEditor(...)` | Registers a custom `PropertyEditor` by type/property |

**Distinguishing "wrapper" and "wrapped instance":** the `BeanWrapperImpl` variable holds the access operations/configuration; `getWrappedInstance()` retrieves the business Java object. Callers can keep a reference to that object and observe its changes after the wrapper invokes setters.

`BeanWrapperImpl` is not a validation interface: it does not have `BindingResult` or `Errors` to accumulate errors automatically like `DataBinder`. Direct property access errors are typically raised as exceptions.

## 3. Three Ways to Create a Wrapper and Target Lifecycle

### Approach A: wrapping an existing object

```java
Person person = new Person();
BeanWrapperImpl wrapper = new BeanWrapperImpl(person);

boolean same = wrapper.getWrappedInstance() == person; // true
```

The `==` operator here checks **reference identity**, not `equals()`. The wrapper **does not clone** `person`. If external code modifies `person`, the wrapper reads the new value; if the wrapper changes `person.name`, the external `person` variable sees it too.

### Approach B: having the wrapper instantiate an object from a `Class`

```java
BeanWrapperImpl wrapper = new BeanWrapperImpl(Person.class);
Person created = (Person) wrapper.getWrappedInstance();
```

The constructor taking `Class<?>` attempts to instantiate the class and wrap that instance. The class must be instantiable via Spring's mechanism (the example uses a public no-arg constructor). An abstract class, missing suitable constructor, or a throwing constructor can cause instantiation to fail.

An object created from `Class` **does not automatically become a Spring bean in `ApplicationContext`** and does not automatically receive dependency injection, lifecycle callbacks, transactional proxies, or service configuration. This is an infrastructure-level instantiation and property-access operation.

### Approach C: creating an empty wrapper and then setting the target

```java
BeanWrapperImpl wrapper = new BeanWrapperImpl();
wrapper.setWrappedInstance(new Person());
```

An empty wrapper has no wrapped instance to read/write yet; calling operations that require a target before assigning one can throw an exception. Approach A is more concise and easier to control when the object already exists.

### Simple Lifecycle

```text
new BeanWrapperImpl(first)
  -> wrapper.getWrappedInstance() == first
  -> wrapper.setPropertyValue("name", "Lan")
  -> first.name becomes "Lan"
  -> wrapper.setWrappedInstance(second)
  -> wrapper.getWrappedInstance() == second
  -> subsequent operations target second
  -> first still retains the name "Lan"
```

Switching the target **does not copy** values from the old object to the new one. If two wrappers point to the same mutable instance, they can observe the same changes; that does not make wrappers a multithreaded synchronization mechanism.

## 4. Runnable Java 17+ Example: Observing Changes on the Original Object

This example runs as a plain Java application using the Spring Beans library, **without needing Spring Boot or a web server**. It demonstrates object references, property reading/writing, nested properties, type conversion, and replacing the wrapped instance.

Create `pom.xml`:

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
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/example/BeanWrapperDemo.java`:

```java
package example;

import org.springframework.beans.BeanWrapperImpl;

public class BeanWrapperDemo {

    public static class Address {
        private String city;

        public Address() {}

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class Person {
        private String name;
        private Integer age;
        private Address address = new Address();

        public Person() {}

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static void main(String[] args) {
        Person first = new Person();
        BeanWrapperImpl wrapper = new BeanWrapperImpl(first);

        System.out.println("sameReference="
                + (wrapper.getWrappedInstance() == first));
        System.out.println("wrappedClass="
                + wrapper.getWrappedClass().getSimpleName());
        System.out.println("writableAge="
                + wrapper.isWritableProperty("age"));

        wrapper.setPropertyValue("name", "Lan");
        wrapper.setPropertyValue("age", "28");
        wrapper.setPropertyValue("address.city", "Hue");

        System.out.println("first=" + first.getName()
                + "/" + first.getAge()
                + "/" + first.getAddress().getCity());
        System.out.println("cityViaWrapper="
                + wrapper.getPropertyValue("address.city"));

        Person second = new Person();
        second.setName("Mai");

        wrapper.setWrappedInstance(second);
        System.out.println("changedReference="
                + (wrapper.getWrappedInstance() == second));
        System.out.println("newName="
                + wrapper.getPropertyValue("name"));

        wrapper.setPropertyValue("name", "An");
        System.out.println("secondName=" + second.getName());
        System.out.println("oldName=" + first.getName());
    }
}
```

Run in the directory containing `pom.xml`, with Java 17+ and Maven:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=example.BeanWrapperDemo
```

Stdout from `main` (ignoring logs produced by Maven/plugins):

```text
sameReference=true
wrappedClass=Person
writableAge=true
first=Lan/28/Hue
cityViaWrapper=Hue
changedReference=true
newName=Mai
secondName=An
oldName=Lan
```

**Explanation of each observation:**

1. `sameReference=true` verifies that the wrapper holds **the exact reference to `first`**.
2. `getWrappedClass().getSimpleName()` returns `Person`, because the target is a `Person` instance.
3. Property `age` has setter `setAge(Integer)`, so it is writable. Spring converts the string `"28"` to `Integer 28` via its conversion/property editor mechanism before calling the setter.
4. `address.city` is a nested path; `first.address` was already initialized, so the wrapper can locate and call `Address.setCity(...)`.
5. `setWrappedInstance(second)` switches the target. From that point on, calling `getPropertyValue("name")` returns `second`'s name, and `setPropertyValue("name", "An")` mutates `second`.
6. `oldName=Lan` shows that the `first` instance is neither replaced nor copied when the wrapper switches to `second`.

The `Person` and `Address` classes in the example have full JavaBeans getters/setters. If you write a field `private String name` without a setter, `BeanWrapperImpl` in default JavaBean mode cannot write that property via `setPropertyValue("name", ...)`.

## 5. How Does a JavaBean Property Differ from a Java Field?

`BeanWrapperImpl` is built on **JavaBeans** conventions, where properties are primarily identified through accessor methods and introspection metadata:

```java
public class Account {
    private String label;

    public String getLabel() { return label; }
    public void setLabel(String label) { this.label = label; }
}
```

With this class:

- `getLabel()` makes property `label` **readable**.
- `setLabel(String)` makes `label` **writable**.
- Field `label` is an internal storage detail; the wrapper does not automatically perform direct-field reflection.
- A property with only a getter is **read-only** from BeanWrapper's perspective; one with only a setter is **write-only** (if recognized by JavaBeans introspection).

How to check before accessing:

```java
BeanWrapperImpl wrapper = new BeanWrapperImpl(new Account());

if (wrapper.isWritableProperty("label")) {
    wrapper.setPropertyValue("label", "Ready");
}

if (wrapper.isReadableProperty("label")) {
    System.out.println(wrapper.getPropertyValue("label"));
}
```

The snippet above must be placed inside a method that has class `Account`; output after setting:

```text
Ready
```

**Do not mechanically infer property names from field names.** For example, a JavaBean can expose a property from a `getEnabled()/setEnabled(...)` pair even if the backing field has a different name. For booleans, an `isEnabled()` getter can also be recognized by JavaBeans.

### Inspecting Metadata

```java
import java.beans.PropertyDescriptor;
import org.springframework.beans.BeanWrapperImpl;

BeanWrapperImpl wrapper = new BeanWrapperImpl(new Account());
PropertyDescriptor descriptor =
        wrapper.getPropertyDescriptor("label");

System.out.println(descriptor.getName());
System.out.println(descriptor.getPropertyType().getSimpleName());
```

This is a snippet inside a method of a class containing `Account`; stdout:

```text
label
String
```

`getPropertyDescriptor(...)` returns a JavaBeans descriptor, including `getReadMethod()` and `getWriteMethod()` when present. If the property does not exist, Spring may throw `InvalidPropertyException`; you can call `isReadableProperty`/`isWritableProperty` for appropriate checks, while still handling errors in case an object's state changes between check and operation.

**Records and immutable DTOs:** A Java `record` has accessors like `name()` and no JavaBean setters, so it is unsuitable as a mutable object for `BeanWrapperImpl.setPropertyValue(...)` to assign fields. For immutable input, consider constructor binding in `DataBinder`/`@ModelAttribute`; do not use BeanWrapper as a mechanism to copy and mutate records.

## 6. Types of Operations on the Wrapped Object

| Operation | Effect on the target |
| --- | --- |
| `getWrappedInstance()` | Retrieves the current reference, without cloning |
| `getWrappedClass()` | Retrieves the runtime class of the current target |
| `getPropertyValue("name")` | Reads via accessor |
| `setPropertyValue("name", "Lan")` | Writes to the current target via setter |
| `setPropertyValues(...)` | Attempts to write a group of properties, following the accessor's error-handling rules |
| `setWrappedInstance(newTarget)` | Switches target; subsequent operations target the new instance |
| `new BeanWrapperImpl(Target.class)` | Creates a new target without automatically registering it in the IoC container |

There are two levels of "change" to distinguish:

- **Changing a property value:** `wrapper.setPropertyValue("name", ...)` — the wrapper still wraps **the same object**, only the object's state changes.
- **Changing the wrapped instance:** `wrapper.setWrappedInstance(second)` — the wrapper switches to **a different object**. The old target remains alive if external references exist; it is neither deleted nor automatically synchronized.

If `target` is a Spring bean already managed by the container, a wrapper can read/write properties of the supplied instance. However, writing properties manually at runtime **does not re-run the lifecycle**, and does not guarantee reapplying `@ConfigurationProperties` binding, bean post-processors, or dependency injection.

## 7. Nested Properties: Traversing from Parent Bean to Child Bean

BeanWrapper supports paths such as:

| Path | Meaning |
| --- | --- |
| `name` | Simple property |
| `address.city` | `city` property on the `address` bean |
| `items[0].price` | `price` of element at index `0` in `items` |
| `attributes[region]` | Value for map key `"region"` |
| `matrix[1][2]` | Multi-dimensional access if types and accessors support it |

For example, `wrapper.setPropertyValue("address.city", "Hue")` tells the wrapper to look up `address` in the root object, then access the `city` property on the child object. In the runnable example, `address` was created in a field initializer, so no null nested path error occurs.

### When the Nested Object Is `null`

If `person.getAddress() == null` and code runs:

```java
wrapper.setPropertyValue("address.city", "Hue");
```

with a plain wrapper in its default non-auto-grow configuration, Spring typically throws `NullValueInNestedPathException`. You can enable:

```java
wrapper.setAutoGrowNestedPaths(true);
wrapper.setPropertyValue("address.city", "Hue");
```

When enabled, Spring attempts to instantiate intermediate objects if the types are instantiable, the properties are writable, and configuration permits it. Do not assume every interface, abstract type, custom constructor, or collection will instantiate successfully. For collections/arrays, `setAutoGrowCollectionLimit(int)` can prevent unbounded expansion from client-supplied indices.

**Note on context differences:** auto-grow configuration in `DataBinder` has its own defaults/limits depending on the Spring version; do not infer the behavior of a fresh `BeanWrapperImpl` from a configured `DataBinder`. If a nested path must be present, initializing it explicitly in the DTO can be more predictable than enabling auto-grow.

### When a Property Has an Index or Map Key

`items[0].price` only works when `items` is actually a list/array and that element has an accessible type. Errors can occur if the collection is uninitialized, the index is out of bounds, or the element object has no writable property. Path names must be treated as **untrusted input** when coming from requests.

## 8. Type Conversion Before Invoking Setters

`BeanWrapperImpl` does not necessarily require input matching the setter's exact Java type. It can convert from the source type to the target type through configured converters and default JavaBeans `PropertyEditor`s.

Example:

```java
// Person.age is Integer, setter is setAge(Integer).
wrapper.setPropertyValue("age", "28");
// getPropertyValue("age") then returns Integer 28.
```

Even though the input is a `String`, the wrapper can convert it to `Integer` before invoking the setter. If `"abc"` is passed without a matching converter, Spring may throw `TypeMismatchException` or a conversion/property-access related exception.

### Integrating ConversionService

You can provide a `ConversionService` explicitly to the wrapper when an extensible type conversion system is needed:

```java
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.core.convert.support.DefaultConversionService;

// Snippet inside a method, with variable person of type Person:
BeanWrapperImpl wrapper = new BeanWrapperImpl(person);
wrapper.setConversionService(new DefaultConversionService());
wrapper.setPropertyValue("age", "31");
```

`DefaultConversionService` provides common converters. Date/time formatters using `@DateTimeFormat` typically require `FormattingConversionService` and appropriate configuration; do not assume a plain Java `BeanWrapperImpl` automatically picks up all Spring MVC formatter annotations.

A traditional JavaBeans option is registering a custom editor:

```java
wrapper.registerCustomEditor(
        java.time.LocalDate.class,
        new java.beans.PropertyEditorSupport() {
            @Override
            public void setAsText(String text) {
                setValue(java.time.LocalDate.parse(text));
            }
        });
```

This snippet is for an existing wrapper; when the target property has type `LocalDate`, the editor above can parse ISO strings such as `2026-11-02`. Format exceptions for invalid input must be handled according to the application contract. In new code, `ConversionService` is usually easier to extend and test than stateful editors.

**Conversion is not validation.** `age=-5` converts to Integer successfully yet still violates business rules; `BeanWrapperImpl` does not automatically run Jakarta Bean Validation `@Min`/`@NotNull` when calling setters. To collect errors and run validation, use `DataBinder`, `Validator`, or Spring MVC's corresponding mechanisms.

## 9. BeanWrapperImpl, DataBinder, and Spring IoC: What Is Each Responsible For?

| Criterion | `BeanWrapperImpl` | `DataBinder` | `BeanFactory` / Spring IoC |
| --- | --- | --- | --- |
| Primary purpose | Read/write JavaBean properties by name | Bind data from `PropertyValues`, manage errors/validation | Create and manage lifecycle/dependencies of Spring beans |
| Wrapped/target object | The wrapped object | Binding target (typically property access or constructor binding) | Container-managed bean |
| Type conversion | Has conversion/editor mechanism | Yes, via binding infrastructure | Yes, when configuring properties |
| Errors | Typically throws exceptions directly | Collects errors in `BindingResult` when appropriate | Bean creation/configuration errors via container exceptions |
| Automatic validation | No | Yes, if a validator is configured/invoked | Depends on configuration and integration |
| Allowed fields for requests | Not a request binder whitelist | Has `setAllowedFields(...)` | Not a request-binding feature |

`DataBinder` example inside a method (assuming `person` has getters/setters as in the example):

```java
import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

DataBinder binder = new DataBinder(person, "person");
binder.setAllowedFields("name", "age");
binder.bind(new MutablePropertyValues(
        Map.of("name", "Lan", "age", "28")));

if (binder.getBindingResult().hasErrors()) {
    // Handle conversion/binding errors.
}
```

`DataBinder` uses Spring's property access mechanism and adds error management, allowed fields, and validation. `BeanWrapperImpl` is a lower-level tool for directly accessing a JavaBean object; it is neither equivalent to `DataBinder` nor to `BeanFactory`.

For REST JSON bodies, `HttpMessageConverter` (typically Jackson) handles deserialization into DTOs; do not describe `BeanWrapperImpl` as Spring MVC's default JSON converter.

### Does BeanWrapperImpl Create Spring Beans?

`new BeanWrapperImpl(Person.class)` instantiates an object through a helper; it does **not** mean `Person` is registered in `ApplicationContext`. To have an object managed by IoC, create/register the bean through appropriate container configuration. Conversely, Spring may use the BeanWrapper mechanism **internally** during bean configuration, but that does not turn an application-created wrapper into a Spring bean.

## 10. Common Errors When Working with the Target

| Situation | Common symptom/exception | What to check |
| --- | --- | --- |
| Property does not exist | `NotWritablePropertyException` on write, `NotReadablePropertyException` on read | Check property name, getter/setter, and method types |
| Property exists but is read-only | `NotWritablePropertyException` | No valid setter; use constructor binding or an explicit setter |
| String cannot be converted to target type | `TypeMismatchException` | Check converter/editor and input data |
| Nested property has `null` parent object | `NullValueInNestedPathException` | Initialize child bean or enable auto-grow when appropriate |
| Out-of-bounds index used | `InvalidPropertyException` or index-related exception | Check list/array and auto-grow limit |
| Target not assigned yet | Exception because wrapper has no object | Use constructor taking an object or `setWrappedInstance(...)` |
| Switched target and assumed wrapper still writes to old target | Old object receives no new updates | Check `getWrappedInstance() == expected` reference |
| Target class cannot be instantiated from `Class` | `BeansException`/constructor-related exception | Use a pre-created instance or a class with a compatible constructor |
| Custom converter not registered | Conversion does not support desired format | Attach suitable `ConversionService`/`PropertyEditor` |
| Attempted to write directly to `private field` without setter | Property is not writable | Use a JavaBean setter or a dedicated direct-field mechanism |

Specific exceptions depend on the operation type and Spring version/configuration; the entries above are common cases, not a guarantee of exact exception types for every object model.

### Catching Errors on Direct Calls

```java
import org.springframework.beans.BeansException;
import org.springframework.beans.BeanWrapperImpl;

// Inside a method with a valid Person object:
BeanWrapperImpl wrapper = new BeanWrapperImpl(person);

try {
    wrapper.setPropertyValue("age", "not-a-number");
} catch (BeansException ex) {
    // Report data error or use DataBinder to produce BindingResult.
    System.out.println(ex.getClass().getSimpleName());
}
```

The snippet above must be placed in a valid method. For an `Integer` `age` property with default type conversion, the exception is typically `TypeMismatchException`; do not treat the printed exception name as fixed output in every situation. When processing multiple fields from a form, using `DataBinder` aggregates field errors better than catching individual exceptions from BeanWrapper.

## 11. Checking the Target and Readability/Writability Before Operating

If code processes property names dynamically, inspecting metadata helps reduce errors:

```java
import java.util.Set;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;

// Example running inside a method with a target variable that has JavaBean setters.
BeanWrapper accessor = new BeanWrapperImpl(target);
Set<String> allowed = Set.of("name", "age");

String propertyName = "name";
Object value = "Lan";

if (allowed.contains(propertyName)
        && accessor.isWritableProperty(propertyName)) {
    accessor.setPropertyValue(propertyName, value);
}
```

This is an **illustrative** snippet requiring a `target` object with matching properties. For untrusted input, the `allowed` whitelist is an important layer of defense; `isWritableProperty(...)` **only** indicates API-level writability, not whether the client is authorized to write that property.

When handling forms/requests, continue to apply Bean Validation and authorization in the service layer. Fields such as `role`, `admin`, `approved`, or `balance` may be writable properties on a business object without being data the client is permitted to modify.

**Avoid mass assignment:** Do not feed all keys from a request directly into a loop calling `wrapper.setPropertyValue(key, request.get(key))` on an entity containing sensitive properties. Use dedicated DTOs, allowlists of permitted fields, or `DataBinder#setAllowedFields(...)` when handling external data.

## 12. Nested Path Configuration and Impact on the Object Graph

When a wrapper writes a nested property, the change can affect existing child objects, for example:

```text
Person first
  address ────────> Address(city="Hanoi")

wrapper.setPropertyValue("address.city", "Hue")

Person first
  address ────────> Address(city="Hue")
```

**The Address object can remain the exact same instance**, with only its `city` property modified. If other code also holds a reference to that `Address`, it sees the new value. This is a natural consequence of a shared mutable object graph, not an event-sourcing or unit-of-work mechanism.

To avoid side effects, proactively create/copy the data structure before wrapping, or use immutable DTOs with appropriate constructors. `BeanWrapperImpl` does not provide deep copying or undo. For objects tied to transactions/databases, mutating a JavaBean in memory **does not automatically mean** changes are persisted to the database; the persistence context/transaction still governs storage.

## 13. Advanced Details on Targets and Introspection

### Where Is Reflection Used?

Spring uses JavaBeans introspection and accessor invocation mechanisms to work with properties. It can cache metadata per class to reduce repeated getter/setter lookup costs. However, **cached metadata does not mean the wrapper synchronizes state between two objects**. `getWrappedInstance()` still represents the current target.

### When the Target Is a Subclass/Proxy

`getWrappedClass()` returns the runtime class of the wrapped object. If the target is actually a proxy/subclass, the runtime class may be the proxy class rather than the original domain class. Whether properties are accessible also depends on the proxy, public accessors, visibility, and how the proxy forwards methods. Do not always use `getWrappedClass().getSimpleName()` as a stable business identifier.

### When the Target Is Replaced with a Different Class

When `setWrappedInstance(other)` receives an object of a different class, the wrapper must update its access/introspection information for the new target. Previous property names and types are no longer guaranteed to exist; for instance, a wrapper wrapping `Person` with an `age` property switched to `Product` without `age` will cause the old operation to fail.

**Do not cache `PropertyDescriptor` and apply it arbitrarily to another target class.** A descriptor is metadata tied to a specific class/property, not a universal command for all objects.

### Multiple Threads Using the Same Wrapper?

`BeanWrapperImpl` holds mutable state: target reference, conversion/editor configuration, and nested accessors. Do not share a mutable wrapper as a singleton handling concurrent requests. Create wrappers per unit of work, or use clear synchronization/ownership design if sharing is unavoidable.

Even if two separate wrappers wrap the same target, a **mutable target** can still suffer race conditions when multiple threads mutate it; separate wrappers do not protect the underlying object.

## 14. Verification Exercises and Frequently Asked Questions

### Exercise A — Same Object or Copy?

Suppose:

```java
Person first = new Person();
BeanWrapperImpl wrapper = new BeanWrapperImpl(first);
wrapper.setPropertyValue("name", "Mai");
System.out.println(first.getName());
```

With a `Person` class having setters/getters as in section 4, the output is:

```text
Mai
```

Because the wrapper writes directly to the `first` instance without creating a copy.

### Exercise B — After Switching Target?

```java
Person first = new Person();
Person second = new Person();

BeanWrapperImpl wrapper = new BeanWrapperImpl(first);
wrapper.setPropertyValue("name", "Lan");
wrapper.setWrappedInstance(second);
wrapper.setPropertyValue("name", "An");

System.out.println(first.getName());
System.out.println(second.getName());
```

Output:

```text
Lan
An
```

Each call writes to **the target active at the time of the call**.

### Exercise C — Readable Does Not Mean Writable

For a DTO that has only `getId()` and no `setId(...)`, `isReadableProperty("id")` can be `true` while `isWritableProperty("id")` is `false`. Do not use BeanWrapper to bypass immutability policies by mutating `private` fields.

### Debugging Checklist

1. Verify `wrapper.getWrappedInstance() == expectedObject` before/after switching targets.
2. Verify `wrapper.getWrappedClass()` matches the expected runtime class.
3. Check `isReadableProperty(...)` and `isWritableProperty(...)` before dynamic operations.
4. If writing a nested path fails, check whether any intermediate bean is `null`; evaluate whether auto-grow should be enabled.
5. If conversion fails, check setter type, editor/conversion service, and source value.
6. If values do not update as expected, check whether the wrapper switched target, whether the object graph shares references, and whether setters have side effects.
7. If processing request input, check whitelists/DTOs, validation, write permissions, and collection index limits.
8. If running across multiple threads, check ownership of both the wrapper and the wrapped object.

## 15. Key Takeaways

`BeanWrapperImpl` is the controller for accessing **JavaBean properties**; the **wrapped object** is the actual Java instance the controller is currently operating on. The constructor taking an object keeps a reference to that object; `getWrappedInstance()` returns that reference; `setPropertyValue(...)` usually mutates the instance itself; and `setWrappedInstance(...)` switches the wrapper to another instance without copying data. With this understanding, you can accurately explain property reading/writing, nested paths, type conversion, side effects, and BeanWrapper's role underneath `DataBinder` and Spring IoC.

## References

- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework API — BeanWrapper](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapper.html)
- [Spring Framework API — BeanWrapperImpl](https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework API — AbstractNestablePropertyAccessor](https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/beans/AbstractNestablePropertyAccessor.html)
- [Spring Framework API — DataBinder](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework API — PropertyAccessor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/PropertyAccessor.html)
