# Testing an Abstract Class via a Minimal Concrete Subclass

You cannot directly create an object from an abstract class, yet you can still test the concrete methods defined in that class. A common approach is to create a **minimal concrete subclass** for testing: the subclass only provides the required implementation for the abstract methods, and then the test calls the inherited methods of the abstract class.

## 1. Why Is a Concrete Subclass Needed?

An abstract class can contain both types of methods:

- **Abstract methods:** declare only the contract, with no method body; a concrete subclass must implement all remaining abstract methods.
- **Concrete methods:** have a method body and can contain shared logic that needs to be tested directly.

Java does not allow writing `new AbstractFormatter()` if `AbstractFormatter` is abstract. Instead, create a subclass such as `TestFormatter extends AbstractFormatter`. This subclass makes the type instantiable and allows calling the concrete logic of the parent class.

Importantly, the test subclass should **fill in the minimal missing parts** and not override the concrete method you want to test. If it overrides that method, the test could inadvertently check the subclass's logic instead of the logic that actually resides in the abstract class.

## 2. Implementation Pattern

Suppose the abstract class provides a complete `format` method, but delegates content transformation to the abstract `transform` method:

```java
abstract class AbstractFormatter {
    public final String format(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        String cleaned = input.strip();
        if (cleaned.isBlank()) {
            throw new IllegalArgumentException("input must not be blank");
        }
        return "[" + transform(cleaned) + "]";
    }

    protected abstract String transform(String value);
}
```

`format` is a concrete method: it validates the input, trims leading and trailing whitespace, and adds brackets. The `transform` method is an extension point provided by a subclass. A test can use a simple, predictable implementation to verify the logic of `format`.

## 3. Compilable and Runnable Java 17+ Example

Save all of the following code to the file `AbstractClassTestDemo.java`. The program uses a small subclass along with custom-written assertion functions, so no external testing library is required.

```java
public class AbstractClassTestDemo {
    abstract static class AbstractFormatter {
        public final String format(String input) {
            if (input == null) {
                throw new IllegalArgumentException("input must not be null");
            }
            String cleaned = input.strip();
            if (cleaned.isBlank()) {
                throw new IllegalArgumentException("input must not be blank");
            }
            return "[" + transform(cleaned) + "]";
        }

        protected abstract String transform(String value);
    }

    // Minimal subclass for the test: only implements the abstract hook.
    static final class TestFormatter extends AbstractFormatter {
        @Override
        protected String transform(String value) {
            return "<" + value + ">";
        }
    }

    public static void main(String[] args) {
        AbstractFormatter formatter = new TestFormatter();

        assertEquals("[<hello>]", formatter.format("  hello  "), "trim và format");
        assertEquals("[<Java core>]", formatter.format(" Java core "), "nội dung thường");
        assertThrows(IllegalArgumentException.class,
                () -> formatter.format(null), "đầu vào null");
        assertThrows(IllegalArgumentException.class,
                () -> formatter.format(" \t "), "đầu vào chỉ có khoảng trắng");

        System.out.println("PASS: 4 checks");
    }

    private static void assertEquals(String expected, String actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected <" + expected
                    + "> but got <" + actual + ">");
        }
    }

    private static void assertThrows(
            Class<? extends RuntimeException> expectedType,
            Runnable action,
            String label) {
        try {
            action.run();
        } catch (RuntimeException actual) {
            if (expectedType.isInstance(actual)) {
                return;
            }
            throw new AssertionError(label + ": expected "
                    + expectedType.getSimpleName() + " but got "
                    + actual.getClass().getSimpleName(), actual);
        }
        throw new AssertionError(label + ": expected "
                + expectedType.getSimpleName() + " but no exception was thrown");
    }
}
```

Compile and run from the directory containing the file:

```shell
javac AbstractClassTestDemo.java
java AbstractClassTestDemo
```

Exact stdout:

```text
PASS: 4 checks
```

The four checks verify that `format` handles whitespace properly, preserves the content after passing through the hook, and rejects both `null` and whitespace-only strings. If any result is incorrect or an expected exception does not occur, the program throws `AssertionError` and terminates with an error instead of printing the PASS message.

## 4. What Is Being Tested?

In the line `AbstractFormatter formatter = new TestFormatter();`, the reference variable has the abstract class type, while the actual object is an instance of the concrete subclass. When `formatter.format(...)` is called, Java executes the concrete `format` method defined in `AbstractFormatter`. When that method calls `transform`, Java dispatches to the implementation in `TestFormatter`.

