# Converting Collections or Maps According to Type Requirements

In Spring Expression Language (SpEL), an expression can read or update collection and Map values. When the source value and target type differ, Spring can use **TypeConverter** to convert the data. This mechanism relies on Spring's type conversion infrastructure, specifically **ConversionService**, and can leverage generic type information when provided by a property or TypeDescriptor.

An important point is that collection conversion is not just changing the container's type. An application may need to convert each element of a List, or convert both keys and values of a Map. The outcome depends on the target type known to SpEL, registered converters, and the ability to instantiate the target collection or Map.

## TypeConverter and ConversionService in SpEL

**TypeConverter** is the abstraction SpEL uses when it needs to convert a value to another type. In StandardEvaluationContext, the default converter is **StandardTypeConverter**, which integrates with Spring's conversion mechanism.

ConversionService provides built-in converters for many common types, such as String to Integer, Boolean, or enum; conversions between numeric types; and converting collections or Maps when sufficient source and target type information is available.

You can configure StandardEvaluationContext with a dedicated ConversionService:

~~~java
ConversionService conversionService =
        new DefaultConversionService();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
~~~

In the example, SpEL uses a StandardTypeConverter created from the ConversionService provided by the application. If the application needs conversion with custom rules, additional Converters or GenericConverters can be registered on a ConfigurableConversionService before attaching it to the context.

If there are no special requirements, StandardEvaluationContext's default converter usually handles common conversions. Create a dedicated conversion service only when the application needs to control or extend conversion rules.

## Converting a Collection According to Target Element Type

Suppose the source data is a List of numeric strings, while the target property is declared as List<Integer>:

~~~java
public class BatchSettings {
    private List<Integer> retryLimits;

    public List<Integer> getRetryLimits() {
        return retryLimits;
    }

    public void setRetryLimits(List<Integer> retryLimits) {
        this.retryLimits = retryLimits;
    }
}
~~~

SpEL can be used to assign a List<String> to this property:

~~~java
BatchSettings settings = new BatchSettings();

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("settings", settings);

ExpressionParser parser = new SpelExpressionParser();

List<String> source =
        List.of("2", "5", "8");

Expression expression =
        parser.parseExpression("#settings.retryLimits");

expression.setValue(context, source);
~~~

The target property has type **List<Integer>**. When assigning, SpEL obtains the property's type information and uses TypeConverter to convert the String elements into Integers if an appropriate converter exists. After assignment, the list in settings contains the integers 2, 5, and 8.

This is the benefit of generic-aware conversion: SpEL not only knows the target container is a List, but can also know the element type Integer from the Java property declaration.

## Converting an Element in a Generic-Typed Collection

Generic information is also useful when updating a specific element. Suppose the flags property is declared as List<Boolean>:

~~~java
public class FeatureSettings {
    private List<Boolean> flags =
            new ArrayList<>(List.of(false, false));

    public List<Boolean> getFlags() {
        return flags;
    }

    public void setFlags(List<Boolean> flags) {
        this.flags = flags;
    }
}
~~~

You can assign a string to an element:

~~~java
FeatureSettings settings = new FeatureSettings();

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("settings", settings);

ExpressionParser parser = new SpelExpressionParser();

Expression flagExpression =
        parser.parseExpression("#settings.flags[0]");

flagExpression.setValue(context, "true");
~~~

The flags property has element type Boolean. SpEL can use the property's generic metadata to convert the string **"true"** into Boolean true before writing to the element. Conversion depends on the active converter and accessor.

If a collection is declared only with a raw type such as List without element information, SpEL may not know the target type of each element. In that case, do not expect generic conversion to behave like List<Boolean> or List<Integer>.

## Converting Maps: Keys and Values

Map has two independent generic types: key type and value type. For example:

~~~java
public class RuntimeConfig {
    private Map<String, Integer> limits;

    public Map<String, Integer> getLimits() {
        return limits;
    }

    public void setLimits(Map<String, Integer> limits) {
        this.limits = limits;
    }
}
~~~

If the source is a Map<String, String>, it can be assigned to a Map<String, Integer> property:

~~~java
RuntimeConfig config = new RuntimeConfig();

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("config", config);

Map<String, String> source = Map.of(
        "connectTimeout", "10",
        "readTimeout", "30");

ExpressionParser parser = new SpelExpressionParser();

Expression limitsExpression =
        parser.parseExpression("#config.limits");

limitsExpression.setValue(context, source);
~~~

When property metadata is fully provided, ConversionService can convert values from String to Integer while keeping String keys. The result has type Map<String, Integer>.

