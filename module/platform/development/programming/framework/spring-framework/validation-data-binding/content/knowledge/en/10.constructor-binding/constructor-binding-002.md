# Initializing DataBinder with a Null Target and Setting targetType for Constructor Binding

## 1. The Problem: Binding When the Target Object Does Not Exist Yet

In traditional property binding, the application already has an object, creates a `DataBinder` with that object, and then calls `bind(PropertyValues)` to assign data through properties. With **constructor binding**, the target object may **not exist yet**: input data is converted into constructor arguments so Spring can invoke the constructor and create the object.

Spring Framework 6.1+ supports the `DataBinder.construct(ValueResolver)` API along with `setTargetType(ResolvableType)` to accurately describe the target type when the binder is created with `target == null`. Exact API details can vary by version; verify that the project uses a suitable Spring Framework version (such as Spring Framework 6.1+), and do not copy this snippet into Spring 5.x expecting it to compile.

Core idea:

```text
No CustomerRequest instance yet
    |
    v
new DataBinder(null, "customerRequest")
    |
    v
binder.setTargetType(ResolvableType.forClass(CustomerRequest.class))
    |
    v
binder.construct(ValueResolver providing name -> value)
    |
    +--> Determine constructor/parameter names
    +--> Fetch data by parameter names
    +--> Convert values to parameter types
    +--> Invoke constructor to create object
    +--> Record binding errors if any
    |
    v
binder.getTarget() and binder.getBindingResult()
```

`setTargetType` specifies the **desired type**, rather than creating the object itself. It is `construct(...)` that begins the instance creation process. This differs from `bind(...)`, which binds property values onto an already existing object.

## 2. Two Binding Modes and the Target Lifecycle

| Aspect | Property binding | Constructor binding |
| --- | --- | --- |
| Initial target | Usually an already-created object | Can be `null` |
| Key configuration | Property access, allowed fields, conversion | `targetType`, constructor metadata, value resolver, conversion |
| Execution call | `bind(PropertyValues)` | `construct(DataBinder.ValueResolver)` |
| Where data is bound | Setters/fields of the existing instance | Constructor parameters creating a new instance |
| Suitable models | Mutable JavaBean/DTO | Immutable DTO, record, constructor-based DTO |
| Result | The object is mutated | A new object retrievable via `getTarget()` |
| Data errors | `BindingResult` | `BindingResult`/constructor error depending on the issue |

During a single request, Spring MVC may combine constructor binding when creating a model attribute and property binding afterward depending on the execution path and configuration. Therefore, **do not assume** `construct` and `bind` are mutually exclusive in all cases. For immutable DTOs, post-creation property binding typically has no setters to act on.

## 3. Why Does a Null Target Need targetType?

When calling `new DataBinder(null, "customer")`, the binder cannot infer the class from `target.getClass()` because there is no target yet. When constructor binding is needed, supply a `ResolvableType` so Spring knows what object type to create:

```java
import org.springframework.core.ResolvableType;
import org.springframework.validation.DataBinder;

DataBinder binder = new DataBinder(null, "customer");
binder.setTargetType(ResolvableType.forClass(CustomerRequest.class));
```

This snippet sits inside a method where the `CustomerRequest` class is already defined. `ResolvableType` can represent richer type information than a raw `Class`, such as generic type metadata when needed. When the target is already non-null, do not use `setTargetType` to "change the type" of an existing object; it serves the case where the binder must determine the target class for construction.

Set the target type **before** `construct()`. Lacking a target type with a null target leaves the binder without enough information to choose the appropriate constructor.

## 4. Defining a Target Suitable for Constructor Binding

A Java record is a straightforward choice because its data components correspond to the canonical constructor:

```java
public record CustomerRequest(String name, int age) {}
```

For regular classes, ensure Spring can locate the appropriate constructor and discover parameter names. Compile Java with the `-parameters` option when runtime parameter name metadata is needed (along with the corresponding build configuration). Example:

```java
public final class CustomerRequest {
    private final String name;
    private final int age;

    public CustomerRequest(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() { return name; }
    public int getAge() { return age; }
}
```

If parameter names at runtime become `arg0`, `arg1` due to missing metadata, the binder may fail to match inputs `name`, `age` as expected. With records, the canonical constructor and record components provide more reliable name information per framework support.

## 5. Complete Java 17+ Example Using `DataBinder.construct`

Create `ConstructorBindingDemo.java` in a project with Spring Framework **6.1+** and compatible dependencies:

```java
import java.util.Map;
import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class ConstructorBindingDemo {
    public record CustomerRequest(String name, int age) {}

    public static void main(String[] args) {
        Map<String, String> input = Map.of(
                "name", "An",
                "age", "21");

        DataBinder binder = new DataBinder(null, "customerRequest");
        binder.setTargetType(
                ResolvableType.forClass(CustomerRequest.class));

        binder.construct(new DataBinder.ValueResolver() {
            @Override
            public Object resolveValue(String name, Class<?> type) {
                return input.get(name);
            }
        });

        CustomerRequest target = (CustomerRequest) binder.getTarget();
        BindingResult result = binder.getBindingResult();

        System.out.println(target.name());
        System.out.println(target.age());
        System.out.println(result.hasErrors());
    }
}
```

Expected output (matching Spring Framework version, complete classpath):

```text
An
21
false
```

Flow explanation:

1. The binder starts with a `null` target.
2. `setTargetType` passes `CustomerRequest.class` to the binder.
3. `ValueResolver` receives the parameter name and type; for example, returning the input string for `name` or `age`.
4. `construct` finds the record's canonical constructor, uses Spring's conversion to convert `"21"` to `int`, and invokes the constructor.
5. After construction, `getTarget()` returns `CustomerRequest`; `getBindingResult()` reports any binding errors.

**Compatibility note:** depending on the minor version, `DataBinder.ValueResolver` adds name-support contracts such as `getNames()`, provided as a default method. When using `new DataBinder.ValueResolver()`, check against the actual interface in your dependency. If the compiler reports a missing abstract method, implement the exact contract of the version in use; do not infer APIs from another version.

With dependencies resolved by your build tool in `SPRING_CP`, you can compile/run on Linux/macOS:

```bash
javac -cp "$SPRING_CP" ConstructorBindingDemo.java
java -cp ".:$SPRING_CP" ConstructorBindingDemo
```

On Windows, use `;` as the classpath separator. This code will not compile with a plain JDK without the Spring JARs. Spring Boot applications typically manage the Spring Framework version via BOM/starters; do not mix individual Spring versions.

## 6. Passing Data Through `DataBinder.ValueResolver`

`ValueResolver` is the boundary between the **data source** and the **object creation mechanism**. Instead of requiring the data source to have a single fixed format, the binder asks the resolver for the value of each constructor parameter:

```java
Object resolveValue(String name, Class<?> type)
```

For example, when creating `CustomerRequest(String name, int age)`:

```text
resolveValue("name", String.class) -> "An"
resolveValue("age", int.class)     -> "21"
```

The resolver does not have to immediately return a value of the exact Java type of the parameter; Spring can perform conversion afterward. However, the returned value must be suitably convertible, and a converter must be registered if the target type is a custom domain type.

Resolvers typically obtain data from maps, request parameters, or other input sources. In Spring MVC, the framework provides a specialized web binder, and the corresponding factory/resolver prepares request data. When writing your own resolver, you are responsible for key lookup, multiple values, missing values, and untrusted data boundaries.

### Parameter Naming Issues

Not every constructor is safe to bind automatically. If constructor parameters have hard-to-resolve names or multiple overloads cause ambiguity, configure/model clearly and test. When input names need to differ from parameter names, Spring provides naming mechanisms where supported (such as annotations related to constructor binding); use the exact API for your version rather than guessing.

## 7. Conversion Errors and Missing Data

Suppose the input contains:

```text
name=An
age=abc
```

The record's `age` is `int`. Spring cannot convert `"abc"` to an integer, so object creation does not succeed normally. The binder may record a `FieldError` with code `typeMismatch`, but **do not assume** a valid record will always be created when a constructor argument fails conversion: the target may remain null or the process may end with an exception depending on the error kind and version.

For missing input names or values:

- A constructor with a primitive parameter like `int` cannot receive `null` the way a reference type can.
- A nullable `Integer` may allow `null` at the Java constructor level, but business logic still needs to validate required constraints.
- If the constructor itself throws `IllegalArgumentException`, that is an error from constructor logic, not automatically equivalent to a conversion `FieldError`.
- Do not call `binder.getTarget()` and cast or use it immediately when input data is invalid; check errors and safe target state first.

Constraints like age being at least 18 are **validation after data is available to check**, not the responsibility of constructor selection and type conversion. To check constraints via Jakarta Bean Validation or a Spring Validator, configure and trigger the proper flow.

## 8. Constructor Binding in Spring MVC

When Spring MVC handles a `@ModelAttribute`, the framework can use constructor binding to create the object from request values before continuing with the remaining steps.

