# TypeLocator, TypeConverter, and OperatorOverloader in Spring Expression Language

EvaluationContext is the environment that Spring Expression Language (SpEL) uses when evaluating an expression. In addition to the root object and variables, the context provides extension mechanisms for SpEL to locate Java types, convert values, and handle operations that require custom rules.

Three important components are:

- **TypeLocator:** locates a Java type when an expression uses a type reference such as T(java.time.LocalDate).
- **TypeConverter:** checks and converts values to the type required by an operation, such as when assigning a property or requesting a result type.
- **OperatorOverloader:** lets the application define how certain SpEL operators are executed on custom data types.

They solve three different problems. TypeLocator locates classes; TypeConverter converts values; OperatorOverloader changes how an operation is performed. All three are configured through EvaluationContext.

## 1. Role of the three components in EvaluationContext

When SpEL evaluates an expression, it may need several services from the context:

| Component | Question the component resolves | Example |
|---|---|---|
| TypeLocator | Which Class corresponds to this type name? | T(java.math.BigDecimal) |
| TypeConverter | Can this value be converted to the target type? | String "25" to Integer |
| OperatorOverloader | Does this operation have custom handling for these two operands? | Money + Money |

You can visualize the processing flow:

~~~text
Expression
   |
   v
EvaluationContext
   |
   +--> TypeLocator
   |       Finds Class for T(...)
   |
   +--> TypeConverter
   |       Converts values when an operation requires it
   |
   +--> OperatorOverloader
           Handles custom operations if supported
~~~

These components do not replace one another. For example, TypeLocator can find the BigDecimal class, but it does not automatically convert a string into a BigDecimal. TypeConverter can convert a value, but it does not decide which class names are permitted to be referenced. OperatorOverloader can define addition for Money, but it does not make a new type reference automatically discoverable.

## 2. TypeLocator: locating Java types in expressions

SpEL supports type references using the T(...) operator:

~~~spel
T(java.lang.Math)
T(java.math.BigDecimal)
T(java.time.LocalDate)
~~~

When encountering this syntax, SpEL needs to find the class corresponding to the name written inside the parentheses. EvaluationContext provides the TypeLocator interface for that task.

TypeLocator defines the main method:

~~~java
Class<?> findType(String typeName) throws EvaluationException;
~~~

The input is a type name; the result is the corresponding Class object. If the type cannot be found or the locator's policy rejects the name, the operation may throw an EvaluationException.

### Where is TypeLocator used?

Example:

~~~spel
T(java.lang.Math).max(10, 20)
~~~

SpEL needs to:

1. Recognize the type reference T(java.lang.Math).
2. Ask TypeLocator to locate the class java.lang.Math.
3. Receive the corresponding Class.
4. Resolve the static member max.
5. Invoke the method with the arguments and receive the result.

TypeLocator only resolves the type name. Finding and invoking the static method are separate steps, governed by access mechanisms and method resolution.

## 3. StandardTypeLocator and default behavior

StandardEvaluationContext normally uses StandardTypeLocator as its default TypeLocator. StandardTypeLocator finds classes through a classloader and supports package imports.

The java.lang package is imported by default, so short names can be used:

~~~spel
T(String)
T(Integer)
T(Math)
~~~

For types outside java.lang, you can use the fully qualified name:

~~~spel
T(java.math.BigDecimal)
T(java.time.LocalDate)
~~~

Or register package imports to shorten names:

~~~java
StandardTypeLocator typeLocator =
    new StandardTypeLocator();

typeLocator.registerImport("java.math");
typeLocator.registerImport("java.time");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

After registration, expressions can be written as:

~~~spel
T(BigDecimal)
T(LocalDate)
~~~

Imports help shorten type names. They are not an allow-list and do not mean other packages are forbidden. If the application needs to restrict type references, a dedicated policy must be enforced in TypeLocator.

### Configuring the classloader

In multi-module applications, plugins, or environments with custom classloaders, the classloader affects which classes StandardTypeLocator can find.

You can specify a classloader:

~~~java
ClassLoader classLoader =
    Thread.currentThread().getContextClassLoader();

StandardTypeLocator typeLocator =
    new StandardTypeLocator(classLoader);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

The type name must still be valid and the class must be loadable through the selected classloader.

## 4. Creating an allow-listed TypeLocator

If an expression should only reference specific types, you can wrap another TypeLocator with an allow-list policy.

For example, allowing only Math and BigDecimal:

~~~java
public class AllowListTypeLocator implements TypeLocator {

    private final TypeLocator delegate =
        new StandardTypeLocator();

    private final Set<String> allowedTypes = Set.of(
        "java.lang.Math",
        "java.math.BigDecimal"
    );

    @Override
    public Class<?> findType(String typeName)
            throws EvaluationException {

        if (!allowedTypes.contains(typeName)) {
            throw new EvaluationException(
                "Type is not allowed: " + typeName
            );
        }

        return delegate.findType(typeName);
    }
}
~~~

Registering the locator:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(new AllowListTypeLocator());

ExpressionParser parser = new SpelExpressionParser();

Integer result = parser.parseExpression(
    "T(java.lang.Math).max(10, 20)"
).getValue(context, Integer.class);
~~~

The result is 20.

A type reference outside the list, such as T(java.lang.System), is rejected before the delegate locates the class.

If you want to allow both fully qualified names and short names, normalize the names and clearly define the accepted aliases. Do not allow every name that the delegate can find and check the policy afterward.

An allow-list TypeLocator only restricts the access path via T(...). It is not a complete sandbox: the root object, variables, method resolver, property accessor, or bean resolver can still provide other access paths.

## 5. TypeConverter: converting values to a target type

An expression can produce or receive a value whose type differs from what the application needs. TypeConverter helps SpEL check and perform that conversion.

The TypeConverter interface provides two key operations:

~~~java
boolean canConvert(
    TypeDescriptor sourceType,
    TypeDescriptor targetType
);

Object convertValue(
    Object value,
    TypeDescriptor sourceType,
    TypeDescriptor targetType
) throws EvaluationException;
~~~

- canConvert checks whether conversion from the source type to the target type is possible.
- convertValue performs the conversion and returns the new value.

SpEL may need conversion in many situations, for example:

- Assigning a value to a property whose type differs from the input value.
- Calling a method or constructor when arguments need compatible types.
- Retrieving a result via a getValue overload that specifies a target type.
- Performing binding operations that require data conversion.

### Example converting String to Integer when assigning a property

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

Assigning with SpEL:

~~~java
RetrySettings settings = new RetrySettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();

Expression property =
    parser.parseExpression("retryCount");

property.setValue(context, "5");

System.out.println(settings.getRetryCount());
~~~

With the default TypeConverter supporting String to Integer, the output is:

~~~text
5
~~~

PropertyAccessor identifies the target property and setter. TypeConverter converts the string "5" into an Integer before the value is written.

## 6. TypeDescriptor describes source and target types

TypeConverter works together with TypeDescriptor. TypeDescriptor provides richer type information than a plain Class object.

It can describe:

- The Java type of a value.
- The element type of a collection.
- The key and value types of a map.
- The component type of an array.
- Annotations and metadata associated with a property.

Example:

~~~java
private List<Integer> retryCodes;
private Map<String, BigDecimal> thresholds;
~~~

Both properties have outer collection-like class types, but different element or key/value types. TypeDescriptor can supply generic metadata so ConversionService selects the appropriate conversion.

This is especially useful when binding data from strings or generic data structures to strongly typed properties.

## 7. StandardTypeConverter and ConversionService

StandardEvaluationContext normally uses StandardTypeConverter as its default TypeConverter. StandardTypeConverter connects SpEL with Spring's ConversionService conversion mechanism.

You can create the default converter:

~~~java
StandardTypeConverter typeConverter =
    new StandardTypeConverter();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeConverter(typeConverter);
~~~

Or supply a specific ConversionService:

~~~java
ConversionService conversionService =
    new DefaultConversionService();

