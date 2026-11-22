# Member Inner Classes and the Enclosing Class's Type Parameters in Java

A **non-static member inner class** is declared inside the body of another class **without the `static` keyword**. If the enclosing class declares a type parameter `T`, the inner class can use `T` in its fields, constructors, and methods **without redeclaring it**. An inner class can also declare its own type parameter, such as `U`.

A typical example is `Outer<T>.Inner<U>`: `T` is tied to the enclosing class's parameterized type, whereas `U` is the type parameter of the inner class itself. Each inner object is always attached to **a specific outer object**, so object instantiation and member access differ from a `static nested class`.

This lesson explains type variable scope, instantiation syntax, how to read `Outer<String>.Inner<Integer>`, the relationship between the two classes, generics limitations, differences from `static nested class`, and appropriate use cases. The Java examples use syntax runnable on JDK 17 or later.

## 1. Basic Syntax: An Inner Class Using the Outer Class's `T`

Consider the `Container<T>` class:

```java
class Container<T> {
    private final T stored;

    Container(T stored) {
        this.stored = stored;
    }

    class View {
        T get() {
            return stored;
        }
    }
}
```

Key points to read accurately:

- `Container<T>` declares the type parameter `T`.
- `View` is a **non-static member inner class** because it sits inside `Container` without `static`.
- `View` **does not declare its own `<T>`**; when writing `T get()`, it uses `T` belonging to `Container<T>`'s scope.
- `View` can access the `stored` field, even though it is `private`, because Java allows members within the same nested structure to access one another under language rules.
- A `View` object must be attached to an already-created `Container` object.

In a runnable context:

```java
Container<String> container = new Container<>("Java");
Container<String>.View view = container.new View();

String text = view.get(); // Return type is String.
```

Here, `Container<String>.View` is read as **the `View` type belonging to an outer of type `Container<String>`**. Because `T = String`, `View.get()` is type-checked as a method returning `String`.

There is no `View<T>` here: the `View` class has not declared a type parameter of its own. Writing `Container<String>.View<String>` would be wrong because `View` does not accept its own type argument.

## 2. Why Does an Inner Class See the Enclosing Class's Type Parameter?

The scope of a type parameter declared on a class covers the appropriate instance members of that class, including non-`static` member inner class declarations. Because an inner class resides in the outer class's instance context, Java lets its members be expressed using the outer class's own type parameter.

```java
class ResultBox<T> {
    private final T result;

    ResultBox(T result) {
        this.result = result;
    }

    class Reader {
        T read() {
            return result;
        }

        void print() {
            System.out.println(result);
        }
    }
}
```

`Reader.read()` **is not a generic method declaring `<T>` itself**. It simply uses `T` from `ResultBox<T>`. When the outer object is used via `ResultBox<Long>`, `read()`'s result has type `Long`; with `ResultBox<String>`, the result has type `String`.

**There is no need to repeat `<T>` on `Reader`.** Declaring `class Reader<T>` inside `ResultBox<T>` creates a **new type parameter with the same name**, potentially shadowing the outer `T` within the inner scope. That is not a way to "inherit" `T` and easily causes confusion. If the inner class needs its own type, name it something like `<U>` to distinguish them.

The syntactic scope of `T` and attaching an inner object to an outer object are two related yet distinct aspects: `T` serves **static type checking**, whereas an inner object maintains a link to **a specific outer object** at runtime.

## 3. Inner Class with Its Own Type Parameter: `Outer<T>.Inner<U>`

When each inner object needs an additional independent type, declare a new type parameter on the inner class:

```java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    class Inner<U> {
        private final U extra;

        Inner(U extra) {
            this.extra = extra;
        }

        T outerValue() {
            return value;
        }

        U innerValue() {
            return extra;
        }
    }
}
```

In this example:

- `T` is declared by `Outer<T>`.
- `U` is declared by `Inner<U>`.
- `outerValue()` returns the outer's `T`.
- `innerValue()` returns the inner's `U`.
- There is no constraint requiring `T` and `U` to be the same type.

Usage:

```java
Outer<String> outer = new Outer<>("Java");
Outer<String>.Inner<Integer> inner = outer.new Inner<>(17);

String language = inner.outerValue();
Integer version = inner.innerValue();
```

`Outer<String>.Inner<Integer>` is a type carrying **two pieces of generic information at two levels**. `String` is passed to `Outer<T>`, while `Integer` is passed to `Inner<U>`.

Reading from outside in:

| Component | Meaning |
| --- | --- |
| `Outer<T>` | Enclosing class declaring `T` |
| `Outer<String>` | Outer parameterized with `T = String` |
| `Inner<U>` | Inner declaring its own `U` |
| `Outer<String>.Inner<Integer>` | Inner with `T = String` from outer and `U = Integer` of its own |
| `outer.new Inner<>(17)` | Creates an inner attached to `outer`; `U` is inferred from context/arguments |
| `inner.outerValue()` | Returns `String` |
| `inner.innerValue()` | Returns `Integer` |

One outer can create **multiple inner objects with different `U` types**:

```java
Outer<String>.Inner<Integer> count = outer.new Inner<>(3);
Outer<String>.Inner<Boolean> enabled = outer.new Inner<>(true);
```

These inner objects are associated with the same outer having `T = String`, yet each inner has its own type for `U`.

### Difference Between Type Parameters and Object Instances

Two expressions `outer.new Inner<>(3)` and `anotherOuter.new Inner<>(3)` can have the same static type `Outer<String>.Inner<Integer>` if both outers are `Outer<String>`. Even so, the created inner objects remain tied to **two different outer objects** and can observe two different outer states. Type arguments do not describe **object identity**.

## 4. How to Instantiate an Inner Object: `outer.new Inner(...)`

Instantiating a non-static inner class from code outside the outer class requires a valid **enclosing instance**:

```java
Outer<String> outer = new Outer<>("Java");
Outer<String>.Inner<Integer> inner = outer.new Inner<>(17);
```

The syntax `outer.new Inner<>(17)` emphasizes that the inner object is created **in relationship with that specific outer object `outer`**.

The forms below are shown to identify errors, **not as valid code to run**:

```java
// Wrong when standing in a context without an appropriate enclosing instance:
// Outer<String>.Inner<Integer> x = new Inner<>(17);

// Wrong: inner is not an independent static class that can be instantiated directly like that.
// Outer<String>.Inner<Integer> x = new Outer.Inner<>(17);
```

If creating the inner from an **instance method of outer**, Java already has the current enclosing instance and you can write `new Inner<>(...)`:

```java
class Outer<T> {
    class Inner<U> {
        Inner(U data) {}
    }

    <U> Inner<U> create(U value) {
        return new Inner<>(value);
    }
}
```

This is an illustrative snippet independent of the earlier `Outer<T>` declaration. `create` declares `<U>` itself because the method needs to represent the passed-in value's type; the inner class also declares `U`, yet the method's `U` parameter and the inner's `U` parameter are **two separate declarations** linked via `new Inner<>(value)` and the return type `Inner<U>`.

If you do not need to declare a separate `<U>` on `create`, you can also write a method that simply returns an inner with a fixed `U`, such as `Inner<String> createLabel()`.

### Distinguishing from Outer's Constructor

`new Outer<String>("Java")` creates the **outer object**. Afterward, `outer.new Inner<>(17)` creates the **inner object** linked to that outer. Java does not automatically create a new outer when you call a non-static inner class's constructor.

An inner object can be passed out beyond its initial creation scope while retaining its link to the chosen enclosing instance. This characteristic matters when designing object lifecycles.

## 5. Complete Java 17+ Example: Same Inner Class, Different Outer and Inner Types

Save the entire following content to **`Main.java`**. The program contains:

1. `Folder<T>` as the generic enclosing class holding a label of type `T`.
2. `Item<U>` as a **non-static inner class** using both the outer's `T` and its own `U`.
3. `Tag<V>` as a **static nested class** with its own `V`; it does not take `T` from outer.
4. Two outer objects creating inners with different type pairs.

