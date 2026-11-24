# StandardEvaluationContext and Extensibility

## 1. What is StandardEvaluationContext?

In SpEL, the parser converts a string into an Expression, while EvaluationContext provides the environment in which the expression is evaluated. The context determines what the root object is, which variables exist, and which mechanisms the expression can use to access properties, invoke methods, look up beans, create objects, or convert types.

StandardEvaluationContext is the full-featured implementation of EvaluationContext. It is suitable when the application needs flexible control over how SpEL interacts with objects and application services.

Basic example:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("minimum", 1000);
    context.setVariable("active", true);

    Expression expression = parser.parseExpression(
        "#active and #minimum >= 500"
    );

    Boolean result =
        expression.getValue(context, Boolean.class);

The Expression is parsed first. When getValue is called, SpEL reads variables from the context, evaluates the operators, and then returns the result.

StandardEvaluationContext is not a parser and does not create expressions itself. It is the environment that an expression uses during the evaluation phase.

## 2. Root object

The root object is the default object that an expression accesses when no variable prefix or bean reference is used.

You can pass the root object when creating the context:

    StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

Or set it later:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setRootObject(customer);

If customer has properties name and age, the expression can be written as:

    name
    age >= 18

There is no need to write #customer because customer is currently the root object.

You can read the root object using the API:

    Object root = context.getRootObject().getValue();

If no root object is set, an expression can still work with literals, variables, or configured bean references. However, a property expression without a prefix needs a suitable root object to access.

Choose a root object with an appropriately scoped set of data. If you put a large entity or a service with many methods as the root, the expression may see more capabilities than actually needed.

## 3. Variables and functions

StandardEvaluationContext allows registering variables using setVariable:

    context.setVariable("customerName", "Lan");
    context.setVariable("orderTotal", 1200);

In an expression, reference a variable using the # symbol:

    #customerName
    #orderTotal >= 1000

Variables can be updated while the context is still in use:

    context.setVariable("orderTotal", 1500);

When the expression is evaluated again, it reads the current value of the variable in the context.

Functions are also registered in the variable/function namespace. StandardEvaluationContext provides registerFunction to register a Method or MethodHandle:

    Method normalizeMethod =
        RuleFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

    context.registerFunction(
        "normalizeCode",
        normalizeMethod
    );

Calling the function:

    #normalizeCode('  vn  ')

Because functions and variables share the same namespace, you should not give both the same name.

## 4. Default capabilities of StandardEvaluationContext

StandardEvaluationContext provides default mechanisms for SpEL to work with Java objects.

| Component | Responsibility |
| --- | --- |
| PropertyAccessor | Reads or writes properties and fields according to the accessor's capabilities |
| MethodResolver | Finds a suitable method to invoke |
| ConstructorResolver | Finds a suitable constructor to create an object |
| BeanResolver | Looks up a bean by name |
| TypeLocator | Finds a class by name in type references or constructor expressions |
| TypeConverter | Converts values between types |
| TypeComparator | Compares two values |
| OperatorOverloader | Extends how certain operators are handled |

StandardEvaluationContext uses default implementations based on reflection and standard SpEL mechanisms for many operations. Some capabilities still require explicit configuration: for example, to use @beanName in a standalone expression, you must register a suitable BeanResolver.

You can replace or supplement these components when the default behavior does not fit the application's object model or rules.

## 5. PropertyAccessor: customizing how properties are read and written

PropertyAccessor is responsible for accessing properties on a target object. ReflectivePropertyAccessor is a common accessor for working with JavaBeans and fields via reflection.

An application can register its own accessor:

    context.addPropertyAccessor(
        new CustomPropertyAccessor()
    );

A custom PropertyAccessor usually needs to define:

- The target object types that the accessor supports.
- Which properties can be read.
- How to retrieve the value when reading.
- Which properties can be written.
- How to update the value when writing.

Read and write operations are represented through canRead/read and canWrite/write.

For example, an application has a configuration object that only stores data in an internal Map. A custom accessor can map SpEL property names to corresponding keys in the Map, instead of requiring the object to have a getter for every key.

Restrict the accessor to the exact target types and allowed properties. An overly broad accessor can allow expressions to access data outside the original design.

