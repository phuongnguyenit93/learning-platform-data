# Conversion During Property Assignment in Spring Expression Language

Spring Expression Language (SpEL) can write values to properties of a Java object via \`Expression.setValue(...)\` or the assignment operator \`=\`. When the type of the input value differs from the type required by the property, SpEL can convert the value before writing.

For example, the \`retryCount\` property has type \`Integer\`, while the input data is the string \`"5"\`. If the EvaluationContext has a TypeConverter that supports converting String to Integer, SpEL can perform the conversion and then invoke the \`setRetryCount(Integer)\` setter.

This process involves three components:

- **PropertyAccessor:** identifies the target property and how to write the value.
- **TypeDescriptor:** describes the target type, including generic type information where needed.
- **TypeConverter:** checks and performs conversion from the input value's type to the type required by the property.

Understanding this relationship helps avoid errors when binding data, updating nested properties, or using string-typed data in expressions.

## 1. Assigning to a Property Whose Type Differs from the Input Value

Suppose a JavaBean has an integer property:

~~~java
public class RetrySettings {
    private Integer retryCount;

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

Create the object and EvaluationContext:

~~~java
RetrySettings settings = new RetrySettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();
Expression property =
    parser.parseExpression("retryCount");
~~~

You can assign a string to an Integer property:

~~~java
property.setValue(context, "5");

System.out.println(settings.getRetryCount());
~~~

Output:

~~~text
5
~~~

The passed value is a String, whereas the setter expects an Integer. If the current TypeConverter supports String-to-Integer conversion, SpEL converts the value before writing the property.

Therefore, calling setValue does not mean SpEL always passes the raw input object directly to the setter. The write process may include a type conversion step.

## 2. When Does TypeConverter Get Involved?

When writing a property, SpEL needs to know what type the target property requires. For a typical JavaBean, a reflection PropertyAccessor can locate the corresponding setter, determine the setter's parameter type, and ask TypeConverter to convert the input value if needed.

The processing flow can be illustrated as:

~~~text
Expression.setValue(context, "5")
             |
             v
PropertyAccessor finds target property
             |
             v
Determine setter and target type Integer
             |
             v
TypeConverter checks String -> Integer conversion
             |
        +----+----+
        |         |
   Convertible  Not convertible
        |         |
        v         v
   Integer value  Conversion error
        |
        v
Call setRetryCount(Integer)
        |
        v
Property is updated
~~~

If the input value is already compatible with the target type, no actual conversion may be necessary. If the two types differ, TypeConverter decides whether conversion is possible.

PropertyAccessor is responsible for writing to the object. TypeConverter is responsible for converting the value to the type requested by the accessor.

## 3. Assigning with Expression.setValue

\`Expression.setValue(...)\` is the explicit API for writing to a writable target expression.

~~~java
RetrySettings settings = new RetrySettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();

Expression retryCount =
    parser.parseExpression("retryCount");

retryCount.setValue(context, "8");
~~~

SpEL performs these steps:

1. Use context to resolve the root object.
2. Resolve the \`retryCount\` property.
3. Determine the target type from the property or setter.
4. Convert String \`"8"\` to Integer if supported by TypeConverter.
5. Write the value to the property.

You can check whether the property supports writing before calling setValue:

~~~java
if (retryCount.isWritable(context)) {
    retryCount.setValue(context, "8");
}
~~~

\`isWritable\` checks writability in the current context. It does not guarantee every input value can be converted or that the setter will necessarily succeed. Conversion and writing can still fail at runtime.

## 4. Conversion When Using the Assignment Operator =

SpEL also supports the assignment operator in expression strings:

~~~spel
retryCount = '8'
~~~

If the expression is evaluated with a root object that has a writable \`retryCount\` property, SpEL performs the assignment. The write process also uses the EvaluationContext's type conversion mechanism when needed.

For example:

~~~java
RetrySettings settings = new RetrySettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();

Expression assignment =
    parser.parseExpression("retryCount = '8'");

assignment.getValue(context);

System.out.println(settings.getRetryCount());
~~~

Output:

~~~text
8
~~~

Keep the distinction clear:

- \`=\` is assignment, which can mutate the target object.
- \`==\` is comparison, returning a Boolean and not writing properties.

Both \`setValue\` and the assignment operator can trigger value conversion before the property is updated.

## 5. TypeDescriptor Helps Determine the Target Type

TypeConverter needs to know the target type to choose the right conversion. In Spring, \`TypeDescriptor\` describes a data type more richly than a plain Class object.

In addition to the class type, TypeDescriptor can hold information about:

- Collection element types.
- Map key and value types.
- Array component types.
- Annotations attached to a property or field.
- Metadata needed by certain converters.

For example, the following two properties share the same List class type yet have different element types:

~~~java
private List<Integer> retryCodes;
private List<String> labels;
~~~

TypeDescriptor can retain generic information so the conversion system knows which element type the target expects.

This matters when the input data is a collection or map. Conversion is not just changing the container's type; in supported cases, Spring can also convert individual elements according to the target type metadata.

## 6. Converting Strings to Common Property Types

The default TypeConverter in a typical SpEL environment supports many standard conversions via Spring ConversionService.

For example, depending on the target type and input format, common conversions may include:

| Target Property Type | Input Value | Example Result |
|---|---|---|
| Integer | String \`"12"\` | Integer 12 |
| Long | String \`"9000"\` | Long 9000 |
| Boolean | String \`"true"\` | Boolean true |
| BigDecimal | String \`"1250.75"\` | BigDecimal 1250.75 |
| Enum | String \`"PAID"\` | Enum constant PAID |
| String | Number 42 | String \`"42"\` |

Exact conversion capability depends on the ConversionService, registered converters, and data format. Do not assume any string can be converted to any type.

For example, the string \`"five"\` cannot be converted to Integer by a typical numeric converter. In that case, the assignment fails before the property receives a new value.

## 7. Example: Converting String to Enum During Property Assignment

Suppose an application has an enum:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

JavaBean:

~~~java
public class OrderSettings {
    private OrderStatus status;

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
~~~

You can assign the enum name as a String:

~~~java
OrderSettings settings = new OrderSettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();

Expression status =
    parser.parseExpression("status");

status.setValue(context, "PAID");
~~~

If the active ConversionService supports converting String to enum, the property receives the value \`OrderStatus.PAID\`.

If the input is \`"UNKNOWN"\`, there is no matching enum constant and conversion may fail. The property should not be assumed to have updated successfully merely because the setValue call started.

## 8. Using a Custom ConversionService

An application can register custom converters when domain data types are not supported by default converters.

For example, suppose there is a CurrencyCode type:

~~~java
public record CurrencyCode(String value) {
}
~~~

The application wants to convert String to CurrencyCode. You can register a converter in ConversionService:

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(
    String.class,
    CurrencyCode.class,
    CurrencyCode::new
);
~~~

Create a TypeConverter using that ConversionService:

~~~java
StandardTypeConverter typeConverter =
    new StandardTypeConverter(conversionService);

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

context.setTypeConverter(typeConverter);
~~~

When an expression assigns a string to a CurrencyCode property, TypeConverter uses the registered converter to create the target object.

Example JavaBean:

~~~java
public class PaymentSettings {
    private CurrencyCode currency;

    public CurrencyCode getCurrency() {
        return currency;
    }

    public void setCurrency(CurrencyCode currency) {
        this.currency = currency;
    }
}
~~~

Assigning a value:

~~~java
Expression currency =
    parser.parseExpression("currency");

currency.setValue(context, "VND");
~~~

If the context is configured with the TypeConverter above and the root object is PaymentSettings, the setter receives a CurrencyCode with value VND.

Custom converters should clearly define input formats, normalization rules, and behavior for invalid data. Do not silently turn malformed data into a default value if doing so could hide business errors.

## 9. Configuring TypeConverter Directly on EvaluationContext

\`EvaluationContext\` provides the TypeConverter used by SpEL during evaluation. With StandardEvaluationContext, you can replace the TypeConverter using the \`setTypeConverter\` method.

For example:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ConversionService conversionService =
    new DefaultConversionService();

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

Once configured, operations requiring conversion in that context can use the selected ConversionService, including property assignment.

Keep in mind that replacing the TypeConverter can affect many other operations in the same context, not just one specific property. Conversions during method calls or handling target-typed results can also use the same mechanism.

If you only need to add one converter, add it to the existing ConversionService rather than replacing the entire configuration the application relies on.

## 10. Conversion When Assigning Nested Properties

The target property may reside inside a nested object:

~~~spel
customer.age = '35'
~~~

Suppose the root object has a customer property and Customer has a \`setAge(Integer)\` setter. SpEL follows the path:

1. Read the customer property on the root object.
2. Obtain the Customer object.
3. Resolve the age property on Customer.
4. Determine the target type Integer.
5. Convert String \`"35"\` to Integer if supported.
6. Write the value via the corresponding setter mechanism.

If customer is null, SpEL cannot continue accessing the age property in the normal way. Type conversion does not instantiate missing intermediate objects. The application must ensure intermediate objects exist or configure an intentional auto-growing mechanism if desired.

If the nested property exists yet is not writable, the operation still fails even if the converter can convert the value.

## 11. Conversion When Assigning Collection or Map Elements

An indexer can target a collection or map element:

~~~spel
retryCodes[0] = '5'
thresholds['warning'] = '80.5'
~~~

The target type can be inferred from the data structure and available type metadata. For collection properties with explicit generic declarations, TypeDescriptor can supply element type information to the conversion mechanism.

For example:

~~~java
public class RuleSettings {
    private List<Integer> retryCodes;
    private Map<String, BigDecimal> thresholds;

    public List<Integer> getRetryCodes() {
        return retryCodes;
    }

    public void setRetryCodes(List<Integer> retryCodes) {
        this.retryCodes = retryCodes;
    }

    public Map<String, BigDecimal> getThresholds() {
        return thresholds;
    }

    public void setThresholds(
            Map<String, BigDecimal> thresholds) {
        this.thresholds = thresholds;
    }
}
~~~

If the accessor and TypeConverter have sufficient type information, string values can be converted to the corresponding element types before writing.

However, writability also depends on whether the actual collection or map allows updates. An immutable List, an unmodifiable Map, or an invalid index can cause the operation to fail. Successful type conversion does not guarantee the target slot is writable.

## 12. Null and Target Types During Assignment

Null is a value that must be handled according to the target property's type.

- Reference properties such as String, Integer, or BigDecimal can accept null if the setter and application logic allow it.
- Primitive properties such as int or boolean cannot store null.
- A setter can reject null via validation or by throwing an exception.
- Custom converters can define how to handle null under their own contract.

For example, if a setter expects int:

~~~java
public void setRetryCount(int retryCount) {
    this.retryCount = retryCount;
}
~~~

assigning null cannot produce a valid int value. SpEL or the conversion mechanism may raise an error instead of writing null into the property.

If the domain permits an unset state, wrapper types such as Integer or Boolean may be more appropriate than primitives.

## 13. Conversion Cannot Help If a Property Is Not Writable

TypeConverter only resolves data type differences. It does not grant write permission to a property that is inherently non-writable.

For example:

~~~java
public class ReadOnlySettings {
    public Integer getRetryCount() {
        return 3;
    }
}
~~~

The retryCount property is readable yet has no corresponding setter. Unless the current accessor has another write mechanism, setValue will fail.

You can check beforehand:

~~~java
Expression property =
    parser.parseExpression("retryCount");

if (property.isWritable(context)) {
    property.setValue(context, "5");
}
~~~

If isWritable returns false, review the object type, setter, PropertyAccessor, and EvaluationContext write permissions. Registering more converters will not fix a read-only property error.

## 14. Conversion Can Succeed Yet the Setter May Still Fail

Type conversion and writing the property are two separate steps.

Suppose a converter successfully converts String to Integer, yet the setter enforces validation:

~~~java
public void setRetryCount(Integer retryCount) {
    if (retryCount != null && retryCount < 0) {
        throw new IllegalArgumentException(
            "retryCount must be non-negative"
        );
    }
    this.retryCount = retryCount;
}
~~~

Assigning \`"5"\` can succeed because it converts to Integer 5 and the setter accepts the value.

Assigning \`"-1"\` can also convert to Integer successfully, yet the setter rejects negative values. Here the error occurs in the write step or setter logic, not in the converter.

When investigating errors, determine whether the exception comes from:

- Property or setter not found.
- Property does not support writing.
- TypeConverter unable to convert.
- Setter or accessor throwing an exception while writing.

## 15. How to Investigate Conversion Errors During Property Assignment

When setValue or an assignment expression fails, check in this sequence:

1. **Verify the target property:** are the property name and nested path correct?
2. **Check writability:** does the property have a setter or an accessor supporting writes?
3. **Identify the target type:** what is the setter parameter type or the property's TypeDescriptor?
4. **Check the input type:** what is the passed value's type and is its format valid?
5. **Inspect TypeConverter:** which converter is the context using? Does it support this conversion?
6. **Check generic metadata:** if the target is a collection or map, are element/key/value types described?
7. **Inspect the setter:** after conversion, does the setter have validation or logic rejecting the value?
8. **Read the root exception:** is the failure a conversion failure, property access failure, or an exception from the setter?

Do not change input data types by guesswork. Identify the target type and active converter to pinpoint exactly which step failed.

## 16. Complete Example: Assigning Strings to Numeric and Enum Properties

The following example has two properties with different target types:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}

public class OrderSettings {
    private Integer retryCount;
    private OrderStatus status;

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
~~~

Assigning string values:

~~~java
OrderSettings settings = new OrderSettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();

Expression retryCount =
    parser.parseExpression("retryCount");

Expression status =
    parser.parseExpression("status");

retryCount.setValue(context, "5");
status.setValue(context, "PAID");

System.out.println(settings.getRetryCount());
System.out.println(settings.getStatus());
~~~

With a default TypeConverter supporting the respective conversions, the output is:

~~~text
5
PAID
~~~

In this example:

- PropertyAccessor identifies the two target properties and how to write them.
- TypeDescriptor or property metadata indicates the target types are Integer and OrderStatus, respectively.
- TypeConverter performs the necessary conversions.
- The setters receive the converted values and update the object.

If the input is invalid, such as retryCount being \`"five"\` or status being \`"UNKNOWN"\`, conversion may fail and the property is not updated as desired.

## 17. Common Misconceptions

**Misconception 1: setValue always passes the raw input object to the setter.**  
SpEL can convert the value via TypeConverter before writing if the input type differs from the target type.

**Misconception 2: TypeConverter decides whether a property is writable.**  
PropertyAccessor and the target object determine writability. TypeConverter only converts values.

**Misconception 3: ConversionService and TypeConverter are the same interface.**  
ConversionService is Spring's conversion mechanism; StandardTypeConverter is the adapter enabling SpEL to use ConversionService via TypeConverter.

**Misconception 4: Successful conversion means the setter will definitely succeed.**  
The setter may validate, reject values, or throw an exception.

**Misconception 5: Collection generics do not affect conversion.**  
TypeDescriptor can carry element, key, and value type information, enabling collection/map data to be converted to the right types when supported.

**Misconception 6: Any type can accept null.**  
Primitive properties cannot store null; setters or converters may also reject null for reference properties.

## 18. Key Takeaways

- During property assignment, SpEL determines the target type via property access mechanisms and corresponding metadata.
- The EvaluationContext's TypeConverter can convert the input value to the property's required type before writing.
- TypeDescriptor describes the target type and can contain generic metadata for collections or maps.
- StandardTypeConverter connects SpEL to Spring ConversionService.
- You can replace the TypeConverter on StandardEvaluationContext or provide a custom ConversionService.
- \`Expression.setValue(...)\` and the assignment operator \`=\` can both trigger conversion when writing properties.
- Type conversion does not make a read-only property writable.
- Successful conversion does not guarantee the setter accepts the value.
- Null, primitives, immutable collections, invalid indices, and custom converters all need to be handled according to the data contract.
- When debugging, separate property access errors, conversion errors, and errors inside the setter.

When assigning properties with SpEL, identify the target type, verify the property is writable, and check whether the context's TypeConverter can convert the input data. Then inspect the setter and object state to confirm the update completed.
