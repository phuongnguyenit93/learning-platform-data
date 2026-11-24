# EvaluationContext and the data an expression is allowed to see

In Spring Expression Language (SpEL), an expression does not decide on its own what data it can read or what actions it can invoke. The parser only converts the expression string into an Expression object; at runtime, EvaluationContext provides the root object, variables, functions, and mechanisms to access properties, methods, and types. Therefore, understanding EvaluationContext means understanding the data boundary that an expression can see.

## 1. Position of EvaluationContext in the evaluation process

A SpEL evaluation typically has three components:

1. ExpressionParser parses the string, for example total > 100.
2. Expression holds the parsed expression tree and provides the getValue(...) or setValue(...) methods.
3. EvaluationContext provides the runtime environment for Expression to look up data and perform allowed accesses.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("customer.name");

EvaluationContext context =
        new StandardEvaluationContext(order);

String customerName = expression.getValue(context, String.class);
~~~

Here order is the root object. When the expression reads customer.name, SpEL looks up the customer property on the root object, and then reads name on the customer object. The ability to read these two properties depends on the PropertyAccessors in the context and the structure of the supplied objects.

You can pass the root object directly at evaluation time instead of setting it beforehand in the context:

~~~java
String customerName =
        expression.getValue(context, order, String.class);
~~~

This approach is useful when you want to reuse a configured context while evaluating the expression on different root objects. Keep in mind that the context can still contain variables, resolvers, and configurations shared across evaluations.

## 2. Root object: root object, #root, and #this

The root object is the starting point for an expression to access data. With StandardEvaluationContext, it can be set via the constructor or setRootObject(...). If using the getValue(context, rootObject, ...) overload, the passed object serves as the root object for that evaluation.

SpEL provides two references with distinct meanings:

- #root always points to the root object of the evaluation.
- #this points to the current object that the expression is processing. In collection operations such as selection (.?[...]) and projection (.![...]), #this changes for each element being examined, while #root remains the root object.

For example, suppose order has a lines property which is a list of order lines, each having quantity:

~~~text
#root.lines.?[#this.quantity > 1]
~~~

The expression above filters the lines whose quantity is greater than one. Inside the filter condition, #this is each order line. If you need to read data from the root object within the same expression, you can use #root.

The root object does not have to be a large entity. A small DTO containing only the necessary fields is often a better choice: it clarifies what data is exposed to the expression and reduces the chance of the expression reaching internal parts of the application.

## 3. Data sources and capabilities a context can provide

EvaluationContext does not just hold a root object. Depending on the implementation and configuration, an expression can access the following sources.

### 3.1. Object properties and elements

PropertyAccessor determines how SpEL reads or writes a property. The default accessors of StandardEvaluationContext use reflection to work with ordinary Java properties, such as matching getters or fields.

Example:

~~~text
customer.name
customer.address.city
order.lines[0].sku
settings['region']
~~~

The expressions above can read nested properties, collection elements, arrays, or map values when the accessor and data types support such access. For expressions with assignment, writing also depends on whether the accessor supports writing and whether the context allows that operation.

Do not confuse property names in an expression with database column names. SpEL accesses the in-memory object model at runtime; it does not query the database or load lazy relationships on its own. If an object's getter triggers a query or has side effects, an expression invoking that getter can indirectly cause those corresponding behaviors.

### 3.2. Methods

MethodResolver determines which methods can be called on an object. StandardEvaluationContext uses a reflection-based method resolution mechanism by default, so an expression can invoke matching methods permitted by the object and the resolver.

Example:

~~~text
customer.isActive()
order.calculateTotal()
~~~

Only expose on the root object methods that are meaningful and safe to invoke in an expression context. A getter that looks read-only might still contain complex logic; a business method might mutate state, write data, or call external services.

### 3.3. Variables and functions

Variables are referenced with the # prefix. You can set variables on the context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("minimumTotal", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
        "total >= #minimumTotal"
);

Boolean eligible = expression.getValue(context, Boolean.class);
~~~

Variables are useful when a value needs to participate in an expression but should not be attached to the business object. They also help separate input data from the domain object structure.

You can register a function to invoke a selected static method:

~~~java
Method normalize = TextFunctions.class.getMethod(
        "normalize", String.class);

context.registerFunction("normalize", normalize);

Expression expression = parser.parseExpression(
        "#normalize(customer.name)"
);
String normalizedName = expression.getValue(context, String.class);
~~~

A registered function becomes a capability that the expression can invoke. Only register functions whose inputs, outputs, and side effects are controlled. Do not register a general-purpose utility class if that class exposes many unnecessary operations.

