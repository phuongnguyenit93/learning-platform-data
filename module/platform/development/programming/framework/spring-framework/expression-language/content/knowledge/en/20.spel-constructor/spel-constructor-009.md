# Assessing Risks When Expressions Create Objects or Resources

## Objectives

After this lesson, you will be able to identify risks when Spring Expression Language (SpEL) creates objects or resources during expression evaluation; distinguish parse time from the moment a constructor actually executes; estimate the impact of memory allocation and side effects; and choose ways to restrict object creation permissions in EvaluationContext. You will also understand why resources require explicit lifecycle management, how to avoid repeated object creation in collection operations, and how to control expressions originating from external sources.

## 1. SpEL Can Create Objects via Constructors

SpEL supports the `new` operator to invoke a Java class constructor. Basic syntax:

~~~text
new fully.qualified.ClassName(constructorArguments)
~~~

Example creating a date object:

~~~text
new java.util.Date()
~~~

For classes in the `java.lang` package, SpEL can locate the class name by default without writing the full package:

~~~text
new String('hello')
~~~

For classes in other packages, the fully qualified class name is normally required:

~~~text
new java.math.BigDecimal('125.50')
~~~

Constructors can accept literals, variables, properties, or the result of other expressions:

~~~text
new com.example.Invoice(#order.id, #order.total)
~~~

This is convenient when an expression needs to create an intermediate value or a small DTO. However, a constructor is real Java code. When invoked, it runs the logic inside the constructor and can allocate memory, call other methods, or produce side effects.

Do not treat `new` as merely harmless data-creation syntax. The risk level depends on the class being instantiated, the constructor invoked, and the objects the constructor uses.

## 2. Distinguishing parseExpression from getValue

When the application calls:

~~~java
Expression expression =
    parser.parseExpression("new java.util.Date()");
~~~

SpEL parses the string and builds the expression structure. Parsing does not mean the constructor has run.

The constructor is invoked when the application evaluates the expression:

~~~java
Date created = expression.getValue(Date.class);
~~~

If `getValue(...)` is called multiple times, a constructor expression can create a new instance on each evaluation:

~~~java
Date first = expression.getValue(Date.class);
Date second = expression.getValue(Date.class);
~~~

The two variables above receive results from two separate evaluations. Do not assume SpEL caches an object created by a constructor and reuses it like a singleton.

This distinction matters when an expression is parsed once yet evaluated many times during the application's lifecycle. Caching the Expression object avoids re-parsing; it does not turn the object produced by the expression into a shared object.

## 3. Constructors Can Have Side Effects

A Java constructor might only initialize fields, yet it can also perform external work:

- Reading or writing files.
- Opening streams or network connections.
- Creating connections or clients to services.
- Registering listeners or callbacks.
- Allocating a large data structure.
- Initializing pools, schedulers, or resources that require closing.
- Calling another component that has side effects.

For example, creating a `File` object only creates an object describing a path:

~~~text
new java.io.File(#path)
~~~

The `File` constructor does not create a file on disk by itself. By contrast, the `FileInputStream` constructor opens a file for reading:

~~~text
new java.io.FileInputStream(#path)
~~~

The second expression can open a file immediately when evaluated and can fail if the file does not exist, permissions are insufficient, or the system encounters an I/O error.

Other constructors may connect to external systems or hold resources for a long time. Therefore, inspect the actual behavior of the class and constructor rather than looking only at the data type name.

## 4. Memory Allocation and CPU Risks

Even a constructor without I/O can pose risks if it allocates too much memory or performs CPU-intensive work.

Example creating an array:

~~~text
new int[1000]
~~~

A small size may be fine. However, if the size comes directly from input:

~~~text
new byte[#requestedSize]
~~~

a very large value can cause excessive memory consumption, increase garbage collection pauses, or exhaust application memory.

Similarly, creating many objects inside an iterative expression can increase allocation counts. If each element requires a heavy object, the cost grows with the collection size.

Validate input bounds in Java before passing variables into SpEL. Limits on counts, array sizes, string lengths, and data structure depth must stem from business requirements and system capacity.

## 5. Risks When Creating Objects in Selection or Projection

Selection and projection evaluate an expression against each element of a collection. If a constructor sits inside a projection, it can be called once per processed element.

Example:

~~~text
#orders.![new com.example.OrderSummary(#this.id, #this.total)]
~~~

With N orders, the expression can create N OrderSummary objects. This may be reasonable for creating small DTOs, yet it consumes memory proportional to the element count.

If the constructor creates resources, calls services, or performs I/O, iterating over a collection can trigger a wave of unintended side effects.

Avoid placing heavy constructors inside projections or conditions evaluated repeatedly. Construct aggregated data in Java when you need to control creation counts, handle per-element errors, reuse objects, or release resources.

## 6. Large Arrays and Data Structures

SpEL supports creating arrays via constructor-style array expressions:

~~~text
new int[4]
~~~

Arrays can be created with initial values:

~~~text
new int[]{1, 2, 3}
~~~

And multidimensional arrays:

~~~text
new int[2][3]
~~~

Array sizes must be valid for the data type and memory limits. For sizes coming from variables, validate before evaluation:

~~~java
if (requestedSize < 0 || requestedSize > MAX_ARRAY_SIZE) {
    throw new IllegalArgumentException("Array size is out of range");
}
~~~

Do not let expressions decide unbounded sizes based on external data. If large arrays are needed, consider data structures, pagination, or streaming processing in Java.

## 7. Resources Require Lifecycle Management

An ordinary object can be reclaimed when no references remain. External resources such as file streams, sockets, database connections, or executors have their own lifecycles.

SpEL returns the object created by the constructor, yet the expression itself does not establish a procedure to close the resource after use. If an expression creates a stream and the application fails to close it, the resource can remain held longer than intended.

For example, creating a stream:

~~~text
new java.io.FileInputStream(#path)
~~~

must be accompanied by closing the stream on the Java side. Prefer try-with-resources:

~~~java
try (FileInputStream input =
         new FileInputStream(path)) {
    // Read data and process within this scope.
}
~~~

For connections, clients, or pools, clearly define who owns the object, who closes it, and when it is closed. If a resource needs to be shared or reused, let Spring manage the bean with an appropriate lifecycle rather than creating a new one on every SpEL evaluation.

## 8. Constructors Can Throw Exceptions

A Java constructor can fail due to invalid data, missing configuration, insufficient permissions, or system errors. When SpEL invokes a constructor and the constructor raises an error, expression evaluation can fail with a SpEL exception or an exception wrapped from the constructor call.

Example:

~~~text
new java.math.BigDecimal(#amountText)
~~~

If `#amountText` is not a valid numeric string, BigDecimal creation will fail.

Other scenarios can include:

- Missing arguments or wrong argument types.
- No matching constructor found.
- Unable to convert an argument to the parameter type.
- The constructor throws an exception.
- Unable to load or access the requested class.

Validate data and configuration before evaluation. In Java, catch and handle errors at the expression invocation boundary; log enough context to identify which constructor or data caused the failure. Do not swallow all exceptions and return a default object if doing so masks configuration errors.

## 9. Object Creation Permissions Depend on EvaluationContext

Object creation capability depends not only on syntax. It also depends on the EvaluationContext type and the type or constructor resolution mechanism.

`StandardEvaluationContext` provides the default constructor resolvers and supports fuller SpEL features. When using this context, expressions can reference types with `T(...)` and invoke constructors with `new` according to the configured resolvers.

Example:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("new java.math.BigDecimal('10.25')");

BigDecimal amount =
    expression.getValue(context, BigDecimal.class);
~~~

`SimpleEvaluationContext` is designed for a restricted feature set, such as data binding and accessing selected properties. It does not support type references and constructor invocation like StandardEvaluationContext.

If an expression only needs to read properties, use an appropriate restricted context. Do not expand to StandardEvaluationContext just so an expression can arbitrarily create objects if the application has no such need.

## 10. TypeLocator and ConstructorResolver

In StandardEvaluationContext, SpEL uses TypeLocator to look up classes by name and ConstructorResolver to determine invocable constructors.

You can replace TypeLocator:

~~~java
context.setTypeLocator(customTypeLocator);
~~~

And configure the list of ConstructorResolvers:

~~~java
context.setConstructorResolvers(customConstructorResolvers);
~~~

These extension points allow the application to control which classes can be referenced and which constructors may be called. You can build an allowlist-based TypeLocator or ConstructorResolver for approved data types.

An allowlist must be designed carefully:

1. Allow only classes necessary for the expressions.
2. Allow only constructors with well-understood parameters and behavior.
3. Disallow classes capable of performing I/O or mutating state unless explicitly required.
4. Validate argument types and sizes.
5. Test both allowed and rejected class/constructor cases.

Do not consider package-name restriction sufficient if that package still contains classes with side effects. Policy should be based on permitted types and behavior, not merely on class name strings.

## 11. Do Not Evaluate Untrusted Expressions with Broad Permissions

If users can submit SpEL strings, they can control the syntax evaluated by the parser. With a broadly privileged context, an expression can access more object types and object creation capabilities than intended.

Risk increases when combining:

- Constructor invocation with `new`.
- Type references with `T(...)`.
- Bean references with `@beanName`.
- Method invocations on objects privileged to perform actions.
- Broadly scoped custom property accessors or resolvers.

Do not evaluate untrusted expressions with a default-configured StandardEvaluationContext and assume it is safe merely because the expression comes from a configuration field.

If users must write formulas, design a sub-language with an explicit set of permitted operators and data, or use SimpleEvaluationContext with required capabilities enabled deliberately. Do not expose unrelated beans, resolvers, root objects, or methods.

## 12. Controlling Data Sources and Constructor Arguments

Constructors can receive data from variables, properties, or results of other calls. Therefore, even when a class is allowed to be instantiated, arguments still need to be controlled.

Example:

~~~text
new com.example.ReportOptions(#format, #maxRows)
~~~

The application needs to check:

- `#format` belongs to the list of supported formats.
- `#maxRows` is within reasonable limits.
- Strings do not exceed length limits.
- Input objects have the required types and state.
- Paths, URLs, or sensitive details are not passed if the constructor does not need them.

Do not concatenate user data directly into class names or the entire expression string. Pass data through variables in EvaluationContext and validate before evaluation. This separates expression code from input data and makes validation easier to apply.

## 13. Auto-Grow Can Also Create Objects

Beyond explicit `new`, SpEL configuration can allow automatically growing null references or collections when accessing properties or indexers.

`SpelParserConfiguration` has options such as:

- `autoGrowNullReferences`: allows creating objects at certain null references when needed to continue traversal.
- `autoGrowCollections`: allows expanding collections when indexing past the current size.
- `maximumAutoGrowSize`: limits the maximum auto-grow size.

Configuration example:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        true,
        true,
        128
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

The configuration above enables both auto-grow mechanisms and bounds the maximum expansion size to the passed value. Exact behavior also depends on property types, collections, and element instantiability.

Auto-grow can be convenient for data binding, yet it also mutates the object graph during evaluation. Enable it only when needed, set clear bounds, and do not allow sizes to grow from uncontrolled input.

## 14. Comparing Ways to Create and Manage Objects

| Approach | When Appropriate | What to Control |
|---|---|---|
| `new` in SpEL | Creating small, simple values with pure constructors | Allowed types, evaluation counts, arguments |
| Creating DTOs in Java | Need validation, multiple steps, or explicit types | Constructors and business logic |
| Injected Spring bean | Shared objects or objects with lifecycle | Scope, configuration, and method call permissions |
| Application-controlled factory method | Need centralized creation rules | Input allowlist and factory behavior |
| Creating resources in Java with try-with-resources | Files, streams, or bounded-lifetime resources | Closing resources and exception handling |

SpEL is well-suited for short declarative expressions. Java and the Spring container are better suited when lifecycle management, transactions, cleanup, retries, logging, or detailed error handling are needed.

## 15. Example: Using a Constructor for a Simple DTO

Suppose a DTO only stores an ID and total amount, and its constructor performs no I/O or external state changes:

~~~java
public class OrderSummary {
    private final String id;
    private final BigDecimal total;

    public OrderSummary(String id, BigDecimal total) {
        this.id = id;
        this.total = total;
    }

    public String getId() {
        return id;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

You can create the DTO from the root object:

~~~text
new com.example.OrderSummary(id, total)
~~~

Or create one DTO per order in a projection:

~~~text
#orders.![new com.example.OrderSummary(#this.id, #this.total)]
~~~

This approach can be suitable for small collections and simple constructors. If the collection is large, per-element error handling is needed, or the DTO requires complex validation, construct the results in Java for clearer control over allocation and errors.

## 16. Checklist Before Allowing Constructor Invocation

Before enabling object creation in an expression, answer:

1. Which classes are allowed to be created?
2. Which constructors can be invoked?
3. Does the constructor read/write files, open connections, or call services?
4. How long will the created object be used?
5. Who is responsible for closing or releasing resources?
6. How many times and over how many elements is the expression evaluated?
7. Are arguments bounded in size, type, and value?
8. Does the expression come from a user or untrusted source?
9. Can the object be created in Java or via an injected bean instead?
10. Can TypeLocator or ConstructorResolver be restricted by an allowlist?

If an object's behavior and lifecycle cannot be clearly determined, do not let SpEL create that object on its own.

## 17. Testing Object Creation Risks

Tests should verify both the result and creation counts as well as side behaviors:

| Case | What to Verify |
|---|---|
| Simple constructor | Correct type and field values |
| Two getValue calls | Confirm two separate instances can be created |
| Null argument | Behavior matches constructor contract |
| Wrong argument type | Conversion or constructor error reported clearly |
| Constructor throws exception | Error handled at expression invocation boundary |
| Large array size | Bounded prior to allocation |
| Constructor opens resources | Resources are properly closed |
| Projection over collection | Number of created objects matches processed element count |
| Class outside allowlist | Constructor is rejected |
| SimpleEvaluationContext | Constructor invocation is not supported |
| Auto-grow | Objects/collections are only expanded within configured limits |

For constructors with side effects, use test doubles or an isolated test environment. Do not run tests that open connections, write files, or make large allocations in a production environment.

## 18. Key Takeaways

SpEL can create objects using `new` and arrays using array construction syntax. Parsing an expression only builds the expression structure; the constructor runs when getValue evaluates it. Each evaluation can create a new instance, so expressions invoked repeatedly can incur multiple allocations.

Constructors are Java code and can perform I/O, open resources, call external systems, or consume substantial memory/CPU. SpEL does not automatically manage resource-closing lifecycles for created objects. Resources such as streams, sockets, and connections should be managed in Java or by the Spring container.

StandardEvaluationContext supports constructor invocation through type and constructor resolution mechanisms. SimpleEvaluationContext does not provide this object creation capability. When constructors are needed, restrict TypeLocator/ConstructorResolver, validate arguments, evaluation counts, and side effects; do not evaluate untrusted expressions with broad permissions.

Use `new` for small, pure objects with predictable behavior. For resources, complex creation logic, cleanup, or long-lived objects, let Java and Spring manage instantiation and release.

## References

- [Spring Framework Reference — Constructors](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)