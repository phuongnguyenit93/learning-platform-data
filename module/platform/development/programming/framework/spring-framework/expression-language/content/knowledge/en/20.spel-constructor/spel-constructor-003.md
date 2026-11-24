# Creating Objects with Constructor Arguments

Spring Expression Language (SpEL) allows creating Java objects directly inside an expression using the **new** syntax. An expression can invoke a no-arg constructor, a constructor with arguments, overloaded constructors, or nest one constructor call inside another. Arguments are evaluated in the EvaluationContext and can be converted to parameter types through TypeConverter when the configuration supports it.

This capability is useful when you need to create a value object, a small data object, or an argument to pass into a method. However, distinguish creating an object with SpEL from Spring creating a bean in ApplicationContext: constructor invocation does not automatically perform dependency injection, scope management, lifecycle callbacks, or Spring AOP.

## 1. Object Creation Syntax

### 1.1. Invoking a Constructor with new

General syntax:

~~~java
new FullyQualifiedClassName(argument1, argument2, ...)
~~~

Example creating a String:

~~~java
new String('Spring Expression Language')
~~~

Example creating a domain object:

~~~java
new com.example.domain.Customer('C-100', 'An')
~~~

SpEL looks up the class by its type name, selects the constructor matching the arguments, and invokes that constructor when the expression is evaluated.

You do not need **T(...)** before the class name when calling a constructor. **T(...)** is used to reference a type, usually to access static members; **new ...(...)** is used to create an instance.

### 1.2. No-Argument Constructor

If the class has an accessible no-arg constructor, the expression can create an object without passing arguments:

~~~java
new com.example.domain.SearchCriteria()
~~~

Example:

~~~java
public class SearchCriteria {

    private String keyword;

    public SearchCriteria() {
    }

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }
}
~~~

The expression above creates a new SearchCriteria. Fields receive Java's default values or whatever values the constructor assigns.

Successful creation depends on the class being on the classpath, TypeLocator resolving the class name, and a matching constructor being invocable.

### 1.3. Constructor with Arguments

For constructors requiring initial data, pass arguments in the declared parameter order:

~~~java
public class Customer {

    private final String code;
    private final String name;

    public Customer(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }
}
~~~

Expression:

~~~java
new com.example.domain.Customer('C-100', 'An')
~~~

The first argument is used for code, and the second for name. Order and convertibility must match an accessible constructor.

### 1.4. Result Type

Constructor invocation returns an instance of the created class. You can receive the result with a specific type:

~~~java
Customer customer = parser
        .parseExpression(
                "new com.example.domain.Customer('C-100', 'An')"
        )
        .getValue(context, Customer.class);
~~~

Or receive it as Object when the result type is not known in advance:

~~~java
Object value = parser
        .parseExpression(
                "new com.example.domain.Customer('C-100', 'An')"
        )
        .getValue(context);
~~~

If the constructor returns an object of the exact requested type, no result conversion is needed. The type parameter in **getValue(context, Target.class)** is a result-type request from the caller; it differs from converting arguments before invoking the constructor.

## 2. Resolving Class Names with TypeLocator

### 2.1. Fully Qualified Class Name

The class name in a constructor expression is resolved through the EvaluationContext's TypeLocator. The clearest approach is using the fully qualified name with package and class:

~~~java
new com.example.domain.Customer('C-100', 'An')
~~~

The fully qualified name avoids depending on import prefixes and reduces the chance of class name collisions.

### 2.2. Using Import Prefixes with StandardTypeLocator

StandardTypeLocator supports registering package prefixes so shorter class names can be written:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("com.example.domain");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

After registering the package, you can write:

~~~java
new Customer('C-100', 'An')
~~~

The **java.lang** package is registered by default in StandardTypeLocator, so classes like String can be referenced by their short name.

Import prefixes only assist in resolving short names. If you need to restrict which classes are allowed to be instantiated, do not treat StandardTypeLocator's import list as a security allowlist. Fully qualified class names can still be resolved. When true restriction is needed, use a custom TypeLocator that enforces an allowlist.

### 2.3. Configuring ClassLoader

StandardTypeLocator can be created with a specific ClassLoader:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator(applicationClassLoader);
~~~

This is useful when the application runs in an environment with multiple class loaders, plugins, or modules. The ClassLoader must be able to see the class to be instantiated.

If the class is not on the classpath or the chosen ClassLoader cannot load it, the constructor expression will fail during evaluation.

## 3. Constructor Arguments as SpEL Expressions

### 3.1. Using Literals as Arguments

Common literals can be passed directly:

~~~java
new com.example.domain.Customer('C-100', 'An')
new java.math.BigDecimal('125.50')
new java.lang.String('hello')
~~~

The literal type affects the argument type SpEL supplies for constructor resolution. If the constructor requires a different type, TypeConverter may participate when an appropriate conversion exists.

### 3.2. Using Properties of the Root Object

Arguments do not need to be fixed literals. Data can be read from the root object:

~~~java
new com.example.domain.Customer(order.customerCode, order.customerName)
~~~

During evaluation, SpEL reads the properties from the root object and passes the corresponding values into the constructor.

If an intermediate property might be null, check it beforehand or use safe navigation where appropriate. A constructor can accept null for reference types, but cannot accept null for primitive parameters.

### 3.3. Using Variables in EvaluationContext

Data prepared by the application can be passed via variables:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customerCode", "C-100");
context.setVariable("customerName", "An");
~~~

Expression:

~~~java
new com.example.domain.Customer(#customerCode, #customerName)
~~~

Variables are referenced with **#**. This separates data from the expression string, which is especially useful when data comes from requests or a database.

Do not concatenate user values directly into the expression source. Keep the expression fixed and pass values via context variables so data is not re-interpreted as SpEL syntax.

### 3.4. Nesting Constructor Expressions

An argument can be another constructor expression:

~~~java
new com.example.domain.Order(
    'O-100',
    new com.example.domain.Customer('C-100', 'An')
)
~~~

This example creates a Customer first to pass as an argument to the Order constructor. Nested expressions help describe small object graphs within a single expression.

If the structure has many layers or many objects, create the objects in Java and pass the completed object into the context. Overly long expressions are hard to read, hard to debug, and hard to control in cost.

## 4. Type Conversion of Constructor Arguments

### 4.1. How Does TypeConverter Participate?

A constructor has a signature defining its parameter types. If an argument in the expression has a different type, SpEL can ask TypeConverter to convert the value to the target type when a matching converter exists.

Constructor example:

~~~java
public class Customer {
    public Customer(Long id) {
        // Initialize
    }
}
~~~

Expression passing a String:

~~~java
new com.example.domain.Customer('42')
~~~

If TypeConverter supports String to Long, the argument can be converted to a Long value before the constructor is called.

Conversion capability depends on the configured TypeConverter and ConversionService. Do not assume every pair of types converts automatically.

### 4.2. StandardTypeConverter and ConversionService

StandardEvaluationContext uses a default TypeConverter based on Spring's conversion mechanism. An application can provide its own ConversionService:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);
~~~

If you need to convert a String into a domain type, register a converter on ConversionService:

~~~java
public record CustomerCode(String value) {
}
~~~

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

Constructor:

~~~java
public class Customer {
    public Customer(CustomerCode code) {
        // Initialize
    }
}
~~~

Expression:

~~~java
new com.example.domain.Customer('C-100')
~~~

TypeConverter can use the registered converter to create a CustomerCode before calling the constructor.

The converter should validate data and reject invalid values according to domain rules. Succeeding in Java type conversion does not guarantee that the data is valid for the business domain.

### 4.3. Null and Primitives

Reference-type parameters can accept null if the constructor and domain allow it:

~~~java
new com.example.domain.Customer(null, 'An')
~~~

By contrast, primitive parameters such as **int**, **long**, or **boolean** cannot accept null. If an argument is null or cannot be converted to a primitive, the constructor call will fail.

When data may be missing, explicitly decide whether to use a wrapper such as Integer or validate required values before creating the object. Do not replace null with 0 or false unless the business domain has defined that default value.

## 5. Constructor Overloading

### 5.1. Classes with Multiple Constructors

Java allows a class to declare multiple constructors with the same name but different parameter lists:

~~~java
public class SearchCriteria {

    public SearchCriteria() {
    }

    public SearchCriteria(String keyword) {
    }

    public SearchCriteria(String keyword, int pageSize) {
    }
}
~~~

SpEL must choose the constructor matching the number and types of arguments:

~~~java
new com.example.domain.SearchCriteria()
~~~

~~~java
new com.example.domain.SearchCriteria('spring')
~~~

~~~java
new com.example.domain.SearchCriteria('spring', 20)
~~~

Each expression supplies a different number of arguments and can resolve to a different constructor.

### 5.2. When Argument Types Differ from Parameter Types

Constructor resolution examines type compatibility and convertibility. For example, a numeric literal might have a different type from the constructor parameter type; TypeConverter can help convert if suitable.

Do not rely on guessing that the constructor closest to the literal type will always be picked in every case. If multiple constructors can accept an argument after conversion, the result depends on Spring's resolution rules and converter configuration.

To avoid ambiguity:

- Keep the number of overloads moderate.
- Avoid multiple constructors with parameter types that easily convert between one another.
- Use explicit argument types when possible.
- Test each case against the actual Spring version in use.
- Consider named static factory methods when different initialization modes carry different meanings.

### 5.3. Varargs Constructors

Java also allows constructors with varargs parameters:

~~~java
public class TagSet {

    private final String[] tags;

    public TagSet(String... tags) {
        this.tags = tags;
    }
}
~~~

You can write an expression passing multiple arguments:

~~~java
new com.example.domain.TagSet('java', 'spring', 'spel')
~~~

Varargs constructor resolution and per-element conversion should be tested with the exact Spring version and TypeConverter used by the application. When multiple varargs overloads exist, the chance of ambiguity increases; keep the instantiation API simple and clearly typed.

## 6. Constructor Invocation vs. Spring Bean Creation

### 6.1. Directly Created Objects

The expression:

~~~java
new com.example.domain.Customer('C-100', 'An')
~~~

invokes the Java constructor to create a new instance. This object is not automatically registered in ApplicationContext.

Consequently, it does not automatically receive:

- Dependency injection from Spring.
- Bean lifecycle callbacks like a regular Spring bean.
- Container-managed bean scopes.
- AOP proxies or interceptors configured through Spring.
- Post-processors applied during container bean creation.

If the constructor needs a dependency, the expression must pass that dependency as an argument if the design allows; SpEL does not automatically autowire dependencies into a newly created object.

### 6.2. When Should Constructor Expressions Be Used?

Constructor expressions are suitable for:

- Small, immutable value objects.
- DTOs or simple data objects.
- Temporary arguments for a method.
- Domain types with clear constructors and minimal side effects.

Example:

~~~java
new com.example.domain.Money('125.50', 'VND')
~~~

### 6.3. When Should Spring Beans Be Used?

If an object needs dependency injection, lifecycle management, scope, proxies, or container configuration, let Spring create and manage that object. When an expression needs to invoke a bean, use a bean reference with a properly configured and restricted BeanResolver.

Do not use **new** to try to construct a complex Spring service. Calling the constructor directly can create an object missing dependencies or bypass mechanisms the application expects from the container.

## 7. ConstructorResolver and Accessibility

### 7.1. Constructor Resolution Mechanism

EvaluationContext has a ConstructorResolver to find a matching constructor. StandardEvaluationContext uses Spring's reflection-based resolver by default.

General flow:

1. TypeLocator resolves the class name into a Class.
2. ConstructorResolver finds a constructor that can accept the arguments.
3. TypeConverter assists with argument conversion when needed.
4. ConstructorExecutor executes the constructor and returns the instance.

TypeLocator, ConstructorResolver, and TypeConverter have distinct responsibilities. If the class name fails to resolve, check TypeLocator. If no matching constructor is found, check constructor signatures and visibility. If an argument has the wrong type, check TypeConverter.

### 7.2. Constructors Must Be Accessible

Use public constructors for types instantiated from expressions. Private or package-private constructors may not be accessed by the default resolver as intended; do not rely on reflection access bypassing application visibility boundaries.

If the class has no matching constructor or the constructor cannot be invoked in the current environment, SpEL will raise an error during evaluation.

### 7.3. ClassLoader and Modules

In applications with separate modules or class loaders, a class may exist yet not be visible to the TypeLocator's ClassLoader. Reflection access can also be restricted by the module system or runtime configuration.

Verify the classpath, ClassLoader, and constructor accessibility in the actual deployment environment, not only in the IDE.

## 8. Combining Constructors with Methods and Collections

A constructor expression can be used as an argument to a method:

~~~java
#orderService.create(
    new com.example.domain.Customer('C-100', 'An')
)
~~~

