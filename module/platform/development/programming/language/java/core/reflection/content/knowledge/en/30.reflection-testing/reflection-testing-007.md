# Testing Reflection with Non-Static Inner Classes, Enums, Records, and Sealed Types

## 1. Why Do These Four Types Need Dedicated Test Cases?

When writing a tool that uses Java Reflection to inspect, instantiate, read metadata from, or validate class structures, you cannot treat every `Class<?>` like an ordinary top-level class with a no-arg constructor and mutable fields. **Non-static inner classes, enums, records, and sealed types** have distinct contracts for constructors, identity, immutability, inheritance relationships, and object creation.

This lesson focuses on **how to design tests for Reflection-based tools**. The goal is to test behaviors guaranteed by Java/the JDK, separate them from compiler-generated details, and write explicit assertions rather than printing metadata and guessing.

| Type kind | Key condition | What should be tested? |
| --- | --- | --- |
| Non-static member inner class | Outer class instance is bound to the inner instance | `isMemberClass()`, `getEnclosingClass()`, constructor taking outer parameter, proper instantiation. |
| Enum | Constant set managed by enum declaration; Reflection must not create new enum instances | `isEnum()`, `getEnumConstants()`, `Field.isEnumConstant()`, `Enum.valueOf`, and constructor invocation rejected. |
| Record | State declared by record components and `final` component fields | `isRecord()`, `getRecordComponents()`, canonical constructor, accessor, refusing component field modification via `Field.set`. |
| Sealed class/interface | Only direct subtypes listed in `permits` are allowed | `isSealed()`, `getPermittedSubclasses()`, and verifying the direct permitted type list. |

**No single generic field/constructor filter can replace these tests.** For example, `getDeclaredFields()` may reveal backing fields for an inner class, while `getRecordComponents()` describes record components according to language rules.

## 2. Preparing Safe and Stable Tests

Use **JDK 17 or later** because records and sealed classes/interfaces became standard features in Java 16 and Java 17. A simple classpath demo file keeps the focus on Reflection semantics, avoiding confusing module errors with type-design bugs.

Test design rules:

1. **Verify conditions with assertions**: use `AssertionError`/JUnit or explicit condition checks; do not rely solely on inspecting `println`.
2. **Inspect metadata before executing**: looking up a constructor is separate from `Constructor.newInstance`, and reading field metadata is separate from `Field.get` or `Field.set`.
3. **Use specialized APIs**: `isEnum` and `getEnumConstants` for enums, `isRecord` and `getRecordComponents` for records, `isSealed` and `getPermittedSubclasses` for sealed types.
4. **Do not hard-code compiler artifacts/names**: do not assert fields like `this$0`, `$VALUES`, numeric names of local/anonymous classes, or the array order of fields/methods returned by Reflection.
5. **Verify the exact expected exception type**: e.g., `NoSuchMethodException` when looking up a non-existent constructor; `IllegalArgumentException` when attempting to instantiate an enum via Reflection; `IllegalAccessException` when attempting to modify a record component field after enabling accessibility in the example.
6. **Separate the test harness from the real application**: tests on the same classpath/nest easily access non-public members; when deploying across separate named modules, add tests for access boundaries.

## 3. Non-Static Inner Classes: Constructors Require an Outer Instance

Consider `Outer.Inner` as a **member class not declared `static`**. Every `Inner` instance is bound to an `Outer` instance. Consequently, at the JVM level the constructor has a leading parameter representing the enclosing `Outer` instance, even when source code only declares `Inner(String label)`.

Conceptual example:

~~~java
class Outer {
    class Inner {
        Inner(String label) {}
    }
}
~~~

This is only a declaration snippet; the complete program is in section 7.

Appropriate checks:

- `Outer.Inner.class.isMemberClass()` must be `true`: this is a **member class**.
- `getEnclosingClass() == Outer.class` confirms the enclosing class.
- `getDeclaredConstructor()` **does not exist** in an example whose only constructor takes `String` and the enclosing instance; do not assume a zero-argument constructor exists.
- `getDeclaredConstructor(Outer.class, String.class)` finds the reflected constructor.
- `newInstance(new Outer(), "A")` successfully creates an inner instance when access scope permits.

