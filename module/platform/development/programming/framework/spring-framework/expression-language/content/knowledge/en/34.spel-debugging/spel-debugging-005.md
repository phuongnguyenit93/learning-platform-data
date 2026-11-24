# Checking runtime types before choosing an operator in SpEL

## 1. Why check runtime types?

Spring Expression Language (SpEL) evaluates expressions against real objects and values at runtime. A property declared as Object, a variable changed per request, or a method returning multiple data types can cause the same expression to receive different runtime types.

An operator only makes sense when operand types are compatible. For example:

- Adding two numeric values to compute a sum.
- Concatenating strings when building text content.
- Using and, or, and not with Boolean conditions.
- Using matches with a string and a regular expression.
- Using selection on a collection.
- Comparing an enum with a constant of the right enum type.
- Using a method that only exists on a specific type.

If you choose an operator based on type assumptions rather than actual runtime types, the expression can throw an evaluation error or return an unintended result. When debugging, determine the type of each operand first, and then decide on the appropriate operation.

## 2. Distinguishing declared types and runtime types

The declared type is the type written in a class or interface. The runtime type is the actual class of the object held at the time the expression is evaluated.

For example:

~~~java
public class Message {
    private Object value;

    public Message(Object value) {
        this.value = value;
    }

    public Object getValue() {
        return value;
    }
}
~~~

The value property has declared type Object, yet at runtime it can hold String, Integer, BigDecimal, or a business domain object:

~~~java
Message first = new Message("hello");
Message second = new Message(42);
Message third = new Message(new BigDecimal("12.50"));
~~~

The same expression can encounter different actual types depending on the object passed in. Do not infer that value is always a String just because an initial test fixture used String.

With a property of a concrete type like String or BigDecimal, the type contract is usually clearer. With Object, broad interfaces, or collections containing mixed element types, check the runtime type and define the valid cases.

## 3. Using instanceof to check types

SpEL supports the instanceof operator to check whether an object is compatible with a Java type:

~~~java
#value instanceof T(java.lang.String)
~~~

The type reference T(...) specifies the class to check against. For example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression isString =
        parser.parseExpression("#value instanceof T(java.lang.String)");

Expression isNumber =
        parser.parseExpression("#value instanceof T(java.lang.Number)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", "hello");

assertTrue(isString.getValue(context, Boolean.class));
assertFalse(isNumber.getValue(context, Boolean.class));

context.setVariable("value", Integer.valueOf(42));

assertFalse(isString.getValue(context, Boolean.class));
assertTrue(isNumber.getValue(context, Boolean.class));
~~~

instanceof checks type compatibility of the actual object. An Integer is a Number, so checking against Number also returns true.

This check does not convert the value. The string "42" remains a String; it does not become an Integer just because its content can be parsed as a number.

## 4. Checking interfaces or superclasses

instanceof can check interfaces and superclasses, not just concrete classes:

~~~java
#value instanceof T(java.lang.CharSequence)
#value instanceof T(java.lang.Number)
#value instanceof T(java.util.Collection)
#value instanceof T(java.util.Map)
~~~

Example checking whether a value is a collection:

~~~java
Expression expression = parser.parseExpression(
        "#value instanceof T(java.util.Collection)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", List.of("A", "B"));

Boolean isCollection = expression.getValue(context, Boolean.class);
assertTrue(isCollection);
~~~

Checking by interface is often more useful than checking a specific implementation. For example, if the expression only needs size() and iteration, checking Collection allows List, Set, and compatible implementations to all be accepted.

Only check the exact type needed for the next operation. If logic depends on order, additionally verify that the data has a List contract or an appropriately ordered collection.

## 5. Checking null before calling methods or reading properties

Null has no runtime class to inspect with getClass. The instanceof operator returns false when the left operand is null. You can use an explicit condition to clarify the handling branch:

~~~java
Expression expression = parser.parseExpression(
        "#value != null and #value instanceof T(java.lang.String)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", null);

Boolean result = expression.getValue(context, Boolean.class);
assertFalse(result);
~~~

If you need to call a method on a potentially null object, use null-safe navigation or a conditional expression:

~~~text
#value?.toString()
~~~

Or:

~~~text
#value != null ? #value.toString() : 'No value'
~~~

Null-safe navigation protects the operation immediately after the operator. With multi-level paths, check each intermediate object that may be null.

Do not treat null as another data type such as an empty String, the number 0, or Boolean false. Those states have distinct meanings and must be handled according to business requirements.

## 6. Choosing arithmetic operators when operands are numbers

Arithmetic operations such as +, -, *, /, and % require operands that can participate in numeric calculation. If data can be multiple numeric types, define the accepted type range before computing.

