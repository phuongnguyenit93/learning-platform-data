# The new Operator in SpEL

## 1. What Is the new Operator Used For?

Spring Expression Language (SpEL) can create objects directly inside an expression using the new operator. This syntax allows invoking a class constructor and receiving a new instance.

Example:

    new String('Hello')
    new java.util.Date()
    new com.example.Customer('Lan', 30)

When the expression is evaluated, SpEL looks up the specified type, resolves the matching constructor, evaluates the arguments, and then creates the object.

The new operator is useful when you need to create an intermediate value or object directly inside an expression, such as passing a new object into a method, creating a specific collection, or constructing an argument for a computation.

However, new only creates an instance. It does not register that instance as a Spring bean and does not automatically apply the IoC container's bean management lifecycle.

## 2. Constructor Invocation Syntax

General syntax:

    new Fully.Qualified.ClassName(argument1, argument2, ...)

Example:

    new java.util.Date()

    new java.math.BigDecimal('1250.50')

    new com.example.Customer('Lan', 30)

For classes in the java.lang package, the package name can be omitted:

    new String('Spring')
    new Integer(42)
    new Boolean(true)

For classes in other packages, the fully qualified class name should be used by default:

    new java.util.ArrayList()
    new java.math.BigDecimal('99.95')
    new com.example.Order('ORD-001')

The fully qualified name helps TypeLocator determine the exact class to create. If you want to use short names for classes outside java.lang, you need to configure TypeLocator with the appropriate package import.

## 3. Example of Creating a Custom Java Object

Suppose the application has a Customer class:

    package com.example;

    public class Customer {
        private final String name;
        private final int age;

        public Customer(String name, int age) {
            this.name = name;
            this.age = age;
        }

        public String getName() {
            return name;
        }

        public int getAge() {
            return age;
        }
    }

You can create a Customer using SpEL:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    Expression expression = parser.parseExpression(
        "new com.example.Customer('Lan', 30)"
    );

    Customer customer =
        expression.getValue(context, Customer.class);

The result is a Customer instance with name as Lan and age as 30.

In this example:

1. The parser parses the constructor expression syntax.
2. When getValue is called, SpEL looks up the com.example.Customer class.
3. SpEL finds the constructor matching the two arguments: String and integer.
4. The constructor is invoked and the new instance is returned.

Parsing the expression does not create the object yet. The constructor is only executed when the expression is evaluated.

## 4. Passing Variables to a Constructor

Constructor arguments can be variables in the EvaluationContext instead of fixed literals.

Example:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("customerName", "Lan");
    context.setVariable("customerAge", 30);

    Expression expression = parser.parseExpression(
        "new com.example.Customer(#customerName, #customerAge)"
    );

    Customer customer =
        expression.getValue(context, Customer.class);

The syntax #customerName and #customerAge references variables registered in the context.

This approach helps reuse the same expression with different data:

    context.setVariable("customerName", "Minh");
    context.setVariable("customerAge", 25);

    Customer anotherCustomer =
        expression.getValue(context, Customer.class);

On each getValue call, SpEL evaluates the arguments against the current context and then invokes the constructor to create a new instance.

If a variable has not been registered or its value is incompatible with the constructor parameter, evaluation can fail even though the expression was parsed successfully.

## 5. Passing Expressions as Arguments

Constructor arguments do not have to be simple variables or literals. You can pass the result of an operation or another expression.

Example:

    new com.example.Customer(
        #firstName + ' ' + #lastName,
        #birthYear < 2000 ? 26 : 18
    )

SpEL evaluates the arguments and then passes the resulting values into the constructor.

