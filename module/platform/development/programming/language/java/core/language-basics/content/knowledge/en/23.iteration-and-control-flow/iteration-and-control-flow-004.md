# Mutating a Referenced Object Through a Loop Variable in Java

> **Java core — language-basics / Iteration and Control Flow**  
> **Environment:** JDK 17+, single Java file, standard library only.  
> **Goal:** Distinguish **mutating an object's state** through an enhanced `for` variable from **reassigning the loop variable**; know how to actually replace elements of an array/`List`, understand aliasing, immutable types, and the risks of modifying a collection while iterating.

## 1. Enhanced `for` Receives the Element Value Into a Local Variable

~~~java
for (ElementType element : source) {
    // Use element.
}
~~~

With an array or `Iterable`, each iteration retrieves one element and assigns that value to the local variable `element`. Note the distinction:

- **Primitive types** such as `int`: the variable holds a **copy of the value**. Modifying the variable does not modify the source element.
- **Reference types** such as `StringBuilder`, `Box`: the variable holds a **copy of the reference value** to the same object. Calling methods that mutate the object is observable through the array/list.
- **Reassigning the variable** with `element = otherObject` only changes the **local variable** for that iteration; it does not automatically replace the reference stored in the array/list.

This reflects Java's assignment and reference semantics, not a "pass-by-reference" mechanism for variables. Enhanced `for` **does not provide a slot that can write back into the collection**.

## 2. Mutating Object State: The Original Element Still Points to the Same Object

Example with a `Box` class that has mutable state:

~~~java
static final class Box {
    private int value;

    Box(int value) { this.value = value; }

    void add(int amount) { value += amount; }

    int value() { return value; }

    @Override
    public String toString() { return "Box(" + value + ")"; }
}
~~~

An array holding `Box` references:

~~~java
Box[] boxes = {new Box(1), new Box(2)};

for (Box box : boxes) {
    box.add(10); // Modifies the object that the element points to.
}
// boxes contains Box(11), Box(12).
~~~

On each iteration, `box` and `boxes[index]` **both point to the same object**. Hence, changing a property via `box.add(10)` is seen when accessing the array afterward. The same mechanism applies to `ArrayList<Box>` and other `Iterable<Box>` sources holding the same object references.

The object is mutated, yet **the element slot in the array/list has not been replaced**: there is no `boxes[index] = ...` or `list.set(index, ...)` operation in the example.

## 3. Reassigning the Loop Variable Does Not Replace the Source Element

~~~java
Box[] boxes = {new Box(1), new Box(2)};

for (Box box : boxes) {
    box = new Box(99); // Only assigns to the local variable box.
}
// The array still contains Box(1), Box(2).
~~~

Reassigning may make `box` point to another object **for the rest of that iteration**, but the reference stored in the array does not change. On the next iteration, the loop variable receives the next element from the array.

Even if you combine both operations:

~~~java
for (Box box : boxes) {
    box.add(1);        // Mutates the original Box in the array.
    box = new Box(99); // Changes local variable; array does not receive Box(99).
}
~~~

After this loop, the array elements are `Box(2)` and `Box(3)`, **not** `Box(99)`.

If you declare `for (final Box box : boxes)`, Java forbids reassigning `box`, yet still allows calling `box.add(1)` if the object permits state mutation: `final` protects **the variable's reference value**, without automatically making the object immutable.

## 4. To Replace the Actual Element, Use an Index or `ListIterator.set`

With an **array**, replace the reference using indexed assignment:

~~~java
Box[] boxes = {new Box(1), new Box(2)};

for (int i = 0; i < boxes.length; i++) {
    boxes[i] = new Box(boxes[i].value() * 2);
}
// boxes: Box(2), Box(4).
~~~

With a `List` that supports updates, use `list.set(index, value)` when you have an index. When you want to iterate and replace the element at the current position without managing an index manually, `ListIterator.set(value)` is the right approach:

~~~java
java.util.List<Box> list = new java.util.ArrayList<>();
list.add(new Box(3));
list.add(new Box(4));

java.util.ListIterator<Box> it = list.listIterator();
while (it.hasNext()) {
    Box old = it.next();
    it.set(new Box(old.value() * 2));
}
// list: [Box(6), Box(8)].
~~~

| Operation | Mutates the Referenced Object? | Replaces the Element in the Array/List? |
| --- | --- | --- |
| `box.add(5)` | Yes, if `Box` is mutable | Does not replace the element reference |
| `box = new Box(5)` | Does not modify old object | No |
| `array[i] = new Box(5)` | Does not modify old object | Yes |
| `list.set(i, new Box(5))` | Does not modify old object | Yes, if the list permits it |
| `listIterator.set(new Box(5))` | Does not modify old object | Yes, if the iterator permits it |

