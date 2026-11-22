# Exact Class Comparison vs. Checking Subtype Compatibility in Java

## 1. Two Different Questions About an Object's Type

In Java, the **actual class** (*runtime class*) of an object is the class of the object instantiated at runtime, not necessarily the declared type of the variable referencing it. Distinguish two common requirements:

1. **Is it this exact class?** Does the object have the exact runtime class `SomeClass`, without accepting subclasses? Use `obj.getClass() == SomeClass.class` after ensuring `obj != null`.
2. **Is it an object of this type or a subtype?** Can the object be treated as a `SomeClass` according to inheritance or interface implementation? Use `obj instanceof SomeClass`.

Example:

```java
class Animal {}
class Dog extends Animal {}
class Poodle extends Dog {}

Animal pet = new Poodle();

System.out.println(pet instanceof Animal);       // true
System.out.println(pet instanceof Dog);          // true
System.out.println(pet.getClass() == Animal.class); // false
System.out.println(pet.getClass() == Poodle.class); // true
```

This is **a snippet illustrating declarations/statements**; a standalone compilable/runnable program is provided in Section 5. The variable `pet` is declared as `Animal`, yet the actual object is `Poodle`. Thus the same reference can pass the "is an `Animal`" check while not having a runtime class equal to `Animal.class`.

| Expression | Question | `new Poodle()` in hierarchy `Animal → Dog → Poodle` |
| --- | --- | --- |
| `obj instanceof Animal` | Is the object compatible with `Animal`? | `true` |
| `obj instanceof Dog` | Is the object compatible with `Dog`? | `true` |
| `obj instanceof Poodle` | Is the object compatible with `Poodle`? | `true` |
| `obj.getClass() == Animal.class` | Is the runtime class literally `Animal`? | `false` |
| `obj.getClass() == Poodle.class` | Is the runtime class literally `Poodle`? | `true` |
| `Animal.class.isInstance(obj)` | Runtime check equivalent to `instanceof Animal`? | `true` |
| `Animal.class.isAssignableFrom(Poodle.class)` | Can a `Poodle` object be assigned to an `Animal` reference? | `true` |

These are two different **type policies**, not two equivalent syntaxes that can be swapped arbitrarily.

## 2. `getClass() == SomeClass.class`: Exact Class Comparison

Every Java object inherits `public final Class<?> getClass()` from `Object`. It returns a `Class` object representing the **runtime type**. To check the exact class:

```java
if (obj != null && obj.getClass() == Animal.class) {
    // Only objects whose actual class is strictly Animal.
}
```

This is **a snippet placed inside a method that already has variable `obj`**. Checking `obj != null` is critical: `obj.getClass()` throws `NullPointerException` when `obj == null`. By contrast, `null instanceof Animal` is always `false` (when the left-hand side is a null reference).

### Why Use `==` Between `Class` Objects?

Within a single loaded class, the `Class` object representing the runtime type is unique, so comparing with `==` is appropriate for checking the **same runtime class**. There is no need to compare class names as strings:

```java
obj.getClass().getName().equals("com.example.Animal")
```

The snippet above is **an illustrative name comparison**, not the recommended way to perform exact class checks. Two classes loaded by two different class loaders can share the same binary name while still being two different runtime types. `getClass() == Animal.class` accurately reflects this distinction.

### When Is Exact Checking Useful?

- In defining equality by **value type**, if a subclass object is not allowed to equal a superclass object even when shared fields match.
- When processing branches require **the exact current class**, rejecting any subtype.
- When checking invariants of a model where the value kind must be exact—for example, certain data comparisons that have no cross-type equivalence policy.

**Limitation:** Checking with `getClass` excludes all subclasses, even subclasses that add no state. If the system uses runtime-generated subclass proxies or a subclass-based framework, exact type checking may conflict with business requirements. Do not apply it mechanically just because `instanceof` seems "too broad".

## 3. `instanceof`: Checking Compatibility with a Target Type

