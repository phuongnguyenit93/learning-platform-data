# Reflection: Reading static, final, abstract, synchronized, native, and strictfp Flags

In Java, the keywords `static`, `final`, `abstract`, `synchronized`, `native`, and `strictfp` express characteristics of a class, method, or field. When using Reflection, we do not search for keywords in source-code strings; we read the **modifier bitmask** from a `Class`, `Method`, `Field`, or `Constructor` object, then use `java.lang.reflect.Modifier` to check each flag.

This lesson focuses on the question: **which element is a modifier present on, what does it mean, and how does Reflection check it?** You must distinguish characteristics recorded in metadata from runtime JVM effects; in particular, `strictfp` changed meaning in Java 17+.

## 1. How does the modifier bitmask work in Reflection?

Typical APIs:

```java
Class<?> type = SomeClass.class;
int classFlags = type.getModifiers();

java.lang.reflect.Method method =
        type.getDeclaredMethod("someMethod");
int methodFlags = method.getModifiers();

java.lang.reflect.Field field =
        type.getDeclaredField("someField");
int fieldFlags = field.getModifiers();
```

This is an illustrative snippet: `SomeClass`, `someMethod`, and `someField` must be declared in an actual program. All three `getModifiers()` calls return `int`, but each value belongs to a different **element context**.

Each constant in `Modifier` represents a distinct bit, such as `Modifier.STATIC`, `Modifier.FINAL`, `Modifier.ABSTRACT`, `Modifier.SYNCHRONIZED`, `Modifier.NATIVE`, and `Modifier.STRICT`. An element can carry multiple bits, combined using the bitwise OR operator `|`.

```java
int flags = Modifier.PUBLIC | Modifier.STATIC | Modifier.FINAL;

boolean isStatic = Modifier.isStatic(flags);   // true
boolean isFinal = Modifier.isFinal(flags);     // true
boolean isAbstract = Modifier.isAbstract(flags); // false

boolean sameStaticCheck = (flags & Modifier.STATIC) != 0; // true
String labels = Modifier.toString(flags); // "public static final"
```

The illustrative snippet requires `import java.lang.reflect.Modifier;`. `isXxx(flags)` makes code clearer in intent than `&` expressions; the `&` operator remains useful when combining or filtering bitmasks.

Key points:

- **`getModifiers()` does not return a single modifier name.** It returns a set of flags encoded in an integer.
- **`Modifier.toString(flags)` is for presentation**, not for checking the validity rules of a declaration. It can still print a string from a nonsensical combined bitmask.
- **Context determines bit meaning.** Some class-file bits have different meanings on different element kinds (for example, the bit representing `synchronized` on a method differs from class-related flags). Do not pass modifiers from one element kind into a check method for another kind and infer results.
- When you need to filter by the set of modifiers valid for an element kind, you can use `Modifier.classModifiers()`, `interfaceModifiers()`, `fieldModifiers()`, `methodModifiers()`, or `constructorModifiers()`. These are **masks for source-language modifiers**, not an automatic validator for all combination rules and every technical class-file flag.

### APIs to retrieve metadata before inspecting modifiers

| Reflection source | Modifiers read | Notes |
| --- | --- | --- |
| `Class.getModifiers()` | Modifiers of the type (class/interface/nested class) | `static` is meaningful for a member nested class; a top-level class cannot be declared `static` |
| `Method.getModifiers()` | Modifiers of a specific method | Used to check `static`, `final`, `abstract`, `synchronized`, `native`; `strictfp` requires understanding the class-file version |
| `Field.getModifiers()` | Modifiers of a specific field | Often interested in `static`, `final` along with other flags such as `volatile` or `transient` |
| `Constructor.getModifiers()` | Modifiers of a constructor | Primarily checks access levels; a constructor cannot be `static`, `final`, `abstract`, `synchronized`, or `native` |

Choose `getDeclaredMethod(...)`/`getDeclaredField(...)` when you want members **declared directly on the class**, including non-public members; choose `getMethod(...)`/`getField(...)` if you want to find **public** members following inheritance rules. Having metadata does not automatically grant permission to invoke or access the member.

## 2. Six modifiers to understand

