# Managing Variable Lifecycle and Mutability in SpEL

Variables in Spring Expression Language (SpEL) are data registered in an EvaluationContext and referenced in expressions using the # prefix. Variables help separate runtime data from the expression string: the same expression can be evaluated multiple times with different values without re-parsing the syntax.

To manage variables properly, you need to understand which context a variable belongs to, how long it lives, how values are replaced, and what happens when a variable references a mutable object. SpEL does not automatically tie variable lifecycles to request, session, or bean scopes. The actual lifecycle depends on how the application creates, shares, and releases the EvaluationContext.

## 1. Objectives and Prerequisites

After this lesson, you will be able to:

- Declare, read, and update variables using the EvaluationContext API.
- Distinguish variables from the root object, properties, and bean references.
- Explain why a variable's lifecycle is tied to the lifecycle of its EvaluationContext.
- Reuse an Expression across multiple independent contexts.
- Distinguish replacing an object reference from mutating the referenced object's state.
- Handle missing variables, null values, and incompatible data types.
- Understand variable assignment in SpEL and its effect on the context.
- Avoid sharing a mutable context across unrelated requests or threads.
- Design tests for variable lifecycle, values, and mutability.

You should know how to create SpelExpressionParser, Expression, and EvaluationContext, along with Java objects, collections, and basic data types.

## 2. Declaring and Reading Variables

Variables are registered in EvaluationContext. When referenced in SpEL, the variable name has a # prefix.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customerName", "An");

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("#customerName");

String name = expression.getValue(context, String.class);
~~~

The result is An.

The name passed to setVariable does not include the # character; this character only appears in the expression. For example, setVariable("customerName", value) corresponds to #customerName.

Variables can hold many types of objects:

- String, Number, and Boolean.
- DTOs or domain objects.
- List, Set, and Map.
- Objects created by the application to serve a single evaluation.
- Complex structured values, as long as the EvaluationContext and accessors can access them.

SpEL does not require every variable to be a string. The runtime type of the value affects property access, method invocation, operations, and the result type.

## 3. Variable Lifecycle Is Tied to EvaluationContext

Variables are stored in the context where the application registered them. Therefore, the lifetime of a variable depends on the lifetime and usage of that context.

~~~java
StandardEvaluationContext requestA =
    new StandardEvaluationContext();

requestA.setVariable("userId", 101);

StandardEvaluationContext requestB =
    new StandardEvaluationContext();
~~~

The userId variable registered in requestA does not automatically appear in requestB. The two contexts have separate variable scopes.

You can visualize this as:

~~~text
requestA
  variables:
    userId -> 101

requestB
  variables:
    (userId not registered)
~~~

Expression holds the parsed structure. Variable values are looked up in the context passed in at evaluation time. Therefore, the same Expression can be reused with multiple contexts:

~~~java
Expression expression =
    parser.parseExpression("#userId");

StandardEvaluationContext contextA =
    new StandardEvaluationContext();
contextA.setVariable("userId", 101);

StandardEvaluationContext contextB =
    new StandardEvaluationContext();
contextB.setVariable("userId", 202);

Integer first = expression.getValue(contextA, Integer.class);
Integer second = expression.getValue(contextB, Integer.class);
~~~

The results are 101 and 202, respectively.

### 3.1. Variables do not have automatic scopes like request or session

SpEL does not automatically treat a variable as request-scoped, session-scoped, or application-scoped. Where a context is created and how long it is kept is an application decision.

Examples:

- Create a context for each request execution: variables are typically used only during that execution.
- Create a context in a batch job: variables may live for the duration of the job.
- Hold a context in a singleton object: variables may live longer than expected if unmanaged.
- Create a separate context per tenant: variable data is isolated by context, provided the underlying objects are not inadvertently shared either.

Do not infer scope from variable names. Determine where the context is created, where variables are registered, where evaluation happens, and when the context is released.

## 4. Replacing Values Between Evaluations

setVariable can be called multiple times with the same name. The new value replaces the current value of that name in the context:

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

The Expression does not need to be re-parsed just because a variable's value changes. When evaluating, SpEL reads the current value from the context.

This approach is useful when expression rules are stable while data changes. However, if a variable's type changes between evaluations, the expression may yield a different result or throw an error because operand types are no longer compatible.

### 4.1. Replacing a reference differs from mutating the referenced object

Suppose the customer variable holds an object:

~~~java
Customer customer = new Customer();
customer.setName("An");

context.setVariable("customer", customer);
~~~

There are two different kinds of changes:

1. Calling setVariable("customer", anotherCustomer) replaces the object referenced by the variable name customer.
2. Calling customer.setName("Binh") mutates the state of the object currently referenced by the variable.

In the second case, the variable still references the same object; the object's contents have changed. The next evaluation can see the new value because the expression reads the current object.

Variables do not create a deep copy of the object assigned to them. If a mutable object is also held by another component, mutations to the object may be visible in multiple places.

## 5. Unprovided Variables and Null Values

Distinguish between data not being provided and a property having a null value.

