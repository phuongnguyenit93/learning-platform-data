# Calling a static method via the exact interface name

When a `static method` is declared in an interface, that interface name is the target of the call. For example, if `hasText` is declared in `TextRules`, the explicit call is:

~~~java
TextRules.hasText("Java");
~~~

Do not infer where the method is declared from the type of the variable you hold or from a class that `implements` that interface. A static call is resolved by the type name written in the expression, not by the runtime class of the object.

## 1. Runnable example

Save all of the following code as `InterfaceStaticDemo.java`:

~~~java
interface TextRules {
    static boolean hasText(String value) {
        return value != null && !value.trim().isEmpty();
    }

    default boolean accepts(String value) {
        return TextRules.hasText(value);
    }
}

final class BasicRules implements TextRules {
}

public class InterfaceStaticDemo {
    public static void main(String[] args) {
        System.out.println(TextRules.hasText("Java"));
        System.out.println(TextRules.hasText("   "));

        TextRules rules = new BasicRules();
        System.out.println(rules.accepts(" Java "));

        java.util.function.Predicate<String> check = TextRules::hasText;
        System.out.println(check.test("API"));
    }
}
~~~

Compile and run on JDK 8 or later:

~~~bash
javac -encoding UTF-8 --release 8 InterfaceStaticDemo.java
java InterfaceStaticDemo
~~~

Stdout:

~~~text
true
false
true
true
~~~

`TextRules.hasText(...)` is a static call. In contrast, `rules.accepts(...)` is an instance call to a default method. Inside `accepts`, the code still calls the static helper using `TextRules.hasText(value)`.

`TextRules::hasText` is a method reference to the static method declared by the interface. It can be passed to an API that accepts a functional interface such as `Predicate<String>`.

## 2. Invalid calls

In the example above, the following two lines are intentionally commented out because they cause compilation errors if uncommented:

~~~java
// BasicRules.hasText("Java"); // BasicRules does not inherit the static method from TextRules.
// rules.hasText("Java");      // A static interface method is not an instance method.
~~~

`implements TextRules` only connects the class to the instance contract of the interface; it does not make the interface's static methods inherited members of the class. If `BasicRules` itself declares a static method with the same name, that is `BasicRules`'s own method, not an override of `TextRules.hasText`.

## 3. Static import and API choices

In another file in an appropriate package, Java allows a static import of a public method:

~~~java
import static com.example.rules.TextRules.hasText;

class Caller {
    boolean check() {
        return hasText("Java");
    }
}
~~~

This import example illustrates the syntax; the package must match where `TextRules` is actually declared. A static import only shortens the syntax. It does not change the method owner, access permissions, or dispatch rules.

If you want an operation to be behavior that can be customized per implementation, declare an abstract/default instance method and call it through an object. Do not use a static method and expect an implementing class to override it.

**Checklist before calling**

1. Identify the interface that actually declares the method.
2. Use `InterfaceName.method(...)` or the method reference `InterfaceName::method`.
3. If you need to call it through an object and use polymorphism, check whether the method is an instance method.
4. If the compiler reports that the method cannot be found on the implementing class or subinterface, go back to the original declaring type to identify the owner.
