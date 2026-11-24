# DataBinder Constructor Binding Since Spring Framework 6.1

## 1. The Problem Constructor Binding Solves

When Spring receives external data, such as registration form parameters, it needs to create a Java object. With familiar property binding, the application creates a JavaBean up front and Spring calls the corresponding setters. Starting with **Spring Framework 6.1**, `org.springframework.validation.DataBinder` also supports **constructor binding**: reading input values by constructor parameter name, converting types when needed, and **invoking the constructor to create the target**.

Example data:

```text
name = Mai
age  = 21
```

and an immutable type:

```java
public record Registration(String name, int age) {}
```

There are no setters for `name` and `age`. Constructor binding can still create `Registration[name=Mai, age=21]` by converting the string `"21"` to `int` and invoking the record's canonical constructor.

Both binding approaches share the goal of populating an object with data, but differ in when the object is created and which data surface can be written:

| Aspect | Constructor binding (Spring 6.1+) | Property/setter binding |
| --- | --- | --- |
| Initial object | Usually `null`; the binder knows `targetType` in advance | Usually already has an instance |
| How data is populated | Invokes constructor with resolved parameters | Invokes setters or updates fields per configuration |
| Suitable models | Records, immutable DTOs, objects with explicit constructors | JavaBeans with setters, models needing updates to many properties |
| Notable APIs | `setTargetType(...)`, `construct(ValueResolver)` | `bind(PropertyValues)` |
| Property surface accepted | Constructor parameters and nested objects to construct | Writable properties per binder configuration |
| Type conversion/errors | Through the conversion system, reporting binding errors | Through the conversion system, reporting binding errors |
| Validation | Still a separate step to trigger and check | Still a separate step to trigger and check |

**Key point:** constructor binding is **not** Spring IoC's `@Autowired` constructor injection. Both use constructors, but one takes values from **data to be bound**, while the other supplies **bean dependencies**. Nor does constructor binding automatically invoke `jakarta.validation.Validator`: object creation and constraint checking are two separate concerns.

## 2. Three Required Steps of DataBinder.construct

To use the `DataBinder` API directly, the basic sequence according to the Spring 6.1 documentation is:

```java
DataBinder binder = new DataBinder(null, "registration");
binder.setTargetType(ResolvableType.forClass(Registration.class));
binder.construct(valueResolver);
```

Where:

1. **Create a binder with a `null` target**: `new DataBinder(null, "registration")` signals that no instance exists yet. `"registration"` is the object name used for error reporting, not a class name.
2. **Specify the object type to create**: `setTargetType(ResolvableType.forClass(Registration.class))`. `ResolvableType` belongs to `org.springframework.core` and also supports describing generic types when needed.
3. **Provide a way to resolve values and call `construct(...)`**: `DataBinder.ValueResolver` maps constructor parameter names to input values. Spring selects the appropriate constructor, converts types, and constructs the target.

After construction:

```java
Object target = binder.getTarget();
BindingResult errors = binder.getBindingResult();
```

The lines above only illustrate reading the result; they live inside a method that already has `binder`. The application must check `errors.hasErrors()` before treating the target as valid data for use. When construction succeeds, `getTarget()` returns the new instance. When binding/constructor execution encounters errors, handle them according to `BindingResult` and the actual exception rather than assuming a usable object always exists.

### Why Not Start with new Registration(...)

If you already called `new Registration("Mai", 21)` yourself, there is no longer a need for the binder to construct the object from input. With constructor binding, you delegate parameter resolution and type conversion from untyped input data to the binder. The constructor serves as an **input contract**; this process is especially useful in Spring MVC's `@ModelAttribute` mechanism or form/query data.

## 3. What Does DataBinder.ValueResolver Receive and Return?

`DataBinder.ValueResolver` is the interface for the input data lookup strategy. Its primary method has the signature:

```java
Object resolveValue(String name, Class<?> type);
```

- `name`: the parameter name Spring wants to retrieve. It can be a simple name like `age` or a nested path like `address.city`.
- `type`: the Java type of the constructor parameter Spring is trying to bind, such as `String.class` or `int.class`.
- Return value: the source value, typically a `String`, `String[]`, or compatible object; may be `null` if the input does not provide it.
- If the returned value does not yet match the target type, Spring uses the configured type conversion support to convert it before calling the constructor.

