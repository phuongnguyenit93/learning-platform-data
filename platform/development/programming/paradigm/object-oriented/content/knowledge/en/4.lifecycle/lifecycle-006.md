# Object Lifetime, Reachability, and Memory Reclamation in Java

In Java, objects are created while the program runs and are usually stored in JVM-managed memory. Java has a **garbage collector (GC)** that reclaims memory from objects no longer considered usable by the program according to *reachability*.

However, three issues must be distinguished:

1. **Lifetime:** When is an object created, when can the program still use it, and when can its memory actually be reclaimed?
2. **Reachability:** Is there still a reference path to the object from the starting points that the GC considers in use?
3. **Memory and resource reclamation:** JVM object-memory reclamation differs from an application's responsibility to close files, network connections, database connections, or operating-system resources.

An assignment such as `obj = null` **does not delete an object**. Returning from a method also does not guarantee that GC runs immediately. Conversely, an object that seems “finished” may remain in memory for a long time if something else still holds a strong reference.

## 1. Distinguishing Key Concepts

| Concept | Meaning | Example |
|---|---|---|
| **Object creation** | Creating an instance, usually with `new` or another mechanism provided by an API | `new Book("Java")` |
| **Reference** | A value that lets Java code access an object | `Book current = book;` |
| **Variable scope** | The source-code region where a variable name can be used under language rules | A local variable can be named only inside its declaring block |
| **Reachability** | Whether a reference path leads from GC roots to an object | A singleton field still holds a `Book` |
| **Eligibility for collection** | The GC no longer considers the object reachable under the applicable processing model | After removing the last strong reference |
| **Memory reclamation** | The JVM/GC actually reuses or releases the memory occupied by an object | Ordinary Java code cannot select the exact moment |
| **Resource closure** | Ending ownership of a file/socket/connection according to its API contract | `close()` or `try-with-resources` |

The following three statements **are not equivalent**:

- “The variable `x` has gone out of scope.”
- “The object formerly referenced by `x` is now unreachable.”
- “The GC has reclaimed that object's memory.”

These can happen at three different times.

## 2. Creating Objects and Keeping References

For example:

~~~java
class Book {
    final String title;

    Book(String title) {
        this.title = title;
    }
}

Book a = new Book("Java");
Book b = a;
a = null;

System.out.println(b.title); // Java
~~~

Initially, `a` refers to a `Book`. The assignment `b = a` copies the **reference value**, so both variables refer to *one* object. After `a = null`, only `a` stops referring to it; `b` remains usable.

~~~mermaid
flowchart LR
    A["a"] --> N["null"]
    B["b"] --> O["Book object<br/>title = Java"]
~~~

Java **passes parameters by value**. When a reference variable is passed to a method, Java copies the reference value. The method can modify the referenced object's state, but reassigning the local parameter does not change the caller's reference variable.

~~~java
static void clearLocalReference(Book book) {
    book = null; // Chỉ gán lại tham số cục bộ.
}

Book myBook = new Book("OOP");
clearLocalReference(myBook);
System.out.println(myBook.title); // OOP
~~~

The snippet illustrates a method defined inside an appropriate Java class. The object is not deleted when the `book` parameter is set to `null`.

## 3. Complete Example: Object Lifetime Through References

The program below uses a static list to demonstrate how a reference can keep an object reachable and then how removing that reference path affects reachability. The initial output is deterministic; the example **does not try to force GC to run**.

Save it as **`Demo.java`** and run with Java 17 or later:

~~~java
import java.util.ArrayList;
import java.util.List;

public class Demo {
    // Registry tồn tại cùng với lớp Demo khi lớp còn được nạp.
    private static final List<Document> registry = new ArrayList<>();

    public static void main(String[] args) {
        Document original = new Document("Hợp đồng số 1");
        Document alias = original;

        System.out.println(original == alias); // true

        original = null;
        System.out.println(alias.title()); // Hợp đồng số 1

        // Registry tiếp tục giữ tham chiếu mạnh đến Document.
        registry.add(alias);
        alias = null;

        System.out.println(registry.size()); // 1
        System.out.println(registry.get(0).title()); // Hợp đồng số 1

        // Bỏ đường tham chiếu từ registry tới Document.
        registry.clear();
        System.out.println(registry.size()); // 0

        // Từ đây không có lời hứa GC sẽ chạy hay object biến mất ngay.
    }