```java
public class Main {
    static final class Folder<T> {
        private final T label;

        Folder(T label) {
            this.label = label;
        }

        final class Item<U> {
            private final U value;

            Item(U value) {
                this.value = value;
            }

            T ownerLabel() {
                return Folder.this.label;
            }

            U payload() {
                return value;
            }

            String describe() {
                return "label=" + label + ", value=" + value;
            }
        }

        static final class Tag<V> {
            private final V value;

            Tag(V value) {
                this.value = value;
            }

            V value() {
                return value;
            }
        }
    }

    public static void main(String[] args) {
        Folder<String> language = new Folder<>("Java");
        Folder<String>.Item<Integer> page = language.new Item<>(17);
        System.out.println("page: " + page.describe());

        Folder<Integer> priority = new Folder<>(3);
        Folder<Integer>.Item<String> note =
                priority.new Item<>("urgent");
        System.out.println("note: " + note.describe());

        Folder.Tag<String> tag = new Folder.Tag<>("shared");
        System.out.println("tag: " + tag.value());

        System.out.println("owner: " + page.ownerLabel());
        System.out.println("payload: " + page.payload());

        // Folder<String>.Item<String> wrong = language.new Item<>(17);
        // Does not compile: inner expects U = String, yet receives Integer.
    }
}
```

Compile/run in the directory containing the file:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout:**

```text
page: label=Java, value=17
note: label=3, value=urgent
tag: shared
owner: Java
payload: 17
```

Explanation:

- `language` is `Folder<String>`; therefore `page.ownerLabel()` has type `String`.
- `page` is `Folder<String>.Item<Integer>`; therefore `page.payload()` has type `Integer`. The `describe()` method can read outer's `label` field and inner's `value` field.
- `priority` is `Folder<Integer>`; therefore `note.ownerLabel()` returns `Integer` and `note.payload()` returns `String`.
- `Folder.Tag<String>` is a static nested class: `V = String` is declared by `Tag<V>` itself, not taken from `Folder<T>`'s type parameter `T`.
- The ill-typed line is commented out so the program compiles normally; if uncommented, the compiler rejects it because the constructor argument does not match `U = String`.

`Folder` is declared `static` inside `Main` only to package the standalone program conveniently. That **does not make `Item` static**: `Item` remains a non-static inner class of `Folder`, whereas `Tag` is a static nested class of `Folder`.

## 6. `Outer.this` and Accessing the Enclosing Object

Because an inner object has an enclosing instance, inner code can read valid instance members of outer, including `private` members:

```java
class Counter<T> {
    private final T name;
    private int count;

    Counter(T name) {
        this.name = name;
    }

    class Incrementer {
        void increase() {
            count++;
        }

        T label() {
            return Counter.this.name;
        }
    }
}
```

Here:

- `count++` accesses the enclosing `Counter`'s field when no identically named inner member shadows it.
- `Counter.this.name` explicitly specifies the **enclosing `Counter` instance** of the current inner.
- `label()` returns `T` belonging to outer; `Incrementer` itself declares no new type parameter.

`Outer.this` is useful when inner and outer have fields with the same name:

```java
class Example<T> {
    T value;

    class Inner {
        String value;

        T outerValue() {
            return Example.this.value;
        }

        String innerValue() {
            return this.value;
        }
    }
}
```

`this.value` points to inner's field; `Example.this.value` points to outer's field. Note that this is **field name shadowing**, different from **type parameter name** shadowing. Both relate to scope, yet they arise from different declarations.

An inner instance can access outer state, though that **does not guarantee state immutability**. If outer has mutable fields, inner can observe or cause mutations to outer through its declared methods.

## 7. Inner Class Using Outer's `T` Without Declaring Its Own Type Parameter

Not every inner class needs `<U>`. For example, designing a reader handle for a vault's data:

```java
class Vault<T> {
    private final T secret;

    Vault(T secret) {
        this.secret = secret;
    }

    class Reader {
        T read() {
            return secret;
        }
    }
}
```

Usage:

```java
Vault<String> vault = new Vault<>("key");
Vault<String>.Reader reader = vault.new Reader();
String result = reader.read();
```

