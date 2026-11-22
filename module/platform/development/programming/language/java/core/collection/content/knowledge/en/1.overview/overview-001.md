# What is a Collection and the Problem of Managing Groups of Objects

A program often has to work with **a group of related data**: a task list, a shopping cart, event participants, or pending requests. When the number of elements changes, the program needs a way to add, find, remove, count, and iterate over the entire group while still preserving the desired data rules.

In Java, a **collection** is a way to represent a group of elements as a single object for management and manipulation. The `Collection<E>` interface provides a common contract for many collection types; types such as `List`, `Set`, and `Queue` add specific usage rules.

After this lesson, you will be able to:

- Explain what problem collections solve.
- Distinguish between `Collection`, the Java Collections Framework, and `Collections`.
- Use group-of-objects management operations in a small program.
- Ask questions about ordering, duplicates, and access patterns before choosing a collection type.

The complete programs in this lesson use APIs available since Java 17. They have been compiled with `--release 17` and executed to verify the output.

## 1. From a Single Object to a Group of Objects

Suppose you are writing a task management application. One variable can hold one task:

```java
String task = "Đọc đề";
```

This is an illustrative snippet that could be placed inside a method. When there are many tasks, creating variables `task1`, `task2`, `task3` causes difficulties:

- The actual number of tasks is only known at runtime.
- Finding a task requires manually checking each variable.
- Processing all tasks requires repeating statements.
- Removing a task makes keeping track of the remaining variables messy.
- Different parts of the program might invent different ways to manage them.

We need to represent **the entire group** with a single variable, and then operate on it according to our needs:

| Program need | Desired operation |
| --- | --- |
| User creates a task | Add an element |
| User looks for an existing task | Check for existence |
| User drops a task | Remove an element |
| Display the current number of tasks | Count elements |
| Display the tasks | Iterate over each element |
| Start the list over | Clear all elements |

This is the problem of managing a group of objects. Collections provide a data model and reusable operations for that problem.

### Managing a group also includes the group's rules

Given the same input `Lan, Minh, Lan`, the following two requirements produce different results:

- **Store registration entries:** there are three entries; both entries with the name Lan must be kept.
- **Store unique participants:** if the name is used as the identifier in this simple example, only two people remain.

Therefore, choosing a collection is not just about finding a container that holds many elements. You also have to decide whether duplicate elements are allowed, whether order matters, and how elements will be accessed.

In a real system, a participant's identifier should be a stable value such as a user ID; display names can be duplicated.

## 2. Distinguishing Easily Confused Names

| Name | Meaning |
| --- | --- |
| collection | The concept of a group of elements managed together |
| `Collection<E>` | An interface in `java.util` that declares common operations for many collection types |
| Java Collections Framework | The system of interfaces, implementation classes, and utilities for storing and manipulating groups of data |
| `Collections` | A utility class in `java.util` that provides static methods for working with collections |

Capitalization matters. `Collection` is an interface; `Collections` is a different class. The name "Collections Framework" refers to a broader scope than a single interface.

The `E` symbol in `Collection<E>` represents the element type. For example, `Collection<String>` represents a collection whose elements are of type `String`.

### Collection and Map

`Map<K, V>` stores **key → value** relationships, such as `task ID → task details`. `Map` belongs to the Java Collections Framework, but **does not extend `Collection`**.

This distinction affects design decisions:

- If you need to manage a group of tasks, consider collection types.
- If you frequently need to look up a task by its own ID, consider the key–value model of `Map`.

Some data views of a map can be represented as collections, but that does not make `Map` itself a `Collection`.

## 3. What Do Arrays Solve?

Arrays also store multiple elements and are very useful when the number of slots is fixed. However, the length of **an array object** cannot change after it is created.

Illustrative example inside a method:

```java
String[] tasks = new String[3];
int used = 0;

tasks[used++] = "Đọc đề";
tasks[used++] = "Viết mã";
```

At this point:

- `tasks.length` is `3`: the number of slots in the array.
- `used` is `2`: the number of tasks the program is currently managing.
- Unassigned slots still hold the default value `null`.

If you want to add more than three tasks, you have to create another array and copy the data over. If you want to remove an element from the middle, you have to decide yourself whether to shift elements and update `used`.

A class like `ArrayList` encapsulates the work of managing that storage structure. The program can focus on "adding a task" instead of manually managing free slots in an array.

