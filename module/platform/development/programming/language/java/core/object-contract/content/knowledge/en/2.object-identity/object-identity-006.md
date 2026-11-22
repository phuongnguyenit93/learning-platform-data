# `System.identityHashCode()` Bypasses an Overridden `hashCode()`

## 1. Nature of the Identity Hash Code

`System.identityHashCode(Object x)` returns the **identity hash code**: the hash code that the default `Object.hashCode()` implementation would return for that exact object, **regardless of whether the class has overridden `hashCode()` or not**.

Distinguish the following operations:

- `x.hashCode()` is a polymorphic call: it executes the overridden `hashCode()` if `x`'s class redefines the method.
- `System.identityHashCode(x)` is a `static` method on `System`; it **bypasses** any overridden `hashCode()`.
- `x == y` checks whether two reference variables point to **the same object**.
- `x.equals(y)` checks equality according to the `equals()` definition, typically based on data or state.
- `System.identityHashCode(null)` is defined to return `0`.

Identity differs from value equality: two objects with the same data can have `equals() == true`, while `==` remains `false` if they were created separately. An identity hash code is a marker for reference-based handling, **not a unique identifier**.

## 2. Comparing Related Expressions

| Expression | Mechanism | Calls Overridden `hashCode()`? |
| --- | --- | --- |
| `x.hashCode()` | Calls the class's method polymorphically | **Yes**, if the class overrides it |
| `System.identityHashCode(x)` | Retrieves the default identity-based hash code | **No** |
| `Objects.hashCode(x)` | `0` if `x == null`; otherwise calls `x.hashCode()` | **Yes**, if the class overrides it |
| `x == y` | Compares two references | Does not use hash codes |
| `x.equals(y)` | Compares according to the class's rules | Does not inherently use hash codes |

If a class **does not override** `hashCode()`, `x.hashCode()` uses `Object`'s default and obtains the same value as `System.identityHashCode(x)`. If a class **has overridden** it, the two values may differ, though they could also match by coincidence. Matching numbers do not mean `identityHashCode` called the overridden method.

## 3. Standalone Java 17+ Example

The program below uses a counter inside `hashCode()` to observe whether the overridden method is invoked. This is only a demonstration tool for this lesson; in real applications, avoid giving `hashCode()` side effects.

Save to the file `IdentityHashDemo.java`:

~~~java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityHashDemo {
    static final class Key {
        private final int id;
        private int hashCodeCalls;

        Key(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Key key && id == key.id);
        }

        @Override
        public int hashCode() {
            hashCodeCalls++;
            return 42; // Intentionally returns a constant for illustration.
        }
    }

    public static void main(String[] args) {
        Key first = new Key(10);
        Key alias = first;
        Key second = new Key(10);

        System.out.println("first.equals(second) = "
                + first.equals(second));
        System.out.println("first == second = " + (first == second));

        int firstIdentityHash = System.identityHashCode(first);
        System.out.println("calls after identityHashCode = "
                + first.hashCodeCalls);

        System.out.println("first.hashCode() = " + first.hashCode());
        System.out.println("calls after hashCode = "
                + first.hashCodeCalls);

        System.out.println("alias has same identity hash = "
                + (firstIdentityHash == System.identityHashCode(alias)));
        System.out.println("identityHashCode(null) = "
                + System.identityHashCode(null));

        Map<Key, String> byValue = new HashMap<>();
        byValue.put(first, "first");
        byValue.put(second, "second");

        Map<Key, String> byIdentity = new IdentityHashMap<>();
        byIdentity.put(first, "first");
        byIdentity.put(second, "second");

        System.out.println("HashMap size = " + byValue.size());
        System.out.println("IdentityHashMap size = "
                + byIdentity.size());
    }
}
~~~

Compile and run from the directory containing the file using JDK 17 or higher:

~~~bash
javac IdentityHashDemo.java
java IdentityHashDemo
~~~

Deterministic output:

~~~text
first.equals(second) = true
first == second = false
calls after identityHashCode = 0
first.hashCode() = 42
calls after hashCode = 1
alias has same identity hash = true
identityHashCode(null) = 0
HashMap size = 1
IdentityHashMap size = 2
~~~

**Part-by-part explanation:**

1. Two `new Key(10)` calls create two different objects. Because `equals()` compares `id`, `first.equals(second)` is `true` while `first == second` is `false`.
2. `System.identityHashCode(first)` does not increment `hashCodeCalls`: the counter stays `0`, proving the overridden `hashCode()` was not invoked.
3. After the direct call `first.hashCode()`, the counter increments to `1`, and the overridden method's value is `42`.
4. `alias` is simply another reference to `first` itself; the same object must receive the same identity hash code within a single run.
5. `HashMap` relies on regular `equals()` and `hashCode()`, so it treats `first` and `second` as one logical key: size is `1`.
6. `IdentityHashMap` compares keys using `==` and uses identity-based hashing, so it retains **two keys**: size is `2`. This remains true even if the two keys' identity hash codes happen to collide.

