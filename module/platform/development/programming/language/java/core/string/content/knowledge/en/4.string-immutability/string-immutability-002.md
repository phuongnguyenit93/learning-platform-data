# Distinguishing `final` on Variables from Object Immutability in Java

A very common misconception when learning Java is thinking that adding `final` to a variable will make the **object** referenced by that variable immutable. In reality, `final` on a **variable** and *immutability* of an **object** control two different things:

- **`final` on a variable**: once the variable has been assigned a valid value, you cannot reassign that variable. For a reference variable, this fixes the **reference** stored in the variable.
- **Immutable object**: the observable state of the object itself does not change after creation, regardless of how many variables reference it.

Keep this short sentence in mind: **`final` keeps the value of a variable fixed; immutability keeps the state of an object fixed.**

## 1. Two Layers to Distinguish: Variable and Object

Consider the statement:

```java
final StringBuilder builder = new StringBuilder("Java");
```

There are two components:

1. **The reference variable `builder`** holds a reference to a `StringBuilder` object. The `final` keyword forbids assigning a different reference into this variable.
2. **The `StringBuilder` object** exists separately. It is a *mutable* kind of object: methods `append()`, `insert()`, `delete()`, etc. can change its content.

Therefore:

```java
builder.append(" 17"); // Valid: the referenced object is modified.
// builder = new StringBuilder("Kotlin"); // Compile error: cannot reassign a final variable.
```

In contrast:

```java
String language = "Java"; // Not declared final.
language = language.concat(" 17"); // Valid: the variable points to a new result.
```

The `String` object with content `"Java"` remains **immutable**, even though the variable `language` does not have `final` and can be reassigned.

| Case | Can the variable be reassigned? | Can the object's content be modified through its API? |
| --- | --- | --- |
| `int x = 1` | Yes | No object: `int` is a primitive. |
| `final int x = 1` | No | No object: `int` is a primitive. |
| `String s = "A"` | Yes | No, because `String` is immutable. |
| `final String s = "A"` | No | No, because `String` is immutable. |
| `StringBuilder b = new StringBuilder("A")` | Yes | Yes, via `append()`, `setCharAt()`, etc. |
| `final StringBuilder b = new StringBuilder("A")` | No | Yes, same as the case above. |
| `final int[] a = {1, 2}` | Cannot make `a` point to another array | Yes, for example `a[0] = 9`. |

Note carefully: the `=` in `s = "B"` changes **the value of variable `s`**; the call `b.append("B")` changes **the object that `b` is referencing**. Those are two fundamentally different operations.

## 2. `final` on Primitive Types

For `int`, `long`, `double`, `boolean`, `char`, etc., the variable holds the primitive value directly. When declared `final`, the variable cannot receive a new value:

```java
final int maxRetries = 3;
System.out.println(maxRetries); // 3

// maxRetries = 4; // Compile error.
// maxRetries++;    // Compile error: incrementing also requires assigning a new value.
```

A `final` variable can only be **assigned once along each valid execution path**. It can be declared first and assigned later, as long as the compiler can prove the assignment happens exactly once:

```java
final int port;
boolean isProduction = true;

if (isProduction) {
    port = 443;
} else {
    port = 8080;
}

System.out.println(port); // 443
```

This is a snippet placed inside a method; the result depends on `isProduction` being set to `true`. `final` fields in a class also have their own initialization rules: instance fields are typically initialized at declaration or in constructors along every initialization path; `static final` fields are initialized according to static field rules. You should not describe `final` as "always a compile-time constant": only certain primitive/`String` `final` expressions satisfy the *constant variable* conditions of the Java Language Specification.

## 3. `final` on Reference Variables: Target Cannot Change, State Still Can

A `final` reference cannot point to a new object, but the current object can still be modified if its type permits.

### Arrays

```java
final int[] scores = {10, 20};
scores[0] = 99;            // Valid.
System.out.println(scores[0]); // 99

// scores = new int[] {1, 2}; // Compile error: reassigning variable scores.
```

**Java arrays themselves are mutable**: `final` on the variable does not freeze the elements.

### Collections and Custom Mutable Objects