| Characteristic | Array | Collection (depends on implementation) |
| --- | --- | --- |
| Number of managed elements | Often must be tracked manually if only part of the array is used | Queried via `size()` |
| Ability to change element count | Must be managed manually on the existing array or by replacing it | May be supported by the implementation class |
| Add, find, remove by object | Write custom logic or use appropriate utilities | Has a common operation contract |
| Element types | Supports both primitive types and reference types | Type parameters use reference types |
| Ordering and duplicate rules | Follows array structure and custom logic | Depends on the collection type |

Not every collection allows adding or removing elements. For example, a list created by `List.of(...)` does not allow structural modifications. You should read the contract of the specific object rather than assuming "every collection can grow and shrink automatically."

Arrays remain the right choice when the data model requires a fixed number of slots or needs to store primitive values directly. Collections carry additional overhead and their own rules; the choice should come from the problem itself.

## 4. Interfaces, Implementation Classes, and Elements

Consider the declaration:

```java
Collection<String> tasks = new ArrayList<>();
```

There are three things to read from this:

1. **`Collection<String>`** is the type of the variable: the code using this variable relies on the contract for managing `String` elements.
2. **`new ArrayList<>()`** creates the actual object: the `ArrayList` class determines how elements are stored and its specific characteristics.
3. **`tasks`** holds a reference to the collection object; that object manages the elements added to it.

You cannot instantiate an object directly with `new Collection<>()` because `Collection` is an interface.

Declaring variables by interface helps code depend only on the capabilities it needs. However, when switching implementation classes, you must still re-verify the data semantics: replacing a list that allows duplicates with a set that eliminates duplicates can change business results.

### Common interface groups

| Group | Guiding question for selection |
| --- | --- |
| `Collection<E>` | Does the code only need general operations such as adding, counting, finding, or iterating? |
| `List<E>` | Do you need an ordered sequence of elements, indexed access, and usually support for duplicates? |
| `Set<E>` | Do you need to guarantee no duplicates according to set rules? |
| `Queue<E>` | Do you need to accept and process elements according to a queue policy? |
| `Deque<E>` | Do you need operations at both ends of the group? |
| `Map<K, V>` | Do you need to associate and look up values by key? |

`List`, `Set`, and `Queue` are part of the `Collection` type hierarchy; `Deque` extends `Queue`. The table shows their primary roles rather than listing the entire inheritance tree of every Java version.

A `Queue` does not necessarily always follow first-in, first-out order; for example, a priority queue has its own element selection policy. Similarly, the `Collection` interface does not promise that all implementation classes have the same iteration order.

### Request only the capabilities actually needed

If a method only iterates over elements, it does not need to require `ArrayList` specifically. If a method needs to retrieve an element by index, `Collection` is not enough because this interface does not declare `get(int)`; in that case, look at the `List` contract.

`Collection` extends `Iterable`, so it can be traversed with a for-each loop.

## 5. Complete Program: Managing Tasks

Create the file **`CollectionIntroDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;

public class CollectionIntroDemo {
    public static void main(String[] args) {
        Collection<String> tasks = new ArrayList<>();

        System.out.println("Ban đầu: " + tasks.size());

        tasks.add("Đọc đề");
        tasks.add("Viết mã");
        tasks.add("Kiểm thử");
        tasks.add("Viết mã");

        System.out.println("Sau khi thêm: " + tasks.size());
        System.out.println("Có Kiểm thử: " + tasks.contains("Kiểm thử"));
        System.out.println("Xóa Viết mã: " + tasks.remove("Viết mã"));
        System.out.println("Xóa Triển khai: " + tasks.remove("Triển khai"));
        System.out.println("Còn lại: " + tasks.size());

        for (String task : tasks) {
            System.out.println("- " + task);
        }

        tasks.clear();
        System.out.println("Sau clear, rỗng: " + tasks.isEmpty());
    }
}
```

Compile and run in the directory containing the file:

```text
javac -encoding UTF-8 --release 17 CollectionIntroDemo.java
java -Dfile.encoding=UTF-8 CollectionIntroDemo
```

Stdout output:

```text
Ban đầu: 0
Sau khi thêm: 4
Có Kiểm thử: true
Xóa Viết mã: true
Xóa Triển khai: false
Còn lại: 3
- Đọc đề
- Kiểm thử
- Viết mã
Sau clear, rỗng: true
```

### Tracing the program execution