**Distinguish:** `Outer.StaticNested` declared `static` does not need an enclosing instance. **Local classes** inside methods have different capture/constructor rules; do not treat all nested/local/anonymous classes identically. Compiler-generated backing fields holding the outer reference may be synthetic, and their exact names/representations must not be used as test contracts.

If you call `Class.getConstructors()` instead of `getDeclaredConstructors()`, you only see `public` constructors. Since the constructor in the example is package-private, `getDeclaredConstructor` is more appropriate. Across modules, finding a constructor does not guarantee permission to call it; `canAccess`, `trySetAccessible`, and `InaccessibleObjectException` must be handled as appropriate.

## 4. Enum: List Constants, Do Not Instantiate via Constructor

For:

~~~java
enum Stage { NEW, DONE }
~~~

`Stage.class.isEnum()` returns `true`, and `Stage.class.getEnumConstants()` returns constants in **declaration order**: `[NEW, DONE]`. `Enum.valueOf(Stage.class, "DONE")` looks up an existing constant. Using `getDeclaredFields()` to inspect all fields can include implementation-related fields, so when you truly need to distinguish fields representing enum constants, use `Field.isEnumConstant()`.

### Enum Constructors Are an Intentional Exception

`Stage.class.getDeclaredConstructors()` may expose the enum constructor, yet **`Constructor.newInstance` is forbidden from creating additional enum instances**. The API throws `IllegalArgumentException` when the constructor's declaring class is an enum, even after bypassing normal access checks.

Do not treat finding a constructor as a reason to try `newInstance` on every `Class<?>`. An enum's factories are its declared constants, accessed via `valueOf` or `getEnumConstants`.

**Pitfall:** an enum constant with its own class body can have a runtime class that is a special subclass of the enum; `constant.getClass().isEnum()` is not necessarily `true`. `constant.getDeclaringClass()` gives the declared enum type. Do not assert compiler-specific class names.

## 5. Record: Testing Components and State Immutability

For:

~~~java
record Person(String name, int age) {}
~~~

`Person.class.isRecord()` is `true`. `getRecordComponents()` returns `RecordComponent` objects in **record header order**: `name` then `age`. Each component has name, type, and accessor metadata; `getAccessor()` returns the corresponding `Method`.

For example, `Person.class.getDeclaredConstructor(String.class, int.class)` finds the **canonical constructor** with parameters ordered like the record header. In the demo, this constructor is invoked via Reflection to create `new Person("Lan", 20)`.

### Do Not Treat `setAccessible(true)` as Permission to Mutate Every Field

Record component fields are `final` under record immutability semantics. In `java.lang.reflect.Field`, `static final` fields, `final` fields of hidden classes, and `final` fields of records belong to the group of **non-modifiable final fields**. Even if `setAccessible(true)` is accepted for reading, `Field.set` cannot modify a record component field. In the example, `age.set(person, 99)` throws `IllegalAccessException` and `person.age()` remains `20`.

Tests should assert both the **exception** and **unchanged state**. Never equate "can obtain `Field`" with "can write to field."

### Fields and Components Are Not Identical

`getDeclaredFields()` describes JVM fields in the class, whereas `getRecordComponents()` reflects the **record declaration structure**. If a tool extracts schemas/DTOs from records, it should usually inspect record components first. Annotations on components, fields, and accessors have distinct `@Target`/propagation rules: test annotations at the exact site the tool reads.

An ordinary class returns `null` from `getRecordComponents()`; do not iterate over the result before checking `isRecord()` or handling `null`.

## 6. Sealed Type: List of Direct Permitted Subclasses

Example:

~~~java
sealed interface Shape permits Circle, Rectangle {}

record Circle(int radius) implements Shape {}

final class Rectangle implements Shape {}
~~~

These are **declarations in the same file/package**; the standalone runnable program has an equivalent declaration in section 7. `Shape.class.isSealed()` is `true`, and `getPermittedSubclasses()` returns the types permitted to **directly** implement/extend `Shape`.

Checks:

