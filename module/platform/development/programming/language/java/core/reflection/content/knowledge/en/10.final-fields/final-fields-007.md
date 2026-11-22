# `final` Fields: Observability, JVM Optimizations, and Behavior Across Java Versions

## 1. The Problem to Understand

When Java Reflection allows access to a `Field` carrying the `final` modifier, there are three **distinct** questions:

1. **Is writing permitted?** Write permission depends on the field category, declaring class, module boundaries, deep-access permissions, and JDK version.
2. **If a write via Reflection succeeds, what will a subsequent read see?** The result of `Field.get(...)`, direct field reads in bytecode, JIT-optimized getters, and compiled code elsewhere **do not necessarily exhibit the same observable behavior** if the program mutates `final` after publishing the object.
3. **What optimizations can Java/the JVM perform when a field is `final`?** The Java Memory Model (JMM) provides dedicated guarantees for properly initialized `final` fields; compilers and the JVM can rely on value-stability assumptions, and compile-time constants can even be **inlined at compile time**.

This lesson focuses on **the impact of observing/modifying `final` fields via Reflection**, optimizations, and differences across versions. The goal is not to build tricks to force changes onto every `final` field: such operations weaken program contracts and are being tightened by Java.

After this lesson, you will be able to distinguish modifier metadata from actual write permission, accurately describe value-observability limits, recognize `final`-based optimizations, run a Java 17+ example, and explain the changes in JDK 26–27.

## 2. What Does `final` Guarantee, and What Does It Not Guarantee?

### 2.1. Semantics at the Java language level

- A **`final` instance variable** can only be assigned according to language rules during initialization; a **blank final** is assigned in a constructor or a valid instance initializer.
- A **`static final` variable** is normally assigned at declaration or in a static initializer; reassigning it in ordinary Java source is a compile-time error.
- **`final` on a reference does not make the referenced object deeply immutable**. For example, a `final List<String> items` field cannot be switched to another list by valid Java assignment, but `items.add(...)` can be called if the list object allows it.
- **`final` does not mean `volatile`**, and `final` itself is not a mechanism for updating shared state across threads after an object has been created.

Example:

```java
import java.util.ArrayList;
import java.util.List;

class Profile {
    final List<String> tags = new ArrayList<>();

    void addTag(String tag) {
        tags.add(tag); // Valid: modifies the contents of the List.
    }
}
```

The snippet above is **illustrative code**, without a `main`; the point of the lesson is **reference** stability, not immutability of elements.

### 2.2. Visibility guarantees upon proper initialization

The Java Memory Model has special rules for `final` in JLS §17.5. When a constructor finishes, a **freeze action** for `final` fields is established. If the object is properly constructed—specifically **without letting `this` escape while the constructor is still running**—other threads can receive stronger `final` initialization guarantees than for ordinary fields, even in certain situations without additional synchronization.

However, read the limits carefully:

- The rules apply to **values assigned during valid initialization** and accesses conforming to the memory model.
- They **do not automatically make all other fields** thread-safe.
- They **do not guarantee visibility of subsequent mutations** to referenced data.
- Letting `this` escape from a constructor—such as registering a concurrently running callback that accesses an incompletely initialized object—can break proper-construction assumptions.

To communicate mutable state between threads, use appropriate mechanisms such as `volatile`, synchronization, locks, atomic classes, or safely published immutable messages. Do not use reflective writes to `final` as a substitute.

## 3. Observing Fields via Reflection: Metadata vs. Values

Reflection can identify that a field is `final` without modifying it:

```java
Field field = SomeType.class.getDeclaredField("value");
boolean declaredFinal = Modifier.isFinal(field.getModifiers());
```

This is an **illustrative snippet**, assuming `SomeType` has a `value` field and `java.lang.reflect.Field` and `java.lang.reflect.Modifier` are imported.

Different APIs answer different questions:

| API | What it answers | What should not be inferred |
| --- | --- | --- |
| `Field.getModifiers()` + `Modifier.isFinal(...)` | Whether the class file declares the field with the `final` flag | Do not conclude `Field.set` will definitely succeed or fail |
| `Field.get(obj)` / `getInt(obj)` | Reads the runtime value via Reflection subject to access permissions | Not a `volatile` read or a guarantee of uniformity across all getters after editing `final` |
| `Field.set(obj, value)` / `setInt(...)` | Requests writing to the reflected field | Success does not alter the `final` modifier in metadata or bytecode definitions |
| `Field.trySetAccessible()` / `setAccessible(true)` | Attempts to allow bypassing certain language access checks when permitted | Does not remove special restrictions on `final`, records, static fields, or modules |
| `Method.invoke(obj)` calling a getter | Observes the runtime behavior of the getter's executed code | Does not automatically return the same value as a `Field.get` read after improper reflective mutation |

Key point: **read permission, permission to bypass access checks, and write permission are three separate issues**. A field can have `setAccessible(true)` enabled for reading while **still not being permitted to be written**.

### 3.1. `final` fields that cannot be opened for writing via `setAccessible(true)`

Starting in Java 17, the `Field` Javadoc specifies `final` cases that **cannot be modified via normal Reflection mechanisms**, including:

- `static final` fields in a class or interface.
- `final` fields declared in a **record class**, including record components.
- `final` fields declared in a **hidden class**.

Enabling access with `setAccessible(true)`, when permitted, only allows **reading** those fields; calling `set(...)` still fails with `IllegalAccessException`. Using `Unsafe` or modifying JVM internals to bypass constraints lies **outside the standard contract** and is not a portable solution.

Conversely, on JDK 17–25, `Field` generally permits writing to **non-static `final` instance fields** of ordinary classes that are not record/hidden classes, provided `setAccessible(true)` succeeds. **Being allowed to perform the operation** does not mean **the program is guaranteed to observe the new value the way you expect**.

## 4. Standalone Java 17+ Example: Identifying and Testing Write Permission

Save the entire snippet below into **`FinalFieldObservationDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class FinalFieldObservationDemo {
    static final class Box {
        private final int value;

        Box(int value) {
            this.value = value;
        }

        int read() {
            return value;
        }
    }

    static final class Constants {
        static final int ANSWER = 42;
    }

    record Snapshot(int id) {}

    public static void main(String[] args) throws Exception {
        Box box = new Box(10);

        Field boxField = Box.class.getDeclaredField("value");
        Field constantField = Constants.class.getDeclaredField("ANSWER");
        Field recordField = Snapshot.class.getDeclaredField("id");

        boxField.setAccessible(true);
        constantField.setAccessible(true);
        recordField.setAccessible(true);

        System.out.println("box final="
                + Modifier.isFinal(boxField.getModifiers()));
        System.out.println("box initial=" + boxField.getInt(box));
        System.out.println("constant direct=" + Constants.ANSWER);
        System.out.println("record final="
                + Modifier.isFinal(recordField.getModifiers()));

        try {
            constantField.setInt(null, 99);
            System.out.println("static final write=allowed");
        } catch (IllegalAccessException e) {
            System.out.println("static final write=denied");
        }

        try {
            recordField.setInt(new Snapshot(5), 99);
            System.out.println("record final write=allowed");
        } catch (IllegalAccessException e) {
            System.out.println("record final write=denied");
        }

        try {
            boxField.setInt(box, 20);
            System.out.println("ordinary instance final write=accepted");
        } catch (IllegalAccessException e) {
            System.out.println("ordinary instance final write=denied");
        }

        // Intentionally does not assert that box.read() after modification must see 20.
    }
}
```

Compile and run with JDK 17–25 or test on JDK 21:

```bash
javac --release 17 FinalFieldObservationDemo.java
java FinalFieldObservationDemo
```

**Stdout observed when compiled with `javac --release 17` and run on OpenJDK 21:**

```text
box final=true
box initial=10
constant direct=42
record final=true
static final write=denied
record final write=denied
ordinary instance final write=accepted
```

The program was **actually compiled and run on OpenJDK 21**; the stdout above matches the verified test output. When run on JDK 26–27, reflective mutation of `Box.value` may emit a warning **on stderr** under JEP 500 and JVM options. When enabling `--illegal-final-field-mutation=deny` without granting corresponding permission, writing `Box.value` may be rejected, changing the last line to `ordinary instance final write=denied`.