From **Spring 6.1.2 onwards**, the interface also has a `getNames()` method returning a `Set<String>` of available value names. It helps handle scenarios such as nested objects, collections, or indexed keys. The example below **implements both `resolveValue` and `getNames`** for compatibility with Spring 6.1.14 used in this guide.

A resolver backed by a map can be written as:

```java
final class MapValueResolver implements DataBinder.ValueResolver {
    private final Map<String, String> values;

    MapValueResolver(Map<String, String> values) {
        this.values = values;
    }

    @Override
    public Object resolveValue(String name, Class<?> type) {
        return values.get(name);
    }

    @Override
    public Set<String> getNames() {
        return values.keySet();
    }
}
```

This snippet illustrates a class that needs to import `java.util.Map`, `java.util.Set`, and `DataBinder`; the complete runnable program with all imports is in section 5. `resolveValue` **does not need to parse `int` itself** if you choose to let Spring perform the conversion. When input has multiple values or special source formats, the resolver must decide the format and value selection accordingly; Spring will not magically understand arbitrary strings.

### How Does NameResolver Differ from ValueResolver?

- `ValueResolver` decides **where to look up a value and what value to return** for a given name.
- `DataBinder.NameResolver` decides **which name to use** when looking up a constructor parameter's value.

By default, Spring uses constructor parameter names, obtained from appropriate class metadata. You can configure `setNameResolver(...)` to change the naming convention. In Spring MVC/WebFlux, the `@BindParam` annotation can specify an external data parameter name that differs from the Java parameter name. `@BindParam` belongs to the web layer; a standalone `DataBinder` will not automatically apply every MVC annotation convention unless the corresponding `NameResolver` is configured.

Example of name mapping in the Spring MVC layer:

```java
import org.springframework.web.bind.annotation.BindParam;

public record ContactForm(
    @BindParam("full_name") String name,
    String email
) {}
```

This is an illustrative snippet in a Spring Web application; `full_name` is the external key, while `name` is the property name in the record. There is no need to rename Java properties to match every HTML field name. Similarly, you can write a custom `NameResolver` when using `DataBinder` directly.

## 4. How Does Spring Select a Constructor?

Constructor binding relies on a **constructor used for data construction**, rather than automatically calling just any constructor it can find. According to the Spring Framework 6.1 documentation:

- The type should have **one clear data constructor**, either public or suitable for Spring's primary constructor resolution.
- Java records have a canonical constructor tied to record components; `record Registration(String name, int age)` is a natural example.
- Having discoverable constructor parameter names is essential. For regular Java classes, compile with `-parameters` or use `@ConstructorProperties` when appropriate.
- If there are multiple constructors including a no-arg constructor, Spring may pick the default constructor and lean toward property binding; do not leave constructor selection to guesswork in a model with multiple choices.
- With multiple public constructors or a class lacking a clear construction path, check the constructor selection strategy of your Spring version instead of assuming Spring will guess right.

Example class using `@ConstructorProperties`:

```java
import java.beans.ConstructorProperties;

public final class CustomerForm {
    private final String customerCode;
    private final int quantity;

    @ConstructorProperties({"customerCode", "quantity"})
    public CustomerForm(String customerCode, int quantity) {
        this.customerCode = customerCode;
        this.quantity = quantity;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

This is a standalone class example showing how to declare constructor argument names. `@ConstructorProperties` does not perform binding itself; it supplies name metadata to the framework. Keep the declared names aligned with the meaning of each parameter. For Java 17 records, Spring supports resolving canonical constructor/record component names; compiling with `-parameters` remains good practice when working with regular Java classes.

## 5. Runnable Java 17 Program

This program uses **Spring Framework 6.1.14** and Java 17, without needing Spring Boot, a servlet container, controllers, or JSON. We pass the binder a map containing two strings `"Mai"` and `"21"`; after `construct`, the new record has `name` of type `String` and `age` of type `int`.

Directory structure:

```text
constructor-binding-demo/
├── pom.xml
└── src/main/java/demo/ConstructorBindingDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>constructor-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Contents of `src/main/java/demo/ConstructorBindingDemo.java`:

