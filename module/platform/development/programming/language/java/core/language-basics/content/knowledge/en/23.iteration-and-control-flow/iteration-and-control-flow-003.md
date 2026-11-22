# Reassigning the Enhanced `for` Variable Does Not Change Array Elements — Java 17+

## 1. Core Rule

With the **enhanced `for`** loop (also known as *for-each*), Java takes each value from the array in turn and **assigns that value to a local loop variable**. Reassigning the loop variable **does not write back** to the array element being iterated over.

~~~java
import java.util.Arrays;

public class FirstExample {
    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};

        for (int number : numbers) {
            number = number * 10;
        }

        System.out.println(Arrays.toString(numbers));
    }
}
~~~

**Exact expected stdout:**

~~~text
[1, 2, 3]
~~~

Although on every iteration `number` receives a value from the array, the expression `number = number * 10` **only changes the local variable `number`**, without modifying `numbers[0]`, `numbers[1]`, or `numbers[2]`.

**To change the array elements themselves**, use the index position to assign:

~~~java
for (int i = 0; i < numbers.length; i++) {
    numbers[i] = numbers[i] * 10;
}
System.out.println(Arrays.toString(numbers));
~~~

**Exact expected stdout (continuing the example above):**

~~~text
[10, 20, 30]
~~~

This is the most important distinction of the lesson: **the variable in `for (T value : array)` is not a "reference slot" that lets you directly replace `array[index]` by assigning to `value`**.

## 2. Why Doesn't Reassigning the Loop Variable Write Back to the Array?

For an **array**, Java processes enhanced for in a way semantically equivalent to using a hidden index:

~~~java
int[] data = {4, 5};

// Equivalent semantics for retrieving values from the array:
for (int index = 0; index < data.length; index++) {
    int element = data[index];
    element = 100; // Only changes element.
}
~~~

On each iteration:

1. Java retrieves the value `data[index]`.
2. Assigns that value to the local variable `element`.
3. Executes the loop body.
4. When moving to the next iteration, retrieves the next element.

**There is no automatic `data[index] = element;` step after the loop body**. Assigning to the variable and assigning to the array element are two separate operations.

An easy way to remember this:

~~~text
data[0] ----value------> element
  4                        4

element = 100;

data[0]                  element
  4                        100
~~~

This diagram applies to **primitive values**. For object arrays, the value copied into the local variable is a **reference value**; this distinction will be addressed further in the following sections.

## 3. Primitive Types: Incrementing, Decrementing, or Reassigning Does Not Modify Elements

~~~java
int[] values = {5, 6, 7};

for (int value : values) {
    value++;
    value *= 2;
    value = -1;
}

System.out.println(Arrays.toString(values));
~~~

**Exact expected stdout:**

~~~text
[5, 6, 7]
~~~

The operations `++`, `--`, `+=`, `*=`, and `=` all modify only the **loop variable**:

- `value++` is not equivalent to `values[i]++`.
- `value += 10` is not equivalent to `values[i] += 10`.
- `value = -1` is not equivalent to `values[i] = -1`.

**The right approach when you need to modify the entire array:**

~~~java
for (int i = 0; i < values.length; i++) {
    values[i]++;
}
System.out.println(Arrays.toString(values));
~~~

**Exact expected stdout (continued):**

~~~text
[6, 7, 8]
~~~

## 4. `String` Arrays: Reassigning the Variable Also Does Not Change Elements

`String` is a reference type, yet it is **immutable**: methods like `toUpperCase` return a String without modifying the original String's content.

~~~java
import java.util.Locale;

String[] names = {"an", "binh"};
for (String name : names) {
    name = name.toUpperCase(Locale.ROOT);
}

System.out.println(Arrays.toString(names));
~~~

**Exact expected stdout:**

~~~text
[an, binh]
~~~

`name = name.toUpperCase(...)` only makes the variable `name` reference another String, while the elements of `names` remain unchanged.

**The right approach when you want to replace Strings in the array:**

~~~java
for (int i = 0; i < names.length; i++) {
    names[i] = names[i].toUpperCase(Locale.ROOT);
}
System.out.println(Arrays.toString(names));
~~~

**Exact expected stdout (continued):**

