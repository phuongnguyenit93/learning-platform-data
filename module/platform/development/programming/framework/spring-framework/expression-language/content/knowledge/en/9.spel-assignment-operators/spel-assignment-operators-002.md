# Assignment Operator and Side Effects on the Target Object in Spring Expression Language

Spring Expression Language (SpEL) does not only read data and compute values. It can also write values to an object's property when the target expression is writable. This capability is performed using the assignment operator \`=\` or the \`Expression.setValue(...)\` API.

When an assignment is evaluated, the state of the target object can change. That change persists after the evaluation and can be observed by other parts of the application holding the same reference to the object.

To use this feature properly, you must distinguish assignment from comparison, understand which target expressions are writable, and know when an evaluation call can produce side effects.

## 1. The Assignment Operator in SpEL

SpEL uses a single equals sign \`=\` to assign a value to a writable target expression.

Example:

~~~spel
status = 'PAID'
~~~

This expression asks to set the value \`PAID\` on the \`status\` property of the current object, if that property is writable.

You must distinguish between the two operators:

| Syntax | Meaning | Example |
|---|---|---|
| \`=\` | Assign a value to a target | \`status = 'PAID'\` |
| \`==\` | Compare whether two values are equal | \`status == 'PAID'\` |

Comparison only checks a condition and produces a Boolean value. Assignment changes the state of the target. Confusing these two syntaxes can cause an expression to modify an object unintentionally.

## 2. Assigning Properties with Expression.setValue

An explicit way to write a value is to parse an expression pointing to the property, then call \`setValue\`.

Suppose we have an Order class:

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

The application can change the status as follows:

~~~java
Order order = new Order("PENDING");

ExpressionParser parser = new SpelExpressionParser();
Expression statusExpression = parser.parseExpression("status");

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

// Write a value to the status property of order.
statusExpression.setValue(context, "PAID");

System.out.println(order.getStatus());
~~~

Output:

~~~text
PAID
~~~

In this example:

1. \`order\` is set as the root object of the context.
2. The expression \`status\` identifies the property to write on the root object.
3. \`setValue(context, "PAID")\` instructs SpEL to write the new value.
4. When reading \`order.getStatus()\` again, the application sees the updated status.

\`setValue\` is the dedicated API for assigning a value to an Expression's target. This approach makes the intent to write data explicit in Java code.

## 3. Assigning Directly Using the = Operator in an Expression

SpEL also allows placing the assignment directly inside the expression string. When an assignment expression is evaluated with \`getValue\`, the write operation is performed.

~~~java
Order order = new Order("PENDING");

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

ExpressionParser parser = new SpelExpressionParser();

Expression assignment =
    parser.parseExpression("status = 'PAID'");

// Evaluating this expression performs the assignment.
assignment.getValue(context);

System.out.println(order.getStatus());
~~~

Output:

~~~text
PAID
~~~

This is an important point: a call named \`getValue\` is normally used to retrieve a value, yet if the expression contains an assignment, evaluation can also modify the target object.

Therefore, when reading SpEL code, you cannot conclude that an evaluation is read-only solely from the Java method name. You must inspect the expression content as well.

## 4. What Is the Target Object?

The target object is the object or location that the assignment acts upon. It is usually identified through the root object or a property path.

### 4.1. Assigning a Property on the Root Object

If the context is created with an Order:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);
~~~

then the expression:

~~~spel
status = 'PAID'
~~~

targets the \`status\` property of \`order\`.

A simple property name can be used because the root object is the current object.

### 4.2. Assigning a Nested Property

Suppose Order has a Customer, and Customer has a name property. When intermediate objects exist and the path is writable, an expression can target a nested property:

~~~spel
customer.name = 'Linh'
~~~

If the root object is Order, SpEL follows the path:

~~~text
Order
  |
  +-- customer
        |
        +-- name  <-- assigned value
~~~

The assignment acts on the \`name\` property of the Customer object referenced by Order. It does not replace the entire Order.

If \`customer\` is null, the \`name\` property cannot be accessed in the normal way. The application must ensure the intermediate object exists or use an appropriate initialization mechanism configured for SpEL.

### 4.3. Assigning a Collection or Map Element

An indexer can also specify a target location if the data type and accessor support writing:

~~~spel
items[0] = 'updated'
settings['theme'] = 'dark'
~~~

The first example writes to the first element of a mutable collection. The second example writes a value for the \`theme\` key of a mutable map.

Writability depends on the collection type, a valid index or key, and the configured access mechanism. An immutable collection or an invalid position can cause the assignment to fail.

## 5. When Is an Expression Writable?

Not every Expression is a valid write target. The expression must point to a property or location that SpEL can update.

Common requirements include:

- The property path must resolve successfully.
- Intermediate objects along the path must exist when accessed.
- The PropertyAccessor or corresponding access mechanism must support write operations.
- The property must have a setter or a write mechanism supported by the accessor.
- The new value must be compatible with the target type or convertible by the TypeConverter.
- A collection or map must allow updates if the assignment targets one of its elements.

For example, if the Order class only has a getter for \`status\` and no write mechanism supported by an accessor, assignment may fail.

Some ways of creating a context intentionally restrict write permissions. \`SimpleEvaluationContext.forReadOnlyDataBinding()\` is suited for read-only cases; \`SimpleEvaluationContext.forReadWriteDataBinding()\` supports read-and-write data binding. The choice of context affects which operations an expression can perform.

## 6. Side Effects on the Target Object

A side effect is a state change outside the value returned by an expression. With SpEL assignment, the most important side effect is that the target object is modified.

Example:

~~~java
Order order = new Order("PENDING");

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

parser.parseExpression("status = 'PAID'").getValue(context);

// Read the object again after evaluation.
String currentStatus = order.getStatus();
~~~

After the assignment, \`currentStatus\` is \`PAID\`.

This happens because the context holds a reference to the \`order\` object itself. SpEL writes into that object; it does not automatically create a copy of Order and return the modified copy.

### 6.1. Changes Are Visible Through Other References

Suppose two Java variables point to the same object:

~~~java
Order firstReference = order;
Order secondReference = order;
~~~

After SpEL changes \`status\` through a context containing \`firstReference\`, reading \`secondReference.getStatus()\` also sees the new value. Both variables reference the same object in memory.

As a result, an assignment in SpEL can affect logic that runs later, even in another component holding a reference to the same object.

### 6.2. A Setter Can Perform Additional Logic

When an accessor writes a property via a setter, the application's setter may perform other actions besides storing the value:

~~~java
public void setStatus(String status) {
    validateStatus(status);
    this.status = status;
    this.updatedAt = Instant.now();
}
~~~

If SpEL invokes a write mechanism that uses this setter, changes such as updating \`updatedAt\` or validating the status can also occur. The side effects then come from both the assignment operation and the logic executed inside the setter.

You should not assume that a property assignment always modifies only a single data field.

## 7. Assigning a Nested Property: Which Object Is Affected?

Consider the structure:

~~~text
Order
  |
  +-- customer ------> Customer
                         |
                         +-- name
~~~

With the expression:

~~~spel
customer.name = 'Linh'
~~~

SpEL uses Order as the root object, reads the customer property to obtain the reference to Customer, and then writes the value to Customer's name.

After evaluation:

- The customer reference inside Order still points to that Customer object.
- The name property of Customer holds the new value.
- Other places referencing the same Customer also see the change.

Clearly distinguishing the root object from the target object helps avoid the misconception that a nested property assignment replaces the entire root object.

## 8. Type Conversion During Assignment

The data type of the assigned value must be compatible with the target property type. EvaluationContext has a TypeConverter to support allowed conversions.

For example, if the target property is a numeric type and the supplied value is a string representing a number, conversion can succeed depending on the converter and configuration:

~~~java
Expression priceExpression =
    parser.parseExpression("price");

priceExpression.setValue(context, "125000");
~~~

If the target type is BigDecimal and the converter supports converting from String to BigDecimal, the property can receive the corresponding value.

However, not every string can be converted to every type. An invalid value or the lack of an appropriate converter can cause the write operation to fail.

To avoid runtime errors, provide values of the correct type whenever possible and do not rely on implicit conversion when data rules need to be explicit.

## 9. Distinguishing setValue and the Assignment Operator in getValue

Both approaches can modify the target object, but their intended usage differs:

| Style | Purpose | Example |
|---|---|---|
| \`Expression.setValue(context, value)\` | Write a value to a target expression | \`parseExpression("status").setValue(context, "PAID")\` |
| \`getValue(context)\` with an assignment expression | Evaluate an expression containing an assignment | \`parseExpression("status = 'PAID'").getValue(context)\` |
| \`getValue(context)\` with a read expression | Read or compute a value | \`parseExpression("status == 'PAID'").getValue(context)\` |

When Java code updates data explicitly, \`setValue\` usually makes the intent clearer. When an expression needs to contain assignment logic as part of its syntax, the \`=\` operator can be used.

Note that \`getValue\` does not guarantee a read-only expression. If the expression content contains an assignment or a method call with side effects, the object and application state can still change.

## 10. Complete Example: Updating an Object and Reading Back the Result

Suppose we have an Order class:

~~~java
public class Order {
    private String status;
    private BigDecimal total;

    public Order(String status, BigDecimal total) {
        this.status = status;
        this.total = total;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

The application wants to update the status and then check the new value:

~~~java
Order order = new Order(
    "PENDING",
    new BigDecimal("750000")
);

ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

// Target expression pointing to the status property.
Expression statusExpression =
    parser.parseExpression("status");

// Write the new value to the target object.
statusExpression.setValue(context, "PAID");

// Evaluate the read expression after updating.
Expression checkExpression =
    parser.parseExpression("status == 'PAID'");

Boolean paid =
    checkExpression.getValue(context, Boolean.class);

System.out.println(order.getStatus());
System.out.println(paid);
~~~

Output:

~~~text
PAID
true
~~~

Processing flow:

1. Order is created with the status PENDING.
2. StandardEvaluationContext holds Order as the root object.
3. statusExpression identifies the property to write.
4. setValue writes PAID into the object.
5. checkExpression reads the current status and compares it with PAID.
6. The Boolean result is true.

The example demonstrates that changes made by SpEL persist when evaluating another expression on the same context and object.

## 11. Controlling Side Effects and Choosing an Appropriate Context

SpEL's write capability is useful for data binding, configuration, and controlled update rules. However, if expressions come from untrusted sources, allowing arbitrary writes can alter business data unexpectedly.

Some practical guidelines:

- Use a read-only context if the expression only needs to query data.
- Enable write capability only when the application genuinely needs to update properties.
- Restrict the root object and the properties that the expression can access.
- Consider custom PropertyAccessor, MethodResolver, and BeanResolver implementations.
- Avoid letting untrusted expressions call methods with side effects or access sensitive beans.
- Validate input values and target types before writing data.

SimpleEvaluationContext provides restricted data-binding modes, including read-only and read-write modes. StandardEvaluationContext has broader configurability and must be set up appropriately for the intended scope.

## 12. Common Misconceptions

**Misconception 1: Assignment only produces a new value without changing the object.**  
Assigning to a property can update the very object referenced in the context.

**Misconception 2: The root object is always the object being replaced.**  
When assigning customer.name, SpEL writes to the name property of the Customer referenced by the root object. The root object is not automatically replaced.

**Misconception 3: getValue is always a read-only operation.**  
An expression with an assignment operator or a method call causing side effects can still mutate state while getValue runs.

**Misconception 4: Every property is writable.**  
The target must support writing through an accessor, and the object must satisfy the necessary conditions. A read-only context or an object without an appropriate write mechanism can reject the operation.

**Misconception 5: Type conversion always succeeds.**  
TypeConverter only converts supported cases. Incompatible values can cause errors.

**Misconception 6: null always indicates failure.**  
null can be a valid return value. Distinguish it from exceptions during parsing or evaluation.

## 13. Key Takeaways

- Basic components such as literals, properties, variables, and method calls can supply values to larger expressions.
- Expressions are evaluated in an EvaluationContext with a root object, variables, and appropriate access mechanisms.
- Return values can be Number, String, Boolean, objects, collections, maps, or null.
- \`Expression.setValue(...)\` writes a value to a writable target.
- The assignment operator \`=\` can also produce side effects when an expression containing an assignment is evaluated with \`getValue(...)\`.
- Property changes can be observed through all references to the same object.
- Setters and custom accessors can perform additional logic when writing.
- Choose an appropriate context to control an expression's ability to read, write, and invoke methods.

When using SpEL to update data, clearly identify the target object, property path, write mechanism, and value type. Then inspect the object state after evaluation to understand the full side effects of the expression.