```java
package demo;

import java.util.Map;
import java.util.Set;
import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class ConstructorBindingDemo {

    // No setters: Spring must use the record's constructor.
    public record Registration(String name, int age) {}

    public static final class MapValueResolver
            implements DataBinder.ValueResolver {

        private final Map<String, String> values;

        public MapValueResolver(Map<String, String> values) {
            this.values = values;
        }

        @Override
        public Object resolveValue(String name, Class<?> type) {
            return values.get(name);
        }

        @Override
        public Set<String> getNames() {
            return values.keySet();
        }
    }

    public static void main(String[] args) {
        Map<String, String> input = Map.of(
            "name", "Mai",
            "age", "21"
        );

        // Initially there is no Registration instance.
        DataBinder binder = new DataBinder(null, "registration");

        // Spring 6.1+: declare the type to be created.
        binder.setTargetType(
            ResolvableType.forClass(Registration.class)
        );

        // Read values by name and invoke the constructor.
        binder.construct(new MapValueResolver(input));

        BindingResult errors = binder.getBindingResult();
        if (errors.hasErrors()) {
            throw new IllegalStateException(
                "Constructor binding errors: " + errors
            );
        }

        Registration registration =
            (Registration) binder.getTarget();

        System.out.println(registration);
        System.out.println("errors=" + errors.getErrorCount());
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConstructorBindingDemo
```

**Two lines printed by the program** for valid input (excluding Maven or framework logs):

```text
Registration[name=Mai, age=21]
errors=0
```

Why:

1. `binder.getTarget()` is initially `null`.
2. `setTargetType(...)` tells Spring to create `Registration`.
3. Spring reads the record's component names `name` and `age`, querying `MapValueResolver` for the corresponding data.
4. The resolver returns `"Mai"` and `"21"`.
5. Conversion from `String "21"` to `int 21` is performed by Spring based on the constructor parameter type.
6. The canonical constructor effectively creates `new Registration("Mai", 21)`; the binder stores this target.
7. There are no binding errors, so `BindingResult.getErrorCount()` is `0`. Because records provide a `toString()` formatted with the type name and components, the first line displays as shown above.

This code **does not automatically enable Jakarta Bean Validation** and does not check whether `name` is blank or `age` is high enough. It demonstrates **object creation and type conversion**. Validation is an additional step covered later.

## 6. Nested Constructor Binding and Name Paths

Constructor binding is not limited to simple parameters. Spring 6.1 supports **constructing nested objects** via constructors, from inputs with paths such as `address.city`.

Suppose the model is:

```java
public record Address(String city) {}

public record Registration(
    String name,
    int age,
    Address address
) {}
```

External data may carry the keys:

```text
name = Mai
age = 21
address.city = Ha Noi
```

While Spring is constructing `Registration`, it recognizes that the `address` parameter has an object type that also needs construction. It can invoke `Address`'s constructor, look up data with the nested name `address.city`, and pass `Address("Ha Noi")` into `Registration`'s constructor. This is a **mechanism description**, not a replacement for the runnable code in section 5.

With a custom `ValueResolver`, you must support the **full names** that Spring requests. For example, a map-based resolver can directly look up `values.get("address.city")`. In Spring 6.1.2+, `getNames()` helps the framework know which deeply nested names are provided. If the resolver does not list the input keys properly, nested branches or collections may fail to initialize as expected.

### Collections and Maps

Spring can also construct `List`, `Map`, or array parameters from appropriately structured input values. Example names:

```text
items[0].sku = A01
items[1].sku = B02
attributes[COLOR] = blue
```

This represents input keys, not Java code. When using complex data types, consider type parameters (`List<Item>`), how Spring decodes indices/keys, conversion, and element count limits. Do not allow unbounded object graph growth controlled by external input. A simple flat-map `ValueResolver` is a starting point, whereas real-world web applications typically use resolvers provided by Spring MVC/WebFlux.

