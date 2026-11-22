# Direct Subtype and Final Subtype in a Java Sealed Hierarchy

## 1. Why Distinguish Between Direct Subtype and Final Subtype?

A **sealed hierarchy** is a Java type hierarchy whose root class or interface uses the `sealed` keyword to **control which direct subtypes** are allowed to extend or implement it. The `sealed`/`non-sealed` feature became standard in **Java 17** (JEP 409). Since **Java 21**, pattern matching for `switch` (JEP 441) leverages this hierarchy information to check *exhaustiveness* (coverage of `case` labels).

These two concepts are not identical:

- **Direct subtype:** a type declared to **directly** extend or implement a sealed class/interface. With a sealed parent, this type must belong to the set allowed by `permits` (or the set inferred by the compiler when `permits` is omitted).
- **Final subtype:** a subtype that is `final` or **implicitly `final`** (such as a record). That type **cannot have any further subclasses**. `final` describes the extensibility of *the subtype itself*, not whether it is a direct subtype of the root.

Short example:

```java
sealed interface Animal permits Cat, Bird {}

record Cat(String name) implements Animal {}  // Direct subtype, implicitly final.

final class Bird implements Animal {}          // Direct subtype, explicitly final.
```

Both `Cat` and `Bird` are **direct permitted subtypes** of `Animal`; both are also **final subtypes**. Using `record` is a concise way to model an immutable value at the leaf level; use `final class` when a regular class implementation is needed.

Note: the snippet above is a **structural code fragment**, not a standalone Java program with `main`. Section 6 provides a complete, runnable program.

## 2. `permits` Only Lists Direct Subtypes

Consider the type tree:

```text
Shape  (sealed interface)
├── Circle   (record, implicitly final)
├── Polygon  (sealed interface)
│   ├── Square   (record, implicitly final)
│   └── Triangle (final class)
└── Note     (non-sealed class)
    └── SpecialNote (final class)
```

`Shape` has **three** direct permitted subtypes: `Circle`, `Polygon`, `Note`.

- `Circle` directly `implements Shape`, so it must be permitted by `Shape`.
- `Polygon` directly `extends Shape`, so it must be permitted by `Shape`.
- `Note` directly `implements Shape`, so it must be permitted by `Shape`.
- `Square` and `Triangle` belong directly to `Polygon`, and are **not** direct subtypes of `Shape`. They are governed by `Polygon permits Square, Triangle`.
- `SpecialNote` directly `extends Note`; it is still an **indirect subtype** of `Shape`, but it is **not** placed in `Shape permits ...` simply because it inherits from `Note`.

In Java, the *subtype* relationship is transitive; however, `permits` only refers to **direct inheritance edges**. This is the most important distinction.

### Corresponding Declarations

```java
sealed interface Shape permits Circle, Polygon, Note {}

record Circle(int radius) implements Shape {}

sealed interface Polygon extends Shape permits Square, Triangle {}

record Square(int side) implements Polygon {}

final class Triangle implements Polygon {}

non-sealed class Note implements Shape {}

final class SpecialNote extends Note {}
```

These are **illustrative declarations**; when all types are placed in the same valid compilation unit/package, they can be compiled. There is no `main` method here yet.

You should not write:

```java
// INCORRECT regarding the direct subtype relationship:
sealed interface Shape permits Circle, Square {}
record Circle(int radius) implements Shape {}
record Square(int side) implements Polygon {} // Square does not directly extend/implement Shape.
```

If `Shape permits ...` lists `Square` while `Square` only directly implements `Polygon`, Java reports a compile-time error: **a listed permitted subtype must directly extend the sealed parent**. You also need to declare `Polygon` and permit `Polygon` at the appropriate level, rather than trying to flatten all leaf types into the root's `permits`.

## 3. Three Ways a Direct Subtype Continues a Sealed Hierarchy

A class that directly extends a sealed class or directly implements a sealed interface must be in exactly one state: **`final`**, **`sealed`**, or **`non-sealed`**, whether explicitly or implicitly according to the language. A subinterface that directly extends a sealed interface must be **`sealed`** or **`non-sealed`** (an interface cannot be `final`).

