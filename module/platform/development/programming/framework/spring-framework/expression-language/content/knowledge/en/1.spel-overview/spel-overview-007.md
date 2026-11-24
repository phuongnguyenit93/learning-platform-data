# Limitations of SpEL Compared to a Full Programming Language

## Objectives

After this lesson, you will be able to explain why Spring Expression Language (SpEL) is very useful for expressing conditions and accessing data in Spring, yet does not replace Java or a general-purpose programming language. You will also know which work fits SpEL, which work should be moved to Java code, and how to restrict the permissions of the expression evaluator.

## 1. What Is SpEL Designed For?

Spring Expression Language is an expression language provided by Spring. It allows an application to describe a calculation, condition, or data-access operation as a string, and then parse and evaluate that string within a specific context.

For example, an expression can retrieve a customer's name from the root object:

    customer.name

Or decide a label based on the order total:

    total >= 1000 ? 'PRIORITY' : 'STANDARD'

SpEL commonly appears where Spring needs a value or condition configured via an expression, such as:

- `@Value` to retrieve values from the environment, properties, or beans.
- Spring Cache, for example `@Cacheable(key = "#orderId")`, to generate a cache key from a method parameter.
- Spring Security, for example `@PreAuthorize("hasAuthority('invoice:read')")`, to check access permissions.
- Custom application configurations or components that use `ExpressionParser` and `EvaluationContext`.

A string only becomes a SpEL expression when a Spring component or application code explicitly parses and evaluates it. SpEL does not automatically execute every string in an application.

## 2. Expression Evaluation Model

Typically, using SpEL involves three parts:

1. **Parser** parses the expression string into an `Expression` object.
2. **EvaluationContext** provides the capabilities the expression is permitted to use, such as how to read properties, invoke methods, convert types, look up beans, and store variables.
3. **Root object** is the default root object the expression accesses when a property or method name is not written with a `#` variable.

Java example:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("customer.name");

    String name = expression.getValue(order, String.class);

In this example, `order` is the root object. SpEL reads the `customer` property and then reads `name`. Actual access depends on the property accessors and the configuration of the evaluation context.

When you need to pass variables or configure access permissions, you can create an `EvaluationContext`:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression(
        "#order != null and #order.total > #limit ? 'REVIEW' : 'APPROVE'"
    );

    EvaluationContext context = new StandardEvaluationContext();
    context.setVariable("order", order);
    context.setVariable("limit", new BigDecimal("1000"));

    String decision = expression.getValue(context, String.class);

The expression above returns a string value. It does not define a program composed of multiple statements.

## 3. What Can SpEL Do?

SpEL is far more capable than a simple string replacement tool. Common capabilities include:

### 3.1. Values and Operators

SpEL supports literals such as numbers, strings, booleans, and `null`, as well as arithmetic, comparison, and logical operations.

    10 + 5 * 2
    #quantity >= 10 and #enabled
    name matches 'A.*'
    age between {18, 60}

Conditional operators help produce a value per branch:

    #total >= 1000 ? 'PRIORITY' : 'STANDARD'

The Elvis operator provides a default value when the left-hand side is `null`:

    #displayName ?: 'Customer'

The safe navigation operator helps avoid accessing a property or invoking a method on a `null` reference:

    customer?.address?.city

These are conditional expressions within a single expression. They do not create statement-based `if/else` control structures like in Java.

### 3.2. Reading Properties, Invoking Methods, and Accessing Elements

If the context permits, an expression can read properties, invoke methods, and access elements in an array, list, or map.

    customer.address.city
    customer.getDisplayName()
    items[0]
    settings['locale']

SpEL can invoke Java methods exposed through the context. Therefore, a short expression can still invoke logic residing in Java code. This capability depends on the configured method resolvers and access permissions.

### 3.3. Type References, Object Instantiation, and Beans

In a permitting context, SpEL can reference a Java type using the `T(...)` operator, invoke static methods, and instantiate objects with `new`.

    T(java.lang.Math).max(10, 20)
    new java.math.BigDecimal('19.95')

