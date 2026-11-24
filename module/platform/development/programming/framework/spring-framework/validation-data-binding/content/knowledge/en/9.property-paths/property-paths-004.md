# Element Type Conversion Based on Generic Information in Spring Data Binding

When a request sends the string `"7"` to populate an element of `List<Integer>`, Spring needs to know the **type of each element** is `Integer`, rather than only knowing the whole property is a `List`. Similarly, with `Map<String, BigDecimal>`, Spring needs to distinguish the `String` key type and `BigDecimal` value type so it can convert input `"19.50"` into a real decimal number.

Spring Framework uses the declared type metadata of a JavaBean property (including generic types), property path access, and `ConversionService` to perform type conversion. The core model is: **the path identifies the target element; generic metadata specifies the target type; converters perform the conversion; `BindingResult` records errors if conversion fails**.

## 1. Reading the exact element type: `List<Integer>` vs. `List<String>`

Consider the JavaBean:

~~~java
public class OrderForm {
    private List<Integer> quantities = new ArrayList<>();
    private Map<String, BigDecimal> prices = new LinkedHashMap<>();

    public List<Integer> getQuantities() {
        return quantities;
    }

    public void setQuantities(List<Integer> quantities) {
        this.quantities = quantities;
    }

    public Map<String, BigDecimal> getPrices() {
        return prices;
    }

    public void setPrices(Map<String, BigDecimal> prices) {
        this.prices = prices;
    }
}
~~~

The snippet above is an illustrative declaration; it requires imports for `java.util.List`, `ArrayList`, `Map`, `LinkedHashMap`, and `java.math.BigDecimal` when used in an application.

- `quantities` has **container type** `List` and **element type** `Integer`.
- `prices` has **container type** `Map`, **key type** `String`, and **value type** `BigDecimal`.
- Values from forms and query strings normally arrive as strings. If binding succeeds, `quantities.get(0)` must be an `Integer`, and `prices.get("book")` must be a `BigDecimal`.
- The generics `<Integer>` and `<String, BigDecimal>` are **declared type metadata**, not characters inside the field name sent by the client.

Java has **type erasure**, meaning `someList.getClass()` alone is insufficient to know the `Integer` type argument. However, generic metadata on **fields, getters, setters, or typed parameters** can still be inspected via reflection. Spring uses this JavaBean/property context to resolve the element type. Passing a raw `List` without a metadata-bearing target may prevent Spring from determining the desired element type.

## 2. Property paths pinpoint which element to bind

The property path notation of `BeanWrapper`/`DataBinder` combines property names with dots, indices, and map keys:

| Path | Target pointed to | Expected target type |
| --- | --- | --- |
| `quantities` | The entire `List<Integer>` | `List<Integer>` |
| `quantities[0]` | First element of `quantities` | `Integer` |
| `quantities[1]` | Second element | `Integer` |
| `prices[book]` | Value for key `"book"` in `prices` | `BigDecimal` |
| `lines[0].quantity` | Property `quantity` of the first element in `List<OrderLine>` | Declared type of `quantity`, e.g., `Integer` |
| `limits[42]` | Map entry with key `42` | Key and value types based on `Map<K,V>` generics |

The path `quantities[1]` uses a **zero-based index**, so `[1]` is the second element. For a map, `[...]` is interpreted as a key. For example, `prices[book]` targets key `book`, not a JavaBean property named `book`.

Spring solves two distinct tasks: locating the target element via the property path, then converting the source value to the resolved **element/value type**. For example:

~~~text
property path: quantities[1]
source value : "12" (String)
container    : List<Integer>
element type : Integer
conversion   : String -> Integer
result       : quantities.get(1) == Integer.valueOf(12)
~~~

With `lines[0].quantity`, the binder accesses the first element and then its `quantity` property. For writing to succeed, the objects and containing structures must be accessible or creatable according to configuration. `DataBinder` can auto-grow certain nested paths/collections when enabled, though this has limits and should not be treated as a mechanism to construct arbitrary unbounded object graphs.

## 3. Generic resolution flow: from JavaBean to `TypeDescriptor`

Conceptual processing flow:

~~~text
JavaBean:
  List<Integer> quantities
  Map<String, BigDecimal> prices
            |
            v
Reflection / ResolvableType / property metadata
            |
            v
BeanWrapper + property path
  quantities[1] -> Integer
  prices[book]  -> BigDecimal
            |
            v
TypeDescriptor (target type and generic context)
            |
            v
ConversionService / converters
  "12"    -> Integer(12)
  "19.50" -> BigDecimal("19.50")
            |
            v
Assign to JavaBean list / map
  or record conversion error in BindingResult
~~~

Each concept plays a distinct role:

- `BeanWrapper` / `BeanWrapperImpl` understands **JavaBean properties** and nested, indexed, and mapped paths; `DataBinder` uses this property access mechanism during property binding.
- `ResolvableType` is an abstraction representing and querying Java type metadata, including generic type arguments.
- `TypeDescriptor` represents a target type with context, such as `List<Integer>` containing both the collection type and element type; for maps it also tracks key/value types. Useful APIs include `getElementTypeDescriptor()`, `getMapKeyTypeDescriptor()`, and `getMapValueTypeDescriptor()`.
- `ConversionService` selects an appropriate converter based on source and target types. `DefaultConversionService` provides built-in conversions across strings, numbers, enums, collections, and maps.
- `GenericConverter` receives both `sourceType` and `targetType` as `TypeDescriptor`; this allows container-level converters to convert **each element** using metadata rather than seeing only `List.class`.

**Do not confuse generic metadata with runtime validation.** `List<Integer>` allows converting `"12"` into `Integer`, but does not assert that 12 is valid by business rules. Min/max bounds, element counts, or uniqueness rules must be checked by separate validation.

## 4. Runnable Java 17+ example: binding `List<Integer>` and `Map<String, BigDecimal>`

The example below uses **Spring Framework 6.2.x** and needs no HTTP server. It pre-populates the list with two elements to focus on **type conversion** rather than collection auto-growth. The complete code resides at `src/main/java/GenericElementBindingDemo.java` in a Maven project using `spring-context`.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class GenericElementBindingDemo {

    public static class OrderForm {
        private List<Integer> quantities =
                new ArrayList<>(List.of(0, 0));

        private Map<String, BigDecimal> prices =
                new LinkedHashMap<>();

        public List<Integer> getQuantities() {
            return quantities;
        }

        public void setQuantities(List<Integer> quantities) {
            this.quantities = quantities;
        }

        public Map<String, BigDecimal> getPrices() {
            return prices;
        }

        public void setPrices(Map<String, BigDecimal> prices) {
            this.prices = prices;
        }
    }

    public static void main(String[] args) {
        OrderForm form = new OrderForm();

        // Inspect JavaBean metadata before binding.
        BeanWrapper wrapper = new BeanWrapperImpl(form);
        TypeDescriptor quantityDescriptor =
                wrapper.getPropertyTypeDescriptor("quantities");
        TypeDescriptor priceDescriptor =
                wrapper.getPropertyTypeDescriptor("prices");

        System.out.println("elementType="
                + quantityDescriptor.getElementTypeDescriptor()
                        .getType().getSimpleName());
        System.out.println("mapValueType="
                + priceDescriptor.getMapValueTypeDescriptor()
                        .getType().getSimpleName());

        DataBinder binder = new DataBinder(form, "orderForm");
        binder.setConversionService(new DefaultConversionService());

        // Accept only the fields explicitly permitted by the demo.
        binder.setAllowedFields(
                "quantities[0]", "quantities[1]", "prices[book]");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("quantities[0]", "7");
        input.add("quantities[1]", "12");
        input.add("prices[book]", "19.50");

        binder.bind(input);

        BindingResult result = binder.getBindingResult();
        System.out.println("errors=" + result.getErrorCount());
        System.out.println("quantities=" + form.getQuantities());
        System.out.println("price=" + form.getPrices().get("book"));
        System.out.println("firstRuntimeType="
                + form.getQuantities().get(0).getClass().getSimpleName());
        System.out.println("priceRuntimeType="
                + form.getPrices().get("book").getClass().getSimpleName());

        // A value that cannot be converted to Integer.
        DataBinder invalidBinder =
                new DataBinder(new OrderForm(), "orderForm");
        invalidBinder.setConversionService(new DefaultConversionService());
        invalidBinder.setAllowedFields("quantities[0]");

        MutablePropertyValues invalid = new MutablePropertyValues();
        invalid.add("quantities[0]", "not-a-number");
        invalidBinder.bind(invalid);

        FieldError fieldError = invalidBinder.getBindingResult()
                .getFieldError("quantities[0]");
        System.out.println("invalidHasError="
                + (fieldError != null));
        System.out.println("invalidBindingFailure="
                + (fieldError != null && fieldError.isBindingFailure()));
    }
}
~~~

