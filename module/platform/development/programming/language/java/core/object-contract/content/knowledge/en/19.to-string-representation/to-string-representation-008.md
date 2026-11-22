# Avoiding Infinite Recursion in Bidirectional References When Writing `toString()`

## 1. The Problem: Two Objects Referencing Back to Each Other

In Java, a **bidirectional** relationship occurs when one object holds a reference to another object and that other object also holds a reference back. For example:

- `Department` has a list of `Employee`s;
- each `Employee` has a `department` reference;
- both classes override `toString()` to print all of those reference fields.

A `Department` object can be viewed as the root of the graph:

```text
Department(ENG)
    |
    | employees
    v
Employee(An)
    |
    | department
    +-------------------> Department(ENG)  (the original object itself)
```

If `Department.toString()` prints the employee list using `employees.toString()`, the list prints each `Employee.toString()`, and then `Employee.toString()` keeps printing the entire `Department`, returning to the starting point. Without a stopping condition, the call chain loops:

```text
Department.toString()
  -> List.toString()
     -> Employee.toString()
        -> Department.toString()
           -> List.toString()
              -> Employee.toString()
                 -> ...
```

The issue happens **even when the model data is completely valid**. Bidirectional relationships are not wrong; traversing every reference in `toString()` without a stopping rule is the cause.

When call depth exceeds stack capacity, the JVM typically throws `StackOverflowError`. You should not use `catch (StackOverflowError)` as a normal strategy: by then the stack is exhausted and recovery or further printing may be unreliable.

## 2. Why String Concatenation Can Also Trigger the Error

You do not necessarily have to call `obj.toString()` explicitly. The following common patterns can lead to a `toString()` call on a non-`null` object:

- `System.out.println(obj)` and `String.valueOf(obj)`;
- `"data=" + obj` or `StringBuilder.append(obj)`;
- string formatting with object arguments, such as `String.format("%s", obj)`;
- `Collection.toString()` or `Map.toString()` when they render elements, keys, or values;
- loggers/debuggers/IDEs when they choose to display an object via `toString()`.

Logging through a framework may evaluate arguments at different times, yet when it ultimately formats the object via `toString()`, the risk remains. Do not assume a log statement is harmless just because the programmer did not type the method name.

In particular, calling `employees.toString()` does not make Java automatically know that `employee.department` should be skipped. Some standard structures have protection for **direct self-containment** in their own printing, but you cannot generalize that into an ability to detect all reference cycles across multiple application objects.

## 3. Implementation Pattern That Leads to Infinite Recursion

Suppose `Department` and `Employee` have fields `employees` and `department`. These are **two illustrative buggy methods**, not a standalone Java program:

```java
// Inside Department:
@Override
public String toString() {
    return "Department{employees=" + employees + "}";
}

// Inside Employee:
@Override
public String toString() {
    return "Employee{department=" + department + "}";
}
```

What happens with a department that has an employee belonging to that very department:

1. Printing `Department` causes `employees` to be converted to a string.
2. The list converts its elements to strings, calling `Employee.toString()`.
3. `Employee.toString()` converts `department` to a string.
4. That is the exact `Department` from step 1. The call chain loops back to the start and continues infinitely.

Having `final` on references does not eliminate cycles. A graph can be structurally immutable yet still contain cycles; a `toString()` that traverses every edge of the cycle will keep looping.

Nor can you solve the root cause by "increasing stack size" to print more levels: it can only delay the overflow, without introducing a stopping condition.

## 4. The Simple and Usually Preferred Approach: Print Only Essential Attributes

Most `toString()` methods exist to support quick observation, debugging, or logging. They **do not need to present the complete object graph**.

For the Department ↔ Employee example, a concise and easy-to-control design is:

- `Department.toString()` displays `code` and the employee count, instead of printing every employee.
- `Employee.toString()` displays `name` and `department.code`, instead of calling `department.toString()`.
- Choose stable, short, useful display values; avoid accidentally pulling in many objects or sensitive data.

Rule of thumb: in a bidirectional relationship, at least **one display direction must stop at identifying information**, such as an ID, code, count, or an `<omitted>` marker.