| Modifier | Common applicability | Reflection check | Meaning |
| --- | --- | --- | --- |
| `static` | Field, method, member nested class | `Modifier.isStatic(flags)` | Member bound to the class; for a nested class, no enclosing class instance is needed |
| `final` | Class, method, field | `Modifier.isFinal(flags)` | Disallows subclassing a class, overriding a method, or reassigning a field after proper initialization |
| `abstract` | Class, method | `Modifier.isAbstract(flags)` | Class may be incomplete; abstract method declares a contract without a body |
| `synchronized` | Method | `Modifier.isSynchronized(flags)` | When invoking the method, the JVM performs monitor synchronization across the entire method |
| `native` | Method | `Modifier.isNative(flags)` | Method has no Java code body; implementation is bound to native code |
| `strictfp` | Class, interface, method in legacy source | `Modifier.isStrict(flags)` | Historical flag related to floating-point math; since Java 17 it no longer alters computation and is not stored as before in new class files |

The "Common applicability" column describes usual syntactic scope; not every combination in the table is legal. For example, an `abstract` method cannot simultaneously be `static`, `final`, `synchronized`, or `native`.

## 3. static: class members and static nested classes

A **`static` field** has one class-level value (per corresponding loaded `Class`), not a separate copy on each instance. A **`static` method** is invoked via the class name and has no `this` receiver; it undergoes **hiding** when a subclass declares a static method with the same signature, rather than polymorphic overriding like an instance method.

```java
class Counter {
    static int total;
    static void reset() {
        total = 0;
    }
}
```

Checking:

```java
java.lang.reflect.Field total =
        Counter.class.getDeclaredField("total");
java.lang.reflect.Method reset =
        Counter.class.getDeclaredMethod("reset");

System.out.println(Modifier.isStatic(total.getModifiers())); // true
System.out.println(Modifier.isStatic(reset.getModifiers())); // true
```

This illustrative snippet depends on the `Counter` class above and `import java.lang.reflect.Modifier;`; calling code must handle or declare the checked exceptions from `getDeclaredField`/`getDeclaredMethod`.

If a class is a **member nested class** declared `static`:

```java
class Envelope {
    static class Item {
    }
}
```

then `Modifier.isStatic(Envelope.Item.class.getModifiers())` returns `true`. A top-level class such as `Envelope` does not carry the `static` modifier. Nested interfaces can be **implicitly static**, so do not merely look for the word `static` in source code to infer the Reflection value. Conversely, a `static` initializer block is not represented by a regular `Method` object that an application can look up with `getDeclaredMethod("<clinit>")`.

For `Method.invoke`, a static method needs no instance receiver: you can pass `null` for the object argument; for an instance method, a suitable receiver and access permission are required.

## 4. final: different meanings on classes, methods, and fields

**On a class:** `final class X` cannot have subclasses in Java. **On an instance method:** `final` forbids subclasses from overriding that method. **On a field:** the field value cannot be reassigned after initialization completes per Java language rules.

```java
final class ServiceConfig {
    static final int RETRY_LIMIT = 3;

    final String identity() {
        return "service";
    }
}
```

With Reflection, the same `Modifier.isFinal` method checks the `final` flag in all three places:

```java
Class<?> t = ServiceConfig.class;
boolean finalClass = Modifier.isFinal(t.getModifiers());

java.lang.reflect.Method m =
        t.getDeclaredMethod("identity");
boolean finalMethod = Modifier.isFinal(m.getModifiers());

java.lang.reflect.Field f =
        t.getDeclaredField("RETRY_LIMIT");
boolean finalField = Modifier.isFinal(f.getModifiers());
```

This is an illustrative snippet requiring imports and exception handling similar to section 3.

**Do not infer an "immutable object" solely from `final`.** A `final List<String>` prevents reassigning the field reference in normal Java code, but the contents of the `List` can still change. `static final` does not automatically turn every field into a compile-time constant; whether it can be inlined depends on the type and constant initializer expression.

With Reflection, `final` is a marker to respect in the data model; you should not design logic around arbitrarily mutating `final` fields via reflective access. Access rules, inlining, modules, and modern JDKs can make such behavior unavailable or unpredictable.

## 5. abstract: bodyless contracts and types that cannot be directly instantiated

An `abstract` class cannot be instantiated directly with `new`; it may contain both abstract methods and implemented methods. An `abstract` method declares its name, parameters, return type, and exceptions in its signature, without providing a Java body.

```java
abstract class Shape {
    abstract double area();

    String category() {
        return "shape";
    }
}
```

`Modifier.isAbstract(Shape.class.getModifiers())` returns `true`, and `Modifier.isAbstract(Shape.class.getDeclaredMethod("area").getModifiers())` also returns `true`.

Some verification points:

- A class can be marked `abstract` even without declaring any abstract methods; `Modifier.isAbstract(classFlags)` and "has a direct abstract method" are two different questions.
- An abstract method has no body; an abstract method cannot be invoked directly without a concrete implementation on the receiver. When a subclass implements the method, a `Method` retrieved from the superclass can be invoked on an appropriate subclass instance and dispatch to the implementation.
- A method cannot be `abstract` and at the same time `private`, `static`, `final`, `synchronized`, `native`, or `strictfp`.
- Interfaces are inherently abstract types, yet **not every method of an interface is abstract**: an interface can have `default`, `static`, and `private` methods. Read the modifiers of **each method** rather than inferring from the class's `isInterface()`.

## 6. synchronized: reflects only the synchronization declaration on a method

An **instance `synchronized` method** locks the receiver's (`this`) monitor while the method runs. A **static `synchronized` method** locks the monitor associated with the `Class` object declaring the method. These are two different monitors; `synchronized` is only meaningful if contending threads use the appropriate shared monitor.

```java
class BankAccount {
    private int balance;

    public synchronized void deposit(int amount) {
        balance += amount;
    }

    public static synchronized void audit() {
        // Synchronized on BankAccount.class
    }

    public void withdraw(int amount) {
        synchronized (this) {
            balance -= amount;
        }
    }
}
```

Reflection:

```java
java.lang.reflect.Method deposit =
        BankAccount.class.getDeclaredMethod("deposit", int.class);
java.lang.reflect.Method audit =
        BankAccount.class.getDeclaredMethod("audit");
java.lang.reflect.Method withdraw =
        BankAccount.class.getDeclaredMethod("withdraw", int.class);

System.out.println(Modifier.isSynchronized(deposit.getModifiers())); // true
System.out.println(Modifier.isSynchronized(audit.getModifiers()));   // true
System.out.println(Modifier.isSynchronized(withdraw.getModifiers())); // false
```

This illustrative snippet requires imports and handling checked exceptions from lookup. The last line's `false` **does not mean `withdraw` performs no synchronization**: a synchronized block inside a method body does not cause the method to carry the `ACC_SYNCHRONIZED` flag. Reflection modifiers only capture method declaration metadata, not every bytecode instruction or locking policy.

A `synchronized` method does not automatically make all surrounding operations thread-safe: correctness also depends on other access paths, invariants, and using the same monitor. When `Method.invoke` runs a synchronized method, the call still obeys that method's synchronization semantics.

## 7. native: a method without a Java body

A `native` method is typically a bridge to an implementation outside Java, for example via the Java Native Interface (JNI). It has only a method declaration, with no Java body:

```java
class NativeBridge {
    public static native int calculate(int input);
}
```

After obtaining the `Method`:

```java
java.lang.reflect.Method method =
        NativeBridge.class.getDeclaredMethod("calculate", int.class);

boolean nativeMethod = Modifier.isNative(method.getModifiers()); // true
boolean staticMethod = Modifier.isStatic(method.getModifiers()); // true
```

This illustrative snippet requires imports and handling checked exceptions from lookup. Merely **reading metadata** of `NativeBridge.calculate` does not require the native implementation to be available. However, **invoking a native method without a linked implementation** can lead to `UnsatisfiedLinkError` (when invoked through Reflection, an error from the method can be wrapped in `InvocationTargetException`).

`native` does not mean a method is necessarily faster than Java, safer, or automatically allowed to access every resource. It only describes the form of the implementation. Library loading restrictions, native linking, and JDK configuration still need to be handled independently.

## 8. strictfp: legacy heritage and important change since Java 17

Before Java 17, `strictfp` forced `float`/`double` computations within a given scope to follow strict floating-point semantics. Java 17 restored **always-strict** semantics per JEP 306: floating-point operations obey the same strict rules regardless of whether the `strictfp` keyword is present.

Consequences when reading modifiers with Reflection:

1. `Modifier.STRICT` and `Modifier.isStrict(int)` remain **bit**-decoding APIs. If you manually construct the bitmask `Modifier.PUBLIC | Modifier.STRICT`, `isStrict` will return `true`, because the bit is present.
2. **That does not mean a method compiled by JDK 17+ will carry the strict flag.** Per JVMS 17, the `ACC_STRICT` bit is only interpreted as `strictfp` in class files with major version **46 through 60**. For class files with major version **61+** (Java 17+), that bit no longer carries the `ACC_STRICT` meaning; newly compiled code does not need to emit it.
3. Consequently, even if Java 17+ source code writes `strictfp`, `Modifier.isStrict(method.getModifiers())` usually returns `false`. **You cannot use `false` to prove that the source did not contain the `strictfp` keyword.**
4. `strictfp` is an obsolete keyword that modern compilers may warn on; do not add it to new Java code to "increase the accuracy" of floating-point calculations. When reading older class files, always consider the class-file version before inferring the strict flag.

