# Testing Template Method Step Order and Hooks

## Objectives

Template Method defines the skeleton of an algorithm in a superclass, while overridden methods or hooks allow subclasses to customize certain steps. When testing, you need to verify both the result and the step invocation order, the default behavior of hooks, and what happens when a step fails. This article uses Java 17, a small test suite with no external libraries, and recorded events to observe the execution flow.

## 1. Why Test Execution Order?

Suppose a data processing workflow must execute steps in the following order:

1. Run the hook before processing.
2. Read the data.
3. Transform the data.
4. Save the result.
5. Run the hook after completion.

If you only check the final result, the test might miss saving data before transforming it, calling a hook at the wrong time, or running a later step even though an earlier step failed. With Template Method, the order is part of the contract provided by the superclass.

A direct way to test this is to have a test class record the name of each step into a list. After calling the template method, compare the entire actual list against the expected event list. This approach helps detect missing steps, duplicate steps, and reversed order.

## 2. Designing Testable Extension Points

The superclass below defines the `execute()` method as `final`. Subclasses cannot replace the overall workflow, but they can implement the `load()` and `persist()` steps, as well as customize the `before()`, `transform()`, and `after()` hooks.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

abstract class DataPipeline {
    public final String execute(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("source must not be blank");
        }

        before(source);

        String loaded = load(source);
        if (loaded == null) {
            throw new IllegalStateException("load returned null");
        }

        String transformed = transform(loaded);
        if (transformed == null) {
            throw new IllegalStateException("transform returned null");
        }

        persist(transformed);
        after(transformed);
        return transformed;
    }

    protected void before(String source) {
        // Optional hook: does nothing by default.
    }

    protected abstract String load(String source);

    protected String transform(String loaded) {
        return loaded.trim();
    }

    protected abstract void persist(String transformed);

    protected void after(String transformed) {
        // Optional hook: does nothing by default.
    }
}
~~~

The `before()` and `after()` methods are optional hooks with empty default behavior. `transform()` has a default behavior of trimming leading and trailing whitespace. `load()` and `persist()` are required steps implemented by subclasses. The data validation checks reside in the template method, so every subclass must pass through them when `execute()` is called.

Declaring `execute()` as `final` means the compiler will reject a subclass if it tries to override this method. Testing the order is still necessary because template methods can invoke overridable hooks; those calls are what produce polymorphic behavior at runtime.

## 3. Recording Events to Verify Order

Create a test class that records each step. The `load()` method returns a string with whitespace, while `transform()` records the input data and then normalizes it to uppercase. As a result, the test can verify not only the order, but also the data passed between steps.

~~~java
final class RecordingPipeline extends DataPipeline {
    final List<String> events = new ArrayList<>();

    @Override
    protected void before(String source) {
        events.add("before:" + source);
    }

    @Override
    protected String load(String source) {
        events.add("load:" + source);
        return "  hello  ";
    }

    @Override
    protected String transform(String loaded) {
        events.add("transform:" + loaded);
        return loaded.trim().toUpperCase(Locale.ROOT);
    }

    @Override
    protected void persist(String transformed) {
        events.add("persist:" + transformed);
    }

    @Override
    protected void after(String transformed) {
        events.add("after:" + transformed);
    }
}
~~~

The expected event list when calling `execute("source")` is:

~~~text
before:source
load:source
transform:  hello  
persist:HELLO
after:HELLO
~~~

You can see that the `before()` hook runs before reading, the data with whitespace is passed into `transform()`, the normalized result is saved, and the `after()` hook runs only after the save step succeeds. If the actual list differs from the expected list, the test will point out which contract was violated.

## 4. Testing the Failure Path

Beyond the success path, verify that subsequent steps do not run when a step returns invalid data. The class below simulates a data reading error by returning `null`. The `persisted` flag helps verify that the save step is not called.

~~~java
final class NullLoadPipeline extends DataPipeline {
    boolean persisted;

    @Override
    protected String load(String source) {
        return null;
    }

    @Override
    protected void persist(String transformed) {
        persisted = true;
    }
}
~~~

According to the contract of `DataPipeline`, `execute()` must throw `IllegalStateException` with the message `load returned null` immediately after the read step. The `transform()`, `persist()`, and `after()` methods must not run. Testing the failure path is very important when step order involves side effects, such as writing data to a database or emitting events.

## 5. Complete Test Program