If both keys and values need conversion, such as Map<String, String> to Map<Integer, Boolean>, converters must be capable of converting each key and each value to its target type. Do not assume every type pair has a default converter.

## TypeDescriptor and Generic Metadata

Java generics undergo type erasure at runtime, but Spring has **TypeDescriptor** to preserve and carry richer type information, including collection element types and Map key/value types when metadata is available.

For example, you can describe the target type of a List<Integer> using TypeDescriptor:

~~~java
TypeDescriptor sourceType =
        TypeDescriptor.forObject(source);

TypeDescriptor targetType =
        TypeDescriptor.collection(
                List.class,
                TypeDescriptor.valueOf(Integer.class));

@SuppressWarnings("unchecked")
List<Integer> converted =
        (List<Integer>) conversionService.convert(
                source,
                sourceType,
                targetType);
~~~

This snippet demonstrates ConversionService directly: the source type is inferred from the actual object; the target type describes a List with Integer elements. ConversionService uses that information to convert each element if a matching converter exists.

For Map, both generic types can be described:

~~~java
TypeDescriptor mapTargetType =
        TypeDescriptor.map(
                Map.class,
                TypeDescriptor.valueOf(String.class),
                TypeDescriptor.valueOf(Integer.class));
~~~

This TypeDescriptor describes a Map with String keys and Integer values. You can use the convert overload accepting source TypeDescriptor and target TypeDescriptor to request conversion according to that type structure.

In SpEL, generic information usually comes from the property descriptor, field, or collection position being updated by the expression. If an application only requests the result via **getValue(context, List.class)**, the target type is merely raw List; the Class<List> signature does not carry generic element types like List<Integer>. When explicit generic conversion is needed, use a property with a generic declaration, TypeDescriptor, or perform conversion directly via ConversionService.

## Converting Collection and Projection Results

Selection and projection are SpEL collection operations:

- **Selection .?[condition]** filters elements matching a condition.
- **Projection .![expression]** computes a value for each element and collects the results.

For example, extracting names from Products:

~~~java
Expression expression =
        parser.parseExpression("#products.![name]");

List<?> names =
        expression.getValue(context, List.class);
~~~

Projection produces a result List from the name values. If name is String, the resulting elements are String. However, requesting the **List.class** type only specifies that the container is a List, without declaring the generic element type in the Java signature.

If you need to convert projection results to List<Integer> or another element type, explicitly specify the target type and use ConversionService with an appropriate TypeDescriptor, or assign the result to a property with the corresponding generic declaration. Do not rely on a raw Class to infer that all elements have been converted.

## Converting Collections Between Container Types

ConversionService can support converting between different collection kinds if matching converters exist and the target type can be instantiated. For example, source data might be a Set<String> while the target property is a List<Integer>.

~~~java
public class ImportSettings {
    private List<Integer> ids;

    public List<Integer> getIds() {
        return ids;
    }

    public void setIds(List<Integer> ids) {
        this.ids = ids;
    }
}
~~~

~~~java
ImportSettings settings = new ImportSettings();

context.setVariable("settings", settings);

Set<String> source = new LinkedHashSet<>(
        List.of("101", "102", "103"));

parser.parseExpression("#settings.ids")
        .setValue(context, source);
~~~

If the required converters are available, SpEL can convert the container and each element according to the target property type. Element ordering in the resulting collection depends on the created container type and the iteration order of the source. If ordering is a business requirement, choose suitable source/target structures and verify the behavior of the converter used.

Not every collection implementation can be created or converted automatically. A specialized target type, read-only collection, or collection lacking a suitable constructor may require a custom converter or conversion logic in Java.

## Registering Custom Converters

When a business data type is not supported by default converters, a custom Converter can be registered:

~~~java
public class RegionCode {
    private final String value;