Illustrative example of **historical source code**, not required to run:

```java
strictfp class OldCalculation {
    strictfp double half(double input) {
        return input / 2.0;
    }
}
```

On Java 17+, the keyword above does not change the result of `input / 2.0`. Pure Reflection only sees metadata stored in the class file; if you need to know accurately **whether a keyword appeared in source**, you must parse source code or appropriate specialized metadata rather than inferring backwards solely from `getModifiers()`.

## 9. Complete Java 17+ program: checking all six flags

Create the file `ModifierFlagsDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ModifierFlagsDemo {
    static abstract class Task {
        abstract int calculate(int number);

        final String kind() {
            return "task";
        }
    }

    static final class IncrementTask extends Task {
        public static final int STEP = 1;

        @Override
        int calculate(int number) {
            return number + STEP;
        }

        public synchronized int run(int number) {
            return calculate(number);
        }

        // Only a native declaration: the example never calls this method.
        public static native void nativeEntry();
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> taskClass = Task.class;
        Class<?> implClass = IncrementTask.class;

        Method abstractMethod =
                taskClass.getDeclaredMethod("calculate", int.class);
        Method finalMethod = taskClass.getDeclaredMethod("kind");
        Method synchronizedMethod =
                implClass.getDeclaredMethod("run", int.class);
        Method nativeMethod =
                implClass.getDeclaredMethod("nativeEntry");
        Field stepField = implClass.getDeclaredField("STEP");

        System.out.println("Task abstract: "
                + Modifier.isAbstract(taskClass.getModifiers()));
        System.out.println("Task.calculate abstract: "
                + Modifier.isAbstract(abstractMethod.getModifiers()));
        System.out.println("Task.kind final: "
                + Modifier.isFinal(finalMethod.getModifiers()));
        System.out.println("IncrementTask final: "
                + Modifier.isFinal(implClass.getModifiers()));
        System.out.println("IncrementTask nested static: "
                + Modifier.isStatic(implClass.getModifiers()));

        int stepFlags = stepField.getModifiers();
        System.out.println("STEP static final: "
                + (Modifier.isStatic(stepFlags) && Modifier.isFinal(stepFlags)));

        int runFlags = synchronizedMethod.getModifiers();
        System.out.println("run synchronized: "
                + Modifier.isSynchronized(runFlags));
        System.out.println("run static: "
                + Modifier.isStatic(runFlags));
        System.out.println("run modifiers: "
                + Modifier.toString(runFlags));

        int nativeFlags = nativeMethod.getModifiers();
        System.out.println("nativeEntry native: "
                + Modifier.isNative(nativeFlags));
        System.out.println("nativeEntry static: "
                + Modifier.isStatic(nativeFlags));

        // Only illustrative bitmask decoding, not a flag in a new class file.
        int legacyStrictMask = Modifier.PUBLIC | Modifier.STRICT;
        System.out.println("legacy strict bit: "
                + Modifier.isStrict(legacyStrictMask));

        Object result = synchronizedMethod.invoke(new IncrementTask(), 4);
        System.out.println("run(4): " + result);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ModifierFlagsDemo.java
java ModifierFlagsDemo
```

Stdout output:

```text
Task abstract: true
Task.calculate abstract: true
Task.kind final: true
IncrementTask final: true
IncrementTask nested static: true
STEP static final: true
run synchronized: true
run static: false
run modifiers: public synchronized
nativeEntry native: true
nativeEntry static: true
legacy strict bit: true
run(4): 5
```

Explanation:

- `Task` carries the `abstract` flag; method `calculate` also carries its own `abstract` flag. Conversely, method `kind` carries `final` rather than `abstract`.
- `IncrementTask` is both a `static` nested class and a `final` class; flags on the class reflect class characteristics and do not automatically imply every method is `static` or `final`.
- `STEP` has both `static` and `final` flags. Check **both bits**, because `static` does not always imply `final`.
- `run` is a `public synchronized` instance method, so `isSynchronized` is `true` while `isStatic` is `false`. `Modifier.toString` renders the flags of **this method** in canonical order.
- `nativeEntry` is declared `static native`; the program **only retrieves metadata** and never invokes the native method, so no JNI library is needed to run the example.
- `legacyStrictMask` is explicitly constructed by the program from `Modifier.STRICT` to illustrate bit checking. It does **not** represent a method compiled from `strictfp` with JDK 17+.
- `Method.invoke` on `run` obeys instance method and monitor mechanics; the calculation result is `4 + 1 = 5`, returned by Reflection as an `Object` containing an `Integer`.

