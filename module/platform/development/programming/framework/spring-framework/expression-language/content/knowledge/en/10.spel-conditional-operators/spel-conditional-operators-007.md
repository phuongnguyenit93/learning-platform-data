# Testing All Branches of Conditional Expressions in SpEL

## 1. Role of Conditional Operators

Spring Expression Language (SpEL) supports conditional expressions to choose a value or evaluate an expression branch based on the result of a Boolean condition. This is a way to express if-then-else logic directly inside an expression, useful when building display labels, default values, classification rules, or state-dependent configuration.

The two main conditional operators in SpEL are:

| Operator | Syntax | Meaning |
|---|---|---|
| Ternary (if-then-else) | `condition ? valueIfTrue : valueIfFalse` | Selects one of two branches based on a condition. |
| Elvis | `value ?: defaultValue` | Uses the left-hand value if valid; if null or an empty string, uses the default value. |

Ternary has two explicit branches. Elvis is a shorthand form commonly used to replace the pattern of checking for null/empty string and then choosing a fallback value.

When testing, it is necessary to run all possible paths. For ternary, both the true and false branches must be checked. For Elvis, an available value, null, and an empty string must be checked. If expressions are nested, each sub-condition must also pass through both outcomes.

## 2. Ternary Operator: Syntax and Evaluation

Syntax:

```text
condition ? expressionIfTrue : expressionIfFalse
```

- `condition` must evaluate to a Boolean.
- If the condition is `true`, SpEL evaluates and returns `expressionIfTrue`.
- If the condition is `false`, SpEL evaluates and returns `expressionIfFalse`.

Simple example:

```java
ExpressionParser parser = new SpelExpressionParser();

String result = parser.parseExpression(
        "true ? 'approved' : 'rejected'")
        .getValue(String.class);

// result = "approved"
```

Changing the condition to `false` selects the branch after the colon:

```java
String result = parser.parseExpression(
        "false ? 'approved' : 'rejected'")
        .getValue(String.class);

// result = "rejected"
```

The condition and both branches are SpEL expressions. Therefore, each branch can be a literal, string concatenation, arithmetic operation, property access, method invocation, or another conditional expression.

### 2.1. Only the Selected Branch Is Evaluated

Ternary only evaluates the branch corresponding to the condition's result. The other branch is not executed. This matters when a branch invokes a method, accesses data that may not exist, or performs an expensive computation.

Example:

```text
#isMember ? #memberMessage : #guestMessage
```

When `#isMember` is true, only `#memberMessage` is evaluated. When false, only `#guestMessage` is evaluated.

Do not place side effects that must run into a branch that might not be selected. Also remember that if the selected branch has an error, expression evaluation will fail even if the other branch has a valid value.

### 2.2. Conditions Can Be Comparisons or Logical Expressions

The condition is usually not a Boolean literal, but a comparison on data:

```java
int score = 82;

String grade = parser.parseExpression(
        "#score >= 50 ? 'PASS' : 'FAIL'")
        .getValue(context, String.class);
```

Multiple conditions can be combined:

```text
(active and verified) ? 'ACTIVE_VERIFIED' : 'REVIEW_REQUIRED'
```

The condition must have a valid Boolean result. If condition returns null or a value that cannot be converted to Boolean, SpEL may raise an evaluation error; do not treat null as false by default.

## 3. Testing Both Branches of Ternary

A test that only runs an expression with a true condition only proves the true branch. It does not prove the false branch works. For basic branch coverage, use data that makes condition take both outcomes and use distinct output values to identify which branch ran.

Example with a variable in EvaluationContext:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "#isMember ? 'MEMBER' : 'GUEST'");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("isMember", true);
String memberResult = expression.getValue(context, String.class);
// MEMBER

context.setVariable("isMember", false);
String guestResult = expression.getValue(context, String.class);
// GUEST
```

You can write a JUnit 5 test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.expression.Expression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class TernaryExpressionTest {

    @Test
    void evaluatesBothTernaryBranches() {
        var parser = new SpelExpressionParser();
        Expression expression = parser.parseExpression(
                "#isMember ? 'MEMBER' : 'GUEST'");

        var context = new StandardEvaluationContext();

        context.setVariable("isMember", true);
        assertEquals("MEMBER",
                expression.getValue(context, String.class));

        context.setVariable("isMember", false);
        assertEquals("GUEST",
                expression.getValue(context, String.class));
    }
}
```