## 7. Binding Errors When Constructor Arguments Are Invalid

Constructor binding performs **type conversion**, so **data binding errors** can occur before reaching business constraint checks. Consider the input:

```text
name = Mai
age = abc
```

`"abc"` cannot be converted to `int` under default conversion. Spring records an appropriate error in `BindingResult` (typically a field error with root error code `typeMismatch`). An application should inspect:

```java
BindingResult result = binder.getBindingResult();

if (result.hasFieldErrors()) {
    result.getFieldErrors().forEach(error ->
        System.out.println(error.getField()
                + " -> " + error.getCode()));
}
```

This snippet goes after `construct(...)` in a program that has already configured the binder. Do not assume the constructor is always called successfully when conversion fails; target creation depends on constructor structure and how Spring handles errors. Check the result before using `getTarget()`. A constructor that throws its own exception for internal rules can also result in a `BeanInstantiationException` or corresponding exception, unlike simple conversion errors represented in `BindingResult`.

### Binding Is Not Validation

Two different error examples:

- `age = "abc"`: a **binding/conversion** error because a valid `int` value could not be produced.
- `age = "16"`: conversion to `int 16` succeeds, but it may **fail a business rule** such as minimum age 18. `DataBinder.construct(...)` does not enforce a minimum age rule on its own.

If you want validation after constructing the object, register an appropriate validator and invoke validation via the Spring API:

```java
// Once the binder has a valid target:
binder.addValidators(registrationValidator);
binder.validate();

BindingResult errors = binder.getBindingResult();
if (errors.hasErrors()) {
    // Report errors, do not pass the object into business logic.
}
```

This is an illustrative snippet with an application-defined `registrationValidator` supporting the target type. With Jakarta Validation, you can use the `LocalValidatorFactoryBean` adapter and a compatible provider in a Spring context. `construct` itself is only one part of the overall data processing flow.

### Missing Values and Null

If the resolver does not find `age`, it may return `null`. The outcome depends on the parameter type (primitive `int` vs `Integer`), conversion/instantiation strategy, and configured validation rules. Therefore, do not assume "missing data will immediately produce a `required` error" in every constructor. Use appropriate types, constraints like `@NotNull` when a validation provider is present, and required checks at the proper entry point. To distinguish *missing input* from *unconvertible input*, design the responsibilities of the resolver and validation explicitly rather than relying on a default primitive value.

## 8. Comparing construct(...) and bind(...)

Two common APIs on `DataBinder`:

```java
binder.construct(valueResolver);
binder.bind(propertyValues);
```

Meaning:

- `construct(ValueResolver)` creates the target via a constructor, suited for when the target does not yet exist.
- `bind(PropertyValues)` updates **writable properties** of an existing target according to property binding rules. `PropertyValues` is an object holding property name/value pairs; `MutablePropertyValues` is a common implementation.
- Constructor binding and property binding can be combined when a model genuinely needs both, but you must carefully consider which fields are allowed to accept values from clients.

Example model with both a constructor and a setter:

```java
public final class TicketForm {
    private final String ticketCode;
    private String comment;

    public TicketForm(String ticketCode) {
        this.ticketCode = ticketCode;
    }

    public String getTicketCode() {
        return ticketCode;
    }

    public String getComment() {
        return comment;
    }

    public void setComment(String comment) {
        this.comment = comment;
    }
}
```

This is a model design snippet; once the binder has created `TicketForm`, property binding can update `comment` if configuration allows. For **records without setters**, `bind(...)` is not a way to update record components already assigned by the constructor.

Do not use unrestricted property binding on domain entities with sensitive properties (for example `role`, `isAdmin`, `balance`). Users could submit fields beyond the expected form to try modifying internal values. Constructor binding encourages designing models that accept only intended inputs, but **does not automatically protect** if the DTO constructor itself exposes sensitive parameters.

## 9. Protecting Data: declarativeBinding Since Spring 6.1

Spring Framework 6.1 provides the setting:

```java
binder.setDeclarativeBinding(true);
```

The goal is to restrict the binder to fields that are explicitly allowed:

- **Constructor binding** via `construct(...)` remains supported.
- **Property binding** only runs for allowed fields when `setAllowedFields(...)` is configured appropriately.
- If declarative binding is enabled **without** setting allowed fields, Spring does not automatically bind every setter on the object just because the request contains a matching key.

Conceptual example:

```java
binder.setDeclarativeBinding(true);
binder.setAllowedFields("comment");
```

This snippet sits inside binder configuration for a model with a `comment` property, not as a standalone program. It allows drawing an explicit boundary: the constructor receives required parameters, while setters are only updated for allowlisted fields. When using only constructor binding, you can enable declarative mode and add no allowed fields for property binding.

**Do not misunderstand:** `setAllowedFields(...)` is a **property binding** configuration, not a switch to make Spring ignore a constructor parameter already present in the constructor chosen by the application. If a DTO constructor accepts a `role` parameter from the request, the constructor signature itself exposes the ability to receive that value. To stay safe, design DTO constructors with only the data clients are permitted to supply, and determine the actual role in the business/authorization layer.

Supporting practices:

1. Use dedicated input DTOs, separate from entities holding internal state.
2. Keep constructors accepting only fields users are permitted to supply.
3. Enable declarative binding or allowlist property fields when setter binding is needed.
4. Authenticate/authorize in the business layer rather than relying on constructor binding as an authorization mechanism.
5. Enforce sensible limits on size, depth, and collection/index counts when accepting untrusted input.

## 10. In Spring MVC and WebFlux

### @ModelAttribute

In Spring MVC/WebFlux starting in 6.1, model attribute binding can create objects via constructors instead of requiring an existing JavaBean. Example:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

record SearchForm(String keyword, int page) {}

@RestController
class SearchController {

