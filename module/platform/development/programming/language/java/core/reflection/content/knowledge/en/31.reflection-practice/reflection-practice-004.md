# Reading an Object Graph with Reflection and Controlling Reference Cycles

An **object graph** consists of Java objects as **vertices**, and references from fields, array elements, or collections as **edges**. One object can be pointed to by many other objects, point to itself, or sit inside a reference cycle such as `A.next = B` and `B.next = A`.

When writing an object graph walker, debugger, snapshot tool, serializer, or diagnostic inspector using Reflection, you cannot simply recurse across every field indefinitely. You must simultaneously protect **object identity accuracy**, **depth**, **node/element counts**, **access permissions**, **determinism**, and **sensitive data**.

The single most important principle: use **reference identity (`==`)** rather than `equals()` to recognize a previously seen object; record it **before** descending into its fields. When encountering that object again, only print a reference to the recorded node without traversing further.

## 1. How Is a Graph Different from a Tree?

Example:

~~~text
A ──next──> B
^           |
|           |
+──next─────+
A ──items[0]──> B
~~~

Here:

- `A` and `B` are **two independent instances**.
- `A.next` and `A.items[0]` both reference **the same instance B**. This is a **shared reference/alias**.
- `B.next` references back to `A`. This is a **cycle**.
- If you only look at each edge in isolation and recurse, traversal will loop forever `A → B → A → B ...`.

We must distinguish **already seen** from **in the current cycle**:

| State | Meaning |
| --- | --- |
| Unseen instance | Can be assigned an ID and explored if budget remains |
| Already seen on the current recursion path | There is a loop (*cycle*) returning to an active node |
| Already seen, not on the current path | Shared reference (*alias*) to an already processed node |
| Hit depth/node threshold | Cannot conclude whether the remaining portion has a cycle or not; merely mark as **truncated** |

For the goal of **printing a graph without looping while preserving shared structure**, a global `seen` table for *a single traversal* suffices: every repeat encounter prints `ref #id`. If you want to **distinguish cycles from aliases separately**, you also need a set of nodes *currently on the stack* (often called `active`, `gray`, or DFS recursion stack). The practice code below chooses `ref #id` to preserve identity simply; do not call every repeated reference a "cycle".

## 2. Why Must You Use `IdentityHashMap`?

Two concepts are easily confused:

- **Content equality:** `x.equals(y)` can be `true` even when `x` and `y` are two distinct instances. Conversely, some classes define `equals()`/`hashCode()` based on mutable data.
- **Same object:** `x == y`. This is the identity needed for an object graph, because two instances with identical content are still two separate nodes.

If you use `HashSet<Object> visited` or `HashMap<Object, Integer>`, Java calls `equals()` and `hashCode()` on the objects being traversed. That can produce wrong conclusions, side effects, or infinite recursion if those methods themselves walk the graph.

`IdentityHashMap<Object, Integer> seen` uses **reference equality (`==`)** for keys. It avoids depending on an object's `equals()`/`hashCode()` implementation.

~~~java
IdentityHashMap<Object, Integer> seen = new IdentityHashMap<>();
seen.put(node, 1);
Integer previousId = seen.get(node); // 1 when it is the same node instance
~~~

The snippet above only illustrates usage inside a method; it requires `import java.util.IdentityHashMap;`. Do not use `System.identityHashCode(obj)` as a **unique ID** because hashes can collide. In the complete example, we assign sequentially increasing integer IDs in visit order and store them in `IdentityHashMap`.

**Correct order:** upon seeing a new node, assign its ID and put it into `seen` **before** traversing its children. If you wait until finishing children to mark it, a cycle `A → B → A` can still loop infinitely.

## 3. Defining the Tool's Scope and Budgets

Before scanning, you must decide what is permitted to be read. This lesson's example enforces explicit policies:

1. **Leaf objects:** `null`, `String`, `Number`, `Boolean`, `Character`, `enum`, and `Class` are printed by value without expanding their fields. The leaf set can be extended per domain; in untrusted environments, even `toString()` on a `Number` subclass could have side effects, so only print explicitly allowed types.
2. **Arrays:** use `Array.getLength`/`Array.get` to read both primitive and reference arrays. Truncate after `maxArrayItems` elements.
3. **Application objects:** walk instance fields from the class up through superclasses, skipping `static` and `synthetic`; attach the **declaring class** to the field name to distinguish fields hidden by subclasses.
4. **JDK objects that are neither leaves nor arrays:** in the demo, stop as an **opaque** node and do not reflect into internal fields in `java.*` packages. This is a sample policy, not a substitute for a package/type allowlist needed in production.
5. **Read permissions:** check `Field.canAccess(receiver)`; when inaccessible, `trySetAccessible()` is attempted only if permitted by policy. If still inaccessible, print `<inaccessible>`. Do not assume every module permits deep reflection.
6. **Limits:** `maxDepth` caps nesting depth, `maxNodes` caps the number of new objects/arrays expanded, and `maxArrayItems` caps array elements inspected.
7. **Ordering:** sort fields by name and then by declaring class. `getDeclaredFields()` makes no order guarantee; never rely on raw array order to build repeatable snapshots.
8. **Do not call getters automatically:** the example only reads fields. Arbitrary getters and `toString()` can run business logic, perform I/O, mutate state, or throw exceptions.

Note: **depth/node/element limits are not a sandbox against adversarial data**. A class with too many fields, an unsafe `toString()` call, a getter, or arbitrary collection traversal can still exhaust resources. Production requires additional budgets for time, field count, string length, output bytes, cancellation, and allowlisted adapters.

## 4. Complete Java 17+ Example: `IdentityHashMap`, Arrays, and Cycles

Create a file **`ObjectGraphDemo.java`** and copy the entire program:

~~~java
import java.lang.reflect.Array;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.IdentityHashMap;
import java.util.List;

public class ObjectGraphDemo {
    private static final class Node {
        private final String name;
        private Node next;
        private Object[] items;

        private Node(String name) { this.name = name; }
    }

    private static final class Walker {
        private final IdentityHashMap<Object, Integer> seen = new IdentityHashMap<>();
        private final int maxDepth;
        private final int maxNodes;
        private final int maxArrayItems;

        private Walker(int maxDepth, int maxNodes, int maxArrayItems) {
            this.maxDepth = maxDepth;
            this.maxNodes = maxNodes;
            this.maxArrayItems = maxArrayItems;
        }

        private static boolean leaf(Class<?> type) {
            return type.isPrimitive()
                    || type == String.class
                    || Number.class.isAssignableFrom(type)
                    || type == Boolean.class
                    || type == Character.class
                    || type.isEnum()
                    || type == Class.class;
        }

        private static List<Field> fields(Class<?> type) {
            List<Field> result = new ArrayList<>();
            for (Class<?> c = type; c != null && c != Object.class;
                    c = c.getSuperclass()) {
                for (Field field : c.getDeclaredFields()) {
                    int modifiers = field.getModifiers();
                    if (!Modifier.isStatic(modifiers) && !field.isSynthetic()) {
                        result.add(field);
                    }
                }
            }
            result.sort(Comparator.comparing(Field::getName)
                    .thenComparing(f -> f.getDeclaringClass().getName()));
            return result;
        }

        private void visit(String label, Object value, int depth) {
            String pad = "  ".repeat(depth);
            if (value == null) {
                System.out.println(pad + label + ": null");
                return;
            }

            Class<?> type = value.getClass();
            if (leaf(type)) {
                System.out.println(pad + label + ": " + value);
                return;
            }

            Integer id = seen.get(value);
            if (id != null) {
                System.out.println(pad + label + ": ref #" + id);
                return;
            }
            if (depth > maxDepth) {
                System.out.println(pad + label + ": <max depth>");
                return;
            }
            if (seen.size() >= maxNodes) {
                System.out.println(pad + label + ": <max nodes>");
                return;
            }

            id = seen.size() + 1;
            seen.put(value, id); // Must precede exploring children.
            System.out.println(pad + label + ": #" + id + " " + type.getSimpleName());

            if (type.isArray()) {
                int length = Array.getLength(value);
                for (int i = 0; i < Math.min(length, maxArrayItems); i++) {
                    visit("[" + i + "]", Array.get(value, i), depth + 1);
                }
                if (length > maxArrayItems) {
                    System.out.println(pad + "  ... <array truncated>");
                }
                return;
            }

            if (type.getPackageName().startsWith("java.")) {
                System.out.println(pad + "  <opaque JDK object>");
                return;
            }

            for (Field field : fields(type)) {
                String fieldLabel = field.getDeclaringClass().getSimpleName()
                        + "." + field.getName();
                try {
                    if (!field.canAccess(value) && !field.trySetAccessible()) {
                        System.out.println(pad + "  " + fieldLabel + ": <inaccessible>");
                        continue;
                    }
                    visit(fieldLabel, field.get(value), depth + 1);
                } catch (IllegalAccessException | RuntimeException ex) {
                    System.out.println(pad + "  " + fieldLabel + ": <inaccessible>");
                }
            }
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        a.next = b;
        b.next = a;
        a.items = new Object[] {b, "tail"};

        System.out.println("== graph ==");
        new Walker(4, 20, 10).visit("root", a, 0);

        System.out.println("== limits ==");
        new Walker(0, 1, 10).visit("root", a, 0);
    }
}
~~~

In a terminal inside the directory containing the file, using JDK 17+:

~~~bash
javac --release 17 ObjectGraphDemo.java
java ObjectGraphDemo
~~~

Output verified by compiling and running with Java:

~~~text
== graph ==
root: #1 Node
  Node.items: #2 Object[]
    [0]: #3 Node
      Node.items: null
      Node.name: B
      Node.next: ref #1
    [1]: tail
  Node.name: A
  Node.next: ref #3
== limits ==
root: #1 Node
  Node.items: <max depth>
  Node.name: A
  Node.next: <max depth>
~~~

This program defines `Node` as a nested class within the same top-level class as `Walker`; under Java 17+ **nestmate** rules, the code can read `Node`'s private fields when permitted. For classes from other libraries or named modules that do not open their packages, private reads may be blocked and `<inaccessible>` is a valid outcome.

### Explaining the Output in Order

- `root: #1 Node`: first encounter with instance `A`, assigned ID 1 and inserted into `seen` immediately.
- `Node.items: #2 Object[]`: an array is **an object** with its own identity, numbered #2 and walked element by element.
- `[0]: #3 Node`: object `B` has not been seen yet, so it receives ID 3.
- `Node.next: ref #1` under B: `B.next` points back to the already recorded `A`, so traversal stops at this reference instead of looping infinitely.
- `Node.next: ref #3` under A: `A.next` reuses the exact same `B`; it does not create another copy of `B`. This is a shared reference; not necessarily a new cycle.
- The `new Walker(0, 1, 10)` pass uses a **fresh visited table**, expanding only the root at depth 0; objects at depth 1 are cut off with `<max depth>`. The leaf field `Node.name` still reads its value `A`.

Important design point: `seen` is state for **a single walk**, never `static` or shared across requests. Each new walker starts with a fresh ID namespace; furthermore, `IdentityHashMap` is not safe for concurrent mutation by multiple threads.

## 5. Distinguishing Cycle Control from Budget Limits

A recursive snippet like `walk(field.get(value))` is only safe when the graph is known to be an acyclic tree. In a general graph, you must track identity and enforce limits:

| Safeguard | Prevents | Does not solve |
| --- | --- | --- |
| `IdentityHashMap` visited | Re-traversing the same instance, including cycles/aliases | Graphs with unbounded distinct nodes or traversal over unstable data sources |
| Marking *before* entering children | Immediate cycles `A → A` or `A → B → A` | Memory/time quotas |
| `maxDepth` | Excessive stack depth and overly deep traversals | Very wide graphs at shallow depth |
| `maxNodes` | Expanding too many independent objects/arrays | Objects with huge numbers of fields or huge strings |
| `maxArrayItems` | Large arrays causing excessive element reads | Large collections/maps and non-array data |
| Field and type filtering | Accidentally touching static/synthetic fields or JDK internals | Legitimate private access, sensitive data, side effects |
| Sorting fields | Snapshots depending on Reflection array order | Graph changing mid-walk due to concurrent mutation |

**The order of checks also matters:** in the code, null/leaf values are handled first; objects already in `seen` print `ref`; new nodes are checked against depth/node limits afterward. Thus a repeat reference to an already expanded node can still print `ref #id` even deeper than `maxDepth`, while an unexpanded node at that depth prints `<max depth>`.

Strings like `<max depth>` / `<max nodes>` mean **"not yet explored"**, not a null pointer or non-existent object. Do not use a truncated snapshot as proof that a graph is acyclic.

### When You Need to Truly Distinguish Cycles from Aliases

Extend DFS with two structures:

- `seen`: instances discovered across the entire walk (to assign IDs and prevent duplicate traversal).
- `active`: instances currently on the active recursion path.

When visiting a child, if it is in `active`, it is a **back-edge/cycle**; if it is only in `seen` and not in `active`, it is a **shared reference**. Remove the instance from `active` in a `finally` block once its branch finishes, but **never remove it from `seen`**. When traversal is cut off by a limit, preserve a "truncated" flag so missing data is not mistaken for proof of acyclicity.

For snapshot/debug output, `ref #id` alone is usually enough; distinguishing aliases from cycles depends on the application's goal.

## 6. Arrays, Collections, Maps, and Special Types

The example supports **arrays** directly via `java.lang.reflect.Array`:

- `int[]` holds primitives, yet the array itself is still an **object** with identity; `Array.get(array, i)` returns boxed values such as `Integer`.
- `Object[]` can contain nulls, shared-instance elements, or a reference back to the array itself. `seen` handles this provided the array is marked before walking its elements.
- For multidimensional arrays, each sub-array has its own identity. Do not assume all rows have the same length.

**Collections and maps need dedicated adapters**, such as iterating a `List` by index, a `Map` by key/value, or an `Optional` by its value. Do not freely reflect on the internal fields of `ArrayList`/`HashMap`: their internal layout is an implementation detail and may be blocked by JPMS.

When adding adapters:

1. Apply the **same identity table** to containers and elements; a container can also reference itself (e.g., `list.add(list)`).
2. Set element limits to avoid oversized data.
3. Define presentation order; `HashMap`/`HashSet` do not guarantee insertion order. If sorting keys, use only safe comparators for the key type and avoid arbitrarily calling `toString`/`compareTo` on untrusted data.
4. Do not invoke side-effecting getters, lazy collections, or iterators in diagnostic snapshots without explicit policy/authorization.
5. Define policies for `WeakReference`, `AtomicReference`, proxies, records, and ORM lazy proxies; logical references can differ from physical fields.

Objects like `Thread`, `ClassLoader`, `Socket`, or JDK internals are not nodes you should expand deeply by default; it is better to print the type, allowed state, or an `opaque` marker.

## 7. Reflection Access Permissions and Protecting Information

`getDeclaredFields()` returns metadata for private/protected/package-private fields, yet **does not guarantee the caller has permission to read their values**. Code may need `Field.canAccess(receiver)`, `trySetAccessible()`, and `IllegalAccessException` handling; in named modules, packages not `opens` to the caller can block `trySetAccessible()`. Do not force every package to use `--add-opens` just to make a debugger work.

In real applications, consider a **public-only** policy or an explicit allowlist rather than always attempting privilege escalation. This example includes `trySetAccessible()` to demonstrate the technique where permitted; it does not mean every private field should be read in production systems.

You must **redact or skip** passwords, tokens, secret keys, personal information, connection strings, and sensitive HTTP bodies, regardless of field modifiers. Being able to read data via reflection does not grant permission to disclose that data.

A safe output tree might use markers like:

~~~text
user.password: <redacted>
payment.token: <redacted>
jdkObject: #12 SomeJdkType
  <opaque JDK object>
internalField: <inaccessible>
largeGraph: <max nodes>
~~~

When logging, you also need to neutralize escape/control characters and cap string length and total output size; the illustrative example does not implement all of these safeguards yet.

## 8. Consistency and Practical Limitations

- **Complexity:** if each un-truncated node/edge is examined once, graph traversal is roughly `O(V + E)` for the visited portion, aside from reflection and field-sorting costs. `seen` requires `O(V)` memory proportional to encountered instances. Budget caps bound specific resources, without by themselves proving the whole tool meets a time bound.
- **Mutable graphs:** a graph mutating while being read can yield an inconsistent snapshot, or even encounter null or different values between accesses. `IdentityHashMap` does not create an atomic snapshot or thread safety for the object graph. For consistent snapshots, use appropriate snapshotting/locking or read immutable DTOs.
- **Side effects:** `Field.get` does not call getters, but formatting an object via `toString()`, iterators, or user-defined adapters can run arbitrary logic; keep it controlled. In the demo, `Number` leaves are printed via string concatenation; in untrusted systems, narrow the whitelist and normalize values.
- **Class loaders/proxies:** two objects from different class loaders can share the same class name; do not identify objects solely by class name or `System.identityHashCode`. Reference-based identity is what is decisive.
- **Field hiding:** two identically named fields in parent and child are two independent storage slots; the demo prefixes labels with `getDeclaringClass()` to avoid ambiguity. In production, include package/declaring class names if simple class names can collide.
- **Exceptions:** `trySetAccessible()` can be denied, `Field.get` can throw `IllegalAccessException`, and reflecting on exotic or dynamically loaded classes can fail. Never swallow errors and treat failed fields as null.
- **Primitive access:** Reflection may return a wrapper from `Field.get`; if you need to distinguish a primitive declared type, inspect `field.getType()` instead of only `value.getClass()`.
- **Preserving output:** when serializing to JSON, cycles cannot be represented natively as ordinary nested objects. You need a defined schema (`$id`/`$ref` or equivalent), or an explicit cycle-rejection policy.

## 9. Self-Check Questions

1. If two instances have `equals() == true` yet `a != b`, should they be treated as the same node when walking an object graph? **No**; use identity.
2. Why must `seen.put(value, id)` happen before walking child fields? So a cycle returning to the current node is recognized immediately.
3. If `A.child` and `B.child` point to the same `C` and the graph has no cycle, what should the second occurrence of `C` be? **`ref` to the same ID**, because this is an alias.
4. If a private field cannot be read because a module is not open, does that mean the field does not exist? **No**; metadata exists, but access to the value is denied.
5. If traversal stops at `<max depth>`, can you conclude the truncated subgraph has no cycles? **No**.
6. If a `List` contains itself, how should it be handled when adding a List adapter? Assign the List an ID, mark it in `seen` first, then iterate elements and encounter it again as a `ref`.

**Key takeaway:** reading an object graph with Reflection means **traversing a graph by identity with explicit budgets and access permissions**. `IdentityHashMap` + early marking prevent reference cycles; depth/node/array budgets bound the scope; policies for types, fields, access, redaction, and snapshot consistency determine whether the tool is truly safe and reliable.

**Java SE 21 Documentation:** [`IdentityHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/IdentityHashMap.html), [`Class.getDeclaredFields`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getDeclaredFields()), [`Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html), [`Array`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Array.html), [`AccessibleObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html).