`List.of(...)` does not support replacing elements via `set`; you need to use `ArrayList` or a mutable structure. However, an unmodifiable list can still **contain mutable objects**: restricting element replacement and restricting object state mutation are two separate issues.

## 5. Aliasing: Multiple Variables Referencing the Same Object, Yet Replacing an Element Does Not Change Old Aliases

Suppose two variables hold the same object:

~~~java
Box original = new Box(5);
Box alias = original;
alias.add(2);
// original.value() == 7; alias.value() == 7.
~~~

This is **aliasing**: mutating state through one reference is observed through the other reference.

However, if a list contains `original` and we **replace the element** with a new object, `alias` still points to `original`:

~~~java
java.util.List<Box> list =
        new java.util.ArrayList<>(java.util.List.of(original));

list.set(0, new Box(100));
// alias.value() == 7, list.get(0).value() == 100.
// alias == list.get(0) is false.
~~~

Therefore, you must decide whether the business logic intends to **modify a shared object** or **replace an element with a different object**. Mutating an object referenced in many places can unintentionally affect everywhere holding an alias.

## 6. Immutable Objects: Example `String`

`String` is an **immutable** type: it has no methods that change the content of the object itself. Methods like `toUpperCase()` create/return an appropriate string value without modifying the source string.

~~~java
java.util.List<String> names = new java.util.ArrayList<>(
        java.util.List.of("an", "binh"));

for (String name : names) {
    name = name.toUpperCase(java.util.Locale.ROOT);
}
// names is still [an, binh].
~~~

Here, reassigning the variable `name` does not replace the list elements. To transform the source elements themselves:

~~~java
for (int i = 0; i < names.size(); i++) {
    names.set(i, names.get(i).toUpperCase(java.util.Locale.ROOT));
}
// names is [AN, BINH].
~~~

Conversely, `StringBuilder` is mutable, so `builder.append("!")` inside an enhanced `for` mutates the object's content:

~~~java
java.util.List<StringBuilder> builders = new java.util.ArrayList<>();
builders.add(new StringBuilder("A"));

for (StringBuilder builder : builders) {
    builder.append("!");
}
// builders contains a StringBuilder with content "A!".
~~~

**Rule:** "Reference type" does not mean "mutable object". You must check the type's API and the object's immutability.

## 7. Null and Modifying Collection Structure While Iterating

- If an element is `null`, the enhanced `for` variable also receives null. Calling `box.add(1)` when `box == null` will throw `NullPointerException`; you must check beforehand.
- If the **source array or Iterable** is null, the enhanced `for` loop cannot start iterating and will typically throw `NullPointerException`.
- When iterating over an `ArrayList` with enhanced `for`, avoid `list.add(...)` / `list.remove(...)` directly inside the body because that is a **structural modification** outside the iterator, which can cause `ConcurrentModificationException`. Do not rely on fail-fast as a deterministic synchronization mechanism.
- If removal during iteration is needed, use `Iterator.remove()` if the iterator supports it; if replacing the current element is needed, use `ListIterator.set()` if the list/iterator supports it.
- Mutating **internal state of a Box** while iterating over `List<Box>` does not automatically count as modifying the `List`'s structure. However, structures that rely on properties for sorting/hashing may lose consistency if changing properties affects keys after insertion.

Example handling nullable elements:

~~~java
Box[] values = {null, new Box(5)};

for (Box box : values) {
    if (box != null) {
        box.add(1);
    }
}
// values contains null and Box(6).
~~~

## 8. Standalone Java 17+ Program

Create the file **LoopReferenceMutationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;

public final class LoopReferenceMutationDemo {
    static final class Box {
        private int value;

        Box(int value) {
            this.value = value;
        }

        int value() {
            return value;
        }

        void add(int amount) {
            value += amount;
        }

        @Override
        public String toString() {
            return "Box(" + value + ")";
        }
    }