`Reader` is not a generic class **in the sense of declaring a type parameter itself**. Yet **the type `Vault<String>.Reader` still depends on the outer parameterization**. Therefore, do not confuse "an inner without `<U>`" with "an inner unaffected by generics".

If the goal is simply to hold an object referencing outer and provide methods using `T`, this design is usually sufficient. Only add `<U>` when the inner genuinely needs a new independent type.

## 8. Non-Static Inner Class vs. Static Nested Class

Both forms are declared **inside a class body**, yet their relationship to the enclosing instance is completely different.

### 8.1. Non-Static Member Inner Class

```java
class Owner<T> {
    private final T name;

    Owner(T name) {
        this.name = name;
    }

    class Inner {
        T ownerName() {
            return name;
        }
    }
}
```

An `Owner<String>.Inner` is attached to an `Owner<String>` object, so it can use the enclosing class's `T` and access outer's `name` field.

### 8.2. Static Nested Class

```java
class Owner<T> {
    static class Metadata<U> {
        private final U data;

        Metadata(U data) {
            this.data = data;
        }

        U data() {
            return data;
        }
    }
}
```

`Metadata<U>` has no `Owner<T>` enclosing instance, so **it cannot directly use the enclosing class's type parameter `T`** or read outer's instance fields without an object reference passed in.

Usage:

```java
Owner.Metadata<String> meta = new Owner.Metadata<>("info");
String info = meta.data();
```

The proper syntax is `Owner.Metadata<String>`. Do not write `Owner<Integer>.Metadata<String>`: a static nested type does not carry the enclosing class's type argument in its type qualifier. If it needs to work with `T`, declare `Metadata`'s own type parameter or pass in an appropriately typed outer object.

### Direct Comparison

| Criterion | Non-static inner | Static nested |
| --- | --- | --- |
| Declaration | `class Inner` inside outer | `static class Nested` inside outer |
| Has enclosing outer instance | Yes | No |
| Directly uses `T` of `Outer<T>` | Yes, when not shadowed | No |
| Can declare its own type `<U>` | Yes | Yes |
| Common reference type | `Outer<String>.Inner<Integer>` | `Outer.Nested<Integer>` |
| Instantiation from outside outer | `outer.new Inner<>(...)` | `new Outer.Nested<>(...)` |
| Access `Outer.this` | Yes when a matching enclosing instance exists | No |
| Appropriate when | Behavior depends on a specific outer object | Component is only grouped by name and independent of outer objects |

**Design rule:** if a nested class does not need to read or modify an outer object's state, consider a `static nested class` to avoid holding an unnecessary enclosing reference. If the nested class works closely with outer's own state, a non-static inner class is a deliberate choice.

## 9. Type Bounds on Outer and Inner

Outer can constrain `T` and inner can place bounds on `U` without altering each other's responsibilities:

```java
class NumberOwner<T extends Number> {
    private final T number;

    NumberOwner(T number) {
        this.number = number;
    }

    class Caption<U extends CharSequence> {
        private final U text;

        Caption(U text) {
            this.text = text;
        }

        double numericValue() {
            return number.doubleValue();
        }

        int textLength() {
            return text.length();
        }
    }
}
```

Here `T extends Number` ensures outer supports `doubleValue()`, while `U extends CharSequence` ensures inner supports `length()`. Valid declaration:

```java
NumberOwner<Integer> outer = new NumberOwner<>(7);
NumberOwner<Integer>.Caption<String> caption =
        outer.new Caption<>("level");
```

`NumberOwner<String>` is an error because `String` does not extend `Number`. `Caption<Integer>` is an error because `Integer` does not implement `CharSequence`.

Bounds check **reference types**, not specific runtime values. `NumberOwner<Double>` can still hold `Double.NaN`; `Caption<String>` can still hold an empty string if the constructor does not validate it.

## 10. Easily Confused Scope Cases

### 10.1. Do Not Redeclare `<T>` Just to Use Outer's `T`

```java
class Outer<T> {
    class Good {
        T getValue() {
            return null;
        }
    }
}
```

