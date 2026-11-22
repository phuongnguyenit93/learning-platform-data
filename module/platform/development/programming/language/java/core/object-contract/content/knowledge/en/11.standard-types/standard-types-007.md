# Enums preserve constant identity and disallow overriding `equals()` or `hashCode()`

## 1. Outcome to understand

In Java, each **enum constant** represents a distinct object created and managed by Java. Within the scope of a loaded enum class, the same constant name always yields **that exact same constant object**. Therefore, enum equality is **identity equality**, rather than automatically comparing the data fields carried by a constant.

Two key points:

1. `java.lang.Enum.equals(Object)` is declared `final` and returns `true` only when two references point to the exact same constant.
2. `java.lang.Enum.hashCode()` is also `final`, producing a hash code tied to the constant's identity. An enum class you declare **cannot override** either of these two methods.

Because of this, comparing two values of **the same enum type** with `==` is a simple, clear, and type-safe expression; `equals()` is also true for two constants because it uses the same identity principle.

**Scope:** This lesson discusses Java's `enum`, not a regular Java class that merely defines `static final` constants. A regular class can override `equals`/`hashCode` by value; an enum class cannot change those two methods.

## 2. Each constant name is a fixed instance

Example:

```java
enum State {
    NEW, RUNNING, DONE
}
```

`State.NEW`, `State.RUNNING`, and `State.DONE` are three distinct constant objects of `State`. There is no mechanism to create an extra `State.NEW` constant via `new State()` in application code. Every time you access `State.NEW`, call `State.valueOf("NEW")`, or obtain the `NEW` element from `State.values()`, you receive the exact same constant reference in the corresponding enum.

Related methods:

| API | Meaning |
| --- | --- |
| `State.NEW` | Directly accesses the `NEW` constant object. |
| `State.valueOf("NEW")` | Returns the constant object with the exact **declared name** `NEW`. |
| `State.values()` | Returns a **new array** containing references to the constant objects in declaration order; does not create new constant objects. |
| `state.name()` | Returns the declared constant name; this is a `final` method of `Enum`. |
| `state.ordinal()` | Declaration position, starting at 0; not a durable business identifier. |
| `state.getDeclaringClass()` | Returns the enum class declaring the constant, even for constants with their own class body. |

`valueOf` matches the name strictly, including uppercase and lowercase; a non-existent name throws `IllegalArgumentException`. `name()` and `ordinal()` do not replace identity: the name is only meaningful within **the enum type's scope**, and changing declaration order changes `ordinal()`.

### "One instance" within what scope?

Each constant is a fixed instance of **the enum type in the corresponding class load**. Do not interpret this as "only a single constant object across every JVM, every process, or every class loader." Java identifies a type by both its class and its class loader; independent class-loading environments do not share the same constant object in memory.

In ordinary Java programs, you do not need to manage this detail directly: `MyEnum.X` and `MyEnum.valueOf("X")` within the same type in use return the same constant.

## 3. `Enum.equals()` is an identity comparison and is `final`

The logic of `Enum.equals(Object)` is equivalent to:

```java
public final boolean equals(Object other) {
    return this == other;
}
```

This is a **logical description** of the method in `java.lang.Enum`, not code you can copy into an `enum` to override it. The `final` keyword prevents overriding in all concrete enums. You cannot change the meaning of `equals()` just because constants have extra fields or their own class bodies.

Compared with the default `Object.equals()`, the identity criterion is the same; the design difference to remember is that `Enum` **deliberately locks the behavior with `final`**. For a regular class, developers can define value-based comparison; for an enum, users can only define **comparison methods with different semantics under distinct names**, if the problem requires them.

Suppose:

```java
enum Priority {
    LOW(1), MEDIUM(1), HIGH(2);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    public int weight() {
        return weight;
    }
}
```

`Priority.LOW.weight()` and `Priority.MEDIUM.weight()` are both `1`, yet:

- `Priority.LOW == Priority.MEDIUM` is `false`;
- `Priority.LOW.equals(Priority.MEDIUM)` is also `false`;
- `Priority.LOW.weight() == Priority.MEDIUM.weight()` is `true`.

Two constants with the same attribute do not become the same constant. **Do not infer "same enum" from "same data."**

## 4. Why can't `equals` and `hashCode` be overridden?

By the definition of `java.lang.Enum`, both methods are `final`. Java enforces this **at compile time**, so it is not a coding-style warning.

**Deliberately invalid example, does not compile**:

