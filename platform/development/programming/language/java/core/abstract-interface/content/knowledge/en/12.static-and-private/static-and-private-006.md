# Private static methods and instance member access restrictions

The two keywords `private` and `static` answer two different questions. `private` determines where access is permitted; `static` indicates that the method belongs to the declaring type and has no implicit current instance. Therefore, `private static` is often suitable for internal helpers that only need input parameters.

## 1. Private static helpers in interfaces since Java 9

In an interface, `private static` groups internal processing that can be used from both `default` methods and `static` methods of the interface itself. It does not need a receiver object, so it is suitable for parameter normalization or input validation. Unlike an instance method, it cannot directly call `prefix()` or use `this` because there is no current object.

Save the following program as `InterfacePrivateStaticDemo.java` and run it with Java 9 or later:

~~~java
import java.util.Locale;

interface DisplayRule {
    String prefix();

    default String label(String value) {
        return prefix() + ": " + clean(value);
    }

    static String normalize(String value) {
        return clean(value);
    }

    static String labelFor(DisplayRule rule, String value) {
        return rule.prefix() + ": " + clean(value);
    }

    private static String clean(String value) {
        return value == null ? "(empty)" : value.trim().toUpperCase(Locale.ROOT);
    }
}

final class BasicDisplay implements DisplayRule {
    @Override
    public String prefix() {
        return "VIEW";
    }
}

public class InterfacePrivateStaticDemo {
    public static void main(String[] args) {
        DisplayRule rule = new BasicDisplay();
        System.out.println(rule.label(" java "));
        System.out.println(DisplayRule.normalize(" private "));
        System.out.println(DisplayRule.labelFor(rule, " api "));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 9 InterfacePrivateStaticDemo.java
java InterfacePrivateStaticDemo
~~~

Stdout:

~~~text
VIEW: JAVA
PRIVATE
VIEW: API
~~~

`label` is an instance default method, so it can call `prefix()` on the actual object. `normalize` and `labelFor` are public static methods declared by `DisplayRule`; both call the private static `clean`. In `labelFor`, the expression `rule.prefix()` is valid because `rule` provides an **explicit receiver**, whereas `prefix()` on its own inside a static method will not compile. It is these two independent conditions — having a receiver and having access permission — that determine whether referencing an instance member is valid. An external caller cannot call `DisplayRule.clean(...)` because `clean` is private.

## 2. Supporting example: static helper in a class

Save the program as `PrivateStaticDemo.java`:

~~~java
import java.util.Locale;

public class PrivateStaticDemo {
    public static void main(String[] args) {
        Ticket first = new Ticket("  t-01  ");
        Ticket second = new Ticket("t-02");

        System.out.println(first.code() + " / " + second.code());
        System.out.println("Created: " + Ticket.createdCount());
    }
}

final class Ticket {
    private static int created;
    private final String code;

    Ticket(String rawCode) {
        this.code = normalize(rawCode);
        created++;
    }

    private static String normalize(String rawCode) {
        if (rawCode == null || rawCode.trim().isEmpty()) {
            throw new IllegalArgumentException("code is required");
        }
        return rawCode.trim().toUpperCase(Locale.ROOT);
    }

    String code() {
        return code;
    }

    static int createdCount() {
        return created;
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 PrivateStaticDemo.java
java PrivateStaticDemo
~~~

Stdout:

~~~text
T-01 / T-02
Created: 2
~~~

The instance constructor can call `normalize` because it is inside the `Ticket` class itself. The helper only needs the passed-in string, so it does not need `this`. The `code` field belongs to each ticket, whereas `created` is a static variable shared by objects of that class.

`Ticket.normalize("abc")` cannot be called from `PrivateStaticDemo` because the helper is private. Access permission is checked based on where the code appears; using the class-name syntax inside `Ticket` itself is still valid.

Note that `created++` only illustrates shared static state; it is not a safe counter when multiple threads increment the value concurrently.

## 3. A static context has no current instance

A static method has no implicit `this` reference. If you want to read the balance of a `Wallet`, Java needs to know which object is being read.

~~~java
class Wallet {
    private int balance;

    private int getBalance() {
        return balance;
    }

    private static int invalid() {
        // return balance;       // Error: missing receiver object.
        // return this.balance;  // Error: no this in static context.
        // return getBalance();  // Error: missing receiver object.
        return 0;
    }

    private static int readBalance(Wallet wallet) {
        return wallet.balance;
    }
}
~~~

The three commented-out lines are intentionally invalid examples. `readBalance` is valid because `wallet` explicitly specifies the receiver object. That code is inside the `Wallet` class itself, so it also has access to the private `balance` field.

Two conditions must be checked independently:

- **Is there a specific receiver?** `wallet.balance` has one; a bare `balance` inside a static method does not.
- **Is there access permission?** An object reference does not by itself grant an unrelated class permission to read a private field.

Therefore, saying “a static method can never access an instance member” is inaccurate. It does not automatically have a current instance, but it can operate on an object passed in or obtained from a valid reference source.

A nested class can access private members of the outer class according to Java rules, but a static nested class has no `Outer.this`; it still needs a specific object reference to read instance state.

## 4. Private static is not a private instance method

| Member | Has implicit `this`? | Suitable example |
|---|---|---|
| `private void update() { ... }` | Yes | Updating the state of the current object |
| `private static String normalize(String value) { ... }` | No | Normalizing parameters, validating data, parsing |
| `private static int total(Counter a, Counter b) { ... }` | No; but has explicit receivers via `a` and `b` | Computing based on multiple passed-in objects |

For example, a static helper inside the class itself can read private fields of passed-in instances:

~~~java
final class Counter {
    private final int value;

    Counter(int value) {
        this.value = value;
    }

    private static int total(Counter left, Counter right) {
        return left.value + right.value;
    }
}
~~~

`left.value` and `right.value` are valid because the method has references to two specific objects and is inside the class that declares the field. If the code is outside `Counter`, merely having a `Counter` reference is still not enough permission to read `value` directly.

## 5. Inheritance, hiding, and interfaces

A private static method of a parent class does not create an override point for a subclass. If the subclass declares a method with the same name on its own, that is the subclass's own method. For an accessible and inherited static method of a class, a subclass can declare a corresponding method to *hide* the parent method; neither participates in dynamic dispatch via an instance.

In an interface, a private static method is also an internal helper. Java has supported `private static` methods in interfaces since **Java 9**; Java 8 did not yet have private interface methods. That helper must have a body, can only be called from code with access permission inside the interface that declares it, and is not an API for implementing classes to call directly.

Do not confuse private with static: a method can be a private instance method or a private static method. Also do not confuse static with public: access modifiers and instance context are two separate axes.

## 6. Choosing the right method form

- Use `private static` when the processing does not need the state of `this` and the required inputs can be passed via parameters.
- Use a private instance method when the logic needs the state of the current object.
- If another class needs to call the operation, intentionally design a public API; do not widen private access just to avoid a compiler error.
- If behavior needs to be changed by a subclass, create an extension point with an appropriate instance method. Static/private helpers are not polymorphic hooks.
- Mutable state in a static field is shared; consider synchronization or atomics if multiple threads can update it concurrently.

**Self-check**

1. Why can the constructor call the private static `normalize`? Because the constructor code is inside the class that declares the helper.
2. Why is `return balance` invalid in a static method while `return wallet.balance` can be valid? The second form explicitly specifies the receiver object, and private access permission is checked separately.
3. Does a subclass override a parent's private static method? No; private methods are not inherited for overriding, and static methods are not instance overrides.