`Good` uses outer's `T`. Writing `class Good<T>` causes inner's `T` to **shadow** outer's `T` within inner's scope; the new `T` is not automatically identical to the old `T`. To avoid confusion, name it `U` when inner needs its own type parameter.

`return null` here only illustrates type-scope syntax, not a complete implementation logic.

### 10.2. A Method Inside Inner Can Have Its Own Type Parameter

```java
class Outer<T> {
    class Inner {
        <U> U echo(U value) {
            return value;
        }
    }
}
```

`U` in `<U> U echo(U value)` belongs to **the method**, not to `Outer` or `Inner`. Thus an `Outer<String>` can have an inner calling `echo(5)` and `echo(true)` with different `U` types. If a method happens to share a name with a type parameter in an outer scope, examine it to avoid shadowing.

### 10.3. Non-Static Member Inner Class vs. Local Class and Anonymous Class

A **member inner class** such as `Outer<T>.Inner` has a name and is declared directly in the outer body. A **local class** is declared inside a block/method; an **anonymous class** has no declared name of its own. Those nested class forms have their own context and scope rules, especially when declared in a static context.

Do not mechanically apply `Outer<T>.Inner<U>` syntax to local or anonymous classes: it is for named member inner types. This lesson focuses on **member inner classes** within the lesson's scope.

### 10.4. Declaring Inner in a Static Context and the Role of `this`

A `static` method has no current enclosing outer instance. It can create an inner if supplied with **an explicit outer object**:

```java
class Outer<T> {
    class Inner {
        T get() {
            return null;
        }
    }

    static <T> Outer<T>.Inner make(Outer<T> outer) {
        return outer.new Inner();
    }
}
```

Here `make`'s `<T>` is **the static method's own type parameter**; it is not `class Outer<T>`'s `T`. Because it receives `Outer<T> outer` as an argument, the static method has an outer instance available to instantiate inner.

Meanwhile, a static method declaration writing only `static Outer<T>.Inner make()` without declaring `T` itself is wrong because a static member cannot directly use an outer instance's type parameter.

## 11. Type Erasure and Runtime Object Relationships

Generics in Java are primarily implemented via **type erasure**: the compiler checks type arguments at compile time and then erases most of that type information from runtime bytecode. The entity `Outer<String>.Inner<Integer>` does not become a separate JVM class compared to `Outer<Long>.Inner<Boolean>`.

Even so, a non-static inner instance remains attached to an enclosing outer object. This is a **real runtime object relationship**, not merely generic notation:

- The syntax `outer.new Inner(...)` selects a specific outer object.
- Inside, `Outer.this` refers to that enclosing instance.
- Compilation typically generates a mechanism to store the enclosing reference for a non-static inner object.
- Keeping an inner alive for a long time can keep the outer alive in memory via the reference relationship, depending on the actual reference graph.

Do not deduce that because type erasure removes `T`, inner "loses access" to the outer object. **Generic type metadata** and **object linkage** are two distinct mechanisms.

Likewise, you cannot use `instanceof Outer<String>.Inner<Integer>` to verify both exact type arguments; a specific parameterized type is not a runtime type checkable directly in that manner. For data coming from reflection, JSON, or raw types, validate data boundaries with an appropriate mechanism.

## 12. When Is an Inner Class Appropriate?

**Appropriate:** the inner object is a **component tied to a specific outer instance**, needing to invoke outer's methods or read outer's fields and use the same type parameter `T`. Examples include cursors, views, iterators, or builders tightly coupled to the enclosing object's state.

**Consider static nested class:** the nested type is grouped under outer for code organization yet does not need `Outer.this` or object state. A helper holding its own configuration, describing metadata, or an independent value object is usually easier to manage without an enclosing reference.

**Consider top-level class:** if the nested type becomes a widely used public API, has an independent lifecycle, or needs many other classes to depend on it, a top-level class with its own name can be clearer. The choice should be based on domain relationships and usage, not merely on whether a nested class can access private members.

**Consider lifecycle cost:** holding an inner instance in a long-lived cache or callback can retain the enclosing object as well. When that link is unneeded, a static nested class generally reduces coupling and prevents unintended reference retention.

