# TypeConverter During SpEL Evaluation

Spring Expression Language (SpEL) can convert values between data types when evaluating expressions. The conversion mechanism is provided through the **TypeConverter** of the EvaluationContext. This allows values read from properties, variables, or expressions to be converted to the type required by a property, method, constructor, or caller.

TypeConverter is part of the evaluation process, not a syntax parsing step. The parser creates an Expression; when the Expression runs with an EvaluationContext, SpEL components request conversion only if an operation requires a specific target type.

## 1. Role of TypeConverter

EvaluationContext provides a TypeConverter via the `getTypeConverter()` method. TypeConverter determines whether a value can be converted to a target type and performs that conversion.

The main contract of the interface includes:

    boolean canConvert(
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );

    Object convertValue(
            Object value,
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );

TypeDescriptor describes a data type along with related metadata. It can carry additional information such as collection element types, map key/value types, or annotations on a property. This helps conversion better understand the target type rather than relying solely on a simple runtime class.

SpEL can use TypeConverter in situations such as:

- Assigning a value to a property with a specific type.
- Converting arguments for a method or constructor when the signature requires a different type.
- Converting an expression result to a requested type via `getValue(context, TargetType.class)`.

TypeConverter only converts values according to configured rules. It does not determine property access permissions, method invocation permissions, or application business rules.

## 2. TypeConverter Belongs to EvaluationContext

Each time an expression is evaluated, SpEL uses the services provided by EvaluationContext. Therefore, two different contexts can use different converters and produce different conversion results for the same expression.

StandardEvaluationContext provides StandardTypeConverter by default. This converter relies on Spring ConversionService to handle common conversions.

For example:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    ExpressionParser parser = new SpelExpressionParser();

    Integer count = parser.parseExpression("'42'")
            .getValue(context, Integer.class);

The expression evaluates to the string `'42'`. When an Integer result is requested, SpEL uses the context's TypeConverter to convert the value to Integer if the conversion service supports it.

You can retrieve the current converter to inspect or configure the context:

    TypeConverter converter = context.getTypeConverter();

If a separate conversion policy is needed for a use case, create a context with the appropriate TypeConverter instead of modifying a shared converter beyond the required scope.

## 3. Conversion During Property Assignment

When an expression assigns a value to a property, the type of the source value may differ from the target property type. SpEL uses the EvaluationContext's TypeConverter to convert if a suitable converter exists.