Expressions can also reference beans by name, for example:

    @taxCalculator.calculate(#order)

Bean reference syntax only works when the context has a suitable `BeanResolver`. Do not assume every `EvaluationContext` has bean lookup permissions.

### 3.4. Variables and Registered Functions

Variables in the context are typically referenced with the `#` prefix:

    #currentUser
    #order.total

An application can also register a Java method as a function for the expression to call by name. SpEL does not require the author to define a new function body inside the expression; the implementation remains in Java code.

### 3.5. Filtering and Projecting Collections

SpEL has dedicated syntax for working with collections:

- Selection `.?[...]` filters elements matching a condition.
- Projection `.![...]` creates a new collection from a property or expression evaluated on each element.
- `.^[...]` retrieves the first element matching a condition.
- `.$[...]` retrieves the last element matching a condition.

For example:

    #orders.?[status == 'PAID']
    #orders.![id]
    #orders.^[total > 1000]

These operations are very convenient for querying data already in memory. They are not general-purpose loops for controlling a multi-step workflow.

### 3.6. Assigning Values

SpEL has an assignment operator. If write permissions are enabled and the target object allows it, an expression can modify a property:

    name = 'New name'

In addition, an expression can invoke Java methods that have side effects. Therefore, do not treat every SpEL expression as a pure computation or safe by default to run on user-supplied data.

## 4. What SpEL Does Not Provide as a Full Programming Language

The main difference lies in the purpose and structure of the language. SpEL focuses on evaluating expressions within a Spring application. Java is a general-purpose programming language used to build the complete behavior of an application.

| Need | SpEL | Java |
|---|---|---|
| Calculation and comparison | Yes, via expressions | Yes |
| Selecting a value conditionally | Yes, via ternary or Elvis operators | Yes, via expressions or `if/else` |
| Accessing properties and invoking methods | Yes, depending on context permissions | Yes, according to Java access rules |
| Filtering or projecting collections | Has dedicated syntax | Has loops, Stream API, and libraries |
| Declaring local variables for a program block | No general block-statement model; has variables in context | Yes |
| Defining new classes, interfaces, enums, or types | No | Yes |
| Defining methods with new function bodies | No; can call registered or permitted Java methods | Yes |
| General-purpose loops such as `for`, `while`, `do/while` | No corresponding statement constructs | Yes |
| Exception handling with `try/catch/finally` | No corresponding statement constructs | Yes |
| Organizing packages, modules, and dependencies | No | Yes |
| Managing threads, asynchronous tasks, and application lifecycle | Not a role of SpEL | Yes, via Java and libraries |
| I/O, networking, databases, and system resources | Can only indirectly invoke permitted Java code | Yes, via APIs and libraries |
| Static type checking and compile-time error checking | Limited; many errors only surface during evaluation | Stronger thanks to the compiler and Java type system |

Some points to understand accurately:

- **Having conditionals does not mean having full control structures.** The ternary operator selects one result, but does not replace an `if` block containing multiple statements.
- **Having selection/projection does not mean having general-purpose loops.** SpEL can filter or transform collections, but is unsuitable for describing a multi-step iterative algorithm with mutable state.
- **Being able to invoke Java methods does not mean SpEL can define those methods.** The logic still has to be written, compiled, and tested in Java.
- **Being able to assign values does not mean having a complete imperative programming model.** SpEL still lacks program-structuring constructs such as type declarations, blocks, loops, and exception handling.
- **Being able to access APIs does not mean every API is automatically permitted.** Access permissions depend on the root object, `EvaluationContext`, resolvers, and integrating Spring components.

## 5. Comparing the Same Requirement

Suppose an application needs to decide whether an order must move to a manual review step.

If only producing a label from existing data is needed, SpEL is suitable:

    #order != null and #order.total >= #limit ? 'REVIEW' : 'APPROVE'

The expression takes data from the context and returns a result. It fits cleanly in configuration or annotations when the rule is short and stable.

If the workflow requires multiple steps, Java is more suitable:

    if (order == null) {
        throw new IllegalArgumentException("Order is required");
    }

    if (order.isCancelled()) {
        return Decision.REJECT;
    }

    BigDecimal total = order.calculateTotal();
    RiskProfile profile = riskService.evaluate(order);

    if (total.compareTo(limit) >= 0 || profile.requiresReview()) {
        auditService.recordReview(order);
        notificationService.notifyReviewer(order);
        return Decision.REVIEW;
    }

    return Decision.APPROVE;

The Java snippet can declare variables, call multiple services, mutate state, throw exceptions, and return from multiple branches. Trying to force this entire workflow into a SpEL expression would make the expression hard to read, hard to test, and overly dependent on context access rights.

A good combination is letting Java execute the workflow and providing small, clearly named functions to SpEL when a simple rule needs to be configurable.

## 6. Data Type Limitations and When Errors Are Detected

SpEL evaluates expressions based on actual objects and the runtime context. Consequently, some issues only appear when the expression is executed:

- A property or method does not exist on the actual object.
- A `null` value appears where the expression does not handle it.
- A value cannot be converted to the desired result type.
- A collection contains an element without the structure expected by the expression.
- A referenced bean, function, or Java type is absent from the context.
- An invoked method throws an exception during execution.

The parser can detect syntax errors when parsing the expression. However, successful parsing does not guarantee that the expression will evaluate successfully for every input.

Applications should handle parsing errors and evaluation errors in the Java layer calling SpEL. Do not expect an expression to catch exceptions on its own and recover like a Java program block.

SpEL has an expression compilation mechanism to optimize certain repeated evaluation cases. This mechanism does not turn SpEL into Java and does not remove language structure limits. Effectiveness also depends on data types and expression stability; enable it only after measuring performance on the actual execution path.

## 7. Restricting Access Rights and Safety

An expression is only as safe as the permissions allowed by its context. `StandardEvaluationContext` provides flexible access capabilities, including reflection mechanisms to access properties and invoke methods. When configured with additional type locators, constructor resolvers, or bean resolvers, expressions can gain further access to Java types, constructors, and beans.

This is useful for expressions controlled by developers. It can become a risk if an application takes verbatim expressions from users, external content, or an untrusted source and evaluates them with a broadly privileged context.

Some practical principles:

1. Do not evaluate arbitrary user-entered expressions using a `StandardEvaluationContext` with broad access permissions.
2. For simple data binding needs, consider `SimpleEvaluationContext`. This context is designed to enable only required capabilities; by default it does not provide type references, constructor calls, or bean lookups like the standard context.
3. Register only the property accessors, method resolvers, and functions that are genuinely needed.
4. Do not place the entire `ApplicationContext`, sensitive services, or highly privileged objects into the root object or expression variables.
5. Prefer application-controlled expressions with a clear scope and tested against representative data.
6. Keep operations with side effects, network access, data writes, or state mutations inside Java services with permission checks and error handling.

Example of a read-only context for a data binding scenario:

    ExpressionParser parser = new SpelExpressionParser();
    EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Expression expression = parser.parseExpression("customer.name");
    String name = expression.getValue(context, order, String.class);

This configuration fits when the expression only needs to read properties via data binding. If the application needs additional capabilities, enable each capability intentionally and understand the permissions it grants.

## 8. When to Use SpEL and When to Use Java?

Use SpEL when:

- A short condition or calculation is needed in Spring configuration.
- A cache key needs to be generated from method parameters or object properties.
- An access condition needs to be checked in a Spring Security integration.
- Data needs to be selected, read, or projected from an existing object or collection.
- The rule is short enough for a maintainer to understand right where it is declared.

Use Java when:

- The logic has multiple steps or multiple branches.
- Loops, exception handling, retries, or task orchestration are needed.
- Multiple services need to be called or transactions need to be coordinated.
- State, resources, threads, or asynchronous tasks must be managed.
- Explicit types, compile-time error checking, safe refactoring, and deep unit testing are required.
- The expression begins containing many method calls, deeply nested conditions, or side effects.

A practical rule: if a reader has to trace through multiple calls to understand an expression, move the logic into a clearly named Java method. SpEL can then call that method if the decision point truly needs to be configurable.

## 9. Takeaways

SpEL is an expression language embedded in the Spring ecosystem. It is very useful for describing values, conditions, property access, permitted method invocations, and collection operations within a specific context.

Its limitations stem from its design goal: SpEL evaluates expressions, whereas Java builds programs. SpEL has conditional operators, selection, projection, variables, and the ability to call Java code, but does not provide the full type declarations, blocks, loops, exception handling, modules, and developer tooling of a general-purpose language.

Use SpEL for short, declarative rules with a clearly scoped permission boundary. Keep business workflows, side effects, and complex logic in Java.