# Hook methods, final methods, and protecting invariants

## Objectives

After this lesson, you can distinguish a hook method from an abstract method, explain how Template Method keeps the processing order fixed, use `final` to prevent subclasses from changing critical workflows, and recognize why `final` alone is not enough to protect all object invariants.

## 1. What is a hook method?

A **hook method** is a method in a superclass that provides an extension point for subclasses. The superclass usually defines a default behavior; a subclass can override it when it needs to change an optional step. If the subclass does not override it, the workflow still runs using the default behavior.

A simple example:

~~~java
abstract class Report {
    public final void print() {
        String content = createContent();
        String decorated = decorate(content);
        System.out.println(decorated);
    }

    protected abstract String createContent();

    protected String decorate(String content) {
        return content;
    }
}
~~~

In this example, `createContent()` is an abstract operation that subclasses are required to implement so that a concrete class can be created. `decorate()` is a hook with default behavior: if not overridden, the content is kept as is. Subclasses can optionally add a header, separator, or decoration.

A hook should represent an intentional extension point. Avoid creating too many hooks that make it hard for implementers to understand the execution order, or allowing subclasses to alter steps that must always hold true to maintain a valid state.

## 2. Template Method and final methods

**Template Method** is a design pattern in which a superclass defines the skeleton of an algorithm and the order of its steps; certain steps are provided or customized by subclasses. A common way to keep that skeleton fixed is to declare the coordinating method as `final`.

~~~java
abstract class Importer {
    public final void importData(String source) {
        validateSource(source);
        String data = read(source);
        String normalized = normalize(data);
        save(normalized);
        afterImport(normalized);
    }

    private void validateSource(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("source must not be blank");
        }
    }

    protected abstract String read(String source);

    protected String normalize(String data) {
        return data.trim();
    }

    protected abstract void save(String data);

    protected void afterImport(String data) {
        // Optional hook: does nothing by default.
    }
}
~~~

The `importData()` method is the Template Method. It always validates the source, reads the data, normalizes it, saves the data, and only then calls the post-import hook. Subclasses can provide reading and saving implementations suited to a specific format or system; subclasses can also override `normalize()` or `afterImport()` when needed.

The `final` keyword prevents subclasses from overriding `importData()`, so a subclass cannot replace the entire coordination order with a different algorithm. However, the overridable methods called inside the Template Method still use dynamic dispatch. When running `importData()` on a subclass object, Java invokes the `read()`, `normalize()`, `save()`, or `afterImport()` version corresponding to that object.

This is an intentional combination: **the overall workflow is kept fixed, while extension steps are customized within designed boundaries**.

## 3. Runnable Java 17 example

The following example creates a report exporter. The `export()` method is the Template Method and is declared `final`. The hooks can customize the preparation step and the footer; the formatting step is a mandatory abstract operation. The coordinating method validates data before and after each extension point that can return a result.

Save all the code in the file `TemplateMethodInvariantDemo.java`:

~~~java
import java.util.Locale;

abstract class ReportExporter {
    public final String export(String raw) {
        String input = requireNonBlank(raw, "raw input");
        String prepared = requireNonBlank(prepare(input), "prepared text");
        String body = requireNonBlank(format(prepared), "formatted body");
        return requireNonBlank(addFooter(body), "final output");
    }

    private static String requireNonBlank(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return value;
    }

    protected String prepare(String input) {
        return input.trim();
    }

    protected abstract String format(String prepared);

    protected String addFooter(String body) {
        return body;
    }
}

final class PlainTextExporter extends ReportExporter {
    @Override
    protected String format(String prepared) {
        return "REPORT: " + prepared.toUpperCase(Locale.ROOT);
    }

    @Override
    protected String addFooter(String body) {
        return body + "\n-- end --";
    }
}

