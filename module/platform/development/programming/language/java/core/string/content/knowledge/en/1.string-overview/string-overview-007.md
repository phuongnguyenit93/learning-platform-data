# Choosing String, StringBuilder, or StringBuffer Based on Your Needs

In Java, all three types relate to character strings, but they differ in **content mutability**, **cost during repeated concatenation**, and **synchronization under multiple threads**. Choosing the right type should be based on data lifecycle and actual usage.

## 1. Quick comparison table

| Criterion | String | StringBuilder | StringBuffer |
|---|---|---|---|
| Is object content mutable? | No (immutable) | Yes (mutable) | Yes (mutable) |
| Common concatenation | +, concat(), formatted() | append(), insert() | append(), insert() |
| In-place modification | No | Yes | Yes |
| Guarantees when multiple threads modify one object | No content-modification operations; immutable values can be shared | Not synchronized | Main manipulation methods are synchronized |
| Suitable use case | Complete text values, few concatenations | Repeatedly building text in a single thread | Truly needing to modify one buffer from multiple threads where per-method synchronization meets requirements |

Practical rule: **String for ordinary values, StringBuilder for multi-step assembly, StringBuffer when you genuinely need a synchronized mutable buffer**. A multi-threaded application can still use StringBuilder if each thread owns its own separate instance.

## 2. String: immutable data

String is immutable: after creation, the content of a **String object** does not change. concat(), replace(), substring(), and toUpperCase() return String values; they do not modify the original object. A variable can point to a different string, but that is changing the reference.

~~~java
String original = "Java";
String extended = original.concat(" 17");

System.out.println(original); // Java
System.out.println(extended); // Java 17
~~~

Calling original.concat(" 17") and ignoring the result will not give original an extra " 17". To update the variable, use original = original.concat(" 17") or create a new variable.

Immutability makes sharing **String content** across threads safe. However, if threads concurrently read and write a String reference field or an enclosing structure, Java's visibility and synchronization rules still apply; immutability does not automatically make the whole program thread-safe.

Choose String when:

- Representing names, identifiers, messages, or values passed between methods.
- Joining a few parts with a clear expression such as "Hello, " + name.
- Returning a finalized value and wanting to ensure the object's content cannot be modified afterward.
- Comparing content with equals(), equalsIgnoreCase(), or an appropriate method.

**Do not conclude that every + operation has poor performance.** Modern compilers and JVMs optimize concatenations within a single expression. Since Java 9, concatenation calls are often compiled using invokedynamic; specific optimizations depend on the version and context. A short concatenation expression is usually easier to read than manually creating a buffer.

What to avoid is **repeatedly accumulating a String** while building a long result: each step creating a new String value may need to copy the accumulated content. For large strings or many loop iterations, consider StringBuilder.

## 3. StringBuilder: assembling text across multiple steps

StringBuilder has a mutable buffer. append(), insert(), delete(), replace(), and reverse() change the state of the same object, helping reduce intermediate String allocations when adding many pieces.

~~~java
StringBuilder builder = new StringBuilder("Java");
builder.append(" ").append(17);
builder.insert(4, " Core");
System.out.println(builder); // Java Core 17
~~~

toString() creates a **stable result String**. If builder is modified afterward, the String already obtained from toString() does not change.

~~~java
String snapshot = builder.toString();
builder.append("!");
System.out.println(snapshot); // Java Core 17
System.out.println(builder);  // Java Core 17!
~~~

When building a delimited string across multiple iterations, place the builder **outside** the loop:

~~~java
StringBuilder line = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) {
        line.append(", ");
    }
    line.append(i);
}
System.out.println(line.toString()); // 1, 2, 3
~~~

Reusing a single buffer is generally preferable to executing result = result + fragment across many loop iterations. Performance conclusions should rest on actual workloads: data size, JIT optimizations, and implementation details can cause results to vary.

**length() and capacity():** length() is the length of current content in UTF-16 code units; capacity() is the allocated buffer capacity in the same units, which can be larger than length(). When size can be estimated, new StringBuilder(expectedCapacity) can reduce buffer reallocations; you do not need to use it in every case. A Unicode character outside the BMP can occupy two UTF-16 code units, so length() does not necessarily equal the number of visible characters.

StringBuilder **does not synchronize** its operations. If multiple threads modify one instance concurrently without coordination, results can be corrupted. Using a local builder per thread/task is a common way to avoid sharing mutable state.

## 4. StringBuffer: a buffer with method-level synchronization

StringBuffer also provides append(), insert(), delete(), replace(), and toString(), but its main manipulation methods are synchronized on the object. Thus, individual append() calls to the same StringBuffer do not step on each other the way unprotected concurrent edits to StringBuilder would.

~~~java
StringBuffer buffer = new StringBuffer("Log");
buffer.append(": ").append("ready");
System.out.println(buffer); // Log: ready
~~~

Standalone runnable example with two threads appending to one buffer:

~~~java
public class SharedBufferDemo {
    public static void main(String[] args) throws InterruptedException {
        StringBuffer shared = new StringBuffer();

        Runnable task = () -> {
            for (int i = 0; i < 1_000; i++) {
                shared.append("x");
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();

        first.join();
        second.join();
        System.out.println(shared.length());
    }
}
~~~

Save as **SharedBufferDemo.java**, compile, and run with JDK 17+:

~~~bash
javac SharedBufferDemo.java
java SharedBufferDemo
~~~

Output:

~~~text
2000
~~~

Each thread adds 1,000 "x" characters; join() ensures both finish before reading the length. The interleaving order between threads is unspecified, but the final length is 2,000 in this example.

**Warning on atomicity:** A synchronized method protects only **a single method call**. If the task requires checking a condition and then appending a character as a single atomic operation, the following snippet is not atomic when multiple threads run it concurrently:

~~~java
if (shared.length() < 2_000) {
    shared.append("x");
}
~~~

Both length() and append() are synchronized individually, yet another thread can interleave between them. When atomicity across the whole sequence is mandatory, synchronize on the same monitor:

~~~java
synchronized (shared) {
    if (shared.length() < 2_000) {
        shared.append("x");
    }
}
~~~

Other places enforcing the same check-and-update rule must coordinate on the same lock. For complex multi-step workflows, consider reducing or eliminating buffer sharing rather than assuming StringBuffer solves all concurrency issues.

**Do not choose StringBuffer just because an application is multi-threaded.** If data is constructed locally within each task, StringBuilder avoids synchronization overhead; if complex aggregated output is needed from multiple threads, you can produce local results and merge them in a coordinated step.

## 5. Complete comparison program (Java 17+)

This example is independent of SharedBufferDemo above. Save as **StringChoiceDemo.java**:

~~~java
public class StringChoiceDemo {
    public static void main(String[] args) {
        String original = "Java";
        String changed = original.concat(" 17");
        System.out.println("original=" + original);
        System.out.println("changed=" + changed);

        StringBuilder builder = new StringBuilder("Java");
        builder.append(" ").append(17);
        System.out.println("builder=" + builder);
        builder.insert(4, " Core");

        String snapshot = builder.toString();
        builder.append("!");
        System.out.println("snapshot=" + snapshot);
        System.out.println("builder now=" + builder);
        System.out.println("content equals="
                + snapshot.equals("Java Core 17"));

        StringBuffer buffer = new StringBuffer("A");
        buffer.append("B").append("C");
        System.out.println("buffer=" + buffer);

        StringBuilder numbers = new StringBuilder();
        for (int i = 1; i <= 3; i++) {
            if (i > 1) {
                numbers.append(", ");
            }
            numbers.append(i);
        }
        System.out.println("joined=" + numbers);
    }
}
~~~

~~~bash
javac StringChoiceDemo.java
java StringChoiceDemo
~~~

Exact output:

~~~text
original=Java
changed=Java 17
builder=Java 17
snapshot=Java Core 17
builder now=Java Core 17!
content equals=true
buffer=ABC
joined=1, 2, 3
~~~

original stays unchanged after concat(); builder changes in place via append()/insert(); snapshot retains a separate String value after builder is modified further; buffer illustrates StringBuffer's API. This second example only demonstrates StringBuffer operations, whereas SharedBufferDemo illustrates sharing across multiple threads.

## 6. Applying by scenario

| Need | Good starting point | Reason |
|---|---|---|
| Build a "Hello, " + name message once | String | Simple, readable |
| Store/exchange finalized text values | String | Immutable content |
| Join thousands of fields in a single thread | StringBuilder | Reuses one buffer across many appends |
| Each parallel task builds its own report section | Separate StringBuilder per task | No shared mutable state |
| Multiple threads append to the same buffer | StringBuffer, if sharing is genuinely needed | Synchronizes each append call |
| Check then update the same buffer from multiple threads | Lock wrapping the entire group of operations or another design | Per-method synchronization is not enough |
| Join words with commas | String.join() or StringJoiner | Directly expresses the delimiter |
| Build JSON/SQL/HTML with escaping or parameters | Appropriate specialized API | Handles structure, special characters, or parameters more safely than manual concatenation |

Example of joining with a delimiter when you already have finalized strings:

~~~java
String names = String.join(", ", "Lan", "Minh", "An");
System.out.println(names); // Lan, Minh, An
~~~

If data is in a stream, Collectors.joining(", ") also clearly expresses the need to join elements. You do not have to manage delimiters manually with StringBuilder for simple cases.

## 7. Common mistakes

1. **Forgetting to capture String's return value.** s.replace("a", "o") does not modify s. Assign s = s.replace("a", "o") or use the new value.
2. **Using + to accumulate inside a large loop.** Use a StringBuilder created outside the loop when assembling many parts.
3. **Believing every + is slow.** Concatenation within a single expression is optimized by the JVM depending on version/context; do not complicate code unnecessarily.
4. **Choosing StringBuffer for a single-threaded builder.** Unnecessary synchronization can add overhead.
5. **Assuming StringBuffer guarantees atomicity across consecutive method calls.** Check-then-act or coordinated sequences require an enclosing lock.
6. **Comparing StringBuilder with equals() like String.** StringBuilder does not override equals() for String-like content comparison; you can use a.toString().equals(b.toString()).
7. **Confusing StringBuilder/StringBuffer with String.** They implement CharSequence, but an API requiring an explicit String needs toString().
8. **Confusing capacity() with length().** Reserved capacity differs from the number of UTF-16 units currently used.
9. **Passing the same StringBuilder to multiple threads without coordination.** Keep it local per task or design appropriate synchronization.
10. **Benchmarking with a short loop.** Warm-up, JIT, GC, and dead-code elimination skew measurements. If optimization is a real goal, use JMH with a meaningful workload whose result is consumed.

## 8. Simple decision tree

1. Is the text already finalized or only joining a few parts? **Use String**.
2. Do you need to append/insert/delete repeatedly to build a result? **Use StringBuilder**.
3. Is the buffer genuinely modified by multiple threads concurrently? **Consider StringBuffer** or a design that reduces shared mutable state.
4. Must multiple steps execute as one atomic operation? **Design a lock wrapping all steps**; StringBuffer alone is insufficient.
5. Finished building and need to return stable data? **Call toString()** to obtain a String.

Key takeaway: **String is an immutable value; StringBuilder is the default string-building buffer; StringBuffer is a buffer with per-method synchronization**. Choose based on usage and sharing scope, not merely on API names or performance assumptions.