# Repeated Concatenation with += and Total Data Copied in Java

The **+=** operator is often used to append content to a String variable. For example, after each read iteration, a program writes **result += part** to add a new segment. This concise syntax can cause a huge amount of work when the loop runs many times, because String in Java is **immutable**: you cannot directly extend the contents of an existing String.

The key point to analyze is not just the **number of concatenations**, but the **total length of all intermediate results created**. In a sequential concatenation model that must recreate the old prefix, cost can grow **quadratically with the number of iterations**; StringBuilder helps build a growing result using a mutable buffer. This lesson presents the formulas, Java 17 examples, alternatives, and the limits of the cost model when considering a real JVM.

## 1. Immutable String and the Meaning of +=

In Java, the statement:

~~~java
result += part;
~~~

is value-equivalent to:

~~~java
result = result + part;
~~~

When result is a String, concatenation creates a resulting String value, while the old String's contents remain unmodified. If another variable still holds a reference to the old string, it continues to see the old content. The following example illustrates this inside a method:

~~~java
String original = "Java";
String result = original;
result += " 17";

System.out.println(original); // Java
System.out.println(result);   // Java 17
~~~

A single concatenation or one in a short expression usually poses no serious issue; the problem arises when **the result from the previous iteration is fed back into the concatenation in the next iteration**:

~~~java
String result = "";
for (int i = 0; i < n; i++) {
    result += "x";
}
~~~

The loop has n iterations; however, as the string grows longer, the amount of data that must be created for each result also grows longer. You cannot simply look at n iterations and conclude the entire work is O(n).

## 2. Prefix-Copying Model for Repeated Concatenation

Assume each iteration appends exactly one character x, starting from the empty string. Consider a **simple implementation model**: each concatenation creates a new string containing the entire old prefix plus the new character.

| Iteration | Resulting string | New string length | Total length created |
| ---: | --- | ---: | ---: |
| 1 | x | 1 | 1 |
| 2 | xx | 2 | 3 |
| 3 | xxx | 3 | 6 |
| 4 | xxxx | 4 | 10 |
| 5 | xxxxx | 5 | 15 |

After n iterations, the final string length is only n, but the total length of the result values across each concatenation is:

\[
T(n)=1+2+3+\cdots+n=\frac{n(n+1)}{2}.
\]

Therefore **T(n) = Θ(n²)** if each iteration must recreate the entire resulting String. For example, with **10,000 iterations**, the final String is 10,000 characters long, while the total length of intermediate results under the model is:

\[
T(10\,000)=\frac{10\,000 \times 10\,001}{2}=50\,005\,000.
\]

The figure **50,005,000 character units** is the result of **mathematical analysis**, not a measured byte count on a machine. Java does not mandate the physical number of bytes copied in each concatenation; the compiler and JVM may optimize this process. The formula shows why recreating a growing prefix risks becoming inefficient at large scale.

### Counting Only the Old String Portion

If we count only the amount of **old prefix** that must be retained during concatenation, the successive sizes are 0, 1, 2, ..., n - 1 character units:

\[
P(n)=0+1+2+\cdots+(n-1)=\frac{n(n-1)}{2}.
\]

Adding one new character per iteration contributes n units in total, giving P(n) + n = T(n). The two formulas describe two ways of counting: **only the old prefix** versus **the entire new result**.

## 3. Java 17 Example Verifying the Calculation

Create the file **RepeatedConcatDemo.java**:

~~~java
public class RepeatedConcatDemo {
    public static void main(String[] args) {
        int n = 5;
        String joined = "";
        long sumLengths = 0;

        for (int i = 0; i < n; i++) {
            joined += "x";
            sumLengths += joined.length();
        }

        StringBuilder builder = new StringBuilder(n);
        for (int i = 0; i < n; i++) {
            builder.append('x');
        }
        String built = builder.toString();

        System.out.println("+= result: " + joined);
        System.out.println("builder result: " + built);
        System.out.println("equal: " + joined.equals(built));
        System.out.println("sum lengths: " + sumLengths);
        System.out.println("formula: " + ((long) n * (n + 1) / 2));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 RepeatedConcatDemo.java
java RepeatedConcatDemo
~~~

Output:

~~~text
+= result: xxxxx
builder result: xxxxx
equal: true
sum lengths: 15
formula: 15
~~~

The variable **sumLengths** sums the string length after each iteration. It only checks the formula 1 + 2 + ... + n; **this is not a measurement of how many bytes the JVM allocated or copied**. Both ways of building produce the same content, but use different memory strategies. Casting n to long before multiplication avoids int overflow in moderate-n examples; for n near the int limit, cast n + 1 to long as well.

## 4. When Each Iteration Appends a Part of Different Length

In practice, a loop might join lines, JSON fields, or text fragments of uneven sizes. Let **a_i** be the length of the part added in iteration i, and **S_i** be the length of the entire result after that iteration.

\[
S_i=a_1+a_2+\cdots+a_i.
\]

When the model requires recreating the resulting String on each iteration, the total length of intermediate results is:

\[
T=\sum_{i=1}^{n}S_i
 = n a_1 +(n-1)a_2+\cdots+1a_n.
\]

Or equivalently:

\[
T=\sum_{j=1}^{n}(n-j+1)a_j.
\]

This is the **per-data-part view**: a part added early appears in more subsequent intermediate results than a part added at the end. If every part is k characters long, the total length is:

\[
T=k\frac{n(n+1)}{2}.
\]

When k is a constant, this is still **Θ(n²) in the number of iterations n**. If parts have varying lengths, you must state clearly which variables are used for complexity analysis.

For example, three parts **A**, **BB**, **CCC** have lengths 1, 2, 3. The cumulative results have lengths 1, 3, 6, so T = 1 + 3 + 6 = **10**, even though the final String is only **6** long.

### Do the Model and Actual Bytes Match?

Not necessarily. T(n) counts **character units** in the intermediate results according to the model. Java String can use **Latin-1 or UTF-16** representation depending on the data and JVM, the JIT can eliminate some intermediate operations, and total cost includes object management and garbage collection.

Therefore, you should not claim that every **+=** always copies the exact number of bytes given by the formula above. The sound conclusion is: **repeated concatenation that genuinely has to recreate a growing String risks quadratic cost growth**. Actual machine cost must be measured on the specific JDK, hardware, and workload.

## 5. How Does StringBuilder Handle Growing Strings?

**StringBuilder** is a mutable string builder. When calling **append(part)**, it tries to add data into an existing storage region rather than creating an immutable String containing the entire prefix on each iteration:

~~~java
StringBuilder builder = new StringBuilder();
for (String part : parts) {
    builder.append(part);
}
String result = builder.toString();
~~~

This is an illustrative snippet; the variable parts must be declared in a real program.

StringBuilder has two concepts:

- **length():** the number of char units currently in the content.
- **capacity():** the current capacity before the storage needs to expand.

If the buffer has enough space, append can add data without recreating the entire prefix. When capacity is insufficient, the builder may allocate a larger buffer and copy the old content. With a proportional growth strategy, the resizing cost can be **amortized**, making the total string-building work typically near-linear in the total data appended. You do not need to assume append is O(1) in every case: appending a string of length m still has to process m units of data.

When you can estimate the output size in advance, you can initialize:

~~~java
StringBuilder builder = new StringBuilder(estimatedLength);
~~~

The parameter here is **capacity**, not content/length. A new builder with capacity 1000 still has length() == 0. A reasonable estimate helps reduce expansions; an overly large estimate can waste memory.

Important: normally, **call builder.toString() once after the loop**. If you call toString() on every iteration to take a snapshot, the cost of creating growing prefix strings can still reach quadratic levels because the problem's own output requirement is already large.

## 6. Complete StringBuilder Example with a Separator

Create the file **BuilderJoinDemo.java**:

~~~java
public class BuilderJoinDemo {
    public static void main(String[] args) {
        String[] parts = {"A", "BB", "CCC"};
        StringBuilder builder = new StringBuilder(12);

        for (int i = 0; i < parts.length; i++) {
            if (i > 0) {
                builder.append(" | ");
            }
            builder.append(parts[i]);
        }

        String result = builder.toString();
        System.out.println(result);
        System.out.println("length: " + result.length());
        System.out.println("capacity >= length: "
                + (builder.capacity() >= builder.length()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 BuilderJoinDemo.java
java BuilderJoinDemo
~~~

~~~text
A | BB | CCC
length: 12
capacity >= length: true
~~~

The three parts contain 1 + 2 + 3 = 6 characters; the two separators ** | ** contain 3 characters each, so the total length is 12. The builder is given a capacity of 12, matching the example. The last line checks the relationship capacity >= length, without depending on the internal capacity-growth formula of a particular JDK version.

When you only need to join strings with a separator, **String.join(" | ", parts)** is often shorter and clearer than a manual loop. With streams you can use **Collectors.joining(" | ")**; choose a method that expresses intent clearly rather than writing multiple append calls unnecessarily.

## 7. When Does Java Optimize the + Operator?

In Java 9+, the Java compiler can implement string concatenation expressions via **invokedynamic** and **StringConcatFactory**; the JVM can optimize further at runtime. An expression joining a fixed number of parts, for example:

~~~java
String label = "ID=" + id + "; status=" + status;
~~~

should not be assumed by default to be a chain of wasteful allocations. Modern Java can build the result very efficiently. For small parts and simple expressions, the **+** operator is usually the readable, sensible choice.

However, the loop:

~~~java
String result = "";
for (String part : parts) {
    result += part;
}
~~~

feeds **the value from the previous iteration** into the next iteration. If on each iteration the growing string must be recreated, the total amount of intermediate results follows the formula at the start of this lesson. The JVM may optimize certain specific cases, but **the language does not guarantee that this repeated concatenation is always converted into a reusable buffer**. Therefore, for large data or input-dependent loop counts, StringBuilder is the clearer and more predictable solution.

**Do not replace every + with a manual StringBuilder:** the right criteria are how many iterations occur, how the result length grows, whether the expression is genuinely on a hot execution path, and whether readers can clearly understand the intent.

## 8. Measuring Time and Memory Properly

You should not write two small code snippets, time each once with **System.nanoTime()**, and treat that as an absolute conclusion. Runtime depends on JIT warm-up, garbage collector, CPU state, input data, and whether the compiler eliminates unused work.

When you must verify real-world performance:

1. Use the **same input data** and verify **identical output**.
2. Warm up the measured code and run many iterations.
3. Exclude **println**, file reads, or data generation from the string-concatenation measurement.
4. Test multiple values of **n** and part sizes, rather than a single number.
5. Use **JMH** when reliable benchmarks are needed; observe throughput, allocations, and GC.
6. Distinguish **wall-clock time**, **allocated bytes**, and **total prefix length from the formula**.

For example, with text containing Unicode: String.length() counts **UTF-16 units**, which does not necessarily equal the number of user-perceived characters. That further shows why you cannot treat character counts as physical copied bytes without additional verification.

## 9. Applicable Scenarios

| Need | Usually appropriate choice | Why |
| --- | --- | --- |
| Joining a few fixed parts in one expression | Use + | Concise syntax; JVM optimizes the expression effectively. |
| Building a long String across many iterations | Use StringBuilder | Reuses buffer, avoiding recreating growing prefixes. |
| Joining a list with a delimiter | String.join or StringBuilder | Clearly expresses the separator rule. |
| Joining a stream into one string | Collectors.joining | Expresses element reduction cleanly. |
| Independent threads each building strings | One StringBuilder per task | StringBuilder is unsynchronized; avoids sharing mutable state. |
| Genuinely needing a synchronized buffer | Consider StringBuffer or appropriate synchronization | StringBuffer synchronizes methods, though it does not replace synchronizing the whole workflow. |
| Needing a resulting String on every iteration | Accept snapshot cost | The total length of **all required outputs** is inherently large. |

## 10. Common Mistakes

| Mistake | Explanation and fix |
| --- | --- |
| N concatenations are always O(n). | Each iteration may process a growing prefix; calculate the **total result length**. |
| Every + on String is O(n²). | Complexity depends on code shape; fixed expressions can be optimized. |
| The formula T(n) is the exact allocated byte count. | It is a model of total result length, not a physical measurement. |
| StringBuilder never copies old data. | When expanding capacity, it may need to copy its backing buffer. |
| new StringBuilder(1000) creates 1000 characters. | 1000 is initial capacity; length is still 0. |
| Calling builder.toString() on every iteration is still cheap. | Each snapshot is a String result; the total size of snapshots can be quadratic. |
| Using StringBuffer is always faster because it is synchronized. | Synchronization has overhead; local buffers normally use StringBuilder. |
| Measuring once with nanoTime is enough. | JIT/GC/CPU add noise; use measurements with warm-up, multiple samples, or JMH. |
| Concatenating Strings from multiple threads using one shared StringBuilder is safe. | StringBuilder does not guarantee thread safety; isolate per task or synchronize properly. |

## 11. Self-Check Exercises

**Question 1.** With 8 additions of one character, under the model that recreates the full String, what is the total length of intermediate results?

Answer: **8 × 9 / 2 = 36**. The final string is only 8 long; the total length of **old prefixes** is 7 × 8 / 2 = **28**.

**Question 2.** Concatenate three parts of lengths 2, 1, and 3 in order. What is the total length of the results after each iteration?

Answer: the three cumulative lengths are 2, 3, 6; total **11**. By the weighted formula: 3 × 2 + 2 × 1 + 1 × 3 = 11.

**Question 3.** If you use StringBuilder to build the final result once, yet on every iteration you still have to output a copy of the entire prefix, can you still avoid all quadratic cost?

Answer: **no**. Requiring n snapshots of growing length already has a modeled total output size of Θ(n²).

**Question 4.** For an expression combining first name, last name, and a greeting, should you prefer the + operator or StringBuilder?

Answer: **the + operator** is usually clear and efficient enough in a short expression; there is no need to optimize manually without evidence of a bottleneck.

## 12. Conclusion

When you see **result += part inside a loop**, ask not only “how many times does it loop?” but also “**how does the resulting String grow in length?**”. With n single-character parts and a model that recreates a new string on every iteration, the total length of intermediate results equals **n(n + 1) / 2**, growing quadratically with n while the final result is only n long. With uneven part lengths, the total modeled cost is the sum of the prefix lengths.

**StringBuilder** lets you append into a mutable buffer, expanding when needed and creating the resulting String upon completion; it is the standard choice for building long strings in loops. **The + operator** remains suitable for short concatenation expressions. Cost models guide sound design choices, while real program performance should be evaluated with measurement tools on realistic data.