```java
enum InvalidStatus {
    A, B;

    @Override
    public boolean equals(Object other) {
        return true;
    }

    @Override
    public int hashCode() {
        return 1;
    }
}
```

The compiler rejects the overriding methods because `Enum.equals(Object)` and `Enum.hashCode()` are already `final`. Even if you try changing parameter names, using a constant-specific class body, or omitting `@Override`, you still cannot override a `final` method with the same signature.

Design reason: **constant identity must be an invariant of the enum type**. If developers turned `LOW` and `MEDIUM` into "equal" whenever they share the same `weight`, comparing values of the enum type would no longer uniquely identify which constant is being referred to. Java keeps a consistent rule, supported across `switch`, `EnumSet`, `EnumMap`, and mechanisms that work with enum constants.

An enum can still implement custom methods, such as `sameWeight(Priority other)`, `hasCode(int code)`, or `matches(String input)` to express **additional business relations**. Those methods do not alter the enum's `equals()`.

## 5. `Enum.hashCode()` is also tied to identity

The general contract between `equals()` and `hashCode()` in Java requires:

```text
a.equals(b) == true  ⇒  a.hashCode() == b.hashCode()
```

Because two variables pointing to the same enum constant always point to **the exact same object**, they have the same hash code. Two distinct constants are never equal via `equals`, yet **their hash codes can still collide**; a hash code is just an `int` and not a unique key.

Points to remember:

- You cannot override an enum's `hashCode()`, even when you want to hash by `weight`, `code`, or `name`.
- The `hashCode()` value is **not guaranteed to equal `ordinal()`, the constant name, a business code, or a memory address**.
- Do not rely on the concrete hash number for persistent storage, cross-process transmission, or as a fixed ID. Java does not promise the same hash number across runs.
- `System.identityHashCode(enumValue)` is also based on the identity mechanism; it is not a way to generate an absolutely unique ID and does not change enum comparisons.
- Need a stable business code? Define an explicit field such as `code` and a `code()` method, then store or transmit **the designed code** instead of `hashCode()`.

A common misconception is "two distinct enum constants must have distinct hashes." **False**: different identities do not guarantee different hashes. `HashMap` and `HashSet` still need to handle collisions.

## 6. Runnable Java 17+ example

Create the file **`EnumIdentityDemo.java`**:

```java
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EnumIdentityDemo {

    enum Priority {
        LOW(1), MEDIUM(1), HIGH(2);

        private final int weight;

        Priority(int weight) {
            this.weight = weight;
        }

        int weight() {
            return weight;
        }
    }

    enum Other {
        LOW
    }

    public static void main(String[] args) {
        Priority a = Priority.LOW;
        Priority alias = Priority.valueOf("LOW");
        Priority different = Priority.MEDIUM;

        System.out.println("a == alias: " + (a == alias));
        System.out.println("a.equals(alias): " + a.equals(alias));
        System.out.println("a == different: " + (a == different));
        System.out.println("a.equals(different): " + a.equals(different));
        System.out.println("same weight: "
                + (a.weight() == different.weight()));
        System.out.println("same name other type: "
                + a.name().equals(Other.LOW.name()));
        System.out.println("cross enum equals: " + a.equals(Other.LOW));
        System.out.println("same hash for alias: "
                + (a.hashCode() == alias.hashCode()));

        Set<Priority> hashes = new HashSet<>();
        hashes.add(a);
        hashes.add(alias);
        hashes.add(different);
        System.out.println("HashSet size: " + hashes.size());

        EnumMap<Priority, String> names =
                new EnumMap<>(Priority.class);
        names.put(a, "low");
        System.out.println("EnumMap lookup alias: " + names.get(alias));

        EnumSet<Priority> states =
                EnumSet.of(Priority.LOW, Priority.HIGH);
        System.out.println("EnumSet contains alias: "
                + states.contains(alias));

        Priority absent = null;
        System.out.println("null == a: " + (absent == a));
        System.out.println("Objects.equals(null, null): "
                + Objects.equals(null, null));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac EnumIdentityDemo.java
java EnumIdentityDemo
```

Result:

```text
a == alias: true
a.equals(alias): true
a == different: false
a.equals(different): false
same weight: true
same name other type: true
cross enum equals: false
same hash for alias: true
HashSet size: 2
EnumMap lookup alias: low
EnumSet contains alias: true
null == a: false
Objects.equals(null, null): true
```

**Group-by-group explanation:**