The `instanceof` operator returns `true` if a non-null reference points to an object that can undergo a valid type-check conversion (*casting conversion*) to the target type under Java's rules. For ordinary classes and interfaces, that includes the **exact class** and **subtypes**; for interfaces, it includes objects of classes implementing the interface.

```java
Object value = "hello";
System.out.println(value instanceof String);       // true
System.out.println(value instanceof CharSequence); // true
System.out.println(value instanceof Object);       // true
```

This is **an illustrative snippet running inside a method**; `String` implements `CharSequence` and is also an `Object`. This check is appropriate when code needs to use a **capability represented by a superclass or interface** without needing to know the concrete implementing class.

From Java 16 onward, `instanceof` supports **pattern matching**:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

This is **a snippet inside a method that already has variable `value`**. The pattern variable `text` is only available where the check guarantees it within the scope determined by the compiler; Java performs the check and provides a variable of type `String` without an explicit cast.

However, **an `instanceof` check does not prove that every object of a superclass can be cast to a subclass**. Only when `obj instanceof Dog` is true may you use it as a `Dog`; `obj instanceof Animal` being true does not prove it is a `Dog`.

### Relationship to `Class.isInstance` and `Class.isAssignableFrom`

When the target type is known when writing the code, `instanceof Animal` is the most direct form. When the target type sits in a `Class<?>` variable (for example passed from configuration or a reflection API), you can use:

```java
Class<?> target = Animal.class;
boolean supported = target.isInstance(obj);
```

This is **a snippet inside a method**; `Class.isInstance(obj)` takes an **object or null** and returns a boolean. It does not require invoking a method on `obj`, so `target.isInstance(null)` is `false` instead of throwing `NullPointerException`.

With `Class.isAssignableFrom(otherClass)`, both sides are **`Class` objects**:

```java
boolean animalFromDog = Animal.class.isAssignableFrom(Dog.class); // true
boolean dogFromAnimal = Dog.class.isAssignableFrom(Animal.class); // false
```

This is **an illustrative snippet** using the `Animal` and `Dog` declarations above. The direction of the check is crucial: `A.class.isAssignableFrom(B.class)` asks whether a value of type `B` can be assigned where an `A` is expected, not the reverse. It is useful in reflection, generic containers, and frameworks when we need to check type compatibility **before having an instance**.

## 4. Special Consequences for the `equals()` Contract

In the **object-contract** module, the difference between `getClass` and `instanceof` is especially important in **`Object.equals(Object)`**. A valid `equals` method must be reflexive, symmetric, transitive, consistent, and return `false` when compared to `null`.

### 4.1. Using `instanceof` Can Cause a Superclass to Accept Subclasses

Suppose class `Point` has `x` and `y`, while `ColoredPoint extends Point` adds a `color` field. If `Point.equals` uses:

```java
if (!(other instanceof Point p)) return false;
return x == p.x && y == p.y;
```

This is **an illustrative body** of `equals` in class `Point`. The superclass method accepts `ColoredPoint` as well because the subclass is also a `Point`. However, if `ColoredPoint.equals` also checks color and rejects a plain `Point`, the following can happen:

```text
point.equals(coloredPoint)  -> true
coloredPoint.equals(point)  -> false
```

When the two directions return different results, **symmetry is broken**. The bug is not that `instanceof` itself is wrong, but that **the two classes define incompatible equality relations**. Simply swapping `instanceof` in one method without reviewing the whole hierarchy is not enough to preserve the contract.

### 4.2. Using `getClass` to Enforce a "Same Class Only" Policy

