# Traversing the Interface Graph and Avoiding Duplicates with Java Reflection

## 1. Objectives and Problem Statement

When using Reflection, a Java class can implement multiple interfaces; each interface in turn can extend multiple other interfaces. Furthermore, a class also inherits interfaces indirectly through its superclasses. Therefore, calling `getInterfaces()` once is usually **not enough** if you want to find **all interfaces with which a type has an inheritance/implementation relationship**.

After this article, you will be able to:

- Distinguish direct interfaces from interfaces inherited indirectly via `extends` and `implements`.
- Build an interface graph traversal algorithm using `Class<?>`, `getInterfaces()`, and `getSuperclass()`.
- Use a `visited` set so that each interface appears only once, even when there is a diamond structure.
- Choose an appropriate traversal order and understand the edge cases: input as an interface, class, array type, or primitive type.
- Distinguish **listing** interfaces from **checking** a type relationship with `isAssignableFrom()`.

Here, "all interfaces" means: **the ancestor interfaces** of the input type; if the input itself is an interface, **do not include the input interface in the result list**. This definition determines how the algorithm is initialized.

## 2. Graph Model: Why Is Traversal Needed?

Consider the following declarations:

```java
interface Root {}
interface Left extends Root {}
interface Right extends Root {}
interface Diamond extends Left, Right {}

class Base implements Left {}
class Child extends Base implements Diamond, Right {}
```

Main relationships:

```text
                  Child
                 /     \
       implements       extends
        /        \          \
    Diamond     Right       Base
     /   \        |           |
   Left  Right   Root         Left
     \     /                    |
       Root                    Root
```

The diagram depicts multiple paths that can lead to the same interface; this is a **directed graph**, not a tree. For example, `Root` can be reached via `Diamond → Left → Root`, `Diamond → Right → Root`, or `Base → Left → Root`. If you simply combine recursive results without recording seen nodes, `Left`, `Right`, and `Root` can be listed multiple times.

In valid Java code, an interface cannot form an inheritance cycle `A extends B` and then `B extends A`. Even so, `visited` is still necessary to handle **multiple paths to the same node**; the correctness of the algorithm does not rely on the assumption that "every node appears on only one path".

## 3. Reflection APIs You Need to Know

| API | Returns | Role |
| --- | --- | --- |
| `type.getInterfaces()` | `Class<?>[]` | **Direct** interfaces declared in a class's `implements` or an interface's `extends`; for a subclass, does not automatically include all interfaces of its superclass. |
| `type.getSuperclass()` | `Class<?>` or `null` | Direct superclass of a class; returns `null` for interfaces, `Object`, primitives, and `void`. |
| `type.isInterface()` | `boolean` | Distinguishes an interface node from a class node so only interfaces are added to the result. |
| `iface.isAssignableFrom(type)` | `boolean` | Checks whether `type` can be assigned to a variable of type `iface`, including the same type itself. |
| `type.getGenericInterfaces()` | `Type[]` | Reads the generic form of direct interfaces, such as `Comparable<String>`; this is a different problem from deduplicating by `Class<?>`. |

**Distinguishing the two query directions:**

- `Child.class.getInterfaces()` only tells you `Diamond` and `Right` declared directly on `Child`.
- To get `Left` and `Root`, you must walk further through superinterfaces and through `Base`.
- `Root.class.isAssignableFrom(Child.class)` returns `true` if you only want to know whether `Child` fulfills the contract of `Root`, without needing to build an interface list yourself.

`Class<?>` represents runtime type identity. Two classes/interfaces with the same binary name defined by two different class loaders can be two distinct `Class<?>` objects. Therefore store **`Class<?>`**, do not use `getSimpleName()` or `getName()` alone as a deduplication key.

## 4. Duplicate-Avoiding BFS Algorithm

We use **Breadth-First Search (BFS)** with an `ArrayDeque` queue and an order-preserving `LinkedHashSet`:

1. If the input is a **class**, enqueue that class to explore its direct interfaces and superclass. If the input is an **interface**, enqueue only its *direct superinterfaces* to exclude the input itself from the result.
2. Poll the front element from the queue. If it is an interface, try adding it to `visited`. If it already exists, skip expanding this node; if new, enqueue its superinterfaces.
3. If it is a class, enqueue its direct interfaces, then enqueue its superclass when non-`null`. Do not add class nodes to the result.
4. Stop when the queue is empty. Convert `visited` into the result list.

**Key invariant:** an interface is expanded only the first time it is added to `visited`. Subsequent encounters with that interface do not produce duplicate result elements and do not re-traverse all of its ancestors.

`LinkedHashSet` preserves **first-seen** order under BFS. The order in the example is an intentional traversal order; it is not a single canonical hierarchy order that every Reflection tool must return. If a product needs a fixed alphabetical display order, sort separately after collection, using the full name together with loader information when needed.

## 5. Standalone Runnable Java 17+ Example

Save the entire code below into a file named **`InterfaceGraphDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

public class InterfaceGraphDemo {

    interface Root {}
    interface Left extends Root {}
    interface Right extends Root {}
    interface Diamond extends Left, Right {}

    static class Base implements Left {}
    static class Child extends Base implements Diamond, Right {}

    /**
     * Lists all ancestor interfaces of type using BFS,
     * excluding type itself when type is an interface.
     */
    public static List<Class<?>> allInterfaces(Class<?> type) {
        Objects.requireNonNull(type, "type");

        Set<Class<?>> visited = new LinkedHashSet<>();
        Deque<Class<?>> pending = new ArrayDeque<>();

        if (type.isInterface()) {
            pending.addAll(Arrays.asList(type.getInterfaces()));
        } else {
            pending.addLast(type);
        }

        while (!pending.isEmpty()) {
            Class<?> current = pending.removeFirst();

            if (current.isInterface()) {
                // Already seen via another branch: do not add and do not traverse again.
                if (!visited.add(current)) {
                    continue;
                }
                pending.addAll(Arrays.asList(current.getInterfaces()));
            } else {
                // Direct interfaces of the current class.
                pending.addAll(Arrays.asList(current.getInterfaces()));

                // A subclass can inherit interfaces through its superclass.
                Class<?> parent = current.getSuperclass();
                if (parent != null) {
                    pending.addLast(parent);
                }
            }
        }

        return new ArrayList<>(visited);
    }

    private static String names(Collection<Class<?>> types) {
        return types.stream()
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        System.out.println("Direct Child: "
                + names(Arrays.asList(Child.class.getInterfaces())));
        System.out.println("All Child: " + names(allInterfaces(Child.class)));
        System.out.println("All Base: " + names(allInterfaces(Base.class)));
        System.out.println("All Diamond: " + names(allInterfaces(Diamond.class)));
        System.out.println("All Root: " + names(allInterfaces(Root.class)));
        System.out.println("All int: " + names(allInterfaces(int.class)));
        System.out.println("Assignable: "
                + Root.class.isAssignableFrom(Child.class));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac InterfaceGraphDemo.java
java InterfaceGraphDemo
```

Expected output of the program:

```text
Direct Child: [Diamond, Right]
All Child: [Diamond, Right, Left, Root]
All Base: [Left, Root]
All Diamond: [Left, Right, Root]
All Root: []
All int: []
Assignable: true
```

**Output explanation:**

- `Direct Child` has the exact two interfaces declared in `Child`'s `implements`.
- BFS on `Child` visits `Diamond` then `Right`. Next, the algorithm visits `Left` (from `Diamond`) and `Root`. Subsequent encounters with `Right`, `Left`, and `Root` via other branches are all skipped.
- `Base` only declares `Left`, yet also has `Root` via `Left extends Root`.
- For the input `Diamond.class`, we intentionally start from `Left` and `Right` so **we do not include `Diamond` in the result**.
- `Root` has no superinterface. `int` has no interfaces. Both yield an empty list, but for different reasons.
- `isAssignableFrom` returns `true` because `Child` indirectly implements `Root`.

## 6. Why Does the Algorithm Neither Miss Nor Duplicate Interfaces?

**Completeness:** every ancestor interface has a valid edge chain leading from the input type via `getInterfaces()` or via `getSuperclass()` then `getInterfaces()`. The algorithm enqueues adjacent nodes step by step, so it will reach every reachable ancestor interface.

**No duplicates:** only one `visited.add(current)` operation returns `true` for each `Class<?>` object. Every subsequent encounter gets `false` and hits `continue`, so the result contains each interface exactly once.

**Termination:** the number of classes on the `getSuperclass()` chain and the number of ancestor interfaces of a loaded Java type are finite. A superclass is only enqueued by its subclass; each interface is expanded only once. The queue will eventually become empty.

If we let `V` be the number of reachable class/interface nodes and `E` be the number of inheritance/implementation edges examined, time complexity is **O(V + E)**. Space used by the queue and visited set is at most **O(V + E)** in this implementation, because an interface can be enqueued from multiple edges before being processed. Converting `visited` to `ArrayList` takes an additional O(V).

BFS avoids the call depth limits of pure recursion. A DFS version with `HashSet` or `LinkedHashSet` is also correct if `visited.add(...)` is checked **before** recursing into superinterfaces; the main differences are result order and call stack usage.

## 7. Commonly Confused Cases

### 7.1. Taking Only `getInterfaces()` of the Subclass

Wrong for the goal of "all interfaces": `Child.class.getInterfaces()` does not automatically return `Left` via `Base` and does not expand `Root`. You must traverse both kinds of edges: **interface → superinterface** and **class → superclass**.

### 7.2. Using a `List` and Adding Unconditionally

If you merely accumulate interfaces along branches, a diamond structure produces duplicate elements. Use `Set<Class<?>>` to check identity before traversing further. Do not merely filter with `distinct()` at the end: doing so does not prevent shared branches from being processed multiple times during traversal.

### 7.3. Using Interface Names as Keys

`getSimpleName()` can collide across packages. `getName()` distinguishes packages, yet is insufficient when the same name is defined in different class loaders. Keying by `Class<?>` tracks exact runtime types; only use names for **display**.

### 7.4. Confusing Relationship Checks with Ancestor Enumeration

If you only need to ask "Does `Service` implement `Runnable`?", use:

```java
boolean implementsRunnable = Runnable.class.isAssignableFrom(Service.class);
```

This is an **illustrative snippet**, assuming `Service` is an already-defined class. Only when you need the list of all interfaces to build documentation, inspect annotations, analyze types, or generate Reflection reports do you need the traversal algorithm.

Specifically, `SomeInterface.class.isAssignableFrom(SomeInterface.class)` is `true`, whereas `allInterfaces(SomeInterface.class)` by **the definition in this article** does not contain `SomeInterface.class` itself.

### 7.5. Ignoring Array Types and Special Types

- `String[].class` has direct interfaces `Cloneable` and `java.io.Serializable` according to Java's array type model, even without an `implements` clause in source code.
- Primitives like `int.class` and `void.class` have no interfaces and no superclass.
- Interfaces have `getSuperclass() == null`, so you must discover superinterfaces using `getInterfaces()`.
- `Object.class` has no superclass; the loop must handle `null` safely.

### 7.6. Mixing Up Raw Interfaces and Generic Forms

For example, `class X implements Comparable<String>`: `getInterfaces()` returns the `Class` object of `Comparable`, whereas `getGenericInterfaces()` can represent `Comparable<String>` as a `ParameterizedType`. The algorithm here finds **interface identity**, not inferring or unifying type parameters while walking generic chains. If you need an exact `Type` model, you must solve the type variable mapping problem separately, not merely swap `getInterfaces()` for `getGenericInterfaces()`.

### 7.7. Assuming the Order Is a Business Contract

`LinkedHashSet` preserves encounter order under BFS, while branch priority is influenced by the direct interface order provided by the API and the order in which superclasses are enqueued. If you need a list sorted by name, sort explicitly; if you need closest depth, compute and store depth. Do not treat the index in the result as a default "inheritance precedence".

## 8. Checklist for Production Code

- **Lock down the output definition:** ancestors only, or include the input interface itself? This example chooses **not to include it**.
- **Follow all edges:** direct interfaces, superinterfaces of interfaces, and superclasses of classes.
- **Visit once:** only expand an interface the first time `visited.add` returns `true`.
- **Right identity:** use `Class<?>` as the key, not name strings.
- **Handle inputs:** check `null`, interface types, classes, arrays, primitives; do not rely on an `implements` statement in source code.
- **Separate concerns:** to check a single type relationship, prefer `isAssignableFrom()`; only traverse the graph when you need to list all relationships.
- **Verify diamond structures:** for example, `Diamond` must yield `Root` exactly once; inheritance through `Base` must not produce duplicates either.

**Takeaway:** Java's interface model is viewed from Reflection as a graph with converging branches. Traverse every necessary edge, but use `visited` keyed by `Class<?>` identity to process each interface exactly once.