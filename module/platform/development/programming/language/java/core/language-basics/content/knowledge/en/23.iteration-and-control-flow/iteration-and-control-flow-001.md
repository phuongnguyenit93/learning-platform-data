# Enhanced `for` to Iterate Over Arrays or `Iterable` in Java

> **Java core — language-basics / Iteration and Control Flow**  
> **Version:** JDK 17+, single standalone Java file, standard library only.  
> **Goal:** Properly use the *enhanced for* (`for-each`) loop with arrays and `Iterable`; understand how each element is retrieved, iteration order, the effect of the loop variable, and limitations when needing indices or removing elements.

## 1. Syntax and Meaning

~~~java
for (ElementType element : source) {
    // Process element.
}
~~~

`source` must be an **array** or an expression whose type implements `java.lang.Iterable`. On each iteration, Java retrieves one element and assigns it to the local variable `element`. The loop stops after iterating through all elements, or is terminated early by `break`, `return`, or an exception.

~~~java
int[] scores = {3, 5, 8};
int sum = 0;

for (int score : scores) {
    sum += score;
}
System.out.println(sum); // 16
~~~

`for-each` is suitable when you only need **each element's value**, without manually managing an index. It is not an automatic parallel execution mechanism and does not return a new result collection; operations inside the body are still executed sequentially.

In Java 17, you can also write `for (var item : source)` if the compiler can infer the element type. For introductory exercises, writing explicit types like `int` or `String` is usually easier to read.

## 2. Iterating Over Arrays: From Start to End

`for-each` supports primitive arrays such as `int[]`, `double[]` and reference arrays such as `String[]`:

~~~java
String[] names = {"An", "Binh", "Chi"};

for (String name : names) {
    System.out.println(name);
}
// Prints An, Binh, Chi in index order 0, 1, 2.
~~~

In terms of element-traversal behavior, Java handles arrays roughly equivalently to:

~~~java
for (int index = 0; index < names.length; index++) {
    String name = names[index];
    System.out.println(name);
}
~~~

**Difference:** With `for-each`, the index is not available under its own variable name. If you need to modify an element at a specific position, iterate in reverse, skip even/odd positions, or know the exact index, use an indexed `for` loop.

| Need | Usually suitable approach |
| --- | --- |
| Read every element in order | `for (T x : array)` |
| Update array elements at each index | `for (int i = 0; i < array.length; i++)` |
| Iterate from end to start | `for` with descending index |
| Compute sum, count elements, find max | `for-each` and an accumulator variable |
| Stop early when a value is encountered | `break` or `return` |

## 3. Iterating Over `Iterable`: Java Uses `Iterator`

`Iterable<T>` is an interface that defines the `iterator()` method. Many collections such as `List` and `Set` implement `Iterable`:

~~~java
java.util.List<String> colors =
        java.util.List.of("red", "green", "blue");

for (String color : colors) {
    System.out.println(color.toUpperCase(java.util.Locale.ROOT));
}
// Prints RED, GREEN, BLUE.
~~~

Conceptually, Java performs the equivalent of obtaining an `Iterator` and looping:

~~~java
java.util.Iterator<String> it = colors.iterator();

while (it.hasNext()) {
    String color = it.next();
    System.out.println(color.toUpperCase(java.util.Locale.ROOT));
}
~~~

`Iterable` **is not synonymous with** `Iterator`: the former provides `iterator()`, while the latter provides `hasNext()` and `next()` to traverse data. A standalone `Iterator` cannot be placed directly after the `:` in an enhanced for without a suitable `Iterable` source.

**Order:** Arrays always iterate in increasing index order. `List` iterates in the list's element order. For other collections, the order depends on the iterator's contract; **do not assume `HashSet` always has a fixed order**. If expected stdout needs to be deterministic, choose an array, a list, or an iterable source with a defined order.

`String` does not directly implement `Iterable<Character>`; to iterate over characters of a string, you can use indices with `charAt` or iterate over the array from `toCharArray()`. `Map` is not directly an `Iterable`; to iterate over key/value pairs, use `map.entrySet()`.

## 4. Writing Your Own Simple `Iterable`

You do not necessarily have to use a built-in collection. A custom class can implement `Iterable<Integer>` and provide an `Iterator<Integer>`:

~~~java
static final class Range implements Iterable<Integer> {
    private final int from, toExclusive;

    Range(int from, int toExclusive) {
        this.from = from;
        this.toExclusive = toExclusive;
    }