```java
final java.util.List<String> names = new java.util.ArrayList<>();
names.add("An");           // Valid: modifies the state of the ArrayList.
names.add("Binh");
System.out.println(names); // [An, Binh]

// names = new java.util.ArrayList<>(); // Compile error.
```

If two variables point to the same mutable object, a modification through one variable will be observed through the other:

```java
final StringBuilder original = new StringBuilder("A");
StringBuilder alias = original;

alias.append("B");
System.out.println(original); // AB
```

`final` **does not eliminate aliasing** (multiple references to the same object) and does not prevent state changes through an alias.

## 4. Immutable Objects: Reference Can Change, Old Value Cannot Be Modified

`String` is a classic example of a class with an immutability contract. There are no public operations like `append()` or `setCharAt()` that directly change the content of a `String` instance. Calls like `concat()`, `replace()`, or `toUpperCase()` return a new result in terms of **value**; the original string stays intact. Implementations may return the same old instance when the result does not change, so "immutable" does not mean "every operation allocates a new instance."

```java
String title = "Java";
String oldTitle = title;

title = title + " 17";

System.out.println(title);    // Java 17
System.out.println(oldTitle); // Java
```

Here, `title` is reassigned to the result `"Java 17"`, while `oldTitle` still references the `"Java"` object. No operation "modifies the string Java into Java 17."

If `final` is added to `title`:

```java
final String title = "Java";
String another = title.concat(" 17"); // Valid, title is still "Java".
// title = another; // Compile error because title is final.
```

Immutability remains the same; the only new thing is that the variable `title` cannot be reassigned.

## 5. Standalone Runnable Java 17+ Example: Contrasting All Four Scenarios

Save the following code to `FinalVsImmutableDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class FinalVsImmutableDemo {
    public static void main(String[] args) {
        // (1) final + primitive: cannot reassign the variable.
        final int limit = 3;
        System.out.println("limit = " + limit);

        // (2) final + mutable object: cannot reassign the reference,
        // but the object's content can still be changed.
        final StringBuilder buffer = new StringBuilder("Ja");
        buffer.append("va");
        System.out.println("buffer = " + buffer);

        final int[] scores = {1, 2};
        scores[0] = 9;
        System.out.println("scores[0] = " + scores[0]);

        final List<String> names = new ArrayList<>(List.of("An"));
        names.add("Binh");
        System.out.println("names = " + names);

        // (3) NON-final reference + immutable String:
        // the variable changes what it points to, the old string object does not change.
        String first = "Java";
        String oldFirst = first;
        first = first.concat(" 17");
        System.out.println("first = " + first);
        System.out.println("oldFirst = " + oldFirst);

        // (4) final + immutable String: both guarantees coexist.
        final String greeting = "Hi";
        String newGreeting = greeting.concat("!");
        System.out.println("greeting = " + greeting);
        System.out.println("newGreeting = " + newGreeting);
    }
}
```

Compile and run:

```bash
javac FinalVsImmutableDemo.java
java FinalVsImmutableDemo
```

Exact output:

```text
limit = 3
buffer = Java
scores[0] = 9
names = [An, Binh]
first = Java 17
oldFirst = Java
greeting = Hi
newGreeting = Hi!
```

**Explanation:** the lines updating the `StringBuilder`, array, and `ArrayList` change the object's content even though the variables are `final`; `String` concatenation does not change the old instance even though the variable `first` can be reassigned. If you uncomment the reassignments of `final` variables in the earlier examples, the error occurs **at compile time**, not at runtime.

## 6. `final` in Other Positions Does Not Mean Immutable

### `final` Parameters

```java
static void addTag(final StringBuilder target) {
    target.append("-ok"); // Valid: modifies the object.
    // target = new StringBuilder(); // Compile error: reassigning parameter.
}
```

`final` forbids changing **the parameter variable inside the method**. Java still passes **the value of the reference** into the parameter; caller and callee can point to the same mutable object. `final` does not turn the call into a deep copy or block object updates.

### `final` Fields in a Class

```java
class MessageBuffer {
    private final StringBuilder content = new StringBuilder();

    void write(String text) {
        content.append(text); // Valid.
    }

    String read() {
        return content.toString();
    }
}
```

