# StackOverflowError and Uncontrolled Recursion in Java

> **Scope:** Java Core → Exception → Error and initialization. `StackOverflowError` is a type of `Error` that the JVM typically throws when the execution of **a single thread** requires more *call stack* space than can be provided. Very common sources are **recursion without a stopping condition, recursion that does not make progress toward the stopping condition, infinite mutual calls, or finite recursion that is too deep**. What matters is not "catching the error to continue," but designing **appropriate stopping conditions, progress steps, depth limits, and data traversal algorithms**.

## 1. Correctly Identifying `StackOverflowError`

Simplified inheritance tree:

```text
java.lang.Throwable
├── java.lang.Exception
│   └── java.lang.RuntimeException
└── java.lang.Error
    └── java.lang.VirtualMachineError
        └── java.lang.StackOverflowError
```

`StackOverflowError` lies **in the `Error` branch**, not `Exception`. Therefore:

- It is an **unchecked throwable**: the compiler does not require `catch` or `throws`.
- `catch (Exception e)` **cannot catch** it. `catch (Error e)` or `catch (Throwable t)` can catch it according to the inheritance hierarchy, but catching it should not be turned into normal operational flow.
- It describes an inability to expand the stack for the next call/operation, usually from a deep call chain, rather than an expected business exception.
- `VirtualMachineError` is the branch for failures related to virtual machine limits or serious conditions; Errors of this kind should not be treated as equivalent to ordinary input data errors.
- An exception of class `IOException` or `IllegalArgumentException` does not "turn into" `StackOverflowError` merely because it occurs inside a recursive method. These are different kinds of failures.

**Key takeaway:** `StackOverflowError` is usually a **symptom of a call path exceeding the stack limit**, rather than indicating by itself which stopping condition is wrong. You must trace the code and data that produced that depth.

### 1.1. Why Can the Word "Overflow" Be Misleading?

This is **stack overflow**, not **integer overflow**:

```java
int x = Integer.MAX_VALUE;
int y = x + 1; // int overflow: sign flips, usually does not throw an Error.
```

And it is also not **heap memory exhaustion**: `OutOfMemoryError` is a different branch of `VirtualMachineError`. They can be related when a program has a large amount of data/calls, but they have different mechanisms and diagnostic strategies.

| Error/Phenomenon | Key Point | Example |
| --- | --- | --- |
| `StackOverflowError` | Cannot satisfy additional stack demand of a thread | Infinite or overly deep recursion |
| `OutOfMemoryError` | Insufficient memory resources for an allocation request or corresponding VM condition | Retaining a large number of objects on the heap |
| `int` overflow | Computation exceeds the integer representation range | `Integer.MAX_VALUE + 1` |
| `IllegalArgumentException` | Argument violates the contract checked by the API | Negative depth rejected |
| `NullPointerException` | Dereferencing `null` | `node.next.value` when `next == null` |

Do not fix `StackOverflowError` with `Math.addExact`, and do not conclude that "a huge heap means recursion can be arbitrarily deep."

## 2. What Is the Call Stack?

Each Java thread has an **execution stack** serving method calls. When calling a method, the JVM may create a **frame** containing the state needed for that invocation, such as parameters, local variables, intermediate operands, and control information according to the JVM model. When the method returns, the frame for that call can be removed from the stack.

Illustration:

```text
main()
└── calculate(3)
    └── calculate(2)
        └── calculate(1)
            └── calculate(0)
                return
            return
        return
    return
main() continues
```

Frames exist simultaneously while child calls have not yet finished. The number of retained frames depends on the depth of the call chain.

**Not every call has the same frame size.** Stack demand can depend on bytecode, local data, the JIT compiler, optimization mechanisms, CPU architecture, and VM configuration. Therefore, you cannot say "a Java thread always supports at most exactly 10,000 recursive calls."

### 2.1. Stack vs. Heap

Overview:

- **Stack** is tied to the execution thread/call scope; each thread has its own stack.
- **Heap** holds most objects and arrays allocated by the program; multiple threads can reference objects on the heap.
- A reference to an object may reside in a frame's local variable; the **referenced object** does not thereby "live on the stack" as a general rule.
- Allocating more objects on the heap does not directly lengthen the stack of a single call, though operations that create/traverse objects can still use the stack.
- The JVM may optimize certain physical details; the reasoning here focuses on call semantics and resource limits.

**Consequence:** you can keep a very large data tree on the heap yet traverse it using an iterative algorithm with an explicit stack, avoiding dependence on an overly deep JVM call chain.

## 3. Common Causes of Uncontrolled Recursion

### 3.1. Missing *Base Case* (Stopping Condition)

```java
// INTENTIONALLY WRONG: illustrates a method causing infinite recursion.
static void repeat() {
    repeat();
}
```

There is no return path. A typical Java JVM will keep extending the call chain until it can no longer satisfy stack demand and throw `StackOverflowError`.

### 3.2. Having a Base Case Without Making Progress Toward It

```java
// INTENTIONALLY WRONG: n does not decrease, so n > 0 remains true forever if starting with n > 0.
static int countdown(int n) {
    if (n == 0) {
        return 0;
    }
    return countdown(n);
}
```

A stopping condition is present, but **the argument of the next call does not change**. With `n` starting at 5, execution never gets closer to `n == 0`.

### 3.3. Moving in the Wrong Direction

```java
// INTENTIONALLY WRONG: n starts positive and keeps increasing forever.
static int countdown(int n) {
    if (n == 0) {
        return 0;
    }
    return countdown(n + 1);
}
```