## 13. Common Mistakes and Fixes

**Mistake 1 — instantiating a non-static inner without providing an outer object:** use `outer.new Inner(...)` when outside an instance context; do not use `new Outer.Inner(...)` as with static nested classes.

**Mistake 2 — using the wrong type syntax in declarations:** for an inner without its own type parameter, `Outer<String>.Inner` is right—do not write `Outer<String>.Inner<String>`. If inner declares `<U>`, write `Outer<String>.Inner<Integer>`.

**Mistake 3 — mixing outer types:** an `Outer<String>.Inner<Integer>` is not automatically an `Outer<Integer>.Inner<Integer>`. The outer's type argument participates in the member type. Different type arguments cannot be converted merely because they share the same class declaration.

**Mistake 4 — thinking inner must redeclare `<T>` to use outer's `T`:** doing so creates a different type parameter and can shadow the old name. Only declare a new `<U>` when a separate type role is needed.

**Mistake 5 — using outer's `T` inside a static nested class:** static nested classes have no enclosing instance and do not directly carry outer's type parameter. Declare its own type parameter or pass `Outer<T>` from the caller.

**Mistake 6 — accessing shadowed fields without specifying scope:** `this.value` is inner's field if declared; `Outer.this.value` refers to the enclosing outer's field. Use the qualified form when the relationship needs to be clear.

**Mistake 7 — treating inner merely as file grouping:** non-static inners carry a real object link. If neither the link nor state is needed, prefer a static nested or top-level class.

**Mistake 8 — misreading type erasure as removing the outer instance:** erasure removes most runtime type arguments, yet does not remove a non-static inner's enclosing instance relationship.

**Mistake 9 — forgetting null/value validation:** `Outer<String>` does not force `T` to be non-`null`, and `Inner<Integer>` does not force positive numbers. Validation and generic reference types are independent concerns.

## 14. Self-Check

**Question 1.** In `class Outer<T> { class Inner { T read() {...} } }`, does `Inner` need to declare `<T>` again?

**Answer:** No. `Inner` is a non-static member inner class and can use outer's `T`. Declaring `<T>` again would create a different type parameter that shadows the old name.

**Question 2.** Given `Outer<String> outer`, how do you create an inner whose own type parameter is `Integer`?

**Answer:** If declared `class Inner<U>`, use `Outer<String>.Inner<Integer> x = outer.new Inner<>(17);`.

**Question 3.** Why does `Outer<String>.Inner<Integer>` represent two type arguments rather than just `Integer`?

**Answer:** `T = String` comes from `Outer<T>`, and `U = Integer` comes from `Inner<U>`. Methods using `T` have type `String`, while methods using `U` have type `Integer`.

**Question 4.** Can `static class Metadata<U>` inside `Outer<T>` directly return outer's field of type `T`?

**Answer:** No, because a static nested class has no enclosing outer instance and does not directly use outer's `T`. Working with outer data requires passing an appropriate type parameter/object.

**Question 5.** Must two inner objects of the same type `Outer<String>.Inner<Integer>` created from two different outer objects see the same state?

**Answer:** No. Their static type may match, yet each inner is attached to a specific enclosing object and therefore can observe different state.

**Question 6.** Why can retaining an inner object long-term keep the outer object alive in memory?

**Answer:** A non-static inner object holds a reference link to its enclosing outer object; as long as the reference graph retains the inner and no link-breaking mechanism is present, outer can remain reachable through inner.

## Conclusion

A non-static member inner class lies within the outer class's generic scope, so it can use `T` from `Outer<T>` without redeclaring it. When independent data is needed, inner can declare `U` and be used with a type like `Outer<String>.Inner<Integer>`. When instantiating inner from outside, an enclosing object must be supplied in `outer.new Inner(...)`. Distinguish it from a `static nested class`: the static kind has its own type parameters and does not carry `T` or an outer instance reference the way a non-static inner class does. Understanding both **compile-time type scope** and **runtime object relationships** helps you choose the right nesting structure, reduce syntax errors, and clearly control object lifecycles.