| Direct subtype form | Further extensibility | When to choose? |
| --- | --- | --- |
| `final class C extends/implements ...` | Cannot have subclasses of `C` | Leaf type, no further inheritance needed |
| `record C(...) implements SealedInterface` | **Implicitly final** | Data-carrying leaf type, record fits the domain |
| `sealed class S ... permits ...` | Only permitted direct subclasses | Want to close the hierarchy for another level |
| `sealed interface S ... permits ...` | Only permitted direct classes/interfaces | Want to restrict implementation families |
| `non-sealed class N ...` | Allows arbitrary subclasses under normal Java access rules | Need an open extension branch outside the closed leaf set |
| `non-sealed interface N ...` | Allows interfaces/classes to continue extending/implementing | Need an extensible branch of an interface |

**A direct subtype does not have to be final**: `Polygon` can be declared `sealed` to control the next level; `Note` can be `non-sealed` to intentionally open it up for extension.

### 3.1. `final`: stopping the branch at that type

```java
sealed interface Payment permits Cash, Card {}

final class Cash implements Payment {}

record Card(String lastFour) implements Payment {}
```

`Cash` is a `final class`; you cannot write `class SpecialCash extends Cash`. `Card` is a record, which is implicitly `final`, so it also cannot have subclasses.

`final` does not mean the object is **completely immutable**. A final class can still hold mutable fields if the design allows it; `final` here only prohibits **class inheritance**. A record by default has its own data characteristics (component fields are final), but it can still hold references to mutable objects. Do not conflate the three concepts: *final class*, *final field*, and *deep immutability*.

### 3.2. `sealed`: continuing to lock down the next level

```java
sealed interface Message permits Text, Command {}

record Text(String value) implements Message {}

sealed interface Command extends Message permits Start, Stop {}

record Start() implements Command {}

record Stop() implements Command {}
```

`Command` is not a leaf type: it is a **direct subtype of `Message`** and still controls the direct types beneath it via `permits Start, Stop`.

`Start` and `Stop` are not direct permitted subtypes of `Message`; they are direct permitted subtypes of `Command`. When there are multiple sealed levels, the compiler checks the relationship and modifier declarations separately at each level.

### 3.3. `non-sealed`: intentionally opening a branch

```java
sealed interface Action permits BuiltIn, Extension {}

record BuiltIn(String name) implements Action {}

non-sealed interface Extension extends Action {}

final class ThirdPartyAction implements Extension {}
```

`Extension` is a direct permitted subinterface of `Action`, but it **does not continue sealing** its own implementations. Therefore, `ThirdPartyAction` can `implements Extension` without needing to be listed in `Action permits ...`.

`non-sealed` does not mean anyone is guaranteed to be able to extend it: Java's **visibility, module, package, constructor, and abstract method** rules still apply. It only means that from this level onward, there are no longer restrictions imposed by that branch's own sealed modifier.

You cannot place `non-sealed` on a class/interface that has no **sealed direct superclass or sealed direct superinterface**. For example, `non-sealed class Ordinary {}` is invalid just to express an intent to be "open".

## 4. Compilation Rules for Direct Permitted Subtypes

### 4.1. Permitted by `permits`, and must actually be a direct subtype

```java
sealed interface Root permits A, B {}

record A(int id) implements Root {}

final class B implements Root {}
```

In this example:

1. `A` and `B` are type names listed once in `Root permits A, B`.
2. Both actually directly `implements Root`.
3. `A` is an implicitly final record; `B` is a final class.
4. There is no third class `C implements Root` when `C` is not in `permits`, even if `C` is declared `final`.

A class with the `final` keyword **does not automatically grant itself the right** to be a direct subtype of a sealed parent.

### 4.2. Requires `final` / `sealed` / `non-sealed`

Intentionally invalid example:

```java
sealed interface Root permits Child {}

// INVALID: a regular class has not declared how to continue the hierarchy.
class Child implements Root {}
```

Even though `Child` is listed in `permits`, it must still declare one of the three continuation modifiers. Fix:

```java
final class Child implements Root {}
```

If subclasses of `Child` are needed, you can consider `sealed class Child ... permits ...` or `non-sealed class Child ...` depending on the design.

### 4.3. `final` cannot be used simultaneously with `sealed`

A class cannot be both **`final` and `sealed`**. `final` prevents all subclasses; `sealed` allows a specific set of direct subclasses. Similarly, a class that is both `final` and `abstract` is contradictory because it cannot be completed by a subclass. Use the modifier that matches the domain model rather than combining keywords arbitrarily.

