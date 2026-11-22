# Exhaustiveness Analysis in Java Pattern Matching

**Topic:** Compiler and type checking — Java Core Pattern Matching. This article uses **Java 21 or later**, when pattern matching for switch (JEP 441) and record patterns (JEP 440) were standardized. The examples do not require enabling preview features.

## 1. What is exhaustiveness analysis?

**Exhaustiveness** (complete coverage) means that a branching construct using **switch** has a branch handling **every possible case according to the static type of the selector expression**. The Java compiler checks the case labels and type information to conclude whether the branching is complete.

For example, a variable of an **enum** type has two values, LOW and HIGH. If a switch expression has cases for both LOW and HIGH, the compiler knows every non-null enum value is handled even without a default. Similarly, when the selector has a **sealed interface** type, the compiler can rely on the set of permitted branches to prove that a switch expression covers every subtype.

This is part of **static type checking**, with concrete benefits:

1. Detecting **missing branches** at compile time, rather than waiting for rare inputs at runtime.
2. Forcing the author to review logic when adding a new enum constant or a new subtype to a closed type domain.
3. Allowing a switch expression to be written **without a default** if the specific branches are already complete.
4. Clarifying the handling contract: each meaningful case is described by its own branch.

**Exhaustiveness does not mean the data is valid for business logic.** The compiler proves coverage based on types and patterns, but does not automatically prove that strings are non-empty, numbers are positive, or dynamic guards will always hold true.

## 2. Which switches are required to be exhaustive?

Three common cases should be distinguished:

| Switch form | Exhaustiveness rule in Java 21 |
| --- | --- |
| **switch expression** returning a value | **Must be exhaustive**, otherwise it is a compile error |
| **switch statement using patterns** | **Must be exhaustive** under pattern matching for switch |
| **Traditional switch statement** without patterns | May be **non-exhaustive**; if no case matches, the switch exits without executing any branch |

Example of a valid traditional switch statement even without default:

~~~java
static void logNumber(int number) {
    switch (number) {
        case 1 -> System.out.println("one");
    }
}
~~~

If number is not 1, no case runs. However, switching to a **switch expression**:

~~~java
// DOES NOT COMPILE: missing int values other than 1.
static String labelNumber(int number) {
    return switch (number) {
        case 1 -> "one";
    };
}
~~~

The compiler cannot prove that every integer is covered. You can add **default** or a set of cases matching the selector's domain. For the general int domain, default is usually the solution.

A **pattern switch statement** with an Object selector that only has **case String s** will also fail to compile if there is no branch covering the remaining Objects. This differs from a traditional statement that does not use patterns.

## 3. Exhaustiveness with enum

Suppose an enum has only two constants:

~~~java
enum Priority { LOW, HIGH }

static String label(Priority priority) {
    return switch (priority) {
        case LOW -> "low";
        case HIGH -> "high";
    };
}
~~~

This switch expression pattern is exhaustive for **the two non-null enum values**. When **MEDIUM** is added to Priority without adding the corresponding case, the recompiled code will have to handle the missing branch or choose a new default policy.

If written as:

~~~java
return switch (priority) {
    case LOW -> "low";
    default -> "other";
};
~~~

the switch is still complete, but when the enum is extended, most new values automatically fall into default. That may be appropriate if the business logic truly has an “other” group; if you want to review each new value, prefer explicit cases and avoid default.

**Note on null:** Priority is a reference type, so the priority variable can be null. Enum exhaustiveness does not mean there is a case handling null: if the switch receives null without a matching case null, it can throw a **NullPointerException** at runtime. Write **case null** when the contract allows it and you want to handle that value intentionally.

## 4. Exhaustiveness with sealed class or sealed interface

A sealed hierarchy lets the compiler know the valid direct subtypes.

~~~java
sealed interface Outcome permits Success, Failure {}

record Success(String value) implements Outcome {}

record Failure(int code) implements Outcome {}
~~~

The snippet above illustrates a hierarchy declared within the same valid scope. **Outcome** only permits **Success** and **Failure** to implement it directly. Both records are final by nature, so they have no further subclasses.

A switch expression can list the subtypes:

~~~java
static String simpleLabel(Outcome outcome) {
    return switch (outcome) {
        case Success s -> "success";
        case Failure f -> "failure";
    };
}
~~~