A simpler example:

    new java.math.BigDecimal(#amount.toString())

If amount is a variable with an appropriate value, the expression creates a BigDecimal from the result of the toString call.

Ensure that argument expressions return types that the constructor can accept or that can be converted by TypeConverter.

Do not put overly complex logic into a constructor expression. If there are multiple business steps, prepare the data in Java and pass it into the expression as variables.

## 6. Constructor Overloading and Type Conversion

A class can declare multiple constructors with the same name but different parameter lists. This is constructor overloading.

Example:

    public class Customer {
        public Customer(String name) {
            // ...
        }

        public Customer(String name, int age) {
            // ...
        }
    }

SpEL needs to select a constructor that matches the number and types of the arguments.

Example:

    new com.example.Customer('Lan')

selects the constructor accepting a single String if that constructor is accessible and compatible.

Example:

    new com.example.Customer('Lan', 30)

selects the constructor accepting String and int if compatible with the provided values.

SpEL uses the type conversion mechanism in EvaluationContext to support cases where an argument can be converted to the parameter type. Conversion depends on the configured TypeConverter and ConversionService.

If there are multiple similar overloads or an argument has an ambiguous type, clarify the data type in Java before passing it into the expression. Do not rely on implicit conversion when the constructor carries important business meaning.

## 7. Varargs Constructors

SpEL supports varargs when invoking constructors.

Class example:

    public class LabelSet {
        private final List<String> labels;

        public LabelSet(String... labels) {
            this.labels = List.of(labels);
        }

        public List<String> getLabels() {
            return labels;
        }
    }

You can pass multiple arguments:

    new com.example.LabelSet('Java', 'Spring', 'SpEL')

The constructor receives the arguments as varargs and creates the list of labels.

When using varargs, the number of arguments can vary as needed. However, if the class has multiple overloaded constructors, carefully verify which constructor the resolver selects.

Varargs does not mean SpEL automatically converts every kind of collection into a varargs parameter in all cases. Check the argument types and actual constructor signatures.

## 8. TypeLocator and How Classes Are Found

Before invoking a constructor, SpEL must find the class corresponding to the name written after new.

This is handled by TypeLocator in EvaluationContext.

StandardEvaluationContext uses StandardTypeLocator by default. The default type locator knows the java.lang package, so you can write:

    new String('Hello')

However, for classes outside java.lang, you should use the fully qualified name:

    new java.util.ArrayList()

If you want to use short names, you can register a package import:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    StandardTypeLocator typeLocator =
        new StandardTypeLocator();

    typeLocator.registerImport("com.example");

    context.setTypeLocator(typeLocator);

After that you can write:

    new Customer('Lan', 30)

because TypeLocator has been configured to look up classes in the com.example package.

Imports here belong to SpEL's TypeLocator. They are not Java source import statements and do not modify the classpath on their own.

## 9. ClassLoader and Runtime Environment

In some applications, especially plugin environments, application servers, or runtimes with separate class loaders, TypeLocator may fail to find a class even though that class exists in the application.

You can configure StandardTypeLocator with the appropriate ClassLoader:

    StandardTypeLocator typeLocator =
        new StandardTypeLocator(
            MyApplication.class.getClassLoader()
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setTypeLocator(typeLocator);

This helps SpEL find classes through the application's correct ClassLoader.

If you encounter a class-not-found error, check:

- Is the class name in the expression exact?
- Is the package written in full?
- Is the class on the runtime classpath?
- Can the ClassLoader used by TypeLocator see the class?
- Has the package import been registered if using a short name?

Do not confuse a class-not-found error with an error where no matching constructor is found. The two errors occur at different steps.

## 10. ConstructorResolver

After TypeLocator finds the class, SpEL needs to select a matching constructor. This job is handled by ConstructorResolver.

StandardEvaluationContext has a reflective constructor resolver by default, using reflection to find the corresponding constructor.

If the application has special object-creation requirements, a custom ConstructorResolver can be registered in the EvaluationContext. This allows extending the instantiation mechanism beyond the default reflection behavior.

A custom constructor resolver must clearly handle:

- Which classes are allowed to be created.
- Which constructors are allowed to be used.
- How to match argument count and types.
- How to convert values.
- How to report errors when no matching constructor is found.

Do not extend the resolver merely to work around ordinary constructor errors. First verify the class, accessible matching constructor, argument types, and TypeConverter.

## 11. Distinguishing new from Type Reference T()

SpEL has the T() operator to reference a Java Class object.

Example:

    T(java.util.Date)

The expression above returns the Class object representing java.util.Date. It does not create a Date instance.

Meanwhile:

    new java.util.Date()

invokes the constructor and creates a new Date instance.

Comparison:

| Syntax | Meaning | Result |
| --- | --- | --- |
| T(java.util.Date) | Type reference | Class object |
| new java.util.Date() | Constructor invocation | Date instance |
| T(java.lang.Math).max(3, 5) | Static method call | Return value of the method |

Use T() when you need to reference a class, enum, static field, or static method. Use new when you need to create an instance.

Do not confuse TypeLocator finding a class with the constructor being invoked. TypeLocator only helps locate the type; the constructor resolver handles the instantiation step.

## 12. Distinguishing new from Spring Bean Reference

The following two approaches have very different meanings:

    new com.example.Customer('Lan', 30)

    @customerService

The first expression creates a new instance using a constructor.

The second expression looks up the bean named customerService in the Spring BeanFactory through BeanResolver.

An object created with new in SpEL is not automatically managed by the Spring container. It does not automatically receive dependency injection, does not have bean lifecycle callbacks applied, does not automatically get AOP proxies, and does not follow bean scopes.

If you need a service or component managed by Spring, use a bean reference at a SpEL-enabled integration point and provide an appropriate BeanResolver.

If you only need to create a simple data object or a temporary value, a constructor expression can be suitable.

## 13. Constructors and Array Construction

SpEL uses the new operator for both constructor invocation and array construction, though the syntax and result types differ.

Creating an object:

    new java.util.ArrayList()

Creating an array with a size:

    new int[4]

Creating an array with an initializer:

    new int[] {1, 2, 3}

Creating a multidimensional array:

    new int[4][5]

Example in Java:

    int[] numbers = (int[]) parser
        .parseExpression("new int[] {1, 2, 3}")
        .getValue(context);

    int[][] matrix = (int[][]) parser
        .parseExpression("new int[4][5]")
        .getValue(context);

For multidimensional arrays, SpEL currently does not support providing an initializer within the same multidimensional array creation syntax. You can create the array by size and assign each element in Java.

Array construction differs from an inline List:

    {1, 2, 3}

This expression creates an inline List.

    new int[] {1, 2, 3}

This expression creates a primitive int array.

Choose the syntax according to the data type required by downstream code.

## 14. Using Constructor Expressions Inside Method Invocations

A constructor expression can be used as an argument to a method call.

Example:

    Members.add(
        new com.example.Inventor('Albert Einstein', 'German')
    )

In a SpEL expression:

    Members.add(
        new com.example.Inventor('Albert Einstein', 'German')
    )

SpEL creates a new Inventor and passes that instance into the add method of the Members collection.

This approach can be useful when an expression needs to add a new object to a collection or pass a new object to a method.

However, the called method can mutate objects or application state. Consider side effects and the permissions of the EvaluationContext before allowing expressions to perform such operations.

## 15. SimpleEvaluationContext and Constructor Limitations

SimpleEvaluationContext is designed to support only a subset of SpEL features, suited for data binding or property-based filtering cases that require restricted permissions.

This context does not support constructor invocation, type references, or bean references.

Therefore, the expression:

    new com.example.Customer('Lan', 30)

is not suitable for SimpleEvaluationContext.

If you need to use constructor expressions, you must use an EvaluationContext that supports full features such as StandardEvaluationContext, or a custom context that allows constructor resolution.

Do not switch to StandardEvaluationContext just to make an expression run without evaluating access permissions. StandardEvaluationContext is more powerful and must be configured carefully when expressions come from external sources.

## 16. Common Errors When Using new

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| Type cannot be found | Wrong class name or TypeLocator cannot find the class | Use the fully qualified name, check classpath and ClassLoader |
| Constructor cannot be found | No constructor matches the arguments | Check parameter count, order, and types |
| Argument conversion error | Cannot convert argument to parameter type | Prepare the right type in Java or configure TypeConverter |
| Expression parse error | Invalid new syntax, parentheses, or argument list | Check grammar and delimiters |
| Constructor does not run in SimpleEvaluationContext | Context does not support constructor invocation | Use a context with full support if business logic allows |
| Object does not receive dependency injection | Instance was created directly with new, outside the container | Use a Spring bean instead of creating the instance manually if DI is needed |
| Unexpected overload selected for class | Multiple constructors have compatible parameters | Clarify argument types and check overloads |
| Class not found in plugin environment | TypeLocator uses an inappropriate ClassLoader | Configure StandardTypeLocator with the right ClassLoader |

Distinguish three stages when debugging:

1. Parsing: Does the expression have valid syntax?
2. Type lookup: Can TypeLocator find the class?
3. Constructor resolution: Is there a matching constructor that is allowed to be invoked?

After creating the object, errors can still occur in subsequent method calls or property accesses. Therefore, split expressions into smaller steps when you need to pinpoint where an error happens.

## 17. Security and Side Effects

Constructor invocation can run initialization code of a class. A constructor may read configuration, create resources, open connections, or perform other logic depending on its implementation.

Therefore, expressions containing the new operator should not be evaluated arbitrarily if untrusted users can control the expression content.

Principles:

- Do not evaluate arbitrary user-submitted SpEL in a context with full permissions.
- Restrict classes that can be found via TypeLocator if required by the domain.
- Control ConstructorResolver and the reflection capabilities granted.
- Do not expose classes whose constructors have dangerous side effects to untrusted expressions.
- Prefer creating objects in Java code when validation, transactions, or explicit resource management are needed.
- Use a feature-restricted context when constructor invocation is unnecessary.

Changing syntax or using a wrapper does not eliminate risk by itself if the expression still has permission to invoke constructors or methods.

## 18. Key Takeaways

- The new operator is used to invoke constructors and create instances.
- The usual syntax is new Fully.Qualified.ClassName(arguments).
- The java.lang package can be omitted when referencing classes in that package.
- Classes outside java.lang should use the fully qualified name, unless TypeLocator has package imports configured.
- TypeLocator locates the class; ConstructorResolver finds and invokes the constructor.
- StandardEvaluationContext provides reflection-based constructor resolution by default.
- Constructors can be overloaded and support varargs; argument types must be compatible or convertible.
- T() returns a Class object; new creates an instance.
- Array construction such as new int[4] and new int[] {1, 2, 3} differs from an inline List {1, 2, 3}.
- new creates instances outside Spring's bean management lifecycle.
- SimpleEvaluationContext does not support constructor invocation.
- Constructors can have side effects; do not evaluate untrusted expressions with broad object creation permissions.

When using new in SpEL, clearly identify the class to create, the intended constructor, argument types, and the ClassLoader in use. Also clearly distinguish manually created objects from Spring beans so you do not expect automatic dependency injection or lifecycle management.

## References

- Spring Framework Reference — Constructors: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html
- Spring Framework Reference — Array Construction: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/array-construction.html
- Spring Framework Reference — Types: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/types.html
- Spring Framework Reference — EvaluationContext and Security: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
