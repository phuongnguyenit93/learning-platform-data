# SimpleEvaluationContext with a restricted operation surface

**SimpleEvaluationContext** is a SpEL **EvaluationContext** implementation designed for cases where only a subset of the expression language's capabilities is needed. Instead of opening up every access and execution mechanism that a general-purpose evaluation context can provide, you explicitly select only the required capabilities such as reading properties, converting types, or calling instance methods.

The goal is to provide a leaner and more controllable expression evaluation environment, especially in data binding scenarios or when expressions do not need access to broad parts of the application.

## Why is a restricted evaluation context needed?

SpEL can do much more than read a property. Depending on configuration, an expression can call methods, reference Java types, instantiate objects, access beans, or use extension mechanisms. Those capabilities are useful in developer-controlled configurations, but can go beyond the needs of an expression meant only for reading data.

For example, an admin screen might need an expression to display the name and status of a DTO. If only those properties need to be read, granting the expression permission to call arbitrary methods, create objects, or access beans is unnecessary.

**SimpleEvaluationContext** solves this by letting the application choose a restricted configuration. Features excluded from the context do not become available merely because SpEL syntax supports them. An expression's actual permissions depend on the property accessors, method resolvers, type converters, and other components supplied by the context.

## SimpleEvaluationContext and StandardEvaluationContext

Both classes implement EvaluationContext, but serve different usage scopes:

| Aspect | SimpleEvaluationContext | StandardEvaluationContext |
|---|---|---|
| Purpose | Evaluating expressions with a restricted capability set | Evaluating expressions with broader extensibility |
| Property access | Select property accessors; provides builders for data binding | Can configure multiple property accessors |
| Calling instance methods | Not enabled by default; can be explicitly enabled via builder | Supports configurable method resolver mechanisms |
| Type references and constructors | Does not provide these mechanisms | Has type locator and constructor resolvers |
| Bean references | Does not provide a default bean resolver | Can configure a bean resolver |
| Control level | Suitable when wanting to restrict the operation surface | Suitable when needing deep integration and rich SpEL features |

The table above describes design orientation. The final capabilities of a context also depend on the registered components and how the application configures them.

## Creating SimpleEvaluationContext

The simplest way is to use the builder for read-only data binding:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

This builder configures property access in read-only mode. It is suitable when expressions need to read JavaBean properties without modifying the object.

If the use case needs to update properties through expressions, you can choose the read-write builder:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Choosing read-only or read-write should accurately reflect the task's requirements. For expressions used to display or inspect data, read-only is usually the sensible starting point. Only enable write capability when the application genuinely needs expressions to update objects.

## Example: reading properties of an object

Suppose the application has a user object:

~~~java
public class UserProfile {
    private final String displayName;
    private final int age;

    public UserProfile(String displayName, int age) {
        this.displayName = displayName;
        this.age = age;
    }

    public String getDisplayName() {
        return displayName;
    }

    public int getAge() {
        return age;
    }
}
~~~

We want to evaluate an expression that checks the age and returns the display name:

~~~java
UserProfile user = new UserProfile("An", 21);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "age >= 18 ? displayName : 'Underage'");

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

String label = expression.getValue(context, user, String.class);
~~~

Here, **user** is passed as the root object for the evaluation. The data binding property accessor reads the corresponding properties through their getters. The expression uses a comparison and a conditional operator to produce a string result.

Calling **getValue(context, user, String.class)** explicitly specifies the context, root object, and desired result type. The context can be reused with different root objects if they match the properties referenced by the expression.

## Using variables in expressions

An evaluation context can also hold variables supplied by the application. Variable names in an expression are placed after the **#** symbol:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimumAge", 18);

Expression expression =
        parser.parseExpression("age >= #minimumAge");

Boolean eligible =
        expression.getValue(context, user, Boolean.class);
~~~

The **minimumAge** variable does not automatically appear inside the object. The application explicitly puts it into the context using **setVariable**. This allows the expression to receive the exact data it needs without adding every value onto the root object.

