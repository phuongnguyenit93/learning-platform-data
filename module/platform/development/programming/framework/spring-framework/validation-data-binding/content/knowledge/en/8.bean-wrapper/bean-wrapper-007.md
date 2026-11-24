# PropertyAccessorFactory: JavaBean Access or Direct Field Access in Spring Framework

**`PropertyAccessorFactory`** belongs to Spring Framework's `org.springframework.beans` package. It is a simple factory for creating a **property accessor** object wrapping an existing Java object, allowing properties to be read/written by name. This API provides two key choices:

- `PropertyAccessorFactory.forBeanPropertyAccess(target)`: returns a `BeanWrapper` and accesses properties following **JavaBeans** conventions (getters/setters).
- `PropertyAccessorFactory.forDirectFieldAccess(target)`: returns a `ConfigurablePropertyAccessor` and accesses **the object's fields directly** (typically via reflection), bypassing getters/setters.

Both operate **on the exact instance passed in**, supporting named property operations and type conversion. They differ in how property readability/writability is determined, where getter/setter logic executes, and which constraints can be bypassed if direct field access is used.

This article targets Java 17+ and Spring Framework 6.x; the complete example uses Maven and Spring 6.2.14. This is foundational knowledge for `BeanWrapper` and data binding and does not require booting a Spring Boot application.

## 1. What Problem Does the Factory Solve?

Given a Java object:

```java
public class Customer {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name == null ? null : name.strip();
    }
}
```

Normally Java code calls `customer.setName(" Lan ")`. However, components such as data mappers, form binding, bean configuration, or dynamic tools often only know the property name at runtime, e.g., the string `"name"`. A `PropertyAccessor` can perform:

```java
accessor.setPropertyValue("name", " Lan ");
Object current = accessor.getPropertyValue("name");
```

These are two **illustrative** statements assuming an `accessor` variable has been created; not a standalone program.

The factory spares callers from knowing or instantiating concrete implementations such as `BeanWrapperImpl` and `DirectFieldAccessor`. Choosing the **access style** expresses intent: whether Spring should respect the JavaBeans interface or operate on the object's actual fields.

The factory does not clone the target, does not register the target as a Spring bean, does not place the object into an `ApplicationContext`, does not run validation automatically, and does not protect properties from untrusted data on its own.

## 2. Standard API and Return Types

Two static methods:

```java
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.ConfigurablePropertyAccessor;
import org.springframework.beans.PropertyAccessorFactory;

BeanWrapper bean =
    PropertyAccessorFactory.forBeanPropertyAccess(target);

ConfigurablePropertyAccessor fields =
    PropertyAccessorFactory.forDirectFieldAccess(target);
```

This is a fragment requiring a non-null Java object `target`. The class names and signatures are meaningful:

| Method | Declared return type | Access style | Common implementation |
| --- | --- | --- | --- |
| `forBeanPropertyAccess(Object target)` | `BeanWrapper` | JavaBeans properties through valid getters/setters | `BeanWrapperImpl` |
| `forDirectFieldAccess(Object target)` | `ConfigurablePropertyAccessor` | Direct instance fields, potentially including `private` fields when reflection is permitted | `DirectFieldAccessor` |

Interface hierarchy:

```text
PropertyAccessor
  └── ConfigurablePropertyAccessor
        └── BeanWrapper

Typical implementations:
  BeanWrapperImpl  -> BeanWrapper
  DirectFieldAccessor -> ConfigurablePropertyAccessor
```

`BeanWrapper` adds JavaBeans introspection capabilities such as `getPropertyDescriptors()`. The result of `forDirectFieldAccess` is only declared as `ConfigurablePropertyAccessor`, so you **cannot directly call** `BeanWrapper`-only APIs like `getPropertyDescriptors()` on `fields`.

Both support `getPropertyValue(...)`, `setPropertyValue(...)`, `isReadableProperty(...)`, `isWritableProperty(...)`, `getPropertyType(...)`, registering custom editors, setting a `ConversionService`, and configuring nested path handling.