If objects of two different runtime classes **should never be equal**, `Point.equals` can check:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (other == null || getClass() != other.getClass()) return false;
    Point that = (Point) other;
    return x == that.x && y == that.y;
}
```

This is **a method belonging to class `Point`**, assuming fields `x` and `y` are declared; not a standalone program. When a plain `Point` is compared with a `ColoredPoint`, the runtime class check fails in both directions and both methods can consistently return `false`.

On the subclass side, you must build `equals` and `hashCode` compatibly with both inherited data and new data. The example in Section 5 shows a complete, runnable version.

**Important note:** `getClass` in the superclass does not automatically make every `equals` override in subclasses obey the contract. A subclass can be coded incorrectly or use an asymmetric equality relation in its implementation. `getClass` only helps establish an exact-type policy when all classes follow it.

### 4.3. Using `instanceof` Can Still Be Right When the Model Fits

For a **`final` class** with no subclasses, checking `other instanceof FinalValue` and checking the exact class generally lead to the same valid object domain. A hierarchy can also use `instanceof` if **all involved classes share a single stable equality definition**, with no subclass silently adding criteria that skew the relation.

If certain subclasses genuinely need to equal the superclass, you can use a cooperative design such as `canEqual` or a shared identity model; you must still verify symmetry, transitivity, `hashCode`, and edge cases. `getClass` is not the default "upgrade" over `instanceof` in every problem.

## 5. Complete Java 17+ Program: Type Checks and Verifying `equals`

Save the following program as **`RuntimeClassDemo.java`**. The first part illustrates runtime types across three inherited classes. The second part uses `getClass` in `Point.equals` and implements `ColoredPoint` to test equality between parent and child in both directions.

```java
import java.util.Objects;

public class RuntimeClassDemo {
    static class Animal {}
    static class Dog extends Animal {}
    static final class Poodle extends Dog {}

