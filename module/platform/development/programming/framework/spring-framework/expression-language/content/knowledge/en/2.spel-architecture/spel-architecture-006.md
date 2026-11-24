# TypeLocator, TypeConverter, and OperatorOverloader

In Spring Expression Language (SpEL), an expression is parsed into an expression tree and then evaluated within an EvaluationContext. The context provides the services SpEL needs at runtime. The three extension points in this lesson answer three different questions:

- **TypeLocator:** which Java class corresponds to a type name in an expression?
- **TypeConverter:** how is an existing value converted to a target type?
- **OperatorOverloader:** how should built-in operations such as addition or multiplication be executed for domain data types?

They are typically configured on StandardEvaluationContext. By cleanly separating the responsibilities of each component, we can extend SpEL for a custom domain model while keeping expression evaluation clear and controlled.

## 1. Position of the three components in the evaluation process

A basic SpEL flow consists of a parser, an expression, and an evaluation context:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("price * quantity");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Object result = expression.getValue(context);
~~~

The parser creates an Expression from the string. When getValue is called, the Expression reads the root object and uses services in the context when needed. Each of the three components has a distinct role:

| Component | Primary input | Output |
|---|---|---|
| TypeLocator | Class name, e.g., java.lang.Math | Class<?> object |
| TypeConverter | Value, source type, and target type | Converted value |
| OperatorOverloader | Operation type and two operands | Result of the custom operation |

For example, the expression T(Math).max(10, 20) needs TypeLocator to find the Math class. Passing an argument to a method with a different parameter type may need TypeConverter. The expression left + right with two Money objects may need OperatorOverloader if you want to define addition according to business rules.

The three components do not replace one another: TypeLocator does not convert data; TypeConverter does not define operator semantics; OperatorOverloader does not look up classes by name.

## 2. TypeLocator — locating classes from type names

### 2.1. Responsibility and API

TypeLocator belongs to the org.springframework.expression package. It receives a type name referenced in an expression and returns the corresponding Class:

~~~java
public interface TypeLocator {
    Class<?> findType(String typeName) throws EvaluationException;
}
~~~

TypeLocator is commonly used by SpEL when encountering the T(...) type reference operator. Once the class is found, the expression can reference static members or use that type in supported SpEL constructs.

Example:

~~~java
T(java.lang.Math).max(10, 20)
~~~

If the java.lang package is imported by default, it can be written more concisely:

~~~java
T(Math).max(10, 20)
~~~

T(...) is syntax for referencing a Java type. It is not syntax for creating a Spring bean, nor does it instantiate a new object on its own.

### 2.2. StandardTypeLocator

Spring provides StandardTypeLocator to handle standard class lookup. It can locate classes by fully qualified name and supports package prefixes registered as imports. The java.lang package is registered by default.

~~~java
StandardTypeLocator typeLocator = new StandardTypeLocator();
typeLocator.registerImport("com.example.domain");

StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);
context.setTypeLocator(typeLocator);
~~~

After registering the import, expressions can use the short class name if that name is unambiguous:

~~~java
T(Money).of("125.00", "USD")
~~~

Here Money resides in the com.example.domain package. If you do not want to rely on import prefixes, you can use the fully qualified name:

~~~java
T(com.example.domain.Money).of("125.00", "USD")
~~~

StandardTypeLocator also has a constructor accepting a ClassLoader. This is useful in environments with custom class loaders, such as plugin applications or deployment environments with multiple class-loading zones.

### 2.3. When is a custom TypeLocator needed?

Use StandardTypeLocator when the application trusts expressions and only needs standard class resolution. You can implement a custom TypeLocator when the application requires a different resolution policy, for example:

- Allowing only a declared set of classes.
- Mapping business aliases to Java classes.
- Resolving classes using a specific ClassLoader.
- Returning an informative error when an expression references a disallowed type.

Distinguish import prefixes from a security allowlist. Registering only a few packages in StandardTypeLocator does not mean other classes are blocked: fully qualified class names can still be resolved. If you need to restrict classes, implement a TypeLocator that enforces a genuine allowlist and also control the other capabilities granted to EvaluationContext.

## 3. TypeConverter — converting values to a target type

### 3.1. Responsibility and API

TypeConverter is responsible for converting a value from a source type to a target type. The interface resides in org.springframework.expression:

~~~java
public interface TypeConverter {
    boolean canConvert(TypeDescriptor sourceType, TypeDescriptor targetType);

    Object convertValue(
            Object value,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) throws EvaluationException;
}
~~~

TypeDescriptor belongs to org.springframework.core.convert. It describes a Java type along with related metadata, such as generic types and annotations. Therefore, it provides more information than a plain Class alone.

SpEL may need type conversion in situations such as:

- Assigning a value to a property of a specific type.
- Passing arguments to a method or constructor.
- Converting data when an evaluation operation requires a corresponding target type.

For example, a property of type int can accept a value represented as a string if the TypeConverter in use supports that conversion.

### 3.2. StandardTypeConverter and ConversionService

Spring provides StandardTypeConverter. This converter delegates its work to Spring's ConversionService. As a result, applications can reuse the Converter, ConverterFactory, and GenericConverter mechanisms instead of writing all type conversion logic specifically for SpEL.

You can supply a custom ConversionService to StandardTypeConverter:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerId.class,
        CustomerId::new
);

StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);
~~~

The example above assumes CustomerId is a domain type with a constructor accepting a String:

~~~java
public record CustomerId(String value) {
}
~~~

When a position in an expression requires CustomerId and the input value is a String, ConversionService can use the newly registered converter.

### 3.3. Explicit conversion and TypeDescriptor

You can access TypeConverter from EvaluationContext to perform conversions directly:

~~~java
TypeConverter converter = context.getTypeConverter();

Object converted = converter.convertValue(
        "42",
        TypeDescriptor.valueOf(String.class),
        TypeDescriptor.valueOf(Integer.class)
);
~~~

The result is an Integer if the converter supports converting String to Integer. canConvert can be called beforehand to check convertibility without performing the conversion.

TypeDescriptor is especially useful with collections and generic types. For example, List<String> and List<Integer> share the same raw class List but require different element conversions. When full generic metadata is provided, ConversionService can handle element types more accurately.

### 3.4. Where to register converters?

If a converter reflects a conversion rule shared across the application, register it on the application-managed ConversionService and pass that service into StandardTypeConverter. This enables other Spring components to reuse the same rule.

If only one evaluation context needs custom behavior, you can create a dedicated ConversionService for that context. Avoid modifying a shared ConversionService solely for one special expression if doing so could affect other processing flows.

TypeConverter only handles type conversion. It does not determine the meaning of addition, comparison, or other operators. If you want to add two domain objects, look at OperatorOverloader.

## 4. OperatorOverloader — defining operators for domain types

### 4.1. Responsibility and API

OperatorOverloader allows an application to define how several built-in SpEL operators execute with custom operands:

~~~java
public interface OperatorOverloader {
    boolean overridesOperation(
            Operation operation,
            Object leftOperand,
            Object rightOperand);

    Object operate(
            Operation operation,
            Object leftOperand,
            Object rightOperand) throws EvaluationException;
}
~~~

SpEL asks overridesOperation to determine whether the custom implementation handles the operation for the current pair of operands. If the method returns true, SpEL calls operate to obtain the result.

Operation represents built-in operation groups such as ADD, SUBTRACT, MULTIPLY, DIVIDE, MODULUS, and POWER. OperatorOverloader extends the behavior of these operators; it does not add new syntax or operator symbols to the SpEL language.

### 4.2. Example: adding two Money objects

Suppose the application has a Money type consisting of an amount and a currency:

~~~java
public record Money(BigDecimal amount, Currency currency) {

    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
    }

    public static Money of(String amount, String currencyCode) {
        return new Money(
                new BigDecimal(amount),
                Currency.getInstance(currencyCode)
        );
    }
}
~~~

The business rule in this example is that only two monetary amounts with the same currency can be added. We can implement OperatorOverloader:

~~~java
public final class MoneyOperatorOverloader
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
    public Object operate(
            Operation operation,
            Object leftOperand,
            Object rightOperand) throws EvaluationException {

        if (operation == Operation.ADD
                && leftOperand instanceof Money left
                && rightOperand instanceof Money right) {

            if (!left.currency().equals(right.currency())) {
                throw new EvaluationException(
                        "Cannot add Money values with different currencies"
                );
            }

            return new Money(
                    left.amount().add(right.amount()),
                    left.currency()
            );
        }

        throw new EvaluationException(
                "Unsupported operation: " + operation
        );
    }
}
~~~

Register the implementation on the context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setOperatorOverloader(
        new MoneyOperatorOverloader()
);
~~~

Once TypeLocator knows the package containing Money, the expression can call the static factory method and add the two results:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "T(Money).of('10.00', 'USD') + " +
        "T(Money).of('5.00', 'USD')"
);

Money total = expression.getValue(context, Money.class);
~~~

The result is a Money with amount 15.00 and currency USD. If the two operands use different currencies, the implementation throws EvaluationException to report an invalid addition according to the business rule.

This example also illustrates how the three extension points can work together: TypeLocator locates the Money class; OperatorOverloader handles addition; TypeConverter can participate wherever argument or assignment value conversion is needed.

### 4.3. Guidelines when writing an OperatorOverloader

