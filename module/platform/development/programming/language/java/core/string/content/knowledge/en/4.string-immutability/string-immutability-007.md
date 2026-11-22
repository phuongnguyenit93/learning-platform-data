# Benefits of Immutability When Using `String` as Keys, Sharing Data, and Handling Concurrency

**`String` is a reference type, yet the content of a `String` object cannot change after the object is created.** This is *immutability*. Methods such as `concat()`, `replace()`, `substring()`, `toUpperCase()`, or `trim()` do not modify the current object; they return the resulting `String`, which may be a new object or the original object itself if no content change is needed.

Immutability yields three prominent benefits in Java applications:

1. **Serving as stable keys** in `HashMap`, `HashSet`, caches, and structures based on `equals()`/`hashCode()`.
2. **Predictable data sharing** across methods, components, and threads: the receiver cannot modify the `String` content held by the sender.
3. **Easier concurrent reading and processing**: multiple threads can use the same `String` value without locking solely to protect that value's content.

The third benefit has an **important boundary**: an immutable `String` does not make reference variables, `Map`s, `List`s, or entire objects containing `String`s safe when multiple threads mutate them concurrently.

## 1. Stability Lies in the Text Value Itself

Two variables can hold references to the same `String`; transformation operations return a value to use without changing the content of the already created string. As a result, code holding a key or report will not unexpectedly see characters modified from elsewhere. Variables or fields holding references can still be reassigned, so the scope of this benefit is **the `String` value**, not all mutable state surrounding it.

## 2. Benefits When Using `String` as Keys in `HashMap` and `HashSet`

A `HashMap` key needs stable `equals()` and `hashCode()` behavior while residing in the `Map`. `HashMap` uses `hashCode()` to locate the storage bucket and `equals()` when needed to identify keys with equivalent content. `HashSet` relies on the corresponding principle to store unique elements.

For `String`:

- `equals()` compares **content**, not merely two references.
- Two `String`s with equal content have the same `hashCode()` value.
- A `String`'s content does not change, so an object's `hashCode()` and content-comparison results do not change over time.
- You can create a different `String` with equal content to look up a stored key without keeping the exact same instance.

Illustrative example:

~~~java
import java.util.HashMap;
import java.util.Map;

public class StringKeyDemo {
    public static void main(String[] args) {
        Map<String, Integer> prices = new HashMap<>();
        String savedKey = "item:42";
        prices.put(savedKey, 150);

        String lookupKey = new StringBuilder("item:")
                .append(42)
                .toString();

        System.out.println(savedKey.equals(lookupKey));
        System.out.println(savedKey.hashCode() == lookupKey.hashCode());
        System.out.println(prices.get(lookupKey));

        String updatedKey = savedKey.replace("42", "43");
        System.out.println(savedKey);
        System.out.println(updatedKey);
        System.out.println(prices.get(savedKey));
        System.out.println(prices.get(updatedKey));
    }
}
~~~

Save as **StringKeyDemo.java**, then run on JDK 17+:

~~~bash
javac StringKeyDemo.java
java StringKeyDemo
~~~

Output:

~~~text
true
true
150
item:42
item:43
150
null
~~~

**Explanation:** `lookupKey` has the same content as `savedKey`, so the `Map` finds the value `150`. `replace()` produces a different value `updatedKey`; `savedKey` remains `"item:42"`, so the key placed in the `Map` stays intact. There is no `"item:43"` entry, so the final lookup returns `null`.

### What If a Key Could Be Mutated?

Suppose a custom class uses a mutable `id` field in `equals()` and `hashCode()`; placing an instance into a `HashMap` and modifying `id` afterward can cause lookups using that key or an equivalent key to fail to find the entry as expected. The reason is that the hash value at insertion time may differ from the hash value after mutation.

`String` specifically avoids the risk of **key content being modified after insertion**. However, that does not mean all valid keys must be `String`: any other immutable object with consistent `equals()`/`hashCode()` can also be a good key.

**Do not confuse `StringBuilder` or `StringBuffer` with `String` when used as keys:** those two buffer classes do not override `equals()`/`hashCode()` to compare content like `String`. Printing the same text does not make two builder/buffer objects equivalent keys. If the data used to construct a key is in a `StringBuilder`, finish building it and call `toString()` to create a `String` key.

### What `String` Does Not Automatically Solve as a Key