1. A new collection has no elements, so `size()` returns `0`.
2. Four `add` calls create four elements. `ArrayList` allows duplicates, so two `"Viết mã"` strings coexist.
3. `contains("Kiểm thử")` checks for existence and returns `true`.
4. `remove("Viết mã")` on this list removes **the first occurrence**, returning `true`; one `"Viết mã"` element remains.
5. `remove("Triển khai")` does not find an element to remove, so it returns `false`.
6. The for-each loop iterates over the three remaining elements in the order of the `ArrayList`.
7. `clear()` removes all elements from the collection, so `isEmpty()` returns `true`.

The variable has type `Collection<String>`, but the ordering and duplicate behavior in this example come from the actual `ArrayList` object.

### Operations just used

| Operation | Meaning in the example |
| --- | --- |
| `add(element)` | Add an element |
| `size()` | Get the current number of elements |
| `contains(element)` | Check whether a matching element exists |
| `remove(element)` | Remove a matching element if present |
| `isEmpty()` | Check whether the collection contains no elements |
| `clear()` | Remove all elements |
| for-each | Process elements one by one |

This is a usage contract, not a guarantee that every class supports modification or has the same execution cost.

For strings in the example, value matching relies on `String`'s `equals` rule. When using custom objects, you need to design appropriate equality rules; in particular, hash-table-based collections also depend on consistency between `equals` and `hashCode`.

## 6. Same Contract, Different Group Rules

The following program uses a method taking `Collection<String>` to display two groups with different rules.

Create the file **`GroupPolicyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;

public class GroupPolicyDemo {
    public static void main(String[] args) {
        List<String> input = List.of("Lan", "Minh", "Lan");

        Collection<String> registrations = new ArrayList<>();
        Collection<String> uniquePeople = new LinkedHashSet<>();

        registrations.addAll(input);
        uniquePeople.addAll(input);

        printGroup("Lượt đăng ký", registrations);
        printGroup("Người tham gia", uniquePeople);
    }

    private static void printGroup(String label, Collection<String> values) {
        System.out.println(label + " (" + values.size() + "): " + values);
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 GroupPolicyDemo.java
java -Dfile.encoding=UTF-8 GroupPolicyDemo
```

Stdout output:

```text
Lượt đăng ký (3): [Lan, Minh, Lan]
Người tham gia (2): [Lan, Minh]
```

### Why are the results different?

- `ArrayList` keeps all three registrations, including two occurrences of `"Lan"`.
- `LinkedHashSet` keeps each string value once and preserves insertion order, so the result is `[Lan, Minh]`.
- `printGroup` only needs `size()` and the group's representation for display, so a `Collection<String>` parameter meets its needs.

This lesson uses `LinkedHashSet` so that the output order is determined by insertion order. You should not switch to another set type and assume the printed order will stay the same.

Here `List.of(...)` creates an unmodifiable input list. The program only reads it and uses `addAll` to copy the elements into two other modifiable collections. `addAll` adds the elements; it does not turn the two target groups into live views of the input list.

This scenario shows: **a shared contract lets you reuse manipulation code, while the collection type determines the data rules**.

## 7. Collections Manage References to Objects

With `Collection<String>`, the elements are references to `String` objects. With `Collection<Customer>`, the elements are references to `Customer` objects.

Two kinds of changes must be distinguished:

- **Structural changes to the group:** adding, removing, or replacing elements according to what the collection type supports.
- **Changes to the underlying object:** updating the data of a mutable object being referenced.

A collection that does not allow structural modification does not automatically make the mutable objects inside it immutable. Adding an object to a collection also does not automatically create an independent copy of that object.

If two variables reference the same collection, changes made through one variable can be observed through the other. Therefore, when passing a collection between parts of a program, you should agree on which side has permission to modify it and whether the receiver needs a copy.

Removing an element from a collection only removes that element from the group. The object may still be referenced elsewhere; calling remove is not a request to immediately destroy the object.

### Primitive types and wrapper classes

You cannot declare `Collection<int>`. Generic type arguments must be reference types, so `Collection<Integer>` is typically used to manage integers under the collection model.

Java can autobox `int` values into `Integer` in appropriate contexts. When choosing between an array of integers and a collection of integers, you need to account for this difference instead of treating the two storage models as identical.

## 8. What the Collection Contract Leaves Undecided

Knowing that an object has type `Collection<E>` still leaves several questions unanswered:

| Question | What to check |
| --- | --- |
| Are duplicate elements allowed? | Rules of the collection type |
| In what order does iteration happen? | Ordering guarantees of the implementation class |
| Is `null` allowed? | Specific contract of the collection |
| Can elements be added or removed? | Modifiability and optional operations |
| Can elements be accessed by index? | Whether the interface used provides that operation |
| Is it safe for multiple threads to use concurrently? | Specified concurrency or synchronization mechanism |
| Are search or removal operations fast? | Storage structure, size, and usage pattern |