For example, an object with an Integer `quantity` property:

    public class OrderForm {
        private Integer quantity;

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

You can assign a numeric string:

    OrderForm form = new OrderForm();

    StandardEvaluationContext context =
            new StandardEvaluationContext(form);

    ExpressionParser parser = new SpelExpressionParser();
    parser.parseExpression("quantity = '12'")
            .getValue(context);

If the converter supports String to Integer, the `quantity` property receives the Integer value 12. Assignment also depends on whether the PropertyAccessor allows writing that property; TypeConverter does not grant write permission.

You can also use the `setValue` API:

    parser.parseExpression("quantity")
            .setValue(context, "25");

SpEL converts the value to the property type when needed. If the string does not represent a valid Integer, conversion fails and the assignment operation does not complete as expected. Handle conversion errors at the calling layer instead of assuming the value was written.

## 4. Argument Conversion When Calling Methods

A method has specific parameter signatures. When an expression calls a method with arguments of different types, method resolution and TypeConverter can work together to find and invoke an appropriate method.

For example:

    public class ShippingService {
        public String estimate(Integer weight) {
            return "weight=" + weight;
        }
    }

    context.setVariable("shippingService", new ShippingService());
    context.setVariable("rawWeight", "1500");

    String result = parser.parseExpression(
            "#shippingService.estimate(#rawWeight)"
    ).getValue(context, String.class);

The `#rawWeight` argument has type String, while the method accepts Integer. If TypeConverter is capable of converting String to Integer, the call can be executed with the value 1500.

If a class has multiple overloads, for example `estimate(Integer)`, `estimate(Long)`, and `estimate(String)`, runtime types and conversion capabilities can affect which method is selected. When overloads could cause ambiguity, normalize argument types beforehand in Java or use methods with distinct signatures.

Successful conversion also does not mean the data is valid in business terms. A string might convert to a number yet still fall outside the weight limits allowed by the service.

## 5. Argument Conversion When Creating Objects

Constructor invocation may also require argument conversion to match a class constructor:

    new com.example.Customer('Lan', '25')

Suppose Customer has a constructor accepting `String name` and `Integer age`. If TypeConverter supports String to Integer, SpEL can convert the second argument to invoke the matching constructor.

ConstructorResolver is responsible for finding the constructor; TypeConverter assists with type conversion when needed. The two components have different roles. If the class cannot be resolved, no matching constructor exists, or the converter cannot convert an argument, instance creation fails.

If you need to create objects with untrusted data, validate values before invoking the constructor. Do not use type conversion capabilities as a substitute for validation or restricting allowed classes for instantiation.

## 6. Converting Result Types with getValue

Expression provides a `getValue` overload that accepts a target type. SpEL evaluates the expression first, then uses TypeConverter to convert the result to the requested type if needed.

For example:

    Integer result = parser.parseExpression("10 + 5")
            .getValue(context, Integer.class);

Or converting a string value:

    Long id = parser.parseExpression("'123456'")
            .getValue(context, Long.class);

This is a conversion of the final result. It does not change the types of the operands while the operation was already being performed.

For example, division of two integers can produce an integer result before conversion:

    Double result = parser.parseExpression("1 / 2")
            .getValue(context, Double.class);

If the division is performed as integer division, the intermediate result is 0; converting that result to Double still yields 0.0. To get 0.5, use a floating-point operand from the start:

    Double result = parser.parseExpression("1.0 / 2")
            .getValue(context, Double.class);

Therefore, distinguish between result type conversion and how operators handle operand types.

## 7. StandardTypeConverter and ConversionService

StandardTypeConverter is the TypeConverter implementation commonly used in StandardEvaluationContext. It delegates conversion to Spring ConversionService.

You can create a custom ConversionService, register application converters, and attach it to the context:

    DefaultConversionService conversionService =
            new DefaultConversionService();

    conversionService.addConverter(
            String.class,
            ShippingMode.class,
            ShippingMode::valueOf
    );

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeConverter(
            new StandardTypeConverter(conversionService)
    );

    context.setVariable("rawMode", "EXPRESS");

    ShippingMode mode = parser.parseExpression("#rawMode")
            .getValue(context, ShippingMode.class);

In the example, the converter converts a string into the ShippingMode enum. `DefaultConversionService` provides default converters; the application can register additional converters for custom domain types.

When configuring custom converters, clearly define valid inputs and how invalid values are handled. A converter should focus on converting data representations and should not perform database queries, API calls, or mutate system state.

## 8. Using TypeConverter with SimpleEvaluationContext

SimpleEvaluationContext provides a more restricted feature set than StandardEvaluationContext. You can configure a dedicated ConversionService via its builder:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withConversionService(conversionService)
                    .build();

This is useful when expressions need type conversion without broader features such as type references, constructor invocations, or bean references.

SimpleEvaluationContext does not support constructor invocations or bean references. Adding a ConversionService does not re-enable those features; it only configures the conversion mechanism for operations supported by the context.

Choose the read-only or read-write builder according to the intended property access. A converter does not determine which properties are writable.

## 9. Converting Collections and Generic Types

TypeDescriptor helps Spring preserve information about collection element types and map key/value types. As a result, ConversionService can convert collection data when both source and target types are fully described.

For example, an application may need to convert a list of numeric strings into a list of Integers. Conversion depends on the TypeDescriptor of the target property or parameter and the registered converters.

When working with collections, check both the container type and the element type. Converting one List to another is not just changing the collection class; each element may also need to be converted. If one element is invalid, the entire conversion operation can fail.

Do not assume every collection type or nested structure is converted automatically in the same way. For complex domain structures, a specialized converter or explicit mapping step in Java is often easier to control.

## 10. Null, Primitive Types, and Conversion Errors

Null can be passed through an expression, but not every target type can accept null. Reference types such as Integer or Boolean can represent null; primitive types such as `int` or `boolean` cannot.

For example, if a method accepts `int`, a null argument cannot be converted to a valid primitive value without an application-provided default rule. Handle null before calling the method, or use a wrapper type if null is a valid state.

Common conversion errors:

- String does not match the format of the target type.
- Numeric value exceeds the representable range of the target type.
- Converter is not registered or does not support the source/target type pair.
- Collection contains an element that cannot be converted.
- Null is passed to a primitive type.
- Multiple overloads can accept the converted value and cause resolution ambiguity.

When an error occurs, check the runtime type of the source value, the target TypeDescriptor, and the converter being used by the context. Do not catch the error and silently return a default value if doing so could corrupt business data.

## 11. Creating a Custom Converter with the Right Scope

If a domain has custom types, register an explicit converter instead of scattering string-parsing logic across multiple expressions.

For example:

    public enum ShippingMode {
        STANDARD,
        EXPRESS
    }

    Converter<String, ShippingMode> shippingModeConverter =
            source -> ShippingMode.valueOf(
                    source.trim().toUpperCase(Locale.ROOT)
            );

    DefaultConversionService conversionService =
            new DefaultConversionService();

    conversionService.addConverter(shippingModeConverter);

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeConverter(
            new StandardTypeConverter(conversionService)
    );

This converter normalizes the string and converts it to the enum. For inputs that do not match an enum value, `valueOf` throws an exception; the application can turn that error into an appropriate validation message at the calling layer.

Keep converters simple, independently testable, and free of request state. If conversion requires user context, access permissions, or database data, perform it in a business service and pass the validated value into the EvaluationContext.

## 12. Controlling and Testing Conversion

When configuring a TypeConverter, you should test these cases:

1. Source value is properly formatted and converts successfully.
2. Source value is malformed.
3. Value exceeds the target type's range.
4. Null values and primitive types.
5. Method and constructor argument conversion.
6. Conversion during property assignment.
7. Result conversion via `getValue(context, TargetType.class)`.
8. Collections with valid and invalid elements.
9. Custom converters applied to the right context.

You can check conversion capability beforehand:

    TypeConverter converter = context.getTypeConverter();

    boolean supported = converter.canConvert(
            TypeDescriptor.valueOf(String.class),
            TypeDescriptor.valueOf(Integer.class)
    );

This check indicates whether the converter supports the described type pair; it does not guarantee that every specific String value will convert successfully. To confirm actual data, you still need to perform the conversion and handle errors.

If the same Expression is evaluated with multiple EvaluationContexts, test each context because they may use different TypeConverters.

## 13. Key Takeaways

TypeConverter is the EvaluationContext's type conversion service during SpEL expression evaluation. It supports converting values when assigning properties, passing arguments to methods/constructors, and retrieving results in a requested type. StandardEvaluationContext uses StandardTypeConverter based on ConversionService by default; custom converters can be registered and attached to the context. TypeDescriptor helps preserve type metadata, including collection information. Type conversion does not replace validation, does not grant access permissions, and does not change arithmetic rules already applied to operands. Check for null, value ranges, overloads, and conversion errors; only register converters needed for the use case.
