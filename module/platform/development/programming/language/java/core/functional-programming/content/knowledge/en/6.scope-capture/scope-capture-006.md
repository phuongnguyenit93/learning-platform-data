# Meaning of `this` and `super` in Java Lambdas

## 1. Core Question: Inside a Lambda, Who Is `this`?

In Java, a lambda represents behavior according to a **functional interface** (an interface with a single functional abstract method). A lambda can be declared inside a method of an object and access members of that object. In that situation, two ideas must be distinguished:

- **`this` in a lambda** keeps the meaning of `this` at **the location where the lambda is written**: it is the *lexically enclosing instance*.
- **`super` in a lambda** is also resolved according to **the enclosing class context**: it allows referencing superclass members that the current class is allowed to call, just as if written directly at that enclosing location.

A lambda **does not create a new `this` object for the lambda body** the way an anonymous inner class does. Although the runtime needs an appropriate object or execution mechanism to represent the functional interface, the keyword `this` written inside the lambda body still refers to the object of the class containing the lambda expression.

This is an important difference between:

~~~java
Runnable lambda = () -> System.out.println(this);
~~~

and:

~~~java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(this);
    }
};
~~~

Both snippets above are **illustrations placed inside an instance method**. In the first snippet, `this` is the instance of the class containing the method. In the second snippet, `this` is the **instance of the anonymous class** just created by `new Runnable() {...}`.

This affects calling overridden methods, accessing fields, using `super`, writing long-lived callbacks, and refactoring code from anonymous classes to lambdas.

## 2. Brief Review: `this` and `super` Without Lambdas

Suppose there are two classes:

~~~java
class Parent {
    String describe() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    String describe() {
        return "child";
    }

    void print() {
        System.out.println(this.describe());
        System.out.println(super.describe());
    }
}
~~~

This is an **illustrative snippet**. In `Child.print()`:

- `this.describe()` calls the method on the current object. For a `Child` instance, the result is **"child"**.
- `super.describe()` selects the implementation of the superclass **Parent**, so the result is **"parent"**.
- `this` does not mean "parent type"; `super` does not create a new parent object either. Both operate in the context of the same instance, but their **member selection** differs.

When both expressions above are placed inside a **lambda written in an instance method of `Child`**, this meaning is preserved.

## 3. Complete Java 17 Example: Lambdas and Anonymous Classes See `this` Differently

Create the file **LambdaThisSuperDemo.java**:

~~~java
class ParentPrinter {
    String describe() {
        return "parent";
    }
}

public class LambdaThisSuperDemo extends ParentPrinter {
    private final String name = "child";

    @Override
    String describe() {
        return "child";
    }

    void demonstrate() {
        Runnable lambda = () -> {
            System.out.println("lambda this: " + this.describe());
            System.out.println("lambda super: " + super.describe());
            System.out.println("lambda name: " + this.name);
            System.out.println("lambda this==outer: "
                    + (this == LambdaThisSuperDemo.this));
        };

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous this==outer: "
                        + (((Object) this)
                                == LambdaThisSuperDemo.this));
                System.out.println("anonymous outer: "
                        + LambdaThisSuperDemo.this.describe());
            }
        };

        lambda.run();
        anonymous.run();
    }

    public static void main(String[] args) {
        new LambdaThisSuperDemo().demonstrate();
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 LambdaThisSuperDemo.java
java LambdaThisSuperDemo
~~~

Stdout:

~~~text
lambda this: child
lambda super: parent
lambda name: child
lambda this==outer: true
anonymous this==outer: false
anonymous outer: child
~~~

Explanation in order:

1. The lambda is written in `LambdaThisSuperDemo.demonstrate()`, an **instance method**. Therefore, `this.describe()` calls the `LambdaThisSuperDemo` instance's implementation and prints **child**.
2. `super.describe()` in the same lambda uses the inheritance context of `LambdaThisSuperDemo`, so it calls the implementation in `ParentPrinter` and prints **parent**.
3. `this.name` reads the field of the enclosing class instance, printing **child**.
4. `LambdaThisSuperDemo.this` is the `OuterClass.this` syntax to explicitly specify the enclosing instance when allowed. In this lambda, `this` and `LambdaThisSuperDemo.this` reference the same object, so `==` returns **true**.
5. In the anonymous class, `this` is the instance of the anonymous class itself. One side of the comparison is cast to `Object` so the two references can be compared with `==`; the result is **false**.
6. From the anonymous class you can still access the enclosing instance using `LambdaThisSuperDemo.this`, so the final call prints **child**.

**Practical consequence:** Converting `new Runnable() { ... }` to `() -> { ... }` can change behavior if the old code used `this` or `super`. The two forms are not equivalent in receiver semantics, even though both create a callback with a `run()` method.

The example intentionally uses `Runnable` because it has one `void run()` method. For `Supplier<String>` or `Function<T,R>`, the rules for `this` and `super` in lambdas remain the same.

## 4. Which Context's Superclass Does `super` in a Lambda Select?

When class `Child` extends `Parent`, a lambda written in an instance method of `Child` can use `super.method()` if the call is valid at that position. Here, `super` is **not** "the parent of a lambda object" or "the parent of the functional interface."

With the following snippet (illustrated in `Child` from section 2):

~~~java
Runnable task = () -> {
    System.out.println(super.describe());
};
~~~

The result when running `task.run()` on a `Child` is **parent**.

If rewritten using an anonymous class:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        // super.describe() is NOT valid here:
        // super belongs to the anonymous class context, not Child.
        System.out.println(Child.this.describe());
    }
};
~~~

