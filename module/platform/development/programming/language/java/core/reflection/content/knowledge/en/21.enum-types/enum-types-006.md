# Do not create extra enum constants with Constructor.newInstance

## 1. An enum is not a regular class with a private constructor

An enum declares a set of named constants. For example:

~~~java
enum Phase {
    READY, DONE;
}
~~~

In this declaration, `READY` and `DONE` are the constants of `Phase`. The corresponding objects are created during enum class initialization.

When learning Reflection, it is easy to reason that:

1. An enum has a constructor.
2. That constructor is not `public`.
3. If you retrieve the constructor and open access, you can call `newInstance()` to create `EXTRA`.

**The reasoning in step 3 is incorrect.** `Constructor.newInstance()` has a dedicated rule: if the constructor belongs to an enum class, object creation is rejected with `IllegalArgumentException`. This is not merely an issue of the constructor having the `private` modifier.

The rule is recorded in the [Constructor.newInstance](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)) contract. [JLS §8.9](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9) also states that enum instances cannot be created via Reflection.

This lesson focuses on distinguishing **inspecting constructors**, **adjusting access checks**, and **being permitted to instantiate objects**. Achieving the first two does not mean the third is allowed.

## 2. Why does an enum still have constructors?

An enum's constructor serves to initialize its declared constants. It can take custom data, assign fields, and execute initialization logic just like regular Java code.

The following example is a standalone enum declaration:

~~~java
enum Severity {
    LOW(1),
    HIGH(5);

    private final int score;

    Severity(int score) {
        this.score = score;
    }
}
~~~

When the constants are initialized, `LOW` receives the data `1`, and `HIGH` receives `5`. That does not create an API for external code to call `new Severity(3)`.

A few rules to remember:

- You cannot use the `new` expression to instantiate an enum class yourself.
- An enum constructor cannot be declared `public` or `protected`.
- An enum constructor with no written access modifier is treated as `private`.
- Reflection being able to see the constructor does not change the rules of enums.

In particular, `private` and "cannot create extra enum instances with `Constructor.newInstance()`" are two different constraints. The next experiment separates them clearly.

## 3. Complete experiment: same access unlocking, different outcomes

Save the entire code below into `EnumConstructorDemo.java`. Only the `EnumConstructorDemo` class is `public`; the supporting top-level classes and enum reside in the same file.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import java.util.Arrays;

final class PlainItem {
    private PlainItem() {
    }
}

final class PhaseConstructionCount {
    static int count;
}

enum Phase {
    READY, DONE;

    private Phase() {
        PhaseConstructionCount.count++;
    }
}

public class EnumConstructorDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<PlainItem> plain =
                PlainItem.class.getDeclaredConstructor();

        System.out.println("plain private: "
                + Modifier.isPrivate(plain.getModifiers()));
        System.out.println("plain accessible before: "
                + plain.canAccess(null));
        System.out.println("plain access enabled: "
                + plain.trySetAccessible());
        System.out.println("plain created: "
                + (plain.newInstance() != null));

        System.out.println("enum public constructors: "
                + Phase.class.getConstructors().length);

        try {
            Phase.class.getDeclaredConstructor();
            throw new AssertionError("Unexpected no-arg constructor");
        } catch (NoSuchMethodException expected) {
            System.out.println("enum no-arg lookup: NoSuchMethodException");
        }

        Constructor<Phase> constructor =
                Phase.class.getDeclaredConstructor(String.class, int.class);

        System.out.println("enum parameters: "
                + Arrays.toString(constructor.getParameterTypes()));
        System.out.println("enum private: "
                + Modifier.isPrivate(constructor.getModifiers()));
        System.out.println("enum accessible before: "
                + constructor.canAccess(null));
        System.out.println("enum access enabled: "
                + constructor.trySetAccessible());
        System.out.println("enum accessible after: "
                + constructor.canAccess(null));

        System.out.println("values before: "
                + Arrays.toString(Phase.values()));
        int callsBefore = PhaseConstructionCount.count;
        System.out.println("constructor calls before: " + callsBefore);

        try {
            constructor.newInstance("EXTRA", 2);
            throw new AssertionError("Enum construction unexpectedly succeeded");
        } catch (IllegalArgumentException expected) {
            System.out.println("enum newInstance: IllegalArgumentException");
        }

        System.out.println("constructor body unchanged: "
                + (PhaseConstructionCount.count == callsBefore));
        System.out.println("values after: "
                + Arrays.toString(Phase.values()));

        try {
            Enum.valueOf(Phase.class, "EXTRA");
            throw new AssertionError("Unexpected EXTRA constant");
        } catch (IllegalArgumentException expected) {
            System.out.println("lookup EXTRA: IllegalArgumentException");
        }

        System.out.println("lookup READY identity: "
                + (Enum.valueOf(Phase.class, "READY") == Phase.READY));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 EnumConstructorDemo.java
