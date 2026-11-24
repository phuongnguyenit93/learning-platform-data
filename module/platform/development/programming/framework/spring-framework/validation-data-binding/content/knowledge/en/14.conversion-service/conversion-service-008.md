# Role of Type Conversion in Spring Expression Language (SpEL)

Spring Expression Language (SpEL) does not only read properties or invoke methods. When an expression writes a value into an object, collection element, or nested property, the source value may have a different type from what the target requires. **The evaluation context's type converter** helps SpEL convert the value so the assignment matches the target's type.

For example, an object has a `Boolean enabled` property. The expression `parser.parseExpression("enabled").setValue(context, settings, "true")` receives the string "true" yet can assign Boolean true to the property. The type conversion mechanism is invoked during expression execution, based on the `TypeConverter` provided by `EvaluationContext`.

In Spring, SpEL uses Spring Core's `ConversionService` by default through the evaluation context's converter. ConversionService provides common converters for strings, numbers, enums, collections, and many other types; applications can also register custom converters. The system is generic-type aware when converting values in collection properties.

## 1. Why Does SpEL Need Type Conversion?

A SpEL expression is parsed into an execution structure. When evaluating, SpEL needs to know what the root object is, which properties can be read/written, what type the current value has, and what the target type is when assigning.

Consider an object:

~~~java
public class FeatureSettings {
    private Boolean enabled;
    private Integer retryCount;
}
~~~

If the expression receives a string value to assign:

~~~java
parser.parseExpression("retryCount")
      .setValue(context, settings, "5");
~~~

SpEL needs to convert String "5" into Integer before assigning to retryCount. If no matching converter exists or the content is invalid, evaluation fails with the corresponding SpEL exception.

For a list:

~~~java
public class FeatureSettings {
    private List<Boolean> flags = new ArrayList<>();
}
~~~

the expression `flags[0]` points to the first Boolean element. Assigning the string `"false"` to that position requires converting to Boolean. SpEL can use the property's generic metadata to know the expected element type is Boolean.

**Type conversion is not business validation.** Converting "5" into an integer does not prove that retry count is allowed; the application still needs constraints like `retryCount >= 0` and appropriate bounds.

## 2. EvaluationContext and TypeConverter

`EvaluationContext` is the object providing the context for SpEL to read and write data when running expressions. It supplies several strategies, including `TypeConverter`.

| Component | Role |
|---|---|
| `ExpressionParser` | Parses an expression string into an `Expression` object |
| `Expression` | Represents a parsed expression; can read or assign values |
| `EvaluationContext` | Supplies root object, property/method resolvers, type locator, type converter, and evaluation strategies |
| `StandardEvaluationContext` | Full-featured evaluation context allowing configuration of many strategies |
| `SimpleEvaluationContext` | Context with restricted SpEL features for data binding or limited use cases |
| `TypeConverter` | SpEL interface used to convert values during evaluation |
| `StandardTypeConverter` | Adapter connecting SpEL to Spring Core's type conversion mechanism |
| `ConversionService` | Spring Core API performing conversions between types; allows registering converters |

The assignment flow can be pictured as follows:

~~~text
ExpressionParser
      |
      v
parseExpression("retryCount")
      |
      v
Expression.setValue(context, target, "5")
      |
      v
EvaluationContext.getTypeConverter()
      |
      v
TypeConverter / StandardTypeConverter
      |
      v
Spring ConversionService
      |
      v
Matching converter: String -> Integer
      |
      v
Assign Integer(5) to target.retryCount
~~~

This is the conceptual flow. Details of choosing property accessors, determining the target descriptor, and selecting converters are handled by the SpEL/Spring infrastructure.

### StandardEvaluationContext

`StandardEvaluationContext` provides the full implementation for resolving properties, methods, constructors, types, and evaluation strategies. It allows replacing `TypeConverter`:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setTypeConverter(new StandardTypeConverter());
~~~

When custom conversion is needed, a specific `ConversionService` can be passed into `StandardTypeConverter`.

### SimpleEvaluationContext

`SimpleEvaluationContext` is intended for scenarios needing only a subset of SpEL features, such as data binding and property-based filtering. The application explicitly chooses read-only or read-write property access:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

This context does not expose the full functionality of `StandardEvaluationContext`: for instance, type references, constructor references, and bean references are excluded from the default feature set. It is useful when expressions come from users or external configuration and the application only needs operations on controlled properties. Even so, property accessors and read/write permissions must still be configured properly.

