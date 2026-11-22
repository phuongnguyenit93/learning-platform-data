# Comparing `String.join()`, `StringJoiner`, `StringBuilder`, and `+` Concatenation in Java

## 1. Four Ways of Joining Strings Solve Different Needs

In Java, `String` is **immutable**: once a string is created, its contents cannot change. Joining strings produces a new `String` value; how you structure the joining operation affects code clarity, delimiter control, and the amount of work performed when joining many parts.

- **`+` operator**: expresses direct concatenation; very convenient for a short expression or a few fixed parts.
- **`String.join()`**: joins a sequence of elements using **the same delimiter**; suitable when you already have an array or `Iterable` and just want the resulting string.
- **`StringJoiner`**: accumulates elements with a delimiter and supports **prefix/suffix**, an empty value, and `merge()`; suitable when adding elements one by one over time.
- **`StringBuilder`**: a mutable character buffer supporting `append()`, `insert()`, `delete()`, `replace()`, and custom formatting rules; suitable when joining in a loop or needing fine-grained control.

Example with the same data `["Java", "Spring", "SQL"]`:

~~~java
String a = "Java" + " | " + "Spring" + " | " + "SQL";
String b = String.join(" | ", "Java", "Spring", "SQL");

StringJoiner joiner = new StringJoiner(" | ", "[", "]");
joiner.add("Java").add("Spring").add("SQL");
String c = joiner.toString(); // [Java | Spring | SQL]

StringBuilder builder = new StringBuilder();
builder.append("Java").append(" | ").append("Spring").append(" | ").append("SQL");
String d = builder.toString();
~~~

`a`, `b`, and `d` have the same content `Java | Spring | SQL`. `c` differs because square brackets were requested. These four approaches are not equivalent data types: `+` is an operator; `String.join()` returns a `String`; `StringJoiner` and `StringBuilder` are stateful objects used while constructing the result.

## 2. The `+` Operator: Clear for Short Expressions

When **one operand is a `String`**, the `+` operator performs string concatenation. The other operands are converted to their string representations according to Java's string conversion rules. For string constants, the compiler can fold them at compile time (constant folding):

~~~java
String fixed = "Hello" + " " + "Java"; // Constant "Hello Java"
String name = "Lan";
String greeting = "Hello, " + name + "!"; // Concatenated at runtime
~~~

Be careful to distinguish numeric addition from string concatenation, because expressions are evaluated left to right:

~~~java
System.out.println(1 + 2 + " people"); // 3 people
System.out.println("People count: " + 1 + 2); // People count: 12
System.out.println("People count: " + (1 + 2)); // People count: 3
~~~

**Do not conclude that every `+` always creates a separate `StringBuilder` or is always slow.** The compiler and JVM optimize single-expression concatenation; since Java 9, typical concatenation expressions commonly use `invokedynamic` with `StringConcatFactory`. Execution details depend on the compiler and JVM. Therefore, writing `"Hello " + name` is reasonable and readable.

What you should avoid is **updating a growing string inside a loop**:

~~~java
String result = "";
for (String item : items) {
    result += item;
}
~~~

Each update semantically requires a new `String` value to hold the longer result; repeatedly copying the accumulated prefix can cause many allocations and near-quadratic total work as the number or length of elements grows. At sufficiently large scale, `StringBuilder` is more appropriate. This is guidance about usage patterns, not a claim that every `+` performs poorly on every JVM.

In addition, Java converts a `null` value concatenated into a string to the text `"null"` (for example, `"x=" + (Object) null` becomes `x=null`). If you want to skip or replace absent values, handle `null` beforehand.

## 3. `String.join()`: Joining an Element Collection with a Common Delimiter

Common overloads:

~~~java
String.join(CharSequence delimiter, CharSequence... elements)
String.join(CharSequence delimiter, Iterable<? extends CharSequence> elements)
~~~

Examples:

~~~java
String csvLike = String.join(",", "A", "B", "C");
// A,B,C

List<String> paths = List.of("users", "42", "orders");
String path = String.join("/", paths);
// users/42/orders

String empty = String.join(", ", List.<String>of());
// "" (empty string)
~~~

`String.join()` **does not automatically add leading or trailing delimiters** and **does not automatically filter out empty or null elements**. The delimiter is placed only *between* elements:

