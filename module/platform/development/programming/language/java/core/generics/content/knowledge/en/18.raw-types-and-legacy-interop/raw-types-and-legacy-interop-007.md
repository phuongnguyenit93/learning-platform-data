# Raw Types in Inner Classes and Restrictions on Partial Parameterization in Java Generics

## 1. The Problem: Why Can't Raw and Generic Forms Be Mixed Arbitrarily?

A generic class can declare a member class inside it:

~~~java
class Outer<T> {
    class Inner<U> {
    }
}
~~~

Here there are **two type parameters belonging to two distinct declarations**:

- `T` is declared by `Outer<T>`. Every non-static `Inner<U>` object is attached to an `Outer<T>` object, so it can use members of type T from the outer object.
- `U` is declared by `Inner<U>`. It governs members using U in the inner class.

The following representations are important:

~~~java
Outer<String>.Inner<Integer> complete; // Type-valid.
Outer rawOuter;                         // Raw Outer.
Outer.Inner rawInner;                   // Raw member type.
~~~

Conversely, with class `Inner<U>` declared directly inside `Outer<T>` as above, Java **does not permit partial parameterization** by combining a raw outer with an inner that has a type argument, or a parameterized outer with a raw inner:

~~~java
// Outer.Inner<Integer> bad1; // Invalid.
// Outer<String>.Inner bad2;   // Invalid.
~~~

These two intentionally invalid examples are commented out so you do not accidentally put them into a runnable program. The error is not simply "forgetting `<>`". Java has rules for **raw member types** and **types declared at nested levels**, preventing a hybrid type where half retains generic information and half has lost its enclosing generic context.

This lesson focuses on **member classes**, especially **non-static inner classes** of generic outer classes; it then distinguishes them from **static nested classes**, member classes that do not declare U themselves, diamonds, wildcards, and situations that trigger unchecked warnings.

## 2. Foundational Concepts: Member, Inner, Nested, and Enclosing Type

In Java:

~~~java
class Outer<T> {
    class Inner<U> { }       // Non-static member class (inner class).
    class PlainInner { }    // Inner class with no type parameter of its own.
    static class Nested<V> { } // Static nested class.
}
~~~

There are three concepts to keep separate:

A **member class** is a class declared as a member of another class/interface. It can be static or non-static.

An **inner class** in this example is a **non-static** member class, attached to an outer instance. An `Outer<String>.Inner<Integer>` object is associated with a specific `Outer<String>` object; methods inside can read outer's T fields and inner's U fields.

A **static nested class** is a static member class. It **has no implicit outer instance** and cannot directly use the type parameter T of `Outer<T>`. If a static nested class wants to be generic, it must declare its own type parameter, such as `V`.

Do not call all nested classes inner classes. The static/non-static distinction determines how outer type parameters can be accessed and the rules for object instantiation.

## 3. Raw Type Rules for Member Classes

A *raw type* is the use of a generic class/interface name without providing type arguments (in contexts where Java permits it). With `Outer<T>`, the name `Outer` standing alone in a type position is raw.

When a non-static member class is **declared directly** inside a raw outer class, the member type of the raw outer is also considered raw. This still matters even if the member class itself declares no type parameter.

~~~java
class Outer<T> {
    class Inner<U> {
        T ownerValue;
        U innerValue;
    }

    class PlainInner {
        T ownerValue;
    }
}
~~~

Cases:

| Type syntax | Valid? | Meaning |
| --- | --- | --- |
| `Outer<String>.Inner<Integer>` | Yes | Outer has T = String, Inner has U = Integer. |
| `Outer.Inner` | Yes | Raw Outer and raw member Inner; related generic info is erased. |
| `Outer<String>.Inner<?>` | Yes | Outer knows String; U is unknown, represented by a wildcard. |
| `Outer<?>.Inner<?>` | Yes | Both levels are parameterized with wildcards, not raw. |
| `Outer.Inner<Integer>` | No | Cannot attach U = Integer to Inner of a raw Outer. |
| `Outer<String>.Inner` | No | Cannot keep Outer<String> while using raw Inner<U> this way. |
| `Outer<String>.PlainInner` | Yes | PlainInner has no U of its own, yet knows outer's T. |
| `Outer.PlainInner` | Yes | Member type of raw Outer; members using T are viewed via erasure. |