The program intentionally avoids directly printing the numbers `System.identityHashCode(first)` and `System.identityHashCode(second)`, because they depend on the JVM and have no fixed numeric output to memorize.

## 4. Relationship to the `equals()`/`hashCode()` Contract

The `Object.hashCode()` contract specifies: when two objects `a` and `b` are equal according to `a.equals(b)`, `a.hashCode()` and `b.hashCode()` **must be equal**. The converse is not true: two objects with the same hash code can still be unequal. Hash values are expected to remain stable within a single run as long as the information used by `equals()` does not change.

The rule “`equals()` equal ⇒ `hashCode()` equal” applies to `hashCode()` serving value equality; it **is not imposed** on `System.identityHashCode()` of two separate objects. Two objects with `equals() == true` can receive different identity hash codes; they can also collide and be equal.

If a class overrides `equals()` to compare by value, it must override `hashCode()` compatibly when using the class as a `HashMap` key or `HashSet` element. Do not use `System.identityHashCode(this)` to implement `hashCode()` for a type with value-equality semantics: objects equal by `equals()` could then return different hash codes, breaking the contract.

## 5. Appropriate Use Cases

**Debugging object identity.** When `hashCode()` or `toString()` has been overridden to display business data, logging the identity hash code can help observe a specific object instance:

~~~java
static String debugTag(Object obj) {
    if (obj == null) {
        return "null";
    }
    return obj.getClass().getName() + "@"
            + Integer.toHexString(System.identityHashCode(obj));
}
~~~

This is an **illustrative snippet**; place it inside an appropriate class if you want to use it. The `ClassName@hex` form is useful for logs, but is not guaranteed unique: two objects can share a hash code. Nor does it provide a memory location.

**Reference-based lookup structures.** `IdentityHashMap` fits problems that must distinguish individual instances, such as tracking visited objects in graphs with reference cycles or managing state tied to an exact object. `HashMap` is more appropriate when keys represent the same business value.

**True identity comparison.** When you need the exact answer to “is it the same object?”, use `==` on two references; when using an identity-based collection, rely on `IdentityHashMap` semantics. Do not infer identity by comparing two `identityHashCode` numbers.

## 6. Limitations and Common Mistakes

- **Not a memory address.** The API only returns an identity-based `int`. There is no guarantee it is a pointer, heap address, or physical location of the object.
- **Not guaranteed unique.** Two different objects can produce the same `identityHashCode` integer (*hash collision*). Comparing hash codes for equality cannot replace `==`.
- **Not a persistent ID across runs.** Do not store the identity hash code as a database key, user ID, UUID, or cross-JVM identifier; values are not guaranteed stable across processes or restarts.
- **Do not confuse with `Objects.hashCode(x)`.** `Objects.hashCode(x)` calls `x.hashCode()` when `x` is non-`null`, meaning it still goes through overrides. Both return `0` for `null`, but the mechanism for non-`null` objects differs.
- **Do not confuse with `Object.toString()`.** `Object.toString()`'s default implementation typically includes the class name and the hex form of the hash code, but `toString()` can also be overridden; to explicitly get the identity hash code, call `System.identityHashCode(x)`.
- **Do not assume “same number ⇒ same object” or “different objects ⇒ different numbers”.** Both inferences are wrong because of hash collisions. When exact identity is required, choose `==`.
- **Do not assume an override must produce a different result from the identity hash.** An overridden `hashCode()` can coincidentally return the exact identity hash code value. Which method is invoked is not determined by comparing two numbers.
- **Do not copy the counter from the example into real applications.** The counter is only to show execution flow; production `hashCode()` should avoid side effects and remain consistent with `equals()`.

## 7. Self-Check Questions

**1.** A class overrides `hashCode()` to always return `7`. Must `System.identityHashCode(x)` equal `7`?

No. It bypasses the override; the result could coincidentally equal `7`, but there is no such requirement.

**2.** Does `a.equals(b) == true` require `System.identityHashCode(a) == System.identityHashCode(b)`?

No. The rule that equal objects must have the same hash code applies to regular `hashCode()`; `identityHashCode` follows each instance's individual identity.

**3.** If two objects have equal `System.identityHashCode`, must `a == b` be `true`?

No. Identity hash codes can collide. Use `==`.

**4.** Which option is suitable when you need to track each individual object separately, even when their `equals()` returns true?

`IdentityHashMap` is the specialized choice for keys compared by reference; `HashMap` serves value-equality semantics.

**Remember:** `System.identityHashCode(x)` always bypasses an overridden `hashCode()` to retrieve the default identity-based hash code; **exact identity is checked with `==`, not by comparing hash codes**.