StandardTypeConverter typeConverter =
    new StandardTypeConverter(conversionService);

context.setTypeConverter(typeConverter);
~~~

This allows SpEL to use the same converter system that the application uses in other parts of Spring.

Not every value can be converted. Convertibility depends on the registered converters, source type, target type, and data format.

For example, the string "5" can be converted to Integer, whereas the string "five" is not a valid integer representation for standard converters.

## 8. Registering a custom converter

When an application has custom domain types, a Converter can be added to ConversionService.

For example, defining a CurrencyCode type:

~~~java
public class CurrencyCode {
    private final String value;

    public CurrencyCode(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Creating a converter:

~~~java
Converter<String, CurrencyCode> currencyCodeConverter =
    CurrencyCode::new;
~~~

Registering and configuring for SpEL:

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(currencyCodeConverter);

StandardEvaluationContext context =
    new StandardEvaluationContext(paymentSettings);

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

If PaymentSettings has a setter accepting CurrencyCode, an expression can assign a string and use the registered converter:

~~~spel
currency = 'VND'
~~~

When writing the property, TypeConverter asks ConversionService to convert String to CurrencyCode and then passes the converted value to the write mechanism.

A custom converter should clearly define how data is normalized and how invalid input is handled. If the format is wrong, report an error clearly instead of silently producing a domain-invalid value.

## 9. OperatorOverloader: customizing operations in SpEL

SpEL supports operators such as addition, subtraction, multiplication, division, modulo, and exponentiation. For standard Java data types, SpEL applies built-in operator semantics.

When an application has custom domain types, such as Money or Distance, you may want to define how operations execute directly on those values. OperatorOverloader lets the application provide this behavior.

The OperatorOverloader interface has two methods:

~~~java
boolean overridesOperation(
    Operation operation,
    Object leftOperand,
    Object rightOperand
);

Object overloadOperation(
    Operation operation,
    Object leftOperand,
    Object rightOperand
) throws EvaluationException;
~~~

- overridesOperation indicates whether the implementation handles the operation for the current pair of operands.
- overloadOperation executes the operation and returns the result.

SpEL uses Operation to identify the operation kind, such as ADD, SUBTRACT, MULTIPLY, DIVIDE, MODULUS, or POWER.

OperatorOverloader does not add new operator syntax to the language and does not change operator precedence. It provides custom execution for operations that SpEL already recognizes.

## 10. Example of OperatorOverloader for the Money type

Suppose an application has a Money type holding an amount:

~~~java
public class Money {
    private final BigDecimal amount;

    public Money(BigDecimal amount) {
        this.amount = amount;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public Money add(Money other) {
        return new Money(amount.add(other.amount));
    }
}
~~~

Create an OperatorOverloader to support adding two Money values:

~~~java
public class MoneyOperatorOverloader
        implements OperatorOverloader {

    @Override
    public boolean overridesOperation(
            Operation operation,
            Object leftOperand,
            Object rightOperand) {

        return operation == Operation.ADD
            && leftOperand instanceof Money
            && rightOperand instanceof Money;
    }

    @Override
    public Object overloadOperation(
            Operation operation,
            Object leftOperand,
            Object rightOperand)
            throws EvaluationException {

        if (overridesOperation(
                operation,
                leftOperand,
                rightOperand)) {

            Money left = (Money) leftOperand;
            Money right = (Money) rightOperand;

            return left.add(right);
        }

        throw new EvaluationException(
            "Unsupported Money operation: " + operation
        );
    }
}
~~~

Register the implementation in the context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setOperatorOverloader(
    new MoneyOperatorOverloader()
);

context.setVariable(
    "left",
    new Money(new BigDecimal("100"))
);

context.setVariable(
    "right",
    new Money(new BigDecimal("50"))
);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#left + #right");

Money result =
    expression.getValue(context, Money.class);
~~~

The result is a new Money with an amount of 150.

In the example:

1. SpEL reads the two variables left and right.
2. Both operands are Money.
3. OperatorOverloader reports that it supports Operation.ADD for this pair of types.
4. overloadOperation invokes Money's addition logic.
5. The Money result is returned to the expression.

## 11. When is OperatorOverloader used?

OperatorOverloader is appropriate when an operator needs custom meaning for a domain type that SpEL's default semantics do not satisfy.

Some cases to consider:

- Adding two Money values according to the application's currency rules.
- Adding or subtracting two Distance values.
- Combining two domain value types that have custom mathematical rules.
- Defining calculations for specialized data types in an internal DSL.

Do not use OperatorOverloader merely to alter standard integer addition or string concatenation when the default semantics are already correct.

An implementation should:

- Accept only the Operations and operand types it genuinely supports.
- Return a meaningful and consistent result type.
- Throw an EvaluationException if invoked with an operation outside its supported scope.
- Avoid mutating operand state if the operation is expected to be a pure computation.
- Clearly define null rules and type conversion if the domain needs to support those cases.

## 12. Registering the three components on StandardEvaluationContext

StandardEvaluationContext allows separate configuration of TypeLocator, TypeConverter, and OperatorOverloader:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(rootObject);

context.setTypeLocator(typeLocator);
context.setTypeConverter(typeConverter);
context.setOperatorOverloader(operatorOverloader);
~~~

Each setter replaces one service in the evaluation environment.

An illustrative configuration:

~~~java
StandardTypeLocator typeLocator =
    new StandardTypeLocator();

DefaultConversionService conversionService =
    new DefaultConversionService();

StandardTypeConverter typeConverter =
    new StandardTypeConverter(conversionService);

StandardEvaluationContext context =
    new StandardEvaluationContext(rootObject);

context.setTypeLocator(typeLocator);
context.setTypeConverter(typeConverter);
context.setOperatorOverloader(
    new MoneyOperatorOverloader()
);
~~~

In a real application, only replace the components that have custom requirements. If default behavior already meets the need, keep the default component to avoid redundant configuration.

Also note that the context contains other services such as PropertyAccessor, MethodResolver, ConstructorResolver, and BeanResolver. The three components in this article are only part of the complete EvaluationContext.

## 13. The three components collaborating in an expression

An expression can use multiple mechanisms within the same evaluation.

For example, an application uses a type reference to obtain a constant, Money variables to perform custom addition, and requests a specific result type:

~~~spel
#baseAmount + #extraAmount
~~~

Process:

1. TypeLocator participates only if the expression contains T(...), for example when needing to reference a type.
2. TypeConverter participates if an operation needs to convert a value to a compatible type.
3. OperatorOverloader is queried when SpEL evaluates addition and the pair of operands falls within the scope supported by the custom implementation.
4. The Expression returns the final result.

Not every expression needs all three. For example, an expression that only reads properties does not necessarily need type references or operator overloading.

## 14. Distinguishing the three mechanisms from other EvaluationContext components

| Component | Responsibility | Not responsible for |
|---|---|---|
| TypeLocator | Locating a Class from a type name | Converting values or looking up beans |
| TypeConverter | Converting values between types | Deciding whether a property is writable |
| OperatorOverloader | Executing custom operations | Locating classes or calling arbitrary methods |
| PropertyAccessor | Reading/writing properties | Locating types in T(...) |
| MethodResolver | Finding suitable methods | Defining domain addition |
| ConstructorResolver | Finding constructors | Converting arbitrary business data |
| BeanResolver | Looking up beans by name | Locating a Class from a type reference |

This separation helps pinpoint the exact place to configure when an expression encounters an error.

For example:

- T(java.time.LocalDate) cannot find the class: check TypeLocator and the classloader.
- Assigning "abc" to an Integer property fails: check TypeConverter and input data.
- #left + #right does not support the Money type: check OperatorOverloader.
- customer.name cannot be read: check PropertyAccessor and the current object.
- customer.calculate() cannot find the method: check MethodResolver.

## 15. Limitations and configuration considerations

Extension components make SpEL more flexible, but they also affect expression behavior.

### TypeLocator

If using an allow-list, check the type name before delegating to find the Class. However, restricting T(...) does not control every access path to objects already present in the root, variables, or beans.

### TypeConverter

Converters can be used at many points during evaluation. An overly broad converter or loose data conversion can cause unexpected input data to be accepted. Clearly define formats, value domains, and behavior when conversion fails.

### OperatorOverloader

OperatorOverloader can change the meaning of operations for domain types. Keep implementations small, clearly define operand and result types, and avoid unpredictable side effects.

### EvaluationContext lifecycle

If a context is reused across multiple evaluations, its configuration and state are also reused. Do not mutate services or variables in a context shared across concurrent requests without appropriate synchronization and data scoping.

## 16. Comprehensive example: custom context for domain rules

Suppose an application has Money and wants to:

- Allow referencing only Math.
- Convert String to a domain type via ConversionService.
- Support adding two Money values.

It can be configured by responsibility:

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(
    String.class,
    CurrencyCode.class,
    CurrencyCode::new
);

StandardTypeConverter typeConverter =
    new StandardTypeConverter(conversionService);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(new AllowListTypeLocator());
context.setTypeConverter(typeConverter);
context.setOperatorOverloader(
    new MoneyOperatorOverloader()
);

context.setVariable(
    "left",
    new Money(new BigDecimal("100"))
);
context.setVariable(
    "right",
    new Money(new BigDecimal("50"))
);

ExpressionParser parser = new SpelExpressionParser();

Money total = parser.parseExpression(
    "#left + #right"
).getValue(context, Money.class);
~~~

In this configuration, TypeLocator, TypeConverter, and OperatorOverloader do not do the same job. Each component fulfills a distinct requirement in the evaluation environment. Configuring one component does not automatically replace or expand the permissions of the other two.

## 17. Common misconceptions

**Misconception 1: TypeLocator converts a value into a Java type.**  
TypeLocator locates a Class by name. Converting objects between types is the job of TypeConverter.

**Misconception 2: Registering a package import already restricts type references.**  
Imports only shorten type names. To enforce an allow-list, check names inside a custom TypeLocator.

**Misconception 3: TypeConverter decides whether a property is writable.**  
PropertyAccessor and the target object determine writability. TypeConverter only converts values when needed.

**Misconception 4: OperatorOverloader changes Java syntax.**  
It only provides behavior for SpEL operators inside EvaluationContext. It does not make Java's + operator automatically support the Money type.

**Misconception 5: OperatorOverloader is required for every addition.**  
SpEL already has default semantics for supported types. Only use an overloader when a domain type needs custom behavior.

**Misconception 6: Customizing one of the three components is enough to create a sandbox.**  
TypeLocator, TypeConverter, and OperatorOverloader only control their respective aspects. The root object, variables, property access, method resolution, and bean resolution still need to be restricted according to the application's goals.

## 18. Key takeaways

- EvaluationContext provides TypeLocator, TypeConverter, and OperatorOverloader for different needs during SpEL evaluation.
- TypeLocator finds a Class from a type name in T(...); StandardTypeLocator supports classloaders and package imports.
- TypeConverter checks and converts values according to source/target types; StandardTypeConverter integrates with Spring ConversionService.
- TypeDescriptor provides type metadata, including generic information for collections and maps.
- Custom domain converters can be registered into ConversionService and used via StandardTypeConverter in the context.
- OperatorOverloader defines how SpEL operations execute on custom data types.
- overridesOperation identifies the operation and operand pair an implementation supports; overloadOperation executes the operation and returns the result.
- StandardEvaluationContext allows configuring each component using setTypeLocator, setTypeConverter, and setOperatorOverloader.
- These three mechanisms do not replace PropertyAccessor, MethodResolver, ConstructorResolver, or BeanResolver.
- Custom configurations need clear scope, predictable results, and management aligned with the EvaluationContext lifecycle.

When extending SpEL, determine whether the expression needs type lookup, data conversion, or custom operator semantics. Then configure the right component in EvaluationContext, keep responsibilities separate, and expose only the capabilities the expression truly needs.
