# Managing Lifecycle and Mutability of Variables in SpEL

Variables in Spring Expression Language (SpEL) are data placed in EvaluationContext and referenced in expressions with the # prefix. Variables help separate runtime data from the expression string: the same expression can be evaluated multiple times with different values without recreating the syntax.

To manage variables properly, you need to understand which EvaluationContext a variable belongs to, how long it lives, how values are updated or replaced, and what happens when a variable references a mutable object. SpEL does not automatically tie a variable's lifecycle to request, session, or bean scope; the actual lifecycle depends on how the application creates, shares, and discards the context.

## 1. Objectives and Prerequisites

After this lesson, you can:

- Declare and read variables using setVariable and #variable syntax.
- Distinguish variables from the root object, properties, and bean references.
- Understand that variables are stored in EvaluationContext and do not automatically exist globally.
- Change variable values between evaluations.
- Distinguish replacing a variable's reference from mutating the state of the object the variable points to.
- Use assignment in SpEL when the use case permits updates.
- Manage null variables, data types, and variable names.
- Avoid sharing a mutable context across unrelated threads or requests.
- Write tests for variable lifecycle, values, and mutability.

You should know how to create SpelExpressionParser, Expression, and EvaluationContext, along with Java objects, collections, and basic data types.

## 2. What Is a Variable in SpEL?

A variable is a value registered in EvaluationContext. When writing an expression, reference the variable with the # character at the start of the name:

~~~text
#name
~~~

In Java, register the variable using the name without the # character:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("name", "An");
~~~

Reading the value:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("#name");

String name = expression.getValue(context, String.class);
~~~

The result is An.

The name in setVariable is name; in the expression it is #name. Do not pass # into the name when calling setVariable.

Variables can hold many kinds of objects:

- String, Number, and Boolean.
- DTOs or domain objects.
- List, Set, and Map.
- The null value.
- Objects created by the application to serve a single evaluation.

SpEL does not require every variable to be a string. The runtime type of the object placed in the context affects property access, method invocation, operators, and result type.

## 3. Variable Lifecycle Is Tied to EvaluationContext

Variables are stored in the context where the application registered them. Therefore, a variable's lifetime depends on the lifetime and usage of that context.

~~~java
StandardEvaluationContext firstContext =
    new StandardEvaluationContext();

firstContext.setVariable("user", "An");

StandardEvaluationContext secondContext =
    new StandardEvaluationContext();
~~~

The user variable registered in firstContext does not automatically appear in secondContext. The two contexts have separate variable scopes.

You can visualize this as:

~~~text
firstContext
  variables:
    user -> "An"

secondContext
  variables:
    (user not registered yet)
~~~

Creating an Expression and evaluating it with a different context does not automatically transfer variables from the old context to the new context. Expression holds the parsed structure; variable values are looked up in the context passed at evaluation time.

This allows reusing the same Expression across multiple contexts:

~~~java
Expression expression = parser.parseExpression("#user");

StandardEvaluationContext contextA =
    new StandardEvaluationContext();
contextA.setVariable("user", "An");

StandardEvaluationContext contextB =
    new StandardEvaluationContext();
contextB.setVariable("user", "Binh");

String a = expression.getValue(contextA, String.class);
String b = expression.getValue(contextB, String.class);
~~~

The results are An and Binh, respectively.

### 3.1. Variables Have No Automatic Request or Session Scope

SpEL does not automatically recognize a variable as request-scoped, session-scoped, or application-scoped. Where a context is created and how long it is kept is up to the application.

For example:

- Creating a context for each request processing pass: variables are typically only used during that processing pass.
- Creating a context within a batch job: variables may live for the duration of the job.
- Keeping a context inside a singleton object: variables may live longer than expected if unmanaged.
- Creating a new context per tenant: variable data is isolated per context if the application does not share internal objects.

Do not infer scope from variable names. Identify where the context is created, where variables are registered, where evaluation happens, and when the context is discarded.

## 4. Changing Variable Values Between Evaluations

You can call setVariable multiple times with the same name. The new value replaces the value currently registered for that name in the context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("threshold", 100);

Expression expression =
    parser.parseExpression("#amount >= #threshold");

context.setVariable("amount", 120);
Boolean first = expression.getValue(context, Boolean.class);

context.setVariable("threshold", 150);
Boolean second = expression.getValue(context, Boolean.class);
~~~

The first result is true; the second is false.

The Expression does not need to be re-parsed just because a variable value changes. At evaluation time, SpEL reads the current value from the context.

This approach works well when the expression rule is stable while data changes. However, if the variable's type changes between evaluations, the expression may yield a different result or throw an error because operand types are no longer compatible.

### 4.1. Replacing a Value vs. Mutating the Referenced Object

Suppose the customer variable holds an object:

~~~java
Customer customer = new Customer();
customer.setName("An");

context.setVariable("customer", customer);
~~~

There are two different kinds of changes:

1. Calling setVariable("customer", anotherCustomer) replaces the object referenced by the variable name customer.
2. Calling customer.setName("Binh") changes the state of the object currently referenced by the variable.