This switch is **exhaustive for all non-null Outcomes**. The compiler knows each Outcome can currently be Success or Failure. **case Success s** is a type pattern, covering all Success objects; **case Failure f** covers Failures.

You are not required to use a record pattern to achieve exhaustiveness: a sufficiently broad **type pattern** can also cover the entire subtype. A record pattern is used when the branch needs to deconstruct the components, for example **Success(var value)** or **Failure(int code)**.

### When the hierarchy changes

If you add:

~~~java
// Illustrates a declaration change; do not copy both versions of Outcome at the same time.
sealed interface Outcome permits Success, Failure, Pending {}

record Pending(String id) implements Outcome {}
~~~

then the switch without default above lacks handling for Pending. When recompiling the related sources, the compiler will detect that the switch expression is not exhaustive. The business-meaningful fix is to add **case Pending p**, rather than rushing to add default just to silence the error.

An important point: sealed only restricts **direct subtypes**. If a direct branch is declared **non-sealed**, that branch can still be extended:

~~~java
sealed interface Event permits Created, OtherEvent {}
record Created(String id) implements Event {}
non-sealed interface OtherEvent extends Event {}

static String eventName(Event event) {
    return switch (event) {
        case Created(var id) -> "created " + id;
        case OtherEvent e -> "other event";
        case null -> "no event";
    };
}
~~~

The type pattern **OtherEvent e** also covers classes implementing the OtherEvent interface that are validly added later. Therefore, the switch remains exhaustive for this hierarchy. If you want the compiler to prompt an update whenever a specific event kind is added, you may need to design the sub-branches as sealed as well instead of non-sealed.

## 5. Record patterns: naming a subtype does not guarantee covering it

A record pattern can place nested patterns on its components. That makes the case branch **narrower** than a type pattern that only checks the subtype.

For example:

~~~java
record Point(int x, int y) {}
record Route(Point origin) {}
~~~

With a selector of type Route:

~~~java
// Illustrative pattern: a remaining branch is needed.
static String describeRoute(Route route) {
    return switch (route) {
        case Route(Point(int x, int y)) -> x + "," + y;
        case Route(var origin) -> "missing origin";
        case null -> "null route";
    };
}
~~~

The branch **Route(Point(int x, int y))** only matches if the origin component is a non-null Point. A **Route(null)** does not match the nested Point(...) pattern. The branch **Route(var origin)** does not require origin to be non-null, so it covers the remaining Routes.

If you remove the **Route(var origin)** branch, a switch expression with only the nested Point(...) pattern may not be exhaustive because a Route with a null origin still exists. The compiler analyzes **the actual scope of the pattern**, not merely whether the name Route appears in a case.

Component patterns with **unconditional** matching (such as var used for the corresponding component) can include null values of a reference component. However, a **specific nested record pattern** requires a record instance to deconstruct. Therefore, you must understand the kind of sub-pattern being used before concluding that a case covers the entire subtype.

## 6. Guards with when: completeness does not come from dynamic conditions

A **when** guard makes a case apply only when **the pattern has matched** and the additional condition evaluates to true:

~~~java
case Failure(int code) when code >= 500 -> "server error";
~~~

This case **does not cover** every Failure, because code can be less than 500. If there is only this guarded case without an unguarded case or an equivalent general pattern, the switch may be missing a branch.

The clear way to write it:

~~~java
case Failure(int code) when code >= 500 -> "server error";
case Failure(int code) -> "other error";
~~~

The second branch covers all remaining Failures.

You should not assume the compiler uses general logical reasoning to prove that an arbitrary set of guards will always cover every value. For instance, even though a human can see that **code >= 500** and **code < 500** are complementary conditions, Java does not perform arbitrary theorem proving across all guard expressions to guarantee exhaustiveness. Use an unguarded case when you need a catch-all coverage branch.

Place the specific guarded branch **before** the general branch. If you place an unguarded Failure before a guarded Failure, the latter becomes **dominated**, which is a different issue from missing coverage.

## 7. Complete Java 21 program

The example below combines a sealed interface, record patterns, guards, an enum, and case null. The switch expressions **have no default yet are still exhaustive**.

Save the file **ExhaustivenessAnalysisDemo.java**:

~~~java
public class ExhaustivenessAnalysisDemo {
    sealed interface Outcome permits Success, Failure {}

