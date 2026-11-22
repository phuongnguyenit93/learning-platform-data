# sorted() by Natural Order or Comparator in Java Stream

## 1. Objectives

When processing data with Java Stream, **sorted()** lets you produce a stream of elements **sorted in order** before passing it to a terminal operation. There are two main forms:

- **No-argument sorted()**: uses the **natural order** provided by elements via **Comparable**.
- **sorted(Comparator)**: uses a **comparison rule passed in by the caller**, suitable when you need multi-field sorting, descending order, null handling, or multiple ways to sort the same data type.

After this lesson, you will be able to read and write both overloads, understand how a comparator returns negative/0/positive values, build criteria with comparing/thenComparing/reversed, know when sorting preserves the initial order of equal elements, recognize the **lazy yet stateful** nature of sorted, avoid mutating the source, and handle common pitfalls with null, generics, overflow, and parallel streams.

## 2. Where does sorted() sit in a pipeline?

Structure of a pipeline:

~~~java
List<Integer> result = List.of(4, 1, 3, 2)
        .stream()
        .sorted()
        .toList();
~~~

**Result:** [1, 2, 3, 4].

Steps:

1. **List.of(...).stream()** creates a Stream from the source list.
2. **sorted()** creates an **intermediate operation**, describing the requirement to emit elements in ascending order.
3. **toList()** is the terminal operation, triggering the pipeline to produce the result.

**sorted is a lazy intermediate operation:** merely calling sorted() does not necessarily read the entire source or invoke the comparator. However, it is also a **stateful operation**: when evaluated, general sorting typically needs to buffer many or all elements before it can start emitting the first element in the right order.

Diagram:

~~~text
Source List
   |
   v
stream() --> filter(...) --> sorted(comparator) --> limit(3)
                                           |
                                           v
                                         toList()
                                           |
                                           v
                                   Ordered result List
~~~

You should not think of sorted as a call that **modifies the list in place**. It creates a new Stream in terms of the operation chain; the source list is not sorted directly unless callbacks and other operations interfere.

## 3. Two overloads of Stream.sorted

Abbreviated signatures:

~~~java
Stream<T> sorted()

Stream<T> sorted(Comparator<? super T> comparator)
~~~

Both return a Stream<T>: sorted **changes the order**, not the element type.

| Form | Rule | Key condition |
| --- | --- | --- |
| **sorted()** | Natural order | Elements must be comparable via an appropriate Comparable |
| **sorted(comparator)** | Order determined by Comparator | Comparator is compatible with T and obeys the comparison contract |
| **IntStream.sorted()** | Ascending integer order | Primitive int; no Comparator overload for IntStream |
| **LongStream.sorted()** | Ascending long order | Primitive long |
| **DoubleStream.sorted()** | Double order according to defined comparison | Need to understand NaN, +0.0/-0.0 if data contains those cases |

The signature **Comparator<? super T>** means the comparator can accept T **or a supertype of T**, because the comparator will consume two T values in each comparison call. For example, **Comparator<Animal>** can compare **Dog** instances, if Dog is a subtype of Animal and the comparator reads common properties on Animal.

## 4. sorted() and Comparable: natural order

**Comparable<T>** is in java.lang and has the method:

~~~java
int compareTo(T other);
~~~

Some Java types already define a natural order:

- **Integer**, **Long**: ascending numeric order.
- **String**: lexicographical comparison by UTF-16 code units of the string, case-sensitive; not automatically synonymous with a locale's alphabetical rules.
- **LocalDate**: chronological date order.
- **BigDecimal**: numeric value order via compareTo; note that compareTo and equals can be inconsistent for values with different scales.
- **Enum**: declaration order of enum constants.

Example:

~~~java
List<String> languages =
        List.of("Java", "Go", "Kotlin", "C", "java");

List<String> sorted = languages.stream()
        .sorted()
        .toList();

System.out.println(sorted);
// [C, Go, Java, Kotlin, java]
~~~

**"Java"** comes before **"java"** because String natural order is case-sensitive. To sort according to specific language rules, you can use a **Collator** configured for the appropriate locale as a Comparator; do not assume String's sorted() handles all language-specific rules.