This table is based on the structure of a **member class declared directly** inside Outer in the example. For member types inherited from a superclass or superinterface, you must inspect the exact place where the member is declared; do not apply the rule mechanically to every dotted type name.

"No partial parameterization" must be understood in its specific scope: this rule **does not forbid every type lacking angle brackets `<>` at the inner level**. For instance, `Outer<String>.PlainInner` is completely valid because `PlainInner` has no type parameter U to supply. Conversely, `Inner<U>` is a generic member class, so omitting U carries a raw meaning in an invalid combination.

## 4. Complete Runnable Program on Java 17+

Save the following program to file **RawInnerDemo.java**:

~~~java
public class RawInnerDemo {
    static class Outer<T> {
        private final T label;

        Outer(T label) {
            this.label = label;
        }

        class Inner<U> {
            private final U value;

            Inner(U value) {
                this.value = value;
            }

            T ownerLabel() {
                return label;
            }

            U payload() {
                return value;
            }
        }

        // Non-generic at PlainMember level, but uses Outer's T.
        class PlainMember {
            T ownerLabel() {
                return label;
            }
        }

        // Does not directly use Outer's T.
        static class StaticNested<V> {
            private final V value;

            StaticNested(V value) {
                this.value = value;
            }

            V get() {
                return value;
            }
        }
    }

    public static void main(String[] args) {
        Outer<String> typed = new Outer<>("owner");

        // Both outer and inner are fully parameterized.
        Outer<String>.Inner<Integer> inner = typed.new Inner<>(7);
        System.out.println(
                "typed=" + inner.ownerLabel() + "/" + inner.payload()
        );

        // PlainMember has no U of its own, yet knows outer T = String.
        Outer<String>.PlainMember plain = typed.new PlainMember();
        System.out.println("plain=" + plain.ownerLabel());

        // Wildcard is still parameterized, not raw.
        Outer<?> wildcardOuter = typed;
        Outer<?>.Inner<?> unknown = wildcardOuter.new Inner<>("text");
        Object read = unknown.payload();
        System.out.println("wildcard=" + read);

        // Raw Outer causes member Inner to be used in raw form.
        Outer rawOuter = typed;
        Outer.Inner rawInner = rawOuter.new Inner(42);
        Object rawOwner = rawInner.ownerLabel();
        Object rawPayload = rawInner.payload();
        System.out.println("raw=" + rawOwner + "/" + rawPayload);

        // Non-generic member is also affected by raw outer.
        Outer.PlainMember rawPlain = rawOuter.new PlainMember();
        Object rawPlainOwner = rawPlain.ownerLabel();
        System.out.println("rawPlain=" + rawPlainOwner);

        // Static nested class has a type parameter independent of T.
        Outer.StaticNested<String> nested =
                new Outer.StaticNested<>("static");
        System.out.println("nested=" + nested.get());
    }
}
~~~

Compile and run:

~~~bash
javac -Xlint:rawtypes -Xlint:unchecked RawInnerDemo.java
java RawInnerDemo
~~~

`-Xlint:rawtypes` reports where raw class/member types are used; `-Xlint:unchecked` reports raw operations with incomplete type checking, such as calling constructor `Inner(U)` via a raw member type. Compiler warnings from javac are not part of the program's stdout.

Stdout when the program runs:

~~~text
typed=owner/7
plain=owner
wildcard=text
raw=owner/42
rawPlain=owner
nested=static
~~~

### Why does each line have that type?