~~~text
[AN, BINH]
~~~

Do not confuse **creating a new value and assigning it to the loop variable** with **assigning a new value into the array slot**.

## 5. Boundaries: Objects, Subarrays, and Lists

**Reassigning an element** and **mutating the object an element points to** are two different operations. With `StringBuilder[] builders`, `builder.append("!")` modifies the shared object's contents; `builder = new StringBuilder("NEW")` only changes the local variable, whereas `builders[i] = ...` actually replaces the reference at the array position.

With `int[][] matrix`, the variable `row` in `for (int[] row : matrix)` is a copied reference to the subarray. `row[0]++` modifies the subarray's data; `row = new int[]{99}` does not replace `matrix[i]`. When you need to replace an entire row, use the outer array's index.

Enhanced `for` on `List<Integer>` also does not automatically call `set`: `number++` only reassigns the local variable (unboxing/boxing). With mutable Lists, use `set(i, value)` or `replaceAll`. `List.of(...)` does not support element update operations. Aliasing mechanics and `ListIterator.set` are discussed in greater depth in a dedicated lesson on object references.

## 6. Standalone Java 17 Program with Exact Output

Create the exact file **`EnhancedForAssignmentDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public final class EnhancedForAssignmentDemo {
    private EnhancedForAssignmentDemo() {}

    static void primitiveArray() {
        int[] scores = {1, 2, 3};

        for (int score : scores) {
            score *= 10;
        }
        System.out.println("primitive after reassignment="
                + Arrays.toString(scores));

        for (int i = 0; i < scores.length; i++) {
            scores[i] *= 10;
        }
        System.out.println("primitive after indexed update="
                + Arrays.toString(scores));
    }

    static void immutableStringArray() {
        String[] names = {"an", "binh"};

        for (String name : names) {
            name = name.toUpperCase(Locale.ROOT);
        }
        System.out.println("string after reassignment="
                + Arrays.toString(names));

        for (int i = 0; i < names.length; i++) {
            names[i] = names[i].toUpperCase(Locale.ROOT);
        }
        System.out.println("string after indexed update="
                + Arrays.toString(names));
    }

    static void mutableObjectArray() {
        StringBuilder[] builders = {
            new StringBuilder("A"),
            new StringBuilder("B")
        };

        for (StringBuilder builder : builders) {
            builder.append("!");
            builder = new StringBuilder("OTHER");
        }
        System.out.println("objects after mutation="
                + Arrays.toString(builders));

        for (int i = 0; i < builders.length; i++) {
            builders[i] = new StringBuilder("NEW" + i);
        }
        System.out.println("objects after indexed replacement="
                + Arrays.toString(builders));
    }

    static void twoDimensionalArray() {
        int[][] matrix = {
            {1, 2},
            {3, 4}
        };

        for (int[] row : matrix) {
            row[0] += 10;
            row = new int[]{99, 99};
        }
        System.out.println("matrix after row alias mutation="
                + Arrays.deepToString(matrix));

        for (int i = 0; i < matrix.length; i++) {
            matrix[i] = new int[]{20 + i};
        }
        System.out.println("matrix after row replacement="
                + Arrays.deepToString(matrix));
    }

    static void boxedList() {
        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

        for (Integer number : numbers) {
            number++;
        }
        System.out.println("list after variable update=" + numbers);

        for (int i = 0; i < numbers.size(); i++) {
            numbers.set(i, numbers.get(i) + 1);
        }
        System.out.println("list after set=" + numbers);
    }

    static void finalLocalReference() {
        StringBuilder[] items = {new StringBuilder("A")};
        for (final StringBuilder item : items) {
            item.append("!");
        }
        System.out.println("final reference object="
                + Arrays.toString(items));
    }

    public static void main(String[] args) {
        primitiveArray();
        immutableStringArray();
        mutableObjectArray();
        twoDimensionalArray();
        boxedList();
        finalLocalReference();
    }
}
~~~

**Requirements:** JDK 17 or higher; open a terminal in the directory containing the file. The code uses only the standard JDK library, with no preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 EnhancedForAssignmentDemo.java
java -cp . EnhancedForAssignmentDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\EnhancedForAssignmentDemo.java
java -cp . EnhancedForAssignmentDemo
~~~

### Exact expected stdout

~~~text
primitive after reassignment=[1, 2, 3]
primitive after indexed update=[10, 20, 30]
string after reassignment=[an, binh]
string after indexed update=[AN, BINH]
objects after mutation=[A!, B!]
objects after indexed replacement=[NEW0, NEW1]
matrix after row alias mutation=[[11, 2], [13, 4]]
matrix after row replacement=[[20], [21]]
list after variable update=[1, 2, 3]
list after set=[2, 3, 4]
final reference object=[A!]
~~~

**Comparison:**

1. `score *= 10` does not modify `scores`; `scores[i] *= 10` modifies the element directly.
2. `name = name.toUpperCase(...)` does not replace the String in the array; `names[i] = ...` does.
3. `builder.append("!")` changes the shared object's contents; `builder = new ...` does not replace the object referenced by the array.
4. `row[0] += 10` modifies the subarray; `row = new int[] {...}` does not replace the subarray in `matrix`.
5. `Integer number++` only updates the local variable; `numbers.set(...)` actually replaces the List element.
6. `final` prevents the reference variable from switching to another object, but does not make a mutable object immutable.

## 7. Exercises with Answers

### Exercise A — predict the array after the loop

~~~java
int[] a = {2, 4};
for (int x : a) {
    x = 0;
}
System.out.println(Arrays.toString(a));
~~~

**Answer:**

~~~text
[2, 4]
~~~

The assignment only affects `x` on each iteration.

### Exercise B — fix it the right way

Requirement: multiply every element of `a` by 3.

~~~java
for (int i = 0; i < a.length; i++) {
    a[i] *= 3;
}
~~~

With initial array `{2, 4}`, the result is `[6, 12]`.

### Exercise C — mutable object

~~~java
StringBuilder[] a = {new StringBuilder("X")};
for (StringBuilder x : a) {
    x.append("Y");
    x = new StringBuilder("Z");
}
System.out.println(Arrays.toString(a));
~~~

**Answer:**

~~~text
[XY]
~~~

`append` changes the object residing in the array; reassigning `x` does not replace element `a[0]`.

### Exercise D — two-dimensional array

~~~java
int[][] m = {{1, 2}};
for (int[] row : m) {
    row[1] = 9;
    row = new int[]{0};
}
System.out.println(Arrays.deepToString(m));
~~~

**Answer:**

~~~text
[[1, 9]]
~~~

`row[1] = 9` modifies an element of the subarray; reassigning `row` does not replace the outer array element.

### Exercise E — `final` variable

~~~java
StringBuilder[] items = {new StringBuilder("A")};
for (final StringBuilder item : items) {
    item.append("B");
    // item = new StringBuilder("C"); // Does not compile.
}
~~~

**Answer:** the first object becomes `"AB"`; reassigning `item` is forbidden because of `final`, yet `append` is still valid.

## 8. Checklist and Conclusion

- [ ] Understand that enhanced `for` iterates over each **element value**, without providing an array slot for write-back.
- [ ] Know that assigning `value = ...`, `value++`, `value += ...` does not modify a primitive array.
- [ ] Know that `String` is immutable and reassigning a String variable does not replace elements in the array.
- [ ] Distinguish **reassigning a reference variable** from **mutating the state of a referenced mutable object**.
- [ ] Know that `row[0]` can modify a subarray, whereas `row = new int[]` does not replace the row of the outer array.
- [ ] Know that calling `numbers.set(i, ...)` on a mutable List is what replaces a List element.
- [ ] Know that `final` prevents variable reassignment, without making an object's contents immutable.
- [ ] Choose an indexed for loop when element replacement is needed, and enhanced for when iterating/reading data.
- [ ] Do not confuse modifying a collection's structure with reassigning the loop variable.
- [ ] Run `EnhancedForAssignmentDemo.java` on Java 17+ and verify the exact stdout.

**Conclusion:** Enhanced `for` gives you **a local variable holding the element's value in the current iteration**. Because Java copies **values** (including reference values), reassigning that variable **does not write back to the array or List**. To replace elements, update the exact position via index or collection API; if the variable references a mutable object, you can change the **object's state** with a method, though that is a different action from replacing the element.