In the second case, the variable still references the same object; the object's contents changed. The next evaluation can observe the new value because the expression reads the current object.

This is an important distinction when working with mutable objects. A variable does not create a deep copy of the object assigned to it.

## 5. Null Values and Unregistered Variables

A variable can hold a null value if the application registers it as such. When an expression reads the variable, the result can be null; subsequent operations must handle null according to business logic.

Example:

~~~java
context.setVariable("nickname", null);
~~~

Expression:

~~~text
#nickname
~~~

can return null. If the expression continues to access properties or call methods on that variable, use null-safe navigation or an appropriate guard:

~~~text
#nickname != null and #nickname.length() > 0
~~~

Short-circuit AND prevents calling length when nickname is null.

An unregistered variable is a different configuration situation. When looking up, the application can use lookupVariable to inspect the current value:

~~~java
Object value = context.lookupVariable("nickname");
~~~

If you need to clearly distinguish an unprovided variable from a provided variable with a null value, manage a set of input variable names or a request object with an explicit schema. Do not rely on a single null read to interpret data state if business logic needs to distinguish those two cases.

## 6. Variable Data Types

setVariable accepts Object, so the context can hold many different runtime types. The expression uses the actual type of the value when accessing properties or calling methods.

Example:

~~~java
context.setVariable("quantity", 3);
context.setVariable("price", new BigDecimal("12.50"));
context.setVariable("enabled", true);
~~~

Corresponding expressions:

~~~text
#quantity * #price
~~~

~~~text
#enabled and #quantity > 0
~~~

When retrieving results, request the expected type when appropriate:

~~~java
BigDecimal total =
    parser.parseExpression("#quantity * #price")
        .getValue(context, BigDecimal.class);
~~~

If a variable was initially an Integer and is later replaced with a string, an arithmetic expression may stop working. Keep variable types stable according to the expression's contract.

For collections, use explicit generic types in Java, such as List<Order> or Map<String, BigDecimal>, so code supplying data and code consuming results are easier to understand. SpEL still operates on runtime objects, but declaring types in Java helps reduce bugs from inconsistent data.

## 7. Reassigning Variables from Inside an Expression

SpEL supports the assignment operator =. In contexts and use cases that permit writing, a variable can be reassigned inside an expression:

~~~text
#status = 'READY'
~~~

An expression can use the current value to compute a new value:

~~~text
#counter = #counter + 1
~~~

Assignment updates the variable's value in the EvaluationContext being used for evaluation. Subsequent evaluations on the same context can read the new value.

Java example:

~~~java
context.setVariable("counter", 0);

Expression increment =
    parser.parseExpression("#counter = #counter + 1");

Integer first = increment.getValue(context, Integer.class);
Integer second = increment.getValue(context, Integer.class);
~~~

First the counter variable becomes 1; next it becomes 2.

Assignment is a side effect. Do not use it in expressions expected to be pure queries or condition checks. If an expression is evaluated multiple times or across multiple branches, the result can depend on evaluation order.

If you only need to compute a new value without updating the context, use a pure expression and receive the result in Java rather than reassigning the variable.

## 8. Variables and Functions Share a Namespace

SpEL allows registering functions to invoke from expressions using #functionName(...) syntax. A function is registered in the context via a Method, and for storage it uses the context's variable mechanism.

Example:

~~~java
Method formatMethod =
    Formatter.class.getDeclaredMethod("format", String.class);

context.registerFunction("formatName", formatMethod);
~~~

Expression calling the function:

~~~text
#formatName(#name)
~~~

Because functions and variables share the naming mechanism in the context, avoid giving the same name to a data variable and a function. Choose meaningful names, such as formatName for the function and customerName for the variable.

Only register functions controlled by the application. Functions can invoke Java methods and perform side effects depending on implementation; do not expose arbitrary methods merely to shorten expressions.

## 9. Variables, Root Object, and Bean References

Three common ways to supply data:

| Provisioning Method | SpEL Syntax | Value Source |
|---|---|---|
| Root object | name or #root.name | Object set as root |
| Variable | #customer | setVariable in EvaluationContext |
| Bean reference | @customerService | BeanResolver and Spring container |

The root object is the default target when an expression accesses an unprefixed property. #root always represents the root object; #this represents the current object at the evaluation position.

Variables are referenced with # and have a lifecycle tied to EvaluationContext. Bean references use @ and are resolved via BeanResolver.

Do not put services or overly privileged objects into variables merely for convenience. If an expression only needs data, pass a small DTO as the root object or variable. If a bean is needed, expose the exact bean and restrict callable methods.

## 10. Managing Mutable Contexts and Concurrency

EvaluationContext can hold variables and accessor/resolver configurations. When the application calls setVariable, the context changes state. Therefore, do not use a shared context and mutate variables per concurrent request without isolation or synchronization.

Design-wise dangerous example:

~~~text
Request A: setVariable("user", userA)
Request B: setVariable("user", userB)
Request A: evaluate #user.name
~~~

If two requests share one mutable context, Request A may read the value just written by Request B. As a result, data across requests can get mixed up.

Safer ways to organize this:

- Create a dedicated context for each request or each evaluation requiring separate data.
- Create a new context from a pre-prepared shared configuration if resolvers/accessors need to be reused.
- Do not store user data variables inside a singleton context.
- If a context must be shared, do not mutate variables concurrently; use synchronization and a clear usage contract.
- Do not share mutable objects across requests without ownership control.

You can reuse a parsed Expression, but that does not mean every EvaluationContext holding runtime data should also be shared.

## 11. SimpleEvaluationContext and Variables

SimpleEvaluationContext also supports variables through the EvaluationContext contract, while restricting many capabilities compared to StandardEvaluationContext.

Example:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimum", 100);
~~~

The expression can read the variable:

~~~text
#amount >= #minimum
~~~

Choose SimpleEvaluationContext when the use case only needs data binding with restricted permissions. If method invocation, type references, or bean references are needed, carefully review requirements and configure explicitly; do not switch to a broader context just to bypass an error without diagnosing the root cause.

Variables are merely supplied data. Read/write permissions on properties or method calls on the object referenced by a variable still depend on the context's accessors and resolvers.

## 12. Testing Lifecycle and Mutability

A test suite should check:

| Case | Action | What to Verify |
|---|---|---|
| Variables in a new context | Register user in context A | Context B does not automatically have user |
| Replacing values | Call setVariable twice with same name | Subsequent evaluation reads new value |
| Replacing object reference | Assign a different object to variable | Expression reads new object |
| Mutating mutable object | Call setter on current object | Expression sees new state |
| Null value | Register a null variable | Expression handles null as designed |
| Unregistered variable | Do not call setVariable | Application detects unprovided data |
| Changing type | Change Number to String | Expression handles or rejects incompatible type |
| Assignment in expression | Reassign #counter | Context retains new value for next evaluation |
| Function colliding with variable name | Register same name | Naming design prevents conflicts |
| Concurrent contexts | Use data for two requests | No variable values bleed across |

Test both the return value and the state of the context/object after evaluation. For expressions with assignment, verify the variable changed. For read-only expressions, confirm input data was not unexpectedly mutated.

## 13. Common Errors and How to Handle Them

| Symptom | Common Cause | Resolution |
|---|---|---|
| Expression cannot find variable | Not registered with exact name or wrong context used | Check setVariable and context passed to getValue |
| Variable returns null | Value registered as null or data not supplied | Define clear null policy and inspect data source |
| Subsequent evaluation still uses old value | Variable was updated in a different context | Verify the exact EvaluationContext instance |
| Expression fails after changing variable type | Runtime type no longer compatible with operator or method | Keep types consistent with contract or validate before setting |
| Mutating variable affects another object | Variable holds reference to shared mutable object | Create separate objects or manage ownership |
| Values mix across requests | Mutable context shared | Isolate context per request or synchronize properly |
| Wrong function called | Function name collides with variable name or wrong Method registered | Use clear naming namespaces and check method signature |
| Assignment not permitted | Context/accessor lacks write permission or expression is not a valid assignment target | Check context and expression syntax |

When debugging, note the context instance, variable name, runtime type, and when setVariable was called. Do not inspect only the expression string; the same expression can produce different results with different contexts and data.

## 14. Practice Exercises

1. Create a context and register variables name, age, active; read them with an expression.
2. Parse a single expression and evaluate it with two contexts holding different data.
3. Change a variable's value using setVariable and observe the result of the next evaluation.
4. Register a Customer object, change a property on the object, and re-evaluate.
5. Replace the object reference with a different Customer and contrast that with mutating a property.
6. Register a null variable and try safe navigation along with Elvis.
7. Use assignment #counter = #counter + 1 and check state after multiple evaluations.
8. Register a function and a variable, ensuring their names do not collide.
9. Create two independent contexts for two users and verify data does not leak between them.
10. Try SimpleEvaluationContext with variables and verify capability limits.

## 15. Checklist Before Using Variables in an Application

- [ ] Have you identified which context owns the variable?
- [ ] Have you determined how long the variable lives?
- [ ] Is a separate context created per request or evaluation needing isolated data?
- [ ] Does the name in setVariable match the name after the # symbol?
- [ ] Is the variable's runtime type stable according to the expression's contract?
- [ ] Have you distinguished replacing a reference from mutating a mutable object?
- [ ] Are null values and unprovided variables handled clearly?
- [ ] Is assignment used in the expression, and is that side effect necessary?
- [ ] Do any function names conflict with variable names?
- [ ] Is a mutable context shared across threads or requests?
- [ ] Do objects in variables contain services or sensitive data?
- [ ] Does the context grant only the read/write and method invocation permissions needed?

## 16. Conclusion

SpEL variables are stored in EvaluationContext and read using the # prefix. A variable's lifecycle depends on the context lifecycle managed by the application; it does not automatically bind to request, session, or bean scope. setVariable can change values for subsequent evaluations, while a referenced mutable object can change without replacing the variable itself. Keep data types stable, handle null explicitly, avoid unnecessary assignment, and isolate mutable contexts across requests. Parsed Expressions can be reused across multiple independent contexts, helping separate rules from runtime data.