For example:

- `List.of(...)` does not accept `null` elements and does not support structural modifications such as `add`.
- A typical mutable collection is not thread-safe by default for concurrent modifications by multiple threads.
- `size()` is the number of elements; it is not information about internal backing memory capacity.
- Operations like `contains` or `remove` can have different costs across implementation classes.

You should treat an interface as the minimum contract that the code relies on, and then check the additional guarantees of the actual object.

## 9. Choosing a Collection for the Problem

You can start with a short process:

1. **Identify what an element is.** In a task application, it could be a description string or a `Task` object with an ID and status.
2. **Identify the group's rules.** Are duplicates allowed, is ordering needed, do you need to pick from the front, or do you need to look up by key?
3. **Identify the primary operations.** Mostly iterating, searching, accessing by index, appending to the end, or taking elements for processing?
4. **Choose the appropriate interface.** Base this on usage needs rather than immediately picking a familiar class name.
5. **Choose the implementation class.** Check modifiability, ordering, valid values, performance cost, and concurrency requirements.
6. **Verify with a small example.** Test with data containing duplicates, an empty group, and a not-found operation.

Some problem formulations:

| Problem | Initial modeling direction |
| --- | --- |
| A list of tasks ordered by user-arranged position | `List` |
| A set of completed task IDs, each ID appearing only once | `Set` |
| Tasks waiting to be taken for processing | `Queue`, with a defined element-selection policy |
| Looking up task details by ID | `Map` |

These are starting points. For example, saying "a list of tasks" in natural language is not enough to conclude that `List` must be used; if the primary requirement is lookup by ID, a key–value structure may be more appropriate.

## 10. Common Mistakes

### Confusing Collection with ArrayList

`Collection` is a broader interface than any single implementation class. Things true of `ArrayList`, such as indexed access or list ordering, cannot be applied as-is to every collection.

### Assuming every collection is modifiable

The `add` method is present in the interface, but the concrete object may not support that operation and throw `UnsupportedOperationException`. Always check how the collection was created and its contract.

### Treating size like array length or backing capacity

Arrays use the `length` field; collections use the `size()` method. The two models do not share the same space-management mechanism.

### Assuming duplicates are removed automatically

For example, `ArrayList` keeps both occurrences of `"Viết mã"`. If you want uniqueness, choose an appropriate model and comparison rule instead of expecting `add` to deduplicate data automatically.

### Arbitrarily modifying structure while iterating

You should not arbitrarily add or remove elements directly while iterating with a for-each loop. Behavior depends on the collection type and iteration mechanism; some usages can fail on concurrent structural modification.

When learning iteration operations, choose a supported mechanism, such as an iterator's operation or `removeIf` on a collection that supports removal. The fact that a single run did not throw an error does not prove that the iteration and modification pattern is valid.

### Choosing a type just because the name is familiar

Write down the data rules first. If requirements like "no duplicates" or "lookup by ID" are not met, writing a cleaner loop still will not solve the right problem.

## 11. Practice

### Exercise 1: predict before running

Using `CollectionIntroDemo`:

1. Change the string to remove from `"Viết mã"` to `"Chưa có"`.
2. Predict the boolean return value of that removal call.
3. Predict the element count and the two remaining occurrences of `"Viết mã"`.
4. Run it again and compare with your prediction.

Point to verify: a removal call that finds nothing must not reduce the element count; whether duplicate elements are allowed is still determined by the collection type.

### Exercise 2: clarify uniqueness rules

In `GroupPolicyDemo`, change the input to `Lan, Minh, Lan, An, Minh`.

Before running, write down:

- The number of registration entries.
- The number of unique name values.
- The order of appearance in the `LinkedHashSet` group.

With the current rules, the two groups should have sizes `5` and `3` respectively; the unique group has the order `Lan, Minh, An`.

### Exercise 3: choose the model before writing code

You need to manage orders. Choose a model for each independent requirement and explain:

- Keep each time a customer adds an item in order.
- Record the set of order IDs that have been sent a notification, without sending duplicates by ID.
- Look up order details by order ID.
- Receive pending orders for processing according to a clear policy.

For each case, state the element type, duplicate requirements, ordering, and primary operations. Only then choose an interface and an implementation class as an example.
