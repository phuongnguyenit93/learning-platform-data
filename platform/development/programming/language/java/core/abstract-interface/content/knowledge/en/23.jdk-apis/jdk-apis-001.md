# Collection, List, and AbstractList: Contracts and Skeletal Implementation

In the Java Collections Framework, Collection and List describe the **usage contract** of a collection of elements, while AbstractList provides a partial **base implementation** so you do not have to rewrite every behavior of a list. Clearly understanding this boundary helps you choose the right data type, implement a custom List safely, and avoid bugs involving indices, iterators, structural modifications, or performance.

## 1. Relationships Between Types

~~~text
Iterable<E>
   |
   v
Collection<E>                 Map<K, V> is a separate branch
   |
   v
List<E>
   ^
   | implements
AbstractList<E>  (abstract class)
   ^
   |
TaskList       (concrete class defined by the application)
~~~

- **Collection&lt;E&gt;** is the root interface for many kinds of element groups and extends Iterable&lt;E&gt;. It provides general operations such as reading the size, iterating, searching, adding, and removing elements.
- **List&lt;E&gt;** is a subinterface of Collection&lt;E&gt;. List represents an ordered sequence, supports index-based access, and allows duplicate elements.
- **AbstractList&lt;E&gt;** is an abstract class that partially implements the List contract. It extends AbstractCollection and provides common algorithms built on a few core operations that subclasses must define.
- **ArrayList&lt;E&gt;** and **LinkedList&lt;E&gt;** are built-in implementations. When a custom list type is needed, you can extend AbstractList or AbstractSequentialList depending on the storage structure.
- **Map&lt;K, V&gt;** does not extend Collection. Map models key-value mappings; views such as keySet(), values(), and entrySet() are what provide the corresponding Collections.

Distinguish between three questions: what the interface specifies callers are expected to do; what algorithms the abstract class provides out of the box; how the concrete class stores data and which operations it supports.

## 2. The Collection Contract

Collection&lt;E&gt; describes a group of elements that callers can manipulate through a unified API, regardless of whether the underlying data is stored in an array, linked list, hash table, or another structure.

Main method groups:

| Group | Representative Methods | Meaning |
|---|---|---|
| Size | size(), isEmpty() | Read the number of elements or check if empty |
| Search | contains(Object), containsAll(Collection) | Check for an element or a group of elements |
| Iteration/conversion | iterator(), toArray() | Iterate over or convert elements to an array |
| Modification | add(E), remove(Object), clear() | Add, remove an element, or remove all elements |
| Bulk operations | addAll(), removeAll(), retainAll() | Union, remove, or retain only the intersection according to each method's contract |
| Modern APIs | removeIf(), stream(), parallelStream(), spliterator(), forEach() | Filter, process streams, or iterate using callbacks |

Key points in the contract to remember:

- Collection does not inherently guarantee iteration order. Ordering depends on the subinterface and concrete implementation.
- Collection does not mandate allowing duplicate elements or null under a single rule for all implementations. Specific contracts may allow or reject them.
- Some modification operations are **optional operations**. Implementations that do not support an operation may throw UnsupportedOperationException.
- add(element) returns true if the call changed the Collection. For collections that do not allow duplicates, adding an element that is already present may return false.
- You should not assume that every type of Collection defines equals() and hashCode() by content in the same way. List and Set have their own contracts for these methods.

Interfaces help code depend on the required behavior rather than on a concrete class. For example, a method accepting Collection&lt;String&gt; can handle many kinds of collections without needing to know whether the data comes from an ArrayList or a HashSet, provided the method relies only on the guarantees of Collection.

## 3. The List-Specific Contract

List&lt;E&gt; adds the semantics of an **ordered sequence**. Each element has a position, starting at index 0; equal elements can appear at multiple positions.

Important rules:

- get(index) reads the element at the given position. An index that is negative or greater than or equal to size() results in IndexOutOfBoundsException.
- add(index, element) inserts the element at that position and shifts subsequent elements to the right. Valid insertion indices are from 0 to size(), inclusive.
- set(index, element) replaces the existing element at that position and returns the old element. It does not change the size of the list.
- remove(index) removes the element at that position, returns the removed element, and shifts subsequent elements to the left.
- indexOf(value) finds the position of the first occurrence; lastIndexOf(value) finds the last position. If not found, the result is -1.
- iterator() iterates in the order of the List. listIterator() additionally supports moving backward, inspecting indices, and performing certain modification operations if supported by the implementation.
- Two Lists are equal under the List contract when they have the same size and the elements at each corresponding position are equal according to equals rules. Ordering therefore affects a List's equals() and hashCode().

A List can still be immutable, read-only, fixed-size, or mutable. The interface does not mean every modification method is supported. Read the contract of the implementation in use and do not infer mutability from the List type alone.

## 4. What Does AbstractList Provide?

AbstractList is a **skeletal implementation**: a partial, pre-built implementation of the List interface. The goal is to reduce the number of methods you have to write yourself when a subclass can provide index-based element access.