If `n` increases, it does not move toward 0. With `int`, overflow may cause `n` to flip signs, but that does not make this algorithm correct; never rely on overflow to accidentally hit the stopping condition.

### 3.4. Mutual Recursion

```java
// INTENTIONALLY WRONG without a proper stopping condition.
static void first() {
    second();
}

static void second() {
    first();
}
```

A method viewed in isolation may appear to just call "another method," but the chain `first → second → first → ...` is infinite recursion. Call patterns across multiple services, callbacks, serializers, getters, and `toString()` can also create similar cycles.

### 3.5. Cyclic Data

Traversing a linked structure or graph via recursive calls without marking visited nodes can loop forever along:

```text
A.next → B
B.next → C
C.next → A
```

Here, the condition `node != null` is **not enough**: the links never reach `null`. The algorithm needs to identify already-seen nodes or have an input contract guaranteeing the structure is acyclic.

### 3.6. Terminating Recursion That Is Unusually Deep

A linked list with hundreds of thousands of elements can be completely **acyclic**. Traversing it with:

```java
static int size(Node node) {
    return node == null ? 0 : 1 + size(node.next);
}
```

can still overflow the stack when the number of nested calls is too large. **Having a correct stopping condition is not enough**; you must evaluate the **practical depth limit**.

## 4. Three Conditions of Well-Designed Recursion

Check all three conditions:

1. **Base case:** is there a state in which the method returns a result without making another call?
2. **Progress:** at each subsequent call, is there a measure that makes progress toward the base case (for example, `n` decreases toward 0, or the number of unvisited elements decreases)?
3. **Depth bound:** can the maximum depth be proven/bounded to be small enough for the runtime environment?

For recursion over a non-negative integer `n`:

```java
static int sumUpTo(int n) {
    if (n == 0) {
        return 0;
    }
    return n + sumUpTo(n - 1);
}
```

This is an **illustrative** method, assuming `n` is non-negative and the sum does not overflow `int`. The base case `n == 0` and progress `n - 1` make the method terminate for valid `n`, but the depth is about `n + 1`, so it is still unsuitable for arbitrarily huge `n`.

### 4.1. Java 17 — Safe Example: Recursion with a Base Case and Progress

Create **`BoundedRecursionDemo.java`**:

```java
public class BoundedRecursionDemo {
    static long factorial(int n) {
        if (n < 0 || n > 20) {
            throw new IllegalArgumentException(
                    "n phải thuộc [0, 20]");
        }
        if (n <= 1) {
            return 1L;
        }
        return Math.multiplyExact(n, factorial(n - 1));
    }

    public static void main(String[] args) {
        System.out.println("0! = " + factorial(0));
        System.out.println("5! = " + factorial(5));
        System.out.println("10! = " + factorial(10));

        try {
            factorial(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Compile/run on JDK 17+:

```bash
javac -encoding UTF-8 BoundedRecursionDemo.java
java BoundedRecursionDemo
```

Stdout:

```text
0! = 1
5! = 120
10! = 3628800
Invalid: IllegalArgumentException
```

Explanation:

- `factorial(0)` and `factorial(1)` return `1`: **base case**.
- Each step uses `n - 1`, so `n` progresses toward the base case.
- The bound `n <= 20` ensures the factorial result fits within `long`; `20!` fits, whereas `21!` exceeds `long`.
- `Math.multiplyExact` checks for integer overflow, **not** stack overflow. Bounding `n` is what keeps the number of calls small.
- For negative `n`, the method proactively throws `IllegalArgumentException` instead of allowing invalid recursion.
- This is a safe example for learning: it does not intentionally trigger `StackOverflowError` on the normal execution path.

## 5. An Intentional `StackOverflowError` Example — For Identification Only

If you want to observe the exact error type, you can run the following snippet in an isolated test process. **Do not use this as a computation technique or loop-termination mechanism in real applications.** Do not rely on the call count or stack trace length.

Create **`IntentionalStackOverflowDemo.java`**:

```java
public class IntentionalStackOverflowDemo {
    static void infinite() {
        infinite(); // Intentionally has no base case.
    }