### 4.1. Custom classes without a natural order

Suppose we have:

~~~java
record Product(String code, long priceVnd) { }
~~~

A Product record **does not automatically implement Comparable<Product>**. Therefore, calling **sorted() without a Comparator** on a Stream<Product> can throw **ClassCastException** when the terminal operation actually needs to compare elements. Do not assume that a record is automatically sortable by its fields.

If the domain data has **a truly singular and stable natural order**, you can have the class implement Comparable with an appropriate compareTo. However, many classes like Order, Product, and Employee have **multiple valid criteria**, so passing a Comparator is usually more flexible and couples the ordering less tightly to the model.

### 4.2. Writing sorted() does not always throw an exception immediately

Because Stream is lazy, errors from non-Comparable elements usually only appear **when the terminal operation requires evaluating the necessary comparisons**. With an empty or single-element source, the implementation may not need any concrete compare call.

**Proper design:** ensure the element type and comparison rules are valid before building the pipeline; do not rely on when an exception is thrown to check Comparable capability.

## 5. sorted(Comparator): choosing rules by purpose

**Comparator<T>** is in java.util and is a functional interface with the SAM:

~~~java
int compare(T left, T right);
~~~

Meaning of the result's sign:

- **Negative**: left comes before right.
- **0**: left and right are **equivalent in order according to the comparator**.
- **Positive**: left comes after right.

It is not required to return only -1, 0, +1; only the **sign** matters. Example:

~~~java
Comparator<Integer> ascending = Integer::compare;
Comparator<Integer> descending = (a, b) ->
        Integer.compare(b, a);

System.out.println(ascending.compare(2, 5) < 0); // true
System.out.println(descending.compare(2, 5) > 0); // true
~~~

A Comparator can be written using a lambda, method reference, or Comparator factory methods. Use a comparator to express **"compare by which property, in which direction, and how to handle ties"**.

### 5.1. Avoid subtracting two numbers when comparing

~~~java
// Unsafe if int overflows:
// Comparator<Integer> bad = (a, b) -> a - b;

Comparator<Integer> safe = Integer::compare;
~~~

If **a = Integer.MAX_VALUE** and **b = -1**, the expression a-b can overflow int, making the sign of the result wrong. Integer.compare handles the ordering relation correctly. For long, use **Long.compare** or **Comparator.comparingLong** instead of casting the difference to int.

When comparing double, **Double.compare** has rules for NaN and -0.0/+0.0; if the business logic does not expect those values, validation or explicit criteria are needed.

## 6. Comparator.comparing and primitive variants

When you want to sort objects by a field, Java provides factory methods:

~~~java
Comparator<Employee> byName =
        Comparator.comparing(Employee::name);

Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::age);

Comparator<Employee> bySalary =
        Comparator.comparingLong(Employee::salary);
~~~

These are illustrative snippets assuming Employee has the corresponding accessors, not a standalone program. **comparingInt/comparingLong/comparingDouble** extract primitive keys without forcing boxing of the key type in the SAM.

Using with Stream:

~~~java
List<Employee> ascendingByAge = employees.stream()
        .sorted(Comparator.comparingInt(Employee::age))
        .toList();
~~~

Differences:

- **Comparator.comparing(Employee::name)**: creates a comparator by a reference key that already has a natural order, typically String.
- **Comparator.comparingInt(Employee::age)**: creates a comparator by an int key.
- **Comparator.comparing(Employee::name, customKeyComparator)**: uses a custom comparator for the key, for example when you want case-insensitive comparison or null handling.

### 6.1. comparing() and null keys

If **name()** returns null and the key comparator is String's natural order, it can throw a NullPointerException when comparison is needed. For keys that may be null, state an explicit policy:

~~~java
Comparator<Employee> byNullableName =
        Comparator.comparing(
                Employee::name,
                Comparator.nullsLast(Comparator.naturalOrder()));
~~~

Here **nullsLast** applies to **the value of the name key**, and does not automatically allow the Employee object itself to be null. If the Employee element itself can be null, you must wrap the element comparator with **Comparator.nullsLast(...)** separately.