    @Override
    public java.util.Iterator<Integer> iterator() {
        return new java.util.Iterator<>() {
            private int nextValue = from;

            @Override
            public boolean hasNext() {
                return nextValue < toExclusive;
            }

            @Override
            public Integer next() {
                if (!hasNext()) {
                    throw new java.util.NoSuchElementException();
                }
                return nextValue++;
            }
        };
    }
}
~~~

Use it like an array or list:

~~~java
int total = 0;
for (int value : new Range(2, 5)) {
    total += value;
}
// Iterates 2, 3, 4; total == 9.
~~~

This is a simple illustration for an ascending range with `from <= toExclusive`. Each call to `iterator()` creates a separate iterator. For real-world data, an iterator needs to maintain the full `hasNext()/next()` contract, define how exhaustion is signaled, and account for data changes during iteration.

## 5. The Loop Variable's Value Is Not the Original Element Slot

In enhanced `for`, on each iteration the local variable receives **a copy of the element's value**. With `int[]`, reassigning the variable does not write back into the array:

~~~java
int[] numbers = {2, 4};
for (int number : numbers) {
    number *= 10;
}
// numbers is still [2, 4]; to update, use numbers[i] *= 10.
~~~

With reference-type elements, the copied reference still points to **the same object**: `StringBuilder.append` can mutate the object's state, but `builder = new StringBuilder("X")` only changes the local variable. Therefore, distinguish between *mutating an existing object* and *replacing the source element*. The program in section 8 lets you observe both cases; subsequent lessons delve deeper into value-copying rules and update operations.

## 6. `break`, `continue`, and Modifying Collections While Iterating

`continue` skips the rest of the current iteration and takes the next element; `break` exits the entire current enhanced for loop:

~~~java
int[] values = {1, -2, 0, 5, 7};
int counted = 0;

for (int value : values) {
    if (value < 0) {
        continue; // Skip negative numbers.
    }
    if (value == 5) {
        break; // Do not check 5 and 7.
    }
    counted++; // Only counts 1 and 0.
}
// counted == 2.
~~~

**Do not add/remove elements directly from an `ArrayList` inside `for-each`**:

~~~java
// Avoid doing this:
// for (String item : list) {
//     if (item.equals("B")) {
//         list.remove(item); // May cause ConcurrentModificationException.
//     }
// }
~~~

Many common collection iterators have a *fail-fast* mechanism that may throw `ConcurrentModificationException` when the collection is structurally modified outside the iterator. This mechanism **is not a synchronization guarantee or an absolute error-detection mechanism**.

When you need to remove elements while iterating over a mutable `ArrayList`, use `Iterator.remove()` after `next()` if the iterator supports it:

~~~java
java.util.List<String> list = new java.util.ArrayList<>(
        java.util.List.of("A", "B", "C", "B"));

java.util.Iterator<String> it = list.iterator();
while (it.hasNext()) {
    if (it.next().equals("B")) {
        it.remove();
    }
}
// list = [A, C].
~~~

If you only need to filter and do not need further processing in the same iteration, `list.removeIf(predicate)` is also a clear option. With immutable collections like `List.of(...)`, you cannot remove/replace elements; create a new list if you need a transformed result.

## 7. `null`, Empty Sources, and Pitfalls When Choosing an Iteration Style

- Empty array `new int[0]` or `List.of()`: the body runs zero times; accumulator variables keep their initial values.
- **Null source**: enhanced for needs to access the array or call `iterator()`, so it throws `NullPointerException`. Guard before the loop when data may be null.
- **Null elements** inside an array/list can still be iterated over: the loop does not automatically skip them. When calling methods on that element, check for null.
- An `Iterable` can return an iterator that runs over expensive or volatile data; do not assume every iterable source is cheap or repeatable like a list.
- If you need to know the index, you can maintain a manual counter for an `Iterable`, but with index-accessible arrays/lists, an indexed `for` is usually clearer.

| Situation | Outcome / Choice |
| --- | --- |
| `for (int x : new int[0])` | 0 iterations |
| `for (String s : List.of("A", "B"))` | 2 iterations in order A, B |
| `for (int x : (int[]) null)` | `NullPointerException` |
| Changing variable `x` in `for (int x : arr)` | Does not modify the array's elements |
| Structurally modifying `ArrayList` during for-each | Avoid; use an iterator supporting `remove()` or process afterward |

## 8. Standalone Java 17+ Program

Create the file **EnhancedForDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.StringJoiner;

public final class EnhancedForDemo {
    static final class Range implements Iterable<Integer> {
        private final int from, toExclusive;

        Range(int from, int toExclusive) {
            this.from = from;
            this.toExclusive = toExclusive;
        }