    public static void main(String[] args) {
        try {
            infinite();
        } catch (StackOverflowError error) {
            System.out.println("Caught: "
                    + error.getClass().getSimpleName());
        }
    }
}
```

Run on standard JDK 17 in an experimental process:

```bash
javac -encoding UTF-8 IntentionalStackOverflowDemo.java
java IntentionalStackOverflowDemo
```

Typically, stdout is:

```text
Caught: StackOverflowError
```

**Limits to read before trying:**

- This example **intentionally exhausts the thread's stack**; do not run it in a production server, request handler, or severely resource-constrained environment.
- How the VM handles large stack demands depends on the implementation and resources; in practice `StackOverflowError` is the typical result, but depth, timing, or trace length should not be treated as a portable standard.
- In a severe low-stack state, complex logging/formatting/cleanup after catching may fail or trigger additional errors. This snippet intentionally keeps the handler very simple and does not attempt to call `infinite()` again.
- `catch(StackOverflowError)` is strictly for **educational/diagnostic** purposes. Production code must fix the base case, progress, or depth limit rather than relying on catching as a "safe exit."
- In some environments, thread stack/VM configuration may cause different behavior or cause the OS/VM to terminate the process before the learner sees the output; do not conclude the program is correct just because the sample line is not printed.

### 5.1. Why Can the Error Occur Before the Final Log?

Calls to `infinite` continue nesting. At the moment a frame/stack resource is needed that the thread cannot provide, the VM raises the error. Only when control unwinds far enough to reach the handler and the handler can execute does the `Caught` line appear.

If you log a very long stack trace, the text volume and output cost can be large. There is no need to print the entire trace just to prove the error class in an exercise.

### 5.2. Why Not Write `catch(Exception)`?

Because `StackOverflowError` is not under `Exception`; it belongs to `Error`. If you replace the handler with:

```java
// DOES NOT catch StackOverflowError:
catch (Exception e) {
    System.out.println("Handled");
}
```

this is only an **illustrative code fragment**, not a complete program. The handler will not receive `StackOverflowError` according to Java's inheritance hierarchy.

## 6. Stack Overflow Does Not Mean Heap Exhaustion

Java uses different memory regions for different roles. Recursion typically increases stack demand, whereas an algorithm storing too many objects in a collection can increase heap pressure.

Example:

```java
static void recurse() {
    recurse();
}
```

This method creates a deep call chain and **does not necessarily** retain millions of objects on the heap.

Conversely:

```java
List<byte[]> all = new ArrayList<>();
while (true) {
    all.add(new byte[1024 * 1024]);
}
```

This is a **dangerous counterexample — do not run it**. It continuously retains large arrays on the heap and can cause `OutOfMemoryError`, not recursion.

A program can simultaneously put pressure on both stack and heap (for example, each call creates a large object), so diagnosing it requires inspecting the **Throwable type**, stack trace, allocation pattern, and specific root cause.

## 7. Messages and Stack Traces: How to Read Them?

When encountering the error:

```text
Exception in thread "main" java.lang.StackOverflowError
    at example.Parser.read(Parser.java:41)
    at example.Parser.read(Parser.java:41)
    at example.Parser.read(Parser.java:41)
    ...
```

This is an **illustrative trace diagram**, not a fixed stderr output. Repeated lines with the same method and line number usually suggest direct recursion. If there are repeating frames like:

```text
A.convert(...)
B.map(...)
A.convert(...)
B.map(...)
...
```

suspect **indirect recursion** or a call cycle.

### 7.1. Meaningful Steps for Reading a Trace

1. Confirm the **Throwable type is `StackOverflowError`**, not confusing it with OOME or a recursion-specific domain exception.
2. Find the **repeating block of frames** near the deep part of the trace. It may be a single method or a chain of multiple methods.
3. Locate the **base case** and the condition under which the input never reaches it.
4. Check parameters across calls: are numbers decreasing properly? Is the offset advancing? Are nodes being marked visited?
5. For cyclic data, reproduce with a minimal graph.
6. For valid but overly deep input, measure the data depth and choose an iterative algorithm.
7. If it reproduces only in the deployment environment, check stack configuration and differences in thread pools, JDK, architecture, and optimizations.
8. If the code already has input constraints, verify they are applied **before** recursion runs.

### 7.2. Why Might a Trace Not Show the Full Depth?

How `Throwable#printStackTrace()` prints and what stack trace data is available can be affected by the VM and its configuration. HotSpot has options such as `-XX:MaxJavaStackTraceDepth` that affect the stored/displayed trace length; logging tools or APMs may also truncate it.

**Do not use the number of frames printed by `printStackTrace` as an exact, portable measure of recursion depth.** A trace is primarily used to find the **call path** and the faulty region of code.

## 8. `-Xss`: Thread Stack Size and What Not to Infer

Many JVMs allow adjusting the stack size for Java threads via options:

```bash
java -Xss512k MyProgram
java -Xss1m MyProgram
```

These are **configuration-dependent illustrative commands**, assuming `MyProgram.class` is already compiled. The JVM may enforce minimum/maximum limits; option names and how they take effect depend on the VM. Check the documentation and behavior of the specific JVM you are using.

### 8.1. Does Increasing `-Xss` Solve the Error?

**It is not a general solution.** If recursion is **infinite**, increasing the stack only delays the overflow. If recursion is **finite with a known bound**, adjusting the stack size may sometimes allow a valid workload to run—but you must consider resource cost, thread count, and risks in other environments.

A larger stack per thread can increase total memory/virtual address space demand in an application with thousands of threads. Do not blindly raise it to a huge value without analyzing the algorithm.

### 8.2. Is the Maximum Number of Calls Fixed?

No. Even with the same `-Xss`:

- Methods with many local variables, expressions, and large frames may use stack differently from small methods.
- JIT compilation, inlining, and how the VM organizes frames vary by implementation and warm-up state.
- Different JDK versions, operating systems, and CPU architectures may differ.
- Existing stack depth when recursion starts (e.g., from a framework) also varies.
- Handlers/loggers may need stack space to run.

Therefore, you should not state "JDK 17 allows exactly 1,024 recursive calls" as a rule.

### 8.3. Different Threads Have Separate Stacks

`main` runs on one Java thread; request worker threads, scheduled threads, or custom threads have their own stacks. A routine that runs in `main` is not automatically guaranteed to run at the same depth in a thread configured with a smaller stack. Conversely, a `StackOverflowError` on one thread is not by itself evidence that the entire JVM's heap is exhausted.

## 9. Does Tail Recursion Avoid `StackOverflowError` in Java?

*Tail recursion* is when the recursive call is in the logically final position of the method.

Example:

```java
static long sumTail(long n, long acc) {
    if (n == 0) {
        return acc;
    }
    return sumTail(n - 1, acc + n);
}
```

This is an illustrative method for non-negative `n` without `long` overflow. It is written in tail-recursive form, but **Java does not guarantee tail-call optimization (TCO)** under the standard language/JVM contract. You must not assume the JVM will always reuse frames and allow unbounded depth.