### 4.4. An interface cannot be `final`

A direct **subinterface** of a sealed interface can be `sealed` (locking another level) or `non-sealed` (opening the level). An interface cannot be `final`. Meanwhile, a class implementing a sealed interface can be `final`, `sealed`, or `non-sealed`, and a record is implicitly final.

### 4.5. Module and package rules

According to JLS 17/21:

- In a **named module**, all direct permitted subtypes of a sealed class/interface must reside **in the same module** as the sealed parent; they may be in different packages when module/visibility rules allow.
- In an **unnamed module** (the case for many simple Java projects without a module declaration), they must reside **in the same package**.
- It is not required for every type to be in the **same file** if `permits` is explicit and the relationship/module/package conditions are satisfied.

This restriction applies to **direct permitted subtypes**. After passing through a direct `non-sealed` subtype, indirect subtypes are no longer governed by that same `permits` list, though they must still obey standard access rules.

### 4.6. Can `permits` be omitted?

Yes, if the compiler can infer the exact direct subtypes **within the same compilation unit** (the same source file) according to JLS rules and those types have appropriate canonical names. For example:

```java
sealed interface Token {}  // permits is inferred for Word and Numeric.

record Word(String value) implements Token {}

final class Numeric implements Token {}
```

When types are split across multiple files, you should explicitly declare `permits Word, Numeric`. Do not assume that omitting `permits` means any class in the same package can implement the sealed interface. If there are no valid direct permitted subtypes to infer, the compiler reports an error.

## 5. Comparison Table: Direct - Indirect - Final

Consider the tree `Shape → Circle, Polygon, Note → Square, Triangle, SpecialNote` from Section 2:

| Type | Direct subtype of `Shape`? | Direct subtype of `Polygon`? | `final`? | Can have further subclasses? |
| --- | --- | --- | --- | --- |
| `Circle` (record) | **Yes** | No | **Yes, implicitly** | No |
| `Polygon` (sealed interface) | **Yes** | No | No | Only direct subtypes allowed by `permits` |
| `Square` (record) | **No** | **Yes** | **Yes, implicitly** | No |
| `Triangle` (`final class`) | No | **Yes** | **Yes** | No |
| `Note` (`non-sealed class`) | **Yes** | No | No | Yes, under Java access rules |
| `SpecialNote` (`final class`) | **No** | No | **Yes** | No |

Therefore, the question "Is `SpecialNote` a subtype of `Shape`?" has the answer **yes, indirectly via `Note`**; whereas the question "Is `SpecialNote` a direct permitted subtype of `Shape`?" has the answer **no**. Likewise, `Square` is a subtype of `Shape` through the chain `Square → Polygon → Shape`, but it does not need to appear in `Shape permits ...`.

**Final subtype** does not mean "every path from the root is closed": if the tree still has a `non-sealed` branch, new subtypes can still be created under that branch. `final` only closes **the specific type carrying the modifier**.

## 6. Complete Java 21+ Program: Sealed Hierarchy and `switch`

The following program uses a single public class containing nested types, so it compiles with just one file. All direct permitted subtypes are explicitly defined and controlled. It demonstrates:

- Two **final leaves**: record `Circle`, record `Square`.
- One **sealed intermediate subtype**: interface `Polygon`.
- One **final class** directly under `Polygon`: `Triangle`.
- One **non-sealed subtype**: class `Note`; and class `SpecialNote` extending `Note`.
- An exhaustive Java 21 `switch expression` **without `default`**, containing cases for the leaf types and the open `Note`.
- Java 17+ reflection to list **only the direct permitted subtypes**, without confusing them with all transitive subtypes.

Save the file as **`DirectFinalSubtypeDemo.java`**:

```java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.stream.Collectors;

public class DirectFinalSubtypeDemo {
    sealed interface Shape permits Circle, Polygon, Note {}

    record Circle(int radius) implements Shape {}

    sealed interface Polygon extends Shape permits Square, Triangle {}

    record Square(int side) implements Polygon {}

    static final class Triangle implements Polygon {
        private final int base;

        Triangle(int base) {
            this.base = base;
        }

        int base() {
            return base;
        }
    }

    static non-sealed class Note implements Shape {
        private final String text;

        Note(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }
    }

    static final class SpecialNote extends Note {
        SpecialNote(String text) {
            super(text);
        }
    }

    static String classify(Shape shape) {
        return switch (shape) {
            case null -> "NULL";
            case Circle c -> "Circle(radius=" + c.radius() + ")";
            case Square s -> "Square(side=" + s.side() + ")";
            case Triangle t -> "Triangle(base=" + t.base() + ")";
            case Note n -> "Note(text=" + n.text() + ")";
        };
    }

    static String permittedNames(Class<?> type) {
        return Arrays.stream(type.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        System.out.println(classify(new Circle(2)));
        System.out.println(classify(new Square(3)));
        System.out.println(classify(new Triangle(4)));
        System.out.println(classify(new Note("memo")));
        System.out.println(classify(new SpecialNote("urgent")));
        System.out.println(classify(null));

        System.out.println("Shape permits: " + permittedNames(Shape.class));
        System.out.println("Polygon permits: " + permittedNames(Polygon.class));
        System.out.println("Circle is record: " + Circle.class.isRecord());
        System.out.println("Circle is final: "
                + Modifier.isFinal(Circle.class.getModifiers()));
        System.out.println("Polygon is sealed: " + Polygon.class.isSealed());
        System.out.println("Note is sealed: " + Note.class.isSealed());
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac DirectFinalSubtypeDemo.java
java DirectFinalSubtypeDemo
```

**Expected standard output:**

```text
Circle(radius=2)
Square(side=3)
Triangle(base=4)
Note(text=memo)
Note(text=urgent)
NULL
Shape permits: Circle, Note, Polygon
Polygon permits: Square, Triangle
Circle is record: true
Circle is final: true
Polygon is sealed: true
Note is sealed: false
```

**Line-by-line analysis:**

1. `new Circle(2)` is a direct subtype of `Shape`, and `Circle` is an implicitly final record, so `case Circle c` is selected.
2. `new Square(3)` and `new Triangle(4)` are **indirect subtypes of `Shape` via `Polygon`**. `case Square s` and `case Triangle t` are still valid because the runtime type of `Shape` is checked; with the sealed intermediate `Polygon`, the compiler can infer that these two branches cover the entire `Polygon` domain.
3. `new Note("memo")` is a direct subtype permitted by `Shape`. `new SpecialNote("urgent")` is **not listed** in `Shape permits`, but is valid because it inherits from `Note` (`non-sealed`). Both match `case Note n`, yielding `Note(text=...)`.
4. `classify(null)` returns `NULL` because there is an explicit `case null`. The patterns `Circle`, `Square`, `Triangle`, and `Note` do not match null on their own.
5. Reflection `Shape.class.getPermittedSubclasses()` returns **only `Circle`, `Polygon`, `Note`**, without including `Square`, `Triangle`, or `SpecialNote` in `Shape`'s direct permitted set.
6. Reflection `Polygon.class.getPermittedSubclasses()` returns `Square`, `Triangle`. The `permittedNames` method sorts the names alphabetically so the output does not depend on the element order returned by the API.
7. `Circle.class.isRecord()` and `Modifier.isFinal(...)` are both `true` because a record is an implicitly final type; `Polygon.class.isSealed()` is `true`; `Note.class.isSealed()` is `false` because `Note` is declared `non-sealed`.

### Why is `switch` exhaustive without `default`?

In Java 21, the compiler knows `Shape` only has the direct permitted subtypes `Circle`, `Polygon`, and `Note`. Given:

- `Circle`: already has the `case Circle` branch.
- `Polygon`: itself is sealed, permitting only `Square` and `Triangle`; both branches are present.
- `Note`: even though it is `non-sealed` and arbitrary subclasses can exist, `case Note n` matches **both `Note` and all of its subclasses** (such as `SpecialNote`).

Thus all non-null `Shape` values are covered without needing `default`. `case null` ensures an explicit null policy. If `case Note n` were removed, no set of branches listing only current subclasses like `SpecialNote` could guarantee coverage of all future subclasses of `Note`.

**Note the version distinction:** Sealed classes/interfaces and the sealed reflection APIs have existed since **Java 17**; `switch` with type patterns in the example is a standard feature since **Java 21**. If you use JDK 17 without enabling preview features, `switch (shape)` with `case Circle c` is not valid default syntax.

