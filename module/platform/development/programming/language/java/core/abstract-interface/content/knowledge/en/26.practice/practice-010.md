# Completing an Integrated Example and Contract Test Suite

A Java API can combine a public interface, default methods, and a supporting abstract class. To ensure that different implementations still conform to the same contract, test the observable behavior of the interface on **each implementation**. A contract test suite gathers the shared conditions in one place and re-runs them for every implementation class.

This lesson builds a complete example of a text formatter. One class implements the interface directly; the other extends an abstract class to reuse a common workflow. Both run through a single test suite, and then dedicated tests verify each class's specific output.

## 1. The Contract to Test

The `TextFormatter` interface provides two operations:

- `format(String)` formats text. A `null` input is rejected with a `NullPointerException`; leading and trailing whitespace does not affect the result.
- `supports(String)` is a default method that returns `true` when the string is non-`null` and not empty after accounting for whitespace. For `null` or a whitespace-only string, the result is `false`.

The contract describes what callers are allowed to rely on; it does not require every implementation to produce the exact same string. For example, one formatter may return `Java`, while another returns `[JAVA]`. Both still satisfy the contract if they comply with the stated conditions.

The test suite will verify that each formatter:

1. Supports non-blank text.
2. Does not claim to support `null` or an empty string after removing whitespace.
3. Returns a non-`null` result for valid input.
4. Produces an equivalent result when inputs differ only by leading and trailing whitespace, including Unicode whitespace characters.
5. Has a consistent result when called again with the same input.
6. Handles whitespace-only strings consistently with empty strings.
7. Properly throws `NullPointerException` when `format` receives `null`.

These conditions apply to every implementation. Dedicated tests can add specific assertions about each class's formatting style.

## 2. Role of Each Component

```text
TextFormatter (public contract)
    ├── PlainTextFormatter (implements directly)
    └── AbstractTextFormatter (supporting class)
            └── BracketTextFormatter (extends)
```

`TextFormatter` is the type that client code depends on. The default method `supports` provides a small behavior that can be computed from the input without needing object state.

`AbstractTextFormatter` uses Template Method: the `format` method is `final`, validates the input, and normalizes whitespace before passing the rest to the `formatTrimmed` hook. Subclasses only decide how to present the normalized string.

`PlainTextFormatter` implements the interface directly to illustrate that the abstract class is optional. This class implements the rule of stripping leading and trailing whitespace on its own. Even though their implementation structures differ, both classes must pass the same contract test suite.

## 3. Runnable Integrated Example on Java 17+

Save all of the following code into a file named `FormatterContractDemo.java`. The auxiliary types are not declared `public`, so they can be placed in the same file as the main runner class.

```java
import java.util.Locale;
import java.util.Objects;

interface TextFormatter {
    String format(String input);

    default boolean supports(String input) {
        return input != null && !input.isBlank();
    }
}

abstract class AbstractTextFormatter implements TextFormatter {
    @Override
    public final String format(String input) {
        Objects.requireNonNull(input, "input");
        return formatTrimmed(input.strip());
    }

    protected abstract String formatTrimmed(String trimmedInput);
}

class PlainTextFormatter implements TextFormatter {
    @Override
    public String format(String input) {
        Objects.requireNonNull(input, "input");
        return input.strip();
    }
}

class BracketTextFormatter extends AbstractTextFormatter {
    @Override
    protected String formatTrimmed(String trimmedInput) {
        return "[" + trimmedInput.toUpperCase(Locale.ROOT) + "]";
    }
}

public class FormatterContractDemo {
    private static int checks;

    private static void check(boolean condition, String description) {
        checks++;
        if (!condition) {
            throw new AssertionError("Contract check failed: " + description);
        }
    }

    private static void expectThrows(
            Class<? extends Throwable> expected,
            Runnable action,
            String description) {
        try {
            action.run();
        } catch (Throwable actual) {
            check(expected.isInstance(actual),
                    description + " (wrong exception: " + actual + ")");
            return;
        }
        check(false, description + " (no exception thrown)");
    }

    private static void verifyContract(String name, TextFormatter formatter) {
        check(formatter.supports("Java"), name + " supports nonblank text");
        check(!formatter.supports(null), name + " does not support null");
        check(!formatter.supports(" \t "), name + " does not support blank text");

        String expected = formatter.format("Java");
        check(expected != null, name + " returns a non-null result");
        check(expected.equals(formatter.format(" Java ")),
                name + " ignores leading and trailing whitespace");
        check(expected.equals(formatter.format("\u2003Java\u2003")),
                name + " ignores Unicode edge whitespace");
        check(expected.equals(formatter.format("Java")), name + " is deterministic");
        check(formatter.format("   ").equals(formatter.format("")),
                name + " treats whitespace-only input like empty input");
        expectThrows(NullPointerException.class, () -> formatter.format(null),
                name + " rejects null input");

        System.out.println("PASS " + name + ": 9 contract checks");
    }

    public static void main(String[] args) {
        TextFormatter plain = new PlainTextFormatter();
        TextFormatter bracketed = new BracketTextFormatter();

        verifyContract("PlainTextFormatter", plain);
        verifyContract("BracketTextFormatter", bracketed);

        check("Java".equals(plain.format(" Java ")),
                "plain formatter's specific output");
        check("[JAVA]".equals(bracketed.format(" Java ")),
                "bracket formatter's specific output");

        System.out.println("Plain: " + plain.format(" Java "));
        System.out.println("Bracket: " + bracketed.format(" Java "));
        System.out.println("Contract suite passed: " + checks + " checks");
    }
}
```

