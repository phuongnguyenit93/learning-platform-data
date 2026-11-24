# Nullable Boolean Expressions in SpEL

## Objective

In Java, a property of type `Boolean` can have three states: `true`, `false`, or `null`. `null` usually means not set, unknown, or no data. When using these values in Spring Expression Language (SpEL), you need to distinguish between reading a Boolean value directly, comparing it with `true`/`false`, and passing it into logical operators.

Important point: SpEL does not automatically treat `null` as `false` in `and`, `or`, or `not` operators. Logical operators require a non-null Boolean value; if an operand evaluates to `null`, SpEL throws `SpelEvaluationException` because it cannot convert `null` to `boolean`. Check for null or choose a default value explicitly.

## 1. boolean and Nullable Boolean

Java has two common types:

| Type | Nullable? | Meaning |
| --- | --- | --- |
| `boolean` | No | Only `true` or `false`; the default value of a field is `false`. |
| `Boolean` | Yes | Can be `true`, `false`, or `null`; commonly used when a state may not have been provided. |

For example, a nullable database column, an omitted JSON field, or an optional configuration can be mapped to `Boolean`. If the application uses `Boolean` to represent a three-value state, do not automatically merge `null` with `false` if business logic needs to distinguish between "unknown" and "disabled".

## 2. Reading a Null Boolean Value Directly

Suppose the root object has an `enabled` property of type `Boolean` whose current value is `null`. Reading the property directly can still return `null` if the requested result type is `Boolean`:

```java
ExpressionParser parser = new SpelExpressionParser();
Feature feature = new Feature(); // feature.getEnabled() returns null
StandardEvaluationContext context = new StandardEvaluationContext(feature);

Boolean rawValue = parser.parseExpression("enabled")
        .getValue(context, Boolean.class);
// rawValue == null
```

This is a value read, not yet a logical operation. Therefore, it can return `null` without an error. Keep the result type as `Boolean` if null is valid; do not assign directly to a Java primitive `boolean` variable, because Java will have to unbox `null` and may throw `NullPointerException`.

## 3. Using Logical Operators with Null

SpEL supports `and` (`&&`), `or` (`||`), and `not` (`!`). These operators require non-null Boolean values. If an operand actually evaluates to `null`, SpEL reports a type conversion error instead of applying three-valued logic.

| Expression | Result | Explanation |
| --- | --- | --- |
| `true and false` | `false` | Both operands are valid Booleans. |
| `true and null` | Error | The right operand is null and must be converted to boolean. |
| `false and null` | `false` | AND short-circuit: the right-hand side is not evaluated. |
| `false or null` | Error | OR must evaluate the right-hand side because the left-hand side is false. |
| `true or null` | `true` | OR short-circuit: the right-hand side is not evaluated. |
| `!null` | Error | NOT requires a non-null Boolean value. |

Example when the `enabled` property is null:

```spel
enabled and true
enabled or false
!enabled
```

All three expressions above require using `enabled` as a logical operand and will throw `SpelEvaluationException` when the property value is null. Short-circuiting only skips the right-hand side when the left-hand side has already determined the result (`false and ...`, `true or ...`); it does not turn a null left-hand side into false.

### Short-Circuiting Still Matters

SpEL evaluates the left-hand side first. With `and`, if the left-hand side is `false`, the right-hand side is not run. With `or`, if the left-hand side is `true`, the right-hand side is not run. This can be used to guard an access or method call on the right-hand side, but the left-hand side must still be a valid Boolean.

```spel
enabled != null and enabled
```

If `enabled` is null, the left-hand side `enabled != null` returns false and SpEL stops evaluating; if `enabled` is not null, the right-hand side is Boolean true or false. However, in many cases `enabled == true` is easier to read and more direct.

## 4. Comparing Null with true and false

To check a nullable state, compare the property with `null`, `true`, or `false`. Equality/inequality comparisons clearly distinguish null from the two Boolean values:

| Expression when `enabled` is null | Result | Meaning |
| --- | --- | --- |
| `enabled == null` | `true` | No state has been set. |
| `enabled != null` | `false` | No specific Boolean value exists. |
| `enabled == true` | `false` | Cannot confirm the enabled state. |
| `enabled == false` | `false` | Cannot confirm the disabled state. |
| `enabled != true` | `true` | Not the true state; includes both false and null. |

For example, if business logic only allows performing an action when the feature is enabled, use:

```spel
enabled == true
```

Do not replace this with `enabled != false` if null must be rejected: when `enabled == null`, the expression `enabled != false` is true. Write the condition according to the exact business meaning rather than relying on a negated phrasing.

## 5. Providing Default Values with Elvis or Ternary

If business rules specify that null must be treated as false, express that rule explicitly in the expression. The Elvis operator (`?:`) returns the left-hand side when it is not null, and the right-hand side when the left-hand side is null:

```spel
enabled ?: false
```

This preserves `true` and `false`, only replacing `null` with `false`. That result can be used in logical operators:

```spel
(enabled ?: false) and (verified ?: false)
```