- `typed` is `Outer<String>`, so `inner.ownerLabel()` is seen by the compiler as returning `String`. `inner` is `Inner<Integer>`, so `payload()` returns `Integer`.
- `PlainMember` has no type parameter of its own; it still sees T from `Outer<String>`, so `plain.ownerLabel()` returns `String`.
- With `Outer<?>.Inner<?>`, types T and U are undetermined; results can be read as `Object`, while still retaining wildcard generic checking.
- `rawOuter` has raw type `Outer` even though the runtime object is still the exact instance created for `typed`. Member `Inner` via raw Outer is also raw. Hence both `ownerLabel()` and `payload()` are viewed via erased types, which in this example are `Object`.
- `Outer.PlainMember` uses raw outer, so the getter depending on T is also seen after erasure as `Object`.
- `StaticNested<String>` is a complete generic type of a **static member class**; there is no outer instance, and type argument String is independent of T.

Note: the fact that the program compiles and runs with raw types **does not prove raw is safe**. This is an intentional example to pinpoint where type information is lost.

## 5. Why Is `Outer.Inner<Integer>` Rejected?

Revisit:

~~~java
class Outer<T> {
    class Inner<U> {
        T ownerValue;
        U value;
    }
}
~~~

The following line is **invalid type syntax**:

~~~java
// Outer.Inner<Integer> invalid;
~~~

`Outer` is raw. Under raw member type rules, `Inner` follows the raw Outer in this case; Java does not allow "restoring" only parameter U to Integer while leaving outer's T omitted.

When tried in Java 17+, javac may report:

~~~text
improperly formed type, type arguments given on a raw type
~~~

The fix is to parameterize both outer and inner completely:

~~~java
Outer<String>.Inner<Integer> valid;
~~~

If outer's T is unknown, a wildcard can also preserve the parameterized structure:

~~~java
Outer<?>.Inner<Integer> validWithUnknownOuter;
~~~

The declaration above is type-valid; you need a matching `Outer<?>` instance and syntax `outerInstance.new Inner<>(...)` to instantiate because Inner is non-static. You cannot arbitrarily construct an inner without its enclosing outer object.

### Case where only U is known, not T

Do not pick raw Outer to work around the error. You can use:

~~~java
Outer<?> anyOuter = new Outer<String>("owner");
Outer<?>.Inner<Integer> value = anyOuter.new Inner<>(99);
Object ownerPart = value.ownerLabel();
Integer innerPart = value.payload();
~~~

The unknown T part is represented by a wildcard; U remains clearly Integer. `ownerPart` can only be safely read as Object, while `innerPart` is Integer. This is a major difference between **not knowing a type argument** and **dropping the type parameter system altogether via raw**.

## 6. Why Is `Outer<String>.Inner` Also Rejected?

The following line is also invalid with generic `Inner<U>`:

~~~java
// Outer<String>.Inner invalid;
~~~

A parameterized outer must not be combined with a raw inner in this type position. Javac typically diagnoses:

~~~text
improperly formed type, some parameters are missing
~~~

A programmer may want to express "outer definitely holds String, yet I do not know type U". The proper syntax is a **wildcard**:

~~~java
Outer<String>.Inner<?> validUnknownInner;
~~~

If U is known to be Integer:

~~~java
Outer<String>.Inner<Integer> validKnownInner;
~~~

If you need to handle multiple different U types, you can declare a method accepting `Outer<String>.Inner<?>` and read `payload()` as Object, while retaining the String relationship of owner.

**Do not use raw types merely to express "unknown".** `?` is precisely how you express unknownness while remaining subject to generic checks.

## 7. Why Can a Non-Generic Member Class Still Be Affected?

A subtle example:

~~~java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    class PlainInner {
        T readOuter() {
            return value;
        }
    }
}
~~~

`PlainInner` itself has no type parameter of its own, yet it **uses Outer's T**.

~~~java
Outer<String> typed = new Outer<>("hello");
Outer<String>.PlainInner a = typed.new PlainInner();
String x = a.readOuter();
~~~

This style is valid and preserves String thanks to qualifier `Outer<String>`.

When outer is used raw:

~~~java
Outer raw = typed;
Outer.PlainInner b = raw.new PlainInner();
Object y = b.readOuter();
~~~

