# Reassigning a Reference Does Not Change a Shared String

In Java, multiple variables can reference the same `String` object. When **reassigning one variable** to another string, only the reference value stored in that variable changes; the remaining variables still reference the old object. This is a consequence of Java's reference variable mechanism. With `String`, **immutability** further ensures that string-processing operations do not directly modify the original object's content.

This lesson focuses on distinguishing two frequently confused actions:

- **Reassigning a reference:** `b = "New"`, `b = a + "!"`, or `b = a.replace(...)`; `b` receives a reference computed on the right-hand side. None of those statements automatically reassign `a`.
- **Mutating object state:** a mutable object can be modified through any reference pointing to it. `String` does not support this kind of in-place content modification through its standard API.

## 1. Two Variables Can Point to the Same `String`

Consider:

```java
String first = "Java";
String second = first;
```

The first line creates a reference variable `first` pointing to the string `"Java"`. The second line **copies the reference value** from `first` into `second`. Thus both variables point to the same `String` object:

```text
first  ────┐
           ├────────> String "Java"
second ────┘
```

At this point, `first == second` returns `true` because the `==` operator compares whether two variables hold the same object reference.

Important: "two variables sharing a string" means **two references are pointing to the same object**. It does not mean the two variables are linked so that any assignment to one automatically updates the other.

## 2. Reassignment Only Changes the Reference of the Assigned Variable

Add one line:

```java
second = "Kotlin";
```

After the assignment, the diagram becomes:

```text
first  ─────────────> String "Java"

second ─────────────> String "Kotlin"
```

No operation modified `String "Java"` into `"Kotlin"`. Variable `first` still holds the old reference. Variable `second` receives a reference to another string; the previous sharing relationship ends.

In Java, a **variable** holds a reference value; the assignment `second = ...` replaces the value stored inside `second` itself. It does not follow the reference to overwrite the content of the object `second` used to point to, nor does it search for other variables to change them.

### Standalone Runnable Java 17+ Example

Create `ReferenceReassignmentDemo.java`:

```java
public class ReferenceReassignmentDemo {
    public static void main(String[] args) {
        String first = "Java";
        String second = first;

        System.out.println("Before:");
        System.out.println("first = " + first);
        System.out.println("second = " + second);
        System.out.println("same object = " + (first == second));

        second = "Kotlin";

        System.out.println("After:");
        System.out.println("first = " + first);
        System.out.println("second = " + second);
        System.out.println("same object = " + (first == second));
    }
}
```

Compile and run:

```bash
javac ReferenceReassignmentDemo.java
java ReferenceReassignmentDemo
```

Output:

```text
Before:
first = Java
second = Java
same object = true
After:
first = Java
second = Kotlin
same object = false
```

In the first half, `second = first` creates an additional reference name to the same `String`. In the second half, `second = "Kotlin"` only changes the variable `second`. `first` still prints `Java`.

## 3. Even When Calling String-Processing Methods, the Source Object Is Not Modified

Some statements look like "modifying a string":

```java
String original = "cat";
String alias = original;

alias = alias.toUpperCase();
alias = alias.replace("A", "O");
```

The result is that `original` remains `"cat"` while `alias` becomes `"COT"`. The reason consists of **two separate steps**:

1. `toUpperCase()` or `replace(...)` returns a `String` value; it does not modify the source `String`'s content.
2. The assignment `alias = ...` replaces the reference in variable `alias`; `original` still keeps the old reference.

Create `ImmutableOperationDemo.java`:

```java
public class ImmutableOperationDemo {
    public static void main(String[] args) {
        String original = "cat";
        String alias = original;

        alias = alias.toUpperCase();
        alias = alias.replace("A", "O");

        System.out.println(original);
        System.out.println(alias);
        System.out.println(original.equals(alias));

        String appended = original.concat("!");
        System.out.println(original);
        System.out.println(appended);
    }
}
```

```bash
javac ImmutableOperationDemo.java
java ImmutableOperationDemo
```

Output:

```text
cat
COT
false
cat
cat!
```

Methods such as `concat`, `replace`, `toUpperCase`, or `substring` provide no in-place content modification for `String`. Some methods may return the same old object if the result does not change; that does not alter string immutability.

Do not confuse "the variable still has the old name" with "the old object was modified." After `alias = alias.toUpperCase()`, it is **the variable `alias`** that was reassigned; the `"cat"` object did not turn into `"CAT"`.

## 4. Immutability and Reference Reassignment Are Two Different Concepts

Keep them separated:

| Action | What changes | What does not change |
| --- | --- | --- |
| `String b = a;` | Variable `b` holds the reference currently in `a` | Content of the `String` object |
| `b = "Other";` | Reference in variable `b` | Reference in `a`, the old object |
| `b = b.concat("!");` | Reference value in `b` after obtaining the string result | Content of the original `String` |
| `a = null;` | Reference in variable `a` becomes `null` | Variable `b` and the object `b` is holding |
| `mutable.append("!");` on `StringBuilder` | Content of the mutable object | No immutability guarantee like `String` |

Worth noting: **reassigning one variable does not automatically change another variable even for references to mutable objects**. The difference with a mutable object is that a method call through one reference can **modify the object itself**, which the remaining references will also observe.

### Counterexample with `StringBuilder`

Create `MutableContrastDemo.java`:

```java
public class MutableContrastDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("Java");
        StringBuilder second = first;

        second.append(" 21");
        System.out.println(first);
        System.out.println(second);
        System.out.println(first == second);

        second = new StringBuilder("Kotlin");
        System.out.println(first);
        System.out.println(second);
        System.out.println(first == second);
    }
}
```

```bash
javac MutableContrastDemo.java
java MutableContrastDemo
```

Output:

```text
Java 21
Java 21
true
Java 21
Kotlin
false
```

`second.append(" 21")` modifies the content of **the same `StringBuilder`** that `first` also points to, so both print `Java 21`. By contrast, `second = new StringBuilder("Kotlin")` only changes `second`'s reference; `first` still points to the old builder. The example shows why you must distinguish **calling an object-mutating method** from **reassigning a variable**.

## 5. What Happens When Passing a `String` into a Method?

Java uses **pass-by-value** for all parameters. For reference types like `String`, the value copied is the *reference to the object*, not the object itself and not the caller's original variable.

Look at `ParameterReassignmentDemo.java`:

```java
public class ParameterReassignmentDemo {
    static void renameLocally(String name) {
        name = "Changed";
        System.out.println("Inside = " + name);
    }

    static String makeUpperCase(String name) {
        return name.toUpperCase();
    }

    public static void main(String[] args) {
        String shared = "Java";
        String alias = shared;

        renameLocally(shared);
        System.out.println("Caller = " + shared);
        System.out.println("Alias = " + alias);

        String updated = makeUpperCase(shared);
        System.out.println("Updated = " + updated);
        System.out.println("Still shared = " + shared);
    }
}
```

```bash
javac ParameterReassignmentDemo.java
java ParameterReassignmentDemo
```

Output:

```text
Inside = Changed
Caller = Java
Alias = Java
Updated = JAVA
Still shared = Java
```

When calling `renameLocally(shared)`, the parameter `name` is **another local variable** receiving a copy of the reference value in `shared`. The statement `name = "Changed"` only reassigns that local variable. The caller's `shared` and `alias` are not changed.

If you want the caller to receive the transformed string value, a clear way is to **return the result and assign it explicitly**:

```java
String shared = "Java";
String result = shared.toUpperCase();
// shared is still "Java", result is "JAVA".
```

Or if you want the `shared` variable itself to change its value:

```java
shared = shared.toUpperCase();
// Variable shared now points to "JAVA".
```

Neither modifies the previous `"Java"` object's content.

## 6. An Easily Misunderstood Exception: Changing an Object Holding a `String` Field

Suppose two variables point to the same instance of a `Message` class that has a `text` field. If one variable updates **the `text` field of the `Message` object**, the other variable will see the new field value when reading it again. This does not contradict `String` immutability at all: **the `Message` object is mutable**, while both the old and new strings remain immutable `String` values.

Create `SharedHolderDemo.java`:

```java
public class SharedHolderDemo {
    static class Message {
        String text;

        Message(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        Message first = new Message("Original");
        Message second = first;
        String snapshot = first.text;

        second.text = "Updated";

        System.out.println(first.text);
        System.out.println(second.text);
        System.out.println(snapshot);
    }
}
```

```bash
javac SharedHolderDemo.java
java SharedHolderDemo
```

Output:

```text
Updated
Updated
Original
```

`first` and `second` point to the same `Message`, so assigning `second.text = "Updated"` makes **the `Message` object's field** point to the new string. `snapshot` is a `String` variable that received a reference to `"Original"` earlier, so it stays unchanged.

Distinguish these two statements:

- "Reassigning a **reference variable** `second`" — does not automatically change variable `first`.
- "Reassigning **a field of a shared object** `second.text`" — changes the state of the `Message` object that `first` also sees.

Similarly, array elements, mutable list elements, or state inside a shared object can be updated. `String` immutability does not make **the object containing it** immutable.