1. `a` and `alias` are the exact constant `Priority.LOW`. Calling `valueOf("LOW")` looks up the existing constant rather than creating a new object. Thus `==`, `equals`, and `hashCode()` results are all consistent.
2. `different` is `Priority.MEDIUM`, another constant. Even though `weight` of both `LOW` and `MEDIUM` is `1`, both `a == different` and `a.equals(different)` are `false`.
3. Both enums `Priority` and `Other` have a constant named `LOW`, so their `name()` strings are equal. However, `a.equals(Other.LOW)` is `false`, because they are two constant objects from two different enum types.
4. `HashSet` adds three references `a`, `alias`, and `different` yet contains only **two distinct enum objects**, so its size is `2`.
5. `EnumMap` allows looking up the value using the `alias` reference. `EnumSet` contains the same `LOW` constant, so `contains(alias)` is `true`.
6. `absent == a` checks safely when `absent` is null. `Objects.equals(null, null)` returns `true` per the null-safe utility's rule; this is not a comparison of two enum constants.

Do not print or predict the numeric value of `a.hashCode()` in the output because this number is not stable business data.

## 7. Choosing `==` or `equals()` when working with enums

For two enum references of the same type, both `==` and `equals()` correctly answer the question "are these the same constant?"

| Scenario | Recommendation | Reason |
| --- | --- | --- |
| Two variables of type `Priority` | `a == b` | Expresses identity directly, safe when either variable is null. |
| Comparing against a specific constant | `status == Priority.LOW` | Concise, no risk of `NullPointerException`. |
| Potentially null variable | `status == null` or `status == Priority.LOW` | `==` supports null without calling a method. |
| Calling `status.equals(Priority.LOW)` when status is null | Avoid | Calling a method on null throws `NullPointerException`. |
| Comparing an enum with an arbitrary `Object` reference | `status.equals(obj)` if status is non-null, or `Objects.equals(status, obj)` | `equals` accepts `Object` and preserves identity rules. |
| Comparing data fields of two constants | `a.weight() == b.weight()` or a clearly named business method | This is a different relation from "same constant." |

An additional benefit of `==`: when comparing two expressions of **incompatible concrete enum types** (for example, `Priority.LOW == Other.LOW`), the Java compiler rejects that comparison. Meanwhile, `Priority.LOW.equals(Other.LOW)` still compiles because `equals` accepts `Object`, and then returns `false` at runtime.

You can also write `Priority.LOW.equals(status)` to avoid null on the receiver side; however, for enums, `status == Priority.LOW` is usually more readable.

### Null case and `switch`

An enum variable can be null because a **reference variable** can be null; the enum constant itself is never null. In Java 17, using a standard `switch` on a null enum variable throws `NullPointerException`. If null carries business meaning, check for null before switching or disallow null at the input boundary.

## 8. Constants with state and custom class bodies still preserve identity

An enum can declare constructors, fields, and methods:

```java
enum Mode {
    FAST {
        @Override
        String description() {
            return "fast mode";
        }
    },
    SAFE {
        @Override
        String description() {
            return "safe mode";
        }
    };

    abstract String description();
}
```

This is a standalone enum declaration that compiles at package level (if placed in an appropriate file, without needing `public`). The two constants can carry **constant-specific class bodies** to override a method you define, such as `description()`. However, you cannot override `Enum.equals()` or `Enum.hashCode()` even inside the body of `FAST` or `SAFE`, because they are `final`.

For an enum with constant-specific class bodies, calling `getClass()` on a constant can return the implementation class specific to that constant. `getDeclaringClass()` is the proper API to obtain the enum class to which the constant belongs. This is one reason not to infer equality from `getClass()` or fields; Java has already locked enum identity.

Enum fields can reference mutable structures if a developer designs them that way. When internal state mutates, **constant identity, `equals()`, and `hashCode()` still do not change with that state**. Even so, because enums are typically shared application-wide, prefer immutable attributes (`final`, not exposing mutable objects) to avoid state bugs and threading issues.

## 9. Using enums in collections and data persistence

### `HashSet` / `HashMap`

Enums have valid `equals`/`hashCode` out of the box. Using an enum as a key or element in hash-based collections requires no extra overrides. Adding the same constant twice to a `HashSet` produces only one element; two distinct constants remain distinct elements, even if they share identical attributes.

### `EnumSet` and `EnumMap`

If elements/keys always belong to **a single enum type**, consider:

- `EnumSet<Priority>`: a specialized set for `Priority` constants; you can use `EnumSet.of(...)`, `EnumSet.noneOf(Priority.class)`.
- `EnumMap<Priority, V>`: a map whose keys are `Priority` constants; created via `new EnumMap<>(Priority.class)`.

