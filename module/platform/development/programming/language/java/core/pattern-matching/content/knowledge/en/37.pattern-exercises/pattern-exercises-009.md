# Writing Tests for Every Subtype in Java Pattern Matching

**Topic:** Java Core Pattern Matching — Comprehensive Practice. This article uses **Java 21 or later**, the version where **record patterns** (JEP 440) and **pattern matching for switch** (JEP 441) became standard features. The goal is to build a test suite that **does not miss any subtype**, while also verifying valid branches, boundary data, guards, nested records, null components, and null selectors.

## 1. What Does “Testing Every Subtype” Mean?

When an application represents multiple request types using a parent interface, such as **Message**, two kinds of omissions are often conflated:

1. **Missing handling branch:** Production code has no case that accepts a subtype. With a sealed hierarchy and a switch expression without a default, the compiler can detect this error.
2. **Missing behavior tests:** Production has a case for the subtype, but the internal logic may return the wrong result, mishandle null data, skip a false guard, call the wrong service, or mutate state incorrectly. The compiler **does not prove** those behaviors are correct.

Therefore, a good strategy uses **two layers of protection**:

- **Compile-time:** Declare a closed type domain with a sealed interface, use an exhaustive switch expression, and do not add a default just to hide unhandled subtypes.
- **Runtime tests:** Provide test data for **each subtype**, along with multiple meaningful value partitions; compare **actual against expected**, and check exceptions and side effects when present.

A case declared in a switch is **not proof** that the code in that case has been executed in a test. Similarly, merely creating one instance of a subtype in a test is **not proof** that all branches and conditions of that subtype have been verified.

### Setting Clear Completion Criteria

For a model consisting of **Created**, **Updated**, and **Deleted**, a minimal test suite can guarantee:

- Each direct subtype **has at least one fixture** sent to the handler.
- Each subtype has a **happy path** and at least one **failure/edge case** corresponding to the contract.
- Branches with guards must test both **true** and **false**.
- Nested record patterns must test both an **existing child record** and a **null child record** if the model allows it.
- A null selector must have its own test according to the API contract.
- A change that adds a subtype must expose the update requirement at compile time or in the fixture-set check.
- Outputs/exceptions/side effects are asserted, rather than merely recording that the code ran through.

This is a **business-meaningful** test plan, distinct from merely chasing a high line-coverage percentage.

## 2. Test Model: Three Subtypes and Nested Records

Define the Message type:

~~~java
sealed interface Message permits Created, Updated, Deleted {}

record Address(String city) {}
record User(String name, Address address) {}

record Created(long id, User user) implements Message {}
record Updated(long id, String label) implements Message {}
record Deleted(long id) implements Message {}
~~~

**This is the model declaration snippet**; the complete runnable code is in section 6.

The three direct subtypes are records, so they are all implicitly final. Inside **Created** there is a **User** record, which in turn contains **Address**. Because these records do not validate data in their constructors, combinations such as **new Created(1, null)** or **new User("An", null)** still exist and need to be tested.

Business assumptions of the example:

| Subtype | Succeeds when | Success result | Invalid result |
| --- | --- | --- | --- |
| **Created** | positive id, User exists, non-blank name, Address exists, non-blank city | **CREATE:id:name@city** | **REJECT:created** |
| **Updated** | positive id, non-blank label | **UPDATE:id:label** | **REJECT:updated** |
| **Deleted** | positive id | **DELETE:id** | **REJECT:deleted** |
| **Null selector** | Invalid under the illustrative contract | No happy path | **REJECT:null** |

Every valid name, city, and label is **trimmed** when building the result string. Putting trim into the contract means tests must also check strings with leading/trailing whitespace.

**Convention:** In this article, invalid data is converted into a **REJECT** result string for easy observation. Production code may choose a sealed Result hierarchy or specialized exceptions; not every project should be forced to return a String.

## 3. Writing an Exhaustive Handler for Compiler Assistance

A clear implementation of the handler:

~~~java
static String dispatch(Message message) {
    return switch (message) {
        case Created(long id, User(String name, Address(String city)))
                when id > 0 && nonBlank(name) && nonBlank(city) ->
                "CREATE:" + id + ":" + name.trim() + "@" + city.trim();
        case Created(var id, var user) -> "REJECT:created";

        case Updated(long id, String label)
                when id > 0 && nonBlank(label) ->
                "UPDATE:" + id + ":" + label.trim();
        case Updated(var id, var label) -> "REJECT:updated";

        case Deleted(long id) when id > 0 -> "DELETE:" + id;
        case Deleted(var id) -> "REJECT:deleted";

        case null -> "REJECT:null";
    };
}
~~~

