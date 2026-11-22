# `<T extends Comparable<T>>` in Comparison Algorithms

## Learning Objectives

After this lesson, you will be able to:

- Correctly read the recursive generic bound `<T extends Comparable<T>>` and explain why the compiler allows calling `compareTo` on values of type `T`.
- Write algorithms to find the smaller value and sort a list by **natural ordering** without casting or using raw types (`raw type`).
- Build a custom data type that implements `Comparable<T>`, define comparison rules, and predict runtime results.
- Recognize the limitation of the exact `Comparable<T>` bound, and know when `Comparable<? super T>` or `Comparator<? super T>` is needed.
- Avoid common pitfalls with `compareTo`, `null`, unmodifiable lists, and consistency rules when sorting.

## 1. The Problem: An Algorithm Needs to Know How Two Values Compare

Suppose you want to write a function that picks the smaller value for multiple data types:

- Two integers `Integer`: `2` is smaller than `7`.
- Two strings `String`: compared in lexicographical order as defined by `String.compareTo`.
- Two `Student` objects: you can define a custom comparison by grade, then by name.

Writing `static <T> T min(T a, T b)` is **not enough**. `T` is not constrained to have a `compareTo` method, so the expression `a.compareTo(b)` does not compile. Generics only tell the compiler that the two parameters share the same inferred type; they do not automatically create ordering rules.

Java provides the interface:

```java
public interface Comparable<T> {
    int compareTo(T other);
}
```

This is a signature excerpt for explanation, not code to redefine the interface in `java.lang`.

An object implementing `Comparable<X>` can be compared to an object of type `X` via `compareTo(X)`. The result carries a **sign**, and does not necessarily take only `-1`, `0`, `1`:

| Return value of `a.compareTo(b)` | Meaning |
| --- | --- |
| Less than `0` | `a` comes before `b` |
| Equal to `0` | `a` and `b` are equivalent **in comparison order** |
| Greater than `0` | `a` comes after `b` |

`compareTo(...) == 0` does not by default mean that `equals(...)` returns `true`.

## 2. Reading the Recursive Bound Precisely

```java
public static <T extends Comparable<T>> T min(T a, T b) {
    return a.compareTo(b) <= 0 ? a : b;
}
```

Split the syntax into three parts:

1. `<T ...>`: declares the **method's** type parameter `T`.
2. `T extends Comparable<T>`: `T` must be a type satisfying the bound that it can be compared with values of type `T`. In Java type bounds, the `extends` keyword is also used when bounding by an **interface**; it does not require the interface to be a parent class.
3. `T min(T a, T b)`: the return type and parameter types use `T`, allowing the result to retain type information at compile time.

The **recursive** aspect lies in `T` appearing inside its own bound: `T extends Comparable<T>`. This pattern is commonly called *F-bounded polymorphism* or a *self-referential type bound*. It expresses a type relationship in the type system; it does not mean the `min` or `compareTo` method calls itself at runtime.

Valid examples: `Integer` implements `Comparable<Integer>`; `String` implements `Comparable<String>`. If `Student implements Comparable<Student>`, then `Student` can also be used in `min`.

What the compiler checks:

- `a.compareTo(b)` can be called with `a` and `b` typed as `T`.
- An arbitrary type that does not satisfy the bound cannot be passed as `T`.
- There is no need to cast `Object` to `Comparable` or bypass type checking with raw `Comparable`.

What the compiler does **not** guarantee: whether the `compareTo` implementation is correct, symmetric, transitive, or handles every pair of objects in the data domain. That is the responsibility of the data type's author.

## 3. Runnable Example: `min` and Insertion Sort

