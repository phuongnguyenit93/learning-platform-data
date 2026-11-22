# Distinguishing private helpers from extension points for implementing classes

A good API clearly separates **behavior that implementations are allowed to decide** from **shared implementation details**. In an interface, abstract/default instance methods can be part of the API and participate in the overriding mechanism; private helpers keep internal logic. Static methods belong to the declaring type, so they are not polymorphic instance hooks either.

## 1. Comparing roles

| Method kind | Role | Can an implementing class override it? |
|---|---|---|
| `public abstract` instance method | Mandatory contract for concrete implementations | Yes; a concrete class must provide an appropriate implementation |
| `public default` instance method | Default behavior that an implementation can change | Yes |
| `public static` method in an interface | Utility belonging to the interface, called via the interface name | No |
| `private` instance helper | Internal detail with instance context | No |
| `private static` helper | Internal detail that does not need the current instance | No |
| `protected abstract` method in an abstract class | Extension point for subclasses | Yes |

Private methods in interfaces have been supported since Java 9. Helpers must have a method body; they are not a contract for implementing classes. In contrast, a public abstract/default method is designed as an extension point when the API genuinely wants implementations to provide or modify behavior.

Two unrelated interfaces can declare private helpers with the same name and signature without conflict, because private helpers are not inherited. Conversely, if both expose default methods with the same signature, an implementing class may have to override the method to resolve the conflict.

## 2. Complete example: hooks and helpers coexisting

Save the following code as `InterfaceHelperDemo.java` and run it with Java 17 or later:

~~~java
import java.util.Locale;

interface MessageView {
    String transform(String raw);

    default String render(String raw) {
        String checked = requireText(raw);
        return "Result: " + trimResult(transform(checked));
    }

    private String trimResult(String text) {
        return text.trim();
    }

    private static String requireText(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("text must not be null");
        }
        return raw;
    }

    static String kind() {
        return "MessageView";
    }
}

final class UpperMessageView implements MessageView {
    @Override
    public String transform(String raw) {
        return raw.toUpperCase(Locale.ROOT);
    }

    public String trimResult(String text) {
        return "Class method: " + text;
    }
}

public class InterfaceHelperDemo {
    public static void main(String[] args) {
        MessageView view = new UpperMessageView();

        System.out.println(view.render("  java  "));
        System.out.println(new UpperMessageView().trimResult("test"));
        System.out.println(MessageView.kind());

        try {
            view.render(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 --release 17 InterfaceHelperDemo.java
java InterfaceHelperDemo
~~~

Stdout:

~~~text
Result: JAVA
Class method: test
MessageView
Rejected: text must not be null
~~~

### Reading the example by role

- `transform` is an extension point: `UpperMessageView` must provide a public implementation. When `render` calls `transform(checked)`, Java dispatches to the implementation of the actual object.
- `render` is a default method containing the shared workflow. An implementing class can override it if the API allows changing the entire workflow.
- The interface's `trimResult` is a private helper. `render` calls this helper inside the interface, so the result is `Result: JAVA`. The public `trimResult` method in the class is an independent method; it does not override the interface's private helper.
- `requireText` is a private static helper for validating input. External callers cannot call `MessageView.requireText(...)`.
- `MessageView.kind()` is a public static method of the interface. It is called using the interface name, not through `view`.

If `@Override` is added to `UpperMessageView.trimResult`, the compiler will reject it because no corresponding method is inherited to override. Having the same name and signature is not enough to create an override relationship; there must be an original method that can be overridden according to Java's rules.

## 3. When a true extension point is needed

If every implementation must decide for itself how to transform data, expose that behavior in the contract:

~~~java
interface Transformer {
    String transform(String input);
}

final class UpperTransformer implements Transformer {
    @Override
    public String transform(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

`transform` is a public abstract method; concrete implementations are obligated to provide it. If you only want to reuse a normalization step across default methods, using a private helper avoids adding a public method that API consumers could depend on.

A default method sits between these two needs: it provides a shared implementation while still being overridable. If you want to protect the entire default workflow, consider whether the API should allow that default method to be overridden; a private helper only locks down the helper part, not the public method calling it.

## 4. When an abstract class is a better fit

An abstract class lets you design a fixed template method and a hook for subclasses:

~~~java
abstract class BaseWorkflow {
    public final String run(String input) {
        return normalize(step(input));
    }

    private String normalize(String value) {
        return value.trim();
    }

    protected abstract String step(String input);
}

final class EchoWorkflow extends BaseWorkflow {
    @Override
    protected String step(String input) {
        return " " + input + " ";
    }
}
~~~

These are valid class declarations in Java 17, without `main` yet. `run` is `public final`, so subclasses cannot override the algorithm skeleton. `step` is a `protected abstract` hook that subclasses must provide. `normalize` is a private helper of the superclass, used after the hook returns its result.

Use an interface when you need to describe a contract and optionally provide default behavior. Consider an abstract class when you need instance state, constructors, or a template method with more explicitly controlled hooks.

## 5. Decision rules

- **Implementations must decide the behavior:** declare a public abstract instance method in the interface.
- **Need default behavior that can be changed:** use a default method.
- **Need to share internal details between default methods:** use a private instance helper.
- **Need to share internal static logic:** use a private static helper.
- **Need a utility belonging to the interface:** use a public static method and call it via the interface name.
- **Need to keep a fixed superclass workflow while allowing subclasses to replace a step:** consider a `final` template method with a `protected` hook in an abstract class.

Do not make a helper public just so two methods can both call it. Conversely, do not make a mandatory implementation behavior into a private helper: an implementing class cannot use that helper as a contract or override it.

**Self-check:** If an implementing class needs to change the result of a step, determine whether that step is truly an extension point. If so, expose an appropriate method; if not, keep it behind the private boundary so implementations do not depend on internal details.
