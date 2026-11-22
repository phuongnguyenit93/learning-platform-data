# Off-by-one errors at loop boundaries — Java 17+

An **off-by-one error** (*off-by-one error*) occurs when a loop runs **one iteration too few** or **one iteration too many** compared to what is required. The bug usually lies in the starting value, the `<`/`<=` condition, the update step, or how the ending bound is understood to be included or excluded.

~~~java
int[] numbers = {10, 20, 30};

for (int i = 0; i < numbers.length; i++) {
    System.out.println(numbers[i]); // 10, 20, 30.
}
~~~

In Java, an array of length `n` has valid indices from **`0` to `n - 1`**. The value `n` is an **exclusive ending bound**; it is not the index of the last element.

## 1. Distinguishing closed and half-open bounds

| Goal | Correct way to write | Iterations when range is valid |
| --- | --- | --- |
| Traverse an array of length `n` | `for (int i = 0; i < n; i++)` | `n` |
| Iterate from `0` to `n` **inclusive of `n`** | `for (int i = 0; i <= n; i++)` | `n + 1` |
| Iterate indices from `start` up to **before `end`** | `for (int i = start; i < end; i++)` | `end - start` if `start <= end` |
| Iterate from `start` to `end` **inclusive of `end`** | `for (int i = start; i <= end; i++)` | `end - start + 1` if `start <= end` |
| Traverse an array in reverse | `for (int i = a.length - 1; i >= 0; i--)` | `a.length` |

Example starting at 1 and ending at 3:

~~~text
[1, 3)  → 1, 2       (2 values, excluding 3)
[1, 3]  → 1, 2, 3    (3 values, including 3)
~~~

The notation `[start, end)` is a **half-open interval**, very useful when working with array indices. `[start, end]` is a closed interval; clearly state the boundary convention in variable names or method contracts.

**Note:** the iteration count formulas above assume a step size of 1, valid boundary ordering, and no `break`/`return`. If there is a different step size, decrementing, or integer overflow, re-analyze accordingly.

## 2. Self-contained runnable Java 17+ program

Create a UTF-8 file **`OffByOneDemo.java`**:

~~~java
public class OffByOneDemo {
    static int sumFirst(int[] values, int count) {
        if (count < 0 || count > values.length) {
            throw new IllegalArgumentException("invalid count");
        }
        int sum = 0;
        for (int i = 0; i < count; i++) {
            sum += values[i];
        }
        return sum;
    }

    static int sumRange(int[] values, int start, int endExclusive) {
        if (start < 0 || endExclusive < start
                || endExclusive > values.length) {
            throw new IllegalArgumentException("invalid range");
        }
        int sum = 0;
        for (int i = start; i < endExclusive; i++) {
            sum += values[i];
        }
        return sum;
    }