The `content` field cannot be reassigned after initialization, but the state of the `StringBuilder` object still changes. Therefore **"every field is `final`" does not prove the whole class is immutable**.

### `final class`

```java
final class MutableCounter {
    private int value;

    void increment() {
        value++; // Still able to modify state.
    }

    int get() {
        return value;
    }
}
```

`final class` forbids inheritance, not state changes. An immutable design often uses `final class` to prevent subclasses from breaking the contract, but this keyword alone is not enough to achieve immutability. Similarly, `final` on a **method** forbids overriding that method rather than making the method read-only.

### *Effectively Final* Variables

A local variable not written with `final` that is assigned once and never reassigned can be treated by the compiler as *effectively final*, allowing lambdas/inner classes to access it:

```java
String prefix = "Hello, ";
Runnable task = () -> System.out.println(prefix + "Java");
task.run(); // Hello, Java

// prefix = "Hi, "; // If this reassignment is added,
//                   // the lambda above is no longer valid to compile.
```

*Effectively final* is a rule about **the value of a captured variable**, not the immutability of the object the variable references.

## 7. What Does It Take to Create a Truly Immutable Object?

A custom class should only be called immutable when **its observable state after initialization cannot be changed** through any access path the class exposes, even when the object is shared. Common principles:

1. Fully initialize values in the constructor or factory method; do not expose setters that mutate state.
2. Use `private final` for state fields where appropriate: this blocks replacing the field value after initialization, though you must inspect further if the field points to a mutable object.
3. Do not leak references to internal mutable data structures. Make a **defensive copy** when receiving mutable data and when returning mutable data.
4. If a field holds a collection, consider the mutability of **both the collection itself and each element**; copying a list does not automatically make each element immutable.
5. Prevent subclasses from weakening the immutability contract, for example by using `final class` or a controlled inheritance design; do not let `this` escape before initialization completes.

Example designing an immutable snapshot with `String` elements (which are already immutable). Create `ImmutableRosterDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ImmutableRosterDemo {
    static final class Roster {
        private final List<String> members;

        Roster(List<String> source) {
            this.members = List.copyOf(source);
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("An"));
        Roster roster = new Roster(input);

        input.add("Binh"); // Modify source after creating roster.
        System.out.println("input = " + input);
        System.out.println("roster = " + roster.members());

        try {
            roster.members().add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("roster members cannot be modified");
        }

        System.out.println("roster after attempt = " + roster.members());
    }
}
```

Command to run:

```bash
javac ImmutableRosterDemo.java
java ImmutableRosterDemo
```

Output:

```text
input = [An, Binh]
roster = [An]
roster members cannot be modified
roster after attempt = [An]
```

Why does `Roster` achieve immutability in this example?

- The `members` field is `private final`: another list cannot be reassigned after initialization.
- `List.copyOf(source)` creates a list that does not support structural modification, independent of subsequent changes to the source `ArrayList` in the example. It does not allow adding, removing, or replacing elements through the list API.
- Each element is a `String`, which is inherently immutable, so here there is no mutable object inside that could be modified through an alias.
- The `Roster` class is `final` and exposes no setters or writable internal access paths.

**Important limitation:** `List.copyOf` is a **shallow** copy of the elements; it does not deep-copy objects inside the list. For example, if using `List<StringBuilder>`, someone holding an old `StringBuilder` can still call `append()` to change the content of an element referenced by the copied list. Deep immutability requires using immutable elements or making appropriate copies of mutable elements. `List.copyOf` also does not accept `null` elements.

### Distinguishing a Copy from an Unmodifiable View

Two easily confused concepts:

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("B");
System.out.println(view);     // [A, B]
System.out.println(snapshot); // [A]
```

The snippet above is a **fragment** to place inside a method, with imports `java.util.ArrayList`, `java.util.Collections`, and `java.util.List`. `Collections.unmodifiableList(source)` creates a *view* that disallows modification **through the view**, but the `source` can still be modified and the view will reflect the changes. In contrast, `List.copyOf(source)` gives a snapshot list unaffected by subsequent structural changes to `source` in the example above.

When needing to protect an array, copying can be applied in both directions:

```java
final class SafeBytes {
    private final byte[] data;