The snippet above is **the core extracted from the program in section 6**. The **nonBlank** helper is declared in the complete version.

Key points:

1. **Created with a nested record pattern** only matches structures that have User and Address to deconstruct. If User or Address is null, the valid branch does not match.
2. **A null name/city String** can be bound in a record pattern under the rules for unconditional component patterns; the nonBlank helper must check for null itself before calling isBlank.
3. **when** separates valid data from invalid data. When the guard is false, the switch continues to the unguarded case of the same subtype.
4. **Created(var id, var user)** ensures every remaining Created has a handling path, including null child records.
5. **Updated** and **Deleted** also have their own valid and fallback case pairs, enabling tests for both sides of the guard.
6. **case null** handles a null selector. If case null is omitted, subtype coverage can still be complete, but a null selector will have a different policy.
7. **No default**. If a new permitted subtype is added to Message and recompiled, the compiler will report that the switch expression is not exhaustive.

### Do Not Use default to Hide Missing Cases

~~~java
// Anti-pattern if each new subtype must undergo business review.
return switch (message) {
    case Created c -> handleCreated(c);
    case Updated u -> handleUpdated(u);
    default -> "REJECT:unknown";
};
~~~

When Deleted or a new subtype is added, default can let the code still compile while the new subtype gets lumped into “unknown”. With a closed domain and a clear requirement that **every command must be handled individually**, that approach loses the compiler's benefit.

Even when declared exhaustive, tests still need to verify whether **handleCreated**, **handleUpdated**, and the other cases perform the exact required behavior.

## 4. Designing a Test Matrix by Subtype and Data Partitions

Before writing test code, identify the values likely to produce different execution paths.

### 4.1. Created: Nested Structure and Guards

| Test case | Input | Expected result |
| --- | --- | --- |
| created-valid | Created(1, User(" An ", Address(" Hue "))) | **CREATE:1:An@Hue** |
| created-zero-id | Created(0, User("An", Address("Hue"))) | **REJECT:created** |
| created-null-user | Created(1, null) | **REJECT:created** |
| created-null-name | Created(1, User(null, Address("Hue"))) | **REJECT:created** |
| created-null-address | Created(1, User("An", null)) | **REJECT:created** |
| created-null-city | Created(1, User("An", Address(null))) | **REJECT:created** |
| created-blank-city | Created(1, User("An", Address(" "))) | **REJECT:created** |

These tests not only represent the Created subtype, they also check **each nested record level**. For example, **Created(1, null)** differs from **Created(1, User("An", null))**: both are rejected, but the cause and the pattern being exercised are not the same.

If a real API must return detailed error codes per field, expand expected to **the failing field name** rather than just REJECT:created. In this case study, a uniform result is an intentional contract choice to focus on subtype coverage.

### 4.2. Updated: Guard and Null Component

| Test case | Input | Expected result |
| --- | --- | --- |
| updated-valid | Updated(2, " Nova ") | **UPDATE:2:Nova** |
| updated-blank | Updated(2, " ") | **REJECT:updated** |
| updated-null-label | Updated(2, null) | **REJECT:updated** |
| updated-zero-id | Updated(0, "X") | **REJECT:updated** |

If only a valid Updated is tested, the **case Updated(var id, var label)** branch has not been exercised. Blank and null data are also not equivalent: both are rejected, but they can hit different check points.

### 4.3. Deleted and Null Selector

| Test case | Input | Expected result |
| --- | --- | --- |
| deleted-valid | Deleted(3) | **DELETE:3** |
| deleted-bad-id | Deleted(-1) | **REJECT:deleted** |
| selector-null | null | **REJECT:null** |

**Deleted** has no reference component, yet still needs tests for valid and invalid ids. The null selector test does not belong to any subtype: it independently verifies **the handler's input contract**.

### 4.4. Why Not Test Only One Value per Subtype?

A test that checks “there is at least one object of each subtype” verifies **presence in the fixtures**, but fails to catch bugs such as:

- A guard written as **id >= 0** instead of **id > 0**.
- A body that forgets to trim name/city.
- Code that calls **name.trim()** when name is null.
- A null nested Address not being handled.
- A branch returning **DELETE** for Updated due to a copy/paste mistake.
- A fallback for Deleted returning the wrong result.