With Spring Framework 6.2.x (using default converters), expected stdout output:

~~~text
elementType=Integer
mapValueType=BigDecimal
errors=0
quantities=[7, 12]
price=19.50
firstRuntimeType=Integer
priceRuntimeType=BigDecimal
invalidHasError=true
invalidBindingFailure=true
~~~

To run with Maven, use Java 17+ and declare a compatible dependency in `pom.xml` (for example Spring 6.2.x). A minimal illustrative configuration:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>generic-element-binding-demo</artifactId>
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
        </plugins>
    </build>
</project>
~~~

After creating the Java file and `pom.xml`, run from the project directory:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=GenericElementBindingDemo
~~~

The command requires Maven, JDK 17+, and access to download dependencies if not yet cached. Because Spring is an external dependency, `javac GenericElementBindingDemo.java` lacks the classpath needed to compile standalone.

### Step-by-step analysis of the example

1. `BeanWrapperImpl` reads metadata for `quantities`; `getElementTypeDescriptor().getType()` returns `Integer.class`. For `prices`, `getMapValueTypeDescriptor()` returns `BigDecimal.class`. This information comes from the **property signature**, not inferred from existing elements.
2. `input` contains purely string values, similar to HTTP form data. `binder.bind(input)` processes each property path and locates the target JavaBean element.
3. Paths `quantities[0]` and `quantities[1]` lead to elements of type `Integer`, so Spring applies the string-to-integer converter. After binding, the list is `[7, 12]` with actual runtime element type `Integer`.
4. Path `prices[book]` leads to a value of type `BigDecimal`; `"19.50"` becomes `BigDecimal` (printed formatting preserves the decimal scale `19.50`).
5. The second binder receives `"not-a-number"` for an `Integer` element and cannot convert it; `BindingResult` records a `FieldError` and `isBindingFailure()` reports `true`. The example checks booleans so it does not depend on exception message text that can vary across configurations.

`setAllowedFields(...)` in the example restricts which properties are authorized for binding. In a web application, design intentional DTOs and allowlists; generic types **do not protect** against mass assignment or unwanted property paths.

## 5. Why must `TypeDescriptor` be supplied when converting a collection manually?

When calling only:

~~~java
conversionService.convert(source, List.class);
~~~

Java passes only `List.class` as the target type. It **cannot represent `List<Integer>`** because generic parameters are erased on `Class` objects. Consequently, the result is not guaranteed to convert each string into `Integer` as intended. This is the major difference between context-free conversion and binding onto a property with declared generics.

With `DefaultConversionService`, you can explicitly describe both source and target types using `TypeDescriptor`:

~~~java
DefaultConversionService service = new DefaultConversionService();

List<String> source = List.of("3", "8");
TypeDescriptor from = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(String.class));
TypeDescriptor to = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));

Object converted = service.convert(source, from, to);
List<?> result = (List<?>) converted;

System.out.println(result);                                  // [3, 8]
System.out.println(result.get(0).getClass().getSimpleName()); // Integer
~~~

This snippet can be placed in a `main` method of a Java application with `spring-core` on the classpath and imports for `java.util.List`, `TypeDescriptor`, and `DefaultConversionService`. When both descriptors specify the element type, `DefaultConversionService` pairs the collection converter with the `String -> Integer` element converter. The runtime result type is confirmed via `getClass().getSimpleName()`.

