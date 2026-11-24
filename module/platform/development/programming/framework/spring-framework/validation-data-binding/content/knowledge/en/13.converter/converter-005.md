# ConverterFactory for a Family of Target Types in Spring

In Spring Core, `ConverterFactory<S, R>` is an SPI used when **one source type needs to be converted into multiple target types sharing a common base type**. Instead of writing a separate `Converter<S, T>` for each target type, you write a single factory that accepts `Class<T>` and produces an appropriate converter for that specific target type.

A classic example is converting `String` into multiple enums: `Priority`, `OrderState`, `PaymentStatus`. Those enums can all implement a domain interface such as `CodeValue`. The factory receives the target enum class and returns a converter dedicated to handling that class.

~~~text
                 ConverterFactory<String, CodeValue>
                              |
               +--------------+---------------+
               |              |               |
        getConverter(     getConverter(   getConverter(
          Priority)       OrderState)    PaymentStatus)
               |              |               |
        Converter<String, Priority>  ...  Converter<String, PaymentStatus>
~~~

This topic focuses on **a family of target types**. The key point is not merely converting a string to one enum, but keeping a shared conversion rule across multiple target types in the same group while still leveraging target-specific information at converter creation time.

## 1. The ConverterFactory Contract

Spring defines the interface in package `org.springframework.core.convert.converter`:

~~~java
public interface ConverterFactory<S, R> {
    <T extends R> Converter<S, T> getConverter(Class<T> targetType);
}
~~~

Meaning of the generic parameters:

| Component | Meaning |
| --- | --- |
| `S` | The source data type read by the factory's converters. |
| `R` | The base type or upper bound of the **family of target types**. |
| `T extends R` | The concrete target type requested by a `getConverter(...)` call. |
| `targetType` | The `Class<T>` object describing the concrete target type. |
| Return value | A `Converter<S, T>` specialized for converting from `S` to that exact `T`. |

Example:

~~~java
ConverterFactory<String, Enum> factory = ...;

Converter<String, Priority> priorityConverter =
        factory.getConverter(Priority.class);

Converter<String, OrderState> stateConverter =
        factory.getConverter(OrderState.class);
~~~

Both converters share the source type `String` while having different target types. The factory knows which enum to handle via `targetType`, so it can inspect metadata or constants of that exact target enum.

In real applications, `R` does not have to be `Enum`. It can be an application-defined interface like `CodeValue`, a base class like `Number`, or another parent type extended/implemented by the target types.

## 2. When Should You Use ConverterFactory?

Consider three conversion needs:

**Case A — a single source/target type pair**

Converting `String` to `UUID`:

~~~java
Converter<String, UUID>
~~~

A simple `Converter` is usually enough.

**Case B — multiple target types in the same family**

Converting `String` to multiple enums:

~~~java
ConverterFactory<String, Enum>
~~~

One factory supplies the matching converter for each enum. This is the exact case `ConverterFactory` fits.

**Case C — multiple type pairs requiring rich metadata**

For example, converting an array into a collection where you need the target collection's element type, or conversions depending on annotation/field context:

~~~java
GenericConverter
~~~

`GenericConverter` provides both source and target `TypeDescriptor`s as well as the set of type pairs it supports. When multiple source/target types or field/generic type metadata are needed, this is usually the better choice.

Decision table:

| Need | SPI to consider | Reason |
| --- | --- | --- |
| Only one source type and one target type | `Converter<S, T>` | Simple, strongly typed contract. |
| One source type to multiple target types sharing a base type | `ConverterFactory<S, R>` | `getConverter(Class<T>)` receives the concrete target type. |
| Multiple source/target pairs, needing descriptors or metadata | `GenericConverter` | Has `TypeDescriptor` and a set of `ConvertiblePair`s. |
| Applied only when a metadata condition is met | `ConditionalConverter` or `ConditionalGenericConverter` | Allows checking conditions before the converter is selected. |

Do not use `ConverterFactory` just because there is a lot of code. If each target type has independent rules and they do not share a common family, separate `Converter`s can be clearer.

## 3. Business Example: An Enum Family with Custom Codes

Suppose the system receives short codes from a form or configuration:

- `Priority.HIGH` has code `H`.
- `Priority.LOW` has code `L`.
- `OrderState.OPEN` has code `O`.
- `OrderState.CLOSED` has code `C`.