### 2.1. How Does `PropertyAccessor` Here Differ from SpEL's `PropertyAccessor`?

There are two APIs with the same name but different purposes:

- `org.springframework.beans.PropertyAccessor`: interface for manipulating properties by path string; `PropertyAccessorFactory` uses this interface.
- `org.springframework.expression.PropertyAccessor`: strategy for reading/writing properties in **Spring Expression Language (SpEL)** when evaluating expressions.

Do not accidentally import the SpEL class when writing `PropertyAccessorFactory` code. Identical simple names do not make the interfaces interchangeable.

## 3. `forBeanPropertyAccess`: JavaBeans-Based Access

With `BeanWrapper`, Spring identifies properties from JavaBeans methods through introspection. In standard cases:

- `getName()` is the getter for property `name`.
- `isActive()` can serve as the getter for boolean property `active`.
- `setName(String value)` is the setter for `name`.
- An object can have read-only properties (getter, no setter) or write-only properties (setter, no getter) depending on its method structure.
- Getters/setters can execute logic, such as normalizing strings, updating internal state, or enforcing preconditions.

Example:

```java
Customer customer = new Customer();
BeanWrapper wrapper =
    PropertyAccessorFactory.forBeanPropertyAccess(customer);

wrapper.setPropertyValue("name", "  Lan  ");
System.out.println(wrapper.getPropertyValue("name"));
```

With the `Customer` class in section 1, the output is:

```text
Lan
```

Because `setPropertyValue` goes through `setName`, the `strip()` logic runs before the object stores the value. This is a very important distinction when setters enforce business invariants.

Spring can treat a getter method as a JavaBeans property even when **no field with that name exists**. For example, `getFullName()` can join `firstName` and `lastName`; property `fullName` will be readable through `BeanWrapper`, though not writable without `setFullName(...)`.

### 3.1. BeanWrapper Supports Introspection

`BeanWrapper` offers APIs such as:

```java
wrapper.isReadableProperty("name");
wrapper.isWritableProperty("name");
wrapper.getPropertyType("name");
wrapper.getPropertyDescriptor("name");
wrapper.getPropertyDescriptors();
```

From these, dynamic code can determine which properties are readable/writable and what their data types are. `getPropertyDescriptor` and `getPropertyDescriptors` relate to JavaBeans introspection, so this capability is exclusive to the `BeanWrapper` branch of the factory's return types.

Do not conclude that because a `private String name` field exists, `BeanWrapper` can always write `name`. If the class has no setter recognized by JavaBeans introspection, `isWritableProperty("name")` is typically `false` even though the field exists.

## 4. `forDirectFieldAccess`: Accessing Actual Fields

`DirectFieldAccessor` accesses an object's fields via reflection instead of invoking setters/getters. A class like the following can still have its field updated despite lacking a setter:

```java
public class FieldOnly {
    private String token;

    public String viewToken() {
        return token;
    }
}
```

An integration snippet:

```java
FieldOnly obj = new FieldOnly();

ConfigurablePropertyAccessor direct =
    PropertyAccessorFactory.forDirectFieldAccess(obj);

direct.setPropertyValue("token", "OK");
System.out.println(obj.viewToken());
```

Output:

```text
OK
```

In the same design, `BeanWrapper` **has no JavaBeans setter `setToken`** to write property `token`. `token` being `private` does not completely stop direct field access when runtime reflective access is allowed; conversely, it also **does not** mean clients should be allowed to modify that field.

### 4.1. Setter Logic Does Not Run

Suppose a `name` field has a setter:

```java
public void setName(String name) {
    this.name = name.strip();
}
```

If you call `forBeanPropertyAccess` and then `setPropertyValue("name", "  Lan  ")`, the setter normalizes it to `"Lan"`. If you call `forDirectFieldAccess` and assign the same string, the field retains `"  Lan  "` because the setter is never invoked.