~~~java
System.out.println(String.join("-", "A", "", "C"));    // A--C
System.out.println(String.join(",", "A", null, "C")); // A,null,C
~~~

Important rules:

- A `null` delimiter causes `NullPointerException`; the array/`Iterable` argument holding the element list must also be a valid reference.
- A `null` **element** is represented by the string `"null"` rather than disappearing automatically.
- A sequence of 0 elements returns `""`. A sequence of one element returns that element's representation with no delimiter.
- The method returns a new `String`; it does not modify the input array or list.
- The name `csvLike` in the example merely describes the comma separator: this is **not a standard CSV writer**, because `String.join()` does not quote or escape commas, quotes, or newlines inside data.

If you need to remove blank/null strings before joining, normalize the input. For example, with a Stream:

~~~java
List<String> raw = Arrays.asList("Java", null, " ", "Spring");
String result = raw.stream()
        .filter(s -> s != null && !s.isBlank())
        .collect(Collectors.joining(", "));
// Java, Spring
~~~

`Collectors.joining()` fits well when data already flows through a `Stream` pipeline (filtering, mapping, sorting). When an array or `List` is already ready, `String.join()` is usually the choice with the least code.

## 4. `StringJoiner`: Adding Elements One by One, Managing Delimiters Automatically

`StringJoiner` lives in `java.util`. It has two constructors:

~~~java
new StringJoiner(delimiter)
new StringJoiner(delimiter, prefix, suffix)
~~~

Example:

~~~java
StringJoiner j = new StringJoiner(", ", "[", "]");
j.add("red");
j.add("green");
j.add("blue");
System.out.println(j); // [red, green, blue]
~~~

`StringJoiner` inserts the delimiter **between `add()` calls**; the caller never has to check whether this is the first element. `add()` returns the joiner itself for chaining. `toString()` builds the resulting string for the current state; subsequent `add()` calls continue to mutate the joiner.

### 4.1. When No Elements Have Been Added and `setEmptyValue()`

With a prefix and suffix, before `add()` is called, the default representation is `prefix + suffix`. You can override it with `setEmptyValue()`:

~~~java
StringJoiner j = new StringJoiner(", ", "[", "]");
System.out.println(j); // []

j.setEmptyValue("(no elements)");
System.out.println(j); // (no elements)

j.add("A");
System.out.println(j); // [A]
~~~

`setEmptyValue()` affects **only the state where no elements have been added yet**. After `add()`, including `add("")`, the joiner is no longer considered empty of elements.

### 4.2. `merge()` When Combining Groups

`merge(other)` appends the element content of `other` as a single group, using the target joiner's delimiter at the boundary. `other`'s prefix/suffix are not inserted into the result:

~~~java
StringJoiner left = new StringJoiner(" | ", "<", ">");
left.add("A").add("B");

StringJoiner right = new StringJoiner(", ", "(", ")");
right.add("C").add("D");

left.merge(right);
System.out.println(left); // <A | B | C, D>
System.out.println(right); // (C, D)
~~~

Inside the source group's content, `", "` is preserved; therefore the output has a comma followed by a space. `merge()` does not clear `right`'s data; the source joiner remains usable.

When using `merge()`, understand that the internal delimiter of the source group and the group-separating delimiter of the target may differ. Do not assume `merge` rewrites every source delimiter into the target delimiter.

### 4.3. Limitations to Remember

- `StringJoiner` focuses on `add()`, delimiter, prefix/suffix, empty value, and merge; it is **not a general-purpose character editor** like `StringBuilder`.
- Calling `add(null)` appends `"null"`; `null` is not removed automatically.
- `length()` returns the length of the current representation (including prefix/suffix if present), not the number of elements added.
- If the task is simply `String.join(", ", list)`, manually constructing a joiner can make the code unnecessarily verbose.

## 5. `StringBuilder`: Controlling Every Step of String Construction

`StringBuilder` lives in `java.lang` and holds a mutable sequence of characters. `append()` has overloads for strings, numbers, booleans, characters, character arrays, and objects. It does not automatically know where to place delimiters:

~~~java
List<String> names = List.of("An", "Bình", "Chi");
StringBuilder sb = new StringBuilder();

for (String name : names) {
    if (sb.length() > 0) {
        sb.append(", ");
    }
    sb.append(name);
}

String output = sb.toString(); // An, Bình, Chi
~~~