Both enums implement the `CodeValue` interface:

~~~java
public interface CodeValue {
    String code();
}
~~~

The factory can be declared as:

~~~java
public class StringToCodeValueConverterFactory
        implements ConverterFactory<String, CodeValue> {
    // ...
}
~~~

When `getConverter(Priority.class)` is called, the factory creates a converter that only knows about `Priority`. When `getConverter(OrderState.class)` is called, the factory creates a converter that only knows about `OrderState`. Common rules such as trimming input, case-insensitive comparison, and reporting an error when a code is not found can be implemented once.

Key point: `R` is the **target-type bound**, not the source type. In this example, the source is `String`, and the target family is types implementing `CodeValue`.

## 4. Complete Java 17+ Program with Spring

The example below uses Spring Framework `6.2.0`. It registers a `ConverterFactory<String, CodeValue>` with `DefaultConversionService` and converts into two different enums.

Project structure:

~~~text
converter-factory-demo/
├── pom.xml
└── src/main/java/example/ConverterFactoryDemo.java
~~~

### 4.1. Creating pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>converter-factory-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
~~~

### 4.2. Creating ConverterFactoryDemo.java

~~~java
package example;

import java.util.Locale;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.converter.ConverterFactory;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConverterFactoryDemo {

    public interface CodeValue {
        String code();
    }

    public enum Priority implements CodeValue {
        HIGH("H"),
        LOW("L");

        private final String code;

        Priority(String code) {
            this.code = code;
        }

        @Override
        public String code() {
            return code;
        }
    }

    public enum OrderState implements CodeValue {
        OPEN("O"),
        CLOSED("C");

        private final String code;

        OrderState(String code) {
            this.code = code;
        }

        @Override
        public String code() {
            return code;
        }
    }

    public static final class StringToCodeValueConverterFactory
            implements ConverterFactory<String, CodeValue> {

        @Override
        public <T extends CodeValue> Converter<String, T> getConverter(
                Class<T> targetType) {

            if (!targetType.isEnum()) {
                throw new IllegalArgumentException(
                        "Target type must be an enum: " + targetType.getName());
            }

            return source -> {
                String normalized = source.trim()
                        .toUpperCase(Locale.ROOT);

                for (Object constant : targetType.getEnumConstants()) {
                    CodeValue candidate = (CodeValue) constant;

                    if (candidate.code().equalsIgnoreCase(normalized)) {
                        return targetType.cast(candidate);
                    }
                }

                throw new IllegalArgumentException(
                        "Unknown code '" + source
                                + "' for " + targetType.getSimpleName());
            };
        }
    }

    public static void main(String[] args) {
        DefaultConversionService registry =
                new DefaultConversionService();

        registry.addConverterFactory(
                new StringToCodeValueConverterFactory());

        ConversionService conversionService = registry;

        Priority priority =
                conversionService.convert(" h ", Priority.class);

        OrderState state =
                conversionService.convert("o", OrderState.class);

        System.out.println("priority=" + priority);
        System.out.println("state=" + state);
        System.out.println("canConvertToPriority="
                + conversionService.canConvert(
                        String.class, Priority.class));
        System.out.println("canConvertToState="
                + conversionService.canConvert(
                        String.class, OrderState.class));
    }
}
~~~

### 4.3. Compiling and Running

Requires JDK 17+ and Maven. Open a terminal in the `converter-factory-demo` directory:

~~~bash
mvn -q package
java -cp target/classes;... example.ConverterFactoryDemo
~~~

The `java -cp` command in the example requires a classpath containing the Maven dependencies; a shorter and accurate way to run the project above is to add `exec-maven-plugin` to `pom.xml`, then run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.ConverterFactoryDemo
~~~

To run that command, add the plugin to the `build/plugins` section of the pom:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.3.0</version>
</plugin>
~~~

Stdout output:

~~~text
priority=HIGH
state=OPEN
canConvertToPriority=true
canConvertToState=true
~~~

Explanation:

1. `DefaultConversionService` is a built-in implementation of `ConversionService` and registry; we register the factory via `addConverterFactory(...)`.
2. When converting `" h "` to `Priority`, the conversion service selects the registered converter factory and requests the converter specifically for `Priority.class`. The converter trims the string, normalizes it, and locates code `H`.
3. When converting `"o"` to `OrderState`, the same factory is used, yet `targetType` is `OrderState.class`; the converter locates code `O`.
4. Two target types do not require two manually registered `Converter` classes. The factory creates the appropriate converter based on `targetType`.
5. `canConvert(...)` only indicates whether a matching converter exists based on type metadata; it **does not pre-check specific values**. For example, `canConvert(String.class, Priority.class)` can return `true` even though `"X"` is not a valid Priority code.

Note on the run command: if using `exec-maven-plugin` as added above, specify `mainClass` in the plugin configuration or pass `-Dexec.mainClass` as in the command above. Do not use a classpath with only `target/classes`, because Spring dependencies are not in that classpath.

## 5. Reading the Generic Type Carefully: Why Is R a Base Type?

A declaration:

~~~java
ConverterFactory<String, Number>
~~~

means the factory converts from `String` to multiple subclasses of `Number`, such as `Integer`, `Long`, `Double`. It does **not mean** the factory converts to the exact type `Number` on every call.

When calling:

~~~java
Converter<String, Integer> toInteger =
        factory.getConverter(Integer.class);

Converter<String, Long> toLong =
        factory.getConverter(Long.class);
~~~

`T` is inferred as `Integer` and `Long` respectively, both satisfying `T extends Number`.

If you write:

~~~java
ConverterFactory<String, Integer>
~~~

then the target type is bounded much more narrowly; that factory cannot be used to return `Converter<String, Long>` because `Long` is not a subtype of `Integer`.

### The Factory Must Use targetType

Inside `getConverter(Class<T> targetType)`, the target parameter allows the factory to:

- Look up enum constants or metadata of the target class.
- Select an appropriate conversion algorithm.
- Build a specialized converter for that exact target.
- Reject target types that do not belong to the supported group.

If the factory ignores `targetType` and always builds a converter for one fixed enum, it fails to serve the purpose of “a family of target types”.

### Why Should You Not Cast Arbitrarily?

The generic signature guarantees at compile time that `T extends R`, yet **it does not prove every subclass shares the same internal structure**. If the factory relies on an enum assumption, check `targetType.isEnum()` before calling `getEnumConstants()`. If an interface can be implemented by a non-enum class, handle that case explicitly as in the example.

## 6. Registering the Factory in ConversionService

A `ConverterFactory` does not run automatically just because a Java method is called. It must be registered in a registry or configured in the Spring container appropriately.

### 6.1. Using ConversionService Directly

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverterFactory(
        new StringToCodeValueConverterFactory());

Priority priority =
        conversionService.convert("H", Priority.class);
~~~

This is a straightforward way to use the converter in any code without Spring MVC.

### 6.2. Using in DataBinder

`DataBinder` can accept a `ConversionService` to convert property values from sources to property types:

~~~java
ProductForm form = new ProductForm();

DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverterFactory(
        new StringToCodeValueConverterFactory());

DataBinder binder = new DataBinder(form, "product");
binder.setConversionService(conversionService);

MutablePropertyValues values = new MutablePropertyValues();
values.add("priority", "H");

binder.bind(values);

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Do not use the data to execute business logic.
}
~~~

This is an **illustrative snippet**; `ProductForm` needs a `priority` property of the appropriate enum type with getter/setter. Relevant imports include `DataBinder`, `MutablePropertyValues`, and `BindingResult`.

If the converter fails to convert a code, the binder records a binding/conversion error in `BindingResult`. After binding, the application should check `hasErrors()` before proceeding. The converter only handles type conversion; it does not replace value validation or business checks.

### 6.3. Registering in Spring MVC

In a Spring MVC application, you can add the converter to MVC's registry:

~~~java
// Snippet inside @Configuration.
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverterFactory(
            new StringToCodeValueConverterFactory());
}
~~~

`FormatterRegistry` can register `Converter`, `ConverterFactory`, and `GenericConverter`. MVC uses the conversion/formatting system when binding request parameters or model attributes under appropriate configuration. This configuration is for **MVC property binding**; do not assume it automatically turns Jackson JSON deserialization into the same pipeline.

In a Spring Boot application, register the factory in the conversion configuration mechanism appropriate for your version and application type. Avoid creating a new `DefaultConversionService` for every request; the service is designed to be shared and reused.

