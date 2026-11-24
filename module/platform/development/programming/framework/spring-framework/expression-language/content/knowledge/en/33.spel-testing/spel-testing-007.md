# Testing Both Conditional Branches and Empty Collection Cases

## Objectives

After this lesson, you will be able to design tests for both branches of conditional expressions in Spring Expression Language (SpEL); verify the behavior of ternary, Elvis, and logical AND/OR operators; and distinguish empty collections, collections with no matching elements, and null values. You will also know how to test selection, projection, first/last selection, nested data, and boundary cases using JUnit. The goal is to ensure expressions return the right results for both normal data and states that are easy to overlook.

## 1. Why must both branches be tested?

A conditional expression typically has at least two possible outcomes. Example:

~~~text
#paid ? 'PAID' : 'PENDING'
~~~

When paid is true, the expression returns PAID. When paid is false, the expression returns PENDING.

If only the paid = true case is tested, the false branch may contain a bug that the test suite misses. The bug could be a wrong property name, an unregistered variable, an incorrect default value, or a method call appearing only in the other branch.

For business expressions, verify at least:

- The true condition branch.
- The false condition branch.
- Null condition or missing data cases, if allowed by the contract.
- Boundary values causing the condition to flip from false to true or vice versa.
- The result type and value of each branch.

An expression parsing successfully does not mean both branches can execute. The parser checks the syntax of the entire expression, yet property access, method invocation, or type conversion errors in a branch may only appear when that branch is evaluated.

## 2. Testing the ternary operator

The conditional operator has the syntax:

~~~text
condition ? valueWhenTrue : valueWhenFalse
~~~

Example:

~~~text
#order.total >= #minimum ? 'ELIGIBLE' : 'NOT_ELIGIBLE'
~~~

To test thoroughly, create two data sets so the condition is true and false respectively:

| total | minimum | Expected result |
|---:|---:|---|
| 150 | 100 | ELIGIBLE |
| 80 | 100 | NOT_ELIGIBLE |
| 100 | 100 | ELIGIBLE |
| 99.99 | 100 | NOT_ELIGIBLE |

Values right at the threshold are critical. If business rules use >= yet the expression accidentally uses >, tests with 150 and 80 can still pass; testing right at the 100 boundary catches the discrepancy.

Each branch should have both its content and result type verified. If one branch returns a String while the other returns a different object type, check whether that is intentional and convertible to the desired target type.

## 3. Ternary only evaluates the selected branch

In a conditional expression, SpEL evaluates the condition and then evaluates the corresponding branch. The unselected branch does not need to execute.

Example:

~~~text
#customer != null ? #customer.name : 'Guest'
~~~

If customer is null, the result is Guest and accessing name is not performed.

This is why ternary is often used to guard an operation valid only when the condition holds. However, the condition must actually check the state needing protection. If the expression uses another nullable property before deciding the branch, an error can still occur.

When testing, include one test confirming the selected branch and one test confirming the other branch. If a branch contains a method call or function, test doubles can verify that only the intended operation is invoked. Avoid putting side effects into expressions just to check order; test using mocks or spies in Java when needed.

## 4. Testing the Elvis operator

The Elvis operator uses the syntax:

~~~text
value ?: fallback
~~~

Example:

~~~text
#customer.nickname ?: 'Guest'
~~~

If nickname has an appropriate value, the expression returns nickname. If the left-hand value is null, Elvis returns the fallback. For empty strings, determine the desired behavior and test according to the exact rules of the SpEL version in use; do not assume Elvis is synonymous with a blank-string check.

Several cases to test:

| Left-hand value | What to verify |
|---|---|
| "An" | Keeps existing value |
| null | Uses fallback |
| "" | Confirms rule for empty string |
| "   " | Confirms whether separate trim/blank validation is needed |
| 0 | Does not confuse number 0 with null |
| false | Does not confuse false with null |

Elvis is useful for optional values. It does not replace validation for required data. If nickname is required to have content, returning Guest can mask invalid data instead of reporting an error.

## 5. Testing logical AND and OR

Commonly used logical operators:

~~~text
#enabled and #authorized
#isAdmin or #isOwner
not #blocked
~~~

With AND, the result is true only when both conditions are true. With OR, the result is true when at least one condition is true.

Build a combination table instead of checking only one case:

| A | B | A and B | A or B |
|---|---|---|---|
| true | true | true | true |
| true | false | false | true |
| false | true | false | true |
| false | false | false | false |

Testing all four combinations helps catch wrong operators, inverted conditions, or a missing side.