Example checking Number:

~~~java
Expression expression = parser.parseExpression(
        "#value instanceof T(java.lang.Number) "
        + "? #value + 10 "
        + ": null");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", Integer.valueOf(5));

Object result = expression.getValue(context);
assertEquals(15, result);
~~~

Number covers many numeric wrapper types and BigDecimal. However, operations across different numeric types can have different conversion rules and precision. For currency or data requiring decimal precision, prefer BigDecimal and control the types of both operands.

Do not use arithmetic operations directly on a String just because that string looks like a number. If input data is text, convert it explicitly to a numeric type at an appropriate boundary, check for parse errors, and only then perform calculations.

## 7. Distinguishing numeric addition from string concatenation

In SpEL, the + operator can be used for numeric addition or string concatenation depending on operand types. This makes it possible for an expression to behave differently if runtime types change.

For example:

~~~java
Expression expression = parser.parseExpression("#left + #right");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("left", 10);
context.setVariable("right", 5);

assertEquals(15, expression.getValue(context));

context.setVariable("left", "10");
context.setVariable("right", "5");

assertEquals("105", expression.getValue(context));
~~~

The same + symbol yields results depending on data types. If the goal is always numeric addition, normalize both values to numeric types before evaluating or check types before applying the operator.

If the goal is always building strings, convert components to String explicitly and use an expression with textual intent. Do not rely on a single + operator when input data can change types.

## 8. Choosing logical operators for Boolean

The operators and, or, and not combine or negate Boolean conditions. Do not assume SpEL treats every non-null value as true like some scripting languages do.

For example:

~~~java
Expression expression = parser.parseExpression(
        "#active and #approved");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("active", true);
context.setVariable("approved", false);

Boolean allowed = expression.getValue(context, Boolean.class);
assertFalse(allowed);
~~~

If variables can be null or non-Boolean, define a policy before combining conditions:

~~~text
#active == true and #approved == true
~~~

Explicit comparison with true clarifies the expected condition. If a variable is declared as Object, check the runtime type or convert at the input step instead of letting the expression depend on unclear coercion.

When conditions grow complex, split them into smaller expressions or named Java methods to make each branch easy to debug.

## 9. Using matches for strings

The matches operator checks whether a string matches a regular expression. Ensure the left operand is a String before using it:

~~~java
Expression expression = parser.parseExpression(
        "#value instanceof T(java.lang.String) "
        + "and #value matches '[A-Z]{3}-[0-9]{4}'");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", "INV-2026");

Boolean valid = expression.getValue(context, Boolean.class);
assertTrue(valid);
~~~

If value is Integer or null, the type check prevents the matches branch from being used. When needing to handle non-string data, decide whether to convert to String or reject the data.

A regular expression only validates text format. It does not prove the code exists, is valid in the database, or is permitted in business logic.

## 10. Choosing operators for collections and Maps

Before using selection or projection, determine whether the target is an appropriate collection:

~~~java
Expression expression = parser.parseExpression(
        "#items instanceof T(java.util.Collection) "
        + "? #items.?[active] "
        + ": null");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable(
        "items",
        List.of(new Item("A", true), new Item("B", false)));

List<?> activeItems = expression.getValue(context, List.class);
assertEquals(1, activeItems.size());
~~~

If the target is a Map, remember a Map has keys and values; index access uses keys, while selection iterates over entries per SpEL's collection semantics. Do not apply a predicate meant for a List onto a Map without clearly specifying whether you are inspecting the entry or the value.

Null-safe collection operators can help handle a null target collection in Spring Framework versions that support that syntax. They do not automatically guard against null elements inside the collection; the predicate still needs to check the element before reading properties.

## 11. Checking enums before comparing

An enum constant is a value belonging to a specific enum type. When an expression receives a variable that may be a String or an enum, check the type and compare against the constant of the right type:

~~~java
Expression expression = parser.parseExpression(
        "#status instanceof T(com.example.OrderStatus) "
        + "and #status == T(com.example.OrderStatus).PAID");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("status", OrderStatus.PAID);

Boolean paid = expression.getValue(context, Boolean.class);
~~~

If status is the String "PAID", instanceof against OrderStatus returns false. String and enum are two distinct types even when their display text looks identical.

If data arrives from a request as a String, convert it to an enum at the binding or service layer and handle invalid values. Do not compare an enum with a string assuming SpEL automatically turns the string into an enum.

## 12. Distinguishing type checking from type conversion

instanceof and conversion are two different operations:

| Purpose | How to perform | Result |
|---|---|---|
| Check if object is String | #value instanceof T(String) | Boolean, does not change object |
| Check if object is Number | #value instanceof T(Number) | Boolean, does not change object |
| Convert String to Integer | Use ConversionService or appropriate binding step | Produces Integer value if conversion succeeds |
| Request result type from SpEL | getValue(context, Integer.class) | May apply TypeConverter to result |
| Assign String to Integer property | Expression.setValue with appropriate TypeConverter | Converts before assigning if supported |

For example, the string "42" is not an Integer:

~~~java
context.setVariable("value", "42");

Boolean isInteger = parser.parseExpression(
        "#value instanceof T(java.lang.Integer)")
        .getValue(context, Boolean.class);

assertFalse(isInteger);
~~~

You can ask ConversionService to convert it:

~~~java
Integer converted = conversionService.convert("42", Integer.class);
assertEquals(Integer.valueOf(42), converted);
~~~

After conversion, the new object has type Integer. Clearly distinguish the original value from the converted value to avoid mis-debugging runtime types.

## 13. Pay attention when using getValue with a result type

The getValue(context, TargetType.class) overload can instruct SpEL to convert the result to the target type via TypeConverter. Therefore, the type of the variable receiving the result is not necessarily the original runtime type of the final node in the expression.

For example:

~~~java
Expression expression = parser.parseExpression("'42'");

Object raw = expression.getValue();
Integer converted = expression.getValue(Integer.class);

assertEquals("42", raw);
assertEquals(Integer.valueOf(42), converted);
~~~

If you are debugging the runtime type of an expression's result, first call getValue without passing a target type and inspect the returned object in Java:

~~~java
Object raw = expression.getValue(context);

String runtimeType =
        raw == null ? "null" : raw.getClass().getName();
~~~

Only then inspect the conversion to the type requested by application code. This helps separate errors inside the expression from conversion errors or behaviors at the getValue boundary.

## 14. Checking each operand before applying an operator

When a large expression fails, do not debug only the whole string. Parse and evaluate subparts to determine the type and value of each operand.

Example expression:

~~~text
#left + #right > #minimum
~~~

You can check each variable:

~~~java
Object left = context.lookupVariable("left");
Object right = context.lookupVariable("right");
Object minimum = context.lookupVariable("minimum");

System.out.println(left == null ? "null" : left.getClass().getName());
System.out.println(right == null ? "null" : right.getClass().getName());
System.out.println(minimum == null ? "null" : minimum.getClass().getName());
~~~

Then evaluate each operation:

~~~java
Object sum = parser.parseExpression("#left + #right")
        .getValue(context);

Boolean aboveMinimum = parser.parseExpression(
        "#left + #right > #minimum")
        .getValue(context, Boolean.class);
~~~

If sum already has the wrong type or fails, the issue lies in the addition or input data. If sum is right but the comparison fails, check the type of minimum and how the relational operator handles the two operands.

Do not log sensitive data just to inspect types. In production environments, only log type names, null status, and information permitted to be disclosed.

## 15. Checking the impact of ConversionService and TypeConverter

SpEL uses EvaluationContext's TypeConverter for operations requiring type conversion, such as assigning a value to a property or converting a result to a target type. A context can use StandardTypeConverter connected to the default ConversionService or a custom ConversionService.

When results differ from expectations:

- Check which context is being used.
- Check the context's TypeConverter.
- Check whether ConversionService has custom converters.
- Check actual source and target types.
- Test separately with and without the converter.

Do not assume every operator converts every input type in the same way. Just because a String can convert to Integer during property binding does not mean every operation on String will automatically take on numeric meaning.

If numeric calculation is needed, explicitly normalize data to a numeric type beforehand. If string comparison is needed, keep data as String and use corresponding text operations.

## 16. OperatorOverloader can change how operators behave

SpEL allows configuring an OperatorOverloader to define operator behavior for business domain types. StandardOperatorOverloader provides default behavior; a context can be configured with a custom overloader.

For example, an application has a Distance type and wants to use the addition operator for two distances:

~~~java
public class Distance {
    private final BigDecimal meters;

    public Distance(BigDecimal meters) {
        this.meters = meters;
    }

    public BigDecimal getMeters() {
        return meters;
    }
}
~~~

A custom OperatorOverloader can recognize a pair of Distance and Distance for the ADD operator and return a new Distance. This is an intentional extension; you should not assume SpEL understands addition by default for every custom class.

When debugging an expression using operators on domain objects, inspect EvaluationContext's OperatorOverloader. The same source can behave differently if the application attaches different overloaders.

Only overload operations that have natural and consistent meaning. If rules are complex or have side effects, named Java methods are usually easier to understand and test than custom operators.

## 17. Testing multiple runtime types with JUnit 5

Parameterized tests help confirm an expression properly handles the types that may appear:

~~~java
@ParameterizedTest
@MethodSource("values")
void identifiesRuntimeType(Object value, boolean expectedNumber) {
    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("value", value);

    Expression expression = new SpelExpressionParser()
            .parseExpression("#value instanceof T(java.lang.Number)");

    Boolean actual = expression.getValue(context, Boolean.class);

    assertEquals(expectedNumber, actual);
}

static Stream<Arguments> values() {
    return Stream.of(
            Arguments.of(Integer.valueOf(10), true),
            Arguments.of(new BigDecimal("10.50"), true),
            Arguments.of("10", false),
            Arguments.of(Boolean.TRUE, false),
            Arguments.of((Object) null, false));
}
~~~

This test checks runtime types without converting data. You can add separate tests for String, Collection, Map, enums, and the domain classes the expression actually receives.

If the expression performs operations, test both valid results and invalid input types. Do not test only a single happy path because production data may contain other types.

## 18. Testing operator branches with conditional expressions

The ternary operator can select an operation based on runtime type:

~~~java
Expression expression = parser.parseExpression(
        "#value instanceof T(java.lang.Number) "
        + "? #value + 10 "
        + ": (#value instanceof T(java.lang.String) "
        + "? #value.toUpperCase() : 'Unsupported')");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", Integer.valueOf(5));

assertEquals(15, expression.getValue(context));

context.setVariable("value", "hello");

assertEquals("HELLO", expression.getValue(context));

context.setVariable("value", Boolean.TRUE);

assertEquals("Unsupported", expression.getValue(context));
~~~

Each branch only performs an operation suitable for the checked type. This approach can be useful for short expressions and a few clearly supported types.

If there are many type branches, long logic, or many conversion rules, move the classification and processing into a clearly named Java method. An expression with too many branches is harder to read and harder to test than regular Java code.

## 19. Common mistakes

**Using numeric operations on Strings**

A string containing digits is still a String. Check the type or convert explicitly before performing arithmetic operations.

**Using matches on non-String values**

matches checks a regular expression on a string. Verify the input type before applying it.

**Confusing instanceof with conversion**

instanceof only checks type compatibility; it does not parse or convert objects.

**Ignoring null**

Null has no class for reading properties or calling methods. Check for null or use null-safe navigation appropriately.

**Assuming every Number has the same precision**

Integer, Double, and BigDecimal have different arithmetic characteristics. For currency, use BigDecimal and explicit scale/rounding rules.

**Using == instead of class checking**

Comparing values is not runtime type checking. Use instanceof when you need to confirm a type.

**Forgetting custom operators or converters**

EvaluationContext may contain custom OperatorOverloader and TypeConverter instances. Inspect the actual context when behavior differs from defaults.

**Testing only one data type**

An expression may pass with the first fixture yet fail with null, subclasses, or other types. Use test cases covering all types permitted by the contract.

**Looking only at getValue's target type**

getValue(context, TargetType.class) may convert the result. Use getValue(context) to observe the raw runtime type prior to conversion.

## 20. Debugging workflow before choosing an operator

When an expression encounters an error or returns an unexpected result, follow these steps in order:

1. Split the expression into operands and determine the runtime value of each part.
2. Check for null before reading properties or calling methods.
3. Use instanceof to confirm the actual class/interface that needs support.
4. Choose the operator matching the type: arithmetic for Number, matches for String, logical for Boolean, selection for collection, and right-typed constants for enum.
5. Check whether there is a custom conversion service or operator overloader.
6. Evaluate small parts and inspect raw result types.
7. Write tests for all valid runtime types and unsupported types.
8. If branching logic becomes long, move processing into a clearly named Java method.

The goal is for the expression to apply operators only when data satisfies defined type conditions. Checking types at the right boundary makes errors easier to find and prevents a value that merely looks like an expected type from being mishandled.

## 21. Takeaways

- Runtime types can differ from declared types, especially with Object properties, interfaces, and dynamic data.
- Use instanceof T(Type) to check actual classes or interfaces.
- instanceof does not convert values; String "42" remains a String.
- Check for null before accessing properties or calling methods on potentially null objects.
- Choose operators by type: arithmetic for Number, matches for String, logical for Boolean, selection for collection, and right-typed constants for enum.
- The + operator can add numbers or concatenate strings depending on operand types; do not rely on assumptions when input types vary.
- getValue(context) reveals the raw result; getValue(context, TargetType.class) may apply TypeConverter.
- Check TypeConverter, ConversionService, and OperatorOverloader if the context is customized.
- Test multiple runtime types, null, and unsupported types.
- Keep expressions short; move multi-type branching logic to Java when it is easier to read and maintain.