## 7. Handling Invalid Values and Null

The `Converter` contract requires `convert(S source)` to receive a non-null source in normal Spring `ConversionService` flows. When source data is invalid, the converter should throw an unchecked exception—typically `IllegalArgumentException`—to indicate it cannot convert.

Example:

~~~java
throw new IllegalArgumentException(
        "Unknown code '" + source + "'");
~~~

When invoked through `ConversionService`, the conversion exception may be wrapped in a `ConversionFailedException` or a context-appropriate `ConversionException`. When used through `DataBinder`, a conversion error may be recorded as a `FieldError` with a code such as `typeMismatch`.

Do not return `null` to silently indicate every invalid code unless the application's contract explicitly defines that behavior. Bad values should produce an observable, handleable error.

### Null Source Differs from Empty String

Distinguish carefully:

| Input | Common meaning |
| --- | --- |
| `null` | No source object to convert; `ConversionService` has its own null-handling path. |
| `""` | Empty string; the converter receives an empty string and must determine whether this is an invalid code, a default, or a special state per contract. |
| `"  "` | Whitespace string; the converter may trim it and then treat it as empty if rules allow. |
| `"H"` | Valid concrete code if the target type has a matching code. |
| `"UNKNOWN"` | String with no matching code; the converter should report a conversion error. |

Do not call `source.trim()` before handling null if the converter can be called directly outside `ConversionService`. Under the standard contract, converters do not receive null, yet you should document that assumption and validate inputs appropriately if the public method is invoked directly.

### Do Not Use the Default Locale for Technical Codes

When normalizing characters, avoid depending on the runtime machine's locale. Use:

~~~java
source.toUpperCase(Locale.ROOT)
~~~

instead of `toUpperCase()` with no arguments. This is especially important for technical codes independent of user language. If code rules genuinely carry locale semantics, pass the locale as part of the contract instead of relying on JVM-wide configuration.

## 8. Lifecycle and Thread Safety

A `ConversionService` is normally created at application startup and shared across multiple threads. Spring describes `ConversionService` as stateless by design, suitable for sharing. The factory should likewise be implemented as a component **with no per-request mutable state**.

Best practices:

- The factory holds no data that changes per conversion call.
- Converters returned by the factory should be immutable or safe under concurrent use.
- Do not cache results keyed by mutable inputs without synchronization and bounded memory.
- Metadata depending on `targetType` should be computed during `getConverter` and stored in an immutable converter if beneficial.
- Avoid mutating the registry after the service is already in use across the application, unless the API/configuration explicitly supports it.

In the sample program, the returned converter closes over `targetType`. `targetType` is an immutable `Class` object, so referencing it creates no per-request mutable state.

## 9. Deeper Comparison: Converter, ConverterFactory, and GenericConverter

| Feature | Converter | ConverterFactory | GenericConverter |
| --- | --- | --- | --- |
| Source type | Single `S` | Single `S` | Multiple source types via type pairs |
| Target type | Single `T` | A family `T extends R` | Multiple target types via type pairs |
| Receives target Class | No inside convert method | Yes inside `getConverter(Class<T>)` | Has `TypeDescriptor` during convert |
| Field/generic metadata | Not directly | Not directly | Yes via `TypeDescriptor` |
| Complexity | Low | Medium | Higher |
| Fitting example | String -> UUID | String -> any enum in a family | Array -> various collection types |

A helpful rule of thumb: **choose the simplest SPI that satisfies the conversion model**. Use `ConverterFactory` when differences across converters depend primarily on the target type within the same family. Use `GenericConverter` when logic must read richer metadata or support multiple source/target pairs not cleanly represented by one `S` and one `R`.

## 10. Common Pitfalls

**Mistake 1 — Swapping S and R.**

~~~java
ConverterFactory<CodeValue, String>
~~~

This declaration means the source is `CodeValue` and the target type is `String`. If the goal is reading a `String` code to produce an enum, it must be `ConverterFactory<String, CodeValue>`.

**Mistake 2 — Ignoring targetType.**

If the converter always returns `Priority` even when the caller asks for `OrderState`, the factory violates the generic contract and can cause runtime type errors. Use `targetType` to inspect target metadata and return a converter for the exact `T`.

**Mistake 3 — Returning a converter with mismatched generics.**

