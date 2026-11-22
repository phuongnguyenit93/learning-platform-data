# Private Methods in Interfaces Since Java 9

Since **Java 9**, an interface can declare `private` methods with a body. These are internal helpers that allow other methods in the same interface to share logic without making the helper part of the public API.

Java 8 added `default` instance methods and `public static` methods, but did not yet allow private methods in an interface. Therefore, code that uses private interface methods does not compile when targeting `--release 8`.

## 1. Private Instance and Private Static Methods

- A **private instance method** has an object context; it is typically called from a default method or another private instance method in the same interface.
- A **private static method** does not require an instance; it can be called from static methods, default methods, and appropriate helpers in the same interface.

Both forms must have a body. They are not a contract that implementing classes need to implement, are not inherited to be overridden, and cannot be called directly from code outside the interface that declares them.

## 2. Example: Shared Helpers Not Exposed in the API

Save the entire program as `Main.java`. The example requires Java 9 or later.

~~~java
interface TextView {
    default String title(String value) {
        return format("TITLE", value);
    }

    default String summary(String value) {
        return format("SUMMARY", value);
    }

    private String format(String label, String value) {
        return label + ": " + normalize(value);
    }

    static String versionLabel() {
        return "[" + normalize(" Java 9+ ") + "]";
    }

    private static String normalize(String value) {
        if (value == null) {
            return "(empty)";
        }
        return value.trim().toUpperCase(java.util.Locale.ROOT);
    }
}

final class ConsoleTextView implements TextView {
}

public class Main {
    public static void main(String[] args) {
        TextView view = new ConsoleTextView();
        System.out.println(view.title(" private helper "));
        System.out.println(view.summary(" shared code "));
        System.out.println(TextView.versionLabel());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 --release 9 Main.java
java Main
~~~

Stdout:

~~~text
TITLE: PRIVATE HELPER
SUMMARY: SHARED CODE
[JAVA 9+]
~~~

`title` and `summary` are public default instance methods; both call `format` to reuse the label-concatenation step. `format` can operate in an instance context and call `normalize`. The public static method `versionLabel` can also call `normalize` because this helper is private static and does not need `this`.

`ConsoleTextView` does not need to declare or override the helpers. If this class declares its own method with the same name as `format`, that is not an override of the private helper; the call inside the interface still uses the private implementation declared in `TextView`.

## 3. Access Rules to Remember

| Declaration | Directly callable from outside the interface? | Can an implementing class override it? |
|---|---|---|
| `default String title(...) { ... }` | Yes, via an object | Yes |
| `static String versionLabel() { ... }` | Yes, via `TextView.versionLabel()` | No |
| `private String format(...) { ... }` | No | No |
| `private static String normalize(...) { ... }` | No | No |

**If you uncomment one of the lines below, that declaration will be invalid.** Each line is a separate example; you cannot combine all errors into a single runnable program.

~~~java
interface InvalidHelpers {
    // private abstract String helper();
    // private default String other() { return "x"; }
    // private void missingBody();
}
~~~

`private abstract` and `private default` are invalid. A private method cannot have only a semicolon; it needs a body because it is not inherited by subclasses to provide an implementation. An interface also does not use `protected` or package-private methods to create an intermediate scope like a class does.

A private helper can still declare `throws` for a checked exception. If a default/static method calls that helper, the calling method must catch or declare the appropriate checked exception; the `private` modifier does not make the exception disappear.

## 4. Choosing the Helper Type Based on Your Needs

Use a private instance method when the logic needs the context of the current object, such as when calling another instance method of the interface. Use a private static method when the logic only needs parameters or static members and also needs to be used from static methods.

If every implementing class must provide a behavior, expose an abstract instance method. If you need a default behavior that classes can change, use a default method. Private helpers should only contain internal implementation details.

**Version check:** if the build uses Java 8, move the helper to an appropriate utility class or adjust the target; you cannot keep a private method in an interface and expect `--release 8` to accept it.
