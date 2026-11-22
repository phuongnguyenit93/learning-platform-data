# The Loop Variable Is a Copy of the Element Value — Java 17+

In **enhanced `for`** (also called *for-each*), the loop variable receives **the value of each element**, rather than a storage slot that can be assigned to replace the element in the array or list. Because Java passes and assigns **by value**, **reassigning the loop variable** does not modify the original element.

~~~java
int[] numbers = {1, 2, 3};

for (int number : numbers) {
    number *= 10;
}
// numbers is still {1, 2, 3}.
~~~

With **primitive types**, the variable receives a copy of the number. With **reference types**, the variable receives **a copy of the reference**: it can point to the *same object*, but the variable itself is not the element slot inside the collection. This distinction determines which changes are visible externally.

## 1. How Does Enhanced `for` Read Elements?

~~~java
int[] a = {10, 20};
for (int value : a) {
    System.out.println(value);
}
~~~

In terms of what happens to the element variable, you can think of it roughly as:

~~~java
for (int i = 0; i < a.length; i++) {
    int value = a[i]; // Receives a copy of the element value.
    System.out.println(value);
}
~~~

For an `Iterable` like `List`, enhanced `for` uses an `Iterator` to fetch each value, rather than providing a variable directly representing a storage slot. Whether values are retrieved from an array or an iterator, **reassigning the element variable does not write back to the source**.

| Element Type | What Does the Loop Variable Hold? | Does Reassigning the Variable Change the Original Element? |
| --- | --- | --- |
| `int`, `double`, `boolean`... | Copy of the primitive value | **No** |
| `String`, `Integer` | Copy of reference to an immutable object | **No** |
| Mutable object, such as `Box` | Copy of reference to the same object | **No**, but the object's state can be mutated |
| Subarray `int[]` of `int[][]` | Copy of reference to the subarray | **No**, but elements inside the subarray can be modified |

The word "copy" here means **copying the variable's value** (for objects, the reference address according to the semantic model), **not** automatically creating a *deep copy* of the object.

## 2. Standalone Java 17+ Program, Run via CLI