You can choose `departmentId` instead of the `department` object when displaying an employee. This is a representation choice inside `toString()`; you do not necessarily have to remove the bidirectional relationship from the domain model.

If you need to export the entire structure to JSON or an interchange format, design **serialization/DTOs** with dedicated strategies for back-references, identity, depth, and cycles. `toString()` should not be treated as a general-purpose serializer.

## 5. If You Must Print a Graph: Track Already-Visited Objects

There are diagnostic situations that need to display multiple levels of references. In those cases, `toString()` or a helper function must track the objects **currently on the active recursion path**.

A useful approach is `IdentityHashMap<Node, Boolean>`:

- `IdentityHashMap` compares keys by **reference identity** (`==`), not relying on `equals()`.
- If you are traversing an object and encounter **that exact object again on the same call path**, a cycle is detected.
- Instead of calling `toString()` again, display a short marker such as `Node(A, cycle)`.
- Remove the object from the path set in a `finally` block when finished traversing, even if traversal ends with an exception.

Why compare by identity? Two different objects can have `equals()` return `true` without forming a cycle. Conversely, an object's `equals()` or `hashCode()` itself might traverse bidirectional relationships or depend on mutable data. Using a `HashSet` as the cycle-detection set would call those methods and could cause other errors.

Distinguish two strategies:

- **Active path (current recursion path):** add upon entry, remove upon backtracking. Only mark `cycle` when encountering a node again on the path currently being traversed. A node shared by two different branches can still appear in both branches.
- **Global visited (seen anywhere across any branch):** mark persistently; suitable when you want to avoid printing duplicate nodes, though the second occurrence of a shared node does not necessarily form a **cycle**. If using this strategy, clearly label it `already shown` instead of automatically calling it `cycle`.

Each `toString()` call should use its own traversal context; avoid a shared `static` set across all calls, as that causes interference across prints and across threads.

## 6. Complete Java 17 Example: Bidirectional Relationships and Cyclic Graphs

The program below illustrates two safe strategies:

1. `Department` and `Employee` only display IDs/summaries, so they do not continuously call each other's `toString()`.
2. `Node` allows multi-level link traversal; `IdentityHashMap` detects nodes currently on the traversal path to break cycles.

Create the file **`ToStringCycleDemo.java`**:

```java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;

public class ToStringCycleDemo {
    static final class Department {
        private final String code;
        private final List<Employee> employees = new ArrayList<>();

        Department(String code) {
            this.code = Objects.requireNonNull(code);
        }

        void add(Employee employee) {
            employees.add(Objects.requireNonNull(employee));
            employee.department = this;
        }

        @Override
        public String toString() {
            return "Department{code='" + code + "', employeeCount="
                    + employees.size() + "}";
        }
    }

    static final class Employee {
        private final String name;
        private Department department;

        Employee(String name) {
            this.name = Objects.requireNonNull(name);
        }

        @Override
        public String toString() {
            String departmentCode = department == null ? null : department.code;
            return "Employee{name='" + name + "', departmentCode='"
                    + departmentCode + "'}";
        }
    }

    static final class Node {
        private final String id;
        private final List<Node> links = new ArrayList<>();

        Node(String id) {
            this.id = Objects.requireNonNull(id);
        }

        void link(Node target) {
            links.add(Objects.requireNonNull(target));
        }

        @Override
        public String toString() {
            return render(this, new IdentityHashMap<>());
        }

        private static String render(Node current,
                IdentityHashMap<Node, Boolean> activePath) {
            if (activePath.containsKey(current)) {
                return "Node(" + current.id + ", cycle)";
            }
            activePath.put(current, Boolean.TRUE);
            try {
                StringJoiner children = new StringJoiner(", ");
                for (Node next : current.links) {
                    children.add(render(next, activePath));
                }
                return "Node(" + current.id + " -> [" + children + "])";
            } finally {
                activePath.remove(current);
            }
        }
    }

    public static void main(String[] args) {
        Department department = new Department("ENG");
        Employee an = new Employee("An");
        Employee binh = new Employee("Binh");
        department.add(an);
        department.add(binh);
        System.out.println(department);
        System.out.println(an);

        Node a = new Node("A");
        Node b = new Node("B");
        a.link(b);
        b.link(a);
        System.out.println(a);

        Node root = new Node("R");
        Node shared = new Node("S");
        root.link(shared);
        root.link(shared);
        System.out.println(root);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 ToStringCycleDemo.java
java ToStringCycleDemo
```