You can create an object and immediately access a member or method on it in the same expression:

~~~java
new com.example.domain.Money('100.00', 'VND').amount
~~~

You can also create a collection containing new objects:

~~~java
{
    new com.example.domain.Customer('C-100', 'An'),
    new com.example.domain.Customer('C-200', 'Binh')
}
~~~

These expressions are useful for small data with simple structure. If the list is long or the object graph is complex, prepare it in Java for easier validation, testing, and lifecycle management.

A constructor expression creates a new instance when evaluated. If the expression is evaluated multiple times, the constructor can be called multiple times. Do not assume objects are cached or shared across evaluations.

## 9. Common Errors When Instantiating Objects

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| Type not found | Wrong class name or TypeLocator cannot resolve it | Use fully qualified name or register import prefix |
| Constructor not found | Wrong argument count or no matching signature | Check constructor and parameter order |
| Constructor not accessible | Visibility or reflection/module restriction | Use a public constructor and check runtime |
| Argument cannot be converted | TypeConverter lacks an appropriate converter | Configure ConversionService or fix input type |
| Null passed to primitive | Primitives cannot accept null | Use wrapper or validate beforehand |
| Unexpected overload selected | Multiple constructors compatible after conversion | Reduce overloads, clarify argument types |
| Constructor throws exception | Validation or initialization logic failed | Handle errors in the Java layer and preserve the cause |
| Object missing dependencies | Confused constructor invocation with Spring bean creation | Let the container create the bean or pass dependencies explicitly |
| Hard-to-read nested expressions | Object graph constructed directly is too complex | Prepare objects in Java and put them in context |