    static class Point {
        private final int x, y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (other == null || getClass() != other.getClass()) {
                return false;
            }
            Point that = (Point) other;
            return x == that.x && y == that.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint extends Point {
        private final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!super.equals(other)) return false;
            ColoredPoint that = (ColoredPoint) other;
            return color.equals(that.color);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + color.hashCode();
        }
    }

    public static void main(String[] args) {
        Object poodle = new Poodle();
        System.out.println("instanceof Animal = "
                + (poodle instanceof Animal));
        System.out.println("instanceof Dog = "
                + (poodle instanceof Dog));
        System.out.println("exact Animal class = "
                + (poodle.getClass() == Animal.class));
        System.out.println("exact Poodle class = "
                + (poodle.getClass() == Poodle.class));
        System.out.println("Animal isInstance = "
                + Animal.class.isInstance(poodle));
        System.out.println("Animal assignable from Poodle = "
                + Animal.class.isAssignableFrom(Poodle.class));
        System.out.println("Poodle assignable from Animal = "
                + Poodle.class.isAssignableFrom(Animal.class));
        Object missing = null;
        System.out.println("null instanceof Animal = "
                + (missing instanceof Animal));

        Point base = new Point(2, 3);
        ColoredPoint red = new ColoredPoint(2, 3, "red");
        ColoredPoint copy = new ColoredPoint(2, 3, "red");
        System.out.println("base.equals(red) = " + base.equals(red));
        System.out.println("red.equals(base) = " + red.equals(base));
        System.out.println("red.equals(copy) = " + red.equals(copy));
        System.out.println("equal colored hash = "
                + (red.hashCode() == copy.hashCode()));
    }
}
```

Run in the directory containing the file with JDK 17 or higher:

```bash
javac RuntimeClassDemo.java
java RuntimeClassDemo
```

Output:

```text
instanceof Animal = true
instanceof Dog = true
exact Animal class = false
exact Poodle class = true
Animal isInstance = true
Animal assignable from Poodle = true
Poodle assignable from Animal = false
null instanceof Animal = false
base.equals(red) = false
red.equals(base) = false
red.equals(copy) = true
equal colored hash = true
```

**Explanation of output:**

1. The `Poodle` object is also a `Dog` and an `Animal`, so the first two `instanceof` checks are both true. However, the object's runtime class is **`Poodle`**, not `Animal`.
2. `Animal.class.isInstance(poodle)` is also `true`: this is the runtime check when type information is held in a `Class` object. `isAssignableFrom` shows that the inheritance direction `Poodle → Animal` is valid for assignment; the `Animal → Poodle` direction is not.
3. A `null` reference yields `false` when used with `instanceof`. Calling `missing.getClass()` without a null check would throw `NullPointerException`.
4. `base.equals(red)` is `false` because runtime class `Point` differs from `ColoredPoint`. The reverse direction is also `false`, because `super.equals(other)` detects the different class.
5. Two independent `ColoredPoint` instances with the same coordinates and color return `true`. Both compute their hash from the inherited point part and color, so equal objects also share the same hash.

Do not generalize that any two objects of the same class are equal. `getClass` only answers whether **types are compatible under the chosen policy**, while field contents must still be compared properly in `equals`.

## 6. When Should You Use Which Check?

| Scenario | Suitable Choice | Reason |
| --- | --- | --- |
| Handling any object implementing an interface | `instanceof InterfaceType` | Accepts different implementations |
| Accepting an object of a base class or any subclass | `instanceof BaseType` | Supports polymorphism |
| Handling only the exact runtime class `FinalMessage` or `ExactEvent` | `getClass() == ExactEvent.class` | Does not accept subclasses |
| Value class where `equals` can only be `true` within the same runtime class | `getClass()` in `equals` along with field checks | Establishes an exact-type equality policy |
| Type chosen dynamically via `Class<?> target` | `target.isInstance(obj)` | Checks compatibility with an instance when the type is runtime data |
| Determining whether two types are assignable in one direction | `Target.class.isAssignableFrom(Source.class)` | A question about **types**, requiring no instance |
| Safe casting and declaring a new variable | `obj instanceof Target t` | Both checks and binds the pattern variable in the appropriate scope |
| Objects created by a framework using runtime subclass proxies | Design the domain policy first | `getClass` sees the proxy class instead of always seeing the original model class |

### Two Common Reflection Pitfalls

- `A.class.isAssignableFrom(B.class)` goes from **target type** `A` to **source type** `B`. Reversing it produces a different result; in a parent/child relationship, only one direction can be assigned safely.
- `Class.isInstance` is not `getClass()==...`. `Animal.class.isInstance(new Poodle())` is `true` even though the two `Class` objects `Animal.class` and `Poodle.class` are not identical.

An `Object` variable can point to an object carrying any runtime type. Therefore, when you want to know what **behavior** an object supports, usually use interfaces and `instanceof`/polymorphism; when you want to enforce exact **runtime class identity**, use `getClass` or compare `Class` objects.

## 7. Edge Cases and Limitations of Both Approaches

### 7.1. `null`

`obj instanceof SomeType` is `false` if `obj == null`. `SomeType.class.isInstance(null)` also returns `false`. Meanwhile, `obj.getClass()` throws `NullPointerException`; an exact-class check must follow a null check. When writing `equals`, typically start with:

```java
if (this == other) return true;
if (other == null || getClass() != other.getClass()) return false;
```

This is **a logic snippet inside `equals`**, not a standalone program. It handles both same-reference comparison and avoiding a `getClass` call on a null object.

### 7.2. Interfaces, Abstract Classes, and Polymorphic Types

An object implementing `Runnable` can satisfy `obj instanceof Runnable`. However, `obj.getClass() == Runnable.class` is always false for an ordinary instance, because an interface is not a class that can be instantiated directly. Similarly, a subclass instance can satisfy `obj instanceof AbstractBase`, while its runtime class cannot equal an abstract class that cannot be instantiated.

This clarifies the distinction: **"belonging to a type" does not mean "having a runtime class identical to that type"**.

### 7.3. Arrays

A `String[]` array satisfies `instanceof Object[]` because its elements are references, yet its runtime class does not equal `Object[].class`; it equals `String[].class`. An `int[]` array, on the other hand, is **not** an `Object[]` because its elements are primitive; nevertheless the `int[]` array itself is still an `Object`. Different array kinds have different runtime classes and can be distinguished via `getClass` when the exact array type is truly needed.

### 7.4. Proxies and Dynamically Generated Classes

Some frameworks create proxies by generating subclasses of a domain class. In that case, `getClass() == DomainType.class` can be `false` even though the proxy is designed to act as a `DomainType` in the application. Conversely, `proxy instanceof DomainType` can be `true` when the proxy extends `DomainType`.

**Not every proxy is a subclass of the domain class**: interface-based proxies have type relationships through interfaces rather than necessarily inheriting a concrete class. ORMs and frameworks also have their own policies regarding identity, lazy loading, and `equals`. Define identity rules at the domain level or follow your framework's guidance rather than automatically picking `getClass` or `instanceof` from a simplistic example.

### 7.5. New Subclasses Can Break the `equals` Contract

Even when the superclass uses `getClass` properly, a subclass implementing an asymmetric `equals` or forgetting `hashCode` can still break the contract. In value models, using `final class` or `record` (implicitly final) usually reduces the risk of subclasses altering equality criteria. When inheritance is needed, you must verify the entire relationship across all actual classes that may appear.

## 8. Common Mistakes and Self-Check

| Mistake | Cause | Fix |
| --- | --- | --- |
| Thinking `obj instanceof Base` only matches `Base` itself | Overlooks subtypes | Use `getClass() == Base.class` when you want the exact runtime class |
| Thinking `obj.getClass() == Base.class` accepts subclasses | Exact `Class` equality, not inheritance-based | Use `instanceof Base` or `Base.class.isInstance(obj)` |
| Calling `getClass()` on null | Null dereference | Check `obj != null` first |
| Reversing `isAssignableFrom` | Confusing source class and target class | Remember `Target.class.isAssignableFrom(Source.class)` |
| Superclass uses `instanceof` while subclass adds its own equality criteria | `equals` can become asymmetric or non-transitive | Design a consistent equality relation across the hierarchy |
| Replacing `instanceof` with `getClass` everywhere without considering the domain | Rejects all subclasses/proxies | Determine whether you need type compatibility or the exact class |
| Comparing class names as strings instead of `Class` objects | Class loaders can create different types with the same name | Compare `Class` directly when checking type identity |
| Checking `instanceof` and still casting wrongly | Checking one type while casting to another subtype | Use a pattern variable of the exact checked type |
| Checking only type in `equals`, forgetting values and `hashCode` | Incomplete equality contract | Compare equality-defining fields and produce a compatible hash |

### Self-Check Questions

**1.** `Animal pet = new Poodle();`. Is `pet.getClass() == Animal.class` true? What about `pet instanceof Animal`?

The results are `false` and `true`, respectively. The variable's declared type does not change the object's runtime class.

**2.** `Class<?> target = Animal.class`. Does `target.isInstance(new Poodle())` mean something different from `new Poodle().getClass() == Animal.class`?

Yes. The first expression checks type compatibility and gives `true`; the second checks the exact runtime class and gives `false`.

**3.** In the `Point` hierarchy, `ColoredPoint` adds color to determine identity. If the superclass uses `instanceof Point` to treat the subclass as equal by coordinates, while the subclass rejects the superclass, which property is violated?

**Symmetry** of `equals`. The two directions give different results. One solution is an exact runtime-class policy on both sides, provided it fits the business domain.

**4.** What does `Runnable.class.isAssignableFrom(MyTask.class)` being true mean?

If `MyTask` implements `Runnable`, then a `MyTask` object can be used wherever a `Runnable` is needed. It does not claim the object's runtime class is literally `Runnable.class`.

**Key Takeaway:** `instanceof` answers "can the object **be treated as** this type?", whereas `getClass() == SomeType.class` answers "does the object have **this exact runtime class**?". For `equals` and object contracts, the choice depends on how the application defines equality across the hierarchy; after the type check, you must still compare values and ensure a compatible `hashCode`.