These two structures are optimized for a finite enum constant domain, using internal structures based on enum values/ordinals. There is no need—and no way—to define a custom hash so that they treat two constants with identical attributes as one.

### Persistence and inter-system communication

When storing/transmitting enum values, never persist `hashCode()` or assume `ordinal()` is a long-lived business ID. `ordinal()` depends on declaration order, so adding or reordering constants can change the ordinal numbers.

You can store `name()` if the system defines enum names as a stable data contract and manages renames; or better, define an explicit business code such as `"LOW"`, `"MEDIUM"` and controlled conversion methods. Even if one constant has a business code matching another constant, **their identities still do not collide**.

When Java serializes/deserializes an enum using standard mechanisms, the enum value is handled specially to restore **the declared constant** by name and type, rather than creating a new enum object copy in the ordinary way. Still, whether a constant exists and whether names match across application versions must be managed.

## 10. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "Two constants with equal fields have equal `equals()`." | False; enum `equals()` is based solely on being the same constant object. |
| "You can override `equals` or `hashCode` in an enum if needed." | False; both methods on `Enum` are `final`. |
| "`values()` recreates all constant objects." | False; it returns a new array containing references to the existing constants. |
| "Two different enum types with the same `name()` are equal." | False; identical names do not turn two objects into one. |
| "`ordinal()` is `hashCode()`." | False; they have different purposes and contracts. |
| "Two distinct constants must have distinct hash codes." | False; collisions are allowed. |
| "Every enum can only hold constant names, with no data or methods." | False; enums can have constructors, fields, methods, and constant-specific class bodies. |
| "Enums cannot be used in `HashMap` without overriding hash." | False; `Enum` already provides valid `final` `equals/hashCode`. |
| "`status.equals(X)` is safe if status is null." | False; the call throws `NullPointerException`. Use `status == X`. |
| "You should use an enum's `hashCode()` as a database ID." | False; hash is not a business identifier and is not guaranteed stable across runs. |

## 11. When do you need value-based comparison instead of enum constant comparison?

For example, `Priority.LOW` and `Priority.MEDIUM` both have `weight = 1`, yet are two separate choices. If the program needs to group by weight, express that **with a dedicated comparison method**:

```java
static boolean hasSameWeight(Priority a, Priority b) {
    if (a == null || b == null) {
        return a == b;
    }
    return a.weight() == b.weight();
}
```

This is an illustrative method that should be placed in a class with access to the `Priority` enum and the `weight()` method. It intentionally defines a **same-weight** relation, distinct from the **same-constant** relation. In terms of `a == b` when null, the case where both are null is treated as equal by the function above; business rules may specify otherwise.

If the data model requires **each distinct value to be an object with data-based equality**, and values can arise at runtime, an enum is usually unsuitable. Use an immutable class or a `record` with a component-based `equals()`/`hashCode()` contract, or design a dedicated value key. Never try to make two distinct enum constants equal via `equals()`.

## 12. Self-check

**Question 1.** In enum `Priority { LOW(1), MEDIUM(1) }`, two constants have the same weight. Does `LOW.equals(MEDIUM)` return `true`?

**Answer:** No. They are two separate constant objects, regardless of equal data fields.

**Question 2.** What does `Priority.valueOf("LOW") == Priority.LOW` return?

**Answer:** `true`. `valueOf` returns the declared enum constant, without creating a copy.

**Question 3.** Why can't you write `@Override public int hashCode()` in an enum?

**Answer:** `Enum.hashCode()` is `final`; the compiler forbids overriding it.

**Question 4.** Are two constants from two different enum types both named `READY` equal via `equals`?

**Answer:** No. Their `name()` may be the same, but the enum objects are not the same constant.

**Question 5.** When `status` may be null, should you use `status == State.NEW` or `status.equals(State.NEW)`?

**Answer:** `status == State.NEW`; it is null-safe and directly expresses enum identity comparison.

**Question 6.** Can you rely on `Priority.LOW.hashCode()` always keeping a fixed number across all JVM runs?

**Answer:** No. You should only rely on the equality/hash contract during normal execution; never treat the hash as a stable identifier.

**Remember:** An enum has a finite set of constants and each constant has a **unique identity**. `Enum.equals()` and `Enum.hashCode()` are declared **`final`**, so they cannot be changed to value-based comparison. Use `==` to identify constants; when you need to compare attributes, define a dedicated business comparison method.
