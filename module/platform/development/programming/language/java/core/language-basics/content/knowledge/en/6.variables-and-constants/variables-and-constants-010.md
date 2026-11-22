# `final` References Do Not Change, Yet Objects Can Still Mutate

> **Java core — language-basics / Variables and Constants**  
> **Environment:** Java 17+, using only the standard library.  
> **Objective:** Explain accurately that `final` constrains the **reference variable** rather than automatically locking **object state**; distinguish reassigning a reference from mutating an object, understand aliases, arrays, and collections, and recognize when an object is truly immutable.

## 1. What Does `final` Constrain?

When declaring:

~~~java
final StringBuilder message = new StringBuilder("Java");
message.append(" 17");                   // Valid: modifies the referenced object.
// message = new StringBuilder("Kotlin"); // Compile error: reassigning a final variable.
~~~

There are **two things to distinguish conceptually**:

- **Variable `message`:** a reference variable assigned exactly once. The `final` keyword prevents **reassigning that variable** to a different reference.
- **`StringBuilder` object:** its internal data can be modified by the `append` method. `final` on the `message` variable does **not** make this object immutable.

Comparison table:

| Operation on `final StringBuilder message` | Valid? | Reason |
| --- | --- | --- |
| `message.append("!");` | Yes | Mutates the object's state |
| `message.setLength(0);` | Yes | Modifies the object via a method |
| `message = new StringBuilder();` | No | Reassigns the `final` variable |
| `message = message;` | No | Still a reassignment, even when the RHS is the same reference |
| `System.out.println(message);` | Yes | Reads/references the object without reassigning |

**Takeaway:** `final` on a reference means "**do not change which object this variable points to**", not "**every byte of the object is locked**".

## 2. Runnable Java 17+ Program

Create the file **FinalReferenceDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class FinalReferenceDemo {
    static class Counter {
        private int value;

        Counter(int value) {
            this.value = value;
        }

        void increment() {
            value++;
        }

        int getValue() {
            return value;
        }
    }

    private static void increase(final Counter target) {
        target.increment(); // Allowed: mutates the object.
//      target = new Counter(0); // Invalid: reassigning a final parameter.
    }

    public static void main(String[] args) {
        final Counter counter = new Counter(10);
        Counter alias = counter;

        increase(counter);
        alias.increment();
        System.out.println("counter=" + counter.getValue());
        System.out.println("sameObject=" + (counter == alias));

        final int[] numbers = {1, 2, 3};
        numbers[0] = 9;
        System.out.println("array=" + Arrays.toString(numbers));

        final StringBuilder builder = new StringBuilder("Java");
        builder.append(" 17");
        System.out.println("builder=" + builder);

        final List<String> names = new ArrayList<>();
        names.add("Lan");
        names.add("Mai");
        System.out.println("names=" + names);

        final String language = "java";
        String upper = language.toUpperCase();
        System.out.println("string=" + language + ", upper=" + upper);

        final List<String> unmodifiable = List.of("A", "B");
        try {
            unmodifiable.add("C");
        } catch (UnsupportedOperationException exception) {
            System.out.println("listOfAdd=blocked");
        }

//      counter = new Counter(99); // Invalid: reassigning a final variable.
//      numbers = new int[3];      // Invalid: reassigning a final variable.
//      builder = new StringBuilder(); // Invalid: reassigning a final variable.
    }
}
~~~

Run in the directory containing the file using Bash, PowerShell, or Command Prompt:

~~~bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
~~~

**Exact expected output:**

~~~text
counter=12
sameObject=true
array=[9, 2, 3]
builder=Java 17
names=[Lan, Mai]
string=java, upper=JAVA
listOfAdd=blocked
~~~

**Explanation:**

1. `counter` and `alias` point to **the same object**. `increase(counter)` increments from `10` to `11`; `alias.increment()` increments further to `12`. The `counter` variable was never reassigned.
2. `numbers` always holds the reference to the same array, yet `numbers[0] = 9` is allowed: `final` **does not lock array elements**.
3. `builder.append` and `names.add` mutate mutable objects.
4. `String` is an **immutable** type. `toUpperCase()` returns another string `"JAVA"`, without modifying the string contents `language` points to.
5. `List.of("A", "B")` creates a list that **disallows adding/removing/replacing elements**; calling `add` throws `UnsupportedOperationException`. This is a **property of the list object**, not from the `final` variable.

The invalid reassignment lines are commented out so the main program compiles. You can **uncomment each line individually** to see the compiler error message, then comment it back before running.

## 3. Why Can Aliases Still Modify the Object?

Suppose:

~~~java
final Counter original = new Counter(1);
Counter otherName = original;

otherName.increment(); // original.getValue() also becomes 2.
~~~

Reference relationship diagram:

~~~mermaid
flowchart LR
    A["final original"] --> O["Counter object: value = 2"]
    B["otherName"] --> O
    C["otherName.increment()"] --> O
~~~

`final` only constrains assignments to the name `original`. It **does not revoke** other references and does not forbid the object from being modified through:

- An **alias** (`otherName`).
- A **method** receiving a reference parameter (`increase(final Counter target)`).
- Another **field** or collection holding a reference to the object.