| Part | Role in the test |
| --- | --- |
| `AbstractFormatter.format` | Concrete logic to be tested: null check, string normalization, emptiness check, and result assembly. |
| `AbstractFormatter.transform` | Abstract extension point that every concrete subclass must implement. |
| `TestFormatter.transform` | Minimal, predictable implementation to allow object creation and provide a result to the concrete method. |
| `assertEquals` | Compares the actual value with the expected result. |
| `assertThrows` | Verifies that an operation throws the expected exception type. |

The type of the reference variable does not determine object instantiation; the concrete runtime class is the type actually created. However, declaring the variable with the abstract class type helps the test express the exact API that users of the parent class will see.

## 5. How to Apply This in JUnit 5

In a real-world project, you should use an existing testing framework such as JUnit 5 instead of custom-written assertion functions. Keep the same minimal subclass idea, and separate each case into its own test:

```java
@Test
void formatTrimsInputAndUsesTransformHook() {
    AbstractFormatter formatter = new TestFormatter();
    assertEquals("[<hello>]", formatter.format("  hello  "));
}

@Test
void formatRejectsNull() {
    AbstractFormatter formatter = new TestFormatter();
    assertThrows(IllegalArgumentException.class,
            () -> formatter.format(null));
}
```

The snippet above is an illustrative excerpt used inside a JUnit 5 test class with the appropriate imports declared; it is not a standalone file. With JUnit, each test has a clear name, provides more detailed failure reports, and can run automatically in the build.

## 6. When the Abstract Class Depends on a Constructor or External Services

If the abstract class has a constructor that takes parameters, the test subclass must call that constructor using `super(...)`. Pass small, deterministic configuration values or an appropriate fake dependency. If the concrete method calls a database, network, or system clock, consider extracting the dependency into an interface and providing a fake/mock in the test.

```java
abstract class AbstractRepositoryClient {
    private final String endpoint;

    protected AbstractRepositoryClient(String endpoint) {
        this.endpoint = endpoint;
    }

    public String endpointLabel() {
        return "endpoint=" + endpoint;
    }

    protected abstract boolean isAvailable();
}

final class TestRepositoryClient extends AbstractRepositoryClient {
    TestRepositoryClient() {
        super("test://local");
    }

    @Override
    protected boolean isAvailable() {
        return true;
    }
}
```

This is an illustrative structural example, not part of the runnable program from the previous section. The subclass calls the parent constructor and provides a stable value for the abstract hook. There is no need to start a real service if the goal is to test the standalone logic of the parent class.

## 7. Common Mistakes

| Mistake | Why it is a problem | How to fix it |
| --- | --- | --- |
| Attempting to create `new AbstractFormatter()` | An abstract class cannot be instantiated directly. | Create a concrete subclass that implements the missing abstract methods. |
| Test subclass does not implement all abstract methods | The subclass itself remains abstract and cannot be instantiated. | Implement all abstract methods that have not yet been implemented in the parent class. |
| Overriding the concrete method under test | The test may execute the subclass's logic, bypassing the original logic to be tested. | Implement only the necessary abstract hooks; keep the concrete method under test unchanged. |
| Test subclass contains a lot of its own logic | Bugs in the fixture can make results hard to interpret. | Keep the fixture small and predictable; add only the behavior needed to invoke the parent class's logic. |
| Testing only successful outcomes | Input validation and error-handling branches may be missed. | Test valid inputs, boundary inputs, and cases that must throw exceptions. |
| Testing via a subclass while forgetting to test the abstract hook | It may leave unverified whether the subclass provides the behavior the parent class needs. | Write separate tests for the hook contract if that behavior falls within the module's scope of responsibility. |
| Using Java assertions while forgetting to enable `-ea` | The `assert` statement may not execute by default if the flag enabling assertions is missing. | Use a testing framework or explicit condition checks as in the example above; if using `assert`, run `java -ea ...`. |

## 8. Checklist When Writing Tests for an Abstract Class

- [ ] Identify which concrete methods of the abstract class need to be tested.
- [ ] List the abstract methods and implement them in a minimal test subclass.
- [ ] Do not override the concrete method that is the target of testing.
- [ ] Provide constructor arguments or fake dependencies if required by the parent class.
- [ ] Test correct results, boundary inputs, and exceptions according to the contract.
- [ ] Run the tests using the corresponding build command or `javac`/`java`, then verify the actual results.
- [ ] If there are multiple different implementing subclasses, consider testing the shared contract through the same test suite for each subclass.

Core principle: test the concrete logic of an abstract class through a minimal concrete subclass. The subclass should only fill in the mandatory extension points, so that the test results reflect the true behavior of the abstract class.