    public static void main(String[] args) {
        int[] values = {10, 20, 30};
        System.out.println("== array indices ==");
        System.out.println("length=" + values.length);
        for (int i = 0; i < values.length; i++) {
            System.out.println("index=" + i + ",value=" + values[i]);
        }

        System.out.println("== inclusive vs exclusive ==");
        for (int i = 1; i < 3; i++) {
            System.out.println("exclusive=" + i);
        }
        for (int i = 1; i <= 3; i++) {
            System.out.println("inclusive=" + i);
        }

        System.out.println("== prefix and range ==");
        System.out.println("first0=" + sumFirst(values, 0));
        System.out.println("first2=" + sumFirst(values, 2));
        System.out.println("first3=" + sumFirst(values, 3));
        System.out.println("range1to3=" + sumRange(values, 1, 3));
        System.out.println("emptyRange=" + sumRange(values, 2, 2));

        System.out.println("== reverse and empty array ==");
        for (int i = values.length - 1; i >= 0; i--) {
            System.out.println("reverse=" + values[i]);
        }
        int[] empty = {};
        int visits = 0;
        for (int i = 0; i < empty.length; i++) {
            visits++;
        }
        System.out.println("emptyVisits=" + visits);

        System.out.println("== one past the end ==");
        int index = 0;
        while (index < values.length) {
            index++;
        }
        System.out.println("indexAfterWhile=" + index);
        try {
            System.out.println("unexpected=" + values[values.length]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("atLength=ArrayIndexOutOfBoundsException");
        }
        try {
            sumFirst(values, 4);
        } catch (IllegalArgumentException ex) {
            System.out.println("count4=" + ex.getMessage());
        }

        System.out.println("== substring uses exclusive end ==");
        String text = "ABCDE";
        System.out.println("slice=" + text.substring(1, 4));
        System.out.println("done");
    }
}
~~~

In the directory containing the file, use **JDK 17 or later** with PowerShell or Bash:

~~~bash
java -version
javac -version
javac -encoding UTF-8 OffByOneDemo.java
java OffByOneDemo
~~~

**Exact expected stdout** of the `java OffByOneDemo` command alone:

~~~text
== array indices ==
length=3
index=0,value=10
index=1,value=20
index=2,value=30
== inclusive vs exclusive ==
exclusive=1
exclusive=2
inclusive=1
inclusive=2
inclusive=3
== prefix and range ==
first0=0
first2=30
first3=60
range1to3=50
emptyRange=0
== reverse and empty array ==
reverse=30
reverse=20
reverse=10
emptyVisits=0
== one past the end ==
indexAfterWhile=3
atLength=ArrayIndexOutOfBoundsException
count4=invalid count
== substring uses exclusive end ==
slice=BCD
done
~~~

The output of `java -version`/`javac -version` depends on the installed JDK and is not part of the fixed stdout. The code uses standard APIs and requires no external libraries.

## 3. Why is `i <= array.length` usually wrong?

~~~java
int[] values = {10, 20, 30};

// WRONG if accessing values[i]:
// for (int i = 0; i <= values.length; i++) {
//     System.out.println(values[i]);
// }
~~~

The loop `i <= values.length` runs when `i == 3`, but for an array of length 3, only indices 0, 1, and 2 are valid. Accessing `values[3]` throws `ArrayIndexOutOfBoundsException`.

If the requirement is **traversing elements**, use `i < values.length`. If the requirement is **traversing boundary positions between elements**, `i <= values.length` might be needed, since there are `n + 1` boundary positions, but in that case you must not read `values[i]` at position `i == n`.

In other words, **`<=` is not automatically wrong**; it is only wrong when it does not match the value range and the operations in the body.

## 4. Counting iterations differs from indexing

Two tasks can use different conditions:

~~~java
// Perform an action exactly 3 times:
for (int turn = 1; turn <= 3; turn++) {
    System.out.println("turn=" + turn);
}

// Traverse three array elements:
for (int i = 0; i < 3; i++) {
    System.out.println(values[i]);
}
~~~

Both run three iterations, but one variable is an **iteration number** 1..3, and the other is an **index** 0..2. Mixing the two conventions easily causes an off-by-one error.

For the first `count` elements of an array, the number of elements to process is `count` itself; write `i < count`. When `count == 0`, the body must run 0 times. Writing `i <= count` would process **one element** even when 0 elements were requested.

### Half-open intervals help join adjacent segments

For example, suppose you want to process indices belonging to two intervals:

~~~text
[0, 2) = 0, 1
[2, 5) = 2, 3, 4
Joined: [0, 5) = 0, 1, 2, 3, 4
~~~

The two intervals do not overlap and leave no gap. When `start == end`, the interval `[start, end)` is **empty**, so running 0 iterations is the right behavior. Java's `String.substring(beginIndex, endIndex)` API also uses an **exclusive ending bound**.

## 5. Reverse traversal and empty arrays

An array of `n` elements has last valid index `n - 1`, so:

~~~java
for (int i = values.length - 1; i >= 0; i--) {
    System.out.println(values[i]);
}
~~~

If `values.length == 0`, the initial value is `i == -1` and the condition `i >= 0` is immediately false; no element is read. This is why this pattern handles empty arrays properly.

Avoid starting at `i = values.length` if the body will read `values[i]`: that index is **one past the right bound**.

Be especially careful with a condition like `i > 0`: when counting down to 0, it **misses element index 0**. Use `i >= 0` if you want to include the first element.

### Be careful when counting with an unsuitable type

Java uses `int` for array indices. Do not switch the counter variable to a type that does not support negative values and assume `i >= 0` will terminate the same way `int` does. In Java, `char` is an unsigned 16-bit type; after decrementing and converting, it can wrap around, making it unsuitable for reverse traversal with a `>= 0` condition.

## 6. Testing boundary points

Off-by-one errors usually surface at **boundary values**, not necessarily on ordinary inputs.

| Test case | Expected behavior |
| --- | --- |
| Empty array (`length == 0`) | No element access |
| 1-element array | Exactly 1 traversal; does not exceed index 0 |
| 3-element array | Indices `0, 1, 2`; does not access 3 |
| `count = 0` | Processes 0 elements |
| `count = length` | Processes all elements, none extra |
| `count = length + 1` | Rejected if parameter is the number of elements to process |
| `start == endExclusive` | Empty interval, initial sum unchanged |
| Reverse traversal | Reaches and includes index 0 |

An effective testing approach is to first write down the **valid index range**, and then verify three values: just before the bound, right at the bound, and just past the bound. When writing a `for` or `while` loop, always verify both the **final value of the counter variable** and the **last value actually processed in the body**.

## 7. Common mistakes

| Misconception | Correct way |
| --- | --- |
| “An array of length `n` has last index `n`.” | Last index is `n - 1` |
| “`i <= array.length` traverses all elements.” | Usually one iteration too many; use `i < array.length` |
| “`i < n` starting at 0 runs `n + 1` times.” | Runs `n` times when `n >= 0` and step is 1 |
| “`for(i=n-1; i>0; i--)` traverses all elements.” | Skips index 0 |
| “Interval `[start, end)` includes `end`.” | `end` is excluded |
| “If an array is empty, at least one element must be accessed.” | Correct traversal is 0 times |
| “Testing large arrays is enough.” | Boundaries 0, 1, and exact `length` are critical |
| “If there's an exception, fix it by adding an early `break` at the end.” | Must fix the **index range and condition** |

## 8. Self-check exercises

1. For `int[] a = new int[4]`, what are the valid indices?  
   *Answer:* `0, 1, 2, 3`.
2. How many iterations does `for (int i = 0; i <= 4; i++)` run?  
   *Answer:* `5` iterations; reading `a[i]` on the last iteration goes out of bounds.
3. How many consecutive integers does the interval `[2, 6)` contain?  
   *Answer:* 4 numbers (`2, 3, 4, 5`).
4. Does reverse traversal `for (int i = 4; i > 0; i--)` process `i == 0`?  
   *Answer:* No.
5. What does `String "ABCDE".substring(1, 4)` produce?  
   *Answer:* `"BCD"`.
6. If `count = 0`, how many times does `for (int i = 0; i < count; i++)` run?  
   *Answer:* 0 times.

## Checklist

- [ ] Clearly distinguish **element index** from **iteration count**.
- [ ] Know that `n` elements have indices `0..n-1`.
- [ ] Properly use an **exclusive** end bound with `<` and an **inclusive** end bound with `<=`.
- [ ] Test empty arrays, 1-element arrays, and exact boundary values.
- [ ] Ensure reverse traversal accounts for index 0.
- [ ] State the `[start, end)` convention explicitly and check `start <= end <= length`.
- [ ] Ensure counter variables progress and avoid overflow if bounds are very large.

**Conclusion:** Off-by-one is not just confusing `<` with `<=`, it is confusing **the meaning of the boundary**. Before writing a loop, determine the first value processed, the last value processed, the desired iteration count, and whether the ending bound is included or excluded.
