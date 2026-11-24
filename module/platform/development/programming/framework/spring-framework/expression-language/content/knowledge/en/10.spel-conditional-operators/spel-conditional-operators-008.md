# Risk of Mutating State Through Expressions

SpEL can perform data write operations, not just read properties or compute a value. The assignment operator **=** allows an expression to update a writable property or location through the EvaluationContext. Therefore, when an expression is evaluated with **getValue(...)**, the original object can still be modified if the expression string contains an assignment and the context permits that operation.

Risk arises when an expression is placed where readers expect only read operations, such as a condition, a configuration, or a calculation. A hidden assignment inside a SpEL string can alter business state, trigger logic inside a setter, and affect subsequent processing steps.

## Assignments Can Appear Right Inside an Expression

For example, suppose an application has an order object:

~~~java
public class Order {
    private String status;

    public Order(String status) {
        this.status = status;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

An expression that assigns the status can be created:

~~~java
Order order = new Order("PENDING");

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("status = 'APPROVED'");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Object result = expression.getValue(context);
~~~

When the expression is evaluated, SpEL finds the status property on the root object and performs the assignment if the property accessor permits writing. After evaluation, **order.getStatus()** returns **APPROVED**. The expression's return value is not proof that the operation was read-only; the evaluation itself modified the object.

This differs from a read-only expression such as **status == 'APPROVED'**. The comparison expression returns a Boolean without actively assigning a new value to status.

## Why Can getValue Produce Side Effects?

The name **getValue(...)** is often understood as retrieving a value. However, this API asks SpEL to evaluate the entire expression. If the expression contains an assignment operator, method invocation, or another operation with side effects supported by the context, evaluation can mutate state.

Compare the two expressions:

~~~java
Expression readExpression =
        parser.parseExpression("status == 'PENDING'");

Expression writeExpression =
        parser.parseExpression("status = 'APPROVED'");

Boolean isPending =
        readExpression.getValue(context, Boolean.class);

Object assignmentResult =
        writeExpression.getValue(context);
~~~

The first expression checks the current status. The second updates the status. Both can be invoked via getValue, yet their meaning and impact are completely different.

Therefore, do not judge safety solely by the name of the API called. Inspect the expression content, the root object, and the capabilities provided by the evaluation context.

## Data Areas That Can Be Modified

An assignment can affect any location that the corresponding property accessor or access mechanism allows writing to. Common cases include:

- **JavaBean property:** assigning to a property through a setter.
- **Nested property:** updating a property deep inside an object graph, for example **customer.address.city**.
- **Collection or array element:** replacing an element at a writable index, for example **items[0]**.
- **Map entry:** updating the value at a key if the accessor supports that operation.
- **Shared data object:** modifying the root object or a nested object that other components also reference.

For example, **address.city = 'Da Nang'** can update city on the address object. The expression **items[0] = 'Updated'** can replace the first element of a collection. These operations depend on object structure, accessor writability, and target data type.

If a property has no setter, a collection does not support updates, or the target location does not exist, the write operation may fail during evaluation. The fact that an expression parses successfully does not mean every assignment will succeed on every object.

## Setters Can Trigger Business Logic

When a property is updated through a setter, side effects can extend beyond changing a field value. A setter may validate state transitions, record an update timestamp, publish events, or modify related properties.

~~~java
public void setStatus(String nextStatus) {
    validateTransition(this.status, nextStatus);
    this.status = nextStatus;
    this.updatedAt = Instant.now();
    publishStatusChangedEvent();
}
~~~

If a SpEL expression assigns to the status property and the property accessor calls this setter, all logic inside the setter can execute. A short expression like **status = 'APPROVED'** can therefore trigger many actions that a reader cannot see directly in the expression string.

This is why SpEL assignments should not be used to replace an important business command. If a status transition requires permission checks, rule validation, audit logging, or coordinating multiple objects, invoke a service method whose name clearly expresses that action.

## Repeated Evaluation Can Repeat Side Effects

An Expression can be parsed once and reused. Reusing an Expression object does not make the expression read-only. Each time it is evaluated, the assignment in the expression can be executed again.

Even if the expression assigns the same value, the setter may still run multiple times. This can emit multiple events, repeatedly update timestamps, write duplicate audit entries, or invoke secondary logic repeatedly.

A common situation is an expression declared in configuration and evaluated by the framework on every request. If the expression contains an assignment, system behavior can depend on how many times the framework evaluates it and in what order. This makes outcomes harder to predict than with a purely read-only expression.

For expressions used in conditions, cache keys, or configurations that may be evaluated multiple times, keep the expressions free of side effects. When updates are needed, perform the write operation at a point in the business flow that the application explicitly controls.

## Impact on Objects Shared Across Multiple Components

The root object may be referenced simultaneously by multiple services, components, or requests. When an expression modifies that object, every component holding a reference can observe the new state.

For example, a shared configuration object may be in use by many requests. An assignment to a property while another request is reading that property can make results depend on execution timing. If multiple threads write concurrently, the application must also handle consistency and synchronization.

SpEL does not automatically create locks, transactions, or synchronization mechanisms for mutated objects. Those guarantees belong to application design. Do not pass shared or long-lived objects into a writable evaluation context without clear control rules.

## In-Memory Changes and Persisted Data

A SpEL assignment directly modifies an object in memory. It does not automatically invoke a repository, open a transaction, or write data to the database.

However, if the root object is an entity managed by a persistence context, property changes can be detected by the ORM. When the transaction flushes or commits, those changes can be written to the database via the persistence provider's dirty checking mechanism.

This means side effects can extend beyond the scope of the expression. A configuration line containing an assignment can indirectly alter persisted data if the object is managed within an active transaction.

For business entities, updates should be performed in a service method with a transaction boundary and validation. SpEL can be used to describe conditions or retrieve values, while state mutation should live where it is observable and controllable.

## Restricting Write Capabilities with EvaluationContext

EvaluationContext determines how SpEL is allowed to read or write data. If the use case only needs reading, choose a read-only context:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

This context is suited for data-binding expressions that only need to read properties. Property write operations via data binding will not be permitted as in a read-write context.

If updating properties via SpEL is genuinely needed, the read-write builder can be used:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Choosing read-write should be intentional. Enable write capabilities only for data flows that need updates, and restrict the root object as well as property accessors. Do not grant a broad context just to solve a simple assignment.

With **StandardEvaluationContext**, an application can configure property accessors, method resolvers, bean resolvers, and other components. Broader capabilities also mean stricter control is needed over what is exposed to expressions.

## Checking Whether an Expression Is Writable

The **Expression** interface provides **isWritable(...)** to check whether the target location pointed to by the expression can be updated in a specific context and root object:

~~~java
Expression nameExpression =
        parser.parseExpression("name");

if (nameExpression.isWritable(context, user)) {
    nameExpression.setValue(context, user, "Alex");
}
~~~

This example checks whether the name property is writable before calling setValue. This practice is useful when an application works with dynamic properties or object structures not fully known at compile time.

However, isWritable only reflects writability according to the current accessor and context. It does not verify that the user has permission to update the data, does not check state-transition rules, and does not guarantee the setter will not produce side effects. Business validation still needs to be performed at the appropriate layer.

## Separating Read and Update Operations

An easy-to-understand design uses an expression to read a value, then lets Java decide when to update:

~~~java
Expression statusExpression =
        parser.parseExpression("status");

String currentStatus =
        statusExpression.getValue(
                readOnlyContext, order, String.class);

if ("PENDING".equals(currentStatus)) {
    orderService.approve(order.getId());
}
~~~

In this example, the expression only reads the status. Approval is delegated to a service method, where permissions, current state, transactions, and audit logging can be handled.

If updating a simple property is part of data binding, **setValue(...)** can be used with a read-write context. But if the change carries business meaning, prefer a clearly named Java API to express the action and its accompanying conditions.

## Places to Avoid Expressions with Assignments

Avoid assignments in expressions designed for reading or computing, such as:

- Permission checks or conditions deciding whether to perform an action.
- Expressions generating cache keys or determining cached values.
- Expressions displaying data on the user interface.
- Configurations that the framework may evaluate multiple times or across multiple requests.
- Expressions obtained from users or uncontrolled configuration sources.
- Expressions operating on entities or objects shared across multiple components.

In these places, side effects can alter data unexpectedly, cause order-dependent bugs, or make the same condition return different results across evaluations.

## If Externally Supplied Expressions Must Be Evaluated

Do not allow an arbitrary SpEL string to operate across the application's entire object graph. If users or external systems are allowed to supply expressions, restrict:

- **Root object:** use a small DTO containing only the necessary data.
- **Property access:** expose only properties on an allowlist using an appropriate accessor.
- **Evaluation context:** use a read-only context if the use case only needs data retrieval.
- **Method access:** do not enable method invocation unless there is a clear requirement.
- **Expression source and lifecycle:** validate before storing, limit length, and control who is allowed to modify expressions.

A read-only context does not automatically make every object safe data. If the root object holds references to services or objects with complex behavior, you still need to restrict what expressions can access.

## Conclusion

Assignments in SpEL can mutate object state right during evaluation. Effects can go through setters, nested properties, collections, or shared objects; setters can also trigger events and business logic. If the object is a managed entity, in-memory changes can be persisted to the database when the transaction flushes or commits.

Keep expressions read-only where the framework expects data retrieval or computation. Use read-only contexts when appropriate, check writability when data binding is needed, and place business mutations in clearly named service methods. This organization makes side effects easier to spot, test, and control.