**Explanation of each group of results:**

1. `Modifier.isFinal` accurately identifies both `Box.value` and `Snapshot.id` as `final`; metadata does not grant write permission.
2. `constantField` is `static final`, so `setInt(null, 99)` is rejected. Passing `null` here is valid to designate the target of a static field, yet does not make the field writable.
3. `recordField` represents record component `id`, which is `final` and cannot be modified via `Field.setInt`.
4. `Box.value` is a `final` instance field of an ordinary class. On JDK 21, once `setAccessible(true)` is enabled, `setInt(box, 20)` is accepted.
5. The example intentionally **does not conclude** that after the write, `box.read()` or a loop on another thread will always see `20`. That is precisely the subject of **observability and optimization** in this lesson.

If the target class resides in **another named module** whose package is not opened to the caller module, `setAccessible(true)` can even fail with `InaccessibleObjectException` before the program reaches the write check.

## 5. Why Does a Successful `final` Write Still Not Guarantee Reads See the New Value?

### 5.1. The JLS permits optimizations based on `final`

JLS §17.5.3, **Subsequent Modification of `final` Fields**, discusses cases where systems such as deserialization need to modify `final` after an object is constructed. That rule has sensible semantics only in a specific model: create the object, update fields before the object is **published** to other parts, and allow no other code to read the fields until updates complete.

For situations where an object **has already been used/read/published**, a program cannot treat reflective mutation as a guaranteed regular state update. The JLS acknowledges that the compiler/JVM can optimize `final` aggressively, including reordering reads relative to non-constructor modifications of `final`.

An illustrative model of the consequences:

```java
final class Counter {
    final int value;

    Counter(int value) {
        this.value = value;
    }

    int read() {
        return value;
    }
}
```

This is only an **illustrative class**, not a standalone program. If you create `Counter(1)`, let code call `read()` repeatedly, and then use Reflection to change `value` to `2`, there is no general guarantee that:

- A JIT-optimized call to `read()` will always reload the field from memory.
- Another thread will see `2` immediately or within any bounded time.
- All methods/read paths observe the exact same result as `Field.getInt(...)`.
- Running in the interpreter and running JIT-optimized code will produce the same result.

**Do not write unit tests asserting "after `Field.set`, the getter must read the new value" as a stable Java contract.** One test run showing the new value only proves what happened under that specific execution's conditions.

### 5.2. Three levels of "observation" to separate

| Observation layer | Example | Conclusion that can be drawn |
| --- | --- | --- |
| **Metadata** | `Modifier.isFinal(field.getModifiers())` | The field is declared `final`; does not mean the value has never been written post-constructor |
| **Specific reflective read** | `field.getInt(instance)` | Value returned by that Reflection access at a specific time and execution path |
| **Read in application code** | `instance.read()`, JIT-compiled code, or other compiled code | Subject to constant folding, hoisting, cached reads, and JMM constraints; does not automatically synchronize with reflective mutation |

In particular, when testing race conditions, adding logging or Reflection can alter timing, execution paths, and optimization levels. A bug **disappearing once instrumentation is turned on** does not prove the underlying concurrency bug is fixed.

### 5.3. "Freeze" after a reflective write does not make mutation a valid design

The JLS describes a freeze action at the end of a constructor and immediately after certain valid reflective modifications of `final`. However, this is not a license to treat `final` like a mutable variable. The intended scope is very narrow cases such as **reconstruction/deserialization**, where the field is populated **before the object is read/published**.

If the object has already been shared, read repeatedly by getters, or entered a JIT-compiled loop, you cannot invoke a freeze action to force all threads/compilation contexts to see the new version.

## 6. Key Optimization: `static final` Compile-Time Constants

Not every `final` field is a **constant variable** under the JLS. A field is a constant variable when it has a primitive or `String` type, is `final`, and is initialized with a **constant expression** according to language rules.

Example:

```java
class ConstantsExample {
    static final int MAX = 42;            // Constant variable
    static final String LABEL = "READY";   // Constant variable

    static final Integer BOXED = 42;       // Not a constant variable
    static final int COMPUTED = Integer.parseInt("42");
                                         // Not a constant expression
}
```

This is an **illustrative snippet**. `MAX` and `LABEL` can be **inlined at compile time** at usage sites. If a client class is compiled with `ConstantsExample.MAX == 42`, the client's bytecode may embed the literal `42` directly instead of reading the field at runtime.

Therefore:

- Even under the hypothetical scenario of using non-standard means to alter the storage of a `static final`, code paths that already inlined the literal may **continue using the old value**.
- Changing a constant variable's value in a library and deploying only the library JAR without **recompiling clients** can cause clients to keep using the old constant. This is a consequence of **compile-time constant inlining**, distinct from JIT caching.
- A `static final` initialized at runtime, such as `Integer.parseInt("42")`, is not a compile-time constant expression, even though the field is still assigned only once in valid Java source.

You can inspect bytecode:

```bash
javap -c -p FinalFieldObservationDemo
```

In the runnable example above, the expression `Constants.ANSWER` is a compile-time constant. `javap` may show an instruction pushing the literal `42` at the call site instead of a `getstatic` instruction reading the field each time; exact mnemonics and instruction sequences depend on compiler-generated bytecode.

**Note:** `static final` and compile-time constant are two distinct conditions. Forbidding reflective writes to `static final` in Java 17+ does not mean **every `static final`** is inlined as a literal at compile time.

## 7. JVM Optimizations and Performance Trade-Offs

The JVM/JIT can leverage the stability of `final` to reduce memory loads, keep values in registers, eliminate redundant reads, perform constant propagation/constant folding in valid cases, and reorder instructions around points where no valid change can occur under the language model.

However:

- **There is no rule that "every `final` is always inlined"**. Exact techniques depend on the field, escape analysis, JIT configuration, JVM version, and code path.
- **There is no rule that "`final` is always faster"** across every workload. The value of `final` lies primarily in correctness, expressing immutability, and optimization opportunities.
- A system that permits mutating `final` via deep reflection while the application runs constrains the optimization assumptions the JVM can safely apply, because it must account for potential immutability violations.
- The JDK's increasing restriction of reflective mutation aims for **integrity by default**: making the `final` promise more trustworthy and opening more optimization headroom long-term.

When benchmarking, avoid evaluating with a naive handwritten loop: warm-up, inlining, dead-code elimination, constant folding, and the runtime environment can skew conclusions. When a valid microbenchmark is needed, use JMH with consistent test conditions. Do not infer JMM contracts from timing measurements.

## 8. Behavior by JDK Version: What to Check When Upgrading

### 8.1. Version milestones

| JDK line | Points relevant to `final` via Reflection |
| --- | --- |
| **JDK 8** | The JMM `final` model already existed; reflective mutation techniques were used by some object-initialization libraries. Tricks touching JVM internals are not stable APIs. |
| **JDK 9–16** | JPMS added module boundaries and deep-reflection checks; records and hidden classes arrived during platform evolution. Write permission for `final` should not be inferred merely from `private` access. |
| **JDK 17–25** | Strong encapsulation in the JDK tightened; `Field` explicitly disallows writing `static final`, record final, and hidden-class final via `setAccessible`. Certain ordinary-class `final` instance fields can still be reflectively modified when conditions are met. |
| **JDK 26** | **JEP 500 – Prepare to Make Final Mean Final**: warns by default on unauthorized reflective mutation of `final` instance fields, preparing for stricter restrictions in the future; adds policy and launch options. |
| **JDK 27 (released 09/2026)** | Continues **warning** on policy-violating reflective mutation under JEP 500; migration docs still describe blocking with an exception as the direction for a **future release**, so one should not claim all writes are blocked by default in JDK 27. |

**Scope of version information:** the table is based on Java/JDK releases published up to 10/2026. If an application runs on a specific vendor/update JVM or newer JDK, consult the **API docs and migration notes of the exact deployed runtime**.

### 8.2. JDK 26–27: warnings when mutating `final`