java EnumConstructorDemo
~~~

Exact output when run with the commands above on a standard classpath:

~~~text
plain private: true
plain accessible before: false
plain access enabled: true
plain created: true
enum public constructors: 0
enum no-arg lookup: NoSuchMethodException
enum parameters: [class java.lang.String, int]
enum private: true
enum accessible before: false
enum access enabled: true
enum accessible after: true
values before: [READY, DONE]
constructor calls before: 2
enum newInstance: IllegalArgumentException
constructor body unchanged: true
values after: [READY, DONE]
lookup EXTRA: IllegalArgumentException
lookup READY identity: true
~~~

The program prints the exception types without depending on the verbatim error message of a particular JDK version.

`PlainItem` and `Phase` are top-level types separate from the class containing `main()`. Putting them there clearly demonstrates that the `private` constructors are inaccessible before calling `trySetAccessible()`.

### 3.1. A regular class can be instantiated after enabling access

For `PlainItem`:

- The constructor is `private`.
- Before enabling access, `canAccess(null)` returns `false`.
- In the experiment's environment, `trySetAccessible()` returns `true`.
- `plain.newInstance()` creates an object.

This serves as a control sample for the statement "a private constructor can be invoked when access conditions permit". It does not generalize to enums.

### 3.2. An enum is still rejected even after enabling access

For `Phase`'s constructor, the program also confirms:

~~~text
enum private: true
enum accessible before: false
enum access enabled: true
enum accessible after: true
~~~

Immediately afterward, the call:

~~~java
constructor.newInstance("EXTRA", 2);
~~~

still throws `IllegalArgumentException`.

Thus, the failure does not stem from failing to unlock access to the constructor in this experiment. Accessibility has been proven to be enabled; the rule prohibiting enum instantiation still remains in effect.

`canAccess(null)` only asks whether the current caller can access that Reflection object. It does not ask whether every subsequent execution operation is semantically valid. For a constructor, the argument to `canAccess` must be `null`; it is not an object that will receive a method call.

### 3.3. The constructor body is not invoked again

To observe this, `Phase`'s constructor increments a counter located in a separate helper class:

~~~java
private Phase() {
    PhaseConstructionCount.count++;
}
~~~

Before testing extra instantiation, the program calls `Phase.values()` to initialize the two existing constants. Therefore, the counter is `2`.

After the rejected `newInstance()` attempt:

- The counter stays unchanged.
- `Phase.values()` still contains only `READY` and `DONE`.
- Looking up `EXTRA` with `Enum.valueOf(...)` still fails.

Placing the counter outside the enum also avoids mixing the experiment with special rules on accessing static fields during enum initialization.

## 4. Why does looking up a no-arg constructor fail?

The source code may show:

~~~java
private Phase() {
    PhaseConstructionCount.count++;
}
~~~

yet the constructor metadata in the class file generated by `javac` in this example has the parameters:

~~~text
[class java.lang.String, int]
~~~

They serve the constant's name and ordinal position. The base `Enum` class constructor accepts `name` and `ordinal`; these values are supplied by compiler-generated code.

Therefore, in the experiment:

~~~java
Phase.class.getDeclaredConstructor();
~~~

does not find a constructor with an empty parameter type list and throws `NoSuchMethodException`.

The lookup matching the observed metadata is:

~~~java
Phase.class.getDeclaredConstructor(String.class, int.class);
~~~

**Finding the signature does not mean it can be called to create an enum.** The example passed two arguments of matching types and was still blocked.

If an enum has author-declared parameters, such as `Severity(int score)`, the metadata generated by `javac` typically shows the helper parameters before `score`. When inspecting constructors, check `getParameterTypes()` and the actual class file metadata rather than guessing from the parameter count visible in source code. Do not use the first element of `getDeclaredConstructors()` as a rule for picking a constructor when an enum has multiple constructors.