    private static final class Document {
        private final String title;

        private Document(String title) {
            this.title = title;
        }

        String title() {
            return title;
        }
    }
}
~~~

Execute:

~~~bash
javac Demo.java
java Demo
~~~

Output:

~~~text
true
Hợp đồng số 1
1
Hợp đồng số 1
0
~~~

**Explanation:**

1. `new Document(...)` creates a `Document` object.
2. `alias = original` adds another reference variable to the same object; it does not create a new one.
3. `original = null` removes just one reference path. `alias` is still usable.
4. `registry.add(alias)` makes the static list hold a strong reference to the object.
5. `alias = null` does not make the object eligible for collection because the list still holds it.
6. `registry.clear()` removes the list's reference path. If no other strong path makes the object reachable, it may become eligible for collection. This **does not** mean the GC has actually reclaimed its memory at that statement.

Diagram before and after clearing the registry:

~~~mermaid
flowchart TB
    subgraph before["Trước registry.clear()"]
        R1["GC root: lớp đang được sử dụng"] --> S1["Demo.registry"]
        S1 --> L1["List"]
        L1 --> D1["Document<br/>Hợp đồng số 1"]
    end
    subgraph after["Sau registry.clear()"]
        R2["GC root: lớp đang được sử dụng"] --> S2["Demo.registry"]
        S2 --> L2["List rỗng"]
        D2["Document từng được giữ<br/>không còn cạnh từ List"]
    end
~~~

The diagram shows **logical reference relationships**. JVMs and JIT/GC algorithms can organize memory and optimize code differently; the diagram does not establish an object's physical location in RAM.

## 4. Variable Scope Is Not Object Lifetime

A local variable has block scope. But an object it once referenced may remain alive if a field, collection element, or another object still holds a reference.

~~~java
import java.util.ArrayList;
import java.util.List;

class Notebook {
    String title;

    Notebook(String title) {
        this.title = title;
    }
}

class NotebookStore {
    private final List<Notebook> books = new ArrayList<>();

    void addExample() {
        Notebook local = new Notebook("Ghi chú");
        books.add(local);
    } // Tên biến local ra khỏi scope.

    int count() {
        return books.size();
    }
}
~~~

After `addExample()` returns, the name `local` is no longer in use, but `books` may still hold the `Notebook`. If `NotebookStore` remains reachable, the `Notebook` object in the list can remain reachable as well.

The reverse also matters: a variable being in scope at the source-code level **does not guarantee** that the GC must keep its object alive until the block ends if the JVM can prove the object is no longer used. JIT and GC optimizations can shorten reference liveness according to actual use.

For ordinary Java code, reason about the reference paths the program truly needs, without relying on a particular collection time. Libraries managing off-heap resources that require a reference to stay live through a precise point can use the specialized `Reference.reachabilityFence(obj)` method; it is not a replacement for `close()`.

## 5. GC Roots and the Reachability Graph

The JVM uses starting points (*GC roots*) to discover objects currently in use. Exact root categories depend on the JVM and collection mechanism, but typically involve:

- Live references in executing Java threads, such as objects held by required local variables or parameters.
- References in static fields of appropriately loaded and retained classes.
- References held through JNI or runtime/native mechanisms.
- Other runtime structures that the JVM treats as roots.

From these roots, the GC traverses reference fields, array elements, and object relationships to identify reachable objects.

~~~mermaid
flowchart LR
    R1["GC root<br/>Luồng đang chạy"] --> A["Service"]
    R2["GC root<br/>Static field"] --> B["Cache"]
    A --> C["Order"]
    C --> D["Customer"]
    B --> E["Report"]
    X["Temporary X"] --> Y["Temporary Y"]
    Y --> X
~~~

In the diagram, `Service`, `Cache`, `Order`, `Customer`, and `Report` have paths from a root. `Temporary X` and `Temporary Y` refer to each other but **have no path from a root**, so the GC may collect them.

**A reference cycle does not automatically cause a memory leak in Java.** Modern JVM collectors primarily use reachability; unlike simple reference-counting systems, they do not require programmers to break every cycle.