The pattern above works when there are no empty elements. If an element can be `""`, using an index or a `first` flag is safer for tracking elements, because `sb.length() == 0` does not necessarily mean "no elements processed yet":

~~~java
StringBuilder sb = new StringBuilder();
boolean first = true;

for (String item : List.of("", "B")) {
    if (!first) {
        sb.append("|");
    }
    sb.append(item);
    first = false;
}
System.out.println(sb); // |B
~~~

In this case `String.join("|", List.of("", "B"))` also returns `"|B"` and is shorter; the `StringBuilder` pattern is useful when each element also needs extra formatting or operations.

Additional operations that `String.join()`/`StringJoiner` do not provide directly:

~~~java
StringBuilder sb = new StringBuilder("abc");
sb.append("de");          // abcde
sb.insert(3, "-");        // abc-de
sb.replace(0, 3, "XYZ");  // XYZ-de
sb.deleteCharAt(3);       // XYZde
sb.reverse();             // edZYX
String result = sb.toString();
~~~

Distinctions:

- `length()` is the current number of characters.
- `capacity()` is the currently allocated buffer capacity for storing characters; it is at least `length()` and can grow automatically.
- `new StringBuilder(estimatedCapacity)` can reduce buffer expansions when a reliable estimate is known. That is a situational optimization, not mandatory.
- `toString()` creates the resulting `String`; call it when the final result is needed rather than repeatedly inside each concatenation iteration.
- `append((String) null)` appends `"null"`; if you want to skip `null`, check beforehand.

`StringBuilder` **does not synchronize operations for sharing a single instance across multiple threads**. Nor should `StringJoiner` be shared and mutated concurrently across threads without safe coordination. `StringBuffer` is an option with synchronized methods, but that alone does not make an entire multi-step assembly an atomic operation; in many cases it is better for each thread to use its own builder.

## 6. Complete Java 17+ Example