AND and OR in SpEL use short-circuit evaluation. With AND, if the left-hand side is already false, the right-hand side does not need to be evaluated. With OR, if the left-hand side is already true, the right-hand side does not need to be evaluated. This is useful when the right-hand side is valid only after the left-hand side confirms a non-null object:

~~~text
#customer != null and #customer.active
~~~

However, write conditions in an easy-to-read order and do not rely on short-circuiting to hide unusual data structures. Test both the case where the left-hand side stops evaluation and the case where the right-hand side actually runs.

## 6. Testing empty collections and collections with no results

An empty collection and a populated collection where no element matches are two distinct inputs.

Selection example:

~~~text
#numbers.?[#this > 10]
~~~

Test at least two cases:

- Source is an empty collection: no elements to check.
- Source has elements, yet none satisfy the condition.

Both selection cases typically produce an empty result, yet they represent different data states. If business logic needs to distinguish them, inspect the source collection before selection or supply separate metadata about the source state.

Example:

| Source | Condition | Selection result |
|---|---|---|
| [] | #this > 10 | Empty collection |
| [1, 2, 3] | #this > 10 | Empty collection |
| [5, 12, 20] | #this > 10 | [12, 20] |

Do not just check the result size and conclude the original source was empty. An empty result can also happen because the filter condition matched no elements.

## 7. Distinguishing an empty collection from null

An empty collection is a valid collection object containing no elements. Null means there is no collection reference.

Example:

~~~java
List<Integer> empty = List.of();
List<Integer> missing = null;
~~~

These two states are not equivalent:

- On an empty collection, size() can be called and returns 0.
- On null, calling size() directly fails.
- Selection on an empty collection returns an empty result.
- Accessing a null collection needs to be guarded or handled per the data contract.

If business logic treats null and empty identically, normalize the data in Java before putting it into the context. If they have different meanings, keep the two states separate and write tests for both.

Example expression with a null check:

~~~text
#orders == null ? 'MISSING' :
    (#orders.isEmpty() ? 'EMPTY' : 'PRESENT')
~~~

This expression distinguishes an unprovided collection, an empty collection, and a populated collection. Ensure the orders variable is registered and its type supports isEmpty().

## 8. Testing standard selection on an empty collection

Selection typically uses the .?[] operator:

~~~text
#orders.?[total >= #minimum]
~~~

With an empty List, selection returns an empty collection. With a populated List where no element meets the condition, the result is also empty.

Example:

~~~text
#orders.?[status == 'PAID']
~~~

Verify:

- Source is an empty List.
- Source has one non-matching element.
- Source has multiple non-matching elements.
- Source has one matching element.
- Source has multiple matching elements.
- Elements with null properties if allowed by the model.
- Source is null if the application can supply that state.

When an empty result is valid, tests should confirm the collection exists and has no elements, rather than only checking the result is non-null.

## 9. Testing projection on an empty collection

Projection uses the .![] operator to transform each element:

~~~text
#orders.![id]
~~~

If the source is an empty List, projection returns an empty result collection. There are no elements on which to evaluate the id expression.

Example:

~~~text
#numbers.![#this * 2]
~~~

With source [], the result is []. With source [2, 4], the result is [4, 8].

Test both an empty source and a populated source. If projection accesses nested properties, add a case for an element with a null child object:

~~~text
#orders.![customer.name]
~~~

If an order has a null customer, reading name can fail. If customer is optional, safe navigation can be used:

~~~text
#orders.![customer?.name]
~~~

Tests must verify the result for null elements according to contract; do not assume projection automatically skips elements missing data.

## 10. Testing first and last selection

First selection uses .^[] to get the first matching element; last selection uses .$[] to get the last matching element.

~~~text
#numbers.^[#this > 10]
#numbers.$[#this > 10]
~~~

If the collection has no matching elements, both first and last selection return null. This is an important difference from standard selection, which returns an empty collection.

Example with [3, 12, 18]:

- Standard selection returns [12, 18].
- First selection returns 12.
- Last selection returns 18.

With [] or [1, 2, 3], first and last selection find no elements and return null.

Test no-match, single-match, and multi-match cases. For first/last, also verify source order because "first" and "last" depend on current iteration order; these operators do not sort the collection.

## 11. Collection behavior comparison table

The following table helps choose the right assertions for each operator:

| Operator | Empty source | No matching elements | Matching elements exist |
|---|---|---|---|
| .?[condition] | Empty collection | Empty collection | Collection of matching elements |
| .![expression] | Empty collection | Filtering condition not applied; projection processes source elements | Collection of projected values |
| .^[condition] | null | null | First matching element |
| .$[condition] | null | null | Last matching element |

Projection does not filter elements by condition. If the source has N elements, projection evaluates the expression on each element in iteration order and produces corresponding results. If filtering before projecting is needed, combine selection and projection:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

With an empty source, the final result is an empty collection. With a non-empty source containing no PAID orders, the result is also empty.

## 12. Testing nested collections

A collection can contain child collections. For example, each customer has a list of orders:

~~~text
#customers.![orders.?[status == 'PAID'].![id]]
~~~

The result is a nested collection; each outer element corresponds to a customer, while the inner collection contains IDs of paid orders.

Test scenarios:

- No customers.
- Customer exists, yet orders list is empty.
- Customer has orders with no matching order.
- Customer has one or more matching orders.
- orders property is null.
- An element in the outer collection is null, if allowed by the source.
- Child data has a required property equal to null.

An empty inner collection does not mean the outer collection is empty. For instance, with two customers where neither has paid orders, the result can be two empty inner collections.

If customers without matching orders should be excluded, outer selection is needed:

~~~text
#customers.?[
    orders != null and orders.?[status == 'PAID'].size() > 0
].![name]
~~~