The runtime value may still be String, but the compile-time type of `readOuter()` through the raw member is Object because the generic link with outer was lost.

This shows that raw member classes do not occur only when inner itself declares `<U>`. The rule concerns **member types of a raw enclosing class**, not just the count of type parameters immediately following the inner name.

## 8. Static Nested Classes Are a Different Case

With:

~~~java
class Outer<T> {
    static class Nested<V> {
        V value;

        Nested(V value) {
            this.value = value;
        }
    }
}
~~~

`Nested<V>` is static. It has no enclosing instance of `Outer<T>` and cannot directly use Outer's type variable T as a T-dependent instance member, because static members are not tied to outer's parameterization.

Proper parameterization:

~~~java
Outer.Nested<String> a = new Outer.Nested<>("text");
Outer.Nested<Integer> b = new Outer.Nested<>(123);
~~~

`Outer` here is **the qualifying name of the static nested class**, not an indication that a raw outer instance is used to construct an inner instance. `Nested<String>` remains a complete parameterized type of the nested class itself.

The following syntax is rejected:

~~~java
// Outer<String>.Nested<Integer> bad; // Invalid.
~~~

javac may report:

~~~text
cannot select a static class from a parameterized type
~~~

Because static Nested needs no outer instance and does not depend on T, you must not attach `Outer<String>` to its name in that way.

A non-generic static nested class like `Outer.Helper` is a non-generic type if Helper itself declares no type parameter. Do not apply non-static raw member rules to static nested classes merely because they appear inside a generic class.

## 9. Raw Outer and Constructor Calls

When you have a parameterized outer variable:

~~~java
Outer<String> outer = new Outer<>("label");
Outer<String>.Inner<Integer> inner = outer.new Inner<>(42);
~~~

The syntax `outer.new Inner<>(42)` does two things:

1. Associates the newly created Inner object with a specific **outer instance**.
2. Infers type argument U from the constructor or target context; here U is Integer.

Diamond `<>` does not create a raw type. It denotes **type argument inference**.

Conversely:

~~~java
Outer raw = new Outer("label");
Outer.Inner inner = raw.new Inner(42);
~~~

This example uses raw Outer and raw Inner; javac may report rawtypes/unchecked. Passing `(42)` does not cause the compiler to automatically promote `Inner` to `Inner<Integer>`, because it is invoked through a raw enclosing type.

It is this difference between **raw construction** and **diamond construction** that easily misleads readers into assuming the compiler can always infer U from constructor arguments. When the enclosing type is already raw, raw member type restrictions apply.

## 10. Reading Errors Properly and Choosing Fixes

| Goal | Common mistake | Proper representation |
| --- | --- | --- |
| Outer String, Inner Integer | `Outer<String>.Inner<Integer>` | Keep as is; already valid. |
| Unknown Outer T, Inner Integer | `Outer.Inner<Integer>` | `Outer<?>.Inner<Integer>` |
| Outer String, Unknown Inner U | `Outer<String>.Inner` | `Outer<String>.Inner<?>` |
| Both T and U unknown | `Outer.Inner` if only observing data | Prefer `Outer<?>.Inner<?>` |
| Member without its own U | Mistaking `Outer<String>.PlainMember` for missing type arguments | `Outer<String>.PlainMember` is valid. |
| Generic static nested | `Outer<String>.Nested<Integer>` | `Outer.Nested<Integer>` |

The row "Both T and U unknown" is worth noting: raw `Outer.Inner` is still a type name that can compile in some snippets, yet because it drops generic information, it is not a safe choice for new APIs. `Outer<?>.Inner<?>` clearly expresses unknownness at each parameter level and preserves constraints.

### Why not cast raw Inner to a parameterized type and use it?

An unchecked cast cannot reliably restore discarded type information:

~~~java
// Suppose rawInner is Outer.Inner:
@SuppressWarnings("unchecked")
Outer<String>.Inner<Integer> guessed =
        (Outer<String>.Inner<Integer>) rawInner;
~~~