If you want to convert a collection containing custom objects, add a converter for the element type and ensure it is registered on the service in use. Never assume every domain type can automatically convert from String.

## 6. Generic metadata in List, Map, Array, and nested paths

### `List<T>` and `Set<T>`

With `List<Integer>` or `Set<LocalDate>`, `<T>` tells Spring the element type. If `String -> T` has a suitable converter/formatter, Spring can convert elements. Lists support indexed paths like `items[0]`; Sets should generally not be assumed to have stable indices. When a form sends multiple values for one property, the source data shape (single string, string array, or collection) and configured converters govern how the entire collection is converted.

Example list with enum elements:

~~~java
enum Priority { LOW, MEDIUM, HIGH }

public class FilterForm {
    private List<Priority> priorities = new ArrayList<>();

    public List<Priority> getPriorities() { return priorities; }
    public void setPriorities(List<Priority> priorities) {
        this.priorities = priorities;
    }
}
~~~

With path `priorities[0]` and value `"HIGH"`, the default enum converter can assign `Priority.HIGH`. Strings not matching an enum constant can produce conversion errors. To support case-insensitive input or custom display names, register an appropriate converter/formatter rather than silently altering data.

### `Map<K,V>`

With `Map<String, BigDecimal>`, `prices[book]` needs metadata for the **value type**. With `Map<Long, Integer>`, a mapped property also carries metadata for the **key type**. To convert `"42"` to `Long 42L` and value `"5"` to `Integer 5`, the service needs both appropriate converters.

~~~java
public class LimitsForm {
    private Map<Long, Integer> limits = new LinkedHashMap<>();

    public Map<Long, Integer> getLimits() { return limits; }
    public void setLimits(Map<Long, Integer> limits) {
        this.limits = limits;
    }
}
~~~

In a binder context supporting key conversion, `limits[42]` targets numeric key `42L`. Note that map key conversion rules become more involved when using domain objects as keys; do not rely on a domain object's `toString()` without defining explicit converters.

### Array

`Integer[] quantities` declares its component type directly via the Java array type (unlike the generic parameter of `List<Integer>`). Spring can use the corresponding element converter when binding arrays. Expanding or writing indices beyond bounds must be handled according to array semantics and binder configuration.

### Nested object

With `List<OrderLine> lines` where `OrderLine.quantity` has type `Integer`, the path `lines[0].quantity` uses metadata at two levels: list element type `OrderLine` and nested JavaBean property `Integer`. It differs from `lines[0]`: one path asks to set **a numeric field**; the other asks to convert **a string into an entire OrderLine object**, typically requiring a dedicated converter.

A nested path binds only when the path is valid and required components can be accessed/created. If the collection is empty, define a clear auto-grow policy and element limit; if the child object is abstract, an interface, or has special constructors, Spring may be unable to instantiate it automatically.

## 7. Configuring custom converters for application element types

Suppose a list declares `List<Sku> skus`, where `Sku` is a business type. Spring does not inherently know product-code normalization rules, so you can register a `String -> Sku` converter:

~~~java
record Sku(String value) {}

final class StringToSkuConverter
        implements org.springframework.core.convert.converter.Converter<String, Sku> {

    @Override
    public Sku convert(String source) {
        String normalized = source.trim().toUpperCase(java.util.Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        return new Sku(normalized);
    }
}
~~~

This is a Java 17+ project snippet, not a standalone main program. Where you configure the conversion service:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToSkuConverter());
binder.setConversionService(service);
~~~

If `binder` binds onto a `List<Sku>` property and the path reaches an element (such as `skus[0]`), Spring can reuse that converter to convert each string into `Sku`. With the code above, input `" ab-12 "` produces `new Sku("AB-12")`.

In Spring MVC, the common approach is registering the converter via `WebMvcConfigurer.addFormatters(FormatterRegistry registry)` (or equivalent configuration) so the MVC layer uses it:

~~~java
@Configuration
class WebConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToSkuConverter());
    }
}
~~~

This configuration snippet needs imports for `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`, and `org.springframework.format.FormatterRegistry`, and `StringToSkuConverter` must be visible in the project. When a Spring Boot/MVC application already has a framework-configured conversion service, **add your converter to the appropriate registry** rather than replacing the entire service and losing default converters.