Compare:

```java
static long sumNonTail(long n) {
    if (n == 0) {
        return 0L;
    }
    return n + sumNonTail(n - 1);
}
```

This is non-tail recursion because an addition remains after the child call. Both approaches need a base case and progress; both can consume significant stack if depth is large.

**Practical rule:** If you need very large and reliable depth across standard Java JVMs, convert to an **iterative loop** or an **application-managed stack/queue** instead of counting on tail-recursion optimization.

## 10. Java 17 — Equivalent Recursive and Iterative Examples

Create **`RecursiveVsIterativeDemo.java`**:

```java
public class RecursiveVsIterativeDemo {
    static int sumRecursive(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n âm");
        }
        if (n == 0) {
            return 0;
        }
        return Math.addExact(n, sumRecursive(n - 1));
    }

    static int sumIterative(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n âm");
        }
        int sum = 0;
        for (int i = 1; i <= n; i++) {
            sum = Math.addExact(sum, i);
        }
        return sum;
    }

    public static void main(String[] args) {
        int n = 5;
        System.out.println("Recursive: " + sumRecursive(n));
        System.out.println("Iterative: " + sumIterative(n));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 RecursiveVsIterativeDemo.java
java RecursiveVsIterativeDemo
```

Stdout:

```text
Recursive: 15
Iterative: 15
```

Explanation:

- Both methods produce `1+2+3+4+5 = 15`.
- Recursion keeps calls waiting on one another, so stack depth grows linearly with `n` in the standard evaluation model.
- The loop keeps `sum` and `i` state within **a single method invocation**, without creating a new call for each number.
- `Math.addExact` handles integer overflow via `ArithmeticException`, not `StackOverflowError`.
- When `n` is large enough, the sum can overflow `int`; the example intentionally picks a small `n` so output is deterministic. To support large numbers, you can use a formula with overflow checking or `BigInteger`.
- This does not mean iteration is always optimal for every recursion: tree/graph traversal is sometimes expressed more naturally with recursion if depth is small and controlled.

## 11. Indirect Recursion in Getters, Listeners, and `toString()`

Some real-world bugs do not have any method named "recurse":

```java
class A {
    B other;
    @Override public String toString() {
        return "A(" + other + ")";
    }
}

class B {
    A other;
    @Override public String toString() {
        return "B(" + other + ")";
    }
}
```

These are **illustrative declarations**, not a standalone runnable program. If `a.other=b` and `b.other=a`, calling `a.toString()` can loop through `A.toString → B.toString → A.toString` until the stack overflows.

Similar situations:

- `equals` or `hashCode` recursing in a cycle across bidirectional object relationships.
- Getter on A calls getter on B, and getter on B calls back into A.
- Event listener A triggers B, and B calls back into A due to a missing flag/reentrancy guard.
- A serializer traverses a cyclic object graph without tracking visited identities.
- Tree traversal where actual data contains a back-reference to a parent.
- A recursive parser that fails to advance its index when encountering a special token.

**Do not fix this by catching `StackOverflowError` in `toString()`.** Reduce depth, avoid following back-references, limit output, or use a visited context.

## 12. Cycles in Object Graphs: Tracking by Identity

A graph can have **cycles** while being completely valid as data. If the traversal algorithm does not record visited nodes, it may loop infinitely or process the same node repeatedly.

Example:

```text
Node A → Node B → Node C → Node A
```

For general graphs, use a `Set<Node> visited`. If the semantics is "have we seen the exact same **object** before?", Java should track by **object identity**, rather than always relying on `equals`/`hashCode`, which might themselves recurse or compare by content.

One way to create an identity set:

```java
Set<Node> visited = Collections.newSetFromMap(
        new IdentityHashMap<Node, Boolean>());
```

This snippet requires importing `Set`, `Collections`, `IdentityHashMap` and defining `Node`. `IdentityHashMap` compares keys using `==` instead of `equals`.

### 12.1. Java 17 — Safe Cyclic Graph Traversal Example

Create **`CyclicGraphTraversalDemo.java`**:

```java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class CyclicGraphTraversalDemo {
    static final class Node {
        final String name;
        Node next;

        Node(String name) {
            this.name = name;
        }
    }

    static int countUnique(Node node, Set<Node> visited) {
        if (node == null || !visited.add(node)) {
            return 0;
        }
        return 1 + countUnique(node.next, visited);
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");

        a.next = b;
        b.next = c;
        c.next = a;

        Set<Node> visited = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());

        int count = countUnique(a, visited);
        System.out.println("Unique nodes: " + count);
        System.out.println("Visited: " + visited.size());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 CyclicGraphTraversalDemo.java
java CyclicGraphTraversalDemo
```

Stdout:

```text
Unique nodes: 3
Visited: 3
```

Step by step:

1. A is added to `visited`; recurses to B.
2. B is marked; recurses to C.
3. C is marked; the next step returns to A.
4. `visited.add(a)` returns `false` because it is the **same object A**, so the second base case returns 0; the cycle terminates.
5. The function counts three distinct nodes.

**Important limitation:** `visited` handles **cycles** but **does not bound depth by itself**. If the graph is an acyclic chain of 200,000 distinct nodes, `countUnique` can still use too much stack. When data can be very deep, combine a depth limit or use **iterative** traversal.

## 13. Java 17 — Iterative Traversal with `Deque` to Avoid a Deep Call Stack

Instead of one recursive call per node, use a heap-allocated data structure to represent nodes to be processed.