## 7. Descending order with reversed and reverseOrder

To reverse the natural order of String:

~~~java
List<String> descending = List.of("Go", "Java", "C")
        .stream()
        .sorted(Comparator.reverseOrder())
        .toList();

System.out.println(descending); // [Java, Go, C]
~~~

**Comparator.reverseOrder()** creates a comparator that reverses the natural order. When you have a custom comparator:

~~~java
Comparator<Integer> byValue = Integer::compare;
Comparator<Integer> reversed = byValue.reversed();
~~~

**reversed()** returns a comparator whose comparison direction is reversed relative to the original comparator; it does not mutate the original comparator.

### 7.1. Be careful with the placement of reversed in multi-key comparators

Suppose you want **highest score first**, and on a tie **name A-Z**:

~~~java
Comparator<Student> byScoreDescNameAsc =
        Comparator.comparingInt(Student::score)
                .reversed()
                .thenComparing(Student::name);
~~~

First reverse the **score** direction; then add the **ascending name** criterion. If you write:

~~~java
Comparator<Student> different =
        Comparator.comparingInt(Student::score)
                .thenComparing(Student::name)
                .reversed();
~~~

then **the entire chain of criteria** is reversed: descending score **and descending name**. Both forms are valid, but they express **different** business rules. Where you call reversed matters greatly.

## 8. thenComparing: multiple priority levels

Some datasets have multiple elements with the same first key. In that case, **thenComparing** lets you add a secondary criterion, which is only used when the preceding criterion considers two elements equal.

~~~java
Comparator<Student> byScoreNameId =
        Comparator.comparingInt(Student::score)
                .reversed()
                .thenComparing(Student::name)
                .thenComparing(Student::id);
~~~

Order:

1. Highest score first.
2. If scores are equal: ascending name.
3. If scores and names are equal: ascending ID.

**thenComparingInt** and the other primitive overloads can also be used when the secondary criterion is numeric:

~~~java
Comparator<Student> byNameThenScore =
        Comparator.comparing(Student::name)
                .thenComparingInt(Student::score);
~~~

If you want a descending secondary criterion, pass a separate secondary comparator:

~~~java
Comparator<Student> byNameThenScoreDesc =
        Comparator.comparing(Student::name)
                .thenComparing(
                        Comparator.comparingInt(Student::score)
                                .reversed());
~~~

The snippets in this section require a Student record/class matching score(), name(), id(). The complete program in section 13 has that definition.

**Placing the ID criterion last** is a business choice that often helps produce a deterministic order even when earlier keys match. However, if you intentionally want to preserve the encounter order of records with the same score and name, you can omit ID and rely on the stability of sorted on an **ordered stream**.

## 9. Stability and encounter order

By the Java Stream contract, **sorted() on an ordered stream is stable**: if the comparator returns 0 for two elements, their original relative order is preserved in the result.

Example source:

~~~text
Student(id=S1, name=An, score=90)
Student(id=S2, name=Binh, score=95)
Student(id=S3, name=An, score=90)
~~~

If the comparator only compares **descending score, then ascending name**, then:

~~~text
S2 (Binh, 95)
S1 (An, 90)
S3 (An, 90)
~~~

S1 and S3 are equal according to the comparator (score 90 and name An), so on an ordered List stream, S1 keeps its relative position before S3.

**On an unordered stream, sorted does not guarantee stability for elements considered equal by the comparator.** The result still obeys the comparison order, but the relative order of elements within the same key group may not be guaranteed. If the business logic needs a consistent order every time, create an **explicit tie-breaker criterion** (ID, creation timestamp, priority order) instead of relying on a nonexistent encounter order.

### 9.1. Comparator returning 0 does not necessarily mean equals

Two Students with the same score and name but different IDs can **differ according to equals**, even though a comparator comparing only score and name returns 0. For Stream.sorted, both elements remain in the result, following the sorting rule.

However, in **TreeSet/TreeMap**, the comparator determines key equivalence: compare(a,b)==0 can prevent an element/key from being added as an independent entry. Therefore, if the same comparator is used for an ordered set/map structure, pay attention to **consistency with equals** and business requirements for unique IDs.