This is an **illustrative snippet** inside an instance method of `Child`; the comment marks code intentionally not used. The anonymous class `new Runnable() {...}` has `Object` as its actual superclass and implements `Runnable`. Because `Object` does not define `describe()`, `super.describe()` inside the anonymous class will not compile. `Child.this.describe()` calls the implementation via the enclosing instance, typically using virtual dispatch. To call the parent's implementation from elsewhere, put the logic into an appropriate method of `Child` and call that method according to a clear contract.

**A limit to remember:** `super` is still subject to Java's rules on access, inheritance, member types, and syntactic position. Being inside a lambda does not grant extra access to private members of the superclass or turn an invalid call into a valid one.

### 4.1. `super` does not mean dynamic dispatch

When overriding an instance method, `this.method()` normally uses dynamic dispatch and can select an overridden implementation at runtime. `super.method()` specifies the superclass implementation selected according to Java rules. Thus, the two expressions can return different results on **the same instance**.

Do not think of `super` as a variable holding a separate "Parent object"; it is member-access syntax in an inheritance relationship. Nor should `super` be used to bypass API design: if the superclass provides behavior that needs extension, check whether overriding and calling `super` fits the contract.

## 5. Method References: `this::method` and `super::method`

Java allows writing method references instead of lambdas when signatures match. In an instance context, the following two forms can differ:

- **`this::method`**: references the method on the current receiver; for overridden methods, invocation follows normal dispatch rules.
- **`super::method`**: creates a method reference calling the superclass implementation, with the semantics of `super.method()` at the writing site.

Create the file **BoundMethodReferenceDemo.java**:

~~~java
import java.util.function.Supplier;

class BaseMessage {
    String message() {
        return "from base";
    }
}

public class BoundMethodReferenceDemo extends BaseMessage {
    @Override
    String message() {
        return "from child";
    }

    void demonstrate() {
        Supplier<String> current = this::message;
        Supplier<String> parent = super::message;

        Supplier<String> currentLambda = () -> this.message();
        Supplier<String> parentLambda = () -> super.message();

        System.out.println(current.get());
        System.out.println(parent.get());
        System.out.println(currentLambda.get());
        System.out.println(parentLambda.get());
    }