### What Is a Strong Reference?

The ordinary reference you use when writing:

~~~java
Order order = new Order();
List<Order> orders = new ArrayList<>();
orders.add(order);
~~~

This is a **strong reference**. The list continues to hold a strong reference to `order`. If the list is reachable from GC roots, the `Order` object is retained.

The `Order` class here is only illustrative and is assumed to be defined in the surrounding context.

An object stops being *strongly reachable* when no appropriate strong-reference path from a root remains. Other reachability levels exist when using `java.lang.ref`, as discussed below.

## 6. What Does “Collected by the GC” Mean, and When Does It Happen?

A high-level lifecycle can be represented as follows:

~~~mermaid
stateDiagram-v2
    [*] --> Allocated: Tạo đối tượng
    Allocated --> StronglyReachable: Có đường strong reference từ roots
    StronglyReachable --> StronglyReachable: Còn được giữ / sử dụng
    StronglyReachable --> NotStronglyReachable: Mất đường strong reference cuối
    NotStronglyReachable --> Reclaimed: GC có thể xử lý, thu hồi
~~~

This diagram simplifies strong-reference reachability. In reality, objects can become strongly reachable again, weak/soft/phantom references may exist, and the GC applies state-dependent processing steps. Do not treat this as a complete garbage collector state machine.

Three key points:

**First:** becoming unreachable does not automatically trigger memory deallocation on the next Java line. The JVM decides when and how to run GC.

**Second:** reclaimed JVM heap memory may be **reused for new objects**. The JVM is not obligated to return that RAM immediately to the operating system.

**Third:** the GC manages object memory; it does not guarantee timely closing of every resource outside the heap.

You may encounter:

~~~java
System.gc();
~~~

This is a **request or hint** for the JVM to consider collecting garbage, not a guarantee that collection has finished or that every eligible object has been reclaimed. Some JVM configurations may ignore the request. Do not write business logic or tests whose correctness depends on `System.gc()`.

## 7. Reference Types: Strong, Soft, Weak, and Phantom

The `java.lang.ref` package supports specialized reachability mechanisms.

| Type | How it is created/represented | Purpose | Considerations |
|---|---|---|---|
| **Strong reference** | Ordinary variable/field/collection reference | Keeps an object ordinarily usable | If strongly reachable from a root, the GC does not reclaim it as garbage |
| **Soft reference** | `SoftReference<T>` | Allows the JVM to reclaim an object under memory pressure; historically used for memory-sensitive caches | Collection timing is not guaranteed; prefer explicit cache policies in most cases |
| **Weak reference** | `WeakReference<T>` | Does not keep an object alive solely through the weak reference | `get()` may become `null` after GC processing |
| **Phantom reference** | `PhantomReference<T>` with `ReferenceQueue` | Tracks a later stage of handling objects no longer usable, for specialized resource management | `get()` always returns `null`; queue and cleanup must be designed correctly |

Ordinary strong references are the most important kind in everyday OOP code. Weak, soft, and phantom references are **advanced tools**; do not add them merely to “optimize memory automatically.”

### WeakReference Example without a Guaranteed GC Schedule

~~~java
import java.lang.ref.WeakReference;

class Payload {
    final String value = "data";
}

class WeakDemo {
    public static void main(String[] args) {
        Payload strong = new Payload();
        WeakReference<Payload> weak = new WeakReference<>(strong);

        System.out.println(weak.get() != null); // true tại đây:
                                                 // strong còn dùng được.

        strong = null; // Bỏ tham chiếu mạnh do biến strong giữ.

        Payload observed = weak.get();
        if (observed == null) {
            System.out.println("Đối tượng đã bị GC làm rỗng weak reference");
        } else {
            System.out.println(observed.value);
        }
    }
}
~~~

After `strong = null`, the program **cannot predict** which branch runs: that depends on when the GC runs and how the JVM determines the object's liveness. If `weak.get()` returns a non-`null` reference, the `observed` variable temporarily holds a strong reference and can use the value.

**Do not** write a test that expects `weak.get() == null` immediately after `strong = null`.

### What Is ReferenceQueue Used For?

A `ReferenceQueue<T>` lets management code detect when the GC enqueues a corresponding reference according to the rules of that reference type.