When a context is reused, variables should be managed per evaluation to avoid accidentally using data from a previous request. In multi-threaded applications, pay attention to the context's lifecycle and sharing scope; do not share a context with mutable state across requests if doing so could mix variables or evaluation data.

## When should instance method calls be allowed?

By default, SimpleEvaluationContext's data binding builders do not enable calling instance methods. If an expression genuinely needs to invoke a method on the root object or a property, it can be explicitly enabled with **withInstanceMethods()**:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();

Expression expression =
        parser.parseExpression("displayName.toUpperCase()");

String normalizedName =
        expression.getValue(context, user, String.class);
~~~

Enabling instance methods widens the operation surface. Only enable it when expressions need specific methods and the exposed objects are controlled. Do not enable it out of habit if property reading already satisfies the requirement.

Distinguish instance methods from referencing a Java type or calling a constructor. **withInstanceMethods()** only opens instance method invocation according to the context's mechanism; it does not turn SimpleEvaluationContext into StandardEvaluationContext and does not add full features such as type references, constructors, or bean references.

## Choosing custom property accessors

The two data binding builders are convenient when objects follow JavaBean conventions. If the application wants to restrict exactly which properties an expression is allowed to read or write, you can build the context from specific **PropertyAccessor** instances:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forPropertyAccessors(myPropertyAccessor)
                .build();
~~~

A **PropertyAccessor** is the SpEL component used to read or write a property on a target object. A custom accessor can expose only selected data fields, map expression property names to internal structures, or apply application-specific access rules.

When using a custom accessor, clearly define whether it supports reading or writing, what target object types it handles, and which property names are accepted. Do not accidentally register an accessor with broader access capabilities than required. If multiple accessors are needed, you can pass multiple accessors into the factory method.

## Restriction does not mean an absolute sandbox

SimpleEvaluationContext helps narrow the capabilities an expression can use, but choosing the context class alone is not enough to guarantee safety for every external expression.

A read-only context can still expose a lot of data if the root object has too many properties. When instance methods are enabled, expressions can call allowed methods on reachable objects. A custom property accessor can also open more capabilities than intended if written or configured carelessly.

If you must evaluate expressions provided by users or external systems, apply the following principles:

- Use a small root object containing only data needed for the expression; avoid putting services, repositories, or resource-managing objects into the context.
- Start with **forReadOnlyDataBinding()** if only reading data is needed.
- Do not enable **withInstanceMethods()** unless there is a clear use case.
- Prefer allowlist-based property accessors when exact control over exposed property names is needed.
- Supply only variables and data that the expression actually requires.
- Control the expression source, limit complexity, and handle parse or evaluation errors as potentially invalid input.

SimpleEvaluationContext does not automatically limit execution time or expression length. If expressions come from untrusted sources, the application must still design resource limits and validation policies appropriate for the execution environment.

## When should SimpleEvaluationContext be chosen?

Consider SimpleEvaluationContext when:

- Expressions only need to read or update data following data binding rules.
- The application wants to allow configuring simple expressions over DTOs or data objects.
- Java type references, object creation, or bean access are not needed.
- You want to opt in to instance methods deliberately rather than allowing all extension mechanisms by default.
- You want to define custom property accessors to expose a small data surface.

If the use case needs bean references, type references, constructor invocation, or custom method resolvers, **StandardEvaluationContext** may be more suitable. In that case, the application needs to explicitly configure allowed components and carefully control expression sources.

## Conclusion

SimpleEvaluationContext is the choice for SpEL expressions that only need a sufficient subset of capabilities. Builders such as **forReadOnlyDataBinding()**, **forReadWriteDataBinding()**, and **forPropertyAccessors(...)** let applications choose how properties are accessed; **withInstanceMethods()** opens method invocation only when genuinely needed.

Limiting the operation surface makes expressions easier to control and avoids exposing unnecessary features. Nevertheless, actual safety still depends on the root object, accessors, variables, and capabilities that the application intentionally provides to the evaluation context.