## 7. Direct Subtype and Exhaustiveness: Which Level Should Cases Target?

A `switch` on a sealed root can choose to handle the **direct level** or the **leaf level**:

### 7.1. Handling each direct permitted subtype

```java
// Valid switch expression fragment with Shape from the Section 6 example:
return switch (shape) {
    case null -> "NULL";
    case Circle c -> "circle";
    case Polygon p -> "polygon";
    case Note n -> "note";
};
```

The rule `case Polygon p` covers every implementation of `Polygon`, including `Square` and `Triangle`. This approach fits when business logic only needs broad group classification.

### 7.2. Handling the leaf level of a sealed subtype

```java
// Switch expression fragment using Shape from Section 6:
return switch (shape) {
    case null -> "NULL";
    case Circle c -> "circle";
    case Square s -> "square";
    case Triangle t -> "triangle";
    case Note n -> "note";
};
```

Here the compiler traces through the sealed `Polygon` branch to know that `Square` and `Triangle` provide full coverage. This approach fits when business logic needs distinct behavior for each polygon kind.

### 7.3. Do not place a parent case before a child case

```java
// INVALID when placed in the same switch:
case Polygon p -> "polygon";
case Square s -> "square"; // Dominated by the Polygon branch (dominance).
```

`Square` is always a `Polygon`. When an unguarded `case Polygon p` comes first, `case Square s` can never be selected, so the compiler reports a *dominated case label* error. If you need special handling for `Square`, place `case Square s` **before** `case Polygon p` or split the groups as needed.

### 7.4. Why consider omitting `default` with a sealed root?

When a sealed hierarchy is closed and all cases are listed exhaustively, **omitting `default`** lets the compiler remind you to add a branch when a new direct permitted subtype is added in the source code. For example, if you add a direct subtype `record Line(int length) implements Shape {}` to `Shape permits`, switches that only have the old branches are no longer exhaustive after recompilation.

If `default` is present, the code may continue compiling while dedicated logic for `Line` is forgotten. For systems/plugins that need extensibility via `non-sealed`, `case Note n` is still needed to cover the open branch; you cannot expect the compiler to know all subclasses of `Note` ahead of time.

Note the **binary evolution** issue: when a hierarchy is modified and distributed separately, switch code compiled against the old subtype set may encounter a new subtype at runtime and throw `java.lang.MatchException`. Therefore, rebuild and retest all related modules when modifying `permits`.

## 8. `final` on a Subtype Does Not Mean an Immutable Object

A common misconception is that `final class` guarantees all internal state cannot change:

```java
sealed interface Box permits MutableBox {}

final class MutableBox implements Box {
    private int count;

    void increment() {
        count++;
    }

    int count() {
        return count;
    }
}
```

This is a valid declaration fragment: `MutableBox` is a **final subtype**, yet the `increment()` method can still mutate the `count` field. The `final` keyword on a class only states that **the class cannot be subclassed**. It does not forbid mutations inside methods.

Similarly, a record is final and does not allow reassigning component fields, but if a component points to a mutable list, the list's contents can still change. When designing a domain, you must also evaluate data immutability; `sealed` and `final` solve **the shape of the type tree**, not all state-management concerns on their own.

## 9. Common Mistakes and How to Fix Them

### 9.1. Putting an indirect subtype in the root's `permits`

**Wrong:** `Shape permits Square` when `Square implements Polygon` and `Polygon extends Shape`. `Square` does not directly `implements Shape`; you must list `Polygon` at the root and `Square` in `Polygon permits`.

### 9.2. Assuming every subtype of a sealed root must appear in `permits`

`permits` only lists **direct subtypes**. Subtypes beneath a `sealed` or `non-sealed` branch are **indirect subtypes** of the root and do not belong in the root's list.

### 9.3. Forgetting the modifier on a direct class

A class that directly `implements SealedInterface` written simply as `class C` (without final/sealed/non-sealed) causes a compile-time error, except where language features make the type **implicitly final** (records, certain enum forms).

### 9.4. Using `non-sealed` on a regular class

`non-sealed` is only valid when the class/interface has a corresponding sealed direct superclass or superinterface. A subclass of a `non-sealed` branch **does not need** the `non-sealed` modifier, and if it is not directly subject to a sealed parent, it is **not allowed** to declare `non-sealed` on its own.