    public static void main(String[] args) {
        Box[] array = {new Box(1), new Box(2)};
        for (Box box : array) {
            box.add(10);
        }
        System.out.println("arrayMutation=" + Arrays.toString(array));

        for (Box box : array) {
            box = new Box(99);
        }
        System.out.println("arrayRebind=" + Arrays.toString(array));

        for (int i = 0; i < array.length; i++) {
            array[i] = new Box(array[i].value() * 2);
        }
        System.out.println("arrayReplace=" + Arrays.toString(array));

        List<Box> list = new ArrayList<>(
                List.of(new Box(3), new Box(4)));
        for (Box box : list) {
            box.add(5);
        }
        System.out.println("listMutation=" + list);

        for (Box box : list) {
            box = new Box(0);
        }
        System.out.println("listRebind=" + list);

        ListIterator<Box> it = list.listIterator();
        while (it.hasNext()) {
            Box old = it.next();
            it.set(new Box(old.value() + 1));
        }
        System.out.println("listReplace=" + list);

        Box alias = list.get(0);
        alias.add(100);
        System.out.println("aliasMutation=" + list);

        list.set(0, new Box(1));
        System.out.println("listAfterSet=" + list);
        System.out.println("aliasOld=" + alias);
        System.out.println("aliasSame=" + (alias == list.get(0)));

        List<String> names = new ArrayList<>(List.of("an", "binh"));
        for (String name : names) {
            name = name.toUpperCase(Locale.ROOT);
        }
        System.out.println("stringsRebind=" + names);

        for (int i = 0; i < names.size(); i++) {
            names.set(i, names.get(i).toUpperCase(Locale.ROOT));
        }
        System.out.println("stringsReplace=" + names);

        List<StringBuilder> builders = new ArrayList<>();
        builders.add(new StringBuilder("A"));
        for (StringBuilder builder : builders) {
            builder.append("!");
        }
        System.out.println("builderMutation=" + builders);

        Box[] nullable = {null, new Box(5)};
        for (Box box : nullable) {
            if (box != null) {
                box.add(1);
            }
        }
        System.out.println("nullable=" + Arrays.toString(nullable));
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, Command Prompt):

~~~bash
javac -encoding UTF-8 LoopReferenceMutationDemo.java
java LoopReferenceMutationDemo
~~~

**Exact expected stdout:**

~~~text
arrayMutation=[Box(11), Box(12)]
arrayRebind=[Box(11), Box(12)]
arrayReplace=[Box(22), Box(24)]
listMutation=[Box(8), Box(9)]
listRebind=[Box(8), Box(9)]
listReplace=[Box(9), Box(10)]
aliasMutation=[Box(109), Box(10)]
listAfterSet=[Box(1), Box(10)]
aliasOld=Box(109)
aliasSame=false
stringsRebind=[an, binh]
stringsReplace=[AN, BINH]
builderMutation=[A!]
nullable=[null, Box(6)]
~~~

Compare `arrayMutation`/`arrayRebind` and `listMutation`/`listRebind` to see that **mutating object state ≠ reassigning a variable**. `listAfterSet` differing from `aliasOld` proves that replacing an element does not automatically switch all existing references to the new object.

## 9. Common Mistakes and Exercises

| Mistake | Fix |
| --- | --- |
| Assuming `box = new Box(...)` in for-each replaces the array/list element | Use `array[i] = ...` or `list.set(i, ...)` |
| Assuming `box.add(1)` only modifies a copy of the object | Distinguish a **reference** copy from the shared original object |
| Calling `String.toUpperCase()` and discarding the result | Assign the result to the element by index if you want to update list contents |
| Thinking `final Box box` makes `Box` immutable | `final` only prevents reassigning the reference variable |
| Calling methods on a null element | Guard with `if (box != null)` |
| Removing/adding directly to an `ArrayList` inside enhanced for | Use an iterator that supports removal, or change the processing approach |
| Modifying elements of `List.of(...)` with `set` | Use a mutable list such as `ArrayList` |

**Exercise 1.** Given `Box[] array = {new Box(2), new Box(4)}`. Predict the result if each iteration sequentially executes `box.add(3)` and `box = new Box(0)`. Explain each operation separately.

**Exercise 2.** Use an indexed `for` loop to replace every element of the array with `new Box(old.value() * 2)`. Compare this with mutating the existing objects via `add`.

**Exercise 3.** Write an `ArrayList<String>` containing two lowercase strings, convert them to uppercase using `set`, and verify why reassigning the variable in for-each is not enough.

**Exercise 4.** Keep an alias to the first element of a `List<Box>`, then replace the element with `set(0, new Box(...))`. Do the old alias and the new element still refer to the same object?

**Exercise 5.** Write code to process a `List<Box>` containing a null element; add a guard to avoid `NullPointerException` when mutating properties.

### Key Takeaways

**Enhanced for only places the element value into a local variable.** For reference types, that value points to the same object: **calling mutable methods** can change the shared object's state, whereas **reassigning the loop variable** does not replace the original element. To replace elements, use an index, `List.set`, or `ListIterator.set`; remember to distinguish mutable/immutable types and keep in mind aliasing, null, as well as the limits of modifying a collection while iterating.