This is an **illustrative code fragment** and cannot run standalone. The ordinary runtime cannot fully verify both T = String and U = Integer of a generic object. If actual data does not match, errors may appear later when reading a field or calling a method.

Preferred approach: keep proper type arguments right when creating outer/inner; if receiving raw data from a legacy API, confine it to the integration boundary and validate the objects/data to be used.

## 11. Type Erasure and Heap Pollution Risk

Raw types do not mean the JVM creates a completely separate class copy for each type parameter value. For ordinary generics, most type parameters are erased during compilation.

In the example:

~~~java
class Outer<T> {
    class Inner<U> {
        T owner();
        U value();
    }
}
~~~

(This illustrates signatures; a standalone Java program must supply method bodies or appropriate declarations.)

When T and U both have no concrete bounds, the erased return descriptors of those methods are Object. Yet for a variable of type `Outer<String>.Inner<Integer>`, the compiler still uses generic signatures to check String/Integer data and can insert casts when needed.

When using raw `Outer.Inner`, the compiler no longer has matching T/U information. A program can accidentally store data incompatible with a parameterized declaration held elsewhere. The risk is **heap pollution** or `ClassCastException` when data is read as a concrete type.

**Do not confuse cause and effect:** merely having a raw reference does not guarantee an immediate error. Trouble arises when the raw path permits operations the compiler cannot prove safe; errors can surface late at another call site.

## 12. Distinguishing Wildcards, Raw Types, and `Object`

Three ways of expressing unknown generic information differ:

~~~java
Outer.Inner rawMember;                 // Raw member.
Outer<?>.Inner<?> unknownMember;      // Two wildcards.
Outer<Object>.Inner<Object> objectMember; // Both T and U are Object.
~~~

- **Raw**: drops type arguments of the related generic types; operations needing T/U checks can trigger unchecked warnings.
- **Wildcard**: knows the object has a generic form with some type arguments without knowing which exact ones; the compiler restricts write operations appropriately.
- **Object arguments**: asserts T and U are specifically Object; still a parameterized type and still checked against Object.

`Outer<String>.Inner<Integer>` does not convert to `Outer<Object>.Inner<Object>`. Java generic types are generally **invariant**. Wildcards can accept different parameterized types under compatibility rules; Object cannot mechanically replace wildcards.

If the goal is merely to read values from any inner object, an API using wildcards usually expresses intent more clearly than raw types or forcing Object parameters.

## 13. Common Mistakes in Code Reviews

### Mistake A: adding `<Integer>` only after a raw inner

~~~java
// Outer.Inner<Integer> fixed; // Still invalid.
~~~

If outer lacks a type argument, fix the outer qualifier first. Use `Outer<?>.Inner<Integer>` when T is unknown or `Outer<String>.Inner<Integer>` when T = String is known.

### Mistake B: using `Outer<String>.Inner` thinking "Inner defaults U = Object"

~~~java
// Outer<String>.Inner value; // Invalid.
~~~

If you genuinely want U = Object, write `Outer<String>.Inner<Object>`. If U is unknown, use `Outer<String>.Inner<?>`. You cannot drop angle brackets at the `Inner<U>` level and expect the compiler to assume Object.

### Mistake C: treating `PlainMember` as generic because it sits inside `Outer<T>`

`PlainMember` declares no U of its own. `Outer<String>.PlainMember` is valid, whereas `Outer<String>.PlainMember<Integer>` is invalid if PlainMember declares no type parameter. It can still use outer's T through context.

### Mistake D: treating a static nested class as an inner class

`Outer.Nested<Integer>` has no enclosing instance. `Outer<String>.Nested<Integer>` is invalid because static Nested is independent of Outer's T parameter.

### Mistake E: using raw to resolve every mismatch

Raw members may let some old code compile with warnings, at the expense of type checking. Revisit type arguments, data models, and wildcard/generic method usage instead of abusing raw and suppressing all warnings.

### Mistake F: confusing direct-member rules with all inheritance cases

Examples in this lesson use member classes **declared directly** in Outer. When a member type appears through a subclass via inheritance, rules for type names and raw members must check **where the member is declared**. Do not infer everything solely from the class name to the left of the dot.