Two assertions prove both outcomes. Keep the outputs of the two branches distinct; if both return the same string, tests might pass even if the expression chooses the wrong branch.

## 4. Testing Nested Expressions

A ternary can contain another ternary in one of its branches. This is a way to represent multiple classification levels without writing multiple separate expressions.

Example grading classification:

```text
#score >= 80 ? 'A' : (#score >= 60 ? 'B' : 'C')
```

Evaluation flow:

1. If `#score >= 80` is true, the result is `A`; the expression inside the false branch does not need to be evaluated.
2. If the first condition is false, SpEL checks `#score >= 60`.
3. If the second condition is true, the result is `B`.
4. If both conditions are false, the result is `C`.

The test dataset should traverse all three output paths:

| Score | First condition `>= 80` | Second condition `>= 60` | Expected result |
|---:|---|---|---|
| 90 | true | Not evaluated | A |
| 70 | false | true | B |
| 50 | false | false | C |

To test thresholds accurately, add boundary values:

| Score | Expected result | Purpose |
|---:|---|---|
| 80 | A | Check right at threshold A. |
| 79 | B | Check just below threshold A. |
| 60 | B | Check right at threshold B. |
| 59 | C | Check just below threshold B. |

A JUnit test can set multiple values on the same context variable:

```java
@Test
void evaluatesEveryGradeBranchAndBoundary() {
    var parser = new SpelExpressionParser();
    var expression = parser.parseExpression(
            "#score >= 80 ? 'A' : (#score >= 60 ? 'B' : 'C')");
    var context = new StandardEvaluationContext();

    context.setVariable("score", 90);
    assertEquals("A", expression.getValue(context, String.class));

    context.setVariable("score", 70);
    assertEquals("B", expression.getValue(context, String.class));

    context.setVariable("score", 50);
    assertEquals("C", expression.getValue(context, String.class));

    context.setVariable("score", 80);
    assertEquals("A", expression.getValue(context, String.class));

    context.setVariable("score", 79);
    assertEquals("B", expression.getValue(context, String.class));

    context.setVariable("score", 60);
    assertEquals("B", expression.getValue(context, String.class));

    context.setVariable("score", 59);
    assertEquals("C", expression.getValue(context, String.class));
}
```

For nested expressions, branch coverage requires each decision to have both true and false outcomes. Merely obtaining all output values is sometimes not enough if a decision has multiple distinct paths; check each sub-condition according to the expression design.

## 5. Elvis Operator: Default Value for Null and Empty Strings

Elvis has the syntax:

```text
value ?: defaultValue
```

SpEL returns the left-hand side if it is not null and not an empty string. If the left-hand side is null or `""`, SpEL returns the right-hand side.

Example:

```java
String displayName = parser.parseExpression(
        "#name ?: 'Anonymous'")
        .getValue(context, String.class);
```

Behavior table:

| Value of `#name` | Result of `#name ?: 'Anonymous'` |
|---|---|
| `"Lan"` | `"Lan"` |
| `null` | `"Anonymous"` |
| `""` | `"Anonymous"` |
| `" "` | `" "` |

A string containing only a space is not an empty string, so Elvis preserves that string. If business logic wants to treat whitespace-only strings as missing data, normalize or check `trim()` explicitly before using Elvis.

Elvis does not check truthiness like some other languages. The Boolean value `false` and the number `0` are neither null nor empty strings, so they are preserved:

| Left-hand value | Result |
|---|---|
| `false` | `false` |
| `0` | `0` |
| `null` | Uses default value |
| `""` | Uses default value |

### 5.1. Testing All Elvis Cases

```java
@Test
void evaluatesElvisFallbackCases() {
    var parser = new SpelExpressionParser();
    var expression = parser.parseExpression(
            "#name ?: 'Anonymous'");
    var context = new StandardEvaluationContext();

    context.setVariable("name", "Lan");
    assertEquals("Lan", expression.getValue(context, String.class));

    context.setVariable("name", null);
    assertEquals("Anonymous",
            expression.getValue(context, String.class));

    context.setVariable("name", "");
    assertEquals("Anonymous",
            expression.getValue(context, String.class));

    context.setVariable("name", " ");
    assertEquals(" ",
            expression.getValue(context, String.class));
}
```

