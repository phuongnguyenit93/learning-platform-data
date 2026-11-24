# DataBinder.ValueResolver and Parameter Value Lookup in Constructor Binding

## 1. The Role of ValueResolver in Spring Data Binding

`DataBinder.ValueResolver` is an interface nested inside `org.springframework.validation.DataBinder`, serving as the **strategy for retrieving input values for each constructor parameter** when Spring creates an object via constructor binding. It separates two responsibilities:

- **Data lookup:** finding the value corresponding to a parameter name from a data source, such as request parameters or a `Map`.
- **Object construction and type conversion:** `DataBinder` selects the constructor, determines parameter names/types, asks the resolver for data, performs type conversion, constructs nested objects when appropriate, and then invokes the constructor.

Example Java DTO to create:

```java
public record Registration(String name, Integer age) {}
```

Form data might be:

```text
name=Lan&age=24
```

Spring looks up values for constructor parameters `name` and `age`, receives the two strings `"Lan"` and `"24"`, converts `"24"` to `Integer 24`, and then instantiates `new Registration("Lan", 24)`. `ValueResolver` performs the **lookup step**, not automatically calling constructors or replacing the entire type conversion mechanism.

Basic flow:

```text
Constructor parameter name + type
                 |
                 v
   DataBinder.NameResolver (if configured)
          determines lookup name
                 |
                 v
ValueResolver.resolveValue(name, type)
                 |
         raw value or null
                 |
                 v
   DataBinder converts type if needed
                 |
                 v
    Constructor(normalized values)
                 |
                 v
         New Java object
                 |
                 v
     BindingResult if errors occur
```

This is **constructor binding in Spring Framework 6.1+**, not `@Component`/`@Service` constructor dependency injection. `ValueResolver` supplies input data for a *request/model object*; Spring IoC constructor injection resolves **bean dependencies** from the container by type/qualifier and a different mechanism.

## 2. Exact API Contract

In Spring Framework 6.2.x, the interface has two methods:

```java
package org.springframework.validation;

public class DataBinder {
    public interface ValueResolver {
        Object resolveValue(String name, Class<?> type);
        java.util.Set<String> getNames();
    }
}
```

**This is a condensed API signature for learning**, not the full source of `DataBinder`; the actual Javadoc includes nullable annotations and many other members. Meaning:

| Method | Input | Output | Responsibility |
| --- | --- | --- | --- |
| `resolveValue(String name, Class<?> type)` | Lookup name and Java type of the constructor parameter | An `Object` or `null` | Retrieve the value for a specific key |
| `getNames()` | No parameters | `Set<String>` | List all value names managed by the resolver, especially for detecting nested data |

**`resolveValue(...)`:**

- `name` is usually the constructor parameter name, such as `"name"` or `"age"`; for nested parameters it can be a path like `"address.city"`.
- `type` indicates the target type of the parameter, such as `String.class`, `Integer.class`, or `Address.class`. The resolver **may** use this type to choose the form of data returned (especially for multi-value or multipart requests), but does not have to cast every value itself.
- Returns `null` when no suitable value is found. Spring can then inspect nested fields, collection/map/indexed input, or missing-value handling depending on the parameter.

**`getNames()`:**

- Returns a set of key names, such as `Set.of("name", "age", "address.city")`.
- Spring uses this key set to check whether data exists *beneath* a complex parameter. Even if the key `"address"` is absent, it may still need to create an `address` object if `"address.city"` is present.
- The interface does not require a stable iteration order; the names are lookup data. Do not rely on `Set` iteration order to predict constructor call order or output formatting.
- Return a complete, accurate list consistent with `resolveValue`. Returning an empty set arbitrarily can cause the binder to skip nested data.

**Version differences:** `ValueResolver` was introduced in Spring Framework 6.1; `getNames()` was added in **6.1.2**. In older examples based on 6.1.0, the interface could be written as a lambda because it had only one abstract method. With **6.2.x**, you must implement **both `resolveValue` and `getNames`**, as it is no longer a functional interface under the two-method contract.

## 3. Where Does Parameter Lookup Fit in the Construct Process?

When using core `DataBinder` directly, the typical sequence of steps is:

1. Create `new DataBinder(null, "registration")`: the target does not exist yet. `"registration"` is the object name used in error reporting.
2. Call `binder.setTargetType(ResolvableType.forClass(Registration.class))` to declare the type to construct; this requires the target to currently be `null`.
3. Prepare a `ValueResolver` that knows how to read the input.
4. Call `binder.construct(resolver)`; Spring determines the constructor, each parameter name, and reads values through the resolver.
5. `DataBinder` converts raw values to target types using appropriate conversion/editors.
6. If data for nested objects is present, Spring can recursively construct child objects.
7. Check `binder.getBindingResult()` for type conversion/binding errors; use `binder.getTarget()` to obtain the object after successful construction.

```text
new DataBinder(null, "registration")
          |
setTargetType(Registration.class)
          |
construct(ValueResolver)
          |
    [name / String] -> "Lan"
    [age / Integer] -> "24" -> 24
          |
new Registration("Lan", 24)
          |
getBindingResult() -> check for errors
getTarget() -> instance if created successfully
```

`construct(...)` requires that **the target has no instance yet** and `targetType` has been set. Creating a `DataBinder` with an existing object and calling `construct(...)` violates the API precondition: property binding on an existing object uses `bind(PropertyValues)`.

Spring can select a public data constructor or an appropriate constructor according to framework rules. For a Java class with multiple constructors, the presence of a default/no-arg constructor affects selection. To keep examples predictable, prefer a `record` or a DTO with one clear constructor. When using regular classes, the build must preserve parameter names (e.g., javac `-parameters`), or use framework-supported metadata/annotations. Java records also provide record component names for their canonical constructor.

## 4. Runnable Java 17+ Example: MapValueResolver for a Nested Record

This example uses **Spring Framework 6.2.x**, **Java 17+**, and Maven; it does not need a Spring Boot application, Servlet container, HTTP server, or Jakarta Bean Validation. We simulate request input with a `Map<String, Object>`, provide a custom `ValueResolver`, and read the result from `DataBinder`.

### Step 1 — Declare Dependency

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>value-resolver-demo</artifactId>
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

`spring-context` brings in the Spring Beans/Core libraries needed for `DataBinder`. The `maven.compiler.parameters=true` property preserves parameter names for regular Java data constructors; `record` types also have canonical component name metadata.

### Step 2 — Create the Complete Class

Create `src/main/java/demo/ValueResolverDemo.java`:

```java
package demo;

import java.util.Map;
import java.util.Set;

import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class ValueResolverDemo {

    public record Address(String city) {}

    public record Registration(
            String name,
            Integer age,
            Address address) {}

    public static void main(String[] args) {
        Map<String, Object> input = Map.of(
                "name", "Lan",
                "age", "24",
                "address.city", "Hue");

        DataBinder.ValueResolver resolver =
                new DataBinder.ValueResolver() {

            @Override
            public Object resolveValue(String name, Class<?> type) {
                // Return raw input: DataBinder converts types as needed.
                return input.get(name);
            }

            @Override
            public Set<String> getNames() {
                // Key "address.city" is required to detect
                // nested data under the "address" parameter.
                return input.keySet();
            }
        };

        DataBinder binder = new DataBinder(null, "registration");
        binder.setTargetType(
                ResolvableType.forClass(Registration.class));
        binder.construct(resolver);

        BindingResult errors = binder.getBindingResult();
        System.out.println("errors=" + errors.getErrorCount());

        if (errors.hasErrors() || binder.getTarget() == null) {
            System.out.println("binding failed");
            return;
        }

        Registration result = (Registration) binder.getTarget();
        System.out.println("name=" + result.name());
        System.out.println("age=" + result.age());
        System.out.println("city=" + result.address().city());
    }
}
```

### Step 3 — Compile and Run