~~~java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

class QueueDemo {
    static final class Session {}

    public static void main(String[] args) {
        ReferenceQueue<Session> queue = new ReferenceQueue<>();
        Session session = new Session();
        WeakReference<Session> weak =
                new WeakReference<>(session, queue);

        session = null;

        // Không được dựa vào việc queue đã có phần tử ngay lúc này.
        Reference<? extends Session> event = queue.poll();
        System.out.println("Có sự kiện đã enqueue: " + (event != null));

        // Giữ biến weak ở đây để minh họa đối tượng Reference.
        System.out.println("Tham chiếu weak còn được giữ: " + (weak != null));
    }
}
~~~

The first output line **is nondeterministic**. Real applications need an appropriate queue-processing loop and lifecycle; this example only shows the API and why GC timing cannot be assumed.

### WeakHashMap Is Not a “Leak-Proof Map”

`WeakHashMap<K,V>` holds keys weakly. When no other strong reference to a key remains, its entry may be removed after GC processing. However:

- It is not a cache with TTL, size limits, or deterministic eviction.
- If a *value* holds a strong reference back to its own *key*, that key may remain reachable through the map and value, defeating entry cleanup.
- Do not rely on it for scheduled record removal or for solving every memory leak.

## 8. A Java Object Can Be Closed Yet Remain Alive

**Reachable/unreachable** describes whether the GC can find an object from its roots. **Open/closed** describes the lifecycle of an external resource that the object may represent. These states are independent:

| Example | Is the object still reachable? | Is the resource open? |
|---|---|---|
| `BufferedReader` in use within `try` | Yes | Usually yes |
| `BufferedReader` already `close()`d while a variable still holds its reference | Possibly | Closure requested according to the contract |
| Code drops all references to a reader without closing it | Possibly not | Timely closure is not guaranteed |

When the method itself opens and owns the reader, use:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
} // Java gọi close() khi rời try.
~~~

This snippet requires imports of `java.io.BufferedReader` and `java.nio.file.Files` and a valid `Path path`. `try-with-resources` guarantees that `close()` is invoked when the block exits through ordinary Java control flow, including exceptions; it does not mean the GC reclaims the object at the closing brace. For errors from `close()`, nested resources, `AutoCloseable`, `finalize()`, and ownership, see *Resource cleanup and the limits of finalizers*.

## 9. When Can Memory Leaks Still Happen in Java?

In Java, a *memory leak* need not mean “lost address of an allocated block” as in manually managed memory. It usually means **an object no longer useful to the application remains strongly referenced from a root**, preventing the GC from reclaiming it.

Common cases:

| Reference holder | Situation | Consequence | Mitigation |
|---|---|---|---|
| Static collection | Every session is added to a `static List` and never removed | Memory grows with requests | Remove expired entries, bound caches, define ownership |
| Unbounded cache | A `Map<Id, Value>` retains every result indefinitely | Uncontrolled heap growth | Use cache size limits, TTL, and eviction |
| Event listener | A listener is registered but never unregistered | Publisher retains subscriber | Call `unsubscribe` at the correct lifecycle point |
| Scheduled task | A task's closure references an object no longer needed | Object remains retained longer than expected | Cancel tasks; close executors according to ownership |
| ThreadLocal | Value stays on a long-running thread without proper cleanup | Stale data survives across many tasks | Call `remove()` in `finally` |
| Collection / queue | Processed elements are never removed | Elements remain reachable | Use `remove()` or `clear()` when appropriate |
| Object graph | A root retains a large object and all its children | Many objects remain indirectly retained | Review reference edges and root lifetime |

### Example: Memory Growth from an Unbounded Cache

~~~java
import java.util.ArrayList;
import java.util.List;

class BadHistory {
    private static final List<byte[]> ALL_REQUESTS = new ArrayList<>();

    static void record(byte[] data) {
        ALL_REQUESTS.add(data); // Không có chính sách loại bỏ.
    }
}
~~~

If `record` is called repeatedly with large arrays, `ALL_REQUESTS` retains all arrays through strong references. The GC cannot determine which entries have “no remaining business value.”

One approach is to use **bounded** storage with an eviction mechanism:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

