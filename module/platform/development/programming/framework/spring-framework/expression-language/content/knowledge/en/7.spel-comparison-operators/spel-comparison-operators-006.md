# The instanceof Operator and Type Checking

In Java, a variable can be declared with a general type such as Object, a superclass, or an interface, while the actual object at runtime belongs to a concrete class. When rules need different handling depending on the object type, the application must check the actual type before selecting a processing branch.

SpEL provides the instanceof operator to check whether a value is an instance of a type. The result is a Boolean: true if the object belongs to the specified type or a compatible subtype; false if it does not match. This operator is useful when an expression receives polymorphic data, though it requires understanding how types are declared, how the context resolves types, and the limitations of runtime type checking.

## 1. Why Is Type Checking Needed?

Suppose a system receives multiple event types through the same interface:

    public interface DomainEvent {
    }

    public class OrderCreatedEvent implements DomainEvent {
        private final String orderId;

        public OrderCreatedEvent(String orderId) {
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public class PaymentFailedEvent implements DomainEvent {
        private final String paymentId;
        private final String reason;

        public PaymentFailedEvent(String paymentId, String reason) {
            this.paymentId = paymentId;
            this.reason = reason;
        }

        public String getPaymentId() {
            return paymentId;
        }

        public String getReason() {
            return reason;
        }
    }

A processing flow may receive a DomainEvent, yet need to apply separate rules for an order creation event and a payment failure event. The variable's declared type only tells us it is a DomainEvent; the runtime type tells us whether the concrete object is an OrderCreatedEvent or a PaymentFailedEvent.

In Java, the familiar check is:

    if (event instanceof OrderCreatedEvent) {
        // handle order created event
    }

SpEL has an operator with the same name to put a type-checking condition into an expression. This is useful when a rule is stored as an expression or when Spring configuration needs to select based on object type.

## 2. Syntax of instanceof in SpEL

The basic syntax takes the form:

    expression instanceof T(type-name)

The left side is an expression producing the object to check. The right side uses the T(...) operator to reference a Java type.

Example checking whether a value is a string:

    #value instanceof T(java.lang.String)

Some types in the java.lang package can be written more concisely:

    #value instanceof T(String)

For types in other packages, write the fully qualified name to avoid ambiguity:

    #event instanceof T(com.example.events.OrderCreatedEvent)

Do not put the type name in quotes. The following expression only compares against a string literal and is not a type check:

    #value instanceof 'java.lang.String'

Similarly, writing the class name directly without T(...) does not create a type reference:

    #value instanceof String

Use T(...) on the right side so SpEL can resolve the class name into a Class object.

## 3. How Is the Type Reference T(...) Resolved?

T(...) is SpEL's type reference operator. It asks the EvaluationContext to resolve the type name through a TypeLocator. With the default StandardEvaluationContext, Spring uses StandardTypeLocator; types in java.lang are pre-registered, whereas types in other packages usually require the fully qualified name.

Example:

    T(String)
    T(java.time.LocalDate)
    T(com.example.events.OrderCreatedEvent)

Type references do not only appear with instanceof. SpEL also uses them to access static members:

    T(java.lang.Math).max(10, 20)

The expression above calls the static max method of Math. This shows that T(...) opens up the ability to reference classes and class members, so a context with broad type lookup permissions must be managed carefully.

Not every context supports T(...). SimpleEvaluationContext is designed for a safer subset of SpEL and by default does not support type references, constructor references, or bean references. When an expression requires instanceof with T(...), the examples below use StandardEvaluationContext. If the application only needs ordinary property reading and does not need type references, SimpleEvaluationContext remains the appropriate restricted-privilege choice.

## 4. Example Evaluating instanceof in Java

Suppose the payload variable can hold multiple object types. The application creates a context, registers the variable, and evaluates the expression:

    Object payload = "payment received";

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("payload", payload);

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "#payload instanceof T(java.lang.String)");

    Boolean isText = expression.getValue(context, Boolean.class);

Here:

1. payload is the actual data placed into the context under the variable name payload.
2. #payload retrieves the value of that variable inside the expression.
3. T(java.lang.String) references the String class.
4. instanceof compares the object's runtime type against the target type.
5. getValue(..., Boolean.class) requests a Boolean result.

With the string value in the example above, the result is true. If payload is replaced with an Integer object, the result will be false. The expression only checks the type; it does not convert the object into the requested type.

## 5. Checking Superclasses and Interfaces

instanceof checks type assignability, not just whether the class name matches identically. If a class extends another class or implements an interface, an object of the subclass also satisfies the check against that superclass or interface.

Example:

    #event instanceof T(com.example.events.DomainEvent)

The expression above returns true for both OrderCreatedEvent and PaymentFailedEvent because both classes implement DomainEvent.

Checking a specific class:

    #event instanceof T(com.example.events.OrderCreatedEvent)

The expression is true only for OrderCreatedEvent and its subclasses. An unrelated PaymentFailedEvent will not satisfy the condition.

An interface can be checked to express a capability that the object supports:

    #handler instanceof T(com.example.spi.Retryable)

This is often more resilient when a rule cares about shared behavior or contract. If several different classes implement Retryable, a single expression checking the interface can apply to all of them without listing each concrete class.

Illustration table with the class hierarchy above:

| Runtime Object | instanceof DomainEvent | instanceof OrderCreatedEvent |
|---|---:|---:|
| OrderCreatedEvent | true | true |
| PaymentFailedEvent | true | false |
| A class not implementing DomainEvent | false | false |
| null | false | false |

## 6. Null Values and the Difference Between Type Checking and Null Checking

If the left side is null, instanceof returns false. This behavior matches Java's type check: null is not an instance of any class.

Example:

    #payload instanceof T(java.lang.String)

If payload is null, the result is false. However, that does not indicate whether the value is null or simply an object of another type.

If the business logic needs to distinguish the two cases, check for null separately:

    #payload == null

Or combine them in a single expression:

    #payload != null and
        #payload instanceof T(java.lang.String)

The and operator has a short-circuit mechanism: when the left side is already false, the right side does not need to be evaluated. Even so, for instanceof alone, a preceding null check is usually only necessary when the subsequent expression will access properties or call methods on the object.

Do not use instanceof as a complete data validation check. An object of the right type can still contain null properties, malformed values, or invalid business state. Those conditions must be checked separately.

## 7. Exact Class Check vs. Type Compatibility Check

Two intents must be distinguished:

- **Type compatibility check:** whether the object belongs to the specified type or a subtype. Use instanceof.
- **Exact class check:** whether the object's runtime class is strictly equal to the specified class.

Example with instanceof:

    #payload instanceof T(java.lang.Number)

The expression returns true for Integer, Long, Double, and other subclasses of Number.

If the business logic strictly requires accepting only Integer, the runtime class can be compared:

    #payload != null and
        #payload.getClass() == T(java.lang.Integer)

This comparison is true only when the runtime class is strictly Integer. A Long or Double value, although also a Number, will not satisfy the condition.

Do not use an exact-class check merely to write a stricter condition. In interface-oriented or inheritance-based designs, checking with instanceof is usually more appropriate because it accepts compatible implementations and subclasses. Only choose an exact-class check when the business rule genuinely depends on concrete class identity.

## 8. Type Checking Is Not Type Conversion

instanceof only answers the question "is the current object of this type?". It does not convert values, parse strings, or create a new object.

For example, a string containing digits:

    Object value = "42";

does not become an Integer just by checking:

    #value instanceof T(java.lang.Integer)

The result remains false, because the runtime object is still a String.

Spring has a TypeConverter mechanism to convert values in situations where SpEL or Spring features require type conversion, such as assigning a value to a property or matching method parameter types. That conversion mechanism is a separate step; do not infer that instanceof will automatically invoke TypeConverter.

If input data needs to be parsed, convert it explicitly in the Java layer or use a controlled conversion mechanism before checking and evaluating rules. This helps handle formatting errors and input limits in the right place.

## 9. Limitations with Generics and Collections

Java uses type erasure for generics. At runtime, an ArrayList<String> and an ArrayList<Integer> both have the runtime class ArrayList. Therefore, SpEL can check whether an object is a List:

    #items instanceof T(java.util.List)

However, instanceof cannot be used to directly distinguish List<String> from List<Integer>:

    #items instanceof T(java.util.List<java.lang.String>)

This is not a valid type reference for checking generic type arguments like compile-time types. Generic type parameter information is no longer fully retained in the collection's runtime class.

If you need to verify that every element is a string, inspect the collection contents. Selection can be used to find elements that are not String:

    #items.?[!(#this instanceof T(java.lang.String))]

The result is a list of elements failing the type condition. If the resulting list is empty, every checked element is a String. In real applications, inspecting collections in Java is often easier to read and provides clearer error reporting when handling large datasets or multiple nesting levels.

## 10. Combining instanceof with the Conditional Operator

When a branch needs to be selected by object type, instanceof can be combined with the ternary operator:

    #event instanceof T(com.example.events.OrderCreatedEvent)
        ? 'ORDER_CREATED'
        : 'OTHER_EVENT'

If you need to access a property present only on a specific class, place the property access in the true branch:

    #event instanceof T(com.example.events.PaymentFailedEvent)
        ? #event.reason
        : 'No payment failure'

The conditional ensures only the matching branch is evaluated. However, an expression with many branches and many concrete classes quickly becomes hard to maintain. If each event type has its own workflow, consider using polymorphism, a handler registry, or dispatch in Java instead of packing all logic into one SpEL string.

instanceof is well suited to expressing a concise type condition. It does not replace Java's polymorphic design.

## 11. Controlling Access Privileges When Evaluating Expressions

StandardEvaluationContext supports many SpEL features, including type references, method invocation, property access, and bean references when configured. These capabilities are useful for applications, but also create a security boundary.

Do not take an arbitrary expression string from external users and evaluate it directly with a broadly privileged StandardEvaluationContext. An expression does not just check instanceof; it can use T(...) to reference other classes or invoke static methods, depending on the privileges the context allows.

Some principles to apply:

- Only evaluate rules provided by the application or trusted administrative sources.
- Only expose the necessary variables and input objects in the context.
- When rules only need a few specific types, configure TypeLocator with an allowlist instead of allowing resolution of every class on the classpath.
- Restrict method resolvers, property accessors, and bean resolvers strictly to what is needed.
- Validate rule syntax and result types before placing them into critical processing flows.
- Log rule identifiers and evaluation errors for traceability; avoid logging entire sensitive data payloads.

If type references or advanced features are not needed, prefer SimpleEvaluationContext with a minimal feature set. If instanceof with T(...) is strictly required, choose StandardEvaluationContext and proactively restrict access privileges suited to the expression source.

## 12. Testing Expressions Against Type Cases

A type-checking rule should be tested with representative cases, not just one matching object.

| Input Data | Expected Result for String Check |
|---|---|
| Ordinary string | true |
| Another class such as Integer | false |
| A subclass of the target type (if inheritance is allowed) | true |
| null | false |
| Collection containing heterogeneous elements | List check is true; elements must be checked individually |

When testing, verify all three parts: whether the expression string parses, whether the context resolves the type, and whether the runtime result matches the input data. If an error occurs at the parse or type lookup step, it is a configuration/expression error. If the expression runs but returns false, that may simply be the valid result for the current data.

## Conclusion

SpEL's instanceof operator checks the runtime type of a value by comparing it against a type reference created via T(...). It supports checking concrete classes, superclasses, and interfaces; returns false for null; and does not perform type conversion or check type-erased generic parameters.

To use it properly, choose a context supporting type references, understand the difference between compatibility checks and exact class checks, and restrict expression privileges. When a rule only needs to select by object type, instanceof is a concise and clear tool. When logic starts branching across many classes or performing multiple actions, move the dispatching to Java and keep SpEL in the role of expressing small conditions.