In the directory containing `pom.xml`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.ValueResolverDemo
```

The stdout produced by `main` (excluding Maven logs):

```text
errors=0
name=Lan
age=24
city=Hue
```

Component-by-component explanation:

- `new DataBinder(null, ...)` creates a binder with no target yet.
- `ResolvableType.forClass(Registration.class)` declares the type to instantiate.
- `resolveValue("name", String.class)` retrieves `"Lan"`.
- `resolveValue("age", Integer.class)` retrieves `"24"`; converting the string to a number is handled by `DataBinder`.
- For constructor parameter `address` of type `Address`, the map **does not contain the key `"address"`**. However, `getNames()` includes `"address.city"`, indicating there is data under the `address` branch; the binder can construct `Address("Hue")` from the nested path.
- `construct(...)` creates `Registration("Lan", 24, new Address("Hue"))`; `getTarget()` returns that instance.
- The code prints output directly from the Java record, so the result does not depend on `Map.of` iteration order.

This is a standalone Java file **within the Maven project containing the `pom.xml` above**. If you want to use Gradle, declare the equivalent dependency `implementation("org.springframework:spring-context:6.2.12")` in an appropriate Gradle Java project. Do not drop the example into a Spring Boot project using a different BOM version without checking compatibility.

### Rerunning with Different Data

Replace:

```java
Map<String, Object> input = Map.of(
        "name", "Mai",
        "age", "31",
        "address.city", "Da Nang");
```

The printed values after `errors=0` become:

```text
name=Mai
age=31
city=Da Nang
```

Changing the data only affects the `Map` read by the resolver; there is no need to modify the constructor or add JavaBean setters.

## 5. Why Is getNames() Important for Nested Objects?

Suppose the DTO has the structure:

```java
public record Customer(
        String fullName,
        Address address) {}

public record Address(String city, String street) {}
```

This snippet illustrates **two top-level records**, which must be placed in two files `Customer.java` and `Address.java` (or converted into member records of a class).

Input:

```text
fullName=Lan
address.city=Hue
address.street=Le Loi
```

A map-based `ValueResolver` might only store the keys:

```text
fullName
address.city
address.street
```

For the `address` parameter, a direct lookup `resolveValue("address", Address.class)` returns `null` because no such key exists. Spring can query `getNames()` to determine whether keys with the `address.` prefix exist. Because **they do**, it recursively processes `Address`'s constructor and looks up the paths `address.city` and `address.street`.

Conceptual diagram:

```text
Customer constructor
  ├── fullName:String
  │       -> resolveValue("fullName", String.class) = "Lan"
  └── address:Address
          -> resolveValue("address", Address.class) = null
          -> getNames() shows "address.city" and "address.street"
          -> build Address constructor:
                 resolveValue("address.city", String.class) = "Hue"
                 resolveValue("address.street", String.class) = "Le Loi"
          -> Address("Hue", "Le Loi")
  -> Customer("Lan", address)
```

This is a **conceptual lookup model**, not a guarantee of call order or frequency across all Spring versions. A custom resolver must remain consistent when Spring queries the same key repeatedly.

If `getNames()` always returns `Set.of()` even though `resolveValue("address.city", ...)` could read a value, Spring may conclude there is no nested data and skip creating `Address`. As a result, `customer.address()` may be `null` or data may be missing depending on context. Therefore **`getNames()` is not a decorative method**; it participates in deciding the object graph structure to construct.

Conversely, if no key exists under `address.`, Spring can treat that complex argument as *missing* rather than unnecessarily creating an empty child object. This differs from property binding auto-growing the object graph when `autoGrowNestedPaths` is enabled; do not treat the two mechanisms as identical.

## 6. NameResolver and ValueResolver: One Picks the Name, One Fetches the Data

Two interfaces nested inside `DataBinder` have similar names but different duties:

| Part | API | Question it answers |
| --- | --- | --- |
| `DataBinder.NameResolver` | `String resolveName(MethodParameter parameter)` | "Under what name should this Java parameter be looked up?" |
| `DataBinder.ValueResolver` | `Object resolveValue(String name, Class<?> type)` | "Given the chosen name and type, what value does the input source have?" |
| `DataBinder.ValueResolver` | `Set<String> getNames()` | "What are all the keys present in the input source, including nested keys?" |
| `DataBinder` type conversion | `ConversionService`/`PropertyEditor` | "Can the raw value be converted to the Java type required by the constructor?" |

For example, constructor parameter `fullName` when an HTTP form sends `full-name`:

```text
full-name=Lan
```

`NameResolver` decides to use the key `"full-name"` instead of `"fullName"`; then `ValueResolver` reads `"full-name"` from the source. Do not mutate the value map by guessing names when Spring already provides a name resolution mechanism.

In Spring MVC 6.1+ applications, the common way to express name mapping is `@BindParam`:

```java
import org.springframework.web.bind.annotation.BindParam;