class RecentMessages {
    private static final int MAX_SIZE = 100;
    private final Deque<String> messages = new ArrayDeque<>();

    public void add(String message) {
        if (message == null) {
            throw new IllegalArgumentException("message không được null");
        }
        if (messages.size() == MAX_SIZE) {
            messages.removeFirst();
        }
        messages.addLast(message);
    }

    public int size() {
        return messages.size();
    }
}
~~~

The memory used by this bounded structure still depends on input string sizes, because `MAX_SIZE` limits only the **number of entries**, not total bytes. For a memory quota, bound both the size of each entry and the overall budget.

### Example: ThreadLocal in a Thread Pool

~~~java
private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

static void handleRequest(String userId) {
    CURRENT_USER.set(userId);
    try {
        // Xử lý request với thông tin người dùng hiện tại.
        System.out.println(CURRENT_USER.get());
    } finally {
        CURRENT_USER.remove();
    }
}
~~~

This snippet belongs inside a suitable class. In a thread pool, a thread may be reused for a later request. Calling `remove()` in `finally` helps prevent stale context from being retained or leaked across requests. If asynchronous processing moves to another thread, use an appropriate context-propagation mechanism; ThreadLocal values do not move automatically.

## 10. Do Mutually Referencing Objects Remain Alive Forever?

Not necessarily. Consider:

~~~java
class Node {
    Node next;
}

Node first = new Node();
Node second = new Node();
first.next = second;
second.next = first;

first = null;
second = null;
~~~

The two `Node` objects form a cycle. If neither is reachable from any GC root, the GC may collect both even though they still refer to each other.

~~~mermaid
flowchart LR
    R["GC root"] -.->|"Không còn đường tham chiếu"| A["Node A"]
    A --> B["Node B"]
    B --> A
~~~

The dashed line indicates a lost root path, **not an actual reference edge**. A reachability-based GC can recognize that the entire group is no longer used by the program. Be careful when one node in a cycle remains root-reachable: the whole group may then remain retained.

## 11. Memory Areas: Heap, Stack, and Static State

When learning Java, people often say “objects live on the heap, local variables on the stack.” This is a **useful learning model**, but it does not capture every modern JVM optimization.

| Aspect | Programming-level model | Considerations |
|---|---|---|
| Objects and arrays | May be allocated in JVM-managed object memory | The JIT may eliminate or transform allocations through escape analysis |
| Local variables and parameters | Exist in logical method execution frames | The JVM/JIT may use registers or other optimizations |
| Instance fields | Form part of each object's state | May strongly reference other objects |
| Static fields | Belong to loaded classes, not individual instances | Can retain objects for a long time |
| Native/off-heap resources | May be managed outside the Java heap | Follow the API contract, often using close/release mechanisms |

Avoid absolute claims such as “every local variable always resides on the physical stack,” “every object has a fixed address,” or “static variables always occupy a predetermined memory area.” Implementation details depend on the JVM, collector, and optimizations.

### Does Moving an Object in Memory Change Its Identity?

Some garbage collectors **move objects** to compact memory and reduce fragmentation. This does not change the logical identity observed by Java code through `==` comparisons between valid references. Java does not let you treat a fixed raw object address as a business ID.

For durable IDs, use an application-managed identifier such as a `UUID`, database key, or domain ID rather than `hashCode()` or a machine address.

## 12. Diagnosing Unexpected Object Retention

If heap use keeps growing after old business data should have expired, **do not infer a leak from a single RAM measurement**. Measure live-object trends after comparable load cycles, then inspect **reference paths from GC roots to retained objects**.

An investigation using a profiler or heap dump might look like this:

~~~text
GC root → Static field → Cache → Map entry → RequestData
~~~

If `RequestData` has expired but an entry remains, the fix is usually in the **cache policy** (size limits, TTL, removal when no longer needed), not the `new RequestData(...)` statement. Heap dumps and dominator trees identify retained object sets; JFR and GC metrics help correlate allocation and collection trends. Heap dumps can affect production performance, so choose collection times carefully.

GC diagnostic tools, distinguishing heap leaks from native memory pressure, and JDK command examples are covered in *Garbage collection and manual memory management*.

## 13. Common Design Scenarios

