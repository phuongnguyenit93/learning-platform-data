# Risk of Mutating State Through Expressions

SpEL does not only read data and compute values. The language also supports the **assignment operator** to modify properties or data elements if the evaluation context and target object permit writing. Therefore, an expression that looks like an ordinary condition or calculation can still produce side effects on objects during evaluation.

The primary risk is that readers may assume calling **getValue(...)** only retrieves data, while an expression containing an assignment mutates state. If the object is shared, managed by the framework, or used across multiple processing steps, that mutation can affect subsequent behavior.

## The Assignment Operator in SpEL

The **=** operator assigns a value to a property or a writable location. Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression assignment =
        parser.parseExpression("name = 'Alex'");

assignment.getValue(context, user);
~~~

If the root object is user and the name property is writable through the property accessor, the expression assigns the value **Alex** to that property. Evaluating the expression therefore modifies the object in memory.

The same operation can be performed via the **setValue(...)** API:

~~~java
Expression nameExpression =
        parser.parseExpression("name");

nameExpression.setValue(context, user, "Alex");
~~~

The second approach clearly expresses update intent: the application obtains an Expression pointing to the property and then calls setValue with the new value. When the goal is to change data, this API is usually easier to read and search for in source code than hiding an assignment inside an expression invoked via getValue.

## getValue Is Not Always Read-Only

The method name **getValue(...)** can easily lead readers to think it only observes state. Yet if the expression string contains an assignment operator, evaluation can perform the assignment as part of evaluating the expression.

Example:

~~~java
Expression expression =
        parser.parseExpression("status = 'APPROVED'");

expression.getValue(context, order);
~~~

After evaluation, order's status property may have changed if the context allows writing and the object supports updating the property. Therefore, inspect the full expression before using getValue in an integration point where readers expect only read operations.

In particular, expressions may be stored in configuration files or databases. Application maintainers might see only a SpEL string without realizing it is capable of mutating state. Name and organize expressions so that read or write intent is clear.

## Where State Changes Can Occur

An assignment in SpEL can affect several kinds of data, depending on the property accessor and target object:

- **JavaBean properties:** assigning to a property via a setter or corresponding access mechanism.
- **Nested properties:** modifying a property deep inside an object graph, if intermediate objects exist and are accessible.
- **Collection or array elements:** updating an element at a writable position if the accessor supports it.
- **Data exposed by the context:** modifying an object passed as the root object or exposed through a property.

For example, the expression **address.city = 'Hanoi'** can change city on the address object inside the root object. The expression **items[0] = 'Updated'** can replace the first element of a suitable collection. These operations depend on the accessor's write capability and the actual data types.

Do not infer that every expression can assign to every property. A property without a setter, a collection that does not support updates, or a read-only accessor can cause the assignment to fail during evaluation.

## Setters Can Introduce Additional Side Effects

Modifying a property does not necessarily mean just changing a value in a field. A JavaBean setter can execute additional logic:

~~~java
public void setStatus(String status) {
    validateTransition(this.status, status);
    this.status = status;
    this.updatedAt = Instant.now();
    publishStatusChangedEvent();
}
~~~

If SpEL assigns to the status property through this setter, all logic inside the setter can run. That can update timestamps, publish events, write logs, or perform other actions.

Therefore, assess the impact of the setter rather than looking only at the property name in the expression. A short assignment expression can trigger substantial business logic. If updating status requires permission checks, state-transition validation, or coordinating multiple actions, invoke a clearly named business method instead of letting an expression perform it indirectly.

## Repeated Evaluation Can Repeat Side Effects

An Expression can be parsed once and evaluated many times. If the expression only reads data, repeated evaluation generally does not mutate objects. However, if the expression contains an assignment, each evaluation can perform the update again.

Even when assigning the same value, a setter can still run again and produce side effects such as updating timestamps, publishing events, or writing audit entries. Thus, never assume an assignment expression is safe when invoked repeatedly.

A framework integration point may evaluate an expression in situations where the developer does not directly call getValue in a visible place. If an expression is used as a condition, key, or configuration evaluated repeatedly, having side effects makes behavior hard to predict and hard to test.

## Impact on Shared Objects and Concurrency

The root object may be referenced concurrently by multiple components in the application. If an evaluation mutates that object, other threads or requests can observe the new state.

For example, two requests share a configuration object or a shared business object. One expression modifies a property while another request is reading that property, creating results dependent on execution order. If multiple threads update concurrently, the application must also handle synchronization and data consistency.

SpEL does not automatically add locks, transactions, or synchronization to objects modified by expressions. Responsibility for state management remains with the application. Do not use assignment expressions on shared objects if lifecycle, write permissions, and concurrency rules are not clearly defined.