Do not cast `Converter<String, Priority>` to `Converter<String, OrderState>`. Let the compiler check generic relationships and avoid raw types or unnecessary casts.

**Mistake 4 — Assuming enums always use name().**

`Enum.valueOf(...)` only looks up by constant name, such as `HIGH`. If the wire format uses code `H`, look up code metadata as in the `CodeValue` example.

**Mistake 5 — Failing to handle unknown codes.**

An unmapped code must have clear behavior: throw a conversion exception, produce an appropriate validation error, or apply a contract-permitted default. Never silently return the first enum constant.

**Mistake 6 — Using the default locale.**

Technical codes exchanged between systems must not change behavior depending on the machine's default locale. Use `Locale.ROOT` when normalizing language-independent ASCII codes.

**Mistake 7 — Creating a ConversionService on every call.**

Doing so incurs initialization and converter-registration overhead while scattering configuration. Configure a shared service in the application context or a dedicated initialization point.

**Mistake 8 — Treating canConvert as a value check.**

`canConvert(String.class, Priority.class)` answers whether a converter exists at the type level; it does not prove every string is a valid code. Only calling `convert(...)` with a concrete value enforces the data rules.

**Mistake 9 — Assuming ConverterFactory registers itself automatically.**

Implementing the interface does not make Spring auto-discover every class. Register it into `ConverterRegistry`/`ConversionService` or configure it in the appropriate formatter registry.

**Mistake 10 — Putting heavy business logic into converters.**

A converter should transform data representations between types. Do not query the database, check permissions, or mutate domain state inside `convert(...)`. Those belong in the service/application layer.

## 11. How to Test a ConverterFactory

Tests should verify both **multiple target types** and **invalid data**.

Example with JUnit 5:

~~~java
// Test snippet with JUnit 5 assertions already imported.
DefaultConversionService service = new DefaultConversionService();
service.addConverterFactory(new StringToCodeValueConverterFactory());

assertEquals(Priority.HIGH,
        service.convert("H", Priority.class));

assertEquals(OrderState.OPEN,
        service.convert("O", OrderState.class));

assertThrows(ConversionException.class,
        () -> service.convert("unknown", Priority.class));
~~~

`ConversionException` is the base class in Spring's conversion system; testing an exact subtype may tie the test to the specific implementation/call path in use, so the assertion above uses the base class to avoid depending on a particular wrapper. This test snippet is illustrative and requires JUnit dependencies and appropriate imports.

A practical test suite should include:

| Test case | Expectation |
| --- | --- |
| Valid code for the first enum | Returns the exact constant of the first enum. |
| Valid code for the second enum | The same factory returns the exact constant of the second enum. |
| Lowercase code | Handled per case-insensitive policy if specified by the factory. |
| Leading/trailing whitespace | Trimmed per contract, or rejected if contract forbids it. |
| Non-existent code | Throws a conversion error. |
| Target type outside the family | Factory rejects explicitly. |
| Non-`String` source type | Converts only if another converter is registered; this factory does not match it. |
| Concurrent calls across threads | Consistent results, no dependence on shared mutable state. |

In addition to unit testing the converter directly, write integration tests for where it is used: `DataBinder`, Spring MVC form binding, or services using `ConversionService`. If the converter is used in a form, verify `BindingResult` has errors on invalid values and verify the service is not invoked when binding fails.

## 12. Application Implementation Workflow

1. Identify the **source type S** and the family of target types sharing a **base type R**.
2. Write `ConverterFactory<S, R>`, implementing `getConverter(Class<T>)` to build converters for each target.
3. Define clear rules for input normalization, missing data, invalid codes, and unsupported target types.
4. Ensure the converter/factory is safe when shared across threads.
5. Register the factory into `ConversionService` or `FormatterRegistry` wherever the application uses it.
6. Use `ConversionService.convert(...)` or let `DataBinder` use the conversion service when binding properties.
7. Check conversion and validation errors before passing the object to data-mutating business logic.
8. Test at least two target types in the same family along with invalid-data branches.

### Official Spring Documentation

- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework 6.2 — `ConverterFactory` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/convert/converter/ConverterFactory.html)
- [Spring Framework 6.2 — `ConversionService` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework 6.2 — `DefaultConversionService` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
- [Spring Framework 6.2 — `GenericConversionService` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