Successful parsing only means the expression syntax is valid. Looking up the class, picking the constructor, converting arguments, and running the constructor occur during evaluation, so these errors usually appear in the evaluation phase.

## 10. Security Boundaries When Allowing Constructor Expressions

A constructor expression can instantiate classes that TypeLocator resolves. If untrusted users can control expressions and the context allows broad type references, they may request creation of unintended objects.

Some principles:

- Do not evaluate untrusted expressions with an overly permissive StandardEvaluationContext.
- If restricting classes is needed, use a custom TypeLocator with a real allowlist.
- Do not let users supply class names and concatenate them directly into the expression source.
- Provide only the necessary root object and variables.
- Restrict constructors of classes that have side effects, system access, or large resource allocations.
- Control object counts and input data sizes.
- Consider SimpleEvaluationContext when only a restricted SpEL feature set is needed; this context does not provide constructor references like StandardEvaluationContext.
- Do not treat a TypeLocator allowlist as the sole security boundary if the context still permits broad method calls or bean access.

A constructor can execute whatever logic its code was written to perform. Therefore, prefer lightweight, deterministic constructors without I/O or unintended side effects.

## 11. Complete Example

Suppose we have value objects CustomerCode and Customer:

~~~java
public record CustomerCode(String value) {
    public CustomerCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer code is required"
            );
        }
    }
}

public record Customer(
        CustomerCode code,
        String name
) {
}
~~~

Configure TypeLocator and TypeConverter:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("com.example.domain");

context.setTypeLocator(typeLocator);
context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

context.setVariable("customerName", "An");
context.setVariable("customerCode", "C-100");
~~~

Create the object with a constructor expression:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Customer customer = parser
        .parseExpression(
                "new Customer(#customerCode, #customerName)"
        )
        .getValue(context, Customer.class);
~~~

SpEL resolves the Customer class via the import prefix, evaluates the two variables, converts customerCode from String to CustomerCode via ConversionService, and then invokes the matching constructor.

In practice, classes and records must reside in the registered package and be visible to the ClassLoader. If using the fully qualified name, the import registration step can be omitted.

## 12. Testing Constructor Expressions

Valid and failure cases should be tested separately:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Customer customer = parser
        .parseExpression(
                "new com.example.domain.Customer(" +
                "new com.example.domain.CustomerCode('C-100'), 'An')"
        )
        .getValue(context, Customer.class);

assertEquals("C-100", customer.code().value());
assertEquals("An", customer.name());
~~~

Beyond the success case, test:

- No-argument constructor.
- Single-argument and multi-argument constructors.
- Overloads sharing the same class name.
- Null arguments for reference and primitive types.
- Converting String to a domain type.
- Invalid constructor input data.
- Constructors throwing exceptions.
- Class names not resolved by TypeLocator.
- Constructors lacking appropriate accessibility.
- Expressions nesting constructors and methods.
- Expressions evaluated multiple times to confirm each evaluation creates a new instance as designed.

With custom converters, test valid values, empty strings, null, and malformed data. Do not only check that the object was created; verify domain invariants after construction.

## 13. Summary

SpEL creates Java objects using the syntax **new FullyQualifiedClassName(arguments)**. TypeLocator resolves the class name, ConstructorResolver chooses the constructor, TypeConverter converts arguments when needed, and the constructor creates the instance during evaluation.

Use fully qualified class names or explicit import prefixes, design public constructors with simple signatures, control overloads, and test argument conversions. Remember that directly created objects are not Spring beans and do not automatically receive dependency injection, lifecycle management, or AOP.

For user-controlled expressions, restrict instantiable classes, input data, and constructor cost. If a Spring-managed service is needed, let the container create the bean and expose only a narrow, access-controlled API to the expression.