Therefore, simply seeing `final` at a declaration is **not enough** to conclude the object's state will stay unchanged throughout the program's lifetime.

## 4. Distinguishing `final`, Immutable, and Unmodifiable

| Concept | What does it constrain? | Example |
| --- | --- | --- |
| **`final` reference variable** | Cannot reassign the assigned reference | `final StringBuilder b = new StringBuilder();` |
| **Mutable object** | Internal state can change | `b.append("X")`, `list.add("X")`, `array[0] = 2` |
| **Immutable object** | Object API/design disallows changing observable state after creation | `String`, `Integer` |
| **Unmodifiable collection** | Structure/elements cannot be modified via the collection's mutating operations | `List.of("A", "B")` |

A variable **without `final`** can still hold an immutable object:

~~~java
String label = "A";
label = "B"; // Changes reference to another String; does not modify object "A".
~~~

A variable **with `final`** can completely point to a mutable object:

~~~java
final List<String> labels = new ArrayList<>();
labels.add("A"); // Allowed.
~~~

`List.of` prevents modifying the **structure/element list** through its API; however, if the elements inside are mutable objects, **those elements' states can still change**. Do not treat an "unmodifiable list" as a guarantee of *deep immutability* across the entire object graph.

## 5. Applying to Local Variables, Parameters, and Fields

`final` can be applied to **local variables**, **method parameters**, or **fields**:

~~~java
class Basket {
    private final List<String> items = new ArrayList<>();

    void add(String item) {
        items.add(item); // Allowed: modifies the referenced List.
    }

    int size() {
        return items.size();
    }

//  void reset() {
//      items = new ArrayList<>(); // Invalid: reassigning a final field.
//  }
}
~~~

- For **`final` local variables**, Java allows the first assignment following definite assignment rules, but forbids reassignment afterward.
- For **`final` parameters**, code inside the method cannot point the parameter to another object; it can still call methods that mutate the passed-in object.
- For **`final` fields**, they must be validly initialized (e.g., at declaration or in a constructor for instance fields). Once assigned, the field cannot be reassigned in normal Java code.

For **primitives**, `final` prevents changing the variable's value itself because primitives store values rather than references:

~~~java
final int maxItems = 10;
// maxItems++; // Error: attempting to modify a final variable.
~~~

That is why `final int` often looks like a constant, whereas `final SomeMutableObject` does **not** promise the object is constant.

## 6. Common Pitfalls and How to Address Them

| Misconception / symptom | Fact |
| --- | --- |
| "`final` makes an `ArrayList` immutable." | False. `final` forbids reassigning the variable; `add` still modifies the mutable list. |
| "`final int[] a` cannot change `a[0]`." | False. Array elements can still be modified. |
| "`final String s` then calling `toUpperCase()` modifies `s`." | False. `String` is immutable; the method returns another `String` or appropriate result without modifying `s`. |
| "Assigning `x = x` does not count as reassignment." | False when `x` is an already assigned `final` variable. |
| "Changing the object through an alias is blocked by `final`." | False. Aliases can mutate object state without reassigning the `final` variable. |
| "`List.of(...)` is unmodifiable because of the `final` keyword." | False. The List object does not support modification operations; even if the variable is not `final`, `add` calls are still blocked. |
| "`final` guarantees thread safety." | False. Mutable objects can still be accessed/modified concurrently; proper synchronization or immutability design is needed. |

To protect data from unwanted changes, consider **the object type and how references are shared**, not just adding `final`:

- Choose **immutable types** where appropriate, such as `String` and value types designed to be immutable.
- Avoid exposing mutable objects directly; use **defensive copies** when data isolation is needed.
- For collections, consider APIs creating unmodifiable copies like `List.copyOf` per your data contract; note that this does not mean deep copying every element.
- For multithreaded access, control synchronization/shared state; `final` alone is not a *lock*.

## 7. Self-Check Exercises

**Exercise 1.** Given `final int[] a = {1, 2};`. Does `a[1] = 5;` compile? What about `a = new int[]{3, 4};`? Explain what changes.

**Exercise 2.** Use two variables referencing the same `StringBuilder`, where the first is `final`. Call `append` via the second variable and print the first: predict the output.

**Exercise 3.** Given `final List<String> a = new ArrayList<>();`. Is `a.add("x")` valid? Change creation to `List.of("x")` and try `add("y")`; identify which step is a compile error and which is a runtime exception.

**Exercise 4.** Write `final String s = "Java";` and call `s.concat(" 17");`. Does string `s` change? How can you use the concatenated result without reassigning `s`?

**Exercise 5.** In `FinalReferenceDemo`, set `Counter alias = counter;` and call `alias.increment()` twice; check the value printed from `counter`. Did the `final` variable change or did the object change?

### Conclusion

**`final` on a reference variable prevents reassigning the variable, without freezing the object.** The object can still change through the same variable, a method receiving the reference, or an alias if it is mutable itself. Immutability is **a property of the object/API design**; thread safety and preventing mutation through aliases are separate requirements that must be addressed with proper design.