This can be used intentionally in an internal migration tool, yet it can also break object invariants. For business logic or HTTP input, consider receiving data into a dedicated DTO, validating it, and applying changes through business APIs.

### 4.2. What Are the Limitations of Direct Field Access?

- Requires an **actual field** to resolve the name. A computed JavaBeans property with only a getter and no matching backing field will not automatically become a field for `DirectFieldAccessor`.
- Requires runtime reflective access permissions. Under the Java Platform Module System (JPMS) where a package is not open for reflection, accessing non-public fields can fail. Do not treat reflective access as an automatic bypass for module boundaries.
- Do not rely on direct field access to mutate `final` fields, record components, or immutable data. Mutating them may be unsupported or produce undefined consequences in object design.
- Direct field access can traverse inherited fields and nested paths when accessible; still, do not assume it can update every kind of object, proxy, or specialized structure.
- Reflection skips setter/getter logic and can lose method-driven behaviors. Validation/business rules will not run automatically.

## 5. Comparison Table of Both Access Approaches

| Aspect | Bean property access | Direct field access |
| --- | --- | --- |
| Factory call | `forBeanPropertyAccess(obj)` | `forDirectFieldAccess(obj)` |
| Return type | `BeanWrapper` | `ConfigurablePropertyAccessor` |
| How properties are identified | JavaBeans getters/setters | Actual fields in the class |
| Writing `name` | Via `setName(...)` | Writes directly to field `name` |
| Reading `name` | Via `getName()` | Reads field `name` directly |
| Without a setter | Property is typically not writable | Can still be written if a matching field exists and reflection permits |
| Setter normalizes/validates | Setter logic executes | Setter logic is bypassed |
| Computed property without field | Readable via getter | No matching field to read |
| Nested path `address.city` | Supported | Supported |
| Indexed/Map path | Supported when type/structure fits | Supported when type/structure fits |
| Type conversion | Supports `PropertyEditor`/`ConversionService` | Supports `PropertyEditor`/`ConversionService` |
| JavaBeans-specific introspection | `getPropertyDescriptor(s)` | Not part of the direct return type API |
| Usage in `DataBinder` | Default mode | Selected via `initDirectFieldAccess()` before binding |

You can declare a variable as `ConfigurablePropertyAccessor` for both because `BeanWrapper` extends it. If you need `BeanWrapper`-specific introspection, keep the variable typed as `BeanWrapper`.

## 6. Runnable Java 17 Example: Same Input, Two Different Results

This complete example verifies four points:

1. Bean access calls the setter, stripping whitespace.
2. Direct field access preserves the string and does not increment the setter counter.
3. Both accessors convert the string `"21"` to `int` using the same `ConversionService`.
4. A `private` field without a setter can still be updated via the direct accessor, whereas BeanWrapper reports it as non-writable.

### 6.1. Creating the Maven Project

```text
property-accessor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── AccessorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>property-accessor-demo</artifactId>
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
        <version>3.5.1</version>
        <configuration>
          <mainClass>example.AccessorDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

File `src/main/java/example/AccessorDemo.java`:

```java
package example;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.ConfigurablePropertyAccessor;
import org.springframework.beans.PropertyAccessorFactory;
import org.springframework.core.convert.support.DefaultConversionService;

public class AccessorDemo {

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
        private int age;
        private int setterCalls;
        private Address address = new Address();

        public String getName() {
            return name;
        }

        public void setName(String name) {
            setterCalls++;
            this.name = name.strip();
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }

        public int getSetterCalls() {
            return setterCalls;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static class FieldOnly {
        private String secret;

        public String showSecret() {
            return secret;
        }
    }

    public static void main(String[] args) {
        DefaultConversionService converters =
            new DefaultConversionService();

        Person beanPerson = new Person();
        BeanWrapper bean =
            PropertyAccessorFactory.forBeanPropertyAccess(beanPerson);
        bean.setConversionService(converters);

        bean.setPropertyValue("name", "  Lan  ");
        bean.setPropertyValue("age", "21");
        bean.setPropertyValue("address.city", "Ha Noi");

        System.out.println(
            "bean: name=[" + beanPerson.getName()
                + "] age=" + beanPerson.getAge()
                + " city=" + beanPerson.getAddress().getCity()
                + " setterCalls=" + beanPerson.getSetterCalls()
        );

        Person fieldPerson = new Person();
        ConfigurablePropertyAccessor direct =
            PropertyAccessorFactory.forDirectFieldAccess(fieldPerson);
        direct.setConversionService(converters);

        direct.setPropertyValue("name", "  Lan  ");
        direct.setPropertyValue("age", "21");
        direct.setPropertyValue("address.city", "Da Nang");

        System.out.println(
            "field: name=[" + fieldPerson.getName()
                + "] age=" + fieldPerson.getAge()
                + " city=" + fieldPerson.getAddress().getCity()
                + " setterCalls=" + fieldPerson.getSetterCalls()
        );

        FieldOnly fieldOnly = new FieldOnly();
        PropertyAccessorFactory.forDirectFieldAccess(fieldOnly)
            .setPropertyValue("secret", "OK");

        BeanWrapper beanView =
            PropertyAccessorFactory.forBeanPropertyAccess(fieldOnly);

        System.out.println("field-only: secret=" + fieldOnly.showSecret());
        System.out.println(
            "bean-secret-writable="
                + beanView.isWritableProperty("secret")
        );
        System.out.println(
            "bean-age-type=" + bean.getPropertyType("age").getSimpleName()
        );
    }
}
```

Design notes:

- `Person` has standard getters/setters. Setter `setName` calls `strip()` and increments `setterCalls`.
- `Address` is pre-initialized, so the nested path `address.city` is ready; the example does not rely on auto-creating nested objects.
- Both accessors share `DefaultConversionService` to convert `"21"` to `int 21`.
- `FieldOnly` has a `secret` field without `getSecret`/`setSecret`, so `BeanWrapper` does not consider `secret` a writable JavaBeans property.
- All nested classes are `public static` inside a single public class, so they compile cleanly in a file named `AccessorDemo.java`.

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Expected `stdout`:

```text
bean: name=[Lan] age=21 city=Ha Noi setterCalls=1
field: name=[  Lan  ] age=21 city=Da Nang setterCalls=0
field-only: secret=OK
bean-secret-writable=false
bean-age-type=int
```

The second line has **two leading spaces and two trailing spaces** inside `[...]`, showing that direct field access did not run `strip()`. `age=21` demonstrates conversion in both modes. When running Maven for the first time, dependency/plugin download messages (if any) appear outside these business stdout lines.

If you change the demo to `direct.setPropertyValue("age", "not-a-number")`, type conversion fails and throws a conversion/property-access exception. Do not expect a plain accessor to return a `BindingResult` holding field errors; that error aggregation belongs to `DataBinder`.

## 7. Reading, Writing, and Checking Types with the Common API

Common operations inherited from `PropertyAccessor`:

```java
accessor.isReadableProperty("name");
accessor.isWritableProperty("name");
accessor.getPropertyValue("name");
accessor.setPropertyValue("name", "Mai");
accessor.getPropertyType("name");
accessor.getPropertyTypeDescriptor("name");
```

This is a fragment with an `accessor` variable of type `ConfigurablePropertyAccessor`. Use `isReadableProperty`/`isWritableProperty` when handling dynamic field names, though they only tell you **the property is readable/writable through this accessor**, not that the user has business permission.

Example of defensive application code avoiding accidental calls to a nonexistent property:

```java
if (!accessor.isWritableProperty(propertyName)) {
    throw new IllegalArgumentException(
        "Cannot write property: " + propertyName
    );
}
accessor.setPropertyValue(propertyName, value);
```

The snippet above is **illustrative**, requiring `propertyName` and `value` to be defined; never pass arbitrary property name strings from HTTP clients straight into the accessor. If a whitelist is needed, check that `propertyName` belongs to a predefined set of paths; `isWritableProperty` alone does not establish a security boundary.

Bulk methods such as `setPropertyValues(...)` also exist on both accessor types. When dealing with data that may contain invalid properties, decide explicitly whether to ignore or fail on them, and catch appropriate exceptions per Spring's contract.

## 8. Nested, List, and Map Paths

Both modern `BeanWrapperImpl` and `DirectFieldAccessor` support nested paths, indexed collections, and Maps, provided the object graph is compatible and types are readable/writable.

| Path | Meaning |
| --- | --- |
| `address.city` | `city` field/property inside the `address` object |
| `items[0].name` | Name of the first element in a List/array |
| `tags[2]` | Third element of a List/array |
| `attributes[theme]` | Entry under key `"theme"` in a Map |
| `details[SKU-1].quantity` | Property of an object stored inside a Map |

A nested path like `address.city` is resolved **using the same strategy** across levels: the bean accessor uses getters/setters; the direct field accessor reads/writes fields. Section 6 uses `address.city` for both.

Distinguish "path syntax is supported" from "every graph is always updatable". If `address == null`, if a field is immutable, if the collection does not exist, or if elements have no way to be instantiated, the operation can fail.

### 8.1. `setAutoGrowNestedPaths` and Default Values

`ConfigurablePropertyAccessor` supports:

```java
accessor.setAutoGrowNestedPaths(true);
```

When enabled and conditions permit, the accessor can instantiate a default child object upon encountering `null` in a nested path. **For plain accessors created from `PropertyAccessorFactory`, the default is `false`**. Therefore, do not assume `address.city` will automatically work if `address` is null. Section 6 explicitly creates `new Address()` to avoid relying on auto-grow.

Collection growth limits and nested object auto-grow behavior can differ among `BeanWrapper`, `DirectFieldAccessor`, and `DataBinder`. Do not confuse the default of a plain property accessor with the default of `DataBinder`: `DataBinder` in bean property mode typically enables auto-grow nested paths, whereas this auto-grow is not supported identically in `DataBinder`'s direct field mode.

When receiving client data, do not enable auto-grow merely to make errors disappear. Enforce index/size limits and validate the data graph; an index like `items[999999]` can exhaust resources if processed without bounds.

### 8.2. Type Conversion and Generic Metadata

Both accessors can integrate:

```java
accessor.setConversionService(conversionService);
accessor.registerCustomEditor(TargetType.class, editor);
```

This is an **API illustration**, requiring concrete `conversionService`, `TargetType`, and `editor`. Use `ConversionService` for common conversions, and formatters/editors when needed. A string `"21"` can convert to `int`; custom types require appropriate converters/editors.

When traversing `List<Item>` or `Map<String, Item>`, generic metadata helps determine element or key/value types. Path and metadata support does not mean every element is auto-created or every input type is accepted; test against real DTOs.

## 9. Relationship with `DataBinder` and Spring MVC

`PropertyAccessorFactory` is a **lower-level** API than `DataBinder`. It creates an accessor to read/write values, while `DataBinder` coordinates an input-binding flow with field restrictions, conversion, errors, and validation.

By default, `DataBinder` uses **bean property access**. To have the binder access fields directly, use:

```java
DataBinder binder = new DataBinder(target, "form");
binder.initDirectFieldAccess();
binder.setAllowedFields("city", "postalCode");
binder.bind(new MutablePropertyValues(inputValues));
BindingResult result = binder.getBindingResult();
```

This fragment is **not standalone**: it requires `target`, `inputValues`, and imports:
`org.springframework.validation.DataBinder`,
`org.springframework.beans.MutablePropertyValues`,
`org.springframework.validation.BindingResult`.

Call `initDirectFieldAccess()` **before the binder begins accessing/writing data**. This API switches `DataBinder`'s mode; it is not the same as manually creating `PropertyAccessorFactory.forDirectFieldAccess(target)` and expecting a binder to use that separate accessor.

In Spring MVC, you can configure the binding mode for a model attribute in `@InitBinder`:

```java
@InitBinder("profileForm")
void setupBinder(WebDataBinder binder) {
    binder.initDirectFieldAccess();
    binder.setAllowedFields("displayName", "city");
}
```

This is an **integration snippet inside a controller**, requiring `WebDataBinder` and `@InitBinder`. Configuring direct access for HTTP data must be carefully evaluated because setter validation and value normalization are bypassed.

**Do not confuse with constructor binding:** Spring MVC can construct the target via a constructor before property binding runs. `forBeanPropertyAccess`/`forDirectFieldAccess` govern how **an existing instance** is read/written, not constructor selection or JSON deserialization in `@RequestBody`.

## 10. Common Errors, Exceptions, and Debugging

### 10.1. Field Exists Yet BeanWrapper Reports Not Writable

`FieldOnly.secret` exists without `setSecret`. `bean.isWritableProperty("secret")` is `false`; `bean.setPropertyValue("secret", "X")` can throw `NotWritablePropertyException`. If a class intentionally omits a setter, do not force direct field access in flows handling untrusted data. Consider constructor inputs or explicit update APIs.

### 10.2. Getter Exists Yet Direct Field Accessor Cannot Find the Field

A computed getter like `getFullName()` can expose property `fullName` to `BeanWrapper` even though the class only stores `firstName` and `lastName`. `DirectFieldAccessor` looks for a field named `fullName`; if none exists, reading/writing by that name has no target. Check whether the class design defines computed-only properties.

### 10.3. Setter Does Not Run

If data is no longer stripped, normalized, updating audit timestamps, or checking invariants, check whether binding used `initDirectFieldAccess()` or `forDirectFieldAccess(...)`. Watch a setter breakpoint: bean access invokes the setter normally, while direct field access does not.

### 10.4. Type Conversion Errors

`setPropertyValue("age", "abc")` for an `int` field cannot convert like `"21"`. On a plain accessor, the call normally throws an exception such as `TypeMismatchException` or a `BeansException`-related error. With `DataBinder`, binding errors can be recorded as `FieldError`s in `BindingResult` per the binding mechanism. Do not catch all exceptions and ignore them, or treat pre-error partial state as completely valid.

### 10.5. Nested Path Errors

`setPropertyValue("address.city", "Hue")` can raise `NullValueInNestedPathException` when `address` is null and auto-grow is off, or property access errors if the path is missing or non-writable. Create nested objects appropriately or enable controlled auto-grow in the right mode. Do not view auto-grow as a solution for non-instantiable abstract classes/interfaces.

### 10.6. Errors with `final` Fields, Records, or Java Modules

Direct field access is not a tool for mutating immutable objects. For record components, the constructor is the proper mechanism to establish values. Under JPMS, non-public access also depends on module openness. If you need to manipulate private fields across modules, revisit the public API design and module configuration rather than using reflection as a shortcut.

### 10.7. Confusing `PropertyAccessorFactory` with Spring BeanFactory

Having `Factory` in the name does not mean it manages singletons, scopes, or dependency injection. It simply returns an accessor wrapping the object you pass in. Do not use it to look up `@Component` beans from the container or initialize Spring beans defined in `@Configuration`.

## 11. Which Style Should You Choose in Application Design?

Prefer **bean property access** when:

- The class exposes valid getters/setters and you want to preserve normalization/checks in setters.
- JavaBeans introspection via `PropertyDescriptor` is needed.
- Data comes from form input or an untrusted source and the application explicitly designs which properties may be bound.
- You want the standard default behavior of `DataBinder`/Spring MVC.

**Direct field access** can be reasonable when:

- You have mutable objects in an internal mapping/import tool that lack setters.
- Working with legacy DTOs where field access is an intentional, tested design choice.
- Building an infrastructure-level field-manipulation adapter while understanding the impact of skipping setters.

Do not choose direct field access simply because a setter rejects invalid values. If the setter protects an object invariant, bypassing it usually makes the model less reliable.

A safe organization pattern for REST/web:

```text
HTTP input
    -> input DTO with a finite set of fields
    -> Bean Validation and business checks
    -> Service applies permitted changes
    -> Domain object via business methods
```

Restrict inputs via DTOs and `binder.setAllowedFields(...)` when using property binding. Do not rely on `private`, `isWritableProperty(...)`, or `@InitBinder` alone to replace authorization and validation in the service layer.

## 12. Pre-Implementation Checklist

1. Is the target a suitable mutable instance? Are getters/setters or actual writable fields present?
2. Is the goal to respect setter logic or manipulate raw fields?
3. Does the return type need to be `BeanWrapper` for JavaBeans `PropertyDescriptor`, or is `ConfigurablePropertyAccessor` sufficient?
4. Do `isReadableProperty`/`isWritableProperty` match the expected property names?
5. For nested paths, do intermediate objects already exist? Is auto-grow genuinely needed and configured in the right mode?
6. For non-String types, is a suitable `ConversionService` or editor configured?
7. Are there `final` fields, records, proxies, or module boundaries making direct field access unsuitable?
8. When using `DataBinder`, was `initDirectFieldAccess()` called before binding, and are allowed fields/validation configured?
9. For client-supplied input, are field paths, collection sizes, and edit permissions controlled, preventing sensitive state updates?
10. Are there tests verifying exact post-bind values and whether setters executed?

## 13. Self-Assessment Exercises

### Exercise 1 — Choosing an API by Need

Class `Invoice` has field `private BigDecimal amount` and setter `setAmount(...)` that rounds numbers according to policy. You want to preserve that rounding when updating the value. Which API should you choose?

**Answer:** `forBeanPropertyAccess(invoice)`, because writes will go through the setter. Still, critical monetary calculations should be organized in service/domain methods and tested independently; a DTO setter does not replace business checks.

### Exercise 2 — Distinguishing Computed Getters from Fields

A class stores `firstName` and `lastName` and has `getFullName()`, but has no `fullName` field and no `setFullName(...)` setter. For each accessor type, what is the accessibility of `fullName`?

**Answer:** `BeanWrapper` can read JavaBeans property `fullName` via the getter, but cannot write it without a setter. `DirectFieldAccessor` cannot access a nonexistent `fullName` field.

### Exercise 3 — Predicting Stdout

Given setter `setCode(String s) { this.code = s.toUpperCase(); }`, a bean accessor and a direct field accessor both receive `"ab"` on two identical instances. What is the result?

**Answer:** the bean accessor stores `"AB"`, while the direct field accessor stores `"ab"` if field `code` is mutable and reflection is allowed.

### Exercise 4 — Null Nested Path

An object has `private Address address;` initially null and you create a plain `BeanWrapper` via the factory. Is calling `setPropertyValue("address.city", "Hue")` guaranteed to succeed?

**Answer:** **No.** Plain accessors do not auto-grow nested paths by default. If `address` is null, instantiate a valid instance beforehand or enable `setAutoGrowNestedPaths(true)` with an instantiable child class; input complexity must still be controlled.

## 14. References

- Spring Framework Javadoc — [PropertyAccessorFactory](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/beans/PropertyAccessorFactory.html): the two factory methods and return types.
- Spring Framework Reference — [Property Binding with BeanWrapper](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): JavaBeans, nested/indexed paths, getters/setters, and property access.
- Spring Framework Javadoc — [DirectFieldAccessor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/DirectFieldAccessor.html): direct instance fields and nested/collection/map support.
- Spring Framework Javadoc — [ConfigurablePropertyAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/ConfigurablePropertyAccessor.html): `ConversionService`, property editors, `setAutoGrowNestedPaths`, and plain accessor defaults.
- Spring Framework Javadoc — [BeanWrapper](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapper.html): contract, introspection, and property descriptors.
- Spring Framework Javadoc — [DataBinder](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DataBinder.html): `initBeanPropertyAccess()`, `initDirectFieldAccess()`, and binding mechanism.