## 10. The Comparator contract must be consistent

A proper Comparator does not just "return a number"; it must define a consistent total order.

Core requirements:

1. **Antisymmetry of sign:** sign(compare(a,b)) = -sign(compare(b,a)).
2. **Transitivity:** if a>b and b>c according to the comparator, then a>c.
3. **Consistency with comparator equality:** if compare(a,b)==0 then comparing a and b with any z must have the same sign.
4. During a sort, the **comparison keys must not change unexpectedly**; a comparator should not depend on time, randomness, or mutable shared state in a way that causes inconsistency.

A Comparator that returns different results across calls can lead to an indeterminate order or an **IllegalArgumentException** from the sorting algorithm when a contract violation is detected. Do not expect an exception every time; many buggy comparators still happen to "finish running" on small datasets.

Example to **avoid**:

~~~java
AtomicInteger counter = new AtomicInteger();
Comparator<Student> unstable = (a, b) ->
        counter.incrementAndGet() % 2 == 0 ? -1 : 1;
~~~

This is a counterexample using a mutable counter to decide the sign. The result does not represent a stable ordering relation between a and b; it changes with the number of times the comparator is called. **AtomicInteger** does not save the comparison contract just because incrementAndGet is atomic.

## 11. nullsFirst and nullsLast

When the source may contain null, natural comparators usually do not handle null. You can create a policy:

~~~java
Comparator<String> nullLast =
        Comparator.nullsLast(Comparator.naturalOrder());

List<String> values =
        Arrays.asList("Bee", null, "Ant", "Cat");

List<String> ordered = values.stream()
        .sorted(nullLast)
        .toList();

System.out.println(ordered);
// [Ant, Bee, Cat, null]
~~~

This snippet requires importing Comparator, List, Arrays. **List.of(...) does not allow null**, so the example uses Arrays.asList to create a list containing null.

- **nullsFirst(comparator)**: null is placed before non-null values.
- **nullsLast(comparator)**: null is placed after non-null values.

If the comparator passed to these wrappers is null, all non-null values are considered equal in order; do not assume that solves the business requirement accurately. You should provide a concrete comparator unless you truly want all non-null values to tie.

**Important:** a null element and a null field are two different situations. To put null fields last, use nullsLast on the key comparator; to put null elements last, wrap the element comparator with nullsLast.

## 12. Operation order in a Stream matters

### 12.1. sorted then limit

~~~java
List<Integer> smallestTwo =
        List.of(7, 1, 9, 3).stream()
                .sorted()
                .limit(2)
                .toList();
~~~

Result **[1, 3]**: sorts the entire source in ascending order, then takes the first two elements.

### 12.2. limit then sorted

~~~java
List<Integer> sortedPrefix =
        List.of(7, 1, 9, 3).stream()
                .limit(2)
                .sorted()
                .toList();
~~~

Result **[1, 7]**: takes only the first two elements of the source (7,1), then sorts them.

Therefore, you cannot arbitrarily swap **sorted().limit(k)** to **limit(k).sorted()**. One takes the **top k best across the entire dataset**; the other sorts the **first k elements**. This difference directly affects ranking problems.

### 12.3. filter before sorted

~~~java
List<Integer> chosen = numbers.stream()
        .filter(n -> n > 0)
        .sorted()
        .toList();
~~~

If the requirement is "take only positive numbers and then sort", filtering first reduces the elements entering the sort step. However, if the filter condition depends on position **after sorting**, you need to define the pipeline accordingly; reordering operations is not always equivalent.

### 12.4. map before sorted

~~~java
List<String> sortedNames = persons.stream()
        .map(Person::name)
        .sorted()
        .toList();
~~~

This is a snippet with an existing Person class and persons variable. It sorts **name Strings** and returns Strings, not the Person objects themselves.

If you need to return Person objects sorted by name, use:

~~~java
List<Person> sortedPersons = persons.stream()
        .sorted(Comparator.comparing(Person::name))
        .toList();
~~~