        @Override
        public Iterator<Integer> iterator() {
            return new Iterator<>() {
                private int nextValue = from;

                @Override
                public boolean hasNext() {
                    return nextValue < toExclusive;
                }

                @Override
                public Integer next() {
                    if (!hasNext()) {
                        throw new NoSuchElementException();
                    }
                    return nextValue++;
                }
            };
        }
    }

    public static void main(String[] args) {
        int[] scores = {3, 5, 8};
        int sum = 0;
        for (int score : scores) {
            sum += score;
        }
        System.out.println("arraySum=" + sum);

        int[] numbers = {2, 4};
        for (int number : numbers) {
            number *= 10;
        }
        System.out.println("arrayReassign=" + Arrays.toString(numbers));

        for (int i = 0; i < numbers.length; i++) {
            numbers[i] *= 10;
        }
        System.out.println("arrayIndexed=" + Arrays.toString(numbers));

        List<String> colors = List.of("red", "green", "blue");
        StringJoiner joiner = new StringJoiner("|");
        for (String color : colors) {
            joiner.add(color.toUpperCase(Locale.ROOT));
        }
        System.out.println("iterableColors=" + joiner);

        int rangeSum = 0;
        for (int value : new Range(2, 5)) {
            rangeSum += value;
        }
        System.out.println("customRangeSum=" + rangeSum);

        List<StringBuilder> labels = new ArrayList<>();
        labels.add(new StringBuilder("A"));
        labels.add(new StringBuilder("B"));
        for (StringBuilder label : labels) {
            label.append("!");
        }
        System.out.println("objectMutation=" + labels);

        int[] values = {1, -2, 0, 5, 7};
        int counted = 0;
        for (int value : values) {
            if (value < 0) {
                continue;
            }
            if (value == 5) {
                break;
            }
            counted++;
        }
        System.out.println("skipAndBreak=" + counted);

        List<String> removable = new ArrayList<>(
                List.of("A", "B", "C", "B"));
        Iterator<String> it = removable.iterator();
        while (it.hasNext()) {
            if (it.next().equals("B")) {
                it.remove();
            }
        }
        System.out.println("iteratorRemove=" + removable);

        int emptyVisits = 0;
        for (int value : new int[0]) {
            emptyVisits++;
        }
        System.out.println("emptyVisits=" + emptyVisits);

        int[] missing = null;
        try {
            for (int value : missing) {
                System.out.println(value);
            }
        } catch (NullPointerException ex) {
            System.out.println("nullArray=NullPointerException");
        }
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 EnhancedForDemo.java
java EnhancedForDemo
~~~

**Exact expected stdout:**

~~~text
arraySum=16
arrayReassign=[2, 4]
arrayIndexed=[20, 40]
iterableColors=RED|GREEN|BLUE
customRangeSum=9
objectMutation=[A!, B!]
skipAndBreak=2
iteratorRemove=[A, C]
emptyVisits=0
nullArray=NullPointerException
~~~

The results `arrayReassign` and `arrayIndexed` clarify the difference between changing the **loop variable** versus changing the **actual element**. `objectMutation` shows that mutating object state is reflected in the list. `customRangeSum` illustrates a custom `Iterable`, without needing to be a `List`.

## 9. Checklist and Exercises

**Exercise 1.** Use enhanced for to compute the sum and count of positive elements in `int[] {4, -3, 0, 7}`. Predict the sum and count.

**Exercise 2.** Write an enhanced for loop iterating over `List<String>` and joining the strings with commas. If the list is empty, what is the result?

**Exercise 3.** Predict the array after `for (int value : numbers) { value++; }` and then fix it using an indexed loop to increment every element directly.

**Exercise 4.** Write a class implementing `Iterable<Integer>` that yields the numbers from 1 to 4, ending properly when `hasNext()` is false.

**Exercise 5.** With an `ArrayList<String>`, safely remove elements equal to `"B"` using `Iterator.remove()`. Why should you not modify the list structure directly inside a for-each loop?

**Exercise 6.** Handle a nullable array: when null, return a clear message; when empty, return a sum of 0; when populated, compute the sum using enhanced for.

**Checklist:** Is the source an array or `Iterable`? Does it depend on index/order? Are you modifying the collection structure while iterating? Did you distinguish a null source from an empty source? If you want to update the original values, did you choose the proper element assignment approach?

### Key Takeaways

**Enhanced `for (T element : source)`** is a concise way to iterate over arrays or `Iterable` when you only need each element. For arrays, it iterates from index 0 to the end; for `Iterable`, the order is determined by the iterator. The variable `element` is not a slot address for reassigning the source element; use an index or appropriate iterator when modifications are needed. Check for null sources, avoid structurally modifying collections outside the iterator, and choose an indexed `for` when an index is needed.