| Scenario | Appropriate approach | Why? |
|---|---|---|
| Object used for one computation | Keep a local reference without retaining it beyond the need | Once no root path remains, the GC may collect it |
| Cached result | Use a bounded/TTL cache with eviction policies | Avoid retaining data that is no longer useful |
| Subscription/listener | Return an unsubscription handle or manage `close()` | Prevent publishers from retaining subscribers indefinitely |
| File, stream, database connection | Use `try-with-resources` according to ownership | Close resources at the right lifecycle point |
| Graph with reference cycles | No need to break cycles just to “make GC run” | GC collects unreachable groups |
| Observe objects without keeping them alive | Consider `WeakReference`/queues when truly needed | Avoid introducing strong retention through observation |
| Release an object at an exact source-code line | Do not build designs around this assumption | Java does not guarantee GC scheduling |
| Session associated with a thread pool | Clean up ThreadLocal in `finally` | Threads are reused across tasks |

### Additional Considerations for Resource-Owning Objects

A `Connection` or `InputStream` can **be closed while still existing as a Java object** if references remain. Calling `close()` neither changes a reference to `null` nor immediately reclaims heap memory. Similarly, a reachable object wrapping a socket does not guarantee that the socket is still open; resource state and reachability are separate dimensions.

A good design makes clear **who owns** the resource, who may use it, when it must close, and which operations remain valid afterward.

## 14. Knowledge-Check Exercises

### Exercise 1 — Does `null` Delete an Object?

~~~java
class Item { int count = 2; }

Item x = new Item();
Item y = x;
x = null;
System.out.println(y.count);
~~~

**Answer:** Prints `2`. The object remains accessible through `y`.

### Exercise 2 — Does Leaving Scope Make an Object GC-Eligible?

~~~java
class Service {
    static final List<Object> STORE = new ArrayList<>();

    static void run() {
        Object result = new Object();
        STORE.add(result);
    }
}
~~~

Assume `java.util.List` and `java.util.ArrayList` are imported. After `run()` returns, `result` is out of scope. Is the newly created object definitely eligible for collection?

**Answer:** No. `STORE` still holds a strong reference if that field/list remains reachable. When the data is no longer needed, remove this reference path (and any others).

### Exercise 3 — A Rootless Reference Cycle

~~~java
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;
a = null;
b = null;
~~~

**Answer:** If no other reachable path leads to either node, the GC may collect both. A cycle alone does not keep them alive.

### Exercise 4 — Should You Wait for GC to Close a File?

**Answer:** No. Use `try-with-resources` or `close()` according to resource ownership rules. The GC does not promise timely file closure.

### Exercise 5 — WeakReference Results After Dropping Strong References

~~~java
WeakReference<Object> weak;
{
    Object o = new Object();
    weak = new WeakReference<>(o);
}
// Điều gì được đảm bảo về weak.get() tại đây?
~~~

**Answer:** You cannot conclude that `weak.get()` must be `null` or must be non-`null` merely because a block ended. If the GC cleared the weak reference it returns `null`; otherwise it may still return an object reference.

### Exercise 6 — Choosing an Appropriate Fix

An application keeps all request history in a `static ArrayList`; heap use grows with traffic even though old data is no longer needed.

**Suggested answer:** Bound the history and define a lifecycle policy, retain only necessary information, remove expired entries, and verify with a profiler/heap dump that no unintended reference paths remain. Calling `System.gc()` does not help while the list still retains objects.

## 15. Checklist for Reviewing a Java Class

- When is the object created, and **who** needs to retain a reference?
- Is the object stored in a field, collection, cache, callback, ThreadLocal, or singleton?
- When no longer needed, which strong-reference paths must be removed?
- Are there off-heap resources that need **timely closing**?
- Have request completion, timeouts, subscription cancellation, and shutdown been handled?
- Does any code assume `System.gc()` or `finalize()` will release resources on schedule?
- Can metrics and GC-root paths demonstrate that an object is retained unexpectedly?

**Remember:** Java automatically manages **object-memory reclamation** based on reachability; programmers must still design **data lifecycles, reference relationships, and resource lifecycles**. A no-longer-useful but reachable object can keep occupying memory; an unreachable object does not disappear immediately; and `close()` fulfills a different responsibility from GC.