In StandardEvaluationContext, setVariable(name, null) is used to remove the variable name from the variable map. Therefore, if the application needs to represent an input with a null value, place it inside a DTO or wrapper whose property holds null and pass that object into the context.

Example:

~~~java
public class Input {
    private String nickname;

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}

Input input = new Input();
input.setNickname(null);

context.setVariable("input", input);
~~~

The expression can read:

~~~text
#input.nickname
~~~

The property result is null. This preserves the distinction between an input object that was provided with a null field and a variable name absent from the context.

lookupVariable can be used to read the current value:

~~~java
Object value = context.lookupVariable("input");
~~~

If you need to clearly distinguish an unregistered name from an absent business value, manage the schema or input name set at the Java layer. Do not rely on a single null value to interpret request state if business logic needs to distinguish them.

### 5.1. Handling null in expressions

If a property inside an object can be null, use guards or null-safe navigation:

~~~text
#input.nickname != null and #input.nickname.length() > 0
~~~

Short-circuit AND prevents calling length when nickname is null.

Or provide a default value if that aligns with business rules:

~~~text
#input.nickname ?: 'Guest'
~~~

Do not replace null with a default value mechanically. Null may mean undefined, not yet entered, or invalid; each case may require different handling.

## 6. Variable Data Types

setVariable accepts Object, so a context can hold many different runtime types. Expressions use the value's actual type when accessing properties or calling methods.

~~~java
context.setVariable("quantity", 3);
context.setVariable("unitPrice", new BigDecimal("12.50"));
context.setVariable("enabled", true);
~~~

Corresponding expressions:

~~~text
#quantity * #unitPrice
~~~

~~~text
#enabled and #quantity > 0
~~~

When retrieving the result, request the expected type when reasonable:

~~~java
BigDecimal total =
    parser.parseExpression("#quantity * #unitPrice")
        .getValue(context, BigDecimal.class);
~~~

If a variable is initially an Integer and is later replaced with a String, arithmetic expressions may stop working. Keep variable types consistent with the expression contract.

For collections, use explicit generic types in Java, such as List<Order> or Map<String, BigDecimal>, so both data-providing code and result-consuming code are easier to understand.

## 7. Reassigning Variables from Inside Expressions

SpEL supports the assignment operator =. In contexts and use cases that allow updates, a variable can be reassigned inside an expression:

~~~text
#status = 'READY'
~~~

An expression can use the current value to compute a new value:

~~~text
#counter = #counter + 1
~~~

Assignment updates the variable's value in the EvaluationContext being used for evaluation. Subsequent evaluations on the same context can read the new value.

Example:

~~~java
context.setVariable("counter", 0);

Expression increment =
    parser.parseExpression("#counter = #counter + 1");

Integer first = increment.getValue(context, Integer.class);
Integer second = increment.getValue(context, Integer.class);
~~~

The first time, counter becomes 1; the next time, it becomes 2.

Assignment is a side effect. Do not use it in expressions expected only to query or evaluate conditions. If an expression is evaluated multiple times or across multiple branches, the result may depend on evaluation order.

If you only need to compute a new value without updating the context, use a pure expression and receive the result in Java instead of reassigning the variable.

## 8. Variables and Functions in the Context

SpEL allows registering functions to be called from expressions using the #functionName(...) syntax. Functions are registered in the context through a Method:

~~~java
Method formatMethod =
    Formatter.class.getDeclaredMethod("format", String.class);

context.registerFunction("formatName", formatMethod);
~~~

Expression calling the function:

~~~text
#formatName(#name)
~~~

Functions are registered in the same variable naming mechanism of the context. Therefore, avoid using the same name for a function and a data variable. Choose meaningful names, such as formatName for a function and customerName for a variable.

Only register functions controlled by the application. A function can invoke a Java method and perform side effects depending on its implementation; do not expose arbitrary methods just to make expressions shorter.

## 9. Distinguishing Variables, Root Objects, and Bean References

Three common ways to supply data:

| Provisioning method | Syntax in SpEL | Value source |
|---|---|---|
| Root object | name or #root.name | Object set as root |
| Variable | #customer | setVariable in EvaluationContext |
| Bean reference | @customerService | BeanResolver and Spring container |

The root object is the default target when an expression accesses an unprefixed property. #root represents the root object; #this represents the current object at the evaluation position.

Variables are referenced with # and have a lifecycle tied to the EvaluationContext. Bean references use @ and are resolved via BeanResolver.

Do not place services or broad-privilege objects into variables merely for convenience. If an expression only needs data, pass a small DTO as the root object or variable. If a bean is needed, expose only the exact bean and restrict callable methods.

## 10. Managing Mutable Contexts and Concurrency

An EvaluationContext can contain variables and accessor/resolver configurations. When the application calls setVariable, the context changes state. Therefore, do not use a single shared mutable context and swap variables across concurrent requests without an isolation or synchronization mechanism.

Example of a design that risks mixing data:

~~~text
Request A: setVariable("user", userA)
Request B: setVariable("user", userB)
Request A: evaluate #user.name
~~~

If two requests share a mutable context, Request A may read the value just written by Request B. Data across requests can get mixed up.

A safer organization:

- Create a separate context for each request or each evaluation requiring separate data.
- Reuse the parsed Expression, while passing the appropriate context for each evaluation.
- Do not store variables containing user data in a singleton context.
- If a context must be shared, do not mutate variables concurrently; establish synchronization and a clear usage contract.
- Do not share mutable objects across requests without ownership control.

An Expression can be reused, but that does not mean every EvaluationContext holding runtime data should be shared as well.

## 11. SimpleEvaluationContext and Variables

SimpleEvaluationContext also supports variables through the EvaluationContext contract, while restricting many capabilities compared to StandardEvaluationContext.

Example:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimum", 100);
~~~

An expression can read the variable:

~~~text
#amount >= #minimum
~~~

Choose SimpleEvaluationContext when the use case only needs data binding with restricted permissions. If method invocation, type references, or bean references are required, carefully review requirements and configure specifically; do not switch to a broader context merely to bypass an error whose cause has not been identified.

Variables are simply provided data. Read/write property permissions or method calls on objects referenced by variables still depend on the accessors and resolvers in the context.

## 12. Testing Lifecycle and Mutability

A test suite should check:

| Case | Action | What to verify |
|---|---|---|
| Variable in a new context | Register user in context A | Context B does not automatically have user |
| Replacing value | Call setVariable twice with same name | Subsequent evaluation reads the new value |
| Replacing object reference | Assign another object to the variable | Expression reads the new object |
| Mutating mutable object | Call setter on the current object | Expression sees the new state |
| Unregistered variable | Do not call setVariable | Application handles missing input |
| Null property | Set DTO field to null | Expression handles null as designed |
| Type change | Change Number to String | Expression handles or rejects incompatible type |
| Assignment in expression | Reassign #counter | Context retains new value for next evaluation |
| Function colliding with variable name | Register same name | Naming design avoids conflicts |
| Concurrent contexts | Use data from two requests | Variable values do not mix |

Verify both the return value and the state of the context/objects after evaluation. For expressions with assignment, verify that the variable changed. For read-only expressions, verify that input data was not unexpectedly mutated.

## 13. Common Errors and Resolutions

| Symptom | Common cause | Resolution |
|---|---|---|
| Expression cannot find variable | Not registered under exact name or wrong context used | Check setVariable and context passed to getValue |
| Variable does not have expected value | Value was overwritten or another context was used | Verify the exact EvaluationContext instance |
| Variable removed from context | Called setVariable with null value | Use a DTO/wrapper with a null property if null needs to be represented |
| Expression errors after changing variable type | Runtime type is no longer compatible with operator or method | Keep types per contract or validate before setting |
| Changing variable affects another object | Variable holds a reference to a shared mutable object | Create separate objects or manage ownership |
| Values mixed across requests | Shared mutable context | Isolate context per request or synchronize properly |
| Wrong function called | Function name collides with variable name or wrong Method registered | Use distinct names and verify method signature |
| Assignment does not work as expected | Context or expression does not suit write operations | Check context, variable name, and assignment syntax |

When debugging, record the context instance, variable name, runtime type, and when setVariable was called. The same expression can yield different results with different contexts and data.

## 14. Practice Exercises

1. Create a context and register variables name, age, and active; read them with expressions.
2. Parse a single expression and evaluate it with two contexts containing different data.
3. Replace a variable's value using setVariable and observe the next evaluation result.
4. Register a Customer object, mutate a property of the object, and re-evaluate.
5. Replace the object reference with another Customer and distinguish that from mutating a property.
6. Create a DTO with a null field and read that property via a variable.
7. Use assignment #counter = #counter + 1 and inspect the state after multiple evaluations.
8. Register a function and a variable, ensuring names do not collide.
9. Create two independent contexts for two users and verify data does not mix.
10. Try SimpleEvaluationContext with variables and test capability restrictions.

## 15. Checklist Before Using Variables in an Application

- [ ] Have you determined which context owns the variable?
- [ ] Have you determined how long the variable lives?
- [ ] Is a separate context created for each request or evaluation needing isolated data?
- [ ] Does the name in setVariable match the name after the # sign?
- [ ] Is the variable's runtime type stable according to the expression contract?
- [ ] Have you distinguished replacing a reference from mutating a mutable object?
- [ ] Have you distinguished an unregistered variable from a property with a null value?
- [ ] Is assignment used in the expression, and is that side effect necessary?
- [ ] Do function names collide with variable names?
- [ ] Is a mutable context shared across threads or requests?
- [ ] Does the object in the variable contain services or sensitive data?
- [ ] Does the context grant only the necessary read/write and method invocation permissions?

## 16. Conclusion

SpEL variables are stored in an EvaluationContext and read with the # prefix. A variable's lifecycle depends on the context lifecycle managed by the application; it is not automatically bound to request, session, or bean scope. setVariable can replace values for subsequent evaluations, while a referenced mutable object can change without replacing the variable itself. Keep data types stable, handle nulls explicitly, avoid unnecessary assignments, and isolate mutable contexts across requests. A parsed Expression can be reused across many independent contexts, separating rules from runtime data.