Create a file `ComparableAlgorithms.java` with the following complete code (Java 17 or later):

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ComparableAlgorithms {

    public static <T extends Comparable<T>> T min(T left, T right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.compareTo(right) <= 0 ? left : right;
    }

    public static <T extends Comparable<T>> void insertionSort(List<T> values) {
        Objects.requireNonNull(values, "values");
        for (T value : values) {
            Objects.requireNonNull(value, "element");
        }

        for (int i = 1; i < values.size(); i++) {
            T key = values.get(i);
            int j = i - 1;

            while (j >= 0 && values.get(j).compareTo(key) > 0) {
                values.set(j + 1, values.get(j));
                j--;
            }
            values.set(j + 1, key);
        }
    }

    record Student(String name, int grade) implements Comparable<Student> {
        public Student {
            Objects.requireNonNull(name, "name");
        }

        @Override
        public int compareTo(Student other) {
            Objects.requireNonNull(other, "other");
            int byGrade = Integer.compare(grade, other.grade);
            return byGrade != 0 ? byGrade : name.compareTo(other.name);
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = new ArrayList<>(List.of(7, 2, 5, 2));
        insertionSort(numbers);
        System.out.println("Numbers: " + numbers);
        System.out.println("Min: " + min(7, 2));

        List<Student> students = new ArrayList<>(List.of(
                new Student("Lan", 9),
                new Student("Minh", 7),
                new Student("An", 9)));
        insertionSort(students);
        System.out.println("Students: " + students);
    }
}
```

Compile and run from the directory containing the file:

```bash
javac ComparableAlgorithms.java
java ComparableAlgorithms
```

Actual stdout verified with `javac` and `java`:

```text
Numbers: [2, 2, 5, 7]
Min: 2
Students: [Student[name=Minh, grade=7], Student[name=An, grade=9], Student[name=Lan, grade=9]]
```

### Why Does the Example Compile?

- Both `Integer` and `Student` satisfy `Comparable<T>` with their respective exact types.
- `min(7, 2)` uses *autoboxing*: the `int` arguments are passed into the generic call via `Integer`.
- `Student.compareTo(Student)` compares grades in ascending order using `Integer.compare`. When two grades are equal, the name determines the subsequent order. With the data above, Minh (7) comes before An (9) and Lan (9); An comes before Lan by name.
- `record Student` automatically generates `toString()`, so the list prints in the form `Student[name=..., grade=...]`.

The program intentionally constructs `new ArrayList<>(List.of(...))`: `List.of` returns a list that does not support modifying elements; the algorithm uses `List.set`, so a modifiable list is required. The methods also proactively reject `null` elements.

### How Does Insertion Sort Work?

With `[7, 2, 5, 2]`:

| Iteration | Key element | Sequence after insertion |
| --- | --- | --- |
| Initial | — | `[7, 2, 5, 2]` |
| `i = 1` | `2` | `[2, 7, 5, 2]` |
| `i = 2` | `5` | `[2, 5, 7, 2]` |
| `i = 3` | `2` | `[2, 2, 5, 7]` |

In each iteration, the slice `[0, i)` is already sorted. When `values.get(j).compareTo(key) > 0`, the algorithm shifts elements larger than the key to the right to make room for insertion. The condition **`> 0`**, instead of `>= 0`, avoids moving preceding elements with equal keys, so this insertion sort is **stable** if `compareTo` obeys the comparison contract.

Complexity of this implementation: best-case time `O(n)` when the list is already ordered, average/worst-case `O(n²)`; auxiliary memory `O(1)` apart from loop variables. The example uses a simple algorithm to clarify generics, and does not represent the optimal sorting implementation in the standard library. In applications, `List.sort` or `Collections.sort` is generally preferred.

## 4. Defining Custom `Comparable<T>`: The Contract Must Be Right

When creating a natural ordering for a class, clearly decide the **sort key**, ascending/descending direction, how ties are handled, and the possibility of encountering `null`.

A safe way for integer fields:

```java
int byGrade = Integer.compare(this.grade, other.grade);
```

Avoid writing:

```java
return this.grade - other.grade;
```

because subtraction can overflow when values are near `Integer.MIN_VALUE` or `Integer.MAX_VALUE`, leading to the wrong result sign. When using multiple fields, compare the next field **only when** the previous field yields `0`.

According to the `Comparable` contract, for values eligible to be compared:

- **Sign reversal:** the sign of `a.compareTo(b)` is opposite to the sign of `b.compareTo(a)`.
- **Transitivity:** if `a > b` and `b > c`, then `a > c`.
- **Consistent equivalence:** if `a.compareTo(b) == 0`, the two objects must have the same ordering relationship with every valid `z`.
- **Consistency with `equals` is recommended**, though not enforced by the interface. `BigDecimal("1.0")` and `BigDecimal("1.00")` yield `0` under `compareTo`, yet `equals` is `false`.

The difference between `compareTo` and `equals` is especially important for `TreeSet`/`TreeMap`: they determine duplicate keys by comparison order, so two objects for which `compareTo` returns `0` may be treated as one key even when `equals` is `false`.

Supporting comparison with `null` is not required: `Comparable.compareTo(null)` normally throws `NullPointerException`. If an ordering must support `null`, design it explicitly at the `Comparator.nullsFirst` or `Comparator.nullsLast` layer.

## 5. When the `Comparable<T>` Bound Is Too Strict

For example, `Employee implements Comparable<Employee>` and `Manager extends Employee`. `Manager` inherits the `compareTo(Employee)` method and can be compared with another `Manager`, yet it does **not automatically** become `Comparable<Manager>` because generics are invariant.

```java
class Employee implements Comparable<Employee> {
    final int id;
    Employee(int id) { this.id = id; }
    @Override public int compareTo(Employee other) {
        return Integer.compare(id, other.id);
    }
}

class Manager extends Employee {
    Manager(int id) { super(id); }
}
```

The bound in the insertion sort example is `T extends Comparable<T>`: with `T = Manager`, this requirement is not satisfied. If the algorithm only needs `compareTo` to accept a `T`, a more flexible signature is:

```java
static <T extends Comparable<? super T>> void flexibleSort(List<T> xs) {
    java.util.Collections.sort(xs);
}
```

When `T=Manager`, `Comparable<Employee>` satisfies `Comparable<? super Manager>`, so `flexibleSort(List<Manager>)` can compile. **Note on type inference:** with signatures taking `List<? extends T>`, the compiler may sometimes infer `T=Employee`; in that case the return type can be less specific. The core difference lies in the bound required when **fixing `T=Manager`**.

This section serves as a bridge from `Comparable<T>` algorithms to flexible bounds. The next lesson goes deeper into proving the `? super T` consumer direction, wildcard containment, the standard library's `Collections.max`, and the errors when substituting `? extends T`/`Comparable<?>`.

## 6. When Should You Use `Comparator<? super T>`?

`Comparable<T>` attaches **a single natural ordering** to the type itself. In practice, the same object may need multiple ways of sorting: students by grade or name; products by price or code. When you cannot or do not want to modify the data class, pass a separate comparison strategy:

```java
public static <T> T min(
        T first, T second, java.util.Comparator<? super T> order) {
    java.util.Objects.requireNonNull(order, "order");
    return order.compare(first, second) <= 0 ? first : second;
}
```

This is a **conceptually independent overload** of the `Comparable`-based `min` method; to run it, place it inside a class with a `main` method calling it.

With Java 17, you can use a comparator built from a record:

```java
record Book(String title, int pages) {}

java.util.Comparator<Book> byPagesThenTitle =
        java.util.Comparator.comparingInt(Book::pages)
                .thenComparing(Book::title);

Book chosen = min(
        new Book("Java", 320),
        new Book("Basics", 180),
        byPagesThenTitle);
// chosen.pages() == 180
```

The snippet above illustrates the record declaration and how to call it in a context that has the `min(..., Comparator)` method; on its own it does not contain `main`.

| Need | Choice |
| --- | --- |
| Data type has a clear single natural ordering | Implement `Comparable<T>` |
| Write a simple generic algorithm using natural ordering | `<T extends Comparable<T>>` |
| Need to accept subclasses inheriting comparison capability from a parent type | `<T extends Comparable<? super T>>` |
| Sort by multiple criteria or cannot modify the data class | `Comparator<? super T>` |
| List contains `null` elements and needs clear rules | `Comparator.nullsFirst(...)` / `nullsLast(...)` |

`Comparator<? super T>` follows the *consumer* principle: the comparator accepts two `T` values, so a comparator of a supertype can also compare subtype objects. With `List.sort`, for instance, `students.sort(Comparator.comparing(Student::name))` creates an ordering by name without changing the natural ordering implemented in `Student.compareTo`.

## 7. Common Mistakes and How to Fix Them

**Mistake 1 — Missing bound:**

```java
static <T> T smaller(T a, T b) {
    return a.compareTo(b) <= 0 ? a : b; // Compile error
}
```

The compiler does not know `T` has `compareTo`. Fix it with `<T extends Comparable<T>>` when natural ordering is desired, or accept an additional `Comparator<? super T>`.

**Mistake 2 — Using the wrong type argument for Comparable:**

```java
class Ticket implements Comparable<String> {
    @Override
    public int compareTo(String other) {
        return 0;
    }
}
```

`Ticket` does not satisfy `T extends Comparable<T>` with `T = Ticket`. Writing `Comparable<String>` only states that `Ticket` compares against `String`; this does not meet the requirement of comparing two `Ticket` instances with each other. To sort multiple `Ticket` instances, consider `Comparable<Ticket>` or an external comparator.

**Mistake 3 — Assuming `compareTo` only returns `-1, 0, 1`:** only check the **sign** with `< 0`, `== 0`, `> 0`; do not write conditions like `compareTo(x) == 1`.

**Mistake 4 — Non-transitive ordering:** comparing with contradictory rules across pairs can produce wrong sort results; library algorithms may even report a comparison contract violation in some situations. Verify pairwise symmetry and multi-field combinations before use.

**Mistake 5 — Unmodifiable list:** calling `insertionSort(List.of(...))` can throw `UnsupportedOperationException` when `set` is needed. Use `new ArrayList<>(List.of(...))` if the algorithm mutates the list in place.

**Mistake 6 — `null` or incomparable element types:** generic bounds are compile-time checks, but do not automatically prevent all `null` data at runtime. For natural-order sorting, types like `Object` or `Number` do not automatically satisfy the required `Comparable` merely because a few concrete runtime objects inside happen to be `Integer`. Type the data strictly or provide a suitable comparator.

**Mistake 7 — Raw types and casts to bypass checks:** using `Comparable` without a type parameter or arbitrary casting removes type guarantees and can push errors into `ClassCastException` at runtime. Keep full generic parameters and declared comparison relationships intact.

## 8. Self-Check Exercises

1. Write `max(T a, T b)` with the bound `<T extends Comparable<T>>`. When `a.compareTo(b) == 0`, return `a`; explain why the `>= 0` operator is sufficient.
2. Modify `Student.compareTo` so grades are **descending** while names remain **ascending** when grades tie. Hint: use `Integer.compare(other.grade, grade)`, keeping `name.compareTo(other.name)` as the next step.
3. Given `class Child extends Parent` and `Parent implements Comparable<Parent>`, explain why `List<Child>` needs the signature `Comparable<? super T>` when passed to a generic sorting algorithm.
4. Point out the bug in `return x - y;` when comparing two integers and rewrite it using `Integer.compare(x, y)`.
5. For two `BigDecimal` values representing `1.0` and `1.00`, predict the effect of `compareTo` and `equals` when inserting them into a `TreeSet`.

**Self-check answers:** (1) use `a.compareTo(b) >= 0 ? a : b`; (2) reverse the order of arguments when comparing grades, without reversing the name comparison; (3) the subclass inherits `Comparable<Parent>`, and does not automatically have `Comparable<Child>`; (4) subtraction risks integer overflow; (5) `compareTo` returns `0` whereas `equals` returns `false`, and `TreeSet` relies on comparison results so it keeps only one ordering-equivalent element.

## Takeaways for Application

The `<T extends Comparable<T>>` pattern lets **generic algorithms invoke `compareTo(T)` directly with compile-time type safety**. Use it to understand and implement algorithms based on natural ordering; when building widely reusable APIs, consider `Comparable<? super T>` for inheritance relationships and `Comparator<? super T>` for custom orderings. Verify the `compareTo` contract, `null` data, list mutability, and equality semantics before putting an algorithm into production.