You should also not rely on parameter names like `arg0` or compiler-assigned internal names. Compiler options and metadata can affect how parameter names are reflected.

`String.class` and `int.class` in the example are **types used to look up the signature**. Passing `Integer.class` instead of `int.class` to `getDeclaredConstructor(...)` is not the same lookup. The fact that `newInstance()` supports argument conversions at invocation time does not make the constructor lookup API select a different signature automatically.

## 5. Distinguishing operations and error categories

| Operation or situation | Meaning and result to distinguish |
| --- | --- |
| `getConstructors()` | Returns only `public` constructors; the enum in the example yields an empty array |
| `getDeclaredConstructor(...)` | Finds a constructor declared in the class, including private constructors; mismatched signature causes `NoSuchMethodException` |
| Constructor not yet accessible | When invoked, may hit `IllegalAccessException` |
| `trySetAccessible()` | Attempts to allow bypassing access checks under Java's conditions; success does not bypass the enum prohibition |
| `setAccessible(true)` disallowed by the environment | May hit `InaccessibleObjectException` or the corresponding security check |
| `newInstance()` on an accessible enum constructor | Enum instantiation is rejected with `IllegalArgumentException` |
| Calling with wrong argument count or types | Can also cause `IllegalArgumentException`; do not infer from the exception name alone that it is always due to enum |
| Valid constructor body throws an exception itself | Normally an exception from the constructor body is wrapped in `InvocationTargetException` |

The table helps pinpoint the issue at the exact operation. Do not lump all Reflection failures into "constructor not found" or "missing permission".

### IllegalArgumentException here is not an exception from the constructor body

In the experiment, Reflection refuses to create the enum object; the constructor body does not run again. Therefore, there is no exception thrown by the `Phase()` constructor body itself and wrapped.

If you only catch:

~~~java
// Illustrative snippet of a catch block insufficient to handle the enum case.
catch (java.lang.reflect.InvocationTargetException ex) {
    System.out.println(ex.getCause());
}
~~~

then `IllegalArgumentException` raised by the enum prohibition rule is not handled. The snippet above is only an illustrative `catch` branch and must be placed after an appropriate `try` block when used in Java code.

In applications, read the error together with the **type being constructed**, the **looked-up constructor**, **accessibility**, and the **actual arguments**. Do not inspect only the exception message string.

## 6. setAccessible is not a switch to bypass all constraints

`setAccessible(true)` and `trySetAccessible()` operate on Reflection's access checks, within limits permitted by the module system and environment.

They do not:

- Add a constant to an enum declaration.
- Turn an enum class into a regular class.
- Change the number or types of constructor parameters.
- Make creating an enum via `Constructor.newInstance()` a valid operation.

The experiment uses types defined by the program itself on the classpath, so unlocking access succeeds. When inspecting a type in another module, unlocking access can fail before even reaching the question of object instantiation.

The [AccessibleObject.trySetAccessible](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html#trySetAccessible()) documentation describes the limits of this operation. If access can be enabled, the enum rule still holds; changing package-opening configuration is not a fix for the enum instantiation prohibition.

You must also distinguish **readable metadata** from **executable operations**. A tool can display enum constructors for inspecting signatures, annotations, or bytecode without needing and without being allowed to create extra constants via this API.

## 7. "Retrieving an existing constant" differs from "creating a new constant"

When an enum value is needed from input data, the real goal is usually to select an already-declared constant.

For example, in the context of the program above:

~~~java
Phase ready = Enum.valueOf(Phase.class, "READY");
System.out.println(ready == Phase.READY);
~~~

Output:

~~~text
true
~~~

`Enum.valueOf` does not call the constructor to create another `READY`. It returns the existing constant bearing the exact declared name.

If the name is `EXTRA`, the API throws `IllegalArgumentException` because the enum does not declare that constant. It does not auto-generate a new constant and does not add a constant to `values()`.

| Need | Suitable representation |
| --- | --- |
| Select a constant whose name is known when writing code | `Phase.READY` |
| Convert a declared name into an existing constant | `Enum.valueOf(Phase.class, name)` or `Phase.valueOf(name)` |
| List constants when the enum is known at compile time | `Phase.values()` |
| List when only a class token is available | `enumType.getEnumConstants()` |
| Add a constant to an enum model | Change the enum declaration and rebuild the program |
| Value set needs additions or removals at runtime | An extensible data model, such as a class or record combined with a registry |

When reading names from input, have a policy for handling invalid names, case differences, or display labels. `Enum.valueOf` uses the exact declared name, not customized strings from `toString()`. The API rules are stated at [Enum.valueOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)).

