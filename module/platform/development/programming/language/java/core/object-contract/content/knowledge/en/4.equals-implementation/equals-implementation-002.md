# Why Is `equals(MyType)` an Overload Instead of an Override?

## 1. The Deciding Factor Is the Method Signature

Every Java class inherits (directly or indirectly) from `java.lang.Object`. The equality comparison method that Java declares on `Object` is:

```java
public boolean equals(Object obj)
```

To **override** this method, a subclass must provide a method with the corresponding signature: the name `equals` and **parameter `Object`**. A parameter of `MyType` is not equivalent to `Object`, even though `MyType` is a subclass of `Object`.

```java
class MyType {
    public boolean equals(MyType other) { // overload of equals(Object)
        return true;
    }

    @Override
    public boolean equals(Object obj) {   // override of Object.equals(Object)
        return super.equals(obj);
    }
}
```

This is only a snippet illustrating signatures; returning `true` unconditionally in `equals(MyType)` is not a proper equality implementation for an application.

| Declaration | Relation to `Object.equals(Object)` | Why? |
| --- | --- | --- |
| `boolean equals(Object obj)` | **Override** | Keeps the exact name and parameter type of the original method |
| `boolean equals(MyType other)` | **Overload** | Same name but different parameter type |
| `boolean equals(String text)` | **Overload** | Parameter type is also different |
| `boolean equals(Object a, Object b)` | **Overload** | Different number of parameters |
| `boolean equals(Object obj, int mode)` | **Overload** | Different parameter list |

The return type does not turn `equals(MyType)` into an override. Specifically, when overriding `Object.equals(Object)`, the return type must be compatible with `boolean` — in practice, `boolean`. Similarly, renaming the parameter from `obj` to `other` does not change the signature.

**Note on scope:** If a superclass or interface you defined yourself also declares `equals(MyType)`, then `equals(MyType)` in the subclass can override or implement *that specific method*. However, it still **does not** override `Object.equals(Object)`.

## 2. Why Does Java Call Two Different Versions?

Java selects a method in two steps that must be distinguished:

1. **Overload resolution (at compile time):** Java looks at the static type of the variable, the static types of the arguments, and the applicable methods to choose which signature will be called.
2. **Dynamic dispatch (at runtime):** After the signature has been chosen, if the instance method is overridden, Java selects the appropriate implementation based on the actual runtime type of the receiving object.

Crucially, dynamic dispatch **does not automatically switch** from the `equals(Object)` signature to an `equals(MyType)` overload just because the passed-in object happens to be a `MyType`.

Suppose `a` has static type `MyType`:

```java
MyType b = new MyType();
Object bAsObject = b;

a.equals(b);          // May select equals(MyType)
a.equals(bAsObject);  // Selects equals(Object)
((Object) a).equals(b); // Selects equals(Object)
```

The three expressions above use the same actual object, but the **types at the call site** differ. When `MyType` has both signatures, the first call prefers the overload accepting `MyType` because it is more specific; the remaining two calls use the `equals(Object)` signature.

## 3. Broken Example: Implementing Only `equals(MyType)`

Create the file `BadEqualsDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class BadEqualsDemo {
    static final class Item {
        private final int id;

        Item(int id) {
            this.id = id;
        }

        // This is an overload; it does not override Object.equals(Object).
        public boolean equals(Item other) {
            return other != null && id == other.id;
        }
    }

    public static void main(String[] args) {
        Item a = new Item(7);
        Item b = new Item(7);
        Object bAsObject = b;

        System.out.println(a.equals(b));
        System.out.println(a.equals(bAsObject));
        System.out.println(((Object) a).equals(b));

        Set<Item> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        System.out.println(unique.size());
    }
}
```

Run with JDK 17 or newer:

```bash
javac BadEqualsDemo.java
java BadEqualsDemo
```

Output:

```text
true
false
false
2
```

Line-by-line explanation:

- `a.equals(b)`: `b` has static type `Item`, so Java selects the `equals(Item)` overload; the two `id` values are equal, returning `true`.
- `a.equals(bAsObject)`: the argument has static type `Object`, so `equals(Item)` does not apply. Java calls `equals(Object)` inherited from `Object`, which defaults to reference identity comparison; the result is `false`.
- `((Object) a).equals(b)`: the static type of the receiver is `Object`, so only signatures visible through `Object` are considered; because `Item` has not overridden `equals(Object)`, the result is still `false`.
- `HashSet` checks equality through the `equals(Object)` and `hashCode()` contract; the two separate instances are not considered equal, so the size is `2`.

This is an easy bug to miss: manual tests like `a.equals(b)` may “pass”, while `Set`, `Map`, or utilities working through `Object` do not share the same view of equality.

**How to self-check with `@Override`:** If you add `@Override` right before `equals(Item other)` in this example, compilation will fail because that method does not override any method with a matching signature in a supertype or interface. This is why you should use `@Override` whenever you *intend* to override.

## 4. Proper Fix: Override `equals(Object)` and `hashCode()`