Create **`IterativeGraphTraversalDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.Set;

public class IterativeGraphTraversalDemo {
    static final class Node {
        Node next;
    }

    static int countUnique(Node start) {
        if (start == null) {
            return 0;
        }

        Set<Node> visited = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        Deque<Node> pending = new ArrayDeque<>();
        pending.push(start);

        while (!pending.isEmpty()) {
            Node current = pending.pop();
            if (!visited.add(current)) {
                continue;
            }
            if (current.next != null) {
                pending.push(current.next);
            }
        }
        return visited.size();
    }

    public static void main(String[] args) {
        Node first = new Node();
        Node current = first;
        for (int i = 1; i < 50_000; i++) {
            current.next = new Node();
            current = current.next;
        }

        current.next = first; // Cycle back to the start.
        System.out.println("Unique nodes: " + countUnique(first));
    }
}
```

Run:

```bash
javac -encoding UTF-8 IterativeGraphTraversalDemo.java
java IterativeGraphTraversalDemo
```

Stdout:

```text
Unique nodes: 50000
```

Meaning:

- The `for` loop creates 50,000 `Node` objects and links them into a list; finally it creates a cycle back to `first`.
- `Deque` holds the nodes to process and `visited` prevents looping over cycles.
- `countUnique` does not call itself. The call stack depth of the **traversal algorithm itself** does not grow linearly with the number of nodes.
- In return, the `Node` objects, `Deque`, and `visited` require **heap** memory. For very large data, memory limits or appropriate algorithms are still needed; avoiding stack overflow does not mean memory pressure cannot occur.
- For general graphs with many edges, the `pending` structure can hold many elements. Both time complexity and memory complexity must be evaluated, not just recursion depth.

### 13.1. Why Use `ArrayDeque` Instead of `Stack`?

`ArrayDeque` is the common modern choice when LIFO/FIFO semantics are needed in Java. You can use `push`/`pop` as a manual stack. It does not allow `null` elements, so the example only pushes non-null nodes.

Do not confuse the **Java call stack** with a **`Deque` object**: `Deque` is an application-managed data structure, typically on the heap, and does not create a JVM frame for each element.

## 14. Safe Depth Must Be Enforced at Input Boundaries

Even when input has no cycles, an API accepting nested JSON/XML/expression trees from external sources can encounter extremely deep data. If using recursion, you can:

- Reject input exceeding a defined **maximum depth**.
- Switch to an iterative parser/traversal when large depth must be supported.
- Bound size, node count, edge count, and processing time as well.
- Use parser/framework configuration that limits nesting if the library supports it.
- Separate validation errors into an **appropriate business/domain exception**, rather than waiting for the VM to throw `StackOverflowError`.

For example: "Maximum 64 levels of nesting" is a deliberately chosen **application contract**, completely different from "the JVM's stack happens to survive 64 levels right now."

### 14.1. Java 17 — Enforcing a Depth Limit with a Meaningful Error

Create **`DepthLimitDemo.java`**:

```java
public class DepthLimitDemo {
    static final int MAX_DEPTH = 4;

    static int visit(int depth, int remaining) {
        if (depth > MAX_DEPTH) {
            throw new IllegalArgumentException(
                    "Vượt giới hạn độ sâu " + MAX_DEPTH);
        }
        if (remaining == 0) {
            return depth;
        }
        return visit(depth + 1, remaining - 1);
    }

    public static void main(String[] args) {
        System.out.println("Safe result: " + visit(0, 3));
        try {
            visit(0, 5);
        } catch (IllegalArgumentException e) {
            System.out.println("Rejected: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 DepthLimitDemo.java
java DepthLimitDemo
```

Stdout:

```text
Safe result: 3
Rejected: Vượt giới hạn độ sâu 4
```

Interpretation:

- `visit(0,3)` calls with depth 0, 1, 2, 3, then the base case returns 3.
- `visit(0,5)` reaches depth 5; the `depth > 4` condition proactively rejects it.
- This is an **application-chosen `IllegalArgumentException`**, not `StackOverflowError`.
- Depth limits must clearly define whether counting starts from 0 or 1, and whether the check is `>` or `>=` to avoid off-by-one bugs.
- When used with untrusted data, besides depth you also need to check `remaining >= 0` and other invariants. The example intentionally uses valid step counts to focus on depth.
- The value 4 in the program is only an illustrative limit, **not** a claim that 4 is a JVM limit or general safety limit.

### 14.2. Depth Limits and Visited Sets Solve Different Problems

| Mechanism | What It Prevents | What It Does Not Solve by Itself |
| --- | --- | --- |
| Base case + progress | Recursion without a stopping path on valid input | Unexpected cyclic data, very large depth |
| Visited set | Cycles/revisiting already-seen nodes | Very deep chain of new nodes, memory used by the set |
| Depth limit | Overly deep recursion | Result correctness when data is rejected |
| Traversal with `Deque` | Call stack growing too deep with node count | Large heap usage, algorithm may still loop infinitely without `visited` |
| Input validation | Contract-violating cases up front | Bugs in internal recursion if still implemented incorrectly |
| Larger `-Xss` | May allow some finite depths to run | Infinite recursion, side effects, cycles |

## 15. Recursion in Trees: Depth vs. Node Count

A balanced tree can have many nodes yet small depth. A completely skewed tree can have `n` nodes and depth around `n`.

```text
Balanced tree:               Skewed tree:
        A                     A
      /   \                    \
     B     C                    B
    / \   / \                    \
   D   E F   G                    C
                                   \
                                    D
```