This distinction is important: **map changes the type**, whereas sorted only changes the order of the current type.

## 13. Standalone Java 17 program

Example usage:

- **sorted()** for String and int.
- **sorted(Comparator)** for Student with descending score, ascending name.
- **Stability** when two Students have the same score and name.
- **nullsLast** when the list contains null.
- **sorted().limit()** and **limit().sorted()**.
- **Stream.toList()** does not mutate the source list.

Create file **StreamSortingDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.IntStream;

public class StreamSortingDemo {
    record Student(String id, String name, int score) { }

    static String label(Student s) {
        return s.id() + ":" + s.name() + ":" + s.score();
    }

    public static void main(String[] args) {
        List<String> languages =
                List.of("Java", "Go", "Kotlin", "C", "java");

        System.out.println("natural: "
                + languages.stream().sorted().toList());

        List<Student> students = List.of(
                new Student("S1", "An", 90),
                new Student("S2", "Binh", 95),
                new Student("S3", "An", 90),
                new Student("S4", "Chi", 95)
        );

        Comparator<Student> byScoreDescNameAsc =
                Comparator.comparingInt(Student::score)
                        .reversed()
                        .thenComparing(Student::name);

        List<Student> ranked = students.stream()
                .sorted(byScoreDescNameAsc)
                .toList();

        System.out.println("ranked: "
                + ranked.stream()
                        .map(StreamSortingDemo::label)
                        .toList());

        System.out.println("original IDs: "
                + students.stream()
                        .map(Student::id)
                        .toList());

        List<String> withNull =
                Arrays.asList("Bee", null, "Ant", "Cat");

        System.out.println("null last: "
                + withNull.stream()
                        .sorted(Comparator.nullsLast(
                                Comparator.naturalOrder()))
                        .toList());

        int[] primitive = IntStream.of(7, 1, 9, 3)
                .sorted()
                .toArray();

        System.out.println("primitive: "
                + Arrays.toString(primitive));

        List<Integer> numbers = List.of(7, 1, 9, 3);

        System.out.println("sorted then limit: "
                + numbers.stream()
                        .sorted()
                        .limit(2)
                        .toList());

        System.out.println("limit then sorted: "
                + numbers.stream()
                        .limit(2)
                        .sorted()
                        .toList());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac StreamSortingDemo.java
java StreamSortingDemo
~~~

**Exact output:**

~~~text
natural: [C, Go, Java, Kotlin, java]
ranked: [S2:Binh:95, S4:Chi:95, S1:An:90, S3:An:90]
original IDs: [S1, S2, S3, S4]
null last: [Ant, Bee, Cat, null]
primitive: [1, 3, 7, 9]
sorted then limit: [1, 3]
limit then sorted: [1, 7]
~~~

### 13.1. Student ordering analysis

The source list has S1, S2, S3, S4. According to the comparator:

1. **S2**: score 95, name Binh.
2. **S4**: score 95, name Chi; tied in score with S2 so name is compared, Binh before Chi.
3. **S1**: score 90, name An.
4. **S3**: score 90, name An; the comparator evaluates S1 and S3 as equal, since both score and name match. On an ordered Stream from List, sorted is **stable**, so S1 comes before S3 by encounter order.

If you add **thenComparing(Student::id)**, the comparator will have a third criterion; then the order within a group tied by score/name is decided by ID instead of relying on stability.

### 13.2. Unchanged source

The **original IDs** line is still **[S1, S2, S3, S4]**. Calling **students.stream().sorted(...)** does not reorder the source List.of. The result list from Stream.toList also does not support mutation, so you cannot call add/set/remove directly on it.

The Student records hold String and int, keeping the data stable in the example. With mutable objects in a real application, the result list **is not deep-copied**; updating a field on a Student can be observed through both the source and the result because they reference the same object.

### 13.3. Primitive sorted

**IntStream.sorted()** always sorts int values in ascending order. If you want larger numbers first in a Stream<Integer> with a Comparator, you can use:

~~~java
List<Integer> descending = IntStream.of(7, 1, 9, 3)
        .boxed()
        .sorted(Comparator.reverseOrder())
        .toList();
~~~

Result **[9, 7, 3, 1]**. Calling **boxed()** converts primitive int to Integer to create a Stream<Integer>; only then can you use the **sorted(Comparator)** overload of a reference Stream. This can incur boxing overhead, so only do it when you genuinely need a comparator rule or object type.

## 14. sorted is lazy yet stateful

Example:

~~~java
Stream<Integer> pipeline = Stream.of(9, 2, 5)
        .sorted();

// No terminal operation here yet.

int minimum = pipeline.findFirst().orElseThrow();
System.out.println(minimum); // 2
~~~

Calling sorted() does not sort immediately when building the pipeline. When **findFirst()** requests the first element after sorting, general sorting typically has to know all elements reaching the sorted stage in order to determine the smallest element. Therefore, **findFirst is not guaranteed to read only one element of the source** when placed after sorted.

This distinguishes sorted from a **stateless** intermediate operation like map/filter. In many sequential pipelines, map/filter can be fused to process one element at a time without buffering the entire result; sorted, on the other hand, is **stateful** and has memory/CPU costs for comparisons.

**Note:** Stream may optimize in certain cases, and some sources are already marked SORTED; you should not treat "always allocates an array of size N" as a JDK contract. Understand the cost risks and the dependence of results on order, rather than relying on implementation internals.

### 14.1. Considerations for large data and infinite Streams

A pipeline that tries to sort **an entire infinite source** cannot complete under general sorting, which needs to inspect all values before emitting the first element. Example:

~~~java
// Avoid without an appropriate limiting step:
// Stream.iterate(1, n -> n + 1).sorted().findFirst();
~~~

If the business logic genuinely only needs the **k best-valued elements from finite data**, consider a top-k algorithm based on a priority queue or a dedicated optimized API when N is very large, instead of always sorting everything. For typical data sizes, sorted().limit(k) remains a clear and safe way to express it when correctness matters more than premature optimization.

### 14.2. sorted and count do not guarantee the comparator is called

An easily misunderstood case:

~~~java
long count = List.of(3, 1, 2).stream()
        .sorted()
        .count();
~~~

**The result is 3**, and for a source with a known size, the count terminal operation can optimize based on the element count without actually performing the sort. Therefore, do not put mandatory business side effects inside Comparator, map, or peek and expect sorted().count() to execute every callback.

## 15. sorted vs. List.sort and Collections.sort

| API | Mutates source? | Result |
| --- | --- | --- |
| **source.stream().sorted(...).toList()** | No, if callbacks do not interfere | New result List in terms of collection, unmodifiable per Stream.toList |
| **source.sort(comparator)** | Yes, on a List supporting mutation | void; the List itself is reordered |
| **Collections.sort(list)** | Yes, on a List supporting mutation | void; sorted by natural order |
| **Collections.sort(list, comparator)** | Yes, on a List supporting mutation | void; sorted by Comparator |
| **Arrays.sort(array)** | Yes, on the array | Changes element order in the array |

Example:

~~~java
List<Integer> original = new ArrayList<>(List.of(3, 1, 2));

List<Integer> snapshotSorted = original.stream()
        .sorted()
        .toList();

System.out.println(original);     // [3, 1, 2]
System.out.println(snapshotSorted); // [1, 2, 3]

original.sort(Comparator.naturalOrder());
System.out.println(original);     // [1, 2, 3]
~~~

**List.of** is unmodifiable, so you should not call **sort** directly on List.of when you need to change its order; use a mutable copy **new ArrayList<>(...)** first.

**Stream.toList() does not guarantee a deep copy**: if the elements are mutable objects, both the source list and the result list can hold references to the same objects.

## 16. Observing during debugging with peek and side effects

The context of sorted often comes with the need to observe the pipeline:

~~~java
List<Integer> values = List.of(4, 1, 3, 2)
        .stream()
        .peek(n -> System.out.println("before: " + n))
        .sorted()
        .peek(n -> System.out.println("after: " + n))
        .toList();
~~~

This is a snippet inside a method where List is imported. It illustrates positions **before/after sorted** and can be useful for learning or debugging. However, **peek** is an intermediate operation; peek's callback **is not guaranteed to run completely** in every pipeline, because a terminal operation or optimization can skip unnecessary parts.

**Do not put mandatory functionality** such as recording payments, sending emails, or auditing inside Comparator/peek. A Comparator can be called multiple times and in a non-fixed order; a sort may need to call compare(a,b) several times on the same pair. If a side effect mutates a comparison key, the comparator can also violate its contract.

When you need business logging, separate the result computation step and the event handling step into parts with clear error/transaction contracts.

## 17. sorted in parallel streams

**sorted** still retains its sorting semantics when used on a parallel stream, though execution may split the source, process branches, and merge results. Note:

- **The Comparator must be stateless and thread-safe in how it is used**. A Comparator that only reads immutable fields is generally more suitable than one using shared mutable variables.
- **An ordered stream** still has sorted's stability contract; **an unordered stream** has no corresponding stability guarantee.
- Buffering, merging, and synchronization costs can be high; parallel is not always faster.
- **peek/forEach** in parallel may observe callbacks running on multiple threads or not in encounter order; do not use log order to infer the sorted result order.
- If the data is too small or the comparator is lightweight, parallel overhead can make it slower than sequential.

Example:

~~~java
List<Student> result = students.parallelStream()
        .sorted(byScoreDescNameAsc)
        .toList();
~~~

This is a snippet using the data and comparator declared in section 13. The **result** order obeys the comparator; do not infer that Comparator calls happen in the order S1→S2→S3→S4.

## 18. Testing a Comparator and result order

For a business comparator, you should test **sign**, **tie cases**, **transitivity**, and **the order of the sorted result**.

### 18.1. Testing comparison sign

~~~java
Comparator<Integer> ascending = Integer::compare;
if (ascending.compare(1, 2) >= 0) {
    throw new AssertionError("Expected 1 before 2");
}
if (ascending.compare(2, 2) != 0) {
    throw new AssertionError("Expected equality by comparator");
}
if (ascending.compare(3, 2) <= 0) {
    throw new AssertionError("Expected 3 after 2");
}
~~~

This is an illustrative test snippet inside a method where Comparator is imported.

### 18.2. Testing multiple criteria and stability

With Student from the program in section 13, check:

- S2 comes before S4 because both have score 95, and Binh comes before Chi.
- S1 comes before S3 when both have score 90 and name An, because the source is an ordered List.
- If you add a descending ID key, the S1/S3 order may change according to the ID policy; update tests to clearly describe the expectation.
- Sorting does not change the order of the source list.

### 18.3. Testing null and boundary values

Test:

- Null elements with nullsFirst/nullsLast.
- Null name fields when the comparator extracts keys.
- Integer.MIN_VALUE and Integer.MAX_VALUE if the comparator works with numbers.
- Equal values, already-sorted data, completely reversed data, and empty collections.
- Floating-point NaN if the domain can encounter it.
- Comparators using mutable state: replace with a pure/stable comparator before going to production.

Just because 5 elements sort correctly **does not prove** a comparator is always transitive. For critical data, randomized/property-based testing can help verify sign antisymmetry and transitivity across many triples of values.

## 19. Common mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Calling sorted() on non-Comparable objects | No natural order | Pass a Comparator or design an appropriate Comparable |
| Assuming sorted() mutates the source List | Stream only produces a result pipeline | Use List.sort separately when mutation is desired |
| Using (a,b) -> a-b | Subtraction can overflow | Integer.compare or comparingInt |
| Calling reversed() at the end of the whole chain when only reversing score | Reverses the entire comparator | Reverse the score comparator before thenComparing |
| Comparator changes results across calls | Violates ordering contract | Use pure rules and stable keys |
| Forgetting null keys/elements | Can throw NPE | nullsFirst/nullsLast at the right layer |
| Treating compare(a,b)==0 as a.equals(b) | Comparator equivalence differs from equals | Add a secondary criterion if distinction is needed |
| Assuming sorted is always stable on unordered sources | No stability guarantee in this case | Add an explicit secondary criterion |
| Putting sorted after limit when global top-k is needed | Only sorts the prefix | sorted then limit, or a proper top-k algorithm |
| Assuming sorted.findFirst reads only one element | Sorted may need all data | Consider the whole pipeline |
| Calling sorted on an infinite source | Cannot complete when full general sorting is needed | Limit the source first or design a different algorithm |
| Using peek/comparator for auditing | No guarantee on invocation count or order | Separate the audit step from the sort pipeline |
| Calling List.sort on List.of | List does not support mutation | Use a new ArrayList or Stream.sorted |
| Using a Comparator with IntStream.sorted() | Primitive stream has no comparator overload | boxed() then sorted(comparator) if needed |

## 20. Practice exercises

### Exercise 1 — Natural order

Given **List.of("java", "Go", "C", "Java")**. Predict the result after **stream().sorted().toList()**.

**Answer hint:** **[C, Go, Java, java]** because String natural order is case-sensitive.

### Exercise 2 — Descending score, ascending name

Write a comparator for the record:

~~~java
record Candidate(String name, int score) { }
~~~

Requirement: highest score first; on a tie, name A-Z.

**Hint:**

~~~java
Comparator<Candidate> ranking =
        Comparator.comparingInt(Candidate::score)
                .reversed()
                .thenComparing(Candidate::name);
~~~

These snippets illustrate usage in a class where Comparator is imported and record Candidate is defined.

### Exercise 3 — Comparing limit positions

With source **[8, 2, 9, 1]**, evaluate:

~~~java
numbers.stream().sorted().limit(2).toList();
numbers.stream().limit(2).sorted().toList();
~~~

**Answer:** **[1, 2]** and **[2, 8]**. The first selects the two smallest numbers overall; the second only sorts the first two elements of the source.

### Exercise 4 — Handling null

Given **["B", null, "A"]**. Write a pipeline to sort as **A, B, null**.

**Suggested answer:**

~~~java
List<String> result = values.stream()
        .sorted(Comparator.nullsLast(
                Comparator.naturalOrder()))
        .toList();
~~~

**values** must be a list that allows null elements, such as one created with Arrays.asList.

### Exercise 5 — Fixing an unsafe comparator

~~~java
Comparator<Integer> wrong = (a, b) -> a - b;
~~~

Fix it and test with **Integer.MAX_VALUE** and **-1**.

**Answer:** use **Integer::compare**, because correct ordering cannot rely on subtraction that risks overflow.

### Exercise 6 — Stable order and ID

Two Students have the same score=90 and same name=An, but IDs S3/S1 appear in different orders. When should the result preserve encounter order and when should it sort by ID?

**Hint:** if the requirement is **stability by original order**, use a comparator without ID on an ordered source; if the requirement is **deterministic order independent of source**, add **thenComparing(Student::id)**.

## 21. Takeaways

**Stream.sorted()** uses **natural order**; **Stream.sorted(Comparator)** uses **rules you define**. In both cases, sorted is a **lazy yet stateful intermediate operation**, does not directly mutate the source List, and is only evaluated when the terminal operation requests it.

Keep these principles in mind:

- Use **Comparable** when a type has a clear natural order; use **Comparator** for different sorting policies.
- Prefer **Comparator.comparing/comparingInt**, **thenComparing**, **reversed**, and **nullsFirst/nullsLast** to express criteria transparently.
- A Comparator must be consistent, transitive, and not depend on mutable state; **avoid subtraction that can overflow**.
- On an **ordered stream**, sorted is stable when the comparator considers two elements equal; on an unordered stream, there is no corresponding stability guarantee.
- **sorted().limit(k)** differs from **limit(k).sorted()** in result; do not reorder them arbitrarily.
- **Stream.toList()** returns an unmodifiable result, but does not deep-copy element objects.
- If you truly want to mutate the original collection, use **List.sort** on a mutable list; if you only want to produce a sorted result, use **Stream.sorted**.

Understanding natural order, the comparator contract, and sorted's position in a pipeline will help you get accurate results while avoiding subtle bugs when data grows or business requirements change.