Typically, a subclass must implement at minimum:

- get(int index): retrieve the element at the index.
- size(): return the number of elements.

With just these two methods, the subclass can inherit many behaviors such as iterator/listIterator, contains, indexOf, lastIndexOf, equals, hashCode, and subList. Several modification methods in AbstractList throw UnsupportedOperationException by default, so a read-only subclass may not need to override them.

If you want a mutable list, the subclass usually needs to override additional operations that fit its storage design:

- set(int index, E element) if replacing elements is allowed.
- add(int index, E element) if insertion is allowed.
- remove(int index) if removal is allowed.

AbstractList can derive other operations from these methods. For example, add(element) calls add(size(), element); clear() and modifying iteration operations rely on the element-removal mechanism. If only a subset of operations is supported, you must verify explicitly whether the remaining operations are safely inherited or must throw UnsupportedOperationException.

**Choosing the right base class for the data structure:**

- Use AbstractList when index-based access has suitable performance, such as an array or storage where positions can be read directly.
- Use AbstractSequentialList when the data structure uses sequential access, such as a linked list. If get(index) has to traverse multiple nodes one by one, AbstractList's default algorithms can incur O(n²) cost when iterating over the entire list.
- Consider composition (holding an internal List object and delegating) if the goal is only to wrap or restrict the API of an existing List. Extending AbstractList is useful when you genuinely want to define a List type with a clear contract.

## 5. Java 17+ Example: Implementing a Custom List with AbstractList

The following example creates TaskList, a list of strings backed by an ArrayList for storage. The subclass only defines how to read, replace, insert, and remove elements; the remaining behaviors are inherited from AbstractList.

~~~java
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.RandomAccess;

public class AbstractListDemo {
    private static final class TaskList
            extends AbstractList<String> implements RandomAccess {
        private final ArrayList<String> elements = new ArrayList<>();

        @Override
        public String get(int index) {
            return elements.get(index);
        }

        @Override
        public int size() {
            return elements.size();
        }

        @Override
        public String set(int index, String element) {
            return elements.set(index, element);
        }

        @Override
        public void add(int index, String element) {
            elements.add(index, element);
            modCount++;
        }

        @Override
        public String remove(int index) {
            String removed = elements.remove(index);
            modCount++;
            return removed;
        }
    }

    public static void main(String[] args) {
        List<String> tasks = new TaskList();

        tasks.add("read");
        tasks.add("test");
        System.out.println("initial = " + tasks);
        System.out.println("indexOf(test) = " + tasks.indexOf("test"));

        tasks.set(0, "design");
        System.out.println("after set = " + tasks);
        System.out.println("subList = " + tasks.subList(0, 1));

        tasks.remove(1);
        System.out.println("after remove = " + tasks);

        Iterator<String> iterator = tasks.iterator();
        tasks.add("deploy");
        try {
            iterator.next();
        } catch (ConcurrentModificationException ex) {
            System.out.println("iterator detected structural change");
        }

        System.out.println("final = " + tasks);
    }
}
~~~

Save it to the file AbstractListDemo.java, then compile and run:

~~~text
javac AbstractListDemo.java
java AbstractListDemo
~~~

Stdout output:

~~~text
initial = [read, test]
indexOf(test) = 1
after set = [design, test]
subList = [design]
after remove = [design]
iterator detected structural change
final = [design, deploy]
~~~

### Why Does This Example Work?

1. TaskList provides get() and size(), so AbstractList has enough information to implement many read and iteration operations.
2. add(int, element) and remove(int) delegate data changes to the internal ArrayList. After the operation succeeds, they increment TaskList's modCount so that iterators provided by AbstractList detect structural modifications.
3. set() only replaces the value at a position without changing the size or structure of the list, so it does not increment modCount.
4. indexOf() and subList() are inherited from the base class. subList() creates a **view** backed by the original list, rather than always copying all elements into a new list.
5. After creating the iterator, the program adds an element using the list. The subsequent call to next() detects that modCount has changed and throws ConcurrentModificationException.

RandomAccess is a marker interface with no methods. It signals that TaskList's index-based access is suitable for algorithms optimized for random access. In the example, get(index) calls ArrayList.get(index), which has constant-time index access cost under the usual model.

## 6. modCount, Structural Modifications, and Iterators

AbstractList provides the protected field modCount to support the iterator's fail-fast mechanism. When a subclass structurally modifies the list, it must update this field according to AbstractList's contract.

A structural modification is typically an operation that changes the size or modifies the structure in a way that makes an ongoing iteration unreliable, such as adding or removing elements. Replacing a value with set() is generally not a structural modification.

Implementation rules:

- Only increment modCount after the structural modification has succeeded. If an add or remove operation fails due to an invalid index, the list has not changed, so modCount must not be incremented.
- Each operation that structurally modifies the list must update modCount properly according to AbstractList's contract; do not increment it arbitrarily in read methods or set().
- If overriding additional modification methods or using multiple wrapper layers, avoid updating modCount twice for the same structural modification.
- Iterators provided by the base class use the recorded modCount value to detect modifications made outside the iterator. This mechanism helps catch programming bugs in many situations.
- Fail-fast is only a best-effort bug-detection mechanism, not a synchronization guarantee. Do not use ConcurrentModificationException as a way to coordinate threads, and do not treat AbstractList as thread-safe.

When modification through ListIterator needs to be supported, check the execution paths of add(), remove(), and set() on the iterator. These methods must be compatible with how the subclass updates its data and modCount. If writing a custom iterator, the subclass must also clearly define how external modifications are detected.

## 7. subList Is a View, Not Necessarily a Copy

List.subList(fromIndex, toIndex) returns a view of the range from fromIndex (inclusive) to toIndex (exclusive). For example, subList(0, 1) of the list [design, test] represents the range [design].

- Element changes made through the view are reflected in the backing list and vice versa according to the List contract.
- Structurally modifying the backing list outside the view while the view is still in use can make the view's behavior undefined under the contract or throw ConcurrentModificationException depending on the implementation.
- If an independent list is needed, create an explicit copy, such as new ArrayList<>(source.subList(from, to)).

Do not hold onto a subList long-term and arbitrarily insert into or remove from the original list without considering the view's lifecycle. This is an easy bug to introduce when a slice of a list is passed to another class for processing.

## 8. Choosing an Implementation and Avoiding Pitfalls

| Need | Typically Suitable Choice | What to Check |
|---|---|---|
| General-purpose list, fast index access, mutable | ArrayList&lt;E&gt; | Middle insertion/removal cost, mutability |
| Node-based index access or sequential traversal | LinkedList&lt;E&gt; or a suitable sequential implementation | Index access cost and memory usage |
| Custom List type with random-access storage | Extend AbstractList&lt;E&gt; | get, size, modification operations, modCount |
| Custom List type with sequential storage | Consider AbstractSequentialList&lt;E&gt; | listIterator and traversal performance |
| Custom read-only list | AbstractList with get and size, without exposing modification operations | Mutator operations may throw UnsupportedOperationException |
| Independent mutable copy | new ArrayList<>(source) | Copies element references, does not automatically deep-copy objects |

Common pitfalls:

- **Assuming Collection is always ordered:** rely only on the contract of the specific interface. List is ordered; Collection in general does not guarantee this.
- **Assuming List is always mutable:** List.of(...) is unmodifiable; Arrays.asList(...) has a fixed size, allowing set() but not supporting add/remove in the usual way.
- **Forgetting the optional operation case:** an operation may be type-valid yet rejected by an implementation with UnsupportedOperationException.
- **Not checking indices:** insertion allows index == size(); get, set, and remove do not.
- **Forgetting to update modCount:** AbstractList's iterator may fail to properly detect structural modifications if the subclass forgets to update this field.
- **Incrementing modCount in set():** replacing an element at an existing position is not a normal structural modification; incrementing it improperly will cause iterators to fail unnecessarily.
- **Using AbstractList for sequential storage without considering complexity:** algorithms based on get(index) may traverse the list multiple times.
- **Treating subList as a copy:** a view is linked to the backing list; copy it if independent data is needed.
- **Relying on fail-fast for thread safety:** modCount does not replace locks, synchronization, or proper concurrency design.

## 9. Checklist When Implementing AbstractList Yourself

Before using a subclass in an application, check the following points:

1. get(index) returns the correct element and handles invalid indices consistently with the contract.
2. size() always reflects the actual number of elements.
3. set(), add(index, element), and remove(index) are supported only when the class can genuinely define those semantics.
4. Insertion/removal updates modCount exactly once per successful structural modification; set() does not increment modCount merely for replacing a value.
5. Inherited operations such as clear(), addAll(), iterator.remove(), and listIterator() work properly with the operations the subclass supports.
6. The complexity of get(index) is suitable for AbstractList; if index access is sequential, consider AbstractSequentialList.
7. The contract regarding null, duplicate elements, mutability, and thread safety is clearly described.
8. Test the behavior of equals(), hashCode(), subList(), iterators, and boundary indices, not just basic add/remove.

## 10. Self-Check

1. What is the core difference between Collection and List? Collection describes a general group of elements; List adds ordering, indexing, and sequence semantics.
2. Why does AbstractList reduce the work when implementing List? It provides many algorithms out of the box based on get(), size(), and core operations defined by the subclass.
3. What does a read-only class extending AbstractList need at minimum? Typically get() and size(); modification operations can throw UnsupportedOperationException by default.
4. Why does the example increment modCount after add/remove but not after set? Adding/removing changes the structure; replacing a value at an existing position does not change the size.
5. Should AbstractList be used if get(index) has to traverse multiple nodes? You should generally consider AbstractSequentialList to avoid index-based algorithms incurring repeated costs.
6. Is subList() an independent copy? No; it is a view of a range of the backing list according to the List contract.
