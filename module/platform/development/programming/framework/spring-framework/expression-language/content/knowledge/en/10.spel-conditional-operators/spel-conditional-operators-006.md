# Distinguishing Default Values from Error Handling

In Spring Expression Language (SpEL), an expression may receive null data, lack information, or encounter errors during evaluation. A common approach is to provide a default value so the expression still produces a result. However, **default values and error handling are two different things**.

Default values are used when data is structurally valid but has no value yet or is in a state agreed upon as replaceable. Error handling is used when an operation cannot be performed properly, such as invalid expression syntax, a nonexistent property, a failed type conversion, or a method throwing an exception.

SpEL provides the Elvis operator, conditional operator, and safe navigation to handle certain cases of missing data. These operators do not replace the application's exception catching and handling mechanisms.

## 1. Distinguishing the Two Goals

Suppose the application needs to get the customer's name for display. If the name has not been provided, a default value like Guest can be used. This is a fallback case:

~~~java
customerName ?: 'Guest'
~~~

However, if the expression references a nonexistent property or invokes a failing method, providing Guest does not automatically catch that error.

They can be distinguished as follows:

| Situation | Goal | Appropriate handling |
|---|---|---|
| Value is null | Provide a replacement value | Elvis or conditional operator |
| Empty string | Use replacement content per rules | Elvis or explicit string check |
| Whitespace-only string | Normalize or use default | Check isBlank/trim |
| Boolean is false | Preserve false if it is a valid value | Do not treat false as null |
| Property does not exist | Fix property name or model/accessor | Inspect evaluation error |
| Expression has syntax error | Fix expression | Catch ParseException |
| Method throws exception | Handle business or technical error | Catch exception at the Java layer |
| Type conversion fails | Add converter or fix data type | Handle conversion error |

Do not use a default value to mask all errors. If a property name is misspelled, returning Guest may let the application keep running with incorrect data without anyone noticing the cause.

## 2. The Elvis Operator (?:)

### 2.1. Syntax

The Elvis operator is a shorthand way to provide a replacement value when the left-hand side does not have a suitable value:

~~~java
customerName ?: 'Guest'
~~~

If customerName has an acceptable value, SpEL returns that value. If the value falls under the fallback case, SpEL returns Guest.

Example with a variable in EvaluationContext:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customerName", null);

String name = parser
        .parseExpression("#customerName ?: 'Guest'")
        .getValue(context, String.class);
~~~

The result is Guest.

SpEL variables are referenced with the # sign. The variable value is supplied from Java before evaluating the expression.

### 2.2. Elvis with Null and Empty Strings

Elvis is commonly used to provide a default when a value is null. Since Spring Framework 4.3, the Elvis operator also uses the default branch when the left-hand side is an empty string.

Example:

~~~java
#name ?: 'Unknown'
~~~

Cases:

| Value of name | Result |
|---|---|
| null | Unknown |
| Empty string | Unknown |
| An | An |
| An Nguyen | An Nguyen |
| Whitespace-only string | Whitespace string is preserved |

A whitespace-only string is not the same as an empty string. If business logic wants to treat whitespace-only strings as having no content as well, check explicitly:

~~~java
#name == null || #name.trim().isEmpty()
    ? 'Unknown'
    : #name
~~~

In the example above, the OR operator short-circuits. When name is null, the trim side is not evaluated.

If the application uses Java 11 or later, you can call isBlank() to check for empty or whitespace-only strings:

~~~java
#name == null || #name.isBlank()
    ? 'Unknown'
    : #name
~~~

Choose the rule suited to the application's Java and Spring versions.

### 2.3. Elvis Does Not Replace Every Falsy Value

Elvis does not mean "if the left-hand side is not true, use the default". A Boolean value false is still a real value and is not null.

Example:

~~~java
#enabled ?: true
~~~

If enabled is false, the result remains false. This behavior is necessary when false has its own business meaning.

If you want to turn null into true while still preserving false, Elvis is the right choice. If you want both false and null to become true, write a condition following that exact rule:

~~~java
#enabled == null || !#enabled ? true : #enabled
~~~

However, avoid long expressions if the state can be named at the Java layer.

Elvis also does not automatically treat an empty list, empty map, the number 0, or a collection with no elements as null. If a fallback is needed for those cases, check an explicit condition such as isEmpty() or compare with 0.

### 2.4. Using Elvis for Properties

When a property can be null, a default value can be provided:

~~~java
order.note ?: 'No note'
~~~

Or combined with the root object:

~~~java
customer.displayName ?: customer.username
~~~

The second expression uses username when displayName falls into the fallback case. However, if customer can be null, customer needs to be handled first:

~~~java
customer?.displayName ?: 'Guest'
~~~

Safe navigation and Elvis solve two consecutive problems: safe navigation avoids accessing a property on a null receiver; Elvis selects a replacement value when the result is null or an empty string according to the Spring version's semantics.

## 3. The Ternary Conditional Operator

### 3.1. Syntax

The conditional operator has the form:

~~~java
condition ? valueIfTrue : valueIfFalse
~~~

SpEL evaluates condition first. If condition is true, the expression returns valueIfTrue; if false, it returns valueIfFalse.

Example:

~~~java
order.total >= 100 ? 'VIP' : 'STANDARD'
~~~

It can be evaluated:

~~~java
String category = parser
        .parseExpression(
                "order.total >= 100 ? 'VIP' : 'STANDARD'"
        )
        .getValue(context, String.class);
~~~

Ternary is suitable when choosing between two outcomes based on a business condition.

### 3.2. Using Ternary to Provide a Default

A fallback can be written with ternary:

~~~java
#name != null ? #name : 'Guest'
~~~

This approach only replaces null, while an empty string is preserved. This differs from Elvis in Spring versions that support fallback for empty strings.

Compare:

~~~java
#name ?: 'Guest'
~~~

and:

~~~java
#name != null ? #name : 'Guest'
~~~

The two expressions can produce different results when name is an empty string. Choose the syntax based on the business definition of "having no value".

### 3.3. Checking Multiple Cases

Ternary can be used for classification:

~~~java
order.total > 1000
    ? 'LARGE'
    : (order.total > 0 ? 'NORMAL' : 'EMPTY')
~~~

The expression above has three outcomes:

- LARGE if the total amount is greater than 1000.
- NORMAL if the total amount is greater than 0 but does not exceed 1000.
- EMPTY in the remaining cases.

Nested ternaries can become hard to read. If there are many branches, consider a Java method or a decision structure at the business layer.

### 3.4. Ternary Evaluates Only the Selected Branch

After condition is evaluated, SpEL evaluates only the corresponding result branch. The other branch is not executed.

This is useful when the selected branch depends on data that may be null:

~~~java
order.customer != null
    ? order.customer.name
    : 'Guest'
~~~

When customer is null, the branch accessing name is not evaluated.

Do not put actions with side effects into a ternary branch. Keep branches as value-returning expressions so results are easy to test and predict.

## 4. Safe Navigation (?.) Combined with Default Values

### 4.1. Safe Navigation Handles a Null Receiver

The safe navigation operator helps access a property or call a method without raising an error just because the receiver is null:

~~~java
order.customer?.name
~~~

If customer is null, the expression returns null instead of continuing to access name on a null value.

It can be combined with Elvis:

~~~java
order.customer?.name ?: 'Guest'
~~~

Processing flow:

1. Access customer of order.
2. If customer is null, safe navigation returns null.
3. If customer exists, read name.
4. If the result falls under the fallback case, Elvis returns Guest.

With multiple nullable levels, place safe navigation at points that can be null:

~~~java
order.customer?.profile?.displayName ?: 'Guest'
~~~

### 4.2. Safe Navigation Does Not Catch Every Exception

Safe navigation only guards access through a null receiver at the operator's position. It does not handle all kinds of errors.

For example, the following errors can still occur:

- Property does not exist.
- Method does not exist or is inaccessible.
- Invoked method throws an exception.
- Type conversion fails.
- Invalid operator or operation.
- Expression has invalid syntax.

Therefore, the expression:

~~~java
order.customer?.unknownProperty ?: 'Guest'
~~~

should not be viewed as a way to catch misspelled property errors. Safe navigation does not turn a nonexistent property into null. Elvis can only process a result that the left-hand part evaluated successfully.

### 4.3. Distinguishing a Null Receiver from a Business Error

Suppose the application has a customer, but the customer is locked. Safe navigation does not mean a locked customer will be replaced with Guest. Those are two different states:

- No customer: missing data, fallback may be used if business rules allow.
- Customer exists but is locked: business state that needs to be handled separately.

For example:

~~~java
order.customer?.name ?: 'Guest'
~~~

only creates a fallback display name. It does not decide whether the customer is allowed to place an order.

## 5. Default Values Are Not Error Handling

### 5.1. Parse Errors

A parse error occurs when a string does not follow SpEL syntax:

~~~java
order.total >= ? 'VIP' : 'STANDARD'
~~~

The parser cannot create a valid Expression. Elvis or ternary cannot catch this error because the expression has not been parsed successfully.

You need to catch ParseException at the parse step:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
} catch (ParseException ex) {
    // Report invalid expression syntax.
    throw new IllegalArgumentException(
            "Invalid SpEL syntax at position " + ex.getPosition(),
            ex
    );
}
~~~

### 5.2. Evaluation Errors

An expression can be syntactically valid yet fail during evaluation:

~~~java
order.unknownProperty ?: 'Guest'
~~~

If unknownProperty does not exist, SpEL may throw a property access error. Elvis does not automatically catch that error to return Guest.

You need to check the model, property accessor, and context configuration. If the error is caused by data or business rules, handle it according to the corresponding policy.

### 5.3. Method Throws an Exception

Example:

~~~java
order.calculateTax() ?: 0
~~~

Elvis can use 0 if the method evaluates successfully and returns null or an empty string in the applicable case. But if calculateTax() throws an exception, the right-hand side is not an exception-catching mechanism. The error still propagates outward.