- Check the operation and the runtime types of both operands in overridesOperation.
- Only return true for cases the implementation genuinely supports.
- Validate business conditions in operate, such as requiring both currencies to match.
- Throw EvaluationException with a helpful message when operands are invalid.
- Keep behavior predictable; avoid I/O operations or mutating external state inside an operation.
- Support only operations that make sense in the domain. Do not define multiplication or division for Money if the business domain has no clear rule for them.

## 5. Configuring the components in the same EvaluationContext

A single context can configure all three services together:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

// 1. Resolve class names in T(...)
StandardTypeLocator typeLocator = new StandardTypeLocator();
typeLocator.registerImport("com.example.domain");
context.setTypeLocator(typeLocator);

// 2. Convert values according to application rules
DefaultConversionService conversionService =
        new DefaultConversionService();
conversionService.addConverter(
        String.class,
        CustomerId.class,
        CustomerId::new
);
context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

// 3. Define operations for domain types
context.setOperatorOverloader(
        new MoneyOperatorOverloader()
);
~~~

The setters are called before evaluating the expression. The context can be reused if the root object and configured services match the usage scope. If the context holds per-request state or user data, manage its lifecycle separately to avoid unintended state sharing.

In an application with multiple expression groups under different policies, create appropriately configured contexts for each group. This helps limit allowed class references, permitted converters, and supported domain operators.

## 6. Distinguishing the three extension points

| Need | Component to use | Example |
|---|---|---|
| Using T(Money) or T(Math) | TypeLocator | Finding a class by name |
| Assigning a String to an Integer property | TypeConverter | Converting "42" to 42 |
| Adding two Money values | OperatorOverloader | Money + Money |
| Calling a static method after finding a class | TypeLocator, followed by method invocation mechanism | T(Math).max(1, 2) |
| Passing an argument requiring type conversion to a method | TypeConverter | Converting the argument to the parameter type |

A quick way to choose:

1. If the issue is that a class name cannot be found, check TypeLocator.
2. If the class is right but a value cannot be assigned or passed into a parameter, check TypeConverter and ConversionService.
3. If both operands have valid types but the operation does not carry the desired meaning, check OperatorOverloader.

Do not use TypeConverter to simulate object addition. Likewise, do not use OperatorOverloader to convert a String into a target type.

## 7. Common errors and how to handle them

| Symptom | Possible cause | Resolution direction |
|---|---|---|
| Type cannot be found when evaluating T(...) | Wrong class name or TypeLocator lacks the matching import | Use the fully qualified name or register the import prefix |
| Class is found but static method cannot be called | Method does not exist, is not public, or arguments do not match | Check the method signature and type conversion capability |
| Cannot convert value to property type | ConversionService lacks a corresponding converter | Register an appropriate Converter/GenericConverter |
| Collection converts elements to wrong type | Incomplete generic metadata or unsuitable element converter | Check TypeDescriptor and element types |
| Custom operator does not run | overridesOperation returns false or operands have unexpected runtime types | Check Operation and the types of both operands |
| Addition runs but result violates domain rules | Logic in operate does not fully check business conditions | Add validation and specific EvaluationException errors |

When debugging, split large expressions into smaller expressions. Testing type resolution, argument conversion, and operations individually helps pinpoint the exact extension point causing the error.

## 8. Restricting expression permissions and safety

StandardEvaluationContext provides full SpEL evaluation capabilities and can access many features such as type references, methods, properties, constructors, or beans depending on configuration. Therefore, do not directly evaluate expressions submitted by untrusted users using a context with broad access permissions.

Several principles to apply:

- If T(...) is allowed, use a TypeLocator with a real allowlist when class restriction is needed. Limiting import prefixes on StandardTypeLocator alone is not enough to block fully qualified class names.
- Only register the method resolvers, property accessors, bean resolvers, and constructor resolvers that expressions genuinely need.
- Custom converters should have clear behavior, restrict source/target types, and avoid unnecessary side effects.
- OperatorOverloader should only support operations defined in the business domain and validate operands before executing.
- Do not treat TypeLocator or TypeConverter alone as a security boundary for all of SpEL.

If only property access and a limited set of methods are needed, consider SimpleEvaluationContext. It is an intentional choice for a SpEL subset and does not provide full features such as type references, constructors, and bean references. Choose the context matching the exact level of expression power the application requires.

## 9. Summary

TypeLocator, TypeConverter, and OperatorOverloader are three independent extension points in the SpEL evaluation process:

- TypeLocator turns a type name in an expression into a Java class.
- TypeConverter converts values according to source type, target type, and TypeDescriptor metadata.
- OperatorOverloader defines how built-in operators execute with custom domain types.

When implementing, start from StandardEvaluationContext, replace only the services that need customization, and carefully verify the permissions that expressions are allowed to use. Clear configuration enables SpEL to integrate with the application's domain data types while keeping behavior understandable, controllable, and easy to maintain.
