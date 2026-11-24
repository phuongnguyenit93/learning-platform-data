# Instantiating Types by Fully Qualified Name in SpEL

Spring Expression Language (SpEL) supports creating objects directly inside an expression using the `new` operator. When creating an instance, the expression specifies the type name and passes arguments to the corresponding constructor. Writing the fully qualified class name clearly identifies the class to instantiate, especially when the class is outside the `java.lang` package or when the application has multiple classes with the same name.

Example:

    new java.lang.String('Spring Expression Language')
    new java.math.BigDecimal('123.4500')
    new com.example.domain.Customer('An', 25)

SpEL must locate the class first, then resolve the matching constructor and perform instantiation. These two steps involve TypeLocator and ConstructorResolver in EvaluationContext.

## 1. Constructor Invocation Syntax

Basic syntax:

    new fully.qualified.ClassName(argument1, argument2, ...)

Where:

- `new` is the keyword that creates an instance.
- `fully.qualified.ClassName` is the class name, consisting of the package and the class name.
- The argument list is enclosed in parentheses; it can be empty if the class has a no-arg constructor.

Examples of creating a String and a BigDecimal:

    new java.lang.String('Hello')
    new java.math.BigDecimal('19.99')

Example of creating a domain object:

    new com.example.domain.Customer('Lan', 'lan@example.com')

The selected constructor must match the number and types of arguments. If the class has no corresponding constructor or the constructor is not accessible, the expression will fail when evaluated.

Using the fully qualified name avoids relying on default imports and makes clear which class is being created. This is a suitable choice for expressions stored in configuration or shared across multiple modules.

## 2. Difference Between Fully Qualified Names and Short Class Names

StandardTypeLocator supports the `java.lang` package by default. Therefore, some classes in this package can be referenced by their short name:

    new String('Hello')
    new Integer('42')

For classes outside `java.lang`, the clear and reliable approach is to use the fully qualified name:

    new java.util.Date()
    new java.math.BigDecimal('123.45')

If you write:

    new BigDecimal('123.45')

then SpEL needs TypeLocator to know about the `java.math` package to find the BigDecimal class. Without an appropriate import, the parser may accept the expression structure, but the evaluation step will fail to resolve the type.

Do not assume every Java package or application package is imported automatically. When unsure about the TypeLocator configuration, use the fully qualified name to avoid depending on imports.

## 3. TypeLocator Locates the Class Before Creating an Instance

EvaluationContext provides a TypeLocator to look up a class by the name written in the expression. StandardEvaluationContext uses StandardTypeLocator by default.

Example:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    ExpressionParser parser = new SpelExpressionParser();

    BigDecimal amount = parser.parseExpression(
            "new java.math.BigDecimal('123.4500')"
    ).getValue(context, BigDecimal.class);

In this example, SpEL uses TypeLocator to find `java.math.BigDecimal`, then finds the constructor taking a String and creates the object.

You can configure import prefixes on StandardTypeLocator:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    StandardTypeLocator typeLocator =
            new StandardTypeLocator();

    typeLocator.registerImport("java.math");
    context.setTypeLocator(typeLocator);

    ExpressionParser parser = new SpelExpressionParser();

    BigDecimal amount = parser.parseExpression(
            "new BigDecimal('19.99')"
    ).getValue(context, BigDecimal.class);

After registering the `java.math` import, the expression can use the short name `BigDecimal`. An import prefix only assists class lookup; it does not create a bean, does not register the class in the Spring container, and does not decide which constructor is called.

If the application uses a custom classloader, you can initialize StandardTypeLocator with the appropriate classloader or provide a custom TypeLocator. This is important in plugin environments, application servers, or applications with multiple classloaders.

## 4. ConstructorResolver Selects a Matching Constructor

After the class is found, SpEL needs to determine which constructor can accept the evaluated arguments. EvaluationContext provides a list of ConstructorResolver instances to perform this resolution.

In StandardEvaluationContext, the default resolver is ReflectiveConstructorResolver. This resolver looks for an accessible constructor on the class and returns a ConstructorExecutor to execute it.

The workflow can be pictured as follows:

1. SpEL reads the class name in the expression.
2. TypeLocator locates the corresponding class.
3. SpEL evaluates each argument.
4. ConstructorResolver finds a constructor matching the argument types and count.
5. ConstructorExecutor invokes the constructor and returns the instance as a TypedValue.

If the class exists but no matching constructor is found, the error occurs during constructor resolution or execution. If the class does not exist or TypeLocator cannot find it, the error occurs before a constructor is selected.

You can configure custom resolvers on StandardEvaluationContext with `setConstructorResolvers(...)`. When replacing the default resolver list, only re-add ReflectiveConstructorResolver if the application still needs reflection fallback.

## 5. Passing Arguments to a Constructor

Constructor arguments can be literals, variables, properties, or expressions evaluated within the same context.

**Literal:**

    new com.example.domain.Customer('Lan', 25)

**Variable in EvaluationContext:**

    context.setVariable("customerName", "Lan");
    context.setVariable("customerAge", 25);

    new com.example.domain.Customer(#customerName, #customerAge)

**Property of the root object or a variable:**

    new com.example.domain.Invoice(#order.id, #order.total)

**Computed expression:**

    new com.example.domain.Rectangle(#width * 2, #height + 5)

SpEL evaluates the arguments before invoking the constructor. The runtime type of each value affects overload selection. If a property returns null or a sub-expression throws an error, instantiation can also fail before the constructor is called.

When expressions are long, you can compute and validate the data in Java first, then pass the normalized values into the context. This ensures the constructor receives the right types and keeps validation responsibilities clear.

## 6. Constructor Overloading and Type Conversion

A class can have multiple constructors with the same class name but different parameter lists:

    public Customer(String name) { ... }

    public Customer(String name, Integer age) { ... }

    public Customer(String name, Integer age, boolean active) { ... }

SpEL uses ConstructorResolver to pick a constructor matching the argument count and types. EvaluationContext's TypeConverter can assist in converting arguments to parameter types when needed.

Example:

    new com.example.domain.Customer('Lan', 25)

If the second constructor takes String and Integer, SpEL resolves according to those corresponding argument types. When multiple overloads can accept values after conversion, the selection may be unintended or ambiguous.

To avoid issues:

- Use explicitly typed literals when needed, such as `25L` for Long.
- Normalize variables in Java before putting them into the context.
- Avoid overloads with overly similar signatures if expressions are dynamically generated.
- Verify the runtime types of arguments and the selected constructor in tests.
- Do not rely on implicit conversion as a substitute for data validation.

TypeConverter only assists with converting data representations. It does not guarantee that values satisfy the business rules of the constructor or domain object.

## 7. Creating BigDecimal and BigInteger Accurately

Constructor invocation is often useful when creating high-precision numeric types. For BigDecimal, pass the decimal string directly:

    new java.math.BigDecimal('1234567890.12345678901234567890')

This preserves the supplied decimal digits. Do not create a BigDecimal from a Double literal and expect to recover precision already lost to floating point.

For large integers:

    new java.math.BigInteger('123456789012345678901234567890')

BigInteger preserves exact integer digits without being bounded to the Integer or Long range.

If the application uses SimpleEvaluationContext, constructor invocation is not supported. In that case, create the BigDecimal or BigInteger in Java and pass it via a variable:

    context.setVariable(
            "amount",
            new BigDecimal("1234567890.1234567890")
    );

    #amount

This approach is also suitable when data comes from a database or API and needs to be parsed and validated before the expression uses it.

## 8. Creating Arrays with Constructor Syntax

SpEL supports creating arrays using the `new` keyword and a size or initializer:

    new int[3]
    new java.lang.String[2]
    new int[]{10, 20, 30}

`new int[3]` creates an array with three elements initialized to the default int value of 0. The initializer syntax creates an array and populates its elements directly in the expression.

You can access an element of the newly created array:

    new int[]{10, 20, 30}[1]

The result is 20. An array can also be passed as an argument to another constructor or method if the parameter type is compatible.

Distinguish array constructor syntax from an inline list:

    {10, 20, 30}

An inline list creates a collection; `new int[]{10, 20, 30}` creates an int array. The data types and APIs accepting these two structures can differ.

## 9. Constructor Invocation vs. Type Reference and Bean Reference

The three syntaxes below serve different purposes:

| Syntax | Meaning |
|---|---|
| `new com.example.Customer('Lan')` | Creates a new instance via constructor |
| `T(com.example.Customer)` | References the Class object to access the type or static members |
| `@customerService` | Resolves the bean named customerService in the Spring container |

A type reference does not create an object on its own. A bean reference also does not instantiate via a constructor in the expression; it retrieves an object managed by the container.

Example of calling a static factory:

    T(com.example.CustomerFactory).create('Lan')

This is a static method call on the class referenced by `T(...)`, not a constructor invocation. A static factory can apply custom object creation rules, but calling it is subject to the context's method invocation restrictions.

Use `new` when you genuinely need a new instance via a constructor. Use a bean reference when you need a Spring-managed component, preserving container scope, dependency injection, and proxies.

## 10. Constructor Invocation Limitations in EvaluationContext

StandardEvaluationContext supports constructor invocation by default via ReflectiveConstructorResolver. SimpleEvaluationContext is designed with a more restricted feature set and does not support constructor invocation.

Example of creating a read-only simple context:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(order)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    // Constructor invocation is not supported in this context.
    parser.parseExpression(
            "new java.math.BigDecimal('19.99')"
    ).getValue(context);

If the use case requires constructor invocation, use a context that supports it and configure it deliberately. Do not switch to StandardEvaluationContext merely to make the expression run if the expression comes from an untrusted source.

## 11. Safety When Allowing Class Instantiation from Expressions

Constructor invocation can instantiate any class that TypeLocator can resolve and whose constructor is accessible. On the application classpath, there may be classes whose constructors perform I/O, open connections, allocate resources, or create objects with broad privileges.

Therefore, user-supplied expressions should not be allowed to freely use `new` across the entire classpath. Several measures to consider:

- Use SimpleEvaluationContext when type references or constructor invocations are unnecessary.
- If constructors are needed, use a custom TypeLocator that resolves only classes on an allowlist.
- Configure ConstructorResolver to restrict allowed types or constructors.
- Disallow direct instantiation of classes that access files, processes, networks, or administrative resources if the use case does not need them.
- Validate data passed into constructors and limit the size of created objects/arrays.
- Prefer a narrow application-controlled factory or facade when object creation involves business rules.

A custom TypeLocator or ConstructorResolver must be thoroughly verified so it does not accidentally fall back to a broad resolver. Restricting package names by convention alone is insufficient if sensitive classes exist within that package.

## 12. Common Errors and How to Handle Them

- **Not using the fully qualified name for classes outside java.lang:** use `new java.math.BigDecimal(...)` or register an import prefix in TypeLocator.
- **Confusing type reference with constructor:** `T(com.example.Customer)` returns a Class reference; use `new com.example.Customer(...)` to create an instance.
- **Class cannot be resolved:** verify the package name, classpath, and TypeLocator.
- **No matching constructor:** check argument count, types, and constructor accessibility.
- **Ambiguous overload:** standardize argument types or simplify overloads.
- **Numeric precision loss:** create BigDecimal from a string instead of a Double.
- **Using a constructor in SimpleEvaluationContext:** this context does not support constructor invocation; create the object in Java and pass it via a variable.
- **Allowing arbitrary classes:** restrict TypeLocator/ConstructorResolver when expressions are not completely trusted.
- **Confusing a bean with a new instance:** use `@beanName` for container-managed beans, and `new` for instances created during expression evaluation.

## 13. Key Takeaways

Constructor invocation in SpEL uses the syntax `new fully.qualified.ClassName(arguments)`. TypeLocator locates the class; ConstructorResolver selects the constructor; TypeConverter can assist with argument conversion. StandardTypeLocator recognizes the `java.lang` package by default, while classes outside this package should use their fully qualified name or register an import prefix. Arrays can be created using `new Type[size]` or an initializer. StandardEvaluationContext supports constructor invocation, whereas SimpleEvaluationContext does not. When expressions are not completely trusted, restrict the allowed classes and constructors rather than opening up the entire classpath.