The four cases above test a normal value, null, empty string, and whitespace-only string. If you only test null, you will miss Elvis's special behavior for empty strings.

### 5.2. Using Elvis to Configure Default Values

Elvis is often used in `@Value`:

```java
@Value("#{systemProperties['pop3.port'] ?: 25}")
private int port;
```

If the `pop3.port` system property has no value or is an empty string, the default value `25` is selected. If it has a value, SpEL returns that value and Spring performs conversion appropriate for the target field type.

## 6. Elvis and Ternary: Choosing the Right Expression Form

Elvis is a shorthand form of a ternary pattern checking for null/empty string. The following two expressions are equivalent in meaning for strings:

```text
#name != null and #name != '' ? #name : 'Anonymous'
```

```text
#name ?: 'Anonymous'
```

Elvis is more concise and handles empty strings as well. A ternary that only checks `#name != null` will return an empty string if `#name` is `""`, so it is not completely equivalent.

Use ternary when there is an explicit business condition and the two branches carry different meanings, for example:

```text
#order.total >= 100000 ? 'VIP' : 'STANDARD'
```

Use Elvis when you only need a fallback value for null or empty string data:

```text
#order.note ?: 'No note'
```

If a condition has multiple criteria, write a clear logical expression in the condition part and place parentheses around sub-groups:

```text
(#order.total >= 100000 and #customer.active) ? 'PRIORITY' : 'NORMAL'
```

## 7. Testing Return Values and Data Types

The two ternary branches can return different values. Example:

```text
#isEnabled ? 1 : 0
```

The runtime result depends on the selected branch. If Java code needs a specific type, request that type when calling `getValue()`:

```java
Integer enabledCode = parser.parseExpression(
        "#isEnabled ? 1 : 0")
        .getValue(context, Integer.class);
```

Design the two branches to have result types compatible with the intended use. If one branch returns a String while the other returns an object of a different type, the caller must handle the actual result type or provide an appropriate conversion.

Condition must evaluate to a Boolean. The following example is a valid conditional expression:

```text
#quantity > 0 ? 'IN_STOCK' : 'OUT_OF_STOCK'
```

A String value such as `'true'` should not be used in place of a Boolean condition. Use a real Boolean or a comparison returning a Boolean.

## 8. Null and Evaluation Errors in Conditional Expressions

Ternary and Elvis handle null differently:

- Ternary requires a Boolean condition. If condition cannot evaluate to a Boolean, SpEL raises an error instead of automatically choosing the false branch.
- Elvis actively treats null as a case that needs the fallback value.
- Elvis also treats an empty string as a case that needs the fallback value.
- A whitespace-only string is still a non-empty string.
- A value of false or 0 does not trigger Elvis's fallback.

For example, if `#user` may be null, do not access `#user.active` directly in condition. You can use short-circuiting in condition or select a branch with a null check:

```text
#user != null and #user.active ? 'ACTIVE' : 'UNKNOWN'
```

If a Boolean property may be null, check for null first:

```text
#enabled != null ? #enabled : false
```

Do not confuse Elvis with safe navigation. Safe navigation `?.` guards property/method access when the left-hand object is null; Elvis `?:` chooses a replacement value when the left-hand value itself is null or an empty string. They solve two different needs and can be combined when necessary.

## 9. Optional and Version Differences

Since Spring Framework 7.0, Elvis supports `java.util.Optional` with unwrapping:

- If the left-hand side is `Optional.empty()`, Elvis uses the right-hand side.
- If the left-hand side is an Optional with a value, the expression returns the value inside the Optional.

Example:

```java
context.setVariable("nickname", Optional.empty());

String displayName = parser.parseExpression(
        "#nickname ?: 'Anonymous'")
        .getValue(context, String.class);
// Anonymous
```

With `Optional.of("Lan")`, the result is `"Lan"`.

This capability was added in Spring Framework 7.0. If the application runs Spring Framework 6.x or older, do not rely on this Optional unwrapping behavior; unwrap Optional in Java or write an expression compatible with the version in use.

## 10. Branch Testing Matrix

Before putting a conditional expression into configuration or an application, build an input/output matrix to identify every branch that must execute.