JDK 26 adds a final-field mutation policy. If code from a module writes a `final` instance field via deep reflection without being granted this capability, the JVM by default may emit a warning identifying the field and the mutating code. Warnings are printed to **stderr**, so tests comparing only stdout may miss them.

Options introduced by JEP 500:

```text
--enable-final-field-mutation=ALL-UNNAMED
--enable-final-field-mutation=module.name
--illegal-final-field-mutation=warn
--illegal-final-field-mutation=allow
--illegal-final-field-mutation=debug
--illegal-final-field-mutation=deny
```

Meaning:

- `--enable-final-field-mutation=ALL-UNNAMED`: grants mutation capability to code in unnamed module(s), suitable when handling legacy libraries on the classpath. This **does not automatically open the target package** for deep reflection.
- `--enable-final-field-mutation=module.name`: grants capability to the corresponding named module; the caller must reside in the permitted module.
- `--illegal-final-field-mutation=warn`: default policy in JDK 26–27, warning on policy-violating operations.
- `allow`: allows without emitting this policy's warning; `debug`: logs more detailed diagnostic info; `deny`: rejects policy-violating mutation, useful for auditing code before the default policy tightens.

To test the example above under the blocking policy when running JDK 26–27:

```bash
java --illegal-final-field-mutation=deny FinalFieldObservationDemo
```

**The last line** of stdout may change to `ordinary instance final write=denied`, because mutation from the unnamed module is not permitted. This is unrelated to the `static final` and record final operations: they were **already forbidden** in standard Reflection before JDK 26.

If legacy software genuinely must be allowed to perform mutation during a transition period:

```bash
java --enable-final-field-mutation=ALL-UNNAMED FinalFieldObservationDemo
```

This option suits the classpath example without complex module boundaries. In a real modular application, being granted mutation capability must also be paired with appropriate access permission to the target package; **`--add-opens` and `--enable-final-field-mutation` govern two different permissions**.

**Important:** choosing `allow` or granting mutation permission is only a compatibility workaround when unavoidable. It creates no new observability guarantees after modifying `final`, does not make `static final`/record/hidden-class final writable via `Field.set`, and does not turn a mutable design into a thread-safe one.

### 8.3. Anticipating changes without overclaiming

JEP 500 explicitly states its goal is to **prepare** for a future release where illegal final field mutation shifts from a warning to a default exception. Therefore:

- Do not hard-code the assumption "on every JDK, `setAccessible(true)` will allow modifying a `final` instance field".
- Do not hard-code the assumption "starting in JDK 26, every `final` modification always throws an exception".
- When upgrading, run compatibility tests with `--illegal-final-field-mutation=deny` to locate dependencies on mutation, checking both stderr and stack traces.
- Upgrade frameworks/serializers to versions supporting valid initialization mechanisms rather than maintaining tricks on already-published objects.

## 9. Common Problem Patterns

### 9.1. Reflection can read but cannot write

`field.trySetAccessible()` returning `true` only says the request to **suppress access checks** was valid. Afterward, `field.set(...)` can still throw `IllegalAccessException` if the field is a non-modifiable final or the final-mutation policy blocks the operation. If the package in a named module is not open to the caller, enabling access may fail earlier.

**How to handle:** log `field.getDeclaringClass().getModule()`, `field.getModifiers()`, `field.getDeclaringClass().isRecord()`, runtime `java.version`, and the exception type. Do not "fix the bug" by arbitrarily removing the `final` modifier.

### 9.2. Unit tests pass via Reflection, but production sees the old value

A short test running in the interpreter may observe the update, whereas a production getter after warm-up may be optimized differently. Benchmark behavior also depends on the JVM, flags, and field declaration kind.

**How to handle:** redesign to initialize full data in the constructor, pass dependencies via constructor/factory, or use proper mutable mechanisms (`volatile`, atomic reference, lock) if the business logic genuinely requires updates.

### 9.3. Changing a constant value in a library, yet the client still prints the old value

If `static final` is a constant variable, client code may have embedded the literal from an earlier compilation. Swapping only the library JAR does not necessarily update already-compiled client code.

**How to handle:** rebuild dependent clients when changing public compile-time constants; avoid treating them as runtime-updatable configuration.

### 9.4. Mistaking Reflection for a synchronization channel

`Field.set`/`get` does not automatically create a safe publish-consume protocol just because a field has the `final` modifier. One party writing to a published object while another reads in a loop can hit visibility limits and data races depending on design.

**How to handle:** separate immutable configuration into new objects and publish safely; for mutable state, use synchronization primitives recognized by the JMM.

### 9.5. Thinking disabling the JIT solves the root cause

`-Xint` is useful for a **diagnostic experiment** (running in interpreted mode), but does not change the specification and does not turn reflective mutation of `final` into a stably contracted behavior. Similarly, `-Xcomp` or JVM optimization flags are no substitute for proper design.

## 10. Safe Design Alternatives

### 10.1. True immutability: pass through constructor

```java
final class ImmutableConfig {
    private final String endpoint;

    ImmutableConfig(String endpoint) {
        this.endpoint = java.util.Objects.requireNonNull(endpoint);
    }

    String endpoint() {
        return endpoint;
    }
}
```

This is an **illustrative class**, without a `main`. The value is set at initialization and never replaced afterward.

### 10.2. When runtime configuration updates are needed

```java
import java.util.concurrent.atomic.AtomicReference;

final class ConfigHolder {
    private final AtomicReference<String> endpoint =
            new AtomicReference<>("https://example.invalid");

    String getEndpoint() {
        return endpoint.get();
    }

    void changeEndpoint(String replacement) {
        endpoint.set(java.util.Objects.requireNonNull(replacement));
    }
}
```

In this example, **the reference to `AtomicReference` is `final`**, while the state managed by the atomic object can change in accordance with the JMM contract. This is an **illustrative class**, without a `main`. In a real application, add validation and lifecycle management matching business rules.

### 10.3. For serialization/deserialization

Prefer frameworks supporting constructors/factories, record constructors, builders, or suitable data-reading mechanisms. If a legacy library must write `final` while reconstructing an object, confine the operation **before the object is published or read**, verify permissions/modules/runtime explicitly, and prepare migration per JEP 500. Do not modify an object after it is already in use and expect every getter and thread to automatically see the new value.

## 11. Diagnostic and Testing Checklist

1. **Identify the field category:** instance or static, `final` or not, belonging to an ordinary class, record, or hidden class? Use `getModifiers()` and `Modifier.isFinal(...)`.
2. **Identify permissions:** is the caller in the same class/module or another module? Is the target package open? Did `setAccessible(true)` succeed?
3. **Identify the runtime version:** `System.getProperty("java.version")` and active JVM flags; do not infer from source compatibility `--release 17`.
4. **Separate the three checks:** permission to write, observed reflective read, and observed compiled getter. Do not treat them as identical.
5. **Check compile-time constants:** is the `static final` field of primitive/`String` type with a constant expression? Must clients be rebuilt?
6. **Check the publication point:** is the object accessed before/during the field change? Is there a race condition?
7. **Use an upgraded environment:** test JDK 26–27 with `--illegal-final-field-mutation=deny`, inspect exceptions, stderr, and which dependency performs mutation.
8. **Choose a design fix:** constructor/factory or synchronized mutable mechanism; treat reflective final mutation as a legacy compatibility case to phase out.

## 12. Specifications and Verification Sources

- Java Language Specification, §17.5 *final Field Semantics* and §17.5.3 *Subsequent Modification of final Fields*: https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html
- Java SE 17, `java.lang.reflect.Field`, sections `setAccessible` and `set`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html
- Oracle JDK 26 Migration Guide, *Preparing for final Field Mutation Restrictions*: https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html
- Oracle JDK 27 Migration Guide, *Significant Changes*: https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html

**Remember:** `final` is not just a modifier flag; it is a design commitment and the basis for memory rules and optimizations. A reflective write may be accepted by the runtime under certain conditions, yet **creates no reliable observability guarantee** on an already-used object. Therefore, separate write capability, observability, and optimization effects—and verify the new JDK 26–27 policies when upgrading.