## 3. ConversionService and Its Relationship to SpEL

`org.springframework.core.convert.ConversionService` defines the runtime conversion API. Two primary call forms:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
~~~

Besides the overloads using `Class`, the API also supports `TypeDescriptor` to describe generic types and property metadata. This matters when the target is a collection, map, or collection element.

Common implementations:

- `DefaultConversionService`: convenient implementation with default converters.
- `GenericConversionService`: general-purpose implementation for registering and executing converters.
- `ConversionServiceFactory`: helps create a conversion service from a list of converters.

`ConversionService` is designed to be stateless and can be shared across threads provided application-registered converters share that property. Normally, converters are configured at application startup rather than altered while handling individual requests.

### Converter SPI

To define conversion from source type `S` to target type `T`, implement the interface:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Example converter taking a string and converting to the `Priority` enum:

~~~java
public final class PriorityConverter
        implements Converter<String, Priority> {

    @Override
    public Priority convert(String source) {
        return Priority.valueOf(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Converters should handle empty inputs, null if the contract requires it, casing, locale, formatting, and errors explicitly. Do not silently turn every error into a default value, as that masks invalid input.

### TypeDescriptor and Generic Types

These two types differ:

~~~java
List<String> names;
List<Boolean> flags;
~~~

Both have raw type `List`, yet their target element types differ. When SpEL writes to `flags[0]`, the infrastructure can use the property/element descriptor to convert the string into Boolean. If you only call `ConversionService.convert(source, List.class)`, the element generic information is not fully conveyed.

For explicit generic collection conversion, you can construct `TypeDescriptor`s for the source and target properties/fields and call the descriptor overload:

~~~java
Object converted = conversionService.convert(
        sourceValue,
        sourceTypeDescriptor,
        targetTypeDescriptor);
~~~

The descriptors must accurately describe source/target types and generic types. Never assume raw `List.class` is enough to determine each element's type.

## 4. Runnable Java 17+ Example: Default Conversion and Custom Converter

The program below illustrates three cases:

1. Assigning string "true" to a Boolean property.
2. Assigning string "false" to a `List<Boolean>` element to show SpEL using generic types.
3. Registering a custom converter from `String` to enum `Priority` and assigning "high" to a property.

The example uses Spring Framework 6.2.12, Java 17+, and Maven. No Spring Boot, web server, or database is required.

Directory structure:

~~~text
spel-conversion-demo/
├── pom.xml
└── src/main/java/demo/SpelConversionDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spel-conversion-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-expression</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/SpelConversionDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.expression.spel.support.StandardTypeConverter;

public final class SpelConversionDemo {

    enum Priority {
        LOW, MEDIUM, HIGH
    }

    public static final class Settings {
        private Boolean enabled = false;
        private List<Boolean> flags = new ArrayList<>(List.of(true));
        private Priority priority = Priority.LOW;

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }

        public List<Boolean> getFlags() {
            return flags;
        }

        public void setFlags(List<Boolean> flags) {
            this.flags = flags;
        }

        public Priority getPriority() {
            return priority;
        }

        public void setPriority(Priority priority) {
            this.priority = priority;
        }
    }

    public static void main(String[] args) {
        ExpressionParser parser = new SpelExpressionParser();
        Settings settings = new Settings();

        // ConversionService has common built-in converters.
        StandardEvaluationContext defaultContext =
                new StandardEvaluationContext(settings);

        parser.parseExpression("enabled")
                .setValue(defaultContext, "true");

        parser.parseExpression("flags[0]")
                .setValue(defaultContext, "false");

        System.out.println("enabled=" + settings.getEnabled());
        System.out.println("flags[0]=" + settings.getFlags().get(0));
        System.out.println("flags.elementType="
                + settings.getFlags().get(0).getClass().getName());

        // Register custom converter for String -> Priority.
        DefaultConversionService conversionService =
                new DefaultConversionService();

        conversionService.addConverter(
                String.class,
                Priority.class,
                source -> Priority.valueOf(
                        source.trim().toUpperCase(Locale.ROOT)));

        StandardEvaluationContext customContext =
                new StandardEvaluationContext(settings);

        customContext.setTypeConverter(
                new StandardTypeConverter(conversionService));

        parser.parseExpression("priority")
                .setValue(customContext, "high");

        System.out.println("priority=" + settings.getPriority());
        System.out.println("priority.type="
                + settings.getPriority().getClass().getName());
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SpelConversionDemo
~~~

Stdout lines printed by the program:

~~~text
enabled=true
flags[0]=false
flags.elementType=java.lang.Boolean
priority=HIGH
priority.type=demo.SpelConversionDemo$Priority
~~~

Maven may print its own logs depending on the environment; the above is the output from the `System.out.println` statements.

**Output explanation:**

- `enabled` is declared as Boolean; string "true" is converted to `Boolean.TRUE` before assignment.
- `flags[0]` is an element of `List<Boolean>`. SpEL uses the element type information to convert string "false" to Boolean instead of storing a string in the list.
- `priority` is declared as enum `Priority`. The custom converter normalizes the string and calls `Priority.valueOf(...)`.
- `StandardTypeConverter(conversionService)` connects the evaluation context to the configured conversion service. SpEL uses `TypeConverter` to execute the assignment.

If the custom converter receives a value that is not a valid enum name, `Priority.valueOf(...)` throws `IllegalArgumentException`; Spring/SpEL surfaces the failure as a conversion/evaluation error. Applications should translate errors into understandable messages without exposing stack traces.

## 5. Configuring a Custom TypeConverter for EvaluationContext

`EvaluationContext` allows replacing `TypeConverter` directly. Two common approaches exist.

Using the default `StandardTypeConverter`:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setTypeConverter(new StandardTypeConverter());
~~~

Using a `ConversionService` with registered converters:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(new PriorityConverter());

StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
~~~

The second approach separates converter registration/management from expression execution. The same conversion service can be shared across multiple expression contexts if the converters are stateless and thread-safe.

Notes:

- Configure the context before evaluating expressions.
- Do not build converters that depend on single-request state if the conversion service will be shared across threads.
- For custom converters, clearly define null, blank, locale, units, precision, and exceptions.
- Do not use converters for authorization or business validation.
- `TypeConverter` is a SpEL strategy. Other direct APIs can call `ConversionService.convert(...)` without an evaluation context.

## 6. SimpleEvaluationContext and SpEL Feature Restrictions

If an application lets users or administrators enter expressions, consider expression permissions carefully. `StandardEvaluationContext` is powerful and can enable many features: properties, methods, type references, constructors, bean resolution, and functions depending on configuration.

`SimpleEvaluationContext` is meant for cases needing a narrower feature set, especially data binding and property-based filtering. For example, needing only property reads:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

If property writes are needed:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

The builder can configure accessors, method resolution, or type converters within its supported scope. This context disables higher-risk features such as type references, constructors, and bean references in its default model. That reduces the expression surface users can exploit.

**Limitation to remember:** SimpleEvaluationContext is not an automatic filter for all business logic, nor does it replace authorization. If property writes are enabled, users can still modify properties permitted by the accessor. Configure root objects and accessors to expose only the necessary data.

## 7. Distinguishing SpEL Type Conversion from DataBinder and Spring MVC

SpEL, `DataBinder`, and Spring MVC can all use Spring's type conversion infrastructure, yet they solve different problems:

| Mechanism | Primary role | Example |
|---|---|---|
| `ConversionService` | Shared type conversion API | String to Integer, enum, or domain type |
| SpEL's `TypeConverter` | Converts values during expression evaluation | Assigning "false" to Boolean `flags[0]` |
| `DataBinder` | Binds property values into an object and collects errors | `age=abc` into a form with `Integer age` |
| `WebDataBinder` | Variant for web binding in Spring MVC | Binding `@ModelAttribute` form/query |
| `HttpMessageConverter` | Reads/writes HTTP bodies such as JSON | Jackson deserializes body into request DTO |
| Bean Validation | Validates data constraints | `@Min(1)`, `@NotBlank`, custom constraints |

`DataBinder` can receive the string "abc" for property Integer age, creating a `FieldError` if conversion fails. SpEL uses `Expression.setValue(...)` and `EvaluationContext.getTypeConverter()` to convert the value assigned in an expression. Sharing Spring converters does not mean `BindingResult` automatically appears when SpEL fails.

In Spring MVC, `@RequestBody` is usually read by an HTTP message converter (such as Jackson), while `@ModelAttribute` goes through data binding. Do not apply every `WebDataBinder` rule to JSON bodies or SpEL expressions.

## 8. Source Values, Target Types, and Generic-Aware Conversion

An important aspect of SpEL type conversion is that the system does not look solely at raw object types. When the target is a property with generic types, Spring can use `TypeDescriptor` to describe the full type.

Example:

~~~java
public class Example {
    private List<Boolean> flags = new ArrayList<>();

    public List<Boolean> getFlags() {
        return flags;
    }

    public void setFlags(List<Boolean> flags) {
        this.flags = flags;
    }
}
~~~

With expression `flags[0]`, the property/element descriptor identifies the target as Boolean. The string "false" is converted to Boolean on assignment.

This helps with `List<Boolean>`, `List<Integer>`, `Map<String, LocalDate>`, and nested properties whose types differ from the source. However, `TypeDescriptor` cannot infer every type in all situations. If a raw collection does not declare generics or metadata is lost, the converter may not know what type elements should convert to. In such cases, provide explicit descriptors or design objects with clear static types.

## 9. Conversion Errors and How to Handle Them

**No matching converter.** The target is a custom domain type, yet the conversion service has no registered converter. Check source type, target type, and register a `Converter`, `ConverterFactory`, or `GenericConverter`.

**Invalid data per converter.** For example, "very-high" is not a valid `Priority` enum name. The converter should report errors consistently; do not silently pick LOW.

**Confusing conversion errors with expression errors.** An expression can fail because a property does not exist, an index is out of bounds, a method cannot be resolved, or a converter fails. Inspect the exception type and context instead of catching a generic exception and ignoring it.

**Lost generic information.** Converting raw `List` does not tell the element types. Use `TypeDescriptor` when converting parameterized collections/maps.

**Using converters with side effects.** Converters should generally be pure, concise, and free of database/HTTP calls. If a converter mutates state or depends on requests, results become unpredictable and cause issues when the conversion service is shared.

**Using StandardEvaluationContext for untrusted expressions.** A full-featured context can open up broad read/write and method invocation rights. Choose SimpleEvaluationContext or design restricted expressions/APIs; do not rely solely on a custom converter.

**Confusing conversion with validation.** "0" converts to Integer successfully yet can still violate `@Min(1)`. Run validation after conversion according to business rules.

## 10. Recommended Tests

| Case | Expected outcome |
|---|---|
| Assign "true" to `Boolean enabled` | `enabled == Boolean.TRUE` |
| Assign "false" to `List<Boolean>` | Element is Boolean false, not String |
| Assign "high" with `String -> Priority` registered | `Priority.HIGH` |
| Assign invalid enum string | Expression fails; does not silently assign default |
| Target lacks matching converter | Conversion error clearly reported |
| Context uses read-only property access | Property writes are disallowed |
| Simple context used for expression needing type references | Feature restricted as designed |
| Collection without declared generics | Do not assume Spring always infers element type |

When checking results, compare the **runtime type** of the assigned value alongside its printed value. For example, `flags.get(0).getClass()` helps catch cases where code accidentally keeps a String instead of a Boolean.

## 11. Design Principles for Type Conversion in SpEL

1. Use only the level of `EvaluationContext` needed; prefer `SimpleEvaluationContext` when only restricted data binding/property access is required.
2. Define clearly typed root objects and expose only necessary properties.
3. Register only converters with clear inputs/outputs; handle empty values, locales, and errors consistently.
4. Reuse a shared `ConversionService` when converters are stateless; avoid configuring converters per request.
5. For generic collections/maps, preserve clear type metadata to convert elements accurately.
6. Distinguish type conversion, expression evaluation errors, and business validation.
7. Never let untrusted expressions access broad internal objects, methods, or application beans.
8. Test success cases, missing converters, invalid values, and restricted write permissions.

**Remember:** SpEL does not magically turn any value into any type. When an expression reads/writes a property requiring type conversion, SpEL delegates to `TypeConverter` in `EvaluationContext`; `StandardTypeConverter` connects to Spring Core's `ConversionService`, which holds default and application-registered converters. The choice of context, property access permissions, converters, and validation determines whether assignments are safe and business-accurate.

### References

- Spring Framework Reference 6.2 — Evaluation: `EvaluationContext`, `StandardEvaluationContext`, `SimpleEvaluationContext`, and type conversion.
- Spring Framework Reference 6.2 — Spring Type Conversion: `ConversionService`, `Converter` SPI, and `TypeDescriptor`.
- Spring Framework Javadoc — `EvaluationContext#getTypeConverter()`, `StandardEvaluationContext#setTypeConverter(...)`, `StandardTypeConverter`.
- Spring Framework Javadoc — `DefaultConversionService` and `ConversionService`.