## Mutating an Object in Memory Is Not the Same as Persisting Data

SpEL assignment modifies the object accessed by the context. It does not automatically open a transaction, call a repository, or write data to a database.

However, if the object is an entity managed by a persistence context, in-memory changes can be detected by the persistence provider and written to the database when the transaction is flushed or committed according to framework rules. Thus, an assignment that looks like it exists only inside an expression can still indirectly affect persistent data.

If business data must be updated, perform it inside a service method with explicit transaction boundaries and validation rules. Using SpEL to express conditions or access data is generally easier to control than using it as an entity-update mechanism.

## Restricting Write Capability with EvaluationContext

EvaluationContext governs how an expression can access and interact with objects. For use cases that only need to read data, you can use **SimpleEvaluationContext.forReadOnlyDataBinding()**:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

This data-reading context is suitable for expressions that need to access properties without updating objects. If an expression attempts an unsupported write operation, evaluation fails instead of mutating the object via the standard data-binding write mechanism.

If the application needs to write properties, you can choose a read-write context or configure appropriate property accessors. Still, grant write permission only to expressions that genuinely need to update, and expose only the necessary properties.

A restricted context does not automatically guarantee that the entire object graph is harmless. If the root object contains references to services or objects with complex behavior, exposing them can still open up other effects depending on what the context allows. Provide small DTOs and allowlist-based accessors when evaluating external expressions.

## Checking Writability Before Updating

Expression provides the **isWritable(...)** method to check whether an expression can write to the location it points to in the current context and root object:

~~~java
Expression nameExpression =
        parser.parseExpression("name");

if (nameExpression.isWritable(context, user)) {
    nameExpression.setValue(context, user, "Alex");
}
~~~

This check is useful when the application needs to update properties based on a dynamic structure. However, isWritable only determines writability according to the accessor and context at the time of the check. It does not replace business validation, user authorization checks, valid-state checks, or guarantee that the operation will succeed under all subsequent conditions.

If a property is not writable, do not try to bypass the restriction by switching to a more privileged context without good reason. Determine why the property cannot be written and choose an appropriate update API.

## Separating Read Expressions and Write Operations

A clear way to organize code is to keep expressions used for reading separate from update operations:

~~~java
Expression statusExpression =
        parser.parseExpression("status");

String currentStatus =
        statusExpression.getValue(readOnlyContext, order, String.class);

// Business decision is made explicitly in Java
if ("PENDING".equals(currentStatus)) {
    statusExpression.setValue(writeContext, order, "APPROVED");
}
~~~

This example clarifies two steps: reading the current status and updating when business conditions are met. In a real application, the decision part may need to call a service method to verify permissions, validate the state transition, and coordinate other actions.

Separating reading and writing also makes mutation points easier to find in source code. When testing, you can verify that the read step does not mutate the object and that writes happen only under defined conditions.

## Cases Where Assignment in Expressions Should Be Avoided

Do not put assignments into expressions when an integration point is designed to read or compute a value, such as:

- Permission checks or feature-toggle conditions.
- Expressions generating cache keys.
- Expressions used solely for displaying data.
- Configurations evaluated repeatedly by the framework or across multiple contexts.
- Expressions obtained from users or untrusted configuration sources.
- Root objects shared across multiple requests or managed by a persistence context.

In these cases, an expression with side effects can alter the outcome of other steps, make bugs hard to reproduce, and cause unexpected data changes. Keep expressions read-only and move update operations into Java whenever possible.

## When Can Assignment in SpEL Be Appropriate?

The assignment operator can still be useful in clearly scoped situations, such as binding data into a temporary object, updating a DTO during a transformation step, or performing a controlled configuration operation.

When using it, ensure that:

- The root object has clear ownership and lifecycle.
- Allowed writable properties are clearly defined.
- Setters do not produce unexpected side effects.
- The expression is not evaluated repeatedly unintentionally.
- Evaluation errors are checked and handled.
- Critical business rules are still enforced in appropriate Java classes.

If expressions are configured outside source code, restrict root objects, variables, and property accessors. Do not supply an object with broad access to an uncontrolled expression string.

## Conclusion

SpEL supports assignment, so evaluating an expression can change object state. Effects can go through setters, nested properties, or collection elements; setters can also trigger events, update timestamps, or execute other logic. In-memory changes can also be persisted by a persistence context if the object is managed.

Use read-only contexts for expressions that only need to observe data, check writability when updating properties, and clearly separate read expressions from write operations. For business changes, prefer clearly named service methods so authorization, validation, and transactions are controlled in the right place.