public record PersonInput(
        @BindParam("full-name") String fullName,
        Integer age) {}
```

This is a standalone DTO record (placed in `PersonInput.java` or declared as a member record). Spring MVC supports `@BindParam` on constructor parameters/fields when constructing `@ModelAttribute`. This is a **Spring Web** annotation; the `ValueResolverDemo` example using **plain core `DataBinder`** will not automatically handle this Web annotation unless an appropriate name resolver is configured.

If using `DataBinder` directly and mapping with custom rules:

```java
// Snippet inside a method before binder calls construct().
binder.setNameResolver(parameter -> {
    if ("fullName".equals(parameter.getParameterName())) {
        return "full-name";
    }
    return null; // Let Spring use the default parameter name.
});
```

With this snippet, `DataBinder` uses `"full-name"` when asking `ValueResolver` to read the value for `fullName`. Returning `null` from `resolveName` means **no custom name**, so Spring falls back to parameter name discovery; unlike `null` returned by `resolveValue`, which means **no value found**.

## 7. Raw Values, Target Types, and Type Conversion

`resolveValue(String name, Class<?> type)` returns `Object`. The source can return a `String`, `String[]`, or an object already of the right type. `type` indicates the **parameter type required by the constructor**, not a guarantee that the data source already holds an object of that type.

| Input | Constructor type | What should happen |
| --- | --- | --- |
| `"Lan"` | `String` | Used directly |
| `"24"` | `Integer` | String converted to `Integer 24` |
| `"true"` | `Boolean` | Converted to `Boolean.TRUE` if configuration supports it |
| `"2026-11-02"` | `LocalDate` | Requires suitable conversion/formatter |
| `address.city=Hue` | `Address` | Can construct nested object from child keys |
| `items[0].sku=ABC` | `List<Item>` | Can construct element by index if type and conditions match |

**Do not cast prematurely when unnecessary:** a simple resolver returns the raw `String` and lets `DataBinder` use its configured conversion system. That keeps input retrieval free from duplicating number/date parsing logic. However, a resolver may use `type` to decide how to return multi-value or special content, as long as the output contract aligns.

Example requiring a date format:

```java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public record Booking(
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {}
```

This is an illustrative DTO and **does not prove** that plain `DataBinder` with only `spring-context` automatically recognizes `@DateTimeFormat`. The application must configure a `FormattingConversionService`/formatter supporting Spring Format (or an appropriate converter). In MVC/Boot, the framework typically pre-configures the relevant formatters.

### Multi-Value Input

An HTML form parameter can be submitted multiple times, for example:

```text
tags=java&tags=spring
```

A web resolver can obtain multiple values; to avoid losing data, do not write a custom resolver that "takes the first element" when the constructor parameter expects `List<String>` or `String[]`. Consider `type` and the characteristics of the data source. In the demo's `Map` source, each key stores only one object; the example does not inherently support duplicate keys like a servlet request.

## 8. Keys for Lists, Maps, Arrays, and Nested Collections

Spring's constructor binding also supports paths containing indices/keys:

```text
accounts[0].name=Lan
accounts[1].name=Mai
labels[home]=Home
scores[0]=8
scores[1]=9
```

For a DTO with matching lists/maps and full type metadata, `DataBinder` can locate these keys to create collections or nested objects. A general-purpose `ValueResolver` must:

1. Preserve key paths and bracketed expressions when reading from the source.
2. Return all available key names in `getNames()`, such as `"accounts[0].name"` and `"accounts[1].name"`.
3. Implement `resolveValue(name, type)` consistently with `getNames()`.
4. Never allocate an unbounded list just because a client sends an enormous index; enforce input size/depth limits at request boundaries and via appropriate binder settings.
5. Distinguish `Map` keys from collection indices according to constructor types; do not decode every `[...]` with a single formula.

**Spring decides how to build collections based on type metadata and the listed names; the resolver primarily supplies raw values/names.** For complex input cases, write real integration tests because element-type conversion and constructors affect the outcome.

For example, if the DTO is:

```java
public record OrderInput(java.util.List<Line> lines) {}

public record Line(String sku, Integer quantity) {}
```

And the input is `lines[0].sku=ABC&lines[0].quantity=2`, Spring can construct `Line` elements from nested paths when full generic info is available. The two `public record` declarations in this example must reside in separate top-level files or be made member records.

Do not infer from `getNames().size()` that there are exactly that many constructor parameters; multiple keys can belong to a single complex object.

## 9. Distinguishing Missing Keys, Null, Empty Strings, and Conversion Errors

This is where custom resolvers most easily introduce silent bugs.

### A. Missing Key

If the key `"age"` is not found, `resolveValue("age", Integer.class)` typically returns `null`. `DataBinder` handles this depending on parameter type and metadata: it may pass `null` for reference types, use defaults in supported contexts, or report an error when the constructor cannot instantiate. **Do not treat a missing key as automatically generating a FieldError in all cases**.

### B. Key Present with Null Value

`Map#get(...)` returns `null` both when a key is absent and when its value is genuinely `null`. `getNames()` helps the framework tell whether a key name exists, especially for nested paths, yet the `resolveValue` contract still returns `null` in both situations. If the application must distinguish "not sent" from "explicitly cleared by client", design a dedicated input contract and resolver rather than assigning fixed semantics to `null`.

### C. Empty String

`age=` produces the string `""` in many request sources. Converting `""` to `Integer` may yield `null` or a result/error depending on conversion/editors, whereas `name=""` remains an empty `String`. A "name is required" rule is **validation**, such as `@NotBlank` backed by a provider, not the default meaning of `ValueResolver`.

### D. Unconvertible Value

If the input is `age=abc` and the constructor expects `Integer`, conversion cannot produce a number. `DataBinder` records binding/conversion errors in `BindingResult` when handled; you can inspect `getFieldError("age")` and codes such as `typeMismatch`. Target state after a constructor failure depends on the scenario; proceed with business logic only if there are no errors and the object was actually created.

```java
// Inspection snippet inside a method that already has binder:
var result = binder.getBindingResult();
if (result.hasErrors()) {
    result.getFieldErrors().forEach(error ->
            System.out.println(error.getField() + ": "
                    + error.getCode()));
}
```

This snippet is only for debugging field names/error codes and is not a standalone Java file. In production systems, avoid printing `getRejectedValue()` if it might contain passwords, tokens, or sensitive data; for constructor instantiation exceptions not captured in `BindingResult`, handle exceptions at the appropriate layer.

### E. Validation Is Separate from Binding

`DataBinder.construct(...)` performs binding/instantiation. It does not automatically check every Jakarta Bean Validation annotation just because the DTO has `@NotBlank` or `@Min`. You must register and invoke a validator via `DataBinder.validate(...)` or use the validation mechanism configured by Spring MVC when `@Valid` is present. Distinguish **type-binding errors** from **business-rule constraint violations**.

## 10. In Spring MVC, Who Provides ValueResolver?

Most Spring MVC applications do not need to write a `ValueResolver` by hand. Spring's web classes can create a resolver from the request:

- `ServletRequestDataBinder` has `construct(ServletRequest request)`, using a resolver tailored for request parameters and multipart input.
- The related resolver class is `ServletRequestDataBinder.ServletRequestValueResolver`, which implements `DataBinder.ValueResolver`. It knows how to fetch values by name from a servlet request and list input names.
- MVC components use the data binder along the `@ModelAttribute` processing pipeline; developers simply declare models/DTOs and configure the binder when needed.

Example `@ModelAttribute` handler in a fully configured Spring MVC application:

```java
import jakarta.validation.Valid;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

// Method snippet inside a @Controller:
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration-form";
    }
    return "registration-success";
}
```

`RegistrationForm`, the views, and Spring MVC/Validation dependencies are part of the real application; this is **not a standalone runnable Java file**. In Spring 6 / Boot 3, `@Valid` comes from `jakarta.validation.Valid`; `BindingResult` remains in `org.springframework.validation`.

A form request:

```text
name=Lan&age=24
```

can be used by MVC to construct an appropriately declared record/class, though the exact outcome depends on DTO design, constructors, conversion, validation, and binding configuration. Do not build a manual resolver just to duplicate how MVC already resolves request parameters.

**Crucial distinction from JSON:** a DTO bound from `@RequestBody` is typically deserialized from JSON by an `HttpMessageConverter` (such as Jackson). Do not describe `DataBinder.ValueResolver` as the default JSON converter for `@RequestBody`. Its primary scope is constructor binding within Spring data binding, particularly with `@ModelAttribute` and corresponding binders.

## 11. When Do You Need a Custom ValueResolver?

A custom `ValueResolver` is useful when:

- Data for constructing an object comes from a `Map`, command-line options, a configuration with property-path keys, or a custom data-source adapter layer.
- You use `DataBinder` at the core level outside MVC and want control over name/type lookup.
- The source holds data in shapes unlike servlet parameters, such as certain keys storing `String[]`, pre-parsed numbers, or values from an internal API.
- You need to integrate nested/collection data into constructor binding while keeping lookup logic decoupled from object construction logic.

You do not need a custom resolver just to turn `full-name` into `fullName`: look at `NameResolver` or `@BindParam` in MVC first. You do not need a custom resolver just to parse dates by format: `ConversionService`/formatters are the right place to configure type conversion rules.

### Designing a Good Resolver

```java
public final class MapValueResolver
        implements DataBinder.ValueResolver {

    private final Map<String, ?> values;

    public MapValueResolver(Map<String, ?> values) {
        this.values = Map.copyOf(values);
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

**Class snippet:** requires importing `java.util.Map`, `java.util.Set`, `org.springframework.validation.DataBinder` and placing in an appropriate file/class. `Map.copyOf` rejects `null` keys/values and creates an immutable snapshot; therefore this snippet only suits data sources without `null`. If you need to preserve nulls, choose an appropriate copy strategy and document the data semantics.

A snapshot-based resolver ensures `getNames()` and `resolveValue()` observe the same dataset. Reading names from source A while values from source B keep changing can cause the binder to detect a nested branch without finding child fields, making debugging difficult.

### Avoiding Side Effects

- `resolveValue` should not remove keys after the first read: Spring may query the same key multiple times.
- Do not rely on `getNames()` ordering for the final result.
- Do not mix multiple users' inputs into a mutable singleton resolver.
- Do not return different values for the same name/type without clear rules.
- Do not log raw inputs containing passwords, personal data, or tokens inside a resolver.
- Do not alter key names ambiguously in ways that lose hierarchy or indices.

## 12. Common Mistakes

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Code does not compile because `getNames()` is unimplemented | Copying a lambda/interface example from Spring 6.1.0 to 6.2.x | Implement both methods per the version in use |
| `construct(...)` reports missing target type | Forgot `setTargetType(ResolvableType.forClass(...))` | Declare the target type before `construct` |
| `construct(...)` reports target already exists | Initializing binder with an instance instead of `null` | Use a binder with a `null` target for constructor binding |
| Child object is not constructed | `getNames()` lacks nested keys or has wrong prefix | Return full keys like `address.city`, `items[0].sku`… |
| Field receives `null` | Key does not match parameter or resolver returns null | Check `NameResolver`, `resolveValue`, and input |
| Invalid numeric value | `"abc"` cannot convert to `Integer` | Check `BindingResult`; fix data or converter |
| `@BindParam` has no effect in custom core binder | Using plain core `DataBinder` without an appropriate NameResolver | Configure custom naming or use Spring MVC with annotation support |
| Multi-value input is lost | Resolver picks only the first `String` even though target needs an array/list | Read all values and inspect `type` |
| Constructor does not receive proper parameter names | Name metadata stripped or class has ambiguous constructors | Keep `-parameters`/use records/clear data constructor |
| Confusing `getNames()` with constructor parameter list | It is the input key set, which may include nested/extra keys | Inspect data structure and target type |
| Assuming `allowedFields` blocks constructor args | Allowed fields is primarily a guard for property binding | Restrict inputs via explicit DTO constructors |
| Returning wrong-typed raw value without a converter | `DataBinder` cannot convert the type | Configure an appropriate `ConversionService`/editor |
| Not checking `BindingResult` | Using the target despite binding errors | Check errors before running business logic |

## 13. Data Safety and Limiting Lookup Scope

Constructor binding is generally safer than allowing every setter on an entity to be modified, because only parameters declared by the constructor are used by Spring to build the object. However, **a constructor can also include parameters that should never come from clients**. For instance, if a DTO constructor has a `role` parameter, a client could try sending `role=ADMIN`; creating the DTO does not perform authorization on its own.

Principles to follow:

1. Create **dedicated request DTOs** containing only fields clients are allowed to provide.
2. Do not expose entities with security-sensitive properties in request-facing constructors merely for convenience.
3. If property binding is needed after constructor binding, control it with `setDeclarativeBinding(true)` and/or `setAllowedFields(...)` by design. In Spring MVC, property binding can still run after object creation unless restricted.
4. Control the size, count, and depth of collection inputs/nested paths; prevent huge index keys from forcing the application to allocate/create excessive objects.
5. Do not treat `getNames()` as a security filter; it merely describes existing keys. Validation/authorization must still be enforced separately.
6. Never use output from `resolveValue` to construct SQL expressions, filesystem paths, or arbitrary reflection without allowlists/valid semantics.

Example enabling declarative binding in a Spring MVC controller:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

// Snippet inside a @Controller class:
@InitBinder
void initBinding(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

With this configuration, Spring favors constructor binding; property binding continues only for fields declared in `allowedFields` when applicable. This reduces over-posting risks on mutable models. It does not replace property-level permission checks in the service layer.

## 14. How to Test ValueResolver Meaningfully

To separate resolver bugs from constructor or converter bugs, test all three layers.

### A. Unit Test the Resolver Standalone

- `resolveValue("name", String.class)` reads the expected input string.
- `resolveValue("age", Integer.class)` can return raw `"24"` for the binder to convert later.
- `resolveValue("unknown", String.class)` returns `null` when the key is absent.
- `getNames()` contains all keys including `"address.city"`.
- Repeated calls for the same key return consistent results if the source has not changed.

### B. Test DataBinder.construct

- Happy path: construct a record with all fields and nested objects, `getErrorCount() == 0`.
- Type mismatch: `age="abc"` produces an observable type conversion error in `BindingResult`; do not treat the target as a valid object.
- Missing input: verify `null` semantics, missing values, and DTO validation.
- Aliasing: verify `NameResolver` or `@BindParam` resolves `full-name` properly.
- Nested collections: test keys like `items[0].name` and index limits.
- Source mutation: if the source can change during binding, snapshot it to ensure consistent data.

### C. MVC Integration Tests When Using Web

Send real form requests to the controller to ensure the servlet resolver, formatter configuration, and `@Valid` behave as expected. Verify status/responses for valid input, type mismatches, missing fields, and disallowed fields. Do not treat a passing unit test for `MapValueResolver` as proof that all request formatting/multipart binding works.

### A Quick Modification Experiment on the Runnable Example

Change `"age", "24"` inside `Map.of(...)` to `"age", "abc"`. Then rerun and observe the `errors.hasErrors()` branch, because `"abc"` cannot be converted to `Integer` by standard numeric converters. Do not assume the target object always exists in a valid state after an error; check `BindingResult` first.

## 15. API Summary and Implementation Mindset

- `DataBinder.ValueResolver` is the **value lookup source** for constructor binding, not an instance builder or validator itself.
- `resolveValue(name, type)` looks up **one value** for a parameter name and type; it can return a raw `String` and let `DataBinder` convert types.
- `getNames()` returns **all input keys**, crucial for detecting nested constructor arguments, lists/maps/arrays; in Spring 6.2 you must implement both methods.
- `DataBinder.NameResolver` determines the lookup name; `@BindParam` is how Spring MVC maps input names differing from Java names.
- To use the core API: `new DataBinder(null, name)` → `setTargetType(ResolvableType)` → `construct(ValueResolver)` → check `getBindingResult()` → use `getTarget()` when successful.
- Design clear DTOs and input boundaries; validation and authorization are subsequent steps, not responsibilities handled by the resolver itself.

## References

- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework 6.2 API — DataBinder.ValueResolver](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html)
- [Spring Framework 6.2 API — DataBinder](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 API — DataBinder.NameResolver](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.NameResolver.html)
- [Spring Framework 6.2 API — ServletRequestDataBinder](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/bind/ServletRequestDataBinder.html)
- [Spring Framework 6.2 API — @BindParam](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/bind/annotation/BindParam.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — Data Binding and Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html)