    SafeBytes(byte[] input) {
        this.data = input.clone(); // Do not keep the caller's mutable array.
    }

    byte[] copyData() {
        return data.clone();       // Do not expose internal array for caller to mutate.
    }
}
```

If you only used `private final byte[] data = input;` and kept the external array directly, the caller could still modify `input[0]` and alter the observable state of `SafeBytes`.

## 8. Impact on Sharing and Multithreading

- **A `final` reference variable does not make an object automatically thread-safe.** For instance, two threads calling `append()` on the same `StringBuilder` still have concurrent access issues; `final StringBuilder shared` does not resolve that race condition.
- **Immutable objects can be conveniently read concurrently by multiple threads.** For example, once the reference is properly published across threads, multiple threads can use an immutable `String` or `Roster` object without needing locks solely to prevent *content* mutation.
- **Reassigning a variable that holds references to immutable objects is still a state change to the variable's holder.** If multiple threads change a `String status` field, you must still consider publication and synchronization mechanisms (`volatile`, `synchronized`, atomic reference, etc.) depending on the operation.
- `final` fields provide certain guarantees under the Java Memory Model when the object is properly constructed, but that does **not** mean every object reachable from a `final` field is also immutable or that all operations using them are thread-safe.

## 9. Misconceptions to Avoid

| Claim | Conclusion |
| --- | --- |
| "An object attached to a `final` variable cannot be modified." | **False.** `final` only forbids reassigning the variable; `ArrayList`, arrays, and `StringBuilder` remain mutable. |
| "If a variable is not `final`, the object is definitely mutable." | **False.** `String s = "A"` is not `final`, yet the `String` object is still immutable. |
| "Every field is `final`, so the entire class is immutable." | **False.** Array elements, collections, and referenced mutable objects can still change. |
| "`final class` means an immutable class." | **False.** It only forbids subclassing; a final class can still provide setters. |
| "`static final List` is an unchangeable list." | **False.** `static` and `final` constrain the field, not `add/remove` on a mutable list. |
| "A `record` is always deeply immutable." | **False.** Record components cannot be reassigned, but components of mutable array/list types can still hold changing state; defensive copying must be designed. |
| "`Collections.unmodifiableList` creates an immutable snapshot." | **False.** It is a view; modifying the backing list shows up in the view. |
| "An immutable object means the variable pointing to it never changes." | **False.** A non-`final` variable can be reassigned to another immutable object. |

## 10. Self-Check

**Question 1.** Which line in the following code causes a compile error?

```java
final StringBuilder b = new StringBuilder("X");
b.append("Y");
// b = new StringBuilder("Z");
```

Answer: the line reassigning `b` (currently commented out) causes a compile error if uncommented; `append("Y")` is valid and the object becomes `"XY"`.

**Question 2.** If `name` is not declared `final`, is the string still immutable?

```java
String name = "An";
String remembered = name;
name = "Binh";
System.out.println(remembered);
```

The output is `An`. Both `String` objects retain their values; only the variable `name` receives a new reference.

**Question 3.** Is `final` required on a variable to use a `String` as a `HashMap` key?

No. The immutability of **the `String` object itself** already keeps the content used for `equals()` and `hashCode()` stable; the variable holding the key reference does not have to be `final`. `final` can make the program more readable when you want to ensure the variable is not reassigned, but that is an additional guarantee at the variable level.

**Key takeaway:** when reading code, always ask two separate questions: **(1) Can this variable be reassigned? (2) Can the object it points to change state?** From `final` on the variable alone, you can answer the first question; to answer the second, you must examine the contract and design of the object's type.

## References

- [Java Language Specification §4.12.4 — `final` Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4) — assignment restrictions and the effectively final concept.
- [Java SE 21 API — `String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html) — immutability and string manipulation APIs.
- [Java SE 21 API — `List.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) — structurally unmodifiable snapshots and shallow element semantics.
- [Java SE 21 API — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) — unmodifiable views and their relation to the backing list.