For dates/times, currencies, and locale-sensitive numbers, a `Formatter` or formatter-capable conversion service can be more appropriate than a string-only converter. Generic metadata determines the element type; **how string representations are parsed** also depends on converters/formatters, locale, and configuration.

## 8. Error output when an element fails type conversion

If the value for `quantities[1]` is `"abc"` while the element type is `Integer`, `DataBinder` typically creates a `FieldError` in `BindingResult`. You can inspect it without letting a technical exception leak to the UI:

~~~java
BindingResult bindingResult = binder.getBindingResult();

if (bindingResult.hasErrors()) {
    for (FieldError error : bindingResult.getFieldErrors()) {
        System.out.println(error.getField());            // e.g. quantities[1]
        System.out.println(error.getCode());             // Usually: typeMismatch
        System.out.println(error.isBindingFailure());    // true when binding failed
    }
}
~~~

This snippet illustrates code after `binder.bind(...)` and requires importing `BindingResult` and `FieldError`. The code can be `typeMismatch` along with more specific codes incorporating the property path and object name, depending on `MessageCodesResolver`. For example, a resource bundle might define:

~~~properties
typeMismatch.orderForm.quantities[1]=The second quantity must be a valid integer.
typeMismatch.quantities=Quantity value has an invalid format.
typeMismatch=Value cannot be converted to the required type.
~~~

To pick the appropriate message, use `MessageSource.getMessage(fieldError, locale)` and inspect the `getCodes()` candidates. When field names include indices, resolved detailed codes may differ by resolver; inspect actual codes instead of assuming one key is always prioritized in every configuration.

**Type conversion and validation are two separate steps:**

- `quantities[1]="abc"`: cannot convert to `Integer`, binding error.
- `quantities[1]="-3"`: converts to `Integer -3` successfully, yet may violate `@Positive` or business rules.
- `quantities[1]="3"`: converts cleanly, though other defined constraints still need checking.

Generic types do not automatically trigger `@Positive` or Bean Validation. If using container element constraints such as `List<@Positive Integer>`, you need a compatible Jakarta Bean Validation provider, validation triggered in the appropriate flow, and properly configured rules.

A conversion error on one element can leave that specific field unset as expected; the state of other elements depends on how the binder processes the remaining property values. Do not assume the entire collection rolls back atomically when one element fails. In a web flow, proceed with business logic only after checking the entire `BindingResult.hasErrors()`.

## 9. Checklist when generic metadata is not resolved

If a list ends up holding `String` values even though you expected `Integer`, check in order:

1. **JavaBean signature:** Is the property genuinely `List<Integer>`, or declared as raw `List`, `List<?>`, or `Object`? Do the getter and setter have matching types?
2. **Property path:** `quantities[0]` targets an Integer element in the list, while `quantities` targets the entire container; conversion paths may differ.
3. **Metadata visible to Spring:** Call `BeanWrapper.getPropertyTypeDescriptor("quantities")` and `getElementTypeDescriptor()` to see whether generics are resolved. `TypeDescriptor` can return `null` where element types cannot be determined.
4. **ConversionService:** Has the `DataBinder` in use been given a `ConversionService`? Does the MVC/Boot app have its own registry? Was a converter added for the domain type?
5. **Source value:** Did the request send a String, `String[]`, JSON, or a List? HTTP converter/Jackson contexts differ from `DataBinder` property binding.
6. **Recorded errors:** Check `getFieldErrors()`, `getCodes()`, and `isBindingFailure()`; do not rely solely on exception message wording.
7. **Collection structure:** Is the list/map writable? Is it immutable? Does the index exceed auto-grow limits, or is the key missing a converter?
8. **Binding scope:** Is the field in `allowedFields`? Was it suppressed by mass-assignment protection?

Raw types make for an easy mistake:

~~~java
// Lacks element information: avoid using in form models.
private List quantities;

// Carries information for Spring to resolve element type.
private List<Integer> quantities;
~~~