If read-only access is needed, disallow writing or only register an accessor with read behavior. Being able to read a property does not mean that property should be allowed to be modified.

## 6. MethodResolver: controlling method invocation

MethodResolver finds a method matching the target object, method name, and argument types.

StandardEvaluationContext has reflective method resolution by default. You can add a custom resolver:

    context.addMethodResolver(
        new CustomMethodResolver()
    );

A custom MethodResolver is suitable when the application wants to expose a limited method API, map calls to another operation, or apply special method selection rules.

When designing a resolver, you need to determine:

- Which target classes are supported.
- Which method names are allowed.
- The number and types of arguments.
- How type conversion is handled, if applicable.
- How MethodExecutor performs the invocation.
- What error is returned when a method is invalid.

Do not allow invoking all methods just because the target is a Java object. An object may contain methods that read data, mutate state, access files, or call external systems.

If an expression does not need method invocation, restrict or omit that capability from the context.

## 7. ConstructorResolver: controlling object creation

ConstructorResolver finds a matching constructor when an expression uses the new operator.

Example:

    new com.example.Customer('Lan', 30)

StandardEvaluationContext has reflective constructor resolution by default. You can add a custom resolver:

    context.addConstructorResolver(
        new CustomConstructorResolver()
    );

A custom resolver can restrict which classes can be created, which constructors can be called, or how arguments are mapped.

This is useful when the application needs a set of allowed classes for instantiation, or needs to apply custom object creation rules.

If an expression does not need to create objects, there is no need to expose constructor invocation. For expressions from untrusted sources, constructor invocation capability can significantly expand the scope of actions an expression can perform.

## 8. BeanResolver: connecting expressions with the Spring container

BeanResolver allows an expression to look up a bean by name using the @beanName syntax.

Example:

    @pricingService.calculate(#amount)

When manually creating a StandardEvaluationContext in Java, you need to register a BeanResolver:

    context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
    );

After that, the expression can reference beans managed by the BeanFactory.

BeanResolver is only responsible for looking up beans. Reading properties or invoking methods on the bean still uses PropertyAccessor and MethodResolver respectively.

Do not put the entire ApplicationContext into the root object or a variable just so an expression can look up data. Provide a bean resolver only when truly needed and control which beans expressions can reference.

## 9. TypeLocator: controlling how classes are located

TypeLocator is used when an expression needs to reference a Java type, such as the T() operator or a new constructor expression.

Example:

    T(java.math.BigDecimal)
    new java.util.ArrayList()

StandardTypeLocator is the standard implementation. By default, the java.lang package is recognized, so short names can be used for some classes in that package.

You can register package imports:

    StandardTypeLocator typeLocator =
        new StandardTypeLocator();

    typeLocator.registerImport("com.example");

    context.setTypeLocator(typeLocator);

After that, expressions can reference classes in the imported package by short name when there is no conflict.

You can provide an appropriate ClassLoader when the application runs in an environment with a custom class loader:

    StandardTypeLocator typeLocator =
        new StandardTypeLocator(
            MyApplication.class.getClassLoader()
        );

    context.setTypeLocator(typeLocator);

TypeLocator locates the class; ConstructorResolver decides which constructor is called when using new. These two components have separate responsibilities.

## 10. TypeConverter: converting values

TypeConverter converts values from a source type to a target type when required by an expression or property access.

For example, the age property has type int, but the value passed in is a string:

    context.setVariable("ageText", "30");

    Expression expression =
        parser.parseExpression("#ageText");

    Integer age =
        expression.getValue(context, Integer.class);

SpEL can use the context's TypeConverter to convert String to Integer if conversion is supported.

You can register a custom TypeConverter:

    context.setTypeConverter(customTypeConverter);

An application can also integrate a suitable ConversionService through StandardTypeConverter.

When customizing a converter, define the source type, target type, null rules, locale, format, and behavior when data is invalid. Do not make conversions overly broad, causing expressions to silently accept malformed data.

## 11. TypeComparator and OperatorOverloader

TypeComparator determines how two values are compared in cases where SpEL needs to compare specific data types.

You can register a custom comparator:

    context.setTypeComparator(customTypeComparator);