Create a standalone file `GoodEqualsDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class GoodEqualsDemo {
    static final class Item {
        private final int id;

        Item(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Item other)) {
                return false;
            }
            return id == other.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Item a = new Item(7);
        Item b = new Item(7);
        Object bAsObject = b;

        System.out.println(a.equals(b));
        System.out.println(a.equals(bAsObject));
        System.out.println(((Object) a).equals(b));

        Set<Item> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        System.out.println(unique.size());
    }
}
```

Compile and run:

```bash
javac GoodEqualsDemo.java
java GoodEqualsDemo
```

Output:

```text
true
true
true
1
```

In the correct version:

- `equals(Object)` is genuinely overridden. Therefore, even when called through an `Object` variable, dynamic dispatch runs `Item.equals(Object)`.
- `this == obj` handles the same-reference case quickly.
- Pattern matching for `instanceof` (`obj instanceof Item other`, available in Java 17) checks the object type, returns `false` for `null` and incompatible types, and creates the cast variable `other`.
- `id == other.id` is the value-based equality rule chosen for the example.
- `hashCode()` uses the same `id` component, ensuring two equal `Item` instances have the same hash code. `HashSet` therefore keeps one element representing the two equal values.

Because `Item` is declared `final` and `id` is immutable, the example avoids complex cases regarding equality between superclass and subclass or hash codes changing after insertion into a `HashSet`. For classes with inheritance, the equality rule must be designed to be symmetric and transitive; one cannot assume every way of using `instanceof` or `getClass()` is always suitable.

## 5. Consequences for Collections, Generics, and APIs

Java APIs often operate through the `Object` type, directly or indirectly:

- **`HashSet` and `HashMap`:** use the `equals(Object)` and `hashCode()` rules to identify equal elements or keys. An `equals(MyType)` overload cannot replace these two contract methods.
- **`Objects.equals(a, b)`:** if `a` is not `null`, the method calls `a.equals(b)` on a reference of type `Object`; hence the call relies on `equals(Object)`.
- **Generic APIs using `Object` or a generic type parameter:** know only the contract of the type declared at the API boundary. An overload taking only a subtype may not be selected.

Generics do not turn `equals(MyType)` into an override. For example, using `Set<Item>` does not mean the Collection will call the `equals(Item)` overload; Java's equality contracts still rely on `Object.equals(Object)`.

**What should you do when you want a domain-specific comparison different from general equality?** Use a distinct name that expresses intent, such as `hasSameId(Item other)`, `matches(Item other)`, or `sameBusinessKey(Item other)`. Do not define an `equals(MyType)` overload with different criteria from `equals(Object)`, because the result when called will change unpredictably depending on the static type of the variable.

## 6. Not Just the Right Signature: Preserving the `equals` Contract

After overriding the right signature, the implementation must also satisfy the `Object.equals` contract:

| Property | Explanation |
| --- | --- |
| Reflexive | `x.equals(x)` must be `true` for non-null `x`. |
| Symmetric | `x.equals(y)` and `y.equals(x)` must return the same result. |
| Transitive | If `x` equals `y` and `y` equals `z`, then `x` must equal `z`. |
| Consistent | When the information used for comparison does not change, repeated calls must return the same result. |
| Non-nullity | `x.equals(null)` must be `false` for non-null `x`. |
| Hash code compatibility | If `x.equals(y)` is `true`, `x.hashCode() == y.hashCode()` must also be `true`. The converse is not required. |

Do not use mutable fields to compute `hashCode` for objects being stored as keys in a hash-based structure; changing the hash code can cause lookups or removals to stop working as expected.

If a type contains only immutable data and uses component-wise equality, a Java `record` can help avoid manual implementation mistakes: `record Item(int id) {}` automatically generates `equals(Object)` and `hashCode()` based on the record components. However, you still need to decide whether field-by-field comparison matches the domain semantics.

## 7. Checklist When Implementing `equals`

1. Use the exact `public boolean equals(Object obj)` and place `@Override` right before the method.
2. Identify which fields truly form value identity; check `null` and the appropriate object type.
3. Ensure reflexivity, symmetry, transitivity, and consistency; pay attention to inheritance and mutable data.
4. Override `hashCode()` based on the same components that define equality.
5. Test `a.equals(b)`, `a.equals((Object) b)`, `Objects.equals(a, b)`, along with behavior in `HashSet` or `HashMap`.
6. If a different kind of comparison is needed, use a clearly named method instead of adding a confusing `equals(MyType)` overload.

**Self-check:** Class `Person` only has `boolean equals(Person p)`. When passing two `Person` objects with the same data into a `HashSet<Person>`, is the collection guaranteed to treat them as one element? **No.** `equals(Person)` is an overload; it does not change the `Object.equals(Object)` contract. To make collections recognize data-based equality, properly override `equals(Object)` and `hashCode()`.

**Key takeaway:** Overriding depends on the signature of the inherited method; `equals(MyType)` has a different parameter from `equals(Object)` and is therefore usually an overload. Java callers and collections rely on the `equals(Object)` contract, so your implementation must override that exact method.