Save the program as **`StringJoiningDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collectors;

public class StringJoiningDemo {
    public static void main(String[] args) {
        List<String> tags = List.of("Java", "Spring", "SQL");

        String viaPlus = tags.get(0) + " | "
                + tags.get(1) + " | " + tags.get(2);

        String viaJoin = String.join(" | ", tags);

        StringJoiner joiner = new StringJoiner(" | ", "[", "]");
        for (String tag : tags) {
            joiner.add(tag);
        }
        String viaJoiner = joiner.toString();

        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < tags.size(); i++) {
            if (i > 0) {
                builder.append(" | ");
            }
            builder.append(tags.get(i));
        }
        String viaBuilder = builder.toString();

        System.out.println("plus   : " + viaPlus);
        System.out.println("join   : " + viaJoin);
        System.out.println("joiner : " + viaJoiner);
        System.out.println("builder: " + viaBuilder);

        StringJoiner empty = new StringJoiner(", ", "[", "]");
        empty.setEmptyValue("(empty)");
        System.out.println("empty  : " + empty);

        List<String> raw = Arrays.asList("A", null, "", "B");
        String filtered = raw.stream()
                .filter(s -> s != null && !s.isEmpty())
                .collect(Collectors.joining(", "));
        System.out.println("filter : " + filtered);
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac StringJoiningDemo.java
java StringJoiningDemo
~~~

Output:

~~~text
plus   : Java | Spring | SQL
join   : Java | Spring | SQL
joiner : [Java | Spring | SQL]
builder: Java | Spring | SQL
empty  : (empty)
filter : A, B
~~~

Explanation:

1. `+` joins three elements at known positions; the code becomes inflexible if the list length varies.
2. `String.join()` accepts the `List` directly, inserts `" | "` between items, and adds nothing at either end.
3. `StringJoiner` takes elements one by one while also wrapping the result with `[` and `]`.
4. `StringBuilder` inserts the delimiter when `i > 0`, then converts the buffer to a `String`.
5. `setEmptyValue()` handles a joiner with no items yet; the Stream example explicitly removes `null` and empty strings before joining.

## 7. Comparison by Usage Requirements

| Criterion | `+` operator | `String.join()` | `StringJoiner` | `StringBuilder` |
|---|---|---|---|---|
| API kind | Expression operator | Static method returning `String` | Accumulator object | Mutable character buffer |
| Best for | A few known parts | Array/`Iterable` with a shared delimiter | Incremental additions, prefix/suffix, merge | Loops, complex formatting, character edits |
| Auto-inserts delimiter | No | Yes | Yes | No |
| Automatic prefix/suffix | No | No | Yes | Must write manually |
| Empty-result handling | Depends on expression | `""` when 0 elements | `prefix+suffix` or `setEmptyValue()` | `""` if builder is empty |
| Arbitrary insert/delete/edit | No | No | No | Yes |
| Final output | `String` | `String` | `toString()` | `toString()` |

### 7.1. Performance and Memory Aspects

Suppose there are `n` elements with total character length `L` and a delimiter of length `d`. A good joining algorithm processes roughly `L + (n - 1) × d` output characters (excluding prefix/suffix). Consequently:

- **A single `String.join()` or using `StringJoiner` and calling `toString()`** is usually appropriate for many delimiter-separated elements; it avoids manual first-element checks.
- **A `StringBuilder` reused across a loop** can concatenate linearly in total data size with buffer-expansion cost amortized across many `append()` calls.
- **A single `+` expression** can be optimized well by the JVM; prioritize clarity before optimizing prematurely.
- **`result += piece` in a long loop** is a warning sign worth revisiting because it repeatedly creates intermediate `String` objects. Do not judge purely by counting `+` signs in source code.

Allocation characteristics, actual overhead, and crossover thresholds depend on JDK version, JVM, JIT, data, and code shape. When performance matters, measure with **JMH**, using warm-up and representative data; avoid drawing conclusions from one-off manual timings or printing logs inside the benchmark loop.

### 7.2. Quick Scenario Selection

- Building a message `"Hello, " + userName` → **`+`** because it is short and direct.
- Building a list `a,b,c` from an existing `List<String>` → **`String.join(",", list)`**.
- Building a string like `[a, b, c]` by calling `add()` per item → **`StringJoiner(", ", "[", "]")`**.
- Building a multi-line report with numbers, conditionals, paragraphs, and positional edits → **`StringBuilder`**.
- Joining data after Stream `filter()`/`map()` → **`Collectors.joining(delimiter)`** is usually cleanest.

## 8. Common Mistakes and Misconceptions

**1. Joining two elements with a delimiter by appending the delimiter after every element.**

~~~java
StringBuilder sb = new StringBuilder();
for (String s : List.of("A", "B")) {
    sb.append(s).append(","); // A,B, (extra trailing comma)
}
~~~

If you just need to join a list: `String.join(",", List.of("A", "B"))` returns `A,B`. If using a builder, append the delimiter **before elements from the second onward** or track by index.

**2. Assuming `join()` filters out null/empty values.** In fact, `String.join("-", "A", "", "C")` becomes `A--C`; `String.join("-", "A", null, "C")` becomes `A-null-C`. Decide upfront whether to keep, skip, or replace these values.

**3. Assuming `StringJoiner.setEmptyValue()` still applies after `add("")`.** An empty string is still an added element; the joiner is no longer in the empty state in the API sense.

**4. Confusing `StringBuilder.length()` with element count.** It counts characters; when the first element is an empty string, `length() == 0` still holds. Use a `first` flag or an index to manage delimiters if the data can include empty strings.

**5. Confusing `String.join()` with a structured data-format encoder.** An input `"Ho, Ten"` containing a comma still retains that comma in the output. For CSV, JSON, SQL, or URLs, use an appropriate formatter/encoder/API; specifically, SQL requires parameterized queries rather than concatenating input manually.

**6. Using `+` to accumulate large amounts of data while assuming it is always as fast as a single expression.** Optimizing a single concatenation expression does not mean the JVM eliminates all intermediate `String` objects across `+=` assignments in a loop.

**7. Sharing a mutable `StringBuilder` across multiple threads.** If threads modify the same object without proper synchronization, the contents can become corrupted. Usually, create the buffer scoped to a single method or task.

## 9. Takeaways When Applying

Start from the **input shape** and **output rules**. For a few fixed parts, use `+`. For an existing sequence and a single delimiter, use `String.join()`. For incremental additions needing prefix/suffix, use `StringJoiner`. For complex string construction or repeated edits, use `StringBuilder`. Then explicitly define how to handle `null`, empty strings, escaping, and thread confinement; those factors affect correctness far more than choosing the shortest API.
