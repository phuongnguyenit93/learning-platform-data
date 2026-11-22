# Mutating Array Contents vs. Reassigning an Array Parameter in Java

> **Java core — language-basics / Methods**  
> **Environment:** JDK 17+, self-contained single Java file, no external libraries.  
> **Objective:** Understand that Java **passes arguments by value**, even when the argument is an array reference; distinguish mutating array elements, reassigning the parameter variable, returning a new array, and reassigning the variable on the caller side.

## 1. Core Rule: The Parameter Receives a Copy of the Reference

When passing an array variable into a method, Java **does not copy all elements** and also does not give the method authority to reassign the caller's variable. Instead, the reference value pointing to the array is **copied** into the parameter variable.

~~~java
static void changeFirst(int[] values) {
    values[0] = 99;
}

int[] numbers = {1, 2, 3};
changeFirst(numbers);
// numbers is now [99, 2, 3].
~~~

Upon entering the method, `numbers` and `values` are **two distinct variables** pointing to the **same array object**:

~~~text
Inside the method:
Caller                        Method
numbers ─────────┐          values ─────────┐
                 ▼                          ▼
               [ 1, 2, 3 ]   (THE SAME ARRAY)
~~~

`values[0] = 99` modifies an element **inside the shared array object**. Because the caller still points to that array, after the method returns, `numbers[0]` is `99`.

**Exact terminology:** Java uses *pass-by-value*, **not** *pass-by-reference* in the sense that a method could reassign the caller's `numbers` variable. The copied value here happens to be an **object reference**, so operations through the reference can mutate the shared object.

## 2. Reassigning the Parameter Only Changes the Method's Local Variable

Compare with the following call:

~~~java
static void replaceLocal(int[] values) {
    values = new int[] {7, 8}; // values points to a new array.
    values[0] = 70;            // Only mutates this new array.
}

int[] numbers = {1, 2, 3};
replaceLocal(numbers);
// numbers is still [1, 2, 3].
~~~

After `values = new int[] {7, 8}`:

~~~text
numbers ────────> [1, 2, 3]    (caller's original array)

values  ────────> [7, 8]       (method's new array)
                          └── mutated to [70, 8]
~~~

The assignment changes **the reference value held in parameter `values`**, without changing the reference stored in the outer variable `numbers`. Therefore the caller does not automatically switch to the new array.

| Statement in method | What changes? | Observable by caller? |
| --- | --- | --- |
| `values[0] = 99;` | Value of an element in the referenced array | Yes, if sharing the array reference |
| `values[0]++;` | Increments an element of the referenced array | Yes, if same array |
| `values = new int[] {7, 8};` | **Local** reference in `values` | Does not change caller's reference variable |
| `values = null;` | Only sets **parameter** to `null` | Does not automatically make caller's array variable `null` |
| `values = values.clone();` | Parameter points to a newly cloned array | Does not automatically change caller's reference |
| `return new int[] {...};` | Returns a new array reference | Caller's variable changes only if it assigns the result |

Important: If you mutate the original array first and then reassign the parameter, **the earlier mutation remains** in the original array.

## 3. Combining Content Mutation and Parameter Reassignment

~~~java
static void mutateThenRebind(int[] data) {
    data[1] = 22;               // Mutates original array.
    data = new int[] {3, 4};    // Only changes local parameter.
    data[0] = 30;               // Mutates new array, not original array.
}

int[] original = {11, 2, 3};
mutateThenRebind(original);
// original == [11, 22, 3] by contents.
~~~

Order matters: `data[1] = 22` happens **before** `data` is assigned to a different array, so the result seen by the caller is `[11, 22, 3]`. Meanwhile `data[0] = 30` happens after the reassignment and does not affect the original array.

**Do not confuse comparison operations:** `original == other` on two array variables checks whether they share the same reference. To compare contents of 1D `int[]` arrays, use `java.util.Arrays.equals(original, other)`.

## 4. When the Caller Needs Another Array: Return and Receive the Result

If the goal is to change **which array the caller's variable points to**, the clear approach is for the method to return the desired array and for the caller to assign it:

~~~java
static int[] replacement(int[] old) {
    return new int[] {100, 200};
}

int[] numbers = {1, 2, 3};
int[] newer = replacement(numbers); // numbers still keeps the old array.
numbers = newer;                    // Caller explicitly reassigns its variable.
~~~

You can also write directly:

~~~java
numbers = replacement(numbers);
~~~

After that assignment, the **caller code itself** changes the value of variable `numbers`. The `replacement` method only returns a reference; it has no way to perform an assignment to the caller's local `numbers` variable.

If you want to create a new array **based on old data** without modifying the source, use `Arrays.copyOf`:

~~~java
static int[] withAppended(int[] source, int value) {
    int[] output = java.util.Arrays.copyOf(source, source.length + 1);
    output[source.length] = value;
    return output;
}
~~~

`withAppended(new int[] {1, 2}, 3)` returns an array with contents `[1, 2, 3]`, while the source array `[1, 2]` is unchanged. `Arrays.copyOf` can throw an exception if `source == null`; establish the input contract before calling.

## 5. Aliasing, `clone()`, and the `final` Keyword

Two variables referencing the same array are called **aliases**. Mutating through one alias mutates the data observed through the other variable:

~~~java
int[] first = {3, 4};
int[] alias = first;
alias[0] = 10;

System.out.println(first[0]);   // 10
System.out.println(alias == first); // true
~~~

Meanwhile `clone()` on an `int[]` array creates a **new array object**:

~~~java
int[] copy = first.clone();
copy[0] = 99;

System.out.println(first[0]);      // 10
System.out.println(copy[0]);       // 99
System.out.println(copy == first); // false
~~~

For `int[]`, clone copies the primitive values. For `String[]` or `Object[]`, clone only copies **element references** without cloning the referenced objects themselves. For `int[][]`, cloning the outer array still shares the subarrays.

`final` on an array parameter **forbids reassigning the parameter variable**, but does not forbid mutating elements:

~~~java
static void increment(final int[] values) {
    values[0]++;                  // Valid.
    // values = new int[] {5};   // Compile ERROR because values is final.
}
~~~

Java arrays remain mutable objects even when their reference sits in a `final` variable.

## 6. Reference Arrays and Multidimensional Arrays Follow the Same Principle

The principle does not apply only to `int[]`:

~~~java
static void changeLabel(String[] labels) {
    labels[0] = "X";                 // Mutates element of original array.
}

static void rebindLabels(String[] labels) {
    labels = new String[] {"LOCAL"}; // Only changes parameter.
}
~~~

With multidimensional arrays, distinguish **replacing an element of the outer array** from **reassigning the outer array parameter variable**:

~~~java
static void changeRows(int[][] matrix) {
    matrix[0][1] = 9;         // Mutates element in existing subarray.
    matrix[1] = new int[] {8}; // Mutates element of OUTER array: replaces row 1.
}

static void replaceMatrixLocally(int[][] matrix) {
    matrix = new int[][] {{100}}; // Only reassigns local parameter.
}
~~~

Both `matrix[0][1] = 9` and `matrix[1] = new int[] {8}` change objects observable by the caller. However, `matrix = new int[][] {{100}}` **does not** replace the outer array held by the caller's variable.

Similarly, if elements of `Person[]` are references to mutable objects, distinguish `people[0] = new Person(...)` (replacing an array element) from `people[0].setName(...)` (changing the state of the object the element points to). Those are two different operations, even though both can be observed by the caller through an appropriate reference.

## 7. `null`, Indices, and Method Contracts

Simple examples often assume the parameter receives a non-`null` array with enough elements:

~~~java
static void increaseFirst(int[] numbers) {
    numbers[0] += 10;
}
~~~

- If `numbers == null`, accessing `numbers[0]` causes `NullPointerException`.
- If `numbers.length == 0`, index 0 does not exist and causes `ArrayIndexOutOfBoundsException`.
- If someone only tries to reassign the parameter `numbers = new int[3]`, that operation **does not** create/replace the array in the caller.

You can choose a safe and explicit contract:

~~~java
static boolean tryIncreaseFirst(int[] numbers) {
    if (numbers == null || numbers.length == 0) {
        return false;
    }
    numbers[0] += 10;
    return true;
}
~~~

If a new array needs to be created for the caller when null, **return the new array** and have the caller assign the result. You cannot turn a `null` argument into a new array in the caller via `numbers = new int[3]` inside a `void` method.

In real APIs, document clearly whether a method **mutates the input array** or returns a copy without touching the source. Choose names like `sortInPlace`, `fill`, `copyAndAppend`, or matching documentation so callers do not mistake the effect.

## 8. Standalone Java 17+ Program: Run and Inspect Output

Create the file **ArrayParameterSemanticsDemo.java**:

~~~java
import java.util.Arrays;

public final class ArrayParameterSemanticsDemo {
    private static void increaseFirst(int[] values) {
        values[0] += 10;
    }

    private static void rebindOnly(int[] values) {
        values = new int[] {7, 8};
        values[0] = 70;
        System.out.println("insideRebind=" + Arrays.toString(values));
    }

    private static void mutateThenRebind(int[] values) {
        values[1] = 22;
        values = new int[] {3, 4};
        values[0] = 30;
        System.out.println("insideCombined=" + Arrays.toString(values));
    }

    private static void setParameterNull(int[] values) {
        values = null;
        System.out.println("insideNull=" + (values == null));
    }

    private static int[] replacement(int[] old) {
        return new int[] {100, 200};
    }

    private static void finalMutation(final int[] values) {
        values[0]++;
    }

    private static void changeLabel(String[] values) {
        values[0] = "X";
    }

    private static void rebindLabels(String[] values) {
        values = new String[] {"LOCAL"};
        System.out.println("insideLabelRebind=" + Arrays.toString(values));
    }

    private static void changeRows(int[][] values) {
        values[0][1] = 9;
        values[1] = new int[] {8};
    }

    private static void rebindMatrix(int[][] values) {
        values = new int[][] {{100}};
        System.out.println("insideMatrixRebind=" + Arrays.deepToString(values));
    }

    public static void main(String[] args) {
        int[] original = {1, 2, 3};
        System.out.println("start=" + Arrays.toString(original));

        increaseFirst(original);
        System.out.println("afterElement=" + Arrays.toString(original));

        rebindOnly(original);
        System.out.println("afterRebind=" + Arrays.toString(original));

        mutateThenRebind(original);
        System.out.println("afterCombined=" + Arrays.toString(original));

        int[] alias = original;
        alias[2] = 33;
        System.out.println("aliasSame=" + (alias == original));
        System.out.println("afterAlias=" + Arrays.toString(original));

        setParameterNull(original);
        System.out.println("afterNullOriginal=" + (original != null));

        int[] returned = replacement(original);
        System.out.println("returned=" + Arrays.toString(returned));
        System.out.println("callerBeforeAssign=" + Arrays.toString(original));
        original = returned;
        System.out.println("callerAfterAssign=" + Arrays.toString(original));
        System.out.println("oldAlias=" + Arrays.toString(alias));

        int[] copied = original.clone();
        copied[0] = 500;
        System.out.println("copySame=" + (copied == original));
        System.out.println("copyChanged=" + Arrays.toString(copied));
        System.out.println("sourceAfterCopy=" + Arrays.toString(original));

        finalMutation(original);
        System.out.println("afterFinalMutation=" + Arrays.toString(original));

        String[] labels = {"A", "B"};
        changeLabel(labels);
        System.out.println("afterLabelMutation=" + Arrays.toString(labels));
        rebindLabels(labels);
        System.out.println("afterLabelRebind=" + Arrays.toString(labels));

        int[][] matrix = {{1, 2}, {3, 4}};
        changeRows(matrix);
        System.out.println("afterNestedMutation=" + Arrays.deepToString(matrix));
        rebindMatrix(matrix);
        System.out.println("afterMatrixRebind=" + Arrays.deepToString(matrix));

        try {
            increaseFirst(null);
        } catch (NullPointerException ex) {
            System.out.println("nullMutation=NullPointerException");
        }
    }
}
~~~

From the directory containing the file, run in PowerShell, Command Prompt, or Bash:

~~~bash
javac -encoding UTF-8 ArrayParameterSemanticsDemo.java
java ArrayParameterSemanticsDemo
~~~

**Exact expected stdout:**

~~~text
start=[1, 2, 3]
afterElement=[11, 2, 3]
insideRebind=[70, 8]
afterRebind=[11, 2, 3]
insideCombined=[30, 4]
afterCombined=[11, 22, 3]
aliasSame=true
afterAlias=[11, 22, 33]
insideNull=true
afterNullOriginal=true
returned=[100, 200]
callerBeforeAssign=[11, 22, 33]
callerAfterAssign=[100, 200]
oldAlias=[11, 22, 33]
copySame=false
copyChanged=[500, 200]
sourceAfterCopy=[100, 200]
afterFinalMutation=[101, 200]
afterLabelMutation=[X, B]
insideLabelRebind=[LOCAL]
afterLabelRebind=[X, B]
afterNestedMutation=[[1, 9], [8]]
insideMatrixRebind=[[100]]
afterMatrixRebind=[[1, 9], [8]]
nullMutation=NullPointerException
~~~

The lines `afterElement`, `afterCombined`, and `afterNestedMutation` prove that mutating the **array object** remains visible after the call. The lines `afterRebind`, `afterLabelRebind`, and `afterMatrixRebind` prove that changing **the parameter variable's reference** does not change the caller's variable. `callerAfterAssign` is the only case in the example where the caller explicitly assigns the returned array.

## 9. Common Mistakes and Exercises

| Misconception | How to correct the mental model |
| --- | --- |
| “Java passes arrays by reference” means a method can change the caller's variable | Java passes **a copy of the reference value**; reassigning the parameter does not reassign the caller |
| A `void` method writing `values = new int[3]` replaces the caller's array | No; return an array or use a state-wrapper type if design requires |
| `values[0] = ...` only changes the parameter variable | No; it modifies an element of the **array object** |
| Replacing `matrix[0] = new int[] {...}` is also invisible outside the caller | Wrong: this assigns an **element of the outer array**, visible via aliases |
| `clone()` always deep-copies every object | No; for reference arrays, elements are copied as references |
| Assigning `values = null` makes the caller's variable `null` | No; only the parameter inside the method changes |
| A `final int[]` parameter makes the array immutable | No; `values[i]` can still be modified |
| `Arrays.equals(a,b)` checks for the same object | No; it compares 1D **contents**, whereas `a == b` compares reference equality |
| Calling `array[0]` when the array is `null` or empty | Check null and length before accessing |

**Exercise 1.** Write `static void doubleFirst(int[] values)` that doubles the first element. Predict the value on the caller side after running with `int[] numbers = {3, 5}`.

**Exercise 2.** Write `static void reset(int[] values) { values = new int[values.length]; }`. Why does the old array keep its values? Fix with `Arrays.fill(values, 0)` if you want to mutate the original array.

**Exercise 3.** Write `static int[] resized(int[] source)` that creates an array one element larger, then use `source = resized(source)` in **caller code**. Compare before and after the assignment.

**Exercise 4.** Pass `String[]` into a method that changes `values[0]`, then try assigning `values = new String[] {...}`. Compare the results on the original array.

**Exercise 5.** With `int[][]`, compare `matrix[0] = new int[] {9}` with `matrix = new int[][] {{9}}` inside a method. Which statement changes a row of the caller's array?

**Exercise 6.** Try `final int[] data` as a parameter: compile the case changing `data[0]` and the case `data = new int[1]`; explain why only one case is valid.

### Key Takeaway

**Java always passes arguments by value.** When the argument is an array, the copied value is the **reference to the array**: modifying `values[i]` changes the shared array, whereas `values = anotherArray` only changes the **local** reference. To make the caller point to a new array, **return the new reference and assign on the caller side**; to keep the same array, mutate elements intentionally and state the method contract clearly.