If explicit syntax is needed or if you must support a Spring version without the Elvis operator, use the ternary operator:

```spel
enabled != null ? enabled : false
```

Do not use this defaulting approach when null has its own business meaning, such as "unconfirmed". In that case, preserve the three states and handle each branch:

```spel
enabled == null ? 'UNSPECIFIED' : (enabled ? 'ENABLED' : 'DISABLED')
```

The example above returns separate labels for the unspecified, enabled, and disabled states.

## 6. Complete Java Example

Suppose `Feature` has a getter `getEnabled()` returning `Boolean`. Multiple expressions can be parsed to inspect each state:

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

When `feature.getEnabled()` returns null, the results are `null`, `true`, `false`, `false`, and `false`, respectively. This approach keeps the original information (`raw`) separate from the value with the default policy applied (`enabledWithDefault`).

If an expression needs to combine multiple nullable flags, normalize each flag before using `and`/`or`:

```java
Boolean allowed = parser.parseExpression(
        "(enabled ?: false) and (verified ?: false)")
        .getValue(context, Boolean.class);
```

The code above returns true only when both flags are true; null is handled according to the default policy of false. If you want the null state preserved as "unspecified", check for null separately before performing the logic.

## 7. Combining with Safe Navigation

Safe navigation (`?.`) helps access a property without causing an error just because the object on the left is null. However, the result of a safe access can itself be null; safe navigation does not turn that result into false.

```spel
customer?.preferences?.marketingEnabled
```

If `customer`, `preferences`, or `marketingEnabled` is null, the result may be null. Use a comparison to check explicitly:

```spel
customer?.preferences?.marketingEnabled == true
```

Or if business logic treats null as false:

```spel
customer?.preferences?.marketingEnabled ?: false
```

Do not write `customer?.preferences?.marketingEnabled and consentGiven` if any of the values can be null; compare with true or apply a default value first.

## 8. Distinguishing SpEL Errors from Java Unboxing Errors

There are two different error situations to recognize:

1. **Error inside the expression:** a logical operator such as `and`, `or`, or `!` receives a null operand. SpEL throws `SpelEvaluationException` with an error converting `null` to `boolean`.
2. **Error after evaluation:** the expression simply returns a null property, `getValue(..., Boolean.class)` returns null, and Java code assigns the result to a primitive `boolean`. Java unboxes null and throws `NullPointerException`.

For example, use the wrapper type if null needs to be preserved:

```java
Boolean result = parser.parseExpression("enabled")
        .getValue(context, Boolean.class);
```

If the method contract requires a primitive result, decide the default in one clear place:

```java
boolean result = Boolean.TRUE.equals(
        parser.parseExpression("enabled")
                .getValue(context, Boolean.class));
```

`Boolean.TRUE.equals(result)` returns true only when the value is `Boolean.TRUE`; both false and null produce false. This is a clear policy when the application wants to accept only the enabled state.

## 9. Common Mistakes and How to Handle Them

| Symptom | Cause | Solution |
| --- | --- | --- |
| `SpelEvaluationException` when using `enabled and ...` | `enabled` is a null `Boolean`. | Check `enabled != null`, compare `enabled == true`, or apply a default before using logic. |
| `!enabled` fails when data is absent | NOT requires a non-null Boolean. | Use `enabled == false` if you only want to check for false; use `!(enabled ?: false)` if policy treats null as false. |
| `enabled != false` evaluates to true when enabled is null | `null` differs from `false`; inequality returns true. | Use `enabled == true` if only the enabled state is valid. |
| `NullPointerException` in Java code after `getValue` | A null Boolean value is unboxed into primitive `boolean`. | Receive the result as `Boolean` or apply an explicit default with `Boolean.TRUE.equals(...)`. |
| Safe navigation still leads to errors in `and`/`or` | Safe navigation returns null; logical operators do not handle null automatically. | Compare the result with true or use Elvis to choose a default. |
| Null is silently treated as false even though business logic needs to distinguish them | The expression applied an inappropriate default or negation. | Preserve the original value and handle the null branch separately. |

## Key Takeaways

- `Boolean` can be null; primitive `boolean` only has true/false.
- Reading a nullable property directly as `Boolean` can return null.
- `and`, `or`, and `not` require non-null Boolean operands; null in an evaluated operand causes `SpelEvaluationException`.
- Short-circuiting only skips the right-hand side for `false and ...` or `true or ...`; it does not turn null into false.
- Use `== null`, `== true`, and `== false` to express each state clearly.
- `enabled ?: false` applies a default-false policy while preserving the false value.
- Safe navigation avoids errors accessing a null object, but the result can still be null.
- Distinguish conversion errors inside SpEL from `NullPointerException` caused by Java unboxing.

## References

- [Spring Framework Reference — Operators](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)
- [Spring Framework Reference — Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html)
- [Spring Framework Reference — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework source — OpAnd](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/OpAnd.java)
- [Spring Framework source — OpOr](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/OpOr.java)
- [Spring Framework source — OperatorNot](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/OperatorNot.java)