| Expression type | Case to test | Result to verify |
|---|---|---|
| Simple ternary | Condition true | Branch after `?` is returned. |
| Simple ternary | Condition false | Branch after `:` is returned. |
| Nested ternary | Outer condition true | Outer true branch is selected. |
| Nested ternary | Outer condition false, inner condition true | Inner true branch is selected. |
| Nested ternary | Both outer and inner conditions false | Final false branch is selected. |
| Threshold ternary | Just below, at, and just above each threshold | No off-by-one discrepancy at boundary conditions. |
| Elvis | Non-null, non-empty value | Preserves the left-hand value. |
| Elvis | Null | Uses default value. |
| Elvis | Empty string | Uses default value. |
| Elvis | Whitespace string | Preserves whitespace string. |
| Elvis | false or 0 | Preserves value, no fallback. |
| Elvis with Optional (Spring 7.0+) | Empty Optional and present Optional | Proper fallback or unwrapping. |

A good testing matrix should record both inputs and expected results. Do not just note "ran the expression"; prove that every path was triggered.

## 11. Common Mistakes and How to Handle Them

| Symptom | Common cause | Solution |
|---|---|---|
| Always gets the false branch | Condition is always false, wrong property read, or test data does not cover true. | Create test data that makes condition true and inspect the condition value separately. |
| True branch works but false branch fails | The false branch was not executed in earlier tests. | Add a condition-false test case and inspect that branch's expression. |
| Nested ternary returns wrong result | Missing parentheses or unintended condition grouping. | Parenthesize each sub-ternary and write a path table. |
| Cannot use a null condition | Null is not Boolean false. | Check for null explicitly before using the condition. |
| Elvis returns a whitespace-only string | That string is not empty. | Normalize the string or check trim according to business rules. |
| Elvis preserves false or 0 | These are valid values, not null or empty String. | If business logic wants fallback on false/0 too, write an explicit ternary condition. |
| Elvis with Optional does not unwrap | Spring version does not support it yet. | Only rely on Optional support from Spring Framework 7.0; older versions need unwrapping in Java. |
| Selected branch raises an error | The expression in that branch is wrong or data fails requirements. | Test each branch individually and verify the object/property/method used. |
| Result type is not as expected | Both branches return different types or caller requests an incompatible type. | Use consistent output types or convert explicitly via `getValue()`/ConversionService. |
| Tests pass but lack branch coverage | Only ran one condition outcome or skipped sub-branches. | Track every decision and add tests for true/false at each level. |

## 12. Practical Testing Workflow

1. Write expressions with meaningful condition and branch names, avoiding identical literals that make outcomes hard to tell apart.
2. List every decision in the expression, including decisions inside nested ternaries.
3. For each decision, prepare at least one dataset making condition true and one making condition false.
4. For threshold comparison conditions, test values just below, equal to, and just above the threshold.
5. For Elvis, test null, empty string, non-empty string, and whitespace string; test false/0 if the data type allows them.
6. Verify the selected branch can evaluate successfully and return the right type.
7. Re-run the expression with the same EvaluationContext or update context variables between runs to prove each branch.
8. Compare actual results against the expected matrix and save edge cases as automated tests.

Separating expression testing from application business logic helps pinpoint whether an error lies in the condition, input data, selected branch, or type conversion.

## 13. Key Takeaways

- Ternary has the form `condition ? trueExpression : falseExpression`; condition must be Boolean.
- SpEL only evaluates the selected branch, so both branches must be tested individually.
- With nested ternaries, test true/false for every decision and boundary values.
- Elvis has the form `value ?: defaultValue`; fallback occurs when the left-hand value is null or an empty string.
- Whitespace strings, Boolean false, and the number 0 do not trigger Elvis fallback.
- Spring Framework 7.0 supports unwrapping Optional in Elvis; check your version before using it.
- Safe navigation `?.` differs from Elvis `?:`: one guards access, the other chooses a default value.
- Use an input/output matrix to prove all branches and save them as automated tests.

## References

- [Spring Framework Reference — Ternary Operator (If-Then-Else)](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-ternary.html)
- [Spring Framework Reference — The Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpEL Ternary AST Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/Ternary.html)
- [SpEL Elvis AST Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/Elvis.html)