### 9.5. Assuming `final` automatically grants permission to extend a sealed parent

No. A direct class must still be in the set allowed by `permits`. `final class Rogue implements Shape` when `Rogue` is not permitted is an error.

### 9.6. Assuming `final` means the same thing as `sealed`

`final` forbids all subclasses; `sealed` permits a specified set of subclasses. If multiple domain levels are needed, use `sealed` for intermediate types and `final` for leaves.

### 9.7. Equating leaf types with the entire tree being closed

`Triangle` may be `final`, but if `Note` is still `non-sealed`, the overall `Shape` tree can still accept new subtypes under `Note`. "All current leaves are final" is not enough to prove the entire tree is closed.

### 9.8. Handling a sealed switch using only specific indirect subtypes of an open branch

If `Note` is `non-sealed`, listing only `SpecialNote` does not cover every `Note` and future subclasses. To make the switch exhaustive, handle `case Note n` or include an appropriate general branch.

### 9.9. Reordering cases so that a child class is dominated

`case Polygon p` before `case Square s` dominates the `Square` branch; `case Shape s` before any subtype will also dominate those subtypes if used as an unguarded pattern. Place specialized branches before general ones.

### 9.10. Misunderstanding file/package/module constraints

In an unnamed module, direct permitted subtypes must be in the same package. In a named module, they must be in the same module, not necessarily the same package. The same file is not required if `permits` is explicit; **only when relying on `permits` inference** is being in the same compilation unit a key requirement.

### 9.11. Not distinguishing between Java 17 and Java 21

Use JDK 17+ to compile sealed hierarchies. Use **JDK 21+** for standard switch type patterns; do not write `case Circle c` in a switch and treat it as default Java 17 syntax.

## 10. Practice Exercises

1. Sketch a sealed hierarchy `Transport` with direct permitted subtypes `Car` (record), `Bike` (final class), `AirVehicle` (sealed interface), and `ExtensionTransport` (non-sealed interface). Clearly list the direct and indirect subtypes of `Transport`.
2. Add `Helicopter` and `Plane` as direct permitted subtypes of `AirVehicle`; choose `record` or `final class` as appropriate. Explain why these two types do not need to appear in `Transport permits ...`.
3. Add `CustomTransport implements ExtensionTransport`; explain why this is a valid indirect subtype of `Transport` even though it is not in `Transport permits`.
4. Try declaring `class Bike implements Transport {}` (with `Bike` in `permits`). Predict the error caused by missing `final/sealed/non-sealed`, then fix it to `final class Bike`.
5. Try adding `final class Scooter implements Transport {}` without updating `Transport permits` and explain the compiler error.
6. Write a Java 21 `switch expression` for `Transport` by **direct permitted subtype**: `case Car`, `case Bike`, `case AirVehicle`, `case ExtensionTransport`, and `case null`. Is `default` needed?
7. Rewrite the switch from Exercise 6 targeting **the leaves** of `AirVehicle`, while still keeping `case ExtensionTransport` to cover the open branch.
8. Given `record Car(List<String> tags) implements Transport {}`, explain why `Car` is final yet the `tags` data is not necessarily deeply immutable.
9. Use `Class.getPermittedSubclasses()` to print the direct permitted types of `Transport` and `AirVehicle`, **sorting the names before printing**. Compare this with your transitive subtype tree.
10. Change `ExtensionTransport` from `non-sealed` to `sealed`, list its direct permitted children, and recompile the switch. State the benefits and costs of tighter control.

**Takeaway:** A sealed parent controls **direct subtypes**, rather than listing all descendants. Every direct class must lock in how it continues using `final`, `sealed`, or `non-sealed`; records are implicitly final. A **final subtype** closes its own branch, whereas a **sealed intermediate subtype** can open another controlled level and a **non-sealed subtype** intentionally opens a branch. In Java 21, these exact relationships allow `switch` to determine an exhaustive set of `case` labels.

## 11. Official References

- [JLS 21, §8.1.1.2 — Sealed, Non-sealed and Final Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2).
- [JLS 21, §8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.6).
- [JLS 21, §9.1.1.4 — Sealed and Non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4).
- [JLS 21, §9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.4).
- [Oracle Java 21 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