If recursion holds one frame per level:

- A balanced tree has `O(log n)` depth in an ideally balanced structure.
- A skewed tree has `O(n)` depth and can overflow the stack when `n` is large.
- A large total node count is not enough to conclude the stack will definitely overflow; you must examine the **longest path depth** and how the traversal invokes methods.
- An algorithm may compute across many branches without **keeping all branches on the call stack simultaneously** if traversed sequentially; however, a single very deep branch is still dangerous.

### 15.1. Java 17 — Illustrating Recursion Entry/Exit Trace

Create **`RecursionTraceDemo.java`**:

```java
public class RecursionTraceDemo {
    static void trace(int depth, int remaining) {
        System.out.println("Enter " + depth);
        if (remaining > 0) {
            trace(depth + 1, remaining - 1);
        }
        System.out.println("Exit " + depth);
    }

    public static void main(String[] args) {
        trace(0, 2);
    }
}
```

Run:

```bash
javac -encoding UTF-8 RecursionTraceDemo.java
java RecursionTraceDemo
```

Stdout:

```text
Enter 0
Enter 1
Enter 2
Exit 2
Exit 1
Exit 0
```

With this trace, three `trace` calls exist nested together before `Exit` begins printing. Printing this way helps visualize the **push** and **unwind** order of the call stack. In non-terminating recursion, execution going deeper never reaches the `Exit` statements on the normal path.

## 16. Why Not Use `try/catch(StackOverflowError)` as a Stopping Condition?

This is an anti-pattern:

```java
// INTENTIONALLY WRONG: do not use stack exhaustion as an algorithm.
static int count(Node node) {
    try {
        return 1 + count(node.next);
    } catch (StackOverflowError ignored) {
        return 0;
    }
}
```

This snippet is **illustrative**, not a standalone program. Problems:

1. For a cyclic list, there is no way to correctly count "distinct nodes" by waiting for the stack to overflow.
2. For a finite list, depth is bounded by VM resources, so the result becomes **machine- and thread-dependent**, not data-dependent.
3. When nearly out of stack, complex error handling/cleanup may fail.
4. Catching can hide bugs, causing the application to return wrong or inconsistent results.
5. In recursion where catching happens in **every frame**, unwinding can hit multiple catch points with further computations, making reasoning even harder.
6. Stack exhaustion does not guarantee atomicity; side effects may have already occurred before the error.
7. Increasing `-Xss` changes the algorithm's output if it relies on where the overflow happens.

**Solution:** stop based on data/structure, use a visited set, depth limits, loops, or an explicit stack; never use an `Error` type as a "termination value."

### 16.1. Is Catching `Error` Ever Allowed at Technical Boundaries?

Some infrastructure systems may catch `Throwable` at a **very narrow boundary** to log/sandbox a failure and then rethrow or terminate the task. But this is an advanced policy, and it cannot be guaranteed that the VM/thread is always in a safe enough state to continue everything.

Normal application code should:

- **Not** broadly catch `Error` and return a "success" response.
- **Not** infinitely retry the same recursion inside a handler.
- Keep cleanup logic simple, controlled, and without losing the original error information.
- Treat `StackOverflowError` as a serious failure signal requiring **code fixes or data limits**.

## 17. Errors During Initialization and `StackOverflowError`

This topic belongs to the "Error and initialization" group, so it is important to distinguish **recursion causing `StackOverflowError`** from **class initialization errors**.

In Java, static initializers and static field initialization can run when a class is first used. If initialization logic accidentally triggers deep recursion (such as calling a non-terminating recursive method), the thread's stack can also overflow.

However:

- `StackOverflowError` is a stack-related error whether it occurs **inside a static initializer**, constructor, or regular method.
- **Class initialization failure** rules can produce other manifestations such as `ExceptionInInitializerError` or `NoClassDefFoundError` in applicable situations; you must not say every error inside a static initializer is always wrapped into a single class.
- An `Error` thrown during class initialization follows different propagation rules from ordinary exceptions thrown from an initializer.
- After a class fails to initialize, the class's state for subsequent uses may be marked erroneous, so retrying in the same JVM will not automatically fix the cause.
- Instance constructors calling themselves via **ordinary methods** can cause recursion; however, constructor calls `this(...)`/`super(...)` have their own compile-time rules and should not be equated with infinite method recursion.

**Key takeaway:** identify the error's position on the stack and **the layer where it originates**. If an `Error` occurs during class initialization, besides recursion you must investigate the initialization chain and JVM limits.

### 17.1. Do Not Rely on Retrying Failed Class Initialization

If a static initializer has failed, code using the class afterward must not assume it can "retry" initialization like a normal method call. When resource/recursion errors occur during initialization, you typically need to fix the initialization design and class/process lifecycle handling, rather than just wrapping in `try/catch` and calling again.

### 17.2. Be Careful with Mutually Calling Factories

A chain such as `ServiceHolder.get() → ServiceFactory.create() → ServiceHolder.get()` can create indirect recursion right at the dependency initialization step. Pay special attention to circular dependencies among constructors/factories or lazy getters; using lazy initialization does not automatically eliminate circular dependencies.

## 18. Recursion and `equals`, `hashCode`, `toString`

Many libraries or logging tools automatically invoke `toString`; collections like `HashMap` can call `hashCode` and `equals`. If two objects have a bidirectional link and those methods traverse the entire graph without a visited check, the failure may surface when **logging an object**, not where the author thought recursion was being used.

Example:

```java
// Anti-pattern when the graph has a back-reference.
@Override
public String toString() {
    return "Parent{child=" + child + "}";
}
```

If `child.toString()` in turn prints `parent`, the call path loops. Fixes include printing only IDs, safe field names, or limiting representation depth.

Similarly:

- `equals` should not compare infinitely across back-references if the graph has cycles.
- `hashCode` should be based on fields with appropriate semantics, avoiding unbounded traversal of bidirectional graphs.
- Auto-generated methods from tools may be unsuitable for cyclic graphs, even if they look like minimal code.
- Java `record`s have `toString/equals/hashCode` based on components; if the component graph is cyclically linked, indirect recursion must still be considered.
- A `StackOverflowError` in a log formatter does not prove the logger is broken; the source may be `toString()` of the object passed to the logger.

## 19. Where Can Depth Guards Be Placed?

Appropriate layers:

- **Parser:** limit the nesting level of JSON/XML/expressions.
- **Graph traversal:** limit depth or use `visited`/iterative traversal.
- **Business rule:** limit the number of parent/child levels in domain structures.
- **API boundary:** reject overly deep or overly large input before passing it down to services.
- **Recursive algorithm:** prove a decreasing and bounded measure.
- **Library integration:** read library limits/configurations and avoid disabling safety measures without reason.

Choose a **clear counting convention**. For example, is the root at depth 0 or depth 1? Does depth 64 mean 64 edges or 64 nodes? A clearly documented contract helps avoid off-by-one vulnerabilities.

### 19.1. What If the Depth Is Unknown in Advance?

When users can send very deep data, do not just raise a constant depth guard to an arbitrarily huge value. Instead:

1. Evaluate how deep the data actually needs to be processed according to requirements.
2. If required, choose an iterative algorithm or parser structure that does not use call stack proportional to nesting.
3. Bound node/edge counts, execution time, and memory.
4. If rejection is needed, use a business result/exception type with an appropriate error code.
5. Keep monitoring for boundary inputs while avoiding printing/dumping raw sensitive or oversized data.

## 20. Java 17 — Finite Mutual Recursion with a Stopping Point

Not every A ↔ B call pattern is wrong. If there is a **decreasing measure** and a base case, mutual recursion can be valid.

Create **`MutualRecursionDemo.java`**:

```java
public class MutualRecursionDemo {
    static boolean isEven(int n) {
        if (n == 0) {
            return true;
        }
        return isOdd(n - 1);
    }

    static boolean isOdd(int n) {
        if (n == 0) {
            return false;
        }
        return isEven(n - 1);
    }

    public static void main(String[] args) {
        System.out.println("Even 4: " + isEven(4));
        System.out.println("Odd 5: " + isOdd(5));
        System.out.println("Even 0: " + isEven(0));
    }
}
```

Run:

```bash
javac -encoding UTF-8 MutualRecursionDemo.java
java MutualRecursionDemo
```

Stdout:

```text
Even 4: true
Odd 5: true
Even 0: true
```

Notes:

- The example only uses **non-negative `n`**; if `n` is negative, the measure decreases forever away from 0 and can cause stack overflow.
- In real applications, you can validate `n >= 0` at the boundary before calling the method.
- Mutual calls are not inherently a problem; what matters is **whether the call path can terminate and whether depth is controlled**.
- If the input is a very large integer, even though the recursion terminates mathematically, there is still a risk of stack overflow due to excessive depth. For even/odd checks, `(n & 1) == 0` is simple and needs no recursion.

## 21. Tree/Graph Traversal: Choosing Based on Data

| Data and Requirements | Reasonable Choice | Remaining Risks |
| --- | --- | --- |
| Small tree, bounded depth | Recursion with a clear base case | Input exceeding limits if validation is missing |
| Tree may be very skewed/deep | Loop or `Deque`/`Queue` | Heap used for intermediate structures |
| Graph with cycles | Visited set, identity when needed | Memory and concurrency |
| Graph with cycles and very deep | Iterative + visited | Time, large number of nodes/edges |
| Only summing a number sequence | Loop/formula with overflow check | Integer overflow independent of stack |
| Deep external JSON/XML | Parser with depth policy; reject or traverse iteratively | High parse/input cost |
| Fixed, very small number of levels | Simple recursive method | Does not scale automatically if input expands |
| Callback/event that may re-invoke itself | Reentrancy guard or work queue | Deadlock/ordering issues if guard is poorly designed |

**Do not mechanically convert recursion to a loop and drop all cycle checks.** If the input graph has cycles, a loop without a visited set can still run forever—it just won't overflow the call stack in the same way.

## 22. Testing Recursion and Error Paths

Tests should cover:

1. **Base case:** empty/0/null input (if allowed by the contract).
2. **One step:** very small input, verifying progress.
3. **Normal path:** expected values at low depth.
4. **Invalid preconditions:** negative numbers, invalid depth.
5. **Boundary edges:** maximum depth, just above the limit.
6. **Cyclic structure:** small graph A → B → A.
7. **Deep acyclic structure:** iterative algorithm must handle it correctly.
8. **No state corruption:** if validation rejects early, no unnecessary side effects have occurred.
9. **Concurrency (if applicable):** can the object graph be modified during traversal?
10. **Error messages:** clear failure semantics without leaking sensitive information.