public class TemplateMethodInvariantDemo {
    public static void main(String[] args) {
        ReportExporter exporter = new PlainTextExporter();
        System.out.println(exporter.export("  hello Java  "));

        try {
            exporter.export("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~text
javac TemplateMethodInvariantDemo.java
java TemplateMethodInvariantDemo
~~~

Exact stdout output:

~~~text
REPORT: HELLO JAVA
-- end --
raw input must not be blank
~~~

The execution flow of the first call is:

1. Validate the initial input.
2. Call the `prepare()` hook; the default behavior trims leading and trailing whitespace.
3. Call the `format()` operation implemented by the subclass.
4. Call the `addFooter()` hook; the subclass adds the ending line.
5. Return the validated string.

The second call is rejected immediately at the input validation step. If a subclass overrides `prepare()`, `format()`, or `addFooter()` to return `null` or a whitespace-only string, the subsequent validation step rejects that result. Subclasses can still customize behavior, but they cannot bypass the validation chain by overriding `export()`.

## 4. What does `final` protect?

In Java, `final` has different meanings depending on where it is declared:

| Usage | Meaning |
|---|---|
| `final class A` | Cannot create a subclass that extends `A`. |
| `final void run()` | Subclasses cannot override the instance method `run()`. |
| `final int limit = 10` | The variable can be assigned only once. For a reference variable, `final` prevents reassigning the reference; it does not by itself make the referenced object immutable. |

A `final` method is useful when a superclass must maintain a stable protocol, such as validating input before processing, performing a state update step, and then checking the result before returning. Subclasses cannot override that method to reverse the order or skip checks placed directly inside the method.

However, `final` **does not automatically make all behavior inside the method unchangeable**. If a `final` method calls an overridable hook, the hook can still execute custom behavior, throw an exception, or cause side effects. Therefore, place critical checks in non-overridable code, restrict the state accessible from subclasses, and validate results after extension points.

The same method cannot be declared both `abstract` and `final`: `abstract` requires subclasses to provide an implementation, whereas `final` forbids overriding. If you need to require subclasses to implement a step, use an abstract method; if you need to preserve the coordination step, use a `final` method that calls that abstract operation.

## 5. Protecting object invariants

An **invariant** is a condition that must always hold true for an object's valid state at times when the object is considered stable and usable. For example, an account might require a non-negative balance; a counter might require a value no less than 0; a configuration object might require its name not to be blank.

To protect invariants in a design using inheritance:

- **Hide state:** prefer `private` fields; do not allow subclasses to directly modify fields that represent invariants.
- **Validate at boundaries:** validate input data before updating and validate results before publishing.
- **Keep critical operations stable:** consider using a `final` method for public operations if subclasses are not allowed to alter their protocol.
- **Design narrow hooks:** only open up the steps that truly need customization. Avoid granting hooks access to directly modify internal state.
- **Do not return state that can be modified unintentionally:** use immutable types or defensive copies when needed; declaring a reference as `final` does not automatically make the referenced object immutable.
- **Validate after calling extension code:** if a hook returns data, inspect that data before using it or returning it to the caller.

A `final` method cannot on its own protect a `public` field from being modified directly, a mutable object returned externally, or state corrupted by a hook's side effects. Invariants are best protected through multiple layers: encapsulating state, validating data, restricting extension points, and coordinating operations in a clear order.

## 6. Constructors and overridable method calls

An important pitfall is calling an overridable method from a superclass constructor. Java can dispatch to the overridden version in the subclass even before the subclass constructor has finished running. When that happens, the overriding method may read subclass fields that have not been fully initialized and observe an invalid state.

Example illustrating the design flaw:

~~~java
class BaseConfig {
    BaseConfig() {
        initialize(); // Should not call an overridable hook here.
    }

    protected void initialize() {
    }
}

class AppConfig extends BaseConfig {
    private String endpoint = "https://example.invalid";

    @Override
    protected void initialize() {
        System.out.println(endpoint.length());
    }
}
~~~

When `BaseConfig`'s constructor calls `initialize()`, the overridden version in `AppConfig` can be invoked before the subclass's initialization of the `endpoint` field completes. The field may still be `null`, leading to a `NullPointerException`. Therefore, avoid calling overridable methods from constructors; complete initialization first and only then invoke extension points.

The code above is only an example illustrating a flaw and is not a working program. Marking the coordinating method as `final` also does not make every call inside it static: if that method calls an overridable hook in a constructor, the risk still exists.

## 7. When should you use hooks and final?

Use a hook when the superclass needs a controlled customization point, such as adding post-processing extensions, providing formatting rules, or allowing subclasses to tailor a secondary step. A hook should have a clear name and contract, as well as sensible default behavior if it is optional.

Use a `final` method when the superclass must guarantee the order of a workflow or disallow subclasses from altering a core operation. Do not mark every method as `final` out of habit: doing so can restrict extensibility that the design actually needs. If inheritance is not needed, a `final` class or a composition-based design may be simpler.

Before adding a hook, ask yourself: does a subclass truly need to change this step? If the hook returns a result, how will the superclass verify that result? Could the hook expose or corrupt internal state? If there is no clear answer, narrow the extension API.

## 8. Review checklist

1. Which method defines the algorithm order? If the order must be fixed, consider marking the coordinating method as `final`.
2. Which steps must subclasses provide? Use `abstract` methods with a specific contract.
3. Which steps are optional? Use hooks with clear default behavior.
4. Which invariants must always hold true? Keep related fields `private`, check inputs, and validate results.
5. Could a hook return `null`, empty data, throw an exception, or cause side effects? Decide how to handle these before publishing the result.
6. Does a constructor call an overridable method? If so, review the initialization flow to avoid using incomplete state.
7. Does the example compile, and does stdout match the run command? Keep runnable examples separate from code snippets intended only to illustrate design flaws.

## Conclusion

Hook methods provide controlled customization points; `final` methods preserve the coordinating skeleton; and checks together with state encapsulation help protect invariants. These three techniques complement one another. A good design clearly defines which steps may be customized, keeps core conditions in non-overridable code, and validates data at the boundary between the superclass and subclasses.