```java
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerController {
    public record CustomerRequest(String name, int age) {}

    @PostMapping("/customers")
    public String create(
            @Validated @ModelAttribute CustomerRequest form,
            BindingResult result) {
        if (result.hasErrors()) {
            return "Invalid customer";
        }
        return form.name() + ": " + form.age();
    }
}
```

This is a **controller snippet**, not a complete Spring MVC application with `main`. When a request sends `name=An&age=21` and the MVC configuration supports appropriate constructor binding, the record object can be created with converted values. `BindingResult` must appear immediately after the model parameter. `@Validated` requests validation through the configured validator; without constraints, it does not impose `age >= 18` on its own.

### Distinguishing `@ModelAttribute` from `@RequestBody`

`@ModelAttribute` typically binds request parameters to an object and can participate in constructor/property binding. `@RequestBody` JSON is typically deserialized by an `HttpMessageConverter` (such as Jackson); even though Jackson can also use constructors/records, that is **a different object creation mechanism**. Do not equate all JSON deserialization with `DataBinder.construct(ValueResolver)`.

### Scope and Security

Constructor binding restricts data passed into the DTO's constructor parameters (often useful for immutable request objects), but **does not mean automatic immunity to mass assignment**. If the model has a sensitive constructor parameter like `admin`, a client may attempt to supply that name. Include only fields permitted from clients in the DTO constructor; perform authorization checks separately and avoid binding security/domain entities directly.

## 9. How `targetType`, `ConversionService`, and `BindingResult` Work Together

| Component | Role in constructor binding |
| --- | --- |
| `ResolvableType targetType` | Identifies the object type Spring needs to create when no target exists yet |
| `ValueResolver` | Fetches input values by constructor parameter name and type |
| `ConversionService` | Converts source values to constructor parameter types |
| `DataBinder.construct(...)` | Selects/invokes the constructor and creates the object |
| `DataBinder.getTarget()` | Retrieves the object after successful creation |
| `BindingResult` | Queries binding errors; not a copy of the object |

When using custom data types such as `Money`, `ProductCode`, or enums with non-standard formats, you can configure a conversion service on the binder before `construct`. Converters are only responsible for type conversion and do not replace business validation.

Conversion configuration example (snippet inside a method):

```java
import org.springframework.core.convert.support.DefaultConversionService;

var conversionService = new DefaultConversionService();
binder.setConversionService(conversionService);
binder.construct(valueResolver);
```

`binder` and `valueResolver` in this snippet must be created beforehand; this is an **illustrative snippet**, not a standalone file. For common types like `String` to integer, the binder infrastructure typically has a suitable default conversion path.

## 10. Common Implementation Mistakes

- **Forgetting `setTargetType` with a null-target binder:** Spring does not know which type's constructor to use.
- **Calling `bind(PropertyValues)` before creating the target:** property binding cannot assign onto a nonexistent object; constructor binding is needed when starting from null.
- **Assuming `setTargetType` instantiates the object itself:** it only stores type metadata.
- **Missing constructor parameter names:** the resolver cannot map expected input keys; for regular classes, check `-parameters`.
- **Using an immutable model while expecting setters:** records do not have setters for the property binder to update after construction.
- **Mixing APIs across Spring 5/6 or minor versions:** check `DataBinder.construct` and `ValueResolver` in your actual dependency.
- **Assuming every conversion failure still yields a valid target:** read `BindingResult` and handle cases where the target was not created.
- **Using `@Validated` and expecting constraints to be generated automatically:** actual validation rules are required.
- **Binding directly to objects containing sensitive parameters:** constructor binding still requires DTOs, input constraints, and authorization.

## 11. Pre-Use Checklist

1. Does the Spring version in use support the constructor binding APIs you intend to call?
2. Does the target object have clear constructor/record component names matching the input names?
3. Was the binder created with a null target and `setTargetType` called before `construct`?
4. Does `ValueResolver` return accurate values and handle missing/multiple values reasonably?
5. Can the conversion service convert all required parameters?
6. On error, does the application check `BindingResult` and the target before using them?
7. Are validation, data boundaries, and client modification permissions designed separately?

**Conclusion:** To bind data via a constructor when no object exists yet, create `DataBinder` with a null target, declare `targetType` using `ResolvableType`, provide a `ValueResolver`, and call `construct`. Unlike `bind` on a mutable JavaBean, this flow creates the object before it can be read via `getTarget()`, making it well suited for records and immutable DTOs while requiring careful management of parameter names, type conversion, errors, and security.