    public RegionCode(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        RegionCode.class,
        RegionCode::new);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
~~~

After registration, a target property of type RegionCode can accept String data if SpEL performs conversion via this context. For a collection with RegionCode elements, the String-to-RegionCode converter can be applied to each element when the target type's generic metadata is provided.

If conversion depends on additional context beyond the source value, such as locale, tenant, or runtime configuration, consider an appropriate **ConverterFactory**, **GenericConverter**, or **ConditionalGenericConverter**. These abstractions allow describing more complex conversions than a simple one-source-one-target converter.

Converters should have a clear contract, handle invalid inputs consistently, and avoid side effects. Type conversion is often invoked in many places across an application; a converter should never silently write data or access external resources.

## Using ConversionService Directly When Fine-Grained Control Is Needed

Not every conversion belongs inside a SpEL expression. If logic requires converting complex collections, inspecting per-element errors, or deciding how to handle invalid elements, you can call ConversionService in Java:

~~~java
TypeDescriptor sourceDescriptor =
        TypeDescriptor.forObject(source);

TypeDescriptor targetDescriptor =
        TypeDescriptor.map(
                Map.class,
                TypeDescriptor.valueOf(String.class),
                TypeDescriptor.valueOf(Integer.class));

Object converted = conversionService.convert(
        source,
        sourceDescriptor,
        targetDescriptor);
~~~

This approach allows specifying target key and value types explicitly. The application can also catch conversion errors at a clear boundary and return a business-appropriate message.

SpEL is well-suited for short expressions at configuration or integration points. If conversion involves multiple steps, detailed logging, skipping certain elements, or aggregating errors, Java is usually easier to control.

## Conversion Errors and How to Diagnose Them

An expression can parse successfully yet fail during evaluation because a collection, key, value, or element cannot be converted. Common causes:

- No Converter exists for the source and target types.
- Source string has an invalid format, for example **"abc"** cannot be converted to Integer.
- Target property has a generic type different from the actual data.
- Map key or value cannot be converted to the target type.
- Target collection cannot be instantiated or does not support the required operation.
- Custom converter throws an exception while processing data.

You can separate parse errors from evaluation errors:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("#settings.retryLimits");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    expression.setValue(context, List.of("2", "5", "invalid"));
} catch (EvaluationException ex) {
    throw new IllegalArgumentException(
            "Cannot convert the supplied collection", ex);
}
~~~

ParseException indicates the expression string has invalid syntax. EvaluationException indicates the expression cannot be executed against the current context or data; conversion errors can appear within this group, often accompanied by a detailed cause from ConversionService.

When handling errors, identify which element or entry is invalid and what target type was requested. Do not replace every conversion error with an empty collection, as that can mask invalid input data.

## Null in Collections and Maps

A Collection or Map can contain null elements, null keys, or null values depending on the implementation. ConversionService cannot convert a null value into every target type in the same way; the result depends on the converter and the null rules of the target type.

For example, a List<String> containing null elements when converted to List<Integer> needs an explicit policy: preserve null if the target type allows it, reject the data, or replace with a default according to business rules. For Maps, inspect null keys and null values separately.

If null is not allowed, validate the source before invoking SpEL or ConversionService. If null is valid, check the actual converter and target collection instead of assuming conversion will filter out null elements on its own.

## Limitations of SimpleEvaluationContext

**SimpleEvaluationContext** provides a subset of SpEL capabilities intended for data binding and allows the application to control property reading/writing. It does not provide the full feature set of StandardEvaluationContext, such as type references, constructor invocation, and bean references.

If a use case requires converting a collection or Map during property assignment, ensure the context has an appropriate TypeConverter and property accessor supporting the operation. With StandardEvaluationContext, you can explicitly configure StandardTypeConverter as in the examples above. With SimpleEvaluationContext, use its builder and the capabilities supported by the Spring version in use; do not assume all features of StandardEvaluationContext are available.

Read-only data binding also does not mean returned collections are automatically immutable. Type conversion policy and property write permissions are two separate concerns; source and result collections retain mutability according to their Java implementations.

## Best Practices

- Declare collection and Map properties with specific generics such as **List<Integer>** or **Map<String, Boolean>** when element types matter.
- Use TypeDescriptor when you need to explicitly describe target element, key, and value types.
- Use StandardTypeConverter backed by an appropriate ConversionService for expressions requiring conversion.
- Register custom Converters for unsupported business types.
- Do not expect **getValue(context, List.class)** to carry generic element information on its own.
- Validate source data, nulls, and formats before converting.
- If detailed per-error control or multi-step rules are needed, perform conversion in Java.
- Do not treat a read-only EvaluationContext as a mechanism that makes collections immutable.

## Conclusion

SpEL uses **TypeConverter** to convert values to the types required by an expression or target location. StandardEvaluationContext integrates StandardTypeConverter by default; applications can supply a custom ConversionService and register additional converters. For collections and Maps, generic information helps convert individual elements, keys, or values when the target type is known through property metadata or TypeDescriptor.

To convert List<String> to List<Integer> or Map<String, String> to Map<String, Integer>, declare the target type explicitly and ensure suitable converters exist. Do not rely on raw List.class to infer element types. When conversions are complex or require detailed error handling, use ConversionService directly in Java to control inputs, target types, and results.