### 3.4. Beans in the Spring container

An expression can reference a bean using the @beanName syntax, but this capability requires an appropriate BeanResolver configured in the context. For example, when the context is connected to a Spring BeanFactory, BeanFactoryResolver can be used:

~~~java
context.setBeanResolver(new BeanFactoryResolver(beanFactory));
~~~

Once configured, the expression can reference a resolved bean, such as @pricingService. The fact that a bean exists in the application context does not mean every SpEL context automatically sees that bean. Bean references only work when the evaluation's context has a corresponding resolver.

Exposing service beans into the expression scope significantly increases the power of the expression: it can call the methods that the bean exposes. Only enable this capability when the use case truly requires it and only allow selected beans.

### 3.5. Java types and object instantiation

With a full context like StandardEvaluationContext, SpEL can support type references via T(...) and object creation via new ...:

~~~text
T(java.lang.Math).max(10, 20)
new java.util.Date()
~~~

Type resolution depends on TypeLocator; object creation depends on ConstructorResolver. These capabilities are useful in controlled internal expressions, but are usually unnecessary for expressions that only filter or display data. If the expression input comes from users, allowing type and constructor access can expand the action scope beyond expectations.

### 3.6. Conversion, comparison, and operators

The context also provides TypeConverter, TypeComparator, and OperatorOverloader. They affect how SpEL converts value types, compares two objects, and handles operators.

For example, numeric comparisons or assigning a value from a string to a specifically typed property may require type conversion. When an application uses a custom ConversionService or specific data types, configuring an appropriate converter helps expressions behave consistently with the application's data model.

These components are not independent data sources like the root object or variables; they are the rules that govern how the expression manipulates the data it has accessed.

## 4. StandardEvaluationContext and SimpleEvaluationContext

Two commonly used implementations serve different capability levels.

### 4.1. StandardEvaluationContext

StandardEvaluationContext provides a fuller set of SpEL capabilities. It supports configuring the root object, variables, functions, property accessors, method resolvers, constructor resolvers, type locators, type converters, type comparators, operator overloaders, and bean resolvers.

Its default accessors and resolvers allow Java access via reflection. This is an appropriate choice when the application controls the expressions and needs advanced SpEL features. However, it should not be treated as a sandbox for untrusted expressions. The root object, variables, functions, and bean resolver can expose more data or actions than intended.

### 4.2. SimpleEvaluationContext

SimpleEvaluationContext is designed for situations requiring a restricted subset of SpEL, especially data binding. The builder requires explicitly choosing how properties are accessed, for example:

~~~java
EvaluationContext readOnlyContext =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Boolean active = parser.parseExpression("customer.active")
        .getValue(readOnlyContext, order, Boolean.class);
~~~

forReadOnlyDataBinding() is suitable when the expression only needs to read data. If the use case needs to write properties, forReadWriteDataBinding() can be considered, but write permission should only be enabled when specifically required and input data is controlled.

SimpleEvaluationContext does not support features such as Java type references, constructor instantiation, and bean references. Instance method invocation is also not enabled by default; the builder can explicitly enable it with withInstanceMethods() when needed. Restricting features helps narrow the access surface, though you still need to control the root object and accessors provided.

### 4.3. Choosing an implementation by requirement

| Need | Configuration direction |
|---|---|
| Reading DTO properties for filtering or display | SimpleEvaluationContext.forReadOnlyDataBinding() |
| Updating properties via expressions | Consider read-write only when input is controlled |
| Calling selected instance methods | Enable method invocation only when truly needed; restrict objects and methods |
| Needing variables, functions, beans, or type/constructor access | Use a context supporting the corresponding features and configure each capability intentionally |
| Evaluating user-supplied expressions | Use a restricted context, a narrow DTO, and an allowlist; avoid granting general permissions |

No implementation automatically makes expressions safe in every scenario. The level of safety also depends on the data passed in, the installed accessors/resolvers, and the origin of the expression.

## 5. Data boundaries are the boundaries of the object graph and resolvers

An expression can only reach data that the context and the objects supplied to it allow accessing. Picture an access path starting from the root object, passing through property accessors, and possibly continuing to child objects, collections, maps, or methods accepted by resolvers.

For example, if the root object is a DTO with only displayName and status, the expression cannot naturally read passwordHash from another entity that the DTO does not reference. Conversely, if the root object is a service holding references to repositories, the application context, and multiple entities, letting the expression call methods on the service can open a path to a very broad range of data.