    @GetMapping("/search")
    String search(@ModelAttribute SearchForm form) {
        return "keyword=" + form.keyword() + ", page=" + form.page();
    }
}
```

This is an **illustrative snippet in a Spring Web MVC application** with full web configuration. It does not belong to the Java SE program in section 5. With a `GET /search?keyword=java&page=2` request, a model attribute can be created via `SearchForm`'s constructor and the `page` value converted to `int`. No setters are needed for the record. If you need to inspect binding errors in the controller, you can declare `BindingResult` immediately after `@ModelAttribute`; do not expect all conversion errors to arrive in the exact same form when parameters are missing.

When using `@BindParam` in Spring MVC/WebFlux, the framework can override input name mapping for a constructor argument. For example, `full_name` in the form maps to the DTO's `name` parameter. When using `DataBinder` standalone without the web framework, you must configure an appropriate resolver/name strategy if input names differ from constructor parameter names.

### Does @RequestBody Use the Same Mechanism?

Do not equate `@ModelAttribute` form/query binding with `@RequestBody` JSON deserialization:

- `@ModelAttribute` primarily goes through the `WebDataBinder`/model-attribute binding system, which supports the constructor binding described here.
- `@RequestBody` reads the payload using an `HttpMessageConverter`, such as Jackson JSON, to create the object. Jackson can also instantiate records via constructors, but that is **Jackson's deserialization mechanism**, not evidence that `DataBinder.construct(...)` was invoked for that JSON.
- After either path creates the object, Spring can trigger validation via `@Valid`/`@Validated` when properly configured.

Keeping the data paths distinct helps accurately explain conversion errors, validation, error codes, and when the target is created.

### Should @Autowired Be Used on DTO Constructors?

No. `@Autowired` is Spring IoC container's dependency injection mechanism for beans, whereas model-attribute constructor binding reads **request/form parameters** to create a data object. Do not add `@Autowired` to a DTO constructor expecting it to automatically pull HTTP data.

## 11. Version Compatibility and Points to Check

Constructor binding via `DataBinder.setTargetType(...)` and `DataBinder.construct(ValueResolver)` is an API introduced in **Spring Framework 6.1**. Keep in mind:

- Verify Spring Framework is on the 6.1+ branch; the Java SE program here uses `spring-context:6.1.14`.
- With Spring 6.x, the minimum JDK is typically Java 17; the example uses Java records and Java 17 compiler configuration.
- Verify constructor parameter names are readable by Spring: records, `-parameters`, or `@ConstructorProperties` where appropriate.
- In Spring Boot, use the Spring Framework version managed by the Boot BOM instead of pinning `spring-context` out of sync with other Spring modules.
- Handling of complex types and resolver support APIs can evolve across minor/patch releases. For example, `ValueResolver.getNames()` was added after 6.1.0, so when copying examples from various sources, check against the Javadoc of your actual version.
- Do not guess which constructor will be chosen in classes with multiple constructors; avoid ambiguous designs.
- If using nested constructor binding/collections, verify the exact input key structure and generic types rather than forcing complex types into strings without a converter.

## 12. Common Mistakes

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Calling `construct` when the binder already has a target | Constructor binding expects the target not to exist yet | Start with `new DataBinder(null, ...)` |
| Not calling `setTargetType(...)` | The binder does not know what type to create | Use `ResolvableType.forClass(...)` before `construct` |
| Constructor argument receives null despite input having a value | Constructor parameter name cannot be resolved or resolver uses wrong key | Check `-parameters`, record metadata, `@ConstructorProperties`, `NameResolver` |
| Age string fails to convert to int | No suitable converter/editor or value cannot be parsed | Check `BindingResult` and conversion configuration |
| Wrongly picking no-args constructor | Class has multiple constructors/ambiguous construction path | Design a clear data constructor; check selection rules |
| Nested data is absent | Wrong `address.city` key or resolver does not list needed names | Check `resolveValue`, `getNames`, and nested paths |
| Using `bind(...)` to create a record from null | `bind` is property binding, not the constructor target creation API | Use `setTargetType` and `construct` |
| Ignoring errors because getTarget is non-null | The object may have been constructed in a state that fails constraints | Check binding errors and validation before using |
| Assuming constructor binding automatically checks `@NotBlank` | Binding and Bean Validation are two separate steps | Configure a validator/provider and trigger validation |
| Thinking `@RequestBody` always calls DataBinder.construct | JSON bodies typically go through Jackson/HttpMessageConverter | Distinguish model attributes from request bodies |
| Using only field allowlists to restrict constructor arguments | `setAllowedFields` controls property binding, not the constructor contract | Design DTO constructors with only permitted inputs |
| Putting @Autowired on a form constructor | Confusing IoC dependency injection with request data binding | Remove `@Autowired` from request DTOs |

## 13. Self-Check Questions

1. Why must `DataBinder(null, "form")` be paired with `setTargetType(...)` before `construct(...)`?
2. How does `DataBinder.ValueResolver.resolveValue(name, type)` differ in responsibility from `DataBinder.NameResolver`?
3. Why is the record `Registration(String name, int age)` well suited for constructor binding?
4. At which step is input `"21"` converted to `int`? If `"abc"` is entered, where should the result be checked?
5. Why does calling `construct(...)` not mean `@NotBlank` or `@Min` has been applied?
6. Which two data paths do an `@ModelAttribute` record and an `@RequestBody` JSON record take?
7. How does `setDeclarativeBinding(true)` affect property binding and constructor binding?
8. Why can a DTO constructor accepting `isAdmin` from user input pose a risk even when using constructor binding?
9. When a nested object receives input `address.city`, what must the resolver ensure regarding name paths?
10. If an object has multiple constructors, why should you verify which constructor Spring selects?

**Takeaway:** Starting in Spring Framework 6.1+, `DataBinder` can **create a new object via a constructor**. The foundational sequence is **`null` target → `setTargetType(...)` → `construct(ValueResolver)` → check `BindingResult` → run validation if needed**. This mechanism fits immutable DTOs and helps narrow the input data surface when constructors are carefully designed.

## References

- Spring Framework 6.1 — Data Binding, Constructor Binding: https://docs.spring.io/spring-framework/reference/6.1/core/validation/beans-beans.html
- Spring Framework 6.1 — DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.1 — DataBinder.ValueResolver Javadoc: https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html
- Spring Framework 6.1 Release Notes: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes
- Spring Framework — Model Design for web data binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