The expression needs testing with orders being null, empty, and having matches. If nested logic becomes hard to read, precompute the state in Java or use a clearly named business method.

## 13. Testing Maps and other collections

SpEL supports selection on Maps. The condition is evaluated on each Map.Entry and can use key or value.

Example:

~~~text
#scores.?[value >= #passingScore]
~~~

With an empty Map, the selection result is an empty Map. With a populated Map where no entry meets the threshold, the result also has no entries.

Verify:

- Empty Map.
- Populated Map with no matching entries.
- Map with one or more matching entries.
- Null key or value if permitted.
- Map implementations with different iteration orders.

With a Set, iteration order depends on the implementation. With a List, order is usually the list element order. This is especially important when testing first/last selection; use a source with deterministic order if the test requires stable results.

## 14. Testing nulls and safe navigation

Null collections must be tested separately from empty collections. If the source can be null, explicitly decide whether the expression should:

- Return null.
- Return an empty collection.
- Return a default status or message.
- Fail because required data is missing.

Example normalizing null to an empty collection inside an expression:

~~~text
#orders == null ? {} : #orders.?[status == 'PAID']
~~~

This approach uses an empty inline list as a fallback. If the result must always have the same concrete collection type, normalizing in Java is usually clearer because the exact desired collection type can be created.

Safe navigation can guard access on a null reference:

~~~text
#customer?.address?.city
~~~

For safe collection selection/projection, syntax and support depend on the Spring version in use. Check your project version's documentation before using it; for broad compatibility, explicit null checks with ternary can be used.

Do not use safe navigation to hide missing required data. Tests should distinguish allowed nulls from nulls that must be rejected.

## 15. Writing tests with JUnit 5

A simple test can create the parser, context, and evaluate the expression:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class SpelCollectionTest {

    private final ExpressionParser parser =
        new SpelExpressionParser();

    @Test
    void selectionOnEmptyListReturnsEmptyResult() {
        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("numbers", List.of());

        Expression expression =
            parser.parseExpression("#numbers.?[#this > 10]");

        List<?> result =
            expression.getValue(context, List.class);

        assertNotNull(result);
        assertTrue(result.isEmpty());
    }

    @Test
    void firstSelectionOnEmptyListReturnsNull() {
        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("numbers", List.of());

        Expression expression =
            parser.parseExpression("#numbers.^[#this > 10]");

        assertNull(expression.getValue(context));
    }
}
~~~

The example verifies two different result types: standard selection returns an empty collection, whereas first selection returns null when no element is found.

Do not rely solely on assertNotNull for every collection result. Also check size, elements, and order if order is part of the contract.

## 16. Using parameterized tests for both branches

JUnit 5 parameterized tests help run the same rule with multiple data sets:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

class SpelConditionTest {

    static Stream<org.junit.jupiter.params.provider.Arguments>
    conditionCases() {
        return Stream.of(
            org.junit.jupiter.params.provider.Arguments.of(true, "PAID"),
            org.junit.jupiter.params.provider.Arguments.of(false, "PENDING")
        );
    }

    @ParameterizedTest
    @MethodSource("conditionCases")
    void evaluatesBothConditionalBranches(
            boolean paid, String expected) {

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("paid", paid);

        Expression expression =
            new SpelExpressionParser().parseExpression(
                "#paid ? 'PAID' : 'PENDING'"
            );

        assertEquals(
            expected,
            expression.getValue(context, String.class)
        );
    }
}
~~~

The test source can be expanded to include boundary values, nulls, or special states. If a condition takes monetary amounts, use BigDecimal in tests to avoid floating-point precision errors and test right at the threshold, below the threshold, and above the threshold.