Create a UTF-8 file named **`EnhancedForCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class EnhancedForCopyDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return Integer.toString(value);
        }
    }

    public static void main(String[] args) {
        System.out.println("== primitive ==");
        int[] numbers = {1, 2, 3};

        for (int value : numbers) {
            value *= 10;
        }
        System.out.println("afterForEach=" + Arrays.toString(numbers));

        for (int i = 0; i < numbers.length; i++) {
            numbers[i] *= 10;
        }
        System.out.println("afterIndexed=" + Arrays.toString(numbers));

        System.out.println("== immutable references ==");
        String[] words = {"cat", "dog"};
        for (String word : words) {
            word = word.toUpperCase(Locale.ROOT);
        }
        System.out.println("afterRebind=" + Arrays.toString(words));

        for (int i = 0; i < words.length; i++) {
            words[i] = words[i].toUpperCase(Locale.ROOT);
        }
        System.out.println("afterReplace=" + Arrays.toString(words));

        System.out.println("== mutable objects ==");
        Box[] boxes = {new Box(1), new Box(2)};
        for (Box box : boxes) {
            box.value += 5;
        }
        System.out.println("afterMutation=" + Arrays.toString(boxes));

        for (Box box : boxes) {
            box = new Box(999);
        }
        System.out.println("afterObjectRebind=" + Arrays.toString(boxes));

        for (int i = 0; i < boxes.length; i++) {
            boxes[i] = new Box(i + 10);
        }
        System.out.println("afterObjectReplace=" + Arrays.toString(boxes));

        System.out.println("== list of wrappers ==");
        List<Integer> ids = new ArrayList<>(List.of(1, 2, 3));
        for (Integer id : ids) {
            id = id + 10;
        }
        System.out.println("listRebind=" + ids);
        ids.replaceAll(n -> n + 10);
        System.out.println("listReplaceAll=" + ids);

        System.out.println("== nested arrays ==");
        int[][] grid = {{1, 2}, {3, 4}};
        for (int[] row : grid) {
            row[0] *= 10;
        }
        System.out.println("gridMutation=" + Arrays.deepToString(grid));

        for (int[] row : grid) {
            row = new int[] {0, 0};
        }
        System.out.println("gridRebind=" + Arrays.deepToString(grid));

        for (int i = 0; i < grid.length; i++) {
            grid[i] = new int[] {-1};
        }
        System.out.println("gridReplace=" + Arrays.deepToString(grid));
        System.out.println("done");
    }
}
~~~

Using **JDK 17 or higher**, open PowerShell or Bash in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 EnhancedForCopyDemo.java
java EnhancedForCopyDemo
~~~

**Exact expected stdout** of the `java EnhancedForCopyDemo` command alone:

~~~text
== primitive ==
afterForEach=[1, 2, 3]
afterIndexed=[10, 20, 30]
== immutable references ==
afterRebind=[cat, dog]
afterReplace=[CAT, DOG]
== mutable objects ==
afterMutation=[6, 7]
afterObjectRebind=[6, 7]
afterObjectReplace=[10, 11]
== list of wrappers ==
listRebind=[1, 2, 3]
listReplaceAll=[11, 12, 13]
== nested arrays ==
gridMutation=[[10, 2], [30, 4]]
gridRebind=[[10, 2], [30, 4]]
gridReplace=[[-1], [-1]]
done
~~~

`java -version` and `javac -version` have output depending on the installed JDK and are not part of the fixed stdout. The program uses only standard Java and requires no external libraries.

## 3. With Primitive Types: Only Modifies the Local Variable

~~~java
int[] scores = {10, 20};
for (int score : scores) {
    score += 5;
}
// scores is still {10, 20}.
~~~

On each iteration, `score` receives **an integer copy**. The statement `score += 5` only updates the local variable during that iteration. If you want to increment the array elements directly:

~~~java
for (int i = 0; i < scores.length; i++) {
    scores[i] += 5;
}
// scores becomes {15, 25}.
~~~

This is the difference between **modifying the loop variable** and **modifying an array slot by index**. Enhanced `for` is particularly well suited for tasks like **reading, summing, printing, or checking** each element.

## 4. With References: Reassigning Differs from Mutating Object State

Consider a mutable class:

~~~java
class Box {
    int value;
    Box(int value) { this.value = value; }
}
~~~

If an array holds `Box` references:

~~~java
Box[] boxes = {new Box(1), new Box(2)};

for (Box box : boxes) {
    box.value += 5; // Modifies the state of the referenced object.
}
// boxes[0].value == 6; boxes[1].value == 7.
~~~

The variable `box` is a **copy of the reference**, yet it still points to **the same `Box` object** held by the array. Therefore, `box.value += 5` mutates the object and is observable through the array.

Conversely:

~~~java
for (Box box : boxes) {
    box = new Box(999); // Only changes the box variable in this iteration.
}
// The array still holds the two original Box objects.
~~~

`box = ...` cannot change `boxes[0]` or `boxes[1]`: the assignment only changes the reference stored in the local variable `box`. To **replace the object at an array position**, use `boxes[i] = new Box(...)` with an index.

| Operation | Changes Array/List Storage Slot? | Can Mutate Original Object State? |
| --- | --- | --- |
| `box = anotherBox;` | No | No, only changes the local variable |
| `box.value = 7;` | No | Yes |
| `boxes[i] = anotherBox;` | Yes | Does not automatically mutate the old object |
| `list.set(i, anotherBox);` | Yes | Does not automatically mutate the old object |

**Note:** Not all references point to objects that allow modification. `String` and wrappers like `Integer` are immutable; expressions that produce a "new value" usually only create/return another object and must then be **assigned back to the original element** if you want to store it.

## 5. `List` and Multidimensional Arrays

Enhanced `for` can iterate over **arrays** and **`Iterable`** objects like `List`:

~~~java
List<Integer> ids = new ArrayList<>(List.of(1, 2));

for (Integer id : ids) {
    id++; // Unboxes, increments, then boxes back into the variable id.
}
// ids is still [1, 2].

ids.replaceAll(n -> n + 1);
// ids becomes [2, 3].
~~~

For lists that allow element replacement, you can use `List.set(index, value)` or `replaceAll` depending on your intent. **Do not remove/add elements directly to an `ArrayList` via `list.add/remove` while iterating over that same list with enhanced `for`**: the fail-fast iterator may throw `ConcurrentModificationException`. When conditional removal is needed safely, use `removeIf` or an `Iterator` with `remove()` following its contract.

A two-dimensional array is also an **array containing references to subarrays**:

~~~java
int[][] grid = {{1, 2}, {3, 4}};

for (int[] row : grid) {
    row[0] *= 10; // Modifies an element inside the subarray.
}
// grid = {{10, 2}, {30, 4}}.

for (int[] row : grid) {
    row = new int[] {0, 0}; // Does not change the reference in grid.
}
// grid is still {{10, 2}, {30, 4}}.
~~~

If you want to replace **an entire subarray**, you must update `grid[index]`. Modifying an element of a subarray is completely different from reassigning the variable `row`.

## 6. Notes on Variable Scope, `final`, and `null`

- The variable declared in `for (Type item : items)` is a loop-scoped variable; **it cannot be used outside the loop's scope**.
- You can write `for (final Box box : boxes)` to **prevent reassigning the reference variable `box`**. However, `final` **does not make the `Box` object immutable**: `box.value++` may still be valid.
- A reference element can be `null`. In that case, the loop variable receives null; calling `item.method()` will throw `NullPointerException` if unchecked.
- If the array or `Iterable` source itself is null, enhanced `for` cannot iterate and will throw `NullPointerException`.
- If you only need to **read each value** without needing positions, enhanced `for` is usually cleaner than a counting loop. If you need to **overwrite the elements themselves**, use an index or an appropriate update API.

## 7. Common Mistakes

| Misconception | Correct Behavior |
| --- | --- |
| "`for (int x : a) { x++; }` increments each element of `a`." | It only increments the **copy** in variable `x` |
| "The loop variable is a direct alias of the array slot." | The variable only receives a **value** of the element |
| "Copying a reference means the object is deep-copied." | No; two references can point to the same object |
| "`box.value++` also cannot change anything outside." | It can mutate the state of the original object |
| "`box = new Box(...)` replaces the original element." | No; you must overwrite the array or list slot |
| "`final Box box` makes the entire Box immutable." | It only prevents reassigning the variable `box` |
| "Changing `String s` with `s.toUpperCase()` updates the list." | Not unless you assign it back to the element |
| "Enhanced `for` is best for replacing every element in place." | Usually use an index, `set`, or `replaceAll` to replace elements |

## 8. Self-Check Exercises

1. `int[] a = {1,2}; for (int x : a) x += 10;` — does the array change?  
   *Answer:* No, it remains `{1,2}`.
2. `String[] a = {"hi"}; for (String s : a) s = "bye";` — what is the first element?  
   *Answer:* `"hi"`.
3. `Box[] a = {new Box(3)}; for (Box b : a) b.value++;` — what is the value in `a[0]`?  
   *Answer:* 4, because it mutates the same object.
4. If `b.value++` is replaced with `b = new Box(9)`, is the original element replaced?  
   *Answer:* No.
5. With `int[][] grid`, how do `row[0]++` and `row = new int[1]` differ?  
   *Answer:* The former modifies the original subarray; the latter only reassigns the variable `row`.
6. To replace all `Integer` elements in a `List` according to a formula, what do you use?  
   *Hint:* `list.replaceAll(...)` or an indexed loop with `list.set(i, ...)`.

## Checklist

- [ ] Understand that enhanced `for` assigns **the element's value** to the variable on each iteration.
- [ ] Distinguish copying **primitive values** from copying **references**.
- [ ] Know that **reassigning the loop variable does not write back to the collection**.
- [ ] Recognize that **mutating object state** can still be reflected through the original element.
- [ ] Use `array[i] = ...`, `list.set`, or `replaceAll` when you need to replace elements.
- [ ] Know variable scope limits, `final`, and how to handle `null` elements.

**Conclusion:** Enhanced `for` is a good way to express **reading each element**, but the loop variable only receives **a copy of the value**. For objects, that copy is **a reference to the same object**, so modifying properties can affect the original object, whereas **reassigning the reference variable** does not replace the element slot in an array or list.