Therefore, you should test by **subtype × meaningful behavior partitions**, not just by subtype count.

## 5. Essential Components of a Test Harness

A simple test harness without external libraries can represent each case as a record:

~~~java
record TestCase(String name, Message input, String expected) {}
~~~

Each TestCase holds three pieces of information:

- **name:** a stable name to identify which case failed;
- **input:** the Message value to pass into the handler, which may be null;
- **expected:** the exact output according to the contract.

The fact that **TestCase** is a record does not forbid null in the input component. Thus **new TestCase("selector-null", null, "REJECT:null")** is valid. When stored in a list, the TestCase itself is a non-null object; do not confuse this with **List.of(null)**, which is rejected.

Comparing results:

~~~java
String actual = dispatch(test.input());
if (!Objects.equals(test.expected(), actual)) {
    throw new AssertionError(test.name()
            + " expected=" + test.expected()
            + ", actual=" + actual);
}
~~~

A test must **actually fail** if expected differs from actual, rather than merely printing the output. **Objects.equals** handles null results safely; even though all expected values in the example are non-null Strings, it remains a clear comparison method.

When a test fails, printing **the test name, expected, and actual** helps quickly locate the failing condition. When using JUnit, assertEquals can be used so the framework reports results automatically.

## 6. Complete, Standalone, Runnable Java 21 Program

Save the entire following program in **SubtypeCoverageTestDemo.java**. It uses **sealed Message**, **nested record patterns**, **guards**, **null**, a list of 14 test cases, and an additional check on the set of direct subtypes.

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class SubtypeCoverageTestDemo {
    sealed interface Message permits Created, Updated, Deleted {}

    record Address(String city) {}
    record User(String name, Address address) {}

    record Created(long id, User user) implements Message {}
    record Updated(long id, String label) implements Message {}
    record Deleted(long id) implements Message {}

    record TestCase(String name, Message input, String expected) {}

    static boolean nonBlank(String value) {
        return value != null && !value.isBlank();
    }

    static String dispatch(Message message) {
        return switch (message) {
            case Created(long id, User(String name, Address(String city)))
                    when id > 0 && nonBlank(name) && nonBlank(city) ->
                    "CREATE:" + id + ":" + name.trim() + "@" + city.trim();
            case Created(var id, var user) -> "REJECT:created";

            case Updated(long id, String label)
                    when id > 0 && nonBlank(label) ->
                    "UPDATE:" + id + ":" + label.trim();
            case Updated(var id, var label) -> "REJECT:updated";

            case Deleted(long id) when id > 0 -> "DELETE:" + id;
            case Deleted(var id) -> "REJECT:deleted";

            case null -> "REJECT:null";
        };
    }

    static List<TestCase> testCases() {
        var cases = new ArrayList<TestCase>();

        cases.add(new TestCase("created-valid",
                new Created(1, new User(" An ", new Address(" Hue "))),
                "CREATE:1:An@Hue"));

        cases.add(new TestCase("created-zero-id",
                new Created(0, new User("An", new Address("Hue"))),
                "REJECT:created"));

        cases.add(new TestCase("created-null-user",
                new Created(1, null),
                "REJECT:created"));

        cases.add(new TestCase("created-null-name",
                new Created(1, new User(null, new Address("Hue"))),
                "REJECT:created"));

        cases.add(new TestCase("created-null-address",
                new Created(1, new User("An", null)),
                "REJECT:created"));

        cases.add(new TestCase("created-null-city",
                new Created(1, new User("An", new Address(null))),
                "REJECT:created"));

        cases.add(new TestCase("created-blank-city",
                new Created(1, new User("An", new Address(" "))),
                "REJECT:created"));

        cases.add(new TestCase("updated-valid",
                new Updated(2, " Nova "),
                "UPDATE:2:Nova"));

        cases.add(new TestCase("updated-blank",
                new Updated(2, " "),
                "REJECT:updated"));

        cases.add(new TestCase("updated-null-label",
                new Updated(2, null),
                "REJECT:updated"));

        cases.add(new TestCase("updated-zero-id",
                new Updated(0, "X"),
                "REJECT:updated"));

        cases.add(new TestCase("deleted-valid",
                new Deleted(3),
                "DELETE:3"));

        cases.add(new TestCase("deleted-bad-id",
                new Deleted(-1),
                "REJECT:deleted"));

        cases.add(new TestCase("selector-null",
                null,
                "REJECT:null"));

        return cases;
    }

    public static void main(String[] args) {
        int passed = 0;
        Set<Class<?>> exercised = new HashSet<>();

        for (TestCase test : testCases()) {
            String actual = dispatch(test.input());
            if (!Objects.equals(test.expected(), actual)) {
                throw new AssertionError(test.name()
                        + " expected=" + test.expected()
                        + ", actual=" + actual);
            }

            if (test.input() != null) {
                exercised.add(test.input().getClass());
            }
            passed++;
            System.out.println("PASS " + test.name() + " => " + actual);
        }

        Class<?>[] direct = Message.class.getPermittedSubclasses();
        for (Class<?> subtype : direct) {
            if (!exercised.contains(subtype)) {
                throw new AssertionError(
                        "Missing test data for " + subtype);
            }
        }

        System.out.println("COVERED: " + exercised.size()
                + "/" + direct.length + " direct subtypes");
        System.out.println("ALL: " + passed + " tests passed");
    }
}
~~~

