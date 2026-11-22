# Why the Part After `@` Must Not Be Understood as a Memory Address

## 1. Common Observation When Printing an Object

When printing a Java object that has not defined its own string representation, we often see a form like:

```text
com.example.Person@5acf9800
```

Many people look at the `5acf9800` part after the `@` sign and call it the object's "memory address". That conclusion **is not guaranteed by the Java contract and is therefore incorrect**. In the default representation from `java.lang.Object.toString()`, the part after `@` is the object's **`hashCode()` value, formatted as a hexadecimal (hex) string**.

Important consequences:

- You cannot deduce an object's location in RAM from the `ClassName@hex` string.
- Two objects with **different references** can still print the **same** suffix after `@`.
- The hash value is not a unique ID or a stable address to store across program runs.
- If a class overrides `hashCode()`, the suffix of `Object.toString()` may reflect a developer-defined hash rule completely unrelated to memory allocation.
- If a class overrides `toString()`, the printed string does **not even need to contain the `@` character**.

This lesson focuses on **how to interpret the default `toString()` string**, especially the origin and limits of meaning of the part after `@`.

## 2. The Actual Formula of Object.toString()

According to the contract of `java.lang.Object.toString()`, the default representation is equivalent to:

```java
getClass().getName() + "@" + Integer.toHexString(hashCode())
```

This is an **illustrative expression showing the method's mechanism**, not a standalone Java program. Each component has a clear role:

| Component | Meaning |
| --- | --- |
| `getClass()` | Gets the **actual runtime** class of the object. |
| `getClass().getName()` | Returns the binary class name that Java uses for `Class.getName()`, e.g., `com.example.Person`. |
| `"@"` | Separator character between the class name and the hash suffix. |
| `hashCode()` | Gets the `int` integer returned by the object's `hashCode()` method. |
| `Integer.toHexString(...)` | Converts the bit pattern of the `int` integer into an unsigned hex representation, using characters `0–9` and `a–f`. |

Suppose `hashCode()` returns the decimal number `42`:

```java
System.out.println(Integer.toHexString(42)); // 2a
```

Therefore, an instance of `Person` using `Object.toString()` with `hashCode() == 42` will be displayed with the suffix `@2a`. The number `2a` in base 16 is simply another way of writing `42` in base 10. It contains no required information about a memory region.

We must distinguish a **hash value** from **reference size/location**. `hashCode()` returns a 32-bit `int`; memory addresses in a process can have a completely different representation, size, and management mechanism. That the suffix contains hex characters making it look like an address is merely a similarity in notation.

### Note on Class Names

If the object is an instance of a nested class, `getClass().getName()` may contain the `$` character. If it is a primitive array such as `int[]`, the name from `getClass().getName()` is `[I`, so the default output of the array object has the form `[I@...`. These class-naming rules also say nothing about memory location.

Example:

```java
int[] values = {1, 2, 3};
System.out.println(values.getClass().getName()); // [I
System.out.println(java.util.Arrays.toString(values)); // [1, 2, 3]
```

*These are illustrative statements inside a method.* To inspect array **contents**, use `Arrays.toString` or `Arrays.deepToString` as appropriate, instead of trying to decode the suffix after `@`.

## 3. A Hash Code Is Neither an Address Nor a Unique Identity

`Object.hashCode()` returns an integer serving Java's hashing contract. For the default `Object.hashCode()`, Java describes the intent to produce distinct codes for distinct objects "as much as is reasonably practical", but **does not guarantee that codes are always unique**.

Several points help avoid misconceptions:

1. **There is no memory-address API in `hashCode()`.** The Java specification does not require `Object.hashCode()` to be computed by reading a RAM address.
2. **Hash collisions are valid.** Two different objects can have the same hash without violating the contract.
3. **Hashes do not determine equality in reverse.** If `a.equals(b)` is `true`, they must have equal hashes; however, having the same hash does not prove `equals()` is `true`.
4. **The suffix is not a storage key.** Do not use `@...` as a database ID, session key, cross-process tracking identifier, or secret value.
5. **Values are not guaranteed to repeat across runs.** With default hashes, restarting the program does not mean new objects of the same type will have the old suffix.
6. **The JVM is free to implement the default hash mechanism** as long as it preserves the language/API contract. A particular implementation might partly rely on object-related information, but you must not infer from that that every JVM or every run outputs a memory address.