### 22.1. JUnit 5 Example for Contract Testing

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RecursionContractTest {
    @Test
    void factorialHasWorkingBaseCases() {
        assertEquals(1L, BoundedRecursionDemo.factorial(0));
        assertEquals(120L, BoundedRecursionDemo.factorial(5));
    }

    @Test
    void negativeInputIsRejectedBeforeRecursion() {
        assertThrows(IllegalArgumentException.class,
                () -> BoundedRecursionDemo.factorial(-1));
    }

    @Test
    void depthGuardRejectsExcessiveInput() {
        assertEquals(3, DepthLimitDemo.visit(0, 3));
        assertThrows(IllegalArgumentException.class,
                () -> DepthLimitDemo.visit(0, 5));
    }
}
```

**This is an illustrative test file requiring JUnit Jupiter and the two demo classes in the same package**, not a standalone JDK-only program. Tests rely on **expected behavior** rather than trying to "wait for the JVM to overflow the stack" to verify base cases.

### 22.2. Do Not Assert on the Exact Depth Before `StackOverflowError`

Call counts are affected by JVM, thread stack, JIT, and frame size. A test like "assert SOE definitely occurs after exactly 10,000 calls" is brittle and non-portable. If you need a test that intentionally triggers a VM error, run it separately in an isolated environment with timeouts/resource limits and treat it as a diagnostic test, not a basic unit test.

## 23. Common Misconceptions and Corrections

| Misconception | What Is True |
| --- | --- |
| "`StackOverflowError` is an `Exception`." | It belongs to `Error → VirtualMachineError`. |
| "`catch(Exception)` catches every Throwable." | It does not catch `Error`. |
| "SOE is always caused by a missing base case." | It can be caused by finite recursion that is too deep or complex call cycles. |
| "Having a base case means the stack cannot overflow." | Valid depth can still exceed VM limits. |
| "A larger `-Xss` fixes infinite recursion." | It only delays overflow; it does not create a stopping condition. |
| "Every JVM allows the same maximum number of calls." | It depends on VM, architecture, frame, JIT, thread, and configuration. |
| "Tail-call recursion in Java is always optimized into a loop." | Java does not guarantee general TCO. |
| "Without cycles, recursion is always safe." | An acyclic path can still be very long. |
| "Using a visited set eliminates all SOE risk." | It solves cycles, not large depth by itself. |
| "Switching to a loop means you can drop `visited`." | A cyclic graph can still run forever. |
| "A loop cannot run out of memory." | `Deque`/`Set` and data on the heap still consume memory. |
| "Just catch `StackOverflowError` and return 0." | Produces wrong results and can leave state unreliable. |
| "`OutOfMemoryError` and `StackOverflowError` are the same." | Different resources and causes. |
| "`int` overflow creates `StackOverflowError`." | Integer overflow is a different arithmetic phenomenon. |
| "Only `recurse()` causes SOE." | `toString`/getters/serializers/equals/callbacks can call one another in cycles. |
| "A `StackOverflowError` during logging is always the logger's fault." | It can be caused by `toString()` of the data passed to the logger. |
| "A long trace tells you the exact depth." | Traces can be truncated/limited by configuration. |
| "If it runs in `main`, it will run in any thread pool." | Stack configurations across threads/environments may differ. |
| "Static initializer stack overflow is just like any initialization exception." | `Error` and class initialization failure rules must be considered separately. |
| "Just give it more heap memory." | Heap and call stack serve different needs. |
| "Uncontrolled recursion is just a performance issue." | It can become a severe VM error and cause loss of availability. |

## 24. Checklist Before Using Recursion in Java

- [ ] Have I clearly stated the **base case** for every valid kind of input?
- [ ] Do I have a measure proving child calls **make progress toward the base case**?
- [ ] Have I checked negative, null, empty, and very large values?
- [ ] Have I evaluated the **maximum depth**, not just the node count/total work?
- [ ] If input is user-supplied, have depth/node/size limits been applied?
- [ ] If the graph may contain cycles, do I have a visited set or cycle-detection mechanism?
- [ ] If object identity matters, have I avoided mistakenly relying on `equals/hashCode`?
- [ ] For very deep data, have I considered `Deque`/`Queue` instead of recursion?
- [ ] Do I understand that `StackOverflowError` is an `Error` and `catch(Exception)` does not catch it?
- [ ] Am I avoiding using `catch(StackOverflowError)` as an algorithm stopping condition?
- [ ] Am I avoiding assuming Java always optimizes tail recursion?
- [ ] Am I avoiding using `-Xss` as the primary fix for infinite recursion?
- [ ] Do I distinguish `StackOverflowError` from `OutOfMemoryError` and integer overflow?
- [ ] Have I checked hidden recursion paths through `toString`, `equals`, getters, and serializers?
- [ ] When reading a trace, do I look for repeating frame patterns and stopping conditions instead of just increasing stack size?
- [ ] Have I tested skewed trees, cyclic graphs, and near-limit depths?
- [ ] If the error occurs during class initialization, have I distinguished class initialization failures?
- [ ] Have I ensured the solution remains correct as inputs/environments scale?

## 25. Summary

`StackOverflowError` is an **unchecked `VirtualMachineError`** related to a thread's call stack limit. Recursion without a base case, without progress toward the base case, cyclic calls across multiple methods, or traversing a cyclic graph can all cause the error; however, **overly deep finite recursion** can also overflow the stack. To prevent it, you need **provable stopping conditions, progress steps, depth limits**, and **iterative algorithms with an explicit stack/queue** when data may be deep. A visited set handles cycles but does not eliminate all depth risks. `-Xss` can shift resource thresholds but does not cure infinite recursion, and `catch(StackOverflowError)` is not a normal recovery mechanism. Proper algorithm design and input bounds are the reliable ways to protect a program.