## 14. How to Design APIs Avoiding Raw Inner Classes

When designing an API with generic outer/inner classes:

1. Specify types clearly on both outer and inner when they genuinely carry two independent typed datasets.
2. Provide factories or suitable accessor methods if `outer.new Inner<>(...)` forces callers to repeat types excessively, without hiding the relationship to the outer instance.
3. Use wildcards in data-receiving signatures when T or U is unknown while still needing generic checks.
4. Choose a static nested class when the member does not need access to outer instance state or type parameters.
5. Keep raw types at legacy integration boundaries, preferring data-validating adapters instead of letting raw types leak into business logic.
6. Enable `javac -Xlint:rawtypes -Xlint:unchecked` when reviewing generics code; treat warnings as signals to understand and resolve.
7. Distinguish valid type names from instantiation requirements: non-static inner classes need an outer instance, while static nested classes do not.

Having `Outer<T>` does not mean every class inside it must have generic parameters. Choose non-static inner, static nested, or top-level class based on the **actual data relationship needed**, then apply the corresponding type argument rules.

## 15. Self-Check Questions

**1.** With `class Outer<T> { class Inner<U> {} }`, why is `Outer.Inner<Integer>` invalid?

**Answer:** Outer is raw; non-static member Inner is used in a raw context and cannot parameterize only U while the Outer qualifier lacks T. Use `Outer<?>.Inner<Integer>` or an Outer with a concrete T.

**2.** Why is `Outer<String>.Inner` rejected even though outer's T is known?

**Answer:** Inner still has type parameter U; a raw Inner under qualifier `Outer<String>` is an invalid partial parameterization. Use `Inner<?>` if U is unknown or `Inner<Integer>` if known.

**3.** Is `Outer<String>.PlainInner` valid if PlainInner declares no U of its own?

**Answer:** Yes. PlainInner has no type parameter of its own to omit, and Outer's T is already specified as String.

**4.** Can `Outer.PlainInner` be affected by raw types even though PlainInner is non-generic?

**Answer:** Yes, for a non-static member class declared directly inside a raw Outer; members of PlainInner that depend on T are viewed via erasure.

**5.** Why is `Outer.Nested<String>` the right syntax for a static generic nested class?

**Answer:** Nested is static and is not attached to an Outer instance or Outer's T; type parameter String belongs to `Nested<V>` itself. You must not select a static class with `Outer<String>.Nested`.

**6.** Is `Outer<?>.Inner<?>` a raw type?

**Answer:** No. Both positions have wildcard type arguments; these are parameterized types, and the compiler still enforces the appropriate generic constraints.

**7.** Does the diamond in `typed.new Inner<>(7)` make Inner raw?

**Answer:** No. Diamond requests inference of U; with a fully parameterized outer and suitable initializer, inner gets the right type argument.

**8.** If a call receives an unchecked warning from javac when using raw `Outer.Inner`, does that mean the program will definitely throw an exception?

**Answer:** No. A warning means the compiler cannot fully prove type safety; the program may run, yet the risk of failure or heap pollution rises when wrong-typed data is actually inserted and used.

## 16. Key Takeaways

In a generic hierarchy with non-static member classes, **outer and inner names form a coupled type-parameter context**. When a generic inner class is declared directly inside a generic outer class:

- `Outer<T>.Inner<U>` specifies both type parameters clearly.
- `Outer.Inner` represents the corresponding raw usage.
- `Outer.Inner<U>` and `Outer<T>.Inner` are invalid partial parameterizations in this structure.
- `Outer<?>.Inner<?>` expresses two unknown types without dropping generic checks.
- `Outer<T>.PlainInner` is valid if the member has no type parameter U of its own.
- `Outer.Nested<V>` for a static nested class follows independent rules because it is not tied to an enclosing instance.

When you encounter an `improperly formed type` error, inspect **both the outer qualifier and the member class's generic declaration**, then replace raw/missing type arguments with concrete types or wildcards matching the available information.