If you need to handle exceptions, catch them at the Java layer:

~~~java
try {
    BigDecimal tax = parser
            .parseExpression("order.calculateTax()")
            .getValue(context, BigDecimal.class);
} catch (EvaluationException ex) {
    // Log and handle the evaluation error according to application policy.
}
~~~

Do not replace every tax calculation error with 0 if doing so could cause invoices or financial reports to be wrong. Default values must be permitted by business rules.

## 6. Choosing the Handling Approach by Situation

| Situation | Syntax or mechanism | Meaning |
|---|---|---|
| Null needs fallback | **value ?: default** | Return default when no value is present |
| Null or empty string needs fallback | **value ?: default** in Spring 4.3+ | Empty string also uses the default branch |
| Only null needs fallback, empty string preserved | **value != null ? value : default** | Distinguish null and empty |
| Whitespace string needs fallback | Check **isBlank()** or **trim().isEmpty()** | Apply separate blank rule |
| Choose one of two results | **condition ? a : b** | True/false condition |
| Receiver may be null | **object?.property** | Avoid property access on null |
| Property does not exist | Check model/accessor | Fix access error |
| Method throws exception | try/catch in Java | Handle evaluation error |
| Expression has syntax error | Catch ParseException | Handle parse error |

## 7. Do Not Hide Errors with Overly Broad Fallbacks

An expression such as:

~~~java
order.customer?.name ?: 'Guest'
~~~

may be suitable for a screen displaying a name. But it should not be used as the basis for verifying customer identity or deciding access permissions.

If customer is null due to unexpectedly missing data, defaulting to Guest can make the system proceed with an incorrect object. Clearly distinguish:

- **Display fallback:** use replacement text so the UI is not blank.
- **Business fallback:** replace a value when rules explicitly define that case.
- **Validation:** confirm required data exists and is valid.
- **Error handling:** log, translate, or handle exceptions according to application policy.

For example, a display name can have a fallback:

~~~java
order.customer?.displayName ?: 'Customer'
~~~

But a required customerId should be checked separately:

~~~java
order.customer != null && order.customer.id != null
~~~

Do not use a placeholder value to substitute for a required identifier and then continue business processing as if the data were valid.

## 8. Designing Default Values at the Java Layer

If the same fallback rule is used in multiple places, consider naming it in Java instead of repeating the expression:

~~~java
public String displayNameOrGuest(Customer customer) {
    if (customer == null) {
        return "Guest";
    }

    String displayName = customer.getDisplayName();

    if (displayName == null || displayName.isBlank()) {
        return "Guest";
    }

    return displayName;
}
~~~

Then SpEL can call the appropriate method if the EvaluationContext allows it:

~~~java
#displayPolicy.displayNameOrGuest(order.customer)
~~~

This approach helps:

- Centralize null and blank handling rules.
- Make unit testing easier in isolation.
- Make changing the default value easier.
- Avoid repeating the same expression in multiple places.
- Separate business decisions from SpEL strings.

For important rules, prefer a clearly named method or service and control method access permissions in the context.

## 9. Testing Fallbacks and Error Handling

Each type of situation should be tested separately. Example with Elvis:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("name", null);

assertEquals(
        "Guest",
        parser.parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class)
);
~~~

Checking empty string:

~~~java
context.setVariable("name", "");

assertEquals(
        "Guest",
        parser.parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class)
);
~~~

Checking false is not replaced:

~~~java
context.setVariable("enabled", false);

assertEquals(
        Boolean.FALSE,
        parser.parseExpression("#enabled ?: true")
                .getValue(context, Boolean.class)
);
~~~

Checking ternary:

~~~java
context.setVariable("score", 80);

assertEquals(
        "PASS",
        parser.parseExpression("#score >= 50 ? 'PASS' : 'FAIL'")
                .getValue(context, String.class)
);
~~~

And checking parse errors independently:

~~~java
assertThrows(
        ParseException.class,
        () -> parser.parseExpression("10 > ?")
);
~~~

For evaluation errors, create a root object or context with the corresponding property/method to test the actual exception. Do not combine parse, fallback, and evaluation tests into a single case because they verify different behaviors.

## 10. Summary

Default values help expressions produce a result when data falls into an anticipated missing-value case. Error handling resolves operations that cannot be executed properly.

- Use **Elvis (?:)** for fallbacks, clearly understanding how null and empty strings are handled.
- Use **ternary (? :)** when you need to choose between two outcomes based on a condition.
- Use **safe navigation (?.)** to guard access through a null receiver.
- Use **ParseException** and **EvaluationException** to handle errors at the right stage.
- Do not use fallbacks to hide misspelled properties, failing methods, conversion errors, or missing required data.
- Place shared fallback rules in Java when they carry business meaning and need to be tested independently.

A good expression should make clear which cases are replaced with a default value and which cases need to report an error. When that boundary is defined, SpEL becomes easier to read and the application avoids silently continuing with invalid data.