### 6.1. Compiling and Running

Using **JDK 21 or newer**, in the directory containing the file:

~~~bash
javac SubtypeCoverageTestDemo.java
java SubtypeCoverageTestDemo
~~~

**Exact output:**

~~~text
PASS created-valid => CREATE:1:An@Hue
PASS created-zero-id => REJECT:created
PASS created-null-user => REJECT:created
PASS created-null-name => REJECT:created
PASS created-null-address => REJECT:created
PASS created-null-city => REJECT:created
PASS created-blank-city => REJECT:created
PASS updated-valid => UPDATE:2:Nova
PASS updated-blank => REJECT:updated
PASS updated-null-label => REJECT:updated
PASS updated-zero-id => REJECT:updated
PASS deleted-valid => DELETE:3
PASS deleted-bad-id => REJECT:deleted
PASS selector-null => REJECT:null
COVERED: 3/3 direct subtypes
ALL: 14 tests passed
~~~

**How to read this:** The 14 PASS lines prove that each **input / expected** pair matches **the current implementation**. The COVERED line proves that the fixtures sent to dispatch include all of **Created, Updated, Deleted** in the set of permitted direct types. It **does not** assert branch coverage or that every data combination has been tested.

If any result is wrong, the program throws an **AssertionError** at the corresponding case and does not print the final summary line normally. If a fixture for a subtype in the sealed hierarchy is missing, the getPermittedSubclasses check loop also throws an AssertionError.

### 6.2. Why Use ArrayList for Test Cases?

The list holds non-null **TestCase records**, in which an input component may be null. Using ArrayList makes adding each case clear. Writing **List.of(new TestCase(...), ...)** is also valid because each TestCase **element** is non-null. However, **List.of(null)** is not allowed.

An unsafe pattern is directly creating **List.of(new Created(...), null)** as the input list; the List.of call will throw a NullPointerException before testing the handler. In a null-selector test, place null **inside a TestCase component** or use a collection that permits null.

## 7. Checking the Subtype Set with getPermittedSubclasses()

Java provides **Class.getPermittedSubclasses()** to retrieve the set of classes/interfaces directly permitted to extend or implement a sealed type. In the example:

~~~java
Class<?>[] direct = Message.class.getPermittedSubclasses();
~~~

With Message having three records **Created**, **Updated**, **Deleted**, the returned array is the list of three direct subtypes. Therefore, the test can compare against the subtypes that actually appear in the data:

~~~java
Set<Class<?>> exercised = new HashSet<>();

for (TestCase test : testCases()) {
    if (test.input() != null) {
        exercised.add(test.input().getClass());
    }
}

for (Class<?> subtype : Message.class.getPermittedSubclasses()) {
    if (!exercised.contains(subtype)) {
        throw new AssertionError("Missing test data for " + subtype);
    }
}
~~~

This is a **fixture presence test**, not a measurement of the number of cases in the switch and not a measurement of line coverage.

### 7.1. When Adding a New Subtype

If the hierarchy is updated to:

~~~java
// Another illustrative version; do not overwrite the demo without
// simultaneously updating permits, dispatch code, and tests.
sealed interface Message permits Created, Updated, Deleted, Archived {}
record Archived(long id) implements Message {}
~~~

Two checks can remind you of the change:

1. **Compiler:** If dispatch is still a switch expression without default and is missing the Archived case, the build will report **not exhaustive**.
2. **Fixture coverage test:** After you add the Archived branch so the code compiles, if you **have not yet added test data for Archived**, the getPermittedSubclasses comparison will throw an AssertionError because an Archived instance has never been run.

This complementary mechanism helps prevent the situation where you fix the code to clear compile errors and then **forget to test the new subtype**.

### 7.2. Important Limitations of the Reflection Check

- **Only direct permitted types:** getPermittedSubclasses does not recursively traverse all leaf subtypes. If a permitted subtype is itself sealed and has multiple child branches, you must define a policy to cover the leaves or perform a controlled tree traversal.
- **non-sealed branches:** Many subclasses may appear later, so the direct permitted set cannot be treated as all concrete descendants that will ever exist.
- **Actual class differs from permitted type:** If a permitted subtype is an intermediate sealed/abstract class, **input.getClass()** may be another descendant. Comparing directly by Class as in the demo is only suitable when the permitted subtypes themselves are the final records being instantiated.
- **Having a representative fixture does not mean full branch coverage:** With only one valid Created input, reflection still reports Created as exercised even if the REJECT:created branch never ran.
- **Does not replace behavior tests:** You must verify expected outputs, exceptions, and side effects rather than just Set<Class<?>>.

Therefore, name this check **direct-subtype fixture coverage**, and do not call it “100% branch coverage”.

## 8. Negative Testing: The Compiler Must Catch a Missing Subtype

Consider another type to illustrate:

~~~java
// Negative code: intentionally fails to compile to demonstrate exhaustiveness.
sealed interface Event permits Added, Changed, Removed {}

record Added() implements Event {}
record Changed() implements Event {}
record Removed() implements Event {}

class MissingSubtypeExample {
    static String classify(Event event) {
        return switch (event) {
            case Added a -> "ADDED";
            case Changed c -> "CHANGED";
        };
    }
}
~~~

**This code snippet intentionally does not compile/run.** The switch expression is missing the branch for Removed. The Java 21+ compiler may report:

~~~text
the switch expression does not cover all possible input values
~~~

The proper fix is to add the branch for Removed with the corresponding business behavior, **not to add a default that removes the requirement to review the subtype**.

### Exhaustiveness Does Not Eliminate All Bugs

You could write:

~~~java
case Removed r -> "ADDED";
~~~

The switch is then exhaustive yet still **produces the wrong result**. Only a test with input Removed and expected "REMOVED" catches this bug. That is why both the compiler **and** runtime tests are needed.

When a guard is present:

~~~java
case Deleted(long id) when id > 0 -> "DELETE:" + id;
~~~

this branch does **not** handle Deleted with id <= 0. An unguarded case for the same subtype such as **case Deleted(var id) -> "REJECT:deleted"** ensures a path exists for the remaining values and provides a target for negative tests.

**Note on binaries:** Exhaustiveness analysis is based on the classes present at **compile time**. If a module or library is swapped after the consumer was compiled, the old binary may encounter a new subtype it has never seen. When no branch matches, a switch pattern can throw **MatchException** at runtime. Dependent modules must be rebuilt and deployed consistently.

## 9. Writing the Same Test Suite with JUnit 5

When bringing code into a real project, **JUnit 5** provides clear per-case reporting and CI integration. The following snippet assumes **JUnit Jupiter + junit-jupiter-params** are declared in test dependencies and JUnit Platform is enabled in the build.