Stdout verified with Java 17:

```text
Department{code='ENG', employeeCount=2}
Employee{name='An', departmentCode='ENG'}
Node(A -> [Node(B -> [Node(A, cycle)])])
Node(R -> [Node(S -> []), Node(S -> [])])
```

**Explanation of output:**

1. `Department` knows two employees and each employee knows the department; even though references are bidirectional, `Department.toString()` **only prints the count** and `Employee.toString()` **only prints the code**. There is no circular call chain.
2. In the graph `A → B → A`, when `render` encounters A a second time, A is still in `activePath`. The function returns `Node(A, cycle)` instead of recursing further.
3. `R` links to **the same S twice**, yet S does not point back to R and is not on the current path after the first branch finishes. Because the code uses an active path and removes the node in `finally`, S is printed in both branches. This is a **shared reference**, not a cycle.
4. `Node.toString()` initializes a new map for each call, so path-tracking state does not leak into another independent call.

This example sequentially traverses a graph that is not concurrently modified. If another thread adds/removes links during printing, an appropriate snapshot or synchronization policy is needed; a per-call `IdentityHashMap` does not by itself make link lists safe against concurrent updates.

## 7. Limitations of Cycle-Detection Solutions

Detecting cycles **does not mean eliminating all deep-recursion risks**.

### 7.1. Acyclic Graphs Can Still Be Very Deep

A long chain `A → B → C → ...` with hundreds of thousands of nodes can overflow the stack even without ever revisiting a node. If printing large or externally supplied graphs, you should bound:

- **maximum depth**, e.g., printing only 3–5 link levels;
- **maximum number of nodes/edges** allowed to be rendered;
- **maximum string length**, avoiding oversized logs;
- or use an **iterative traversal algorithm** (explicit stack/queue) when a large graph representation is genuinely needed.

When hitting a limit, insert a short marker such as `<max-depth>` or `<truncated>` so readers know output was bounded. Do not silently cut the string so that it looks like complete data.

### 7.2. References Printed by Another Formatter

The `activePath` tracker only helps nodes traversed **through the same `render` function**. If during rendering you concatenate `+ someOtherObject`, Java may call `someOtherObject.toString()` outside the current tracking mechanism and recreate the loop.

If multiple object types need to be displayed within the same graph, use **a formatter with a shared traversal context** passed to helper functions, or choose a compact identifying representation for edges you do not traverse further. A single global variable is not a safe shortcut for this design.

### 7.3. Performance and Sensitive Data

A `toString()` that goes too deep or prints entire large collections can consume CPU, memory, and produce huge logs. Printing entire related objects also risks accidentally putting passwords, tokens, emails, or personal information into logs. Output design should be **short, intentional, and free of sensitive fields**, even when data contains no cycles.

With ORM frameworks, having `toString()` read lazy relationships can trigger unintended data loads or fail to access relationships if the persistence context is already closed. Keeping `toString()` to IDs and scalar fields usually avoids both cycles and extra relationship graph loading.

## 8. Do `toString()` Generation Tools Automatically Avoid Cycles?

### 8.1. IDE `toString()` Generators

IDEs can include fields in the output based on user selection. If both `department.employees` and `employee.department` are selected, the generated code can still recurse infinitely. Inspect generated content, especially object-relationship and collection fields.

### 8.2. Lombok `@ToString`

When using Lombok, `@ToString` can include fields in the string; you can use `@ToString.Exclude` to exclude the back-reference side, or `@ToString(onlyExplicitlyIncluded = true)` with `@ToString.Include` to allow only necessary identifying attributes.

Example **illustrative configuration snippet** (requires Lombok dependency, not part of the pure Java demo file above):

```java
@ToString
class Employee {
    private String id;
    @ToString.Exclude
    private Department department;
}
```