Do not use Reflection constructors as a fallback branch when `valueOf` does not find a name. Those two things are not equivalent.

## 8. Impact on general-purpose object creation tools

A Reflection-based data mapper or factory should not process enums via a branch that "finds a no-arg constructor and creates an object".

For enums, a **constant selection rule** based on data is normally needed: the declared name, a defined business code, or an application-provided mapping.

An illustrative method for a default object-creation branch can reject enums right at the start:

~~~java
// Helper method; place inside a class and add import java.util.Objects.
static <T> T createDefault(Class<T> type)
        throws ReflectiveOperationException {
    Objects.requireNonNull(type, "type");

    if (type.isEnum()) {
        throw new IllegalArgumentException(
                "Supply an existing enum constant: " + type.getName());
    }

    return type.getDeclaredConstructor().newInstance();
}
~~~

This method only illustrates the policy of not creating enums via constructors. For regular classes, it still requires an accessible no-arg constructor; it does not by itself solve every case of an object-creation framework.

Example call when adding the method to the sample program:

~~~java
System.out.println(createDefault(StringBuilder.class).length());

try {
    createDefault(Phase.class);
} catch (IllegalArgumentException expected) {
    System.out.println("enum requires an existing constant");
}
~~~

Output for the added snippet alone:

~~~text
0
enum requires an existing constant
~~~

Checking early helps the tool choose the right handling path instead of repeatedly trying parameter combinations or unlocking access only to hit the same Reflection prohibition rule again.

## 9. Common misconceptions

**"An enum has no constructor, so Reflection cannot instantiate it."** An enum does have constructors and can be inspected via Reflection. The restriction lies in creating instances with `Constructor.newInstance()`, not in the existence of constructors.

**"You just need setAccessible(true) because enum constructors are private."** Enabling access does not override the specific rule prohibiting enum instantiation.

**"Passing the name and ordinal as extra arguments will create a new constant."** Those helper arguments explain the compiler-generated signature. They are not an API for extending the enum constant set.

**"NoSuchMethodException and IllegalArgumentException are the same error."** One occurs when a constructor signature is not found; the other in the experiment occurs when invoking a constructor that was found.

**"If canAccess returns true, newInstance is guaranteed to succeed."** Access permission is only one condition. Enums are still rejected; regular classes can also fail for other conditions or because the constructor body throws an exception.

**"Changing the error message or catching InvocationTargetException will let you create an enum."** Exception handling only handles a failed result; it does not turn a prohibited operation into a valid one.

**"ValueOf creates a new enum for the requested name."** It selects an already-existing constant; it does not create or register additional constants.

## 10. Self-check

1. Why can the program obtain `Constructor<Phase>` yet fail to create `EXTRA`?
2. In the experiment, what evidence shows that enabling access succeeded?
3. Why does calling the no-arg `getDeclaredConstructor()` fail to find a constructor in the `javac`-compiled example?
4. Is the enum creation error after enabling access wrapped in `InvocationTargetException` like an exception from a constructor body?
5. Why is seeing `IllegalArgumentException` alone not enough to conclude the cause is an enum?
6. After attempting to create `EXTRA`, how do the constructor counter and `Phase.values()` change?
7. To obtain `READY` from the string `"READY"`, which API should be called?
8. If a business catalog must add elements at runtime, should you try to invoke an enum constructor to do so?

Answers:

1. Constructor metadata exists; the `Constructor.newInstance()` contract prohibits creating enum instances.
2. `trySetAccessible()` returns `true` and `canAccess(null)` afterward also returns `true`.
3. Metadata in the example has two helper parameters `String` and `int`; an empty parameter-list lookup does not match.
4. Not in this experiment. Reflection rejects with `IllegalArgumentException` before executing the enum constructor body again.
5. Because an error in argument count or types can also raise that exception type; you must check the context.
6. The counter stays at `2`; the constant list remains `[READY, DONE]`.
7. Use `Enum.valueOf(Phase.class, "READY")` or `Phase.valueOf("READY")`; the result is the existing constant.
8. No. Use a data model that allows the set of values to change at runtime.