In addition, when converting programmatically, supplying only `List.class` loses the target element type. Use `TypeDescriptor.collection(...)`, or reflect the `TypeDescriptor` from a property that already declares generics.

### Checking nested/indexed paths safely

When binding paths such as `lines[5000].quantity`, client input can cause the binder to create many elements. Spring provides a configurable auto-grow collection limit and field allow/disallow controls. For user-controlled data, limit input size, element counts, and bindable fields. Never raise limits indefinitely just to silence errors. Prefer request DTOs with explicit structure and bounds.

For maps, if keys contain special characters, property path syntax and escaping rules should be tested; do not interpolate arbitrary raw text inside `[...]` without verifying valid syntax and binding allow policies.

## 10. Practical scenarios and verifying results

| Input | Target declaration | Expectation |
| --- | --- | --- |
| `quantities[0]="7"` | `List<Integer>` | Element 0 is `Integer 7` |
| `prices[book]="19.50"` | `Map<String,BigDecimal>` | Entry `"book"` holds `BigDecimal("19.50")` |
| `quantities[1]="abc"` | `List<Integer>` | Produces conversion `FieldError`, typically `typeMismatch` |
| `quantities[1]="-3"` | `List<Integer>` | Conversion succeeds; separate validation can reject the value |
| `priorities[0]="HIGH"` | `List<Priority>` | Matching enum converter produces `Priority.HIGH` |
| `skus[0]=" ab-12 "` | `List<Sku>` and `StringToSkuConverter` | Creates element `Sku("AB-12")` |
| Convert `List<String>` to `List<Integer>` without a JavaBean | `TypeDescriptor.collection(List.class, Integer)` | ConversionService knows element type when descriptors are complete |
| Raw `List` property | No element type declared | No guarantee of conversion to desired element type |

An automated test should assert the **runtime type of elements** rather than merely comparing `toString()` strings. For instance, `List.of("7","12").toString()` and `List.of(7,12).toString()` both look like `[7, 12]`, yet their data types are completely different. Use `getClass()` or `instanceof` assertions on elements, and also inspect `BindingResult`. Separating tests for generic metadata, successful conversion, failed conversion, and validation pinpoints exactly which step fails.

## 11. Common misconceptions

1. **"Because List is generic, the JVM converts String to Integer automatically."** The JVM does not convert value types automatically; Spring needs target metadata and an appropriate converter.
2. **"Just call `convert(value, List.class)`."** `Class<List>` does not carry `<Integer>`; use `TypeDescriptor` or bind onto a JavaBean with a generic signature.
3. **"Property `quantities` and `quantities[0]` are the same."** One is the whole container, the other is an element; metadata and conversion paths can differ.
4. **"Every property path auto-grows."** Auto-grow has preconditions and limits and cannot instantiate arbitrary object or collection types.
5. **"Successful type conversion means valid data."** Validation must run separately; `Integer -3` can still violate `@Positive`.
6. **"Conversion errors automatically throw to the screen."** In property binding via `DataBinder`, errors are normally stored in `BindingResult`; inspect them and present controlled messages.
7. **"A field error code is just one string."** `FieldError.getCodes()` holds candidate codes for resolution; `getCode()` is usually the most specific or primary code.
8. **"Generics are enough to stop dangerous field binding."** Generics govern data types, whereas binding allowlists/DTOs/validation govern scope and rules.
9. **"All date/time and number strings parse identically in every locale."** Formatters, locales, and Spring MVC configuration can affect parsing.
10. **"Any JSON goes through `DataBinder` just like a form."** `@RequestBody` is typically deserialized via `HttpMessageConverter`/Jackson; generic types still matter, yet the conversion path and exceptions differ.

## 12. Summary of project usage

When defining forms/DTOs with collections or maps, keep **concrete generic declarations**, expose valid property paths to Spring, configure `ConversionService`/`FormatterRegistry` for supported element types, and inspect `BindingResult`. For programmatic collection conversion, pass a `TypeDescriptor` specifying concrete element/key/value types. Only after conversion succeeds should appropriate validation constraints be evaluated.

References: [Spring Framework 6.2 – Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html), [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html), [TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/TypeDescriptor.html).