This illustrates the exclusion approach, not a standalone runnable program. If multiple classes use Lombok together, you must audit **every bidirectional relationship edge**, especially when changing fields later.

### 8.3. Java Records

Records generate `toString()` automatically from their components. That is convenient for records holding simple values like `String` or `int`; however, records do not make referenced objects inside deeply immutable or cycle-free.

If a component is a graph object whose `toString()` points back to the record or an earlier reference branch, risk still exists. You can override the record's `toString()` to print only appropriate identifying information.

### 8.4. Array and Collection Helpers

`Arrays.deepToString` has a mechanism to handle certain cases where an array holds circular references back to the array/branch currently being traversed, yet **it is not a general cycle printer for arbitrary object graphs**. An element that is a POJO whose `toString()` loops through its own relationships can still cause recursion.

Therefore, do not see a helper with `deep` in its name and infer that all bidirectional references are safe. You must clearly determine data types and traversal boundaries.

## 9. How to Test a Safe `toString()`

For a model with bidirectional relationships, test at least these cases:

1. **Single object:** object with no links; short and readable output.
2. **Simple bidirectional relationship:** `Department → Employee → Department`; no infinite recursion occurs.
3. **Long cycle:** `A → B → C → A`; cycle detector cuts off at the right place.
4. **Self-reference:** `A → A`; stopping condition still works.
5. **Shared non-cyclic reference:** `R → S` via two edges; if using active path, S is not mislabeled as a cycle.
6. **Empty graph, null elements if permitted by the model:** does not throw exceptions due to missing references.
7. **Very deep/wide graph:** has depth and length limits when needed; does not accidentally generate massive logs.
8. **No sensitive data leaked:** check expected output and newly added fields.
9. **ORM impact:** if using lazy relationships, calling `toString()` does not unexpectedly increase query count or depend on an active session.

Example of a regression check placed in Java test code after building graph `A → B → A`:

```java
String output = a.toString();
if (!output.contains("cycle")) {
    throw new AssertionError("Cycle was not prevented");
}
```

This is an **illustrative test fragment**, assuming variable `a` has already been created in the test. Checks should also verify that actual output matches expected structure. Do not intentionally trigger `StackOverflowError` in tests to prove code is broken; instead, test safe designs and review call paths.

## 10. Frequently Asked Questions

### "I only printed the parent object, without calling `child.toString()`, so why did it still fail?"

Because concatenating a collection into a string can cause the collection to call `toString()` on each element. The indirect call path still loops back to the parent.

### "Is omitting `toString()` on one side enough?"

Usually **enough to break one specific cycle** if the remaining side only prints safe data. However, a graph with multiple link paths may still contain other cycles. Inspect all edges the formatter will traverse.

### "Can I use `HashSet` to record visited objects?"

It can be risky if their `equals/hashCode` recurses along relationships or mutates. For the goal of recognizing **the same instance already on the traversal path**, `IdentityHashMap` provides more appropriate and clearer semantics.

### "What if `toString()` encounters `null`?"

`String.valueOf(null)` produces the string `"null"`; however, calling `null.toString()` directly is invalid. In the formatter, check for `null` before accessing fields or following links.

### "Should `toString()` return JSON?"

Not required and usually inappropriate. `toString()` is for readable, diagnostic representation; data exchange with schemas and graph cycles requires serializers/DTOs and explicit configuration. Choose tools by purpose rather than relying on one method to print unbounded graphs.

## 11. Takeaways

- Bidirectional relationships `A → B → A` are normal in models; **printing both sides in `toString()`** can create an infinite call loop.
- The simplest solution is to **print IDs, scalars, or counts** on one or both sides, instead of printing the entire linked object.
- If multiple levels must be printed, track the traversal path by **identity**, stopping when encountering an active node again; distinguish real cycles from shared nodes.
- Create a dedicated traversal context per call, clean up in `finally`, and bound depth/size for large graphs.
- Review `toString()` generated by IDEs, Lombok, records, or frameworks; do not assume they handle all reference cycles automatically.
- Do not rely on `StackOverflowError`, increasing stack size, or log suppression as a root fix. Designing clear traversal paths and stopping conditions is what makes `toString()` safe.