Here, `strip()` (Java 11+) handles Unicode whitespace consistently with `String.isBlank()`, whereas `trim()` does not remove all Unicode whitespace characters. The test suite adds a case with `U+2003` (EM SPACE) at both ends to verify this.

Compile and run:

```text
javac -encoding UTF-8 FormatterContractDemo.java
java FormatterContractDemo
```

Expected output:

```text
PASS PlainTextFormatter: 9 contract checks
PASS BracketTextFormatter: 9 contract checks
Plain: Java
Bracket: [JAVA]
Contract suite passed: 20 checks
```

The test suite runs nine contract conditions for each formatter, totaling 18 shared checks, and then runs two specific output checks. If any condition fails, `check` throws `AssertionError` and the program stops with details of the failed check. This approach lets you run the example immediately with the JDK, without installing additional testing libraries.

## 4. Why Test Each Implementation?

Testing one class does not prove that every class conforming to the interface is correct. `PlainTextFormatter` may strip whitespace properly, while another implementation accidentally returns the input unchanged. If you only test the first class, the bug in the second class will go undetected.

The `verifyContract` call accepts a name and a `TextFormatter`, so the same test logic is reused for both objects. When adding a third implementation, simply create the object and call the same contract method:

```java
TextFormatter another = new AnotherTextFormatter();
verifyContract("AnotherTextFormatter", another);
```

The lines above are an illustrative snippet to add to the program; `AnotherTextFormatter` must be defined and satisfy the same contract before compiling.

You should run the contract test suite on every public implementation, including implementations from other modules or third parties if the project controls that testing. When adding a new default method to the interface, add the relevant conditions to the contract suite so that every implementation is checked against the same standard.

## 5. How Do Contract Tests and Implementation-Specific Tests Differ?

**Contract tests** verify general rules that callers are entitled to rely on. These rules should not depend on the internal details of a single class.

**Implementation-specific tests** verify the distinctive behavior that a particular class promises. In the example, the following two checks belong only to the concrete formatters:

- `PlainTextFormatter` returns `Java` when the input is `" Java "`.
- `BracketTextFormatter` returns `[JAVA]` for the same input.

You should not put a requirement such as "every formatter must return an uppercase string in square brackets" into the shared contract suite, because that would exclude valid formatters that have other purposes. Distinguish between what belongs to the interface and what belongs solely to a single implementation.

## 6. How Does an Abstract Class Help Maintain the Contract?

`AbstractTextFormatter` declares `format` as `final` so that subclasses cannot accidentally skip the `null` check and whitespace normalization steps. Subclasses only override `formatTrimmed`, which receives the normalized input.

This is a way of using Template Method to keep invariant steps in the base class. It is useful when multiple classes need to share a common workflow and differ only in one step. However, it does not by itself guarantee the entire interface contract: the hook method can still return `null` or produce an inappropriate result. The contract test suite still needs to verify the observable output.

In `PlainTextFormatter`, the rule is implemented directly in `format`. Repeating a small amount of code is intentional to illustrate the option of implementing the interface without extending an abstract class. In a real-world API, weigh the maintenance cost of the duplication against how necessary the supporting class is.

## 7. Extending to JUnit

In a larger project, you can move the same idea to JUnit 5 so that each condition is an independent test, easy to inspect in results and easy to integrate into CI. A common way to organize this is to create a base contract test class with a factory method that supplies the instance under test, and then create a subclass for each implementation. The shared tests are inherited and run separately for each class.

Example structure:

```text
src/
  main/java/
    TextFormatter.java
    AbstractTextFormatter.java
    PlainTextFormatter.java
    BracketTextFormatter.java
  test/java/
    TextFormatterContractTest.java
    PlainTextFormatterTest.java
    BracketTextFormatterTest.java
```

The contract test class in JUnit places the assertions for `supports`, `null` handling, input normalization, and consistency in one place. Each concrete test class provides its formatter via a factory method or constructor. The dedicated tests for the `Java` and `[JAVA]` outputs remain in the corresponding implementation's test class.

Whether you use a custom-written harness or JUnit, the principle remains the same: the same set of conditions must run on every implementation, while specific details must be tested separately. The harness in this example is a standalone version that can be compiled and run immediately without external tool dependencies.

## 8. Common Mistakes

- **Testing only the supporting class:** a class that implements the interface directly can still violate the contract.
- **Testing internal details:** checking how many times a hook is called or what value an internal field holds often couples tests to structure rather than public behavior.
- **Putting specific output into the shared contract:** requiring every implementation to produce the same kind of string makes the contract overly restrictive if the interface only promises general properties.
- **Ignoring edge cases:** `null`, empty strings, whitespace-only strings, and inputs with leading or trailing whitespace often uncover contract bugs.
- **Not updating the test suite when the contract changes:** if you add a default method or change an input rule, update the shared tests and re-run them on all implementations.
- **Looking only at the number of passing tests:** tests must check meaningful conditions; a series of assertions repeating the same behavior is no substitute for contract coverage.

## 9. Workflow for Completing an Integrated Example

1. Identify the public conditions that every implementation must follow.
2. Place the contract in the interface; use default methods only for appropriate shared behavior.
3. Provide an abstract class when there is a genuinely shared implementation workflow, and allow classes to implement the interface directly when needed.
4. Write a test suite that takes the interface as its input type, without depending on concrete classes.
5. Run the contract suite for each implementation, then add dedicated tests for specific behavior.
6. Compile, run the tests, and verify the actual output before including the example in documentation.

A complete integrated example needs to demonstrate both the design and how to verify that design. The interface defines the behavior that client code can expect; the abstract class supports reusing common steps; and the contract test suite confirms that every implementation upholds those public guarantees.