Save all the code in the same `TemplateMethodOrderTest.java` file: place the three `import` lines from section 2 at the **top of the file**, then combine `DataPipeline` (section 2), `RecordingPipeline` (section 3), `NullLoadPipeline` (section 4), and `TemplateMethodOrderTest` (section 5) in order. The `import` lines must precede all class declarations; when combining, do not repeat `import` lines in the middle of the file.

~~~java
public class TemplateMethodOrderTest {
    public static void main(String[] args) {
        RecordingPipeline pipeline = new RecordingPipeline();

        String result = pipeline.execute("source");
        check("HELLO".equals(result), "unexpected result: " + result);

        List<String> expectedEvents = List.of(
            "before:source",
            "load:source",
            "transform:  hello  ",
            "persist:HELLO",
            "after:HELLO"
        );
        check(
            pipeline.events.equals(expectedEvents),
            "unexpected order: " + pipeline.events
        );

        System.out.println("success trace: " + String.join(" -> ", pipeline.events));

        NullLoadPipeline failing = new NullLoadPipeline();
        try {
            failing.execute("source");
            throw new AssertionError("Expected load failure");
        } catch (IllegalStateException expectedFailure) {
            check(
                "load returned null".equals(expectedFailure.getMessage()),
                "unexpected error: " + expectedFailure.getMessage()
            );
        }

        check(!failing.persisted, "persist must not run after invalid load");
        System.out.println("failure path: load returned null; persist skipped");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~text
javac TemplateMethodOrderTest.java
java TemplateMethodOrderTest
~~~

Exact stdout output:

~~~text
success trace: before:source -> load:source -> transform:  hello   -> persist:HELLO -> after:HELLO
failure path: load returned null; persist skipped
~~~

If any condition is not true, the `check()` method throws `AssertionError`, causing the program to exit with an error instead of printing the success output. Therefore, the stdout above appears only when the result, event order, error message, and skipping of the save step are all correct.

## 6. Testing Default Hooks and Overridden Hooks

A hook with default behavior must be tested according to its purpose. If the default is to do nothing, you can create a subclass that implements only the required steps and verify that the result is still correct without overriding the hook. If the default hook normalizes data, verify that normalization occurs when the subclass does not provide its own version.

For overridden hooks, check the following:

- The hook runs exactly once and at the right position in the flow.
- The hook receives the right input data and the result is passed on to the right step.
- Custom behavior does not bypass required conditions of the superclass.
- If the hook throws an exception, steps after it must not run outside the defined contract.
- If the hook returns data, the superclass checks that data before using it further.

You should not test merely by confirming that a hook was called. A hook can be called the right number of times yet in the wrong order or with the wrong data. An event list together with argument values makes checking the contract clearer.

## 7. Test Scope and Limitations of final

A `final` method protects the orchestration point from being overridden, but it does not by itself guarantee that every hook is safe. A subclass can still perform side effects in `load()`, `transform()`, `persist()`, or a hook. Therefore, you should check results and errors at the boundaries between steps, while limiting the state that a subclass can modify.

In a large system, you can move dependencies such as a data store or reader into separate objects and use a fake/mock to verify interaction order. When using JUnit, each path should be an independent test: the success path, invalid input, invalid read data, a hook throwing an exception, and default hook behavior. The example above uses `main` and simple checks so that it can be run directly without installing libraries.

Avoid writing tests that depend on internal details outside the contract. If the order `before → load → transform → persist → after` is the guaranteed behavior, test that order. If the order between two operations is not specified, do not fail the test just because a valid implementation chooses a different order.

## 8. Review Checklist

1. Clearly identify the step order guaranteed by the Template Method.
2. Use a fake or an event-recording class to observe hook calls and required operations.
3. Compare the entire expected event list against the actual list, including the data passed into each step.
4. Test error paths and verify that subsequent steps do not run when a precondition fails.
5. Test default hooks and overridden hooks.
6. Use `final` on the orchestration method when subclasses are not allowed to alter the overall algorithm.
7. Run the example with the exact target Java version and verify that stdout matches the expected output.

## Conclusion

Testing Template Method requires verifying the contract of the entire workflow: which steps run, in what order they run, what data is passed between steps, and how subsequent steps respond when an error occurs. Recording events with a fake or spy is a direct way to verify these requirements. Combining a `final` orchestration method, clearly scoped hooks, and tests for both success and failure helps the superclass keep the workflow stable while still allowing subclasses to customize safely.