- `Shape.class.getPermittedSubclasses()` contains `Circle.class` and `Rectangle.class`.
- `Circle.class.isRecord()` is `true`; records are always final, so they can be valid direct subtypes of a sealed interface.
- `Rectangle.class` is declared `final`, not sealed; `isSealed()` is `false`.
- `getPermittedSubclasses()` does not mean "every indirect subtype that can exist": in a hierarchy allowing a `non-sealed` branch, further descendant generations can exist. The API describes **direct permitted subtypes**.

**Do not rely on the returned array order** when deterministic output is required; the demo maps to names and sorts before asserting. For non-sealed types, `Class.getPermittedSubclasses()` returns `null`. Call `isSealed()` or check for `null` before iterating.

An application note: **a sealed interface is invalid as an input interface for JDK `Proxy.newProxyInstance`** (the API requires input interfaces to be non-sealed). That is a specific rule of dynamic proxies; it does not prevent writing a permitted `final` class in `permits`.

## 7. Complete Test Program on Java 17+

Create file **`ReflectionSpecialTypesTest.java`** with the full code below. The program uses `check` to throw `AssertionError` if any mismatch is detected; thus the final line appears only when all four test groups pass.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.List;

public class ReflectionSpecialTypesTest {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static final class Outer {
        class Inner {
            private final String label;

            Inner(String label) { this.label = label; }

            String display() { return "inner:" + label; }
        }
    }

    enum Stage { NEW, DONE }

    record Person(String name, int age) {}

    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}

    static final class Rectangle implements Shape {}

    static void testInner() throws Exception {
        Class<?> type = Outer.Inner.class;
        check(type.isMemberClass(), "must be a member class");
        check(type.getEnclosingClass() == Outer.class, "wrong enclosing class");

        boolean noZeroArg = false;
        try {
            type.getDeclaredConstructor();
        } catch (NoSuchMethodException expected) {
            noZeroArg = true;
        }
        check(noZeroArg, "unexpected zero-arg constructor");

        Constructor<?> ctor = type.getDeclaredConstructor(Outer.class, String.class);
        Object instance = ctor.newInstance(new Outer(), "A");
        check(((Outer.Inner) instance).display().equals("inner:A"), "wrong inner value");
        System.out.println("inner: outer argument required, value=inner:A");
    }

    static void testEnum() throws Exception {
        Class<Stage> type = Stage.class;
        check(type.isEnum(), "not an enum");
        check(Arrays.equals(type.getEnumConstants(), Stage.values()), "enum constants differ");
        check(Enum.valueOf(type, "DONE") == Stage.DONE, "lookup mismatch");

        List<String> constants = Arrays.stream(type.getDeclaredFields())
                .filter(Field::isEnumConstant).map(Field::getName).sorted().toList();
        check(constants.equals(List.of("DONE", "NEW")), "enum field filter");
        Constructor<?> ctor = type.getDeclaredConstructors()[0];
        ctor.setAccessible(true);
        boolean forbidden = false;
        try {
            ctor.newInstance("INJECTED", 10);
        } catch (IllegalArgumentException expected) {
            forbidden = true;
        }
        check(forbidden, "enum reflection construction must fail");
        System.out.println("enum: [NEW, DONE], reflective construction rejected");
    }

    static void testRecord() throws Exception {
        Class<Person> type = Person.class;
        check(type.isRecord(), "not a record");
        RecordComponent[] components = type.getRecordComponents();
        check(Arrays.stream(components).map(RecordComponent::getName)
                .toList().equals(List.of("name", "age")), "component order");
        Person person = type.getDeclaredConstructor(String.class, int.class)
                .newInstance("Lan", 20);
        check(components[0].getAccessor().invoke(person).equals("Lan"), "bad accessor");

        Field age = type.getDeclaredField("age");
        age.setAccessible(true);
        boolean immutable = false;
        try {
            age.set(person, 99);
        } catch (IllegalAccessException expected) {
            immutable = true;
        }
        check(immutable && person.age() == 20, "record field changed");
        System.out.println("record: [name, age], final field write rejected");
    }

    static void testSealed() {
        check(Shape.class.isSealed(), "not sealed");
        List<String> permitted = Arrays.stream(Shape.class.getPermittedSubclasses())
                .map(Class::getSimpleName).sorted().toList();
        check(permitted.equals(List.of("Circle", "Rectangle")), "permitted classes");
        check(!Circle.class.isSealed() && !Rectangle.class.isSealed(),
                "implementations should not be sealed");
        check(Circle.class.isRecord(), "Circle must be a record");
        System.out.println("sealed: permitted=[Circle, Rectangle]");
    }

    public static void main(String[] args) throws Exception {
        testInner();
        testEnum();
        testRecord();
        testSealed();
        System.out.println("ALL CHECKS PASSED");
    }
}
~~~