Create **SubtypeCoverageJUnitTest.java** in the test source set **in the same package** as SubtypeCoverageTestDemo. The code reuses testCases() and dispatch() from the demo. If the demo is moved into its own package, add the appropriate package/import declarations and adjust visibility accordingly.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class SubtypeCoverageJUnitTest {

    static Stream<Arguments> samples() {
        return SubtypeCoverageTestDemo.testCases().stream()
                .map(tc -> Arguments.of(
                        tc.name(), tc.input(), tc.expected()));
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("samples")
    void dispatchMatchesExpected(
            String label,
            SubtypeCoverageTestDemo.Message input,
            String expected) {

        assertEquals(expected,
                SubtypeCoverageTestDemo.dispatch(input),
                label);
    }

    @Test
    void fixturesCoverEveryDirectSubtype() {
        Set<Class<?>> exercised = SubtypeCoverageTestDemo
                .testCases().stream()
                .map(tc -> tc.input())
                .filter(Objects::nonNull)
                .map(Object::getClass)
                .collect(Collectors.toSet());

        for (Class<?> subtype : SubtypeCoverageTestDemo
                .Message.class.getPermittedSubclasses()) {
            assertTrue(exercised.contains(subtype),
                    "Missing fixture for " + subtype.getSimpleName());
        }
    }
}
~~~

**This code is for a project that already has JUnit 5** and cannot be compiled with the JDK alone without adding dependencies. The **SubtypeCoverageTestDemo.java program in section 6** is the complete standalone example to run directly with javac/java.

Benefits of parameterized tests:

- Each case name is displayed individually in the test report.
- You only need to add a TestCase to the matrix for JUnit to generate another run.
- Assertion logic stays in one place, reducing copy/paste.
- A separate test detects direct subtypes not yet present in the fixtures.

**Note on test discovery:** JUnit picks up tests in the test source set when the build is configured properly. With Gradle, you need appropriate dependencies, useJUnitPlatform() where required, and a Java 21 toolchain/source level. Actual Maven/Gradle commands in a real project may vary; do not mistake an annotated test file for a guarantee that it is actually being executed by CI.

### 9.1. When to Use a Separate @Test Instead of @ParameterizedTest?

Use **@ParameterizedTest** for multiple inputs going through the same processing logic; use a separate **@Test** if you need to check:

- Specific exceptions thrown by a constructor or service;
- Side effects in a database/repository;
- Transaction rollback;
- A stateful sequence of actions, such as Created → Updated → Deleted;
- Reflection-level subtype set checks;
- Concurrency, retries, or idempotency.

A meaningful test must verify **post-command state**, not just a returned String, if the real method has side effects.

## 10. Testing null, Guards, and Record Patterns with Exact Java Semantics

### 10.1. Null Selector

With a pattern switch, null needs an explicit policy. The demo uses:

~~~java
case null -> "REJECT:null";
~~~

If case null is removed, the switch may still be exhaustive over the three subtypes **Created**, **Updated**, **Deleted**, but a null selector can throw NullPointerException. The **selector-null** test helps detect contract changes during refactoring.

**Do not assume a plain default will catch null.** Depending on syntax and label order, case null must be handled explicitly or via an explicit rejection policy such as Objects.requireNonNull before the switch.

### 10.2. Null String Components

The record pattern **Updated(long id, String label)** can bind a null label when the component type is String as an unconditional pattern. Therefore, the helper:

~~~java
static boolean nonBlank(String value) {
    return value != null && !value.isBlank();
}
~~~

uses short-circuiting so it does not call isBlank on null. The **updated-null-label** test confirms the handler returns REJECT instead of throwing an NPE. Meanwhile, **updated-blank** catches the business error when label contains only whitespace.

### 10.3. Null Nested Records

The pattern:

~~~java
Created(long id, User(String name, Address(String city)))
~~~

requires the User and Address components to be deconstructible records. If User or Address is null, the nested pattern **does not match**; the **case Created(var id, var user)** branch takes over the remaining cases.

Tests must include all of:

- **new Created(1, null)**;
- **new Created(1, new User("An", null))**;
- **new Created(1, new User(null, new Address("Hue")))**;
- **new Created(1, new User("An", new Address(null)))**.

They all return REJECT:created in the example, but follow different matching and guard paths. If the application needs to return field-specific error codes, tests must verify each field path.

### 10.4. Guard False vs. Exception

When **when** returns false, the switch continues trying subsequent matching cases. When a guard **throws an exception**, the switch terminates abnormally; it does not treat the guard as false and ignore the error.

Example of what not to write:

~~~java
// Anti-pattern: may call isBlank on a null String.
case Updated(var id, var label)
        when label.isBlank() -> "REJECT:updated";
~~~

If label is null, the guard throws an NPE. Use a null-safe helper or check explicitly inside the case body according to the contract.

### 10.5. Case Ordering and Dominance

In the handler, the unguarded **case Updated(var id, var label)** branch must come **after** the guarded Updated case. If the general branch is placed first, the narrower branch can be dominated and the compiler reports it as unreachable.

Testing multiple inputs helps catch wrong business ordering; the compiler prevents some structural dominance errors, but does not know which expected output is right for the domain.

## 11. Coverage at Three Levels: Subtype, Branch, Business Behavior

To avoid being misled by a single coverage number, separate the questions:

| Level | Question | Method |
| --- | --- | --- |
| **Subtype fixture coverage** | Is there at least one tested instance for every direct subtype? | Check getPermittedSubclasses against the fixture set |
| **Branch/condition coverage** | Are case paths and guard true/false outcomes executed? | Test matrix, coverage report, condition checks |
| **Behavior coverage** | Do results, state, and exceptions match the contract? | assertEquals, assertThrows, state assertions |

A test suite can achieve **3/3 subtypes** yet still miss the REJECT branch of Updated. Conversely, 100% branch coverage in a few functions does not prove every data state of the application has been tested.

For large hierarchies, it is unnecessary to run **the Cartesian product of every value**. Choose partitions by:

1. subtype;
2. valid and invalid branches;
3. boundary conditions, e.g., id = -1, 0, 1;
4. null at each record level;
5. interactions that genuinely change behavior;
6. past bugs or high-probability failure modes.

**Property-based tests** can supplement this by generating many values according to invariants, such as “every Created with a non-positive id is rejected”. However, data generators must understand each subtype's structure, and tests must still assert meaningful expected behavior. Pure random generation does not guarantee every subtype or every guard has been exercised.

## 12. Testing Exceptions, Constructor Validation, and Side Effects

The demo intentionally uses **raw** records without constructor validation so that cases like Created(null user) and Updated(null label) can be tested at the handler. In another domain, a compact constructor might reject bad data **before the handler is ever called**:

~~~java
// Alternative model; do not merge directly into the section 6 demo.
record StrictDeleted(long id) {
    StrictDeleted {
        if (id <= 0) {
            throw new IllegalArgumentException("id");
        }
    }
}
~~~

With that model, testing **new StrictDeleted(0)** must use assertThrows on the constructor. Do not try to pass an object that the constructor already rejects into the handler: the test will fail at data creation, before the dispatch logic.

### 12.1. Two Tests with Different Responsibilities

- **Constructor test:** Invalid domain values are rejected with the right exception type.
- **Handler test:** A validly constructed command/event is processed properly and produces the expected result or side effect.

If using a factory that returns a Result instead of throwing an exception, tests should verify the Result subtype and error code, rather than forcing every validation mechanism to throw exceptions.

### 12.2. When the Handler Is Stateful

For a command handler that modifies a data store, each subtype should test:

- returned response;
- before/after state;
- repository call counts;
- retry behavior;
- secondary actions (audit/event) if required;
- no side effects when the command is rejected.

An exhaustive switch knows nothing about transactions, permissions, or network connections. Testing every subtype **does not replace** integration testing when correctness depends on infrastructure.

## 13. When a Hierarchy Has Intermediate or Non-Sealed Subtypes

The demo only has direct final record subtypes. If the hierarchy is more complex:

~~~java
// Illustrates an extended structure; do not merge into the demo.
sealed interface Input permits UserInput, SystemInput {}

sealed interface UserInput extends Input permits SignIn, SignOut {}

record SignIn(String name) implements UserInput {}
record SignOut(String name) implements UserInput {}

non-sealed interface SystemInput extends Input {}
~~~

**getPermittedSubclasses()** on Input only returns the direct subtypes **UserInput** and **SystemInput**; it does not automatically list SignIn/SignOut or any future implementations of SystemInput. A test suite that only compares actual runtime classes against those two direct types can **report false misses**.

In such hierarchies, clearly design the target:

- Cover **each direct branch** at the dispatch level;
- Cover **the leaf subtypes** recognized in the product;
- Or cover plugins/implementations registered at runtime.

With a **non-sealed** branch, new implementations can be added outside the original module. In that case, permitted enumeration alone cannot prove “every class existing in the world” is tested. A registry, contract tests, or extension-mechanism discovery may be more appropriate.

**Core limitation:** “Every subtype” must be defined by **the type domain and product boundary**. In a closed sealed hierarchy of final records, enumeration is straightforward. In an open plugin system, a different testing strategy is needed.

## 14. Integrating into the Build and CI Pipeline

A workflow for a Java 21 project:

1. **Lock Java source/toolchain to 21+:** Record patterns and switch patterns are standard from Java 21 onward, without needing enable-preview.
2. **Clean build:** Recompile all modules containing the sealed hierarchy so the compiler catches switches missing a subtype.
3. **Run the test matrix:** Use a dedicated test for each meaningful input partition.
4. **Run the fixture coverage test:** Compare the direct subtype set against the fixtures or explicitly declared test suite.
5. **Inspect branch coverage:** Confirm guard true/false paths, fallbacks, and throw paths are exercised.
6. **Run integration tests:** If subtypes have side effects, verify transactions, permissions, repositories, and event emission.
7. **Keep the pipeline strict:** Do not use default to suppress compiler errors when new commands require review.
8. **Review model and test changes in the same pull request:** Add the subtype, handler case, test data, and contract docs together.

With Gradle or Maven, declare JUnit 5 and configure test discovery accordingly. Exact run commands depend on the project; for example, a Gradle wrapper may use:

~~~bash
./gradlew clean test
~~~

Or Maven in a project with compatible test plugins:

~~~bash
mvn clean test
~~~

These commands are for **projects with a configured build and JUnit**, not for running the standalone demo file directly. To run the demo file, use javac/java as shown in section 6.

### Checking Test Names in CI

A name like **created-null-address** is more helpful than **testCase7** when a pipeline fails. A common convention is **subtype-state/condition**, for example:

- created-valid;
- created-null-user;
- updated-zero-id;
- deleted-bad-id.

When a test fails, you can immediately pinpoint which subtype and data partition are affected.

## 15. Common Mistakes When Writing Subtype Tests

**Mistake 1 — Testing only one object per subtype.** This may satisfy fixture presence while missing false guards, null components, and exceptions.

**Mistake 2 — Trusting only the compiler.** The compiler only checks exhaustiveness/dominance; it does not confirm that case bodies return the right values or perform the right side effects.

**Mistake 3 — Always adding default to switch.** Default lets new subtypes silently fall through to a fallback; compile-time checks stop reminding you where to review.

**Mistake 4 — Looking only at line coverage.** The same line may be executed while missing scenarios that produce wrong results, especially with logical conditions.

**Mistake 5 — Assuming case null tests all null components.** A null selector and a null nested component are different execution paths.

**Mistake 6 — Testing unconstructable data.** If a constructor forbids negative ids, creating the invalid object fails before the handler; place that test on the constructor/factory instead.

**Mistake 7 — Using List.of(null) for fixtures.** The test fails during collection creation rather than testing the handler. Wrap null inside a TestCase record or choose a collection that allows null.

**Mistake 8 — Over-interpreting reflection coverage.** getPermittedSubclasses only gives direct subtypes; for nested or non-sealed hierarchies, a tailored policy is required.

**Mistake 9 — Not asserting actual.** Running every subtype and only printing output does not automatically catch regressions; you must have expected values and assertions.

**Mistake 10 — Neglecting test names and failure causes.** Clear case names and assertions reporting expected/actual significantly cut diagnosis time.

**Mistake 11 — Ignoring compatibility when adding a subtype.** Stale binaries or un-recompiled test modules can miss changes; dependent builds and deployments must stay consistent.

**Mistake 12 — Trying to run all meaningless combinations.** Testing too many redundant samples slows down CI and hurts maintainability. Choose partitions by business meaning, boundaries, and risk.

## 16. Code Review Checklist for Comprehensive Practice

- [ ] Are all subtypes belonging to the domain to be tested clearly listed?
- [ ] Do the sealed model and final/record subtypes fit the current architecture?
- [ ] Does the handler use an exhaustive switch expression without default where compile-time checking is needed?
- [ ] Is there at least one fixture for each direct subtype and a test checking the fixture set?
- [ ] Does each subtype have a happy path and key edge/failure paths?
- [ ] Are guards tested for both true and false, especially at boundary values?
- [ ] Do a null selector and null components of nested records have separate tests?
- [ ] Are expected outputs/exceptions/side effects asserted, not just calling the method?
- [ ] Do test case names help trace the subtype and failure condition?
- [ ] If a new subtype is added, do compilation, the fixture coverage test, and behavior tests force a full review?
- [ ] For non-sealed or multi-level hierarchies, is the coverage definition adjusted?
- [ ] Do tests use JDK 21+ and are they actually discovered/run by CI with the right framework?

**Conclusion:** To **write tests for every subtype**, you need more than one instance of each type. Combine a **sealed hierarchy + exhaustive switch** so the compiler catches missing branches, a **test matrix by subtype and data partitions** to verify behavior, and a **fixture coverage test** to warn when the model grows without test data. When records have null components, guards, nested subtypes, or side effects, add semantically accurate tests. A trustworthy suite proves **correct behavior**, not merely **branch presence**.