Therefore, the key questions when designing a context are not only "which fields does the expression need to read?" but also:

- Which objects does the root object reference?
- Which properties can be read or written?
- Which methods can be called and what side effects do they have?
- Which variables, functions, or beans are registered?
- Are Java type access or object creation allowed?
- Are custom type conversions or operators needed?

A well-designed context provides only the exact capabilities that the use case requires.

## 6. Configuration example following the principle of least privilege

Suppose a screen needs to filter orders by minimum total amount and customer status. The goal is strictly to read data for displaying results.

~~~java
ExpressionParser parser = new SpelExpressionParser();

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression filter = parser.parseExpression(
        "total >= 100 and customer.active"
);

Boolean matches = filter.getValue(
        context,
        order,
        Boolean.class
);
~~~

This example illustrates the idea of using a read-only context and passing the root object separately per evaluation. If the expression needs a #minimumTotal variable, verify that the implementation/builder being used supports variables in your Spring version; if StandardEvaluationContext capabilities are needed, configure them explicitly and limit the data passed in. Do not switch to a full context merely for convenience in accessing a large object.

When custom property access is needed, you can provide a PropertyAccessor that only reads allowlisted properties. When method calls are needed, you can use a resolver that restricts methods or only supply DTOs with pure, side-effect-free methods. When bean references are needed, configure a resolver and expose only selected beans.

## 7. Risks when evaluating untrusted expressions

A SpEL expression can do much more than read a value. With a broad context, an expression can call methods, read nested objects, reference beans, access types, or instantiate objects. Therefore, you should not take an expression string submitted by a user and evaluate it directly with a StandardEvaluationContext given the entire application context.

Practical principles:

1. Prefer SimpleEvaluationContext for data binding or read-only filter expressions.
2. Supply a minimal DTO as the root object, not a service, repository, or application context.
3. Register only necessary variables and functions; avoid general-purpose functions that can perform I/O or mutate state.
4. Configure BeanResolver, TypeLocator, ConstructorResolver, or method invocation only when the use case requires them.
5. Restrict properties and methods via custom accessors/resolvers if input data is untrusted.
6. Isolate expressions per user or request; do not let variables and root objects from one evaluation leak into another.
7. Control evaluation duration and frequency if expressions can be complex or run over large datasets.

Do not use successful parsing as proof that an expression is safe. The parser confirms that the syntax can be parsed; access permissions and behavior only emerge when the expression is evaluated within a specific context.

## 8. EvaluationContext in Spring integrations

When using SpEL directly, the application usually creates the parser and context itself. When using SpEL through Spring features such as @Value, caching, method security, or other configuration, the integrating framework creates the context according to that feature's own contract.

Therefore, available variables, the root object, bean references, and supported syntax can differ across integrations. For example, an expression in method security may provide information about the method invocation, parameters, and authentication; an expression in value configuration may have a different root object and bean resolver. Do not take the variable list of one integration and assume the same list exists everywhere.

When you need to know what data an expression sees at a specific integration point, consult the documentation of that feature itself and inspect the implementation/context used at the evaluation point. If the application has a customizer or expression handler, inspect that configuration because it may add or restrict resolvers.

## 9. How to diagnose when an expression cannot see data

When an expression reports that a property, variable, bean, or method cannot be found, check in this order:

1. What is the actual root object of the evaluation? Is the wrong object or null being passed?
2. Does the property name match a getter/field supported by the accessor?
3. Is the expression inside a selection/projection causing #this to point to the current element?
4. Was the variable set with the exact name? Inside the expression, #variableName must be used.
5. Was the function registered with the exact name and method signature?
6. Does a bean reference have a corresponding BeanResolver?
7. Is SimpleEvaluationContext restricting a feature the expression needs to use?
8. Is a custom property accessor, method resolver, or type locator blocking that access?
9. Is the result type requested in getValue(..., ResultType.class) compatible with the actual value?

Distinguishing syntax errors, property/method resolution errors, and type conversion errors helps pinpoint the right configuration layer to fix.

## 10. Summary

EvaluationContext is the contract between a SpEL expression and data at runtime. The root object establishes the starting point; variables and functions provide additional inputs; property accessors and method resolvers decide how objects are accessed; bean resolvers, type locators, and constructor resolvers extend capabilities when configured; converters, comparators, and operator overloaders define how values are manipulated.

When designing, start from the data and actions the expression actually needs. Supply a narrow root object, prefer a read-only context, and enable each resolver based on specific requirements. That structure makes expressions easy to understand, easy to control, and prevents accidentally turning a simple data rule into a deep access path into the application.