Compile with Java 17 language level and run:

~~~bash
javac --release 17 ReflectionSpecialTypesTest.java
java ReflectionSpecialTypesTest
~~~

**Verified standard output:**

~~~text
inner: outer argument required, value=inner:A
enum: [NEW, DONE], reflective construction rejected
record: [name, age], final field write rejected
sealed: permitted=[Circle, Rectangle]
ALL CHECKS PASSED
~~~

### Interpreting Results by Feature

1. **Inner:** the reflected constructor takes `Outer` first; the test creates a valid instance and detects the absence of a zero-arg constructor.
2. **Enum:** retrieves constants in declaration order and filters fields that are genuinely enum constants; a constructor exists in metadata, yet creating new instances is forbidden.
3. **Record:** components match the header and accessors read values accurately. `Field.set` is blocked for final record components even when `setAccessible(true)` succeeds in the demo's scope.
4. **Sealed:** the permitted class list contains the exact two direct subtypes; the test does not assume they must also be sealed. `Circle` is also a record.
5. **Final outcome:** `ALL CHECKS PASSED` appears only if every `check` succeeds.

### Why Can This Run Without `--add-opens`?

The test classes are members inside the same top-level class, running on the classpath (unnamed module). The test executes from the same enclosing class/nest, so it has appropriate permissions. **Do not infer** that library code in a different named module can enable `setAccessible(true)` on arbitrary private members. If a real product works with JDK modules or plugins that do not open packages, add separate tests for `trySetAccessible`, `IllegalAccessException`, and `InaccessibleObjectException`.

## 8. Contract-Based Testing, Avoiding Compiler Details

A Reflection tool operating across multiple JDKs/compilers should choose assertions carefully:

| Assertions to use | Assertions to avoid |
| --- | --- |
| Non-static member inner class has an outer instance in its constructor; public/available constructors match its declaration | Relying on outer backing field names like `this$0` or field index in `getDeclaredFields()`. |
| `isEnum` and `getEnumConstants` in declaration order | Relying on compiler-generated `$VALUES` field or specifically named constructor parameters. |
| `RecordComponent[]` in record header order; proper accessors | Treating every JVM field of a record as a record component or expecting `final` fields to be writable. |
| `isSealed` and the set of permitted **direct subtypes** | Treating `getPermittedSubclasses()` array order as a strict contract when no order is guaranteed. |
| Asserting by `Class<?>` identity when needed | Comparing only class names in systems with multiple ClassLoaders. |
| Checking the right exception class and post-failure state | Depending on exact exception messages or stack traces that vary by JDK. |

When testing a generic helper:

- Start by classifying with `isEnum`, `isRecord`, `isSealed`, `isMemberClass`, `getEnclosingClass`, and `Modifier.isStatic`.
- You can consider `isLocalClass`, `isAnonymousClass`, `isHidden` if the helper claims to support multiple Class kinds. These are related topics, but **must not be assumed to share the same constructor contract as non-static member inner classes**.
- Use `getDeclaredConstructor(...)` and `getDeclaredMethods()` when checking internal declarations; use `getConstructor(...)` / `getMethods()` when targeting public members.
- When reflective execution throws an exception from inside a constructor/method, check `InvocationTargetException` and `getCause()`; do not confuse it with `NoSuchMethodException` during metadata lookup.

## 9. Common Mistakes and How to Fix Them

### Mistake 1: Calling the No-Arg Constructor for Every Class

~~~java
// Illustrative snippet to place inside a method:
Object value = Outer.Inner.class.getDeclaredConstructor().newInstance();
~~~