## 10. Designing Reflection filters by modifiers

Suppose you only want to list **public, static, non-native methods** declared directly in a class. You can filter as follows:

```java
for (java.lang.reflect.Method method : SomeClass.class.getDeclaredMethods()) {
    int flags = method.getModifiers();
    if (Modifier.isPublic(flags)
            && Modifier.isStatic(flags)
            && !Modifier.isNative(flags)
            && !method.isSynthetic()
            && !method.isBridge()) {
        System.out.println(method.getName());
    }
}
```

This is an illustrative snippet requiring an actual `SomeClass` and `import java.lang.reflect.Modifier;`. It inspects **self-declared methods** via `getDeclaredMethods()`; to also consider inherited public methods, consider `getMethods()`. Do not assume the order of the method array returned by the JVM; sort if your tool needs deterministic output. The `isSynthetic()`/`isBridge()` filters depend on tool needs, since the compiler may generate auxiliary methods.

Decision sequence:

1. **Choose the right `Class<?>` object**: declared type or runtime type depending on the inspection goal.
2. **Choose the discovery scope**: `getDeclared*` for the class's own declarations or `get*` to find public members per API rules.
3. **Read `getModifiers()`** from the exact class, method, or field being inspected; do not use a class flag as evidence for every member.
4. **Decode each flag with `Modifier.isXxx(flags)`**, combining conditions when needed (e.g., `static && final`). Use `Modifier.toString` for display, not as a comprehensive validator.
5. **Interpret per Java semantics**: `final` does not guarantee deep immutability; the `synchronized` flag cannot see synchronized blocks; `native` metadata does not prove the native library is ready; `strictfp` in new class files cannot be inferred like in old class files.

## 11. Common mistakes

| Misconception | Reality / how to handle |
| --- | --- |
| An integer from `getModifiers()` represents exactly one keyword | Multiple bits can be set at once; check with `Modifier.isXxx` or `&` |
| `Modifier.isFinal(SomeClass.class.getModifiers())` indicates all fields are final | It checks only the **class**; check the modifiers of each `Field` |
| A `final` field makes the referenced object immutable | It restricts reassigning the field; the referenced object's state may still be mutable |
| `static` methods are overridden like instance methods | Static methods follow hiding rules; there is no receiver-based dynamic dispatch override like instance methods |
| Absence of the `synchronized` flag means no locking is used | The method may still contain a synchronized block or other locking mechanism |
| `Modifier.isNative(flags)` proves the native library is loaded | It only proves the method carries the native flag; linking/execution availability is separate |
| In Java 17+, `isStrict() == false` means source has no `strictfp` | Java 17+ always uses strict FP semantics and need not store ACC_STRICT like older class files |
| `getMethods()` and `getDeclaredMethods()` are the same | One favors public and inherited methods, the other only direct declarations regardless of access |
| Having private metadata means arbitrary calling/reading is allowed | Access permissions and module boundaries must still be respected |
| `Modifier.toString(flags)` guarantees flags are valid for the element | It only renders a bitmask; context and valid combinations must still be checked separately |

## 12. Self-check questions

1. **Can a `public static synchronized` method have both `isStatic` and `isSynchronized` equal to `true`?** Yes. A static synchronized method synchronizes on the `Class` object's monitor.
2. **Can a `final` class contain an `abstract` method?** No. A `final` class cannot be subclassed to complete the abstract method; `final` and `abstract` cannot be combined on a class.
3. **Does `Modifier.isSynchronized` detect `synchronized(this)` inside a normal method body?** No. It only reads the method declaration flag.
4. **Without loading a JNI library, can we read `getDeclaredMethod("nativeEntry")` and `isNative`?** Yes, as long as the class and related metadata are readable; the example does not invoke the native method.
5. **Why is `Modifier.isStrict` unreliable for detecting the keyword in Java 17+ source code?** Because FP code is always strict and `ACC_STRICT` is only defined for class-file major versions 46–60, so new class files do not have to retain that bit.
6. **Is a `static final List<?>` field guaranteed to have an immutable list?** No. Not being able to reassign the field reference does not prevent modifying the contents of the list.

**Key takeaway:** `Modifier` helps decode **metadata flags of the right element**. To understand impact, always consider the element kind, Reflection scope, and Java/class-file version; the flags themselves do not replace analyzing Java semantics or runtime behavior.