    record Success(String value) implements Outcome {}

    record Failure(int code) implements Outcome {}

    static String describe(Outcome outcome) {
        return switch (outcome) {
            case Success(var value)
                    when value != null && !value.isBlank() ->
                    "SUCCESS: " + value;

            case Success(var value) -> "SUCCESS: empty";

            case Failure(int code) when code >= 500 ->
                    "SERVER ERROR: " + code;

            case Failure(int code) -> "ERROR: " + code;

            case null -> "NO OUTCOME";
        };
    }

    enum Priority { LOW, HIGH }

    static String priorityLabel(Priority priority) {
        return switch (priority) {
            case LOW -> "low";
            case HIGH -> "high";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("ready")));
        System.out.println(describe(new Success("")));
        System.out.println(describe(new Success(null)));
        System.out.println(describe(new Failure(503)));
        System.out.println(describe(new Failure(404)));
        System.out.println(describe(null));
        System.out.println(priorityLabel(Priority.HIGH));
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac ExhaustivenessAnalysisDemo.java
java ExhaustivenessAnalysisDemo
~~~

Output:

~~~text
SUCCESS: ready
SUCCESS: empty
SUCCESS: empty
SERVER ERROR: 503
ERROR: 404
NO OUTCOME
high
~~~

**Explanation of describe() coverage:**

1. **Success with a non-null, non-blank value** matches the first case; this is a specific guarded branch.
2. **Remaining Success instances**, including an empty string or a null value component, match the unguarded Success case.
3. **Failure with code >= 500** matches the first Failure case.
4. **Remaining Failure instances** match the second Failure case.
5. **null** is handled by case null.

Because Outcome has only two subtypes, Success and Failure, both are fully covered, and null also has an explicit branch, the switch expression is valid without default. Similarly, Priority has only LOW and HIGH, so priorityLabel() does not need default; however, it does not handle a null selector and will throw a NullPointerException if given null.

A record pattern with a **var value** component can bind a null value. The guard **value != null && !value.isBlank()** both prevents a null dereference error and expresses the data acceptance rule of the first branch. Exhaustiveness only requires having a branch for every structural type/state, and does not automatically validate the text of value.

## 8. Compile error example and how to fix it

The following snippet is **invalid code used to observe a compiler error**, and should not be merged into the runnable program above:

~~~java
sealed interface State permits Good, Bad {}
record Good(int amount) implements State {}
record Bad(String reason) implements State {}

static String guardedOnly(State state) {
    return switch (state) {
        case Good(int amount) when amount > 0 -> "positive";
        case Bad(var reason) -> "bad";
    };
}
~~~

**Why does it fail?** A value like **Good(0)** or **Good(-1)** does not match the guarded Good branch. Bad has a case, but Good is not completely covered. The compiler reports that the switch expression does not cover all input values, which may be phrased as:

~~~text
the switch expression does not cover all possible input values
~~~

It can be fixed by adding a general case after the guarded case:

~~~java
case Good(int amount) -> "non-positive";
~~~

Note that this is **adding a semantically valid handling branch**, not adding a dummy case just to pass the check. When business logic distinguishes positive and non-positive Good, both cases are necessary.

### Dominance and exhaustiveness are two separate checks

- **Exhaustiveness** asks: Is there any valid value **not** covered by any branch?
- **Dominance** asks: Is there any later case that **can never be selected** because an earlier case already covers its cases?

For example, if you place **case Good(var amount)** before **case Good(int amount) when amount > 0**, the second branch is completely overshadowed by the general case and can cause a compile error. A switch can be exhaustive and still have a dominance error; **both** must be satisfied.

## 9. What does the compiler actually know, and what does it not know?

The compiler can reason from static information:

- **Selector type:** an enum, a sealed hierarchy, or a broad type like Object.
- **Case labels:** enum constants, type patterns, record patterns, general branches, default, and case null.
- **Subtype and permits relationships:** which types are closed, which are still extensible, and which types are covered by a pattern.
- **Nested record patterns:** compatibility and totality of deconstruction for components, including non-matching cases.
- **Guards:** a case with an arbitrary guard is not implicitly treated as covering all values of the pattern.

The compiler **does not** replace checks for domain conditions such as valid strings, positive sizes, or business ordering; those must be enforced by code. The compiler also cannot predict every class-change scenario at runtime after compilation.

If you use **case default** for an Object selector, that is a way to cover types not handled by other patterns. For a completely closed sealed hierarchy, omitting default can be an advantage because when a new subtype is added and recompiled, a missing branch becomes a clear error.

## 10. Exhaustiveness and null

**Null is not a subtype of a sealed interface or enum.** Therefore, a switch that is exhaustive over a set of subtypes can still throw a NullPointerException when the selector is null if there is no matching case null. Do not confuse “covering every subtype” with “accepting every reference value including null”.

Establish a null strategy at the API boundary:

- If null is **invalid**, you can use Objects.requireNonNull() at the start of the method or accept the switch failure on null and document the contract clearly.
- If null has a meaning like “no result”, write an explicit **case null** and specify the return value.
- If the input is a record with a **null nested component**, that is different from a null selector. A deeply nested record pattern may not match even though the parent record is non-null; add a branch covering the parent record when needed.

Do not rely on default as an implicit guarantee that null is handled: with a pattern switch, a plain default does not replace case null for a null selector.

## 11. Exhaustiveness across version changes or separate compilation

Exhaustiveness is analyzed **at compile time**, based on the type definitions visible to the compiler. This is very helpful for maintenance:

1. Add an enum constant or a permitted subtype.
2. Recompile the classes containing the relevant switches.
3. If a switch is missing a case, the compiler points out where business logic needs review.
4. Update the branches and test all cases.

However, in multi-module deployments or when classes are compiled at different times, a switch previously considered exhaustive may encounter a new value that the older bytecode did not anticipate. Java's runtime mechanisms can report errors such as **MatchException** in situations where an exhaustive switch cannot find a matching branch. This is not a promise that compile-time analysis alone protects against all out-of-sync binary changes.

You should compile and deploy type-related components consistently, add tests for new subtypes, and watch for runtime errors when hierarchies change. Do not rely on default to mask version mismatches if the requirement is to review every case.

## 12. Common mistakes when evaluating exhaustiveness

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Writing only a **when**-guarded case for a subtype | Fails to cover the subtype when the guard is false | Add an appropriate unguarded case |
| Assuming naming a record in a case is enough | Nested record patterns may miss null sub-records | Add a branch for the remaining record cases |
| Adding default upfront for a sealed hierarchy | No warning received when a new subtype appears | Prefer specific cases if you want to enforce review |
| Placing a broad case before a narrow case | The narrow case is dominated | Move the guarded case first |
| Forgetting null | The switch may throw NullPointerException | Define the contract clearly and use case null if needed |
| Assuming every switch statement must be exhaustive | Confusing rules with traditional statements | Distinguish switch expression, pattern switch statement, and traditional switch statement |
| Assuming sealed closes all branches to infinite depth | A non-sealed branch can still have new descendants | Use a pattern covering the non-sealed branch or redesign the hierarchy |
| Assuming exhaustiveness proves validation | Data can still be business-invalid despite having a branch | Write separate guards/validation |
| Partially compiling after changing types | Older binaries may encounter a runtime mismatch | Compile and test dependencies consistently |

## 13. Practical checklist

When reviewing a switch, follow this sequence:

1. **Identify the selector type** and whether it is a switch expression or statement.
2. **List the valid type domain**: enum constants, permitted descendants of a sealed hierarchy, or an open domain like Object.
3. **Evaluate each case**: does the pattern cover the entire subtype or only part of it due to a guard or nested pattern?
4. **Look for gaps**: uncovered values, especially false guards, null sub-records, or new subtypes.
5. **Check dominance**: does any branch become unreachable because a broader branch precedes it?
6. **Define the null policy**: is there a case null or an explicit contract rejecting null?
7. **Test extending the type domain** when appropriate: add an enum constant or subtype in a test and confirm the compiler flags the switches that need updating.
8. **Run behavioral tests** for each branch, guard boundary values, null, and significant binary changes.

**Takeaway:** Exhaustiveness analysis is the compiler's ability to prove that a switch **covers enough value shapes according to types and patterns**. Sealed types and enums provide an analyzable type domain; record patterns and type patterns describe branches; guards can narrow branches; general cases or default fill the remainder when designed properly. Let the compiler catch missing branches and keep business validation explicit in code.