## 7. How Does `final` Relate?

`final String name = "Java";` prevents **reassigning the variable `name`** after the variable has been initialized:

```java
final String name = "Java";
// name = "Kotlin"; // Compile error: cannot reassign a final variable.
```

But `final` is not what makes `String` immutable: even for `String ordinary = "Java";` without `final`, the `String` object is still immutable.

Conversely, a `final` reference to a mutable object can still be used to change **the object's content**:

```java
final StringBuilder builder = new StringBuilder("Java");
builder.append(" 21"); // Valid: does not reassign variable builder.
```

Therefore:

- `final` restricts reassigning **a reference variable/field**.
- `String` is immutable because the **object type's** contract disallows modifying content through its standard API.
- `String` immutability and reference stability via `final` can coexist, but they do not replace each other.

## 8. Notes on `==`, `equals`, and the String Pool

Another question related to reassignment is "do two variables still point to the same object?". You can check with `==` when you genuinely need to inspect **identity**, but for business logic needing text comparison you should use `equals`.

```java
String a = "Java";
String b = a;
b = new String("Java");

System.out.println(a == b);       // false
System.out.println(a.equals(b));   // true
```

Here reassigning `b` causes the two variables to no longer share the same object. Their content is still equal, so `equals` is true. String literals are interned via the *string pool*, whereas calling `new String(...)` creates a `String` object with a different identity. The existence of the pool does not keep two variables bound together when one side changes its reference.

Do not write business logic under the assumption that every `String` with the same text must evaluate to `== true`.

## 9. Common Misconceptions and Mistakes

**Misconception 1 — "Two variables point to the same thing, so changing `b` must change `a`."** False. `b = ...` only writes a new reference value into variable `b`. No assignment-synchronization link exists between two variables.

**Misconception 2 — "`b = b + "!"` modifies the same old object."** False for `String`. Concatenation produces a resulting string value, and then `b` is assigned the reference to the result; the previous string is not modified.

**Misconception 3 — "To avoid sharing references, you must use `new String(a)`."** Reassigning `a` will not affect another variable even when both point to the same `String`. Because `String` is immutable, there is almost never any need to make a `new String(a)` copy to guard against unintended mutation.

**Misconception 4 — "Passing a reference means the method can reassign the caller's variable."** Java uses pass-by-value. A method receives a copy of the reference value; reassigning the parameter only changes the method's parameter variable.

**Misconception 5 — "`final` and immutable are the same thing."** `final` applies to the reassignability of a variable or field; immutability describes the content of an object. A `final StringBuilder` can still call `append`.

**Misconception 6 — "An object containing a `String` is also automatically immutable."** No. A `String` field can be assigned another string value inside a mutable object. References to the containing object itself will observe the new field state.

**Misconception 7 — "Once a variable no longer points to the old object, the old object disappears immediately."** Not necessarily. If another reference such as `first` remains, the object can still be used. Only when no references to the object remain can the JVM collect it when appropriate; collection timing is not guaranteed.

## 10. Self-Practice: Predict Before Running

### Exercise 1: multiple reassignments

```java
String a = "one";
String b = a;
String c = b;

b = "two";
c = c.concat("!");

System.out.println(a);
System.out.println(b);
System.out.println(c);
```

Output:

```text
one
two
one!
```

The three variables initially share the same reference. Afterward, each assignment only changes **the variable on the left-hand side**: `b` switches to `"two"`; `c` receives the concatenated result from `"one"`, becoming `"one!"`. `a` continues to hold `"one"`.

### Exercise 2: does a transformation inside a method take effect?

```java
static void update(String value) {
    value = value.replace("a", "o");
}
```

If the caller has `String text = "Java";` and calls `update(text)`, does the value of `text` change? **No.** Only the parameter variable `value` is reassigned inside the method. To receive the result, change the method to return `String` and let the caller assign the result.

### Exercise 3: shared holder object

```java
class Box {
    String value = "A";
}

Box x = new Box();
Box y = x;
String saved = x.value;

y.value = "B";
```

Afterward `x.value` is `"B"`, `y.value` is `"B"`, while `saved` is still `"A"`. The field of the shared `Box` was updated; the two `String`s themselves were not modified.

## Takeaways to Remember

**Reassigning a reference updates one variable; it does not modify the referenced object, much less update every variable pointing to that object.** With `String`, immutability ensures string-processing methods do not alter the original string's content. Ask specifically "which variable is being reassigned?" and "which object's state is being modified?" when reading or writing code. Those two questions help avoid confusion between references, object identity, and `String` immutability.