Parameterized tests ensure cases for the same rule run consistently while clarifying the input data table and expected outcomes.

## 17. Checking result types and exceptions

Besides values, verify the result type expected by the application:

~~~java
String status = expression.getValue(context, String.class);
~~~

With selection or projection, the outer collection type can be requested via getValue(context, List.class), yet the generic element type is not guaranteed solely by List.class. If List<String> is needed, inspect each element or convert explicitly.

Also verify cases that must fail:

- Unregistered required variable.
- Null collection in an expression without null protection.
- Null nested property.
- Element with incompatible type.
- Method or getter throws an exception.
- Value cannot be converted to the target type.

Use assertThrows with the appropriate exception type and avoid asserting messages too strictly if messages can change between Spring versions. Prefer checking exception types, causes, or stable error codes controlled by the application.

## 18. Testing boundary data and special cases

A solid test suite should include:

| Group | Cases |
|---|---|
| Conditions | true, false, right at threshold, just below and above threshold |
| Elvis | null, empty string, blank string, 0, false |
| Logic | All four AND/OR combinations |
| Collections | null, empty, single element, multiple elements |
| Selection | No match, one match, multiple matches |
| Projection | Empty, normal values, elements with null properties |
| First/last | Empty, no match, one match, multiple matches |
| Nested collections | Outer empty, inner empty, inner null, inner with matches |
| Map | Empty, no match, match, null key/value |
| Data types | Matching type, different type, unconvertible value |

There is no need to generate every possible combination if they have no business meaning. Prioritize cases that can alter the result, return type, or execution path of the expression.

For each expression, document the input data and expected result clearly. That helps maintainers understand why an empty or null case is considered valid.

## 19. Separating parse tests from evaluate tests

There should be dedicated parse tests for static expressions:

~~~java
@Test
void expressionCanBeParsed() {
    assertDoesNotThrow(() ->
        new SpelExpressionParser().parseExpression(
            "#orders.?[#this > 10]"
        )
    );
}
~~~

Then have evaluate tests with realistic contexts and data. Parse tests catch syntax errors; evaluate tests catch variable, type, property, and data errors.

For template expressions, parse with the corresponding ParserContext. For expressions using beans or functions, the test context must register resolvers or functions just as the application runs.

A successful parse test cannot replace testing both conditional branches or empty collections. Runtime paths must be exercised with corresponding data.

## 20. Common testing mistakes

Several omissions easily create a false sense of security in tests:

- Testing only the true branch while omitting the false branch.
- Testing only populated collections and omitting the empty case.
- Using an empty collection without testing a populated collection with no matches.
- Merging null with empty even though business rules distinguish the two states.
- Checking only that the result is non-null without checking contents.
- Testing first/last without controlling source order.
- Testing only that the expression parses successfully.
- Not testing null nested properties.
- Not verifying the result type after projection.
- Using data that does not hit conditional boundaries.
- Not testing branches containing functions or method calls.
- Sharing a mutable EvaluationContext across tests causing state leakage.

Each test should create its own context and data, unless the test's main purpose is testing context update or reuse behavior. This keeps results independent and avoids test execution-order dependencies.

## 21. Workflow for building the test suite

Follow this sequence:

1. Identify the expression source and required ParserContext.
2. List the variables, root objects, and data types needed.
3. Write a decision table for each condition.
4. Create true/false data sets and boundary values.
5. Enumerate empty, no-match, null, and populated collections.
6. Define result types for selection, projection, and first/last.
7. Write dedicated parse tests.
8. Write evaluate tests using JUnit.
9. Use parameterized tests for repetitive data sets.
10. Add exception tests for states that must be rejected.
11. Run tests on the project's actual Spring version.
12. Maintain regression tests whenever expressions or models change.

For expressions configured outside the application, run tests when loading or updating configuration to catch syntax errors early. Runtime data still needs separate tests because parse alone cannot cover every state.

## 22. Key takeaways

Test every executable branch of an expression, especially both true and false of ternary, null cases of Elvis, and the four AND/OR combinations. Ternary evaluates only the selected branch; AND/OR short-circuit, so tests must confirm both the case where the right-hand side evaluates and the case where it is skipped.

For collections, distinguish empty sources, populated sources with no matches, and null sources. Standard selection with no matches returns an empty collection; projection on an empty source also returns an empty collection; first/last selection finding no elements returns null. Nested collections require testing the state of each level separately.

Use JUnit 5 and parameterized tests to cover valid, invalid, boundary, and empty data. Check values, result types, order when meaningful, and required exceptions. Parse tests only verify syntax; evaluate tests confirm the expression works with realistic contexts and data.

## References

- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [JUnit 5 User Guide — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests)