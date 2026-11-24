# Nullable Boolean Expressions in SpEL

## Objectives

In Java, a property of type `Boolean` can take three states: `true`, `false`, or `null`. `null` usually means unset, unknown, or no data. When using these values in Spring Expression Language (SpEL), it is necessary to distinguish between reading a Boolean value directly, comparing it with `true`/`false`, and passing it into logical operators.

Key point: SpEL does not automatically treat `null` as `false` in the `and`, `or`, or `not` operators. Logical operators require a non-null Boolean value; if an operand evaluates to `null`, SpEL throws `SpelEvaluationException` because it cannot convert `null` to `boolean`. Check for null or choose a default value explicitly.

## 1. Boolean and Nullable Boolean

Java has two common types:

| Type | Nullable? | Meaning |
| --- | --- | --- |
| `boolean` | No | Only `true` or `false`; the default value of a field is `false`. |
| `Boolean` | Yes | Can be `true`, `false`, or `null`; commonly used when the state may not have been provided. |

For example, a nullable database column, an omitted JSON field, or an optional configuration can be mapped to `Boolean`. If the application uses `Boolean` to represent a three-value state, do not automatically merge `null` with `false` if business rules need to distinguish "unknown" and "disabled".

## 2. Reading a Null Boolean Value Directly

Suppose the root object has a property `enabled` of type `Boolean` whose current value is `null`. Reading the property directly can still return `null` if the requested result type is `Boolean`:

```java
ExpressionParser parser = new SpelExpressionParser();
Feature feature = new Feature(); // feature.getEnabled() returns null
StandardEvaluationContext context = new StandardEvaluationContext(feature);

Boolean rawValue = parser.parseExpression("enabled")
        .getValue(context, Boolean.class);
// rawValue == null
```

This is a value read, not yet a logical operation. Therefore, `null` can be obtained without error. Keep the result type as `Boolean` if a null value is valid; do not assign directly to a Java primitive `boolean` variable, because Java will have to unbox `null` and may throw a `NullPointerException`.

## 3. Using Logical Operators with null

SpEL supports `and` (`&&`), `or` (`||`), and `not` (`!`). These operators require non-null Boolean values. If an operand actually evaluates to `null`, SpEL reports a type conversion error instead of applying three-valued logic.

| Expression | Result | Explanation |
| --- | --- | --- |
| `true and false` | `false` | Both operands are valid Booleans. |
| `true and null` | Error | The right-hand operand is null and must be converted to boolean. |
| `false and null` | `false` | AND short-circuit: the right-hand side is not evaluated. |
| `false or null` | Error | OR must evaluate the right-hand side because the left-hand side is false. |
| `true or null` | `true` | OR short-circuit: the right-hand side is not evaluated. |
| `!null` | Error | NOT requires a non-null Boolean value. |

Example when property `enabled` is null:

```spel
enabled and true
enabled or false
!enabled
```

All three expressions above need to use `enabled` as a logical operand and will throw `SpelEvaluationException` when the property's value is null. Short-circuiting only helps skip the right-hand side in cases where the left-hand side already determines the result (`false and ...`, `true or ...`); it does not turn a null left-hand side into false.

### Short-circuiting still matters

SpEL evaluates the left-hand side first. With `and`, if the left-hand side is `false`, the right-hand side is not executed. With `or`, if the left-hand side is `true`, the right-hand side is not executed. This can be used to guard a property access or method call on the right-hand side, but the left-hand side must still be a valid Boolean.

```spel
enabled != null and enabled
```

If `enabled` is null, the left-hand side `enabled != null` returns false and SpEL stops evaluating; if `enabled` is non-null, the right-hand side is Boolean true or false. However, in many cases `enabled == true` is easier to read and more direct.

## 4. Comparing null with true and false

To check a nullable state, compare the property with `null`, `true`, or `false`. Equality/inequality comparisons clearly distinguish null from the two Boolean values:

| Expression when `enabled` is null | Result | Meaning |
| --- | --- | --- |
| `enabled == null` | `true` | No state has been set. |
| `enabled != null` | `false` | There is no concrete Boolean value. |
| `enabled == true` | `false` | Cannot confirm the enabled state. |
| `enabled == false` | `false` | Cannot confirm the disabled state. |
| `enabled != true` | `true` | Not the true state; includes both false and null. |

For example, if the business rule only allows performing an operation when the feature is enabled, use:

```spel
enabled == true
```

Do not replace it with `enabled != false` if null must be rejected: when `enabled == null`, the expression `enabled != false` is true. Write conditions according to the exact business meaning instead of relying on negative phrasing.

## 5. Providing a Default Value Using Elvis or Ternary

If the business rule specifies that null must be treated as false, express that rule explicitly in the expression. The Elvis operator (`?:`) returns the left-hand side when it is non-null, and the right-hand side when the left-hand side is null:

```spel
enabled ?: false
```

This preserves `true` and `false`, replacing only `null` with `false`. That result can be used in logical operators:

```spel
(enabled ?: false) and (verified ?: false)
```

If explicit syntax is needed or a Spring version without the Elvis operator must be supported, use the ternary operator:

```spel
enabled != null ? enabled : false
```

Do not use this defaulting approach when null has a distinct business meaning, such as "unconfirmed". In that case, preserve the three states and handle each branch:

```spel
enabled == null ? 'UNSPECIFIED' : (enabled ? 'ENABLED' : 'DISABLED')
```

The example above returns distinct labels for the unspecified, enabled, and disabled states.

## 6. Complete Java Example

Suppose `Feature` has a getter `getEnabled()` returning `Boolean`. Multiple expressions can be parsed to check each state:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(feature);

Boolean raw = parser.parseExpression("enabled")
        .getValue(context, Boolean.class);

Boolean isUnspecified = parser.parseExpression("enabled == null")
        .getValue(context, Boolean.class);

Boolean isEnabled = parser.parseExpression("enabled == true")
        .getValue(context, Boolean.class);

Boolean isDisabled = parser.parseExpression("enabled == false")
        .getValue(context, Boolean.class);

Boolean enabledWithDefault = parser.parseExpression("enabled ?: false")
        .getValue(context, Boolean.class);
```

When `feature.getEnabled()` returns null, the results are `null`, `true`, `false`, `false`, and `false`, respectively. This keeps the original information (`raw`) separate from the value with the default policy applied (`enabledWithDefault`).

If the expression needs to combine multiple nullable flags, each flag can be normalized before using `and`/`or`:

```java
Boolean allowed = parser.parseExpression(
        "(enabled ?: false) and (verified ?: false)")
        .getValue(context, Boolean.class);
```

The code snippet above returns true only when both flags are true; null is handled according to the default-false policy. If the null state should be preserved as "unspecified", check for null separately before performing logic.

## 7. Combining with Safe Navigation

Safe navigation (`?.`) helps access properties without causing an error solely because an object on the left is null. However, the result of a safe access can itself be null; safe navigation does not turn that result into false.

```spel
customer?.preferences?.marketingEnabled
```

If `customer`, `preferences`, or `marketingEnabled` is null, the result may be null. Use a comparison to check explicitly:

```spel
customer?.preferences?.marketingEnabled == true
```

Or if the business rule treats null as false:

```spel
customer?.preferences?.marketingEnabled ?: false
```

Do not write `customer?.preferences?.marketingEnabled and consentGiven` if any of the values can be null; compare with true or apply a default value first.

## 8. Distinguishing SpEL Errors from Java Unboxing Errors

There are two different error situations to recognize:

1. **Error inside the expression:** a logical operator such as `and`, `or`, or `!` receives a null operand. SpEL throws `SpelEvaluationException` with an error converting `null` to `boolean`.
2. **Error after evaluation:** the expression simply returns a null property, `getValue(..., Boolean.class)` returns null, but Java code assigns the result to a primitive `boolean`. Java unboxes null and throws `NullPointerException`.

For example, use the wrapper type if null needs to be preserved:

```java
Boolean result = parser.parseExpression("enabled")
        .getValue(context, Boolean.class);
```

If a method's contract requires a primitive result, decide the default in one clear place:

```java
boolean result = Boolean.TRUE.equals(
        parser.parseExpression("enabled")
                .getValue(context, Boolean.class));
```

`Boolean.TRUE.equals(result)` returns true only when the value is `Boolean.TRUE`; both false and null yield false. This is a clear policy when the application wants to accept only the enabled state.

## 9. Common Errors and How to Handle Them

| Symptom | Cause | How to handle |
| --- | --- | --- |
| `SpelEvaluationException` when using `enabled and ...` | `enabled` is a null `Boolean`. | Check `enabled != null`, compare `enabled == true`, or apply a default before using logic. |
| `!enabled` fails when data is missing | NOT requires a non-null Boolean. | Use `enabled == false` if you only want to check false; use `!(enabled ?: false)` if policy treats null as false. |
| `enabled != false` returns true when enabled is null | `null` differs from `false`; inequality returns true. | Use `enabled == true` if only the enabled state is valid. |
| `NullPointerException` in Java code after `getValue` | A null Boolean value was unboxed into primitive `boolean`. | Receive the result as `Boolean` or apply an explicit default with `Boolean.TRUE.equals(...)`. |
| Safe navigation still leads to errors in `and`/`or` | Safe navigation returns null; logical operators do not handle null automatically. | Compare the result with true or use Elvis to choose a default. |
| Null is silently treated as false even though business rules require distinguishing it | The expression applied an inappropriate default or negation. | Preserve the original value and handle the null branch separately. |

## Key Takeaways

- `Boolean` can be null; primitive `boolean` only has true/false.
- Reading a nullable property directly as type `Boolean` can return null.
- `and`, `or`, `not` require non-null Boolean operands; null in an evaluated operand causes `SpelEvaluationException`.
- Short-circuiting only skips the right-hand side for `false and ...` or `true or ...`; it does not turn null into false.
- Use `== null`, `== true`, `== false` to express each state clearly.
- `enabled ?: false` applies a default-false policy while preserving the false value.
- Safe navigation avoids errors accessing null objects, but the result can still be null.
- Distinguish conversion errors inside SpEL from `NullPointerException` caused by Java unboxing.

## References

- [Spring Framework Reference — Operators](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)
- [Spring Framework Reference — Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html)
- [Spring Framework Reference — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework source — OpAnd](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/OpAnd.java)
- [Spring Framework source — OpOr](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/OpOr.java)
- [Spring Framework source — OperatorNot](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/OperatorNot.java)