The statement above throws `NoSuchMethodException` at the constructor lookup stage in the fixture, because the inner class requires an outer instance and `String`. **Fix:** plan instantiation based on `Class` kind and constructor signatures; if the library does not support inner classes, fail as unsupported with a clear reason.

### Mistake 2: Iterating Enum Fields and Treating Every Field as a Constant

`getDeclaredFields()` is not promised to return only enum constants. **Fix:** use `getEnumConstants()` when values are needed; use `Field.isEnumConstant()` when field metadata of constants is needed.

### Mistake 3: Treating `private final` Fields in Records as Mutable via `setAccessible`

Record components are protected by final semantics and cannot be mutated via `Field.set`. **Fix:** construct a new object using the canonical constructor or a public factory instead of covertly mutating an existing instance's state.

### Mistake 4: Interpreting `getPermittedSubclasses` as All Subtypes in the Hierarchy

The API reflects **direct permitted subclasses/interfaces** of the sealed type. **Fix:** when the entire hierarchy is needed, traverse recursively in a controlled way, distinguishing `non-sealed` branches that may be open to subtypes not statically listed.

### Mistake 5: Trying to Force `private` Access Across Another Module

`getDeclaredConstructor` can find a member without granting permission to invoke it. **Fix:** prefer public APIs; if deep reflection is genuinely needed, configure `opens` on the right package/module and test access permissions explicitly.

### Mistake 6: Tests Failing Solely Because Metadata Output Changed Order

Reflection does not guarantee ordering for many sets such as `getDeclaredFields()` or `getDeclaredMethods()`. **Fix:** convert to a set or sort by a stable key; only depend on order when API docs confirm order is meaningful, such as enum constants and record components.

## 10. Self-Check Exercises

1. Add a `static class Nested` inside `Outer`, and use `getDeclaredConstructors()` to compare parameters with `Outer.Inner`. State the exact difference when there is no enclosing instance.
2. For enum `Stage`, use `Field.isEnumConstant()` and `getEnumConstants()`; demonstrate why compiler-generated fields should not be tested by name.
3. Add a `boolean active` component to `Person`, and update the canonical constructor and component-order assertion in the test. Why must the test be updated when the record header changes?
4. Create `non-sealed interface Flexible extends Shape` and list it in `permits Shape`. Which direct subtypes does `Shape.getPermittedSubclasses()` return? Are implementations of `Flexible` direct permitted subtypes of `Shape`?
5. Try creating a new enum via `Constructor.newInstance` without calling `setAccessible(true)`: how can the first exception type change depending on the access context? Why must fixtures be designed explicitly when testing a specific contract?
6. Split the demo into four JUnit 5 tests, using `assertThrows` to check `NoSuchMethodException`, `IllegalArgumentException`, and `IllegalAccessException` without depending on exact exception messages.
7. Write a classifier returning `"ENUM"`, `"RECORD"`, `"SEALED"`, `"NON_STATIC_MEMBER"`, or `"OTHER"`. Define check priority for types combining multiple characteristics (e.g., a record that is also a permitted subtype of a sealed interface) rather than assuming categories are mutually exclusive.

**Self-assessment:** A Reflection tool can see a great deal of metadata, yet creating objects, mutating fields, or inferring type relationships must rely on **specific language and API contracts**. For these four groups, test both success conditions and rejected cases using controlled fixtures and meaningful assertions.

## 11. Official Documentation

- [Oracle Java 17 — java.lang.Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) — `isMemberClass`, `getEnclosingClass`, `isEnum`, `getEnumConstants`, `isRecord`, `getRecordComponents`, `isSealed`, `getPermittedSubclasses`.
- [Oracle Java 17 — Constructor.newInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)) — access checks, exceptions, and enum instantiation restrictions.
- [Oracle Java 17 — Field.set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object)) — non-modifiable final fields of records.
- [Oracle Java 17 — RecordComponent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html) — component metadata and accessors.
- [JLS Java 17, 8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3) — enclosing instance constraints.
- [JLS Java 17, 8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10) — record components and constructors.
- [JLS Java 17, 8.9 — Enum Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9) — enum constants and constructors.
- [JLS Java 17, 9.1.1.4 — Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4) — `sealed`, `non-sealed`, and `permits`.