For example, an application has a custom version type and needs comparison rules by major/minor/patch instead of ordinary string comparison.

OperatorOverloader allows extending the behavior of certain operators for custom data types.

Registration:

    context.setOperatorOverloader(
        customOperatorOverloader
    );

Use these extensions only when the data type or business rule genuinely needs behavior different from the default. If used too broadly, the same expression may carry different meanings across contexts and become hard to debug.

Document the supported comparison or overloading rules clearly and test with boundary values.

## 12. Order and scope of extensions

A context can contain multiple PropertyAccessors or MethodResolvers. Selecting the appropriate implementation depends on the target, property/method name, and each component's support capabilities.

When registering multiple extensions:

- Only add an accessor/resolver for the object types that need support.
- Avoid having two extensions accept the same target and both claim to handle the same property/method without a clear reason.
- Control the order in the configured list of accessors or resolvers.
- Clearly define which extension handles first and which fallback is allowed.
- Do not arbitrarily mutate the registry between evaluations.

If a custom accessor handles every target too broadly, it may intercept cases that should have been handled by the default accessor. If a custom resolver returns an executor for methods too generically, unintended invocations may be accepted.

Designing narrow extensions makes behavior predictable and easy to test.

## 13. Example of configuring a context with multiple capabilities

The following example illustrates how to configure a root object, variable, function, and bean resolver:

    ExpressionParser parser =
        new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext(orderFacts);

    context.setVariable("minimum", new BigDecimal("1000"));

    Method normalizeMethod =
        RuleFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

    context.registerFunction(
        "normalizeCode",
        normalizeMethod
    );

    context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
    );

    Expression expression = parser.parseExpression(
        "total >= #minimum and " +
        "#normalizeCode(region) == 'VN'"
    );

    Boolean eligible =
        expression.getValue(context, Boolean.class);

In the example:

- orderFacts is the root object.
- minimum is a variable.
- normalizeCode is an explicitly registered function.
- BeanResolver is configured so the expression can reference beans if needed.

This example demonstrates extensibility. In a rule that only needs a root object, variables, and functions, there is no need to register a BeanResolver just because the context can support it.

## 14. StandardEvaluationContext and SimpleEvaluationContext

StandardEvaluationContext supports a full range of SpEL features and is suitable for expressions controlled by the application.

SimpleEvaluationContext is designed for data binding and property-based expressions with a more limited feature set.

| Criterion | StandardEvaluationContext | SimpleEvaluationContext |
| --- | --- | --- |
| Root object | Yes | Yes |
| Variables | Yes | Yes |
| Property access | Yes, flexible | Yes, according to builder configuration |
| Method invocation | Yes via resolver | Only when configuration allows |
| Bean references | Yes when BeanResolver is registered | Not supported |
| Type references T() | Yes | Not supported |
| Constructor invocation new | Yes | Not supported |
| Customization | Many resolvers and strategies | More limited feature set |

If you only need to read properties from a DTO, consider a read-only SimpleEvaluationContext:

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

If bean references, constructor invocation, or type references are needed, SimpleEvaluationContext does not satisfy that use case.

Do not choose StandardEvaluationContext just because it has more features. Choose the context according to the exact capabilities the expression needs to use.

## 15. Context lifecycle and reuse

StandardEvaluationContext is a mutable object: the root object, variables, and resolvers/accessors can be updated.

A parsed Expression can be retained for repeated evaluations:

    Expression rule =
        parser.parseExpression("#amount >= #minimum");

For each evaluation, the context must provide the appropriate data:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("amount", amount);
    context.setVariable("minimum", minimum);

    Boolean allowed =
        rule.getValue(context, Boolean.class);

Do not share a mutable context across multiple concurrent requests if those requests update variables or the root object together. Data from one request can overwrite data from another.

A clean way to organize this is to keep the expression immutable when the source does not change, while the context holds dynamic data created per request or per evaluation.

If you want to reuse a pre-configured context, clearly separate immutable configuration from mutable state and ensure usage is concurrency-safe.

## 16. Testing extensions

When adding a custom PropertyAccessor, MethodResolver, or TypeConverter, test both success and failure cases.

You should have test groups for:

1. Supported target class and valid property/method.
2. Unsupported target class.
3. Non-existent property or method.
4. Null or wrong-type arguments.
5. Valid and invalid type conversions.
6. Multiple resolvers capable of handling the same target.
7. Missing root object or variable.
8. Unconfigured BeanResolver or non-existent bean name.
9. Write operations rejected in a read-only context.
10. Two concurrent requests evaluating with different context data.

Test expressions through both parse and getValue. Successful parsing does not guarantee that a resolver can handle the target at runtime.

When a custom extension changes behavior, directly test the extension's contract and the expressions that use it. This helps catch configuration errors before deploying rules to production.

## 17. Security and the least privilege principle

StandardEvaluationContext is powerful because it can expose many access capabilities. If an expression comes from an untrusted source, providing a broad root object or resolvers can create risk.

Principles:

- Do not evaluate untrusted expressions using a StandardEvaluationContext with full privileges.
- Only provide a root object or DTO containing the necessary data.
- Only register variables and functions that are truly needed.
- Do not register a BeanResolver if the expression does not need beans.
- Restrict PropertyAccessor and MethodResolver.
- Do not expose a broad ConstructorResolver or TypeLocator if unnecessary.
- Avoid methods with side effects, I/O, or administrative privileges in the rule's context.
- Use SimpleEvaluationContext for limited data-binding cases, while also inspecting all objects and extensions that remain exposed.

SimpleEvaluationContext only limits the language feature set; it does not automatically protect data or methods accessible through the provided objects, accessors, resolvers, variables, or functions.

Treat every extension as a permission granted to the expression. Only grant the permissions necessary for the specific type of rule.

## 18. Common errors

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Property cannot be read | No matching accessor or incorrect getter | Check the target class and PropertyAccessor |
| Property cannot be written | Accessor does not support write or context is read-only | Check canWrite/write and context configuration |
| Method not found | MethodResolver could not select the method | Check the name, arguments, and resolver |
| Constructor not found | TypeLocator or ConstructorResolver cannot handle the class | Check the class name, ClassLoader, and constructor |
| @beanName fails | BeanResolver not registered | Configure BeanFactoryResolver if actually needed |
| T() cannot find class | TypeLocator or package import is not suitable | Use fully qualified name or configure TypeLocator |
| Value cannot be converted | TypeConverter does not support source/target types | Check conversion and format |
| Comparison yields unexpected result | TypeComparator or data type differs from expectation | Check actual types and comparison rules |
| Operator does not work with custom type | OperatorOverloader is not configured | Register an overloader with a clear scope |
| Rule has unexpected access permissions | Root object or resolver is too broad | Narrow down the context and extensions |

When debugging, determine whether the expression fails during parsing or evaluation. Then inspect the component responsible for the failing operation instead of changing the entire context at once.

## 19. Key takeaways

- StandardEvaluationContext is the full-featured implementation of EvaluationContext.
- Root object provides the default object for property expressions.
- Variables are referenced with #name; functions are called with #functionName(...).
- PropertyAccessor reads/writes properties; MethodResolver finds methods; ConstructorResolver finds constructors.
- BeanResolver looks up beans; TypeLocator locates classes.
- TypeConverter converts types; TypeComparator compares values; OperatorOverloader extends operators.
- Extensions can be added or replaced based on application needs.
- The order and scope of accessors/resolvers need to be controlled when multiple implementations exist.
- StandardEvaluationContext does not automatically register a BeanResolver for a standalone context.
- SimpleEvaluationContext restricts features and is more suitable for controlled data binding.
- Retain Expression for reuse, but manage mutable context per request or per evaluation.
- Do not use StandardEvaluationContext to evaluate untrusted expressions; restrict the root object and all extensions according to least privilege.

When extending StandardEvaluationContext, start from the operations the expression genuinely needs. Choose the right extension, restrict its targets and permissions, and test both success and failure behaviors. A small, clear context makes rules easier to maintain and easier to control.

## References

- Spring Framework Reference — Evaluation: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Reference — EvaluationContext and Type Conversion: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html
- Spring Framework Javadoc — StandardEvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html
- Spring Framework Javadoc — EvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html
- Spring Framework Javadoc — PropertyAccessor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html