- **Hash collisions can still happen:** two `String`s with different content can occasionally have the same `hashCode()`; therefore you must rely on `equals()`, never `hashCode()` alone, to prove two strings are equal.
- **Keys are case-sensitive:** `"USER:42"` does not equal `"user:42"` under `String.equals()`. If a system needs case-insensitive keys, normalize according to business rules before storing and looking up; for locale-independent identifiers you can use `toLowerCase(Locale.ROOT)`.
- **Unicode has multiple representations:** some visually identical text can still differ in code-unit sequences; if Unicode normalization is required, establish a consistent normalization step (such as `Normalizer`) on both write and read paths.
- **`HashMap` is not automatically thread-safe:** stable `String` keys do not allow multiple threads to mutate a shared `HashMap` without synchronization. For concurrent updates, use an appropriate mechanism such as `ConcurrentHashMap`, locks, or a read-only policy after construction.

## 3. Benefits When Sharing Data Between Methods and Components

A `String` can be passed as a parameter, returned from a method, stored in an object, or handed to another component without worrying that the receiver will edit **the content of that `String` object itself**. Reasoning about a created value therefore becomes simpler: operations that alter text produce a new value rather than silently mutating data still in use elsewhere.

The following example does not change the caller's value:

~~~java
public class ShareStringDemo {
    static String addSuffix(String input) {
        return input.concat("-done");
    }

    public static void main(String[] args) {
        String original = "task";
        String next = addSuffix(original);

        System.out.println(original); // task
        System.out.println(next);     // task-done
    }
}
~~~

Save as **ShareStringDemo.java**, run with `javac ShareStringDemo.java` and `java ShareStringDemo`. The two printed lines are `task` and `task-done`. Passing a reference to `String` into the method does not give the method any ability to modify the original value.

### Creating a Content Snapshot from a Mutable Buffer

A program can build a string with `StringBuilder` and publish the resulting `String` elsewhere. Once exported, subsequent changes to the builder do not affect the created `String`:

~~~java
StringBuilder draft = new StringBuilder("version 1");
String published = draft.toString();

draft.replace(0, draft.length(), "version 2");

System.out.println(published); // version 1
System.out.println(draft);     // version 2
~~~

A common pattern is **building data locally with `StringBuilder`, converting to `String` when finished, and then sharing the `String`**. For large text payloads, memory and copy costs still matter; immutability gives state clarity rather than guaranteeing every string-building pattern is the fastest.

### Boundaries of Immutability

A class with a `String` field is not necessarily immutable if that object has setters or other mutable fields. For example:

~~~java
class Config {
    String name;

    void changeName(String next) {
        name = next;
    }
}
~~~

The `String` referenced by `name` cannot have its content modified; however, the `name` field of the `Config` object can still be replaced. If `Config` is shared among multiple threads and `name` is updated, concurrent access rules for **the `name` field** must be handled.

Similarly, `List<String>` or `Map<String, String>` are still mutable collections if a mutable implementation is chosen. Immutability of elements/keys/values does not automatically protect add, remove, or replace operations on the collection.

## 4. Benefits in Concurrent Processing

Distinguish two kinds of state:

- **Content of a `String`:** no operation modifies the content of an already created object. Multiple threads can read and use the same `String` without locking merely to prevent its content from being altered.
- **References and structures holding `String`s:** these can still be updated. Operations on shared state such as replacing a field, adding elements to a `List`/`Map`, or check-then-act updates require appropriate concurrency mechanisms.

### Example: Multiple Threads Reading One `String`

The following program has two threads read the same `String` value and produce **separate results**. Neither thread can alter the content of `shared`.

~~~java
import java.util.Locale;

public class SharedStringThreadsDemo {
    public static void main(String[] args) throws InterruptedException {
        String shared = "Java";
        String[] outputs = new String[2];

        Thread upper = new Thread(
                () -> outputs[0] = shared.toUpperCase(Locale.ROOT));
        Thread suffix = new Thread(
                () -> outputs[1] = shared.concat(" 17"));

        upper.start();
        suffix.start();

        upper.join();
        suffix.join();

        System.out.println("shared=" + shared);
        System.out.println("upper=" + outputs[0]);
        System.out.println("suffix=" + outputs[1]);
    }
}
~~~

Save as **SharedStringThreadsDemo.java**, run:

~~~bash
javac SharedStringThreadsDemo.java
java SharedStringThreadsDemo
~~~

Output:

~~~text
shared=Java
upper=JAVA
suffix=Java 17
~~~

**Why is this right?** `shared` stays intact; the two methods produce separate `String` results. Each thread writes to a different element of the `outputs` array, so they do not contend for the same slot. `main` calls `join()` before reading results, establishing a *happens-before* relationship from the actions inside the completed threads to actions after `join()` in `main`. The example does not prove all accesses to any array are thread-safe: this design works because threads write to distinct elements and `main` waits for completion.

There is no need to use `synchronized` to protect **the content of `shared`**, yet coordination mechanisms are still needed when other state is modified concurrently. That is the direct benefit of immutable data: the scope that must be guarded by locks shrinks.

### Limits When Multiple Threads Update State

The example above is safe because each thread writes to a separate result slot, and then `main` calls `join()` before reading. That is explicit thread coordination; immutable `String` content only prevents threads from modifying the same `shared` text.

If threads concurrently modify a `String` **reference field** or concurrently write to a `Map` or `List`, you still must choose suitable publication, synchronization, and update mechanisms. `volatile String` can guarantee visibility for the field, but does not make `status = status + suffix` atomic. When both updates must be preserved, consider `synchronized`, `AtomicReference.updateAndGet`, or an appropriate concurrent collection API. The chapter's lesson on thread-safety boundaries explains this with lost-update and `happens-before` examples.

## 5. Scenario Exercise: Cache Keys and Published Data

Suppose an application generates status labels for multiple jobs:

1. Each task receives a job ID as a `String`, such as `"job:17"`.
2. A `Map` stores results by job ID; lookups use `String`s with equal content to identify the same key.
3. Report content is built over multiple `append` calls on the task's **own** `StringBuilder`.
4. When done, the task calls `toString()` and passes the resulting `String` to the aggregation step.
5. If multiple threads must concurrently update the `Map`, use a concurrency mechanism such as `ConcurrentHashMap` or appropriate locking; if the `Map` is built in a single thread and then published for reading, ensure publication is properly synchronized.

The advantage of this design is that readers of the `Map` never have to worry about a `String` key suddenly changing content. Readers of the results also never see a published report `String` mutate along with a task's internal builder. The remaining concerns lie in **ownership and synchronization of the `Map`**, not in the `String` content.

If business logic requires case-insensitive keys or a normalization step, transform the data **before placing it in the `Map`** and apply that exact same rule to every lookup. For example, if choosing lowercase for machine identifiers, use a consistent normalization such as `id.toLowerCase(Locale.ROOT)`. Immutability only guarantees a key does not change **after creation**; it does not decide which two text forms should be treated as equivalent.

## 6. Takeaways and Self-Check

**Reasoning chains to remember:**

- **Immutable `String` → stable content → stable `equals()`/`hashCode()` → ideal for keys.**
- **Immutable `String` → receivers cannot alter original content → safe value sharing and fewer aliasing bugs.**
- **Immutable `String` → multiple threads read the same content without locks to prevent mutation → helpful for concurrency.**
- **Immutable `String` ≠ containing data is automatically thread-safe:** updating references, collections, or multi-step workflows still requires coordination.

Answer these questions yourself before applying this:

1. If you call `name.replace("A", "B")` without saving the result, does the variable `name` change?
2. Why can `HashMap` look up an entry using a different `String` instance that has the same content as the original key?
3. If one thread updates a `String` field `status` and another thread reads it, is `String` immutability alone enough to guarantee seeing the new update?
4. If two tasks both build reports, why should each task keep its own `StringBuilder` and publish a `String` instead of mutating one shared `StringBuilder`?
5. Is a `Map<String, Integer>` safe when multiple threads call `put()` concurrently just because its keys are `String`?

**Short answers:** (1) No, `replace()` returns a value. (2) Because `String.equals()` compares content and two equal values have the same `hashCode()`. (3) No, proper synchronization/publication relationships are still required. (4) To avoid sharing a mutable buffer and to produce stable output results. (5) No, the `Map` structure itself needs a suitable concurrent access mechanism.

**Conclusion:** `String` immutability delivers stable keys, value sharing without fear of content mutation, and safer multi-threaded reuse of the same text data. That safety applies to **`String` content**; variables and mutable structures around it still require their own concurrency design.