In particular, the garbage collector can move objects in memory in some JVM configurations. Java still requires an object's `hashCode()` to remain consistent within the same execution while information used in equality does not change. Thus, even in an environment with relocating memory management, the hash string cannot be understood as a snapshot of an address existing at all times.

## 4. Key Experiment: Two Different Objects Both Print @2a

We do not need to inspect memory regions to prove that the part after `@` **is not an address**. We simply create a class that **keeps the default `toString()`** while **overriding `hashCode()`** to return a constant. Then every instance of the class will have the same suffix despite being distinct objects.

Create the file `ToStringAtDemo.java`:

```java
public class ToStringAtDemo {

    static final class FixedHash {
        private final String label;

        FixedHash(String label) {
            this.label = label;
        }

        @Override
        public int hashCode() {
            return 42;
        }
        // Does not override toString() and equals().
    }

    static final class Described {
        private final String label;

        Described(String label) {
            this.label = label;
        }

        @Override
        public int hashCode() {
            return 255;
        }

        @Override
        public String toString() {
            return "Described(label=" + label + ")";
        }
    }

    public static void main(String[] args) {
        FixedHash first = new FixedHash("A");
        FixedHash second = new FixedHash("B");

        System.out.println(first);
        System.out.println(second);
        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.toString().equals(second.toString()));

        System.out.println(first.getClass().getName());
        System.out.println(Integer.toHexString(first.hashCode()));
        System.out.println(first.getClass().getName() + "@"
                + Integer.toHexString(first.hashCode()));

        System.out.println(new Described("third"));
        System.out.println(String.valueOf((Object) null));
    }
}
```

Compile and run with JDK 17 or newer, in the directory containing the file:

```bash
javac ToStringAtDemo.java
java ToStringAtDemo
```

Exact output in the default package as in the code above:

```text
ToStringAtDemo$FixedHash@2a
ToStringAtDemo$FixedHash@2a
false
false
true
ToStringAtDemo$FixedHash
2a
ToStringAtDemo$FixedHash@2a
Described(label=third)
null
```

Step-by-step explanation:

1. `first` and `second` are both `FixedHash`, created by two `new` calls, so `first == second` is `false`.
2. `FixedHash` does not override `equals()`, so the default reference comparison also gives `first.equals(second) == false`.
3. `FixedHash` overrides `hashCode()` to always return `42`; `Integer.toHexString(42)` is `2a`.
4. `FixedHash` does not override `toString()`. Calling `Object.toString()` on **each** instance calls the overridden `hashCode()`. Therefore both objects print the same string `ToStringAtDemo$FixedHash@2a`.
5. Their `toString()` strings are equal (`true`) while **the two objects do not share a reference and are not equal according to `equals()`**. Thus the part after `@` cannot be interpreted as a unique address of each object.
6. `Described` overrides `toString()`, so even though `hashCode() == 255`, the displayed string is just `Described(label=third)`. The `ClassName@hex` formula only applies when the default representation is used.
7. For `null`, `String.valueOf((Object)null)` returns the string `"null"`; there is no actual object on which to call `getClass()` or `hashCode()`.

The name `ToStringAtDemo$FixedHash` has a `$` sign because it is a `static` nested class and `Class.getName()` returns the class's binary name. If the class is placed in another package, the printed class name adds the package prefix, but the logic regarding the `@2a` suffix does not change.

### Subtle Point: Object.toString() Still Calls hashCode() via Dynamic Dispatch

A class may **not** define `toString()` yet **still** define `hashCode()`. When `Object.toString()` makes the `hashCode()` call on the object, Java applies dynamic dispatch to run the version matching the runtime class. Therefore, you should not claim that the suffix after `@` is always an "identity hash" even when `toString()` is still using the default.

In the experiment, the suffix is generated directly from the `FixedHash.hashCode()` method written by the programmer. It is a number decided by the program, not memory information revealed by the JVM.

## 5. Distinguishing hashCode() from System.identityHashCode()

Java also has:

```java
int identityHash = System.identityHashCode(object);
```

*This is an illustrative statement inside a method, where `object` has already been declared.*

`System.identityHashCode(object)` returns a hash code matching how **`Object.hashCode()` defaults** are computed for that object, **even when the class has overridden `hashCode()`**. This is useful when observing by identity in debugging tools. However, **an identity hash is also not a memory address** and **is not guaranteed to be unique**.