    public static void main(String[] args) {
        new BoundMethodReferenceDemo().demonstrate();
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BoundMethodReferenceDemo.java
java BoundMethodReferenceDemo
~~~

Stdout:

~~~text
from child
from base
from child
from base
~~~

**Explanation:** `Supplier<String>` has the SAM `String get()`; therefore, a method reference to a zero-argument method returning `String` is compatible. The two pairs of expressions produce the same output, yet what matters is that the **receiver/invocation context** differs. This is a practical example to verify whether converting from a lambda to a method reference preserves the right behavior.

A method reference `this::message` or `super::message` created in an instance context can bind to the existing instance. If the callback is retained in a long-lived structure, holding a reference to that callback can keep the instance alive longer than expected. Lifecycle management remains the responsibility of application design.

## 6. No `this` or `super` in a Static Context

A lambda written in a **static method** has no `this` for the class containing the method, because a static method itself is not tied to a specific instance.

~~~java
import java.util.function.Supplier;

public class StaticContextDemo {
    private static final String PREFIX = "static:";

    static Supplier<String> makeLabel() {
        return () -> PREFIX + "ready";
    }

    public static void main(String[] args) {
        System.out.println(makeLabel().get());
    }
}
~~~

The file **StaticContextDemo.java** above runs cleanly:

~~~bash
javac StaticContextDemo.java
java StaticContextDemo
~~~

Stdout:

~~~text
static:ready
~~~

If inside `makeLabel()` you write `() -> this.toString()` or `() -> super.toString()`, the code **will not compile** because there is no instance context. Similarly, you cannot write `this::someInstanceMethod` in a static method without an existing receiver.

Appropriate approach if a specific instance is needed:

~~~java
// Illustrative snippet with Supplier imported.
static Supplier<String> makeFor(Object receiver) {
    return receiver::toString;
}
~~~

The method takes an instance as a parameter and returns a bound method reference; it does not need `this` in a static context. If the interface only requires an instance-independent transformation, a static method or a lambda that does not capture a receiver is sufficient.

**Note on enclosing level:** a lambda located inside an instance method, even within code invoked from a static context, must still be evaluated according to **the actual location where the lambda is written**. Do not infer `this` semantics from where the callback is called. A lambda declared in an instance method keeps its association with that instance when run on another thread or in another place.

## 7. Nested Lambdas Still Follow Lexical `this`

If a lambda returns another lambda, nesting multiple levels of expressions **does not create additional `this` receivers**:

~~~java
import java.util.function.Supplier;

public class NestedLambdaDemo {
    private final String label = "outer";

    Supplier<Supplier<String>> factory() {
        return () -> () -> this.label;
    }

    public static void main(String[] args) {
        NestedLambdaDemo owner = new NestedLambdaDemo();
        System.out.println(owner.factory().get().get());
    }
}
~~~

Run:

~~~bash
javac NestedLambdaDemo.java
java NestedLambdaDemo
~~~

Stdout:

~~~text
outer
~~~

Both lambdas in `factory()` are written in the instance context of `NestedLambdaDemo`. `this.label` in the innermost lambda is still the field of **owner**.

### 7.1. Local variables differ from `this`

A lambda can use a **local variable** from the enclosing scope if that variable is **final or effectively final** (assigned once according to Java rules). For example:

~~~java
String prefix = "item:";
Supplier<String> labeler = () -> prefix + this.label;
~~~

This is an **illustrative snippet** placed inside an instance method with `Supplier` imported and a corresponding `label` field.

Here there are two different data sources:

1. **`prefix`** is a *captured local variable*, which must be final/effectively final.
2. **`this.label`** is a field of the current receiver. The `this` object reference may be retained for the lambda to use later; if the field is mutable, its value can change between invocations.

`this` is not a local variable subject to the effectively final rule like `prefix`; it is a receiver expression in the instance context of the enclosing class.

### 7.2. Name collision between lambda parameters and enclosing local variables

In Java, a lambda does not create an independent namespace for local variable names the way an anonymous class creates its own class scope. Therefore, you cannot redeclare a lambda parameter with the same name as a local variable in the same enclosing scope.

~~~java
int quantity = 5;
// DOES NOT COMPILE:
// Function<Integer, Integer> f = quantity -> quantity + 1;
~~~

This is an **intentionally invalid** example to highlight local variable shadowing, assuming declaration in the same method and `Function` imported. Use a different name such as `value -> value + 1`.

Conversely, a lambda parameter can share a name with an **instance field** without violating the local variable shadowing rule; in that case use `this.fieldName` to distinguish the field from the parameter. The meaning of `this` remains the enclosing receiver.

## 8. Anonymous Class vs. Lambda: Key Comparison Table

| Aspect | Lambda written in an instance method | Anonymous class `new Runnable() {...}` |
| --- | --- | --- |
| `this` in body | Lexically enclosing class instance | Anonymous class instance |
| `super` in body | Superclass/inheritance context of enclosing class | Superclass of anonymous class |
| `Outer.this` | Usable when a valid enclosing instance exists | Usable to explicitly specify a valid enclosing instance |
| Local variable name scope | Shares enclosing block naming scope; avoid duplicate declarations | Anonymous class has its own class scope |
| Capturing local variables | Only captures final/effectively final variables | Also only captures final/effectively final local variables |
| Callback retaining reference to outer | Possible when lambda uses `this` receiver / instance fields | Possible when anonymous class references enclosing instance |
| Ability to write multiple methods | Target functional interface has one SAM | Anonymous class can implement types with multiple abstract methods |
| Accessing `this::method` | Bound to outer receiver | Inside body, bound to anonymous receiver if using `this::method` |

**A note on methods inside an anonymous class:** If an anonymous class declares its own method, `this.method()` inside it can call the anonymous class's own method. When converted to a lambda, `this.method()` looks up a member of the enclosing class instead; the code may fail to compile or change behavior.

Therefore, refactoring anonymous class → lambda requires checking the **receiver**, selected members, variable names, and callback purpose. Do not judge a refactoring solely by fewer lines of code.

## 9. `this` in a Lambda Does Not Mean Thread-Safe

A lambda can retain the receiver and access instance fields, yet **it does not automatically synchronize** those accesses. If a callback is passed to another thread or executor, mutable fields can create data races without proper synchronization.

Illustrative example:

~~~java
class Counter {
    private int value;

    Runnable incrementAction() {
        return () -> value++;
    }
}
~~~

This is an illustrative class definition snippet. `value++` performs read, add, and write; it is not an atomic increment. If multiple threads run the callback on the same `Counter`, results can miss increments and violate expectations. Switching to a lambda or using `this.value++` does not make the operation safer.

When a callback can run across multiple threads, consider `AtomicInteger`, synchronization, immutable design, or an appropriate coordination mechanism. The **effectively final** rule for captured local variables does not make referenced objects immutable either.

## 10. Capturing `this`, Callback Lifecycle, and Risks of Retaining Instances Too Long

A callback created from an instance method can outlive the call that created it:

~~~java
import java.util.function.Supplier;

class SessionView {
    private final String id;

    SessionView(String id) {
        this.id = id;
    }

    Supplier<String> snapshotLabel() {
        String snapshot = id;
        return () -> snapshot;
    }

    Supplier<String> liveLabel() {
        return () -> this.id;
    }
}
~~~

This is a **class illustration snippet**, not a standalone program. Both methods can return corresponding strings, but their capture semantics differ:

- `snapshotLabel()` holds the **local variable** `snapshot`. The lambda does not need to access `this` in its body to read that value.
- `liveLabel()` references the field via `this`, so the callback may retain the receiver to read the field when invoked.

**You must not infer that every lambda created in an instance method necessarily retains `this`**. A lambda that only uses constants or copied local variables may not need to retain the receiver. Conversely, a lambda accessing instance fields or instance methods needs the corresponding receiver.

If a listener is registered with a long-lived object (event bus, scheduler, static registry) and holds a callback referencing `this`, the instance containing the listener can be kept alive longer than intended. The solution is to manage registration/unregistration by lifecycle, avoid unnecessary receiver capture, or use an appropriate ownership model. Similarly, be careful when publishing `this` via a callback inside a constructor before the object is fully initialized.

## 11. `super` with Interface Default Methods: A Variant to Know

Beyond superclasses, Java also has the syntax **`InterfaceName.super.method()`** to call a specific interface default method when language rules allow. When a lambda expression is in a valid instance context, that syntax is still based on the **enclosing class**.

Example in a class directly implementing an interface:

~~~java
interface Greeter {
    default String message() {
        return "default";
    }
}

class FriendlyGreeter implements Greeter {
    String greeting() {
        Supplier<String> fromDefault =
                () -> Greeter.super.message();
        return fromDefault.get();
    }
}
~~~

This is an **illustrative snippet**, requiring `java.util.function.Supplier` imported. In `FriendlyGreeter`, `Greeter.super.message()` selects the default method of interface `Greeter` according to Java rules. It does not refer to another "interface instance."

Do not use `InterfaceName.super` arbitrarily: rules regarding **superinterfaces**, default method inheritance, and call sites still apply. If there is a default method conflict from multiple interfaces, the implementing class must resolve the conflict according to Java rules before a call inside a lambda has valid meaning.

In a foundational lesson on class inheritance, focus first on the difference between `this.method()` and `super.method()`; the syntax for default methods is a useful extension when studying advanced interfaces.

## 12. Common Errors and How to Diagnose Them

| Situation | Issue | How to handle |
| --- | --- | --- |
| Thinking `this` in a lambda is the functional interface object | Calling the wrong field/method or misexplaining the receiver | Look at the lambda declaration site and enclosing class |
| Converting anonymous class to lambda while keeping `this.method()` | Receiver changes; behavior or compilation changes | Use `Outer.this` when outer is truly needed, or review the contract |
| Writing `super.method()` inside `new Runnable(){...}` to call outer's parent | `super` belongs to the anonymous class, usually lacking the desired method | Put the call in an outer method or adjust the design |
| Writing `this` / `super` in a static method's lambda | No instance context | Pass receiver as a parameter or use static members |
| Assuming `this::method` and `super::method` are equivalent | May call different implementations when overridden | Clarify the dispatch target |
| Thinking `this` is like a captured local variable that must be effectively final | Confusing capture rules with receivers | Distinguish local variables from instance fields |
| Using a lambda parameter name matching an outer local variable | Redeclaration/shadowing error | Rename the parameter or local variable |
| Lambda callback updating a mutable field from multiple threads | Data race or lost updates | Use synchronization/atomics/immutable design |
| Long-lived listener retaining `this` unintentionally | Instance may be kept alive too long | Manage listener lifecycle and minimize unnecessary capture |
| Calling `super` to bypass access restrictions | Java still enforces access control | Check `protected`/`public` and inheritance rules |

A self-review checklist at the lambda writing site:

1. **Is the lambda inside an instance method, constructor, or static context?**
2. **Which class encloses the expression at the writing site?** That determines `this` and `super`.
3. **Is the called member overridden?** `this.method()` and `super.method()` can produce different results.
4. **Is there an anonymous class nested around the lambda?** If the lambda is written inside a method of an anonymous class, the nearest `this` context belongs to that anonymous class.
5. **Can the callback run later or on another thread?** If so, check receiver lifetime and state safety.
6. **Refactoring from an anonymous class?** Carefully check every place with `this`, `super`, field/method names, and local variables.

## 13. Practice Exercises

### Exercise 1: Predict stdout

Based on `LambdaThisSuperDemo`, explain in order the lines **lambda this: child**, **lambda super: parent**, **anonymous this==outer: false**, and **anonymous outer: child**. Why do the two bodies have different `this` even though both are written inside `demonstrate()`?

### Exercise 2: Compare two method references

Change `BoundMethodReferenceDemo`'s `message()` implementation to return **"new child"**. Predict which lines change and which lines remain **"from base"**. Then change `current = this::message` to `() -> this.message()` and check whether the output changes.

### Exercise 3: Find the compile error

Explain why this snippet is invalid:

~~~java
// Intentionally non-compiling snippet.
static Runnable invalid() {
    return () -> System.out.println(this);
}
~~~

How should it be fixed if the callback must display information about an object passed to the static method?

### Exercise 4: Distinguish snapshot from live reference

With a class having a mutable `String label` field, compare callback `() -> label` (reading the field) with `() -> snapshot` (a local variable copied from the field earlier). Modify the field after creating the callback and verify your prediction. Consider the scenario where the callback is stored in a long-lived registry.

### Exercise 5: Review thread safety

Given a callback `() -> counter++` referencing an instance's `counter` field, explain why running the callback from two threads is unsafe. Create a version using `AtomicInteger.incrementAndGet()` and compare the semantics.

## 14. Key Takeaways

- Lambdas use **lexical `this` and `super`**: both keywords keep their meaning from where the lambda is written, not pointing to a "lambda object."
- An anonymous class has its **own `this`**; `super` inside it also belongs to the anonymous class's inheritance context.
- `this::method` and `super::method` can refer to **different implementations**, even though both are valid method references for a SAM.
- A lambda in a **static context** has no instance `this` or `super`; pass a receiver when behavior depends on an object.
- Local variables captured by a lambda must be **final/effectively final**; that rule differs from accessing instance fields via `this`.
- When a lambda retains a receiver, you must consider **callback/listener lifecycles, side effects, and thread safety**.

When encountering an error or surprise about the receiver in a callback, do not start from where the lambda **is run**. Identify the class and context where the lambda expression **is written**; that is the key to understanding `this` and `super` accurately in Java.