| Expression | Value Source | Guaranteed to Be a Memory Address? |
| --- | --- | --- |
| `object.hashCode()` | Actual `hashCode()` method; may be overridden by the class. | No. |
| `System.identityHashCode(object)` | Hash according to `Object`'s default semantics, ignoring `hashCode()` overrides. | No. |
| `Integer.toHexString(object.hashCode())` | Hex representation of the regular hash. | No. |
| Default `Object.toString()` | Class name + `@` + hex of `object.hashCode()`. | No. |
| `object.toString()` if class overrides | String defined by the class itself. | Format cannot be assumed from default Object. |

What happens in the `FixedHash` example?

- `first.hashCode() == 42` is a definite value because the class overrode the method.
- `System.identityHashCode(first)` is provided by the JVM according to identity hash rules and is **not** forced to `42`.
- The actual identity hash number is not guaranteed and may happen to equal or differ from `42`; therefore the lesson does not list an assumed stdout for it.

Even `System.identityHashCode(first) == System.identityHashCode(second)` is not enough to prove two variables point to the same object: two different objects can experience a hash collision. To ask whether they are the exact same instance, use `first == second`. To ask about logical equality according to the class, use `first.equals(second)`.

## 6. Relation to equals() and hashCode(): Three Distinct Concepts

There are three questions to keep separate:

| Question | How to Check | Meaning |
| --- | --- | --- |
| Do two variables point to the same instance? | `a == b` | Reference identity. |
| Are two objects equal in logical value? | `a.equals(b)` | According to the class's contract and implementation. |
| Do two objects have the same hash code? | `a.hashCode() == b.hashCode()` | Compares two `int` values, merely hash-supporting information. |

The Java contract requires: **if two objects are equal by `equals()`, their hashes must be equal**. The converse is not true: two different objects can have the same hash. Therefore, objects printing the same hex suffix does not prove they are equal.

In the `FixedHash` example, all instances have hash `42`, yet the default `equals()` still only recognizes the same reference. This is a very poor-quality hash choice for hash collections if there are many objects, as it causes many collisions, but **it does not violate the `equals()/hashCode()` contract**. We used it intentionally to separate hashes from addresses.

Another mistake: a class overrides `equals()` based on fields but forgets to override `hashCode()` accordingly. Two objects can be equal via `equals()` while having different hashes, violating the contract and causing `HashMap`/`HashSet` lookups to behave incorrectly. Do not use the `@...` suffix to decide equality; design `equals()/hashCode()` for their proper roles.

## 7. Why the Suffix Value Is Unsuitable as a Long-Term Identifier

Suppose an application writes a log:

```text
RequestContext@6d03e736 started
```

Another engineer sees the string `6d03e736` and wants to use it as an ID to link database records or track across multiple restarts. That is unsafe because:

- **No uniqueness guarantee:** a 32-bit hash value can be used by multiple objects.
- **No stability guarantee across processes or different runs:** restarting the JVM does not create an identifier mapping with a preserved contract.
- **Can be overridden:** a class changing how `hashCode()` is computed after a library update will change the meaning of the suffix.
- **Not tied to lifecycle:** there is no promise that the suffix indicates whether the object is still alive, has been collected by GC, or has been relocated in memory.
- **Does not describe content:** readers cannot tell the important fields of a request from `@6d03e736` alone.

If you need to trace a request through logs, generate a managed request ID/correlation ID, such as a per-request UUID, and pass it through processing steps. If you need a durable business ID, use a business key or system-issued identifier. If you only need to read object state for debugging, override `toString()` with useful fields and exclude sensitive information.

**Security note:** Avoid putting passwords, tokens, access keys, or sensitive personal data into `toString()`. Many frameworks or loggers may call `toString()` when presenting an object; a readable string is not worth leaking data.

## 8. If a Class Overrides toString(), What About the `@` Sign?

The `ClassName@hex` formula is the **default representation of `Object.toString()`**, not a mandatory structure for all Java strings.

A class can write:

```java
@Override
public String toString() {
    return "User{id='" + id + "', status='" + status + "'}";
}
```

*This is only the method body inside a class with fields `id` and `status`; not a standalone program.*

Then the printed string is decided by the overriding method. It may have no `@` sign, or have `@` as part of an ordinary value, such as an email address `a@example.com`. Therefore, **do not write a parser that guesses addresses or hash codes based on the `@` character in arbitrary `toString()` outputs**.

Even for objects that have not overridden `toString()`, the `@` character only separates the class name and the hash representation; that information usually does not help reconstruct the object or its data content. If a system needs a machine-readable format, use a serializer/DTO with an explicit schema instead of relying on debug strings.

## 9. Common Misconceptions and Corrections

### Misconception 1: "`@` follows the class name so it must be an address"

Fact: `Object.toString()` combines `getClass().getName()`, `@`, and `Integer.toHexString(hashCode())`. Looking like an address is merely hex formatting.

### Misconception 2: "Two different objects always have different suffixes"

Fact: hash collisions are valid. The `FixedHash` example proved two distinct new objects can share `@2a`.

### Misconception 3: "Same suffix means `equals()` is true"

Fact: same hash does not imply `equals()`. On the other hand, two objects that are `equals()` must have the same `hashCode()` by contract.

### Misconception 4: "Using `System.identityHashCode()` will give the real address"

Fact: `identityHashCode` is a hash code following identity semantics, yet the API still does not promise to return a memory address or a never-colliding value.

### Misconception 5: "Changing `toString()` also changes `hashCode()`"

Fact: the two methods have independent responsibilities. Overriding `toString()` changes representation, not how `equals()` or `hashCode()` behaves. Conversely, overriding `hashCode()` can cause the suffix of the **default `Object.toString()`** to change as well.

### Misconception 6: "The hex number indicates object creation order"

Fact: `hashCode()` has no contract to increase monotonically with allocations. Comparing the magnitude of two suffixes does not determine which object was created first.

### Misconception 7: "You can use the `@hex` string as a key for HashMap"

Syntactically any string can be used as a key, but using the default `toString()` as a logical identifier is an unguaranteed design. Choose actual identity/value fields, use immutable key types, and implement `equals()/hashCode()` consistently.

### Misconception 8: "You can look at an `@hex` log and determine which address the object is at"

No. The `@hex` format provides no address lookup or dereferencing API. Actual heap or memory analysis requires appropriate JVM diagnostic tools; even those tools have snapshot- and runtime-dependent address/ID concepts that cannot be inferred from `Object.toString()`.

## 10. Self-Check Questions

**Question 1.** Does `Person@2a` from the default `Object.toString()` mean `Person` is stored at RAM address `0x2a`?  
**Answer:** No. `2a` is the hex representation of the `hashCode()` value, i.e., decimal `42`.

**Question 2.** Can two different new objects have the same `SomeClass@2a` string?  
**Answer:** Yes. If they share the same class name and the same hash, the default `Object.toString()` produces the same string even though the two references differ.

**Question 3.** If only `hashCode()` is overridden to `return 255;` while still using `Object.toString()`, what is the suffix?  
**Answer:** `@ff` because `255` in base 16 is `ff`.

**Question 4.** Does `System.identityHashCode(obj)` guarantee returning a memory address or a unique ID?  
**Answer:** No. It bypasses `hashCode()` overrides to obtain the identity hash, but it is still a hash, not an address API.

**Question 5.** Are two objects with the same hash guaranteed to be equal by `equals()`?  
**Answer:** No. Having the same hash is only a required condition for equal objects; hash collisions between unequal objects are allowed.

**Question 6.** Why is `Arrays.toString(array)` more suitable than `array.toString()` for viewing one-dimensional array contents?  
**Answer:** `array.toString()` uses the default display format like `[I@...`, whereas `Arrays.toString` displays each element.

**Question 7.** If a class overrides `toString()` to `"User(email=a@example.com)"`, does the `@` character still carry a hash meaning?  
**Answer:** No. When the overriding method determines the format itself, `@` can simply be an ordinary text character.

**Question 8.** When needing to attach an ID across multiple requests and multiple JVM restarts, should you store the part after `@`?  
**Answer:** No. Use an identifier with a clear contract, such as a request ID, UUID, or appropriate business key.

**Key takeaway:** With the default `Object.toString()`, the part after `@` is **`Integer.toHexString(hashCode())`**, with absolutely no promise that it represents a RAM address, object creation order, or a unique identifier. To compare objects, use the `equals()/hashCode()` contract; to check for the same instance, use `==`; to inspect data, build a meaningful `toString()` or use appropriate diagnostic tools.