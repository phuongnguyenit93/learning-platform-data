# Processing a Student List with Multiple Sorting Criteria

In an academic management system, a student list is rarely sorted by a single attribute. For example, when reviewing scholarships, a school wants to prioritize the **highest grade point average (GPA)**, break ties by **more accumulated credits**, then by **student name**, and finally by **student code** so results never depend on data entry order.

The practice lesson **"Processing a Student List with Multiple Sorting Criteria"** belongs to the **Beginner and Intermediate Exercises** chapter of the **JAVA_STREAM_API** module. We use declarative pipelines with `filter`, `map`, `sorted`, `limit`, and `collect`, combined with `Comparator`, to solve a realistic problem. At the same time, this exercise highlights Stream limits regarding **encounter order**, laziness, statefulness, result immutability, complexity, parallel processing, and maintainability.

After this lesson, you will be able to:

- Build a `Comparator<Student>` with multiple independent ascending/descending criteria.
- Identify and fix the common bug of placing `reversed()` in the wrong position.
- Filter and sort student data without mutating the source list.
- Extract the top N, sort within each department, and verify results against expected data.
- Distinguish stable sorting, tie-breaking rules, and tied-rank policies.
- Handle empty inputs, `null`, invalid GPAs, and the cost of `sorted` on large datasets.

The main examples run on **Java 17 or later** to use `record`, `List.of`, and `Stream.toList()`. `Stream.sorted` and the `Comparator` factory methods themselves have been available since Java 8.

## 1. Reading the Problem and Defining the Sorting Policy

A student record has the following fields:

| Field | Type | Meaning |
|---|---|---|
| `code` | `String` | Student code, used as the identifying key |
| `name` | `String` | Display name |
| `major` | `String` | Department/major |
| `gpa` | `double` | Grade point average on a 4-point scale |
| `credits` | `int` | Accumulated credits |

**Priority policy** for the scholarship review list:

1. `gpa` **descending**: higher GPA comes first.
2. If `gpa` is equal, `credits` **descending**: more credits comes first.
3. If both above are equal, `name` **ascending**, case-insensitive.
4. If still equal, `code` **ascending** to produce a deterministic order.

Written concisely:

~~~text
GPA ↓  →  Credits ↓  →  Name ↑  →  Code ↑
~~~

The arrows indicate the sort direction of each individual criterion; they do **not** mean all criteria are reversed together.

### Sample Data

| Code | Name | Major | GPA | Credits |
|---|---|---|---:|---:|
| S01 | An | IT | 3.80 | 60 |
| S02 | Bình | Economics | 3.90 | 58 |
| S03 | Chi | IT | 3.80 | 65 |
| S04 | Dũng | Languages | 3.90 | 58 |
| S05 | Hà | IT | 3.50 | 90 |
| S06 | Bình | IT | 3.90 | 58 |
| S07 | An | Economics | 3.80 | 65 |
| S08 | Bình | IT | 3.90 | 58 |
| S09 | Lan | IT | 4.00 | 40 |
| S10 | Giang | IT | 3.20 | 95 |

The dataset intentionally includes cases with **tied GPAs**, **tied credits**, and **identical names**. If a solution only works when every student has a distinct GPA, the multi-criteria comparator has not been sufficiently tested.

## 2. Why Choose `Stream.sorted`?

`Stream.sorted(...)` is an **intermediate operation** that produces a Stream in sorted order. There are two familiar overloads:

~~~java
Stream<T> sorted()

Stream<T> sorted(Comparator<? super T> comparator)
~~~

The no-argument `sorted()` relies on the **natural order** of elements, meaning elements must be comparable via `Comparable`. Our `Student` record **does not implement `Comparable`**, so we must use `sorted(comparator)`.

A small example:

~~~java
import java.util.List;

List<Integer> scores = List.of(9, 5, 7, 5);

List<Integer> ascending = scores.stream()
    .sorted()
    .toList();

System.out.println(ascending); // [5, 5, 7, 9]
System.out.println(scores);    // [9, 5, 7, 5]
~~~

`sorted` **does not remove duplicates**: both 5s remain. `Stream.toList()` (Java 16+) returns a list that cannot be modified by operations like `add` or `sort`. The original `scores` list is also untouched.

Comparing approaches:

| Approach | Mutates Source? | Output |
|---|---|---|
| `students.stream().sorted(c).toList()` | Does not modify source collection | New list ordered by comparator |
| `students.sort(c)` | **Yes**, sorts the List in place | Does not return a List; changes element order in source |
| `students.stream().sorted(c).collect(toList())` | Does not modify source collection | List created by collector; mutability is not specifically guaranteed |

Use `Stream.sorted` when you want a sorted view of the data while preserving the original input, or when sorting is one stage in a multi-step pipeline.

## 3. Comparator: Negative, Zero, and Positive Values

`Comparator<T>` compares two values `a` and `b` and returns:

- A **negative** integer when `a` comes before `b`.
- **0** when they are considered equal in order by the comparator.
- A **positive** integer when `a` comes after `b`.

Do not test `compare(a, b) == -1`: the contract only requires the **sign** of the returned integer, not specifically `-1` or `1`.

~~~java
import java.util.Comparator;

Comparator<Integer> ascending = Integer::compare;

System.out.println(ascending.compare(2, 8) < 0); // true
System.out.println(ascending.compare(8, 2) > 0); // true
System.out.println(ascending.compare(5, 5) == 0); // true
~~~

A comparator must obey a valid ordering relation: antisymmetric in sign, transitive, and consistent during sorting. A comparator that depends on the clock, random numbers, or mutable external variables can yield unpredictable results or even throw exceptions by violating the comparator contract.

### 3.1. Do Not Write Comparators Using Subtraction That Can Overflow

~~~java
// Avoid when integers may be large:
// Comparator<Student> wrong = (a, b) -> b.credits() - a.credits();
~~~

For arbitrary integers, subtraction can overflow and produce the wrong order. For floating-point numbers, subtraction also suffers from `NaN`, infinity, and values very close together.

Use the built-in comparison helpers instead:

~~~java
Comparator<Student> byCreditsAscending =
    Comparator.comparingInt(Student::credits);

Comparator<Student> byGpaAscending =
    Comparator.comparingDouble(Student::gpa);
~~~

`comparingInt` and `comparingDouble` express intent clearly and avoid boxing just to compare primitive keys.

## 4. Building Ascending and Descending Criteria Individually

Key methods:

~~~java
Comparator.comparing(...)
Comparator.comparingInt(...)
Comparator.comparingDouble(...)
Comparator.reversed()
Comparator.thenComparing(...)
~~~

Assume the `Student` type is declared as shown in Section 7.

### 4.1. GPA Descending

~~~java
Comparator<Student> byGpaDesc =
    Comparator.comparingDouble(Student::gpa)
        .reversed();
~~~

If `a.gpa() = 3.9` and `b.gpa() = 3.8`, the comparator places `a` before `b`.

### 4.2. Credits Descending

~~~java
Comparator<Student> byCreditsDesc =
    Comparator.comparingInt(Student::credits)
        .reversed();
~~~

This comparison inspects **only** `credits`. It can serve as a secondary criterion after GPA.

### 4.3. Name Ascending, Case-Insensitive

~~~java
Comparator<Student> byNameAsc =
    Comparator.comparing(
        Student::name,
        String.CASE_INSENSITIVE_ORDER
    );
~~~

`String.CASE_INSENSITIVE_ORDER` ignores case according to Java's comparison rules, but it is **not a complete Vietnamese linguistic collator**. If a UI must sort names according to specific language or locale rules, choose an appropriate collation mechanism and test with real data. This exercise intentionally uses a simple, deterministic rule that does not depend on the machine's default locale.

### 4.4. Code Ascending

~~~java
Comparator<Student> byCodeAsc =
    Comparator.comparing(Student::code);
~~~

`String.compareTo` sorts by natural string order. Our examples use fixed-width codes (`S01`, `S02`, …), so alphabetical order matches what the sample data expects. For variable-length codes like `S2` and `S10`, lexicographical order does not necessarily match numeric order; parse or separate numeric parts if business rules require it.

## 5. Chaining Multiple Criteria with `thenComparing`

`thenComparing` evaluates the next criterion **only when the preceding comparator returns 0**.

~~~java
Comparator<Student> priorityOrder =
    Comparator.comparingDouble(Student::gpa)
        .reversed()
        .thenComparing(
            Comparator.comparingInt(Student::credits)
                .reversed()
        )
        .thenComparing(
            Student::name,
            String.CASE_INSENSITIVE_ORDER
        )
        .thenComparing(Student::code);
~~~

You can read this statement from top to bottom:

~~~text
Compare GPA, higher first.
    If tied → compare credits, more first.
        If tied → compare name, smaller first.
            If tied → compare code, smaller first.
~~~

This is a **composite comparator**. There is no need to write nested `if` and `return` statements manually for every field.

### 5.1. Decision Flowchart

~~~mermaid
flowchart TD
    A["Compare two students"] --> B{"Different GPA?"}
    B -->|Yes| C["Higher GPA comes first"]
    B -->|No| D{"Different credits?"}
    D -->|Yes| E["More credits comes first"]
    D -->|No| F{"Different name?"}
    F -->|Yes| G["Name ascending"]
    F -->|No| H["Code ascending"]
~~~

The diagram mirrors the exact policy defined above; if the organization changes priority criteria, you must change the order of the `thenComparing` steps accordingly.

## 6. Classic Bug: Placing `reversed()` in the Wrong Position

The following two snippets are **not equivalent**.

**Correct: reverse only the GPA and credits criteria.**

~~~java
Comparator<Student> correct =
    Comparator.comparingDouble(Student::gpa)
        .reversed()
        .thenComparing(
            Comparator.comparingInt(Student::credits)
                .reversed()
        )
        .thenComparing(Student::name)
        .thenComparing(Student::code);
~~~

**Wrong for the requirement: reverses the entire chained comparator.**

~~~java
Comparator<Student> wrong =
    Comparator.comparingDouble(Student::gpa)
        .thenComparingInt(Student::credits)
        .thenComparing(Student::name)
        .thenComparing(Student::code)
        .reversed();
~~~

In `wrong`, calling `reversed()` applies to the **entire comparison chain**. As a result, GPA is descending **but credits, name, and code are also reversed**, violating the "name/code ascending" requirement.

Another subtle bug:

~~~java
Comparator<Student> alsoWrong =
    Comparator.comparingDouble(Student::gpa)
        .reversed()
        .thenComparingInt(Student::credits)
        .reversed();
~~~

The final `reversed()` flips the **entire accumulated comparator**, turning GPA into ascending and credits into descending.

**Rule:** when a secondary criterion has the opposite direction of the primary criterion, build the secondary comparator separately and pass it into `thenComparing(...)`. This makes code reviews clearer and reduces accidental flips.

## 7. Complete Program: Sorting the Student List

Save the code below into `StudentSortingExercise.java` and run it on **Java 17+**. The program is self-contained with sample data, input validation rules, a multi-level comparator, and result verification.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class StudentSortingExercise {

    record Student(
        String code,
        String name,
        String major,
        double gpa,
        int credits
    ) {
        Student {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("Invalid student code");
            }
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Invalid student name");
            }
            if (major == null || major.isBlank()) {
                throw new IllegalArgumentException("Invalid major");
            }
            if (!Double.isFinite(gpa) || gpa < 0.0 || gpa > 4.0) {
                throw new IllegalArgumentException("GPA must be in [0, 4]");
            }
            if (credits < 0) {
                throw new IllegalArgumentException("Credits must not be negative");
            }
        }
    }

    static final Comparator<Student> PRIORITY_ORDER =
        Comparator.comparingDouble(Student::gpa)
            .reversed()
            .thenComparing(
                Comparator.comparingInt(Student::credits)
                    .reversed()
            )
            .thenComparing(
                Student::name,
                String.CASE_INSENSITIVE_ORDER
            )
            .thenComparing(Student::code);

    static List<Student> sampleStudents() {
        return List.of(
            new Student("S01", "An",    "IT",        3.80, 60),
            new Student("S02", "Bình",  "Economics", 3.90, 58),
            new Student("S03", "Chi",   "IT",        3.80, 65),
            new Student("S04", "Dũng",  "Languages", 3.90, 58),
            new Student("S05", "Hà",    "IT",        3.50, 90),
            new Student("S06", "Bình",  "IT",        3.90, 58),
            new Student("S07", "An",    "Economics", 3.80, 65),
            new Student("S08", "Bình",  "IT",        3.90, 58),
            new Student("S09", "Lan",   "IT",        4.00, 40),
            new Student("S10", "Giang", "IT",        3.20, 95)
        );
    }

    public static void main(String[] args) {
        List<Student> students = sampleStudents();

        List<Student> sorted = students.stream()
            .sorted(PRIORITY_ORDER)
            .toList();

        List<String> actualCodes = sorted.stream()
            .map(Student::code)
            .toList();

        List<String> expectedCodes = List.of(
            "S09", "S02", "S06", "S08", "S04",
            "S07", "S03", "S01", "S05", "S10"
        );

        if (!actualCodes.equals(expectedCodes)) {
            throw new AssertionError(
                "Incorrect order: " + actualCodes
            );
        }

        System.out.println("Priority order: " + actualCodes);

        // Select students with GPA >= 3.8, then pick the top 3.
        List<Student> topThree = students.stream()
            .filter(s -> s.gpa() >= 3.8)
            .sorted(PRIORITY_ORDER)
            .limit(3)
            .toList();

        System.out.println(
            "Top 3: " + topThree.stream()
                .map(Student::code)
                .collect(Collectors.joining(", "))
        );

        // Print using Locale.ROOT so decimal formatting is consistent across machines.
        sorted.forEach(s -> System.out.printf(
            Locale.ROOT,
            "%s | %-7s | GPA %.2f | %d credits%n",
            s.code(), s.name(), s.gpa(), s.credits()
        ));

        // Source list preserves its original input order.
        System.out.println(
            "First element of source: " + students.get(0).code()
        ); // S01
    }
}
~~~

### 7.1. Key Output

~~~text
Priority order: [S09, S02, S06, S08, S04, S07, S03, S01, S05, S10]
Top 3: S09, S02, S06
First element of source: S01
~~~

Detailed verification table:

| Rank | Code | GPA | Credits | Why at This Position? |
|---:|---|---:|---:|---|
| 1 | S09 | 4.00 | 40 | Highest GPA |
| 2 | S02 | 3.90 | 58 | Tied GPA/credits/name with S06, S08; smallest code |
| 3 | S06 | 3.90 | 58 | Code comes after S02 |
| 4 | S08 | 3.90 | 58 | Code comes after S06 |
| 5 | S04 | 3.90 | 58 | Name Dũng comes after Bình |
| 6 | S07 | 3.80 | 65 | Tied GPA/credits with S03; name An before Chi |
| 7 | S03 | 3.80 | 65 | Name Chi after An |
| 8 | S01 | 3.80 | 60 | Fewer credits than S07 and S03 |
| 9 | S05 | 3.50 | 90 | Lower GPA despite high credits |
| 10 | S10 | 3.20 | 95 | Lowest GPA; high credits do not override priority |

The last line of the program demonstrates that **the source is not sorted in place**: the original `List.of` still starts with `S01`, even though `sorted` starts with `S09`.

### 7.2. Why Must Code Be the Final Criterion?

If we only compare GPA, credits, and name, students `S02`, `S06`, and `S08` tie under the comparator. With an ordered `List` source, `Stream.sorted` is *stable* and preserves the initial relative order among elements considered equal by the comparator.

However, if the input comes from a source without encounter order or its loading order changes, the order within a tied group can vary. Adding `code` as a tie-breaker ensures the **display order does not depend on insertion history** when student codes are unique.

## 8. Exercise 1 — Sorting by a Single Primary Criterion

Before combining many conditions, check each comparator individually.

**Requirement A:** sort by GPA **ascending**, breaking ties by code ascending.

~~~java
Comparator<Student> gpaAscCodeAsc =
    Comparator.comparingDouble(Student::gpa)
        .thenComparing(Student::code);

List<String> codes = students.stream()
    .sorted(gpaAscCodeAsc)
    .map(Student::code)
    .toList();

System.out.println(codes);
// [S10, S05, S01, S03, S07, S02, S04, S06, S08, S09]
~~~

In the 3.80 GPA group, we use code ascending **without** considering credits, so the order is S01 → S03 → S07. Differing from the main program is completely expected because the **sorting policy changed**.

**Requirement B:** sort by credits **descending**; break ties by code ascending.

~~~java
Comparator<Student> creditsDescCodeAsc =
    Comparator.comparingInt(Student::credits)
        .reversed()
        .thenComparing(Student::code);

List<String> orderedCodes = students.stream()
    .sorted(creditsDescCodeAsc)
    .map(Student::code)
    .toList();

System.out.println(orderedCodes);
// [S10, S05, S03, S07, S01, S02, S04, S06, S08, S09]
~~~

Check: S10 has 95 credits, S05 has 90, S03/S07 have 65, S01 has 60, group S02/S04/S06/S08 has 58, and S09 has 40. This example shows that **when the primary criterion changes, the first element also changes**.

## 9. Exercise 2 — Filtering, Sorting, and Taking Top N

Requirement: select up to five students in the `IT` major with a GPA of at least 3.5, then sort according to the scholarship policy.

~~~java
int topN = 5;

List<Student> topCntt = students.stream()
    .filter(s -> s.major().equals("IT"))
    .filter(s -> s.gpa() >= 3.5)
    .sorted(PRIORITY_ORDER)
    .limit(topN)
    .toList();

System.out.println(
    topCntt.stream().map(Student::code).toList()
);
// [S09, S06, S08, S03, S01]
~~~

IT has S09, S06, S08, S03, S01, S05, and S10, but S10 does not meet 3.5; after sorting, the top 5 excludes S05.

**Placing `filter` before `sorted`** is usually beneficial because it reduces the number of elements that must be sorted. The pipeline also directly expresses "select eligible students, then rank them".

### 9.1. Changing Operation Order Can Change Problem Semantics

~~~java
List<Student> wrongForThisRequirement = students.stream()
    .sorted(PRIORITY_ORDER)
    .limit(5)
    .filter(s -> s.major().equals("IT"))
    .toList();
~~~

This snippet picks the **top five students across the entire school**, and then keeps only those in IT. It **does not guarantee** returning the top five highest-priority IT students.

| Pipeline | Meaning |
|---|---|
| `filter(IT).sorted(priority).limit(5)` | Top 5 **within IT** |
| `sorted(priority).limit(5).filter(IT)` | IT students **among the school-wide top 5** |

Both goals can be valid, but they are not interchangeable. During code review, match the operation order against the exact wording of the requirement.

### 9.2. When N Is Zero or Negative

`limit(0)` returns an empty Stream; `limit(n)` with `n < 0` throws `IllegalArgumentException`. Business APIs should validate arguments:

~~~java
static List<Student> topStudents(
        List<Student> source,
        Comparator<Student> order,
        int limit) {
    if (limit < 0) {
        throw new IllegalArgumentException("limit must not be negative");
    }
    return source.stream()
        .sorted(order)
        .limit(limit)
        .toList();
}
~~~

This method does not modify `source`. It assumes `source` and `order` are non-null; production APIs may add `Objects.requireNonNull` to fail fast.

## 10. Exercise 3 — Sorting Within Each Major

Requirement: build a `Map` where each major maps to a **list of students sorted by the same priority policy**.

~~~java
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, List<Student>> byMajor =
    students.stream()
        .collect(Collectors.groupingBy(
            Student::major,
            TreeMap::new,
            Collectors.collectingAndThen(
                Collectors.toList(),
                group -> group.stream()
                    .sorted(PRIORITY_ORDER)
                    .toList()
            )
        ));

System.out.println(
    byMajor.get("IT").stream()
        .map(Student::code)
        .toList()
);
// [S09, S06, S08, S03, S01, S05, S10]

System.out.println(
    byMajor.get("Economics").stream()
        .map(Student::code)
        .toList()
);
// [S02, S07]
~~~

There are three distinct mechanisms in this example:

1. `groupingBy(Student::major, ...)` classifies students by major.
2. `TreeMap::new` ensures major keys are traversed in natural `String` order.
3. `collectingAndThen(toList(), ...)` receives **each group's** list and sorts that group according to `PRIORITY_ORDER`.

**Mutability note:** `group.stream().sorted(...).toList()` returns an unmodifiable list, but the **outer Map** created by the collector remains modifiable unless wrapped or copied according to policy. If you need an unmodifiable Map result, consider `Map.copyOf(byMajor)` after collecting; note that `Map.copyOf` does not preserve `TreeMap` key ordering, so choose the API based on exact requirements.

### 10.1. Do Not Confuse Sorting Map Keys with Sorting Students

`TreeMap::new` only sorts **major names**; it does not sort students **inside each group**. If you omit `collectingAndThen(...sorted...)`, each group is collected in source encounter order (for sequential `List`), not necessarily by GPA.

Conversely, `sorted(PRIORITY_ORDER)` in the downstream collector does not affect how the outer `Map` iterates over major keys.

### 10.2. When the Number of Majors Is Very Large

`groupingBy` maintains many intermediate containers; sorting each group adds further cost. If you only need the top 3 per major, building and sorting full lists can still consume significant memory. For very large datasets, a custom collector using a bounded priority queue may be appropriate, provided the combiner merges correctly in parallel.

At the beginner/intermediate level, prioritize a correct, easily testable version first; change algorithms only with evidence of a performance issue.

## 11. Exercise 4 — Switching Rule Sets for Different Screens

Not every screen shares the same definition of "first".

**Scholarship screen:** GPA ↓, credits ↓, name ↑, code ↑.

**Administrative roster:** Major ↑, name ↑, code ↑.

**Academic progress list:** Credits ↓, GPA ↓, code ↑.

You can build separate, meaningfully named comparators:

~~~java
Comparator<Student> administrativeOrder =
    Comparator.comparing(Student::major)
        .thenComparing(
            Student::name,
            String.CASE_INSENSITIVE_ORDER
        )
        .thenComparing(Student::code);

Comparator<Student> progressOrder =
    Comparator.comparingInt(Student::credits)
        .reversed()
        .thenComparing(
            Comparator.comparingDouble(Student::gpa)
                .reversed()
        )
        .thenComparing(Student::code);
~~~

Using well-named variables is usually easier to maintain than a method accepting a string of boolean flags such as `sort(students, true, false, true)`. If criteria must be built dynamically from a UI, use enums or config objects representing **field**, **direction**, and **tie-breaker**, while restricting sortable fields and testing each combination.

### 11.1. Never Share a Comparator Whose Rules Mutate Mid-Sort

A comparator must not read a mutable global variable and change comparison direction while `sorted` is running. Returning inconsistent results for the same pair of objects violates the comparator contract.

The safe pattern is to **construct the complete comparator before the pipeline** and keep it immutable throughout sorting.

## 12. Sort Stability (Stable Sort) and Tie-Breaking Rules

On a Stream **with encounter order**, `sorted` is stable: elements considered equal by the comparator preserve their relative input order.

Example:

~~~java
record Score(String code, int points) {}

List<Score> input = List.of(
    new Score("A", 90),
    new Score("B", 80),
    new Score("C", 90)
);

List<String> codes = input.stream()
    .sorted(Comparator.comparingInt(Score::points).reversed())
    .map(Score::code)
    .toList();

System.out.println(codes); // [A, C, B]
~~~

A and C both have 90 points, so the comparator returns 0 and A remains before C as in the source list. On an **unordered** Stream, stability of `sorted` is not guaranteed in that way.

### 12.1. Stable Sort Does Not Replace a Tie-Breaker

If the source is a `HashSet` or data loaded without a guaranteed sequence, the order of tied elements can vary. If the application requires consistent display order across runs, append a unique identifier as the final criterion instead of relying solely on sort stability.

### 12.2. Row Numbers Are Not Tied Ranks

~~~java
List<Student> sorted = students.stream()
    .sorted(PRIORITY_ORDER)
    .toList();

for (int i = 0; i < sorted.size(); i++) {
    System.out.println((i + 1) + ". " + sorted.get(i).code());
}
~~~

This prints **positions** 1, 2, 3... in the output, which does not automatically implement **tied ranking**. If the school defines "same GPA means same rank", S02, S06, S08, and S04 all have GPA 3.90; printing different row numbers does not mean they hold different academic ranks.

A ranking requirement must explicitly specify:

- **Ordinal position:** every row gets a distinct sequential number.
- **Competition rank:** tied entries share a rank, leaving a gap after ties (1, 2, 2, 4).
- **Dense rank:** tied entries share a rank, and the next rank increments by one (1, 2, 2, 3).

Do not infer a ranking policy from the comparator alone. Once the **tie-equality key** (GPA only, or GPA plus credits) is specified, write the rank-assignment logic accordingly.

## 13. Empty Inputs, `null`, and Invalid GPAs

### 13.1. Empty List

~~~java
List<Student> empty = List.of();

List<Student> sortedEmpty = empty.stream()
    .sorted(PRIORITY_ORDER)
    .toList();

System.out.println(sortedEmpty.isEmpty()); // true
~~~

`sorted` does not throw on an empty source. However, `findFirst()`/`min()`/`max()` on an empty list return `Optional.empty()`; do not call `get()` without handling missing data.

### 13.2. A `null` Student Object or `null` Key Field

The `Student` record in our main example **rejects `null`** in the fields used for comparison. This keeps the comparator simple and prevents `NullPointerException` during sorting.

If business rules allow a missing name, you can design a dedicated comparator:

~~~java
Comparator<Student> nullableNameOrder =
    Comparator.comparing(
        Student::name,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
    );
~~~

However, this only makes sense if the **Student model permits null names**; the `Student` record in Section 7 intentionally forbids them. Do not add `nullsLast` just to mask invalid input that should fail validation.

### 13.3. `NaN`, Infinity, and Out-of-Range Scores

`Double.compare` defines ordering rules for `NaN`, `Infinity`, and signed zeros. Without input validation, `Comparator.comparingDouble(Student::gpa)` could place special values into a Java-valid but academically meaningless order.

That is why the constructor checks:

~~~java
if (!Double.isFinite(gpa) || gpa < 0.0 || gpa > 4.0) {
    throw new IllegalArgumentException("GPA must be in [0, 4]");
}
~~~

If scores require exact decimal precision or specific rounding rules, consider storing GPA as a **scaled integer** or `BigDecimal` with an explicit policy. Do not rely on `double` `==` to decide "equal after rounding" if business rules require rounding.

### 13.4. Normalizing Names Before Comparing

`"An"` and `" An "` are not equal under standard `String` comparison; whitespace can skew ordering. For user-entered data, you can normalize when parsing:

~~~java
String cleaned = rawName == null ? null : rawName.trim();
~~~

If you need Unicode normalization, whitespace collapsing, or specific Vietnamese character handling, define a tested normalization rule. Do not rely on the machine's default locale, and do not silently alter real user name spellings unless required.

## 14. Sorting Vietnamese Names: Considering `Collator`

`String.compareTo` and `String.CASE_INSENSITIVE_ORDER` do not implement full linguistic **collation** rules. When a product requires displaying students sorted by Vietnamese alphabetical rules, consider `java.text.Collator`.

Illustrative example for a **sequential** pipeline:

~~~java
import java.text.Collator;
import java.util.Comparator;
import java.util.Locale;

Locale vietnamese = new Locale("vi", "VN");
Collator collator = Collator.getInstance(vietnamese);
collator.setStrength(Collator.PRIMARY);

Comparator<Student> byVietnameseNameThenCode =
    Comparator.comparing(Student::name, collator)
        .thenComparing(Student::code);

List<Student> ordered = students.stream()
    .sorted(byVietnameseNameThenCode)
    .toList();
~~~

Important things to understand here:

- `Collator` uses linguistic comparison rules from the runtime; rules and results can depend on locale/JDK data.
- `PRIMARY` typically ignores certain differences such as diacritics or case according to collator rules, so you must decide the **tie-breaking** policy and append the student code.
- `Collator` has mutable configuration; do not share an instance across threads while reading and calling `setStrength`. In concurrent code, ensure stateful comparators are used safely or create/clone a collator per context.

This example is a **locale-specific variation**, not a reason to replace the main lesson's default comparator. Test with real accented names according to the school's policy.

## 15. `distinct()`, `Set`, and Deduplicating by Student Code

Sorting is different from deduplicating. `sorted` keeps all elements; `distinct` removes duplicates based on `equals`/`hashCode`.

~~~java
List<Student> distinctStudents = students.stream()
    .distinct()
    .sorted(PRIORITY_ORDER)
    .toList();
~~~

Because the `Student` record generates `equals` from **all components**, two records with the same `code` but different `gpa` are considered **different**. The snippet above does not guarantee each code appears only once.

If the requirement says "each student code is unique", code review should settle on one of these policies:

1. **Reject** input data containing duplicate codes.
2. **Keep** the most recent record by update timestamp.
3. **Merge** records according to an approved rule.

Do not use a `TreeSet` with a GPA-only comparator to "deduplicate by code"; it would drop different students who happen to share the same GPA.

### 15.1. Detecting Duplicate Codes with `groupingBy`

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> countByCode = students.stream()
    .collect(Collectors.groupingBy(
        Student::code,
        Collectors.counting()
    ));

List<String> duplicateCodes = countByCode.entrySet().stream()
    .filter(entry -> entry.getValue() > 1L)
    .map(Map.Entry::getKey)
    .sorted()
    .toList();

System.out.println(duplicateCodes); // [] on sample data
~~~

This approach **detects** duplicate codes without silently choosing which record to keep. If a business API requires unique keys, reject inputs whenever `duplicateCodes` is non-empty before sorting.

## 16. Cost of `sorted()`, `limit()`, and Parallel Streams

### 16.1. `sorted` Is a Stateful Intermediate Operation

To sort a finite source accurately, `sorted` generally must **collect and organize the elements to compare** before emitting results. Comparison-based sorting typically has `O(n log n)` time complexity; exact memory and runtime costs depend on the source and execution strategy.

~~~java
List<Student> topTen = students.stream()
    .sorted(PRIORITY_ORDER)
    .limit(10)
    .toList();
~~~

Do not assume `limit(10)` means only 10 students are inspected. Because `sorted` precedes `limit`, the pipeline generally must inspect **all qualifying elements** to determine the true top 10.

If the source has millions of students and you only need the top 10, consider a **heap/top-k** algorithm with roughly `O(n log k)` time and `O(k)` memory. That is an advanced optimization; get it right first, then measure.

### 16.2. Why `filter` Before `sorted` Usually Helps

~~~java
List<Student> qualified = students.stream()
    .filter(s -> s.gpa() >= 3.8)
    .sorted(PRIORITY_ORDER)
    .toList();
~~~

On large sources, filtering early reduces the number of elements to sort. However, **only move `filter` when business semantics do not change**. Section 9 showed that `limit` and `filter` cannot be swapped arbitrarily.

### 16.3. Parallel Streams Are Not Faster by Default

~~~java
List<Student> parallelSorted = students.parallelStream()
    .sorted(PRIORITY_ORDER)
    .toList();
~~~

This is valid when the comparator is pure, non-interfering, and the source satisfies Stream contracts. However, `sorted` can require substantial coordination, partitioning, allocation, and merging. For small lists like our sample dataset, parallel execution has no clear performance benefit.

Also, **never write into a shared `ArrayList`** inside `parallelStream().forEach(list::add)` to build a sorted list manually. Use a collector or Stream's `toList()`.

To decide whether to enable parallel execution in production, benchmark on representative data, verify sequential/parallel equivalence, and consider CPU, memory, bandwidth, and comparator cost. Never draw conclusions from a single run.

## 17. Testing the Comparator, Not Just One Output

A solid sorting exercise should include **unit-level checks** for every criterion and a dataset containing ties.

### 17.1. Testing a Pair with Different GPAs

~~~java
Student higher = new Student("A", "An", "IT", 3.9, 40);
Student lower = new Student("B", "Bình", "IT", 3.8, 100);

if (PRIORITY_ORDER.compare(higher, lower) >= 0) {
    throw new AssertionError("Higher GPA must come first");
}
~~~

Even though `lower` has 100 credits, its lower GPA still places it after `higher`.

### 17.2. Testing a Pair with Equal GPA but Different Credits

~~~java
Student moreCredits =
    new Student("A", "An", "IT", 3.8, 70);
Student fewerCredits =
    new Student("B", "Bình", "IT", 3.8, 60);

if (PRIORITY_ORDER.compare(moreCredits, fewerCredits) >= 0) {
    throw new AssertionError("More credits must come first");
}
~~~

### 17.3. Testing Name and Code in Tied Groups

~~~java
Student an = new Student("S09", "An", "IT", 3.8, 60);
Student chi = new Student("S01", "Chi", "IT", 3.8, 60);

if (PRIORITY_ORDER.compare(an, chi) >= 0) {
    throw new AssertionError("Name An must come before Chi");
}

Student binh2 =
    new Student("S02", "Bình", "IT", 3.9, 58);
Student binh8 =
    new Student("S08", "Bình", "IT", 3.9, 58);

if (PRIORITY_ORDER.compare(binh2, binh8) >= 0) {
    throw new AssertionError("Code S02 must come before S08");
}
~~~

These snippets rely on the `Student` record and `PRIORITY_ORDER` inside `StudentSortingExercise`, rather than being standalone programs. You can put them into a `verifyComparator()` method called from `main`; in real projects, use a unit testing framework like JUnit.

### 17.4. Checking Comparator Properties on Sample Data

For every pair of students `a`, `b` in the sample list:

~~~java
for (Student a : students) {
    for (Student b : students) {
        int ab = Integer.signum(PRIORITY_ORDER.compare(a, b));
        int ba = Integer.signum(PRIORITY_ORDER.compare(b, a));

        if (ab != -ba) {
            throw new AssertionError("Comparator antisymmetry violated");
        }
    }
}
~~~

This is a simple check on the **sign** of the comparator result. To test transitivity, check triples `a`, `b`, `c` and verify the ordering relation; for small sample data this is feasible, though checking all triples costs `O(n³)`. Tests cannot replace designing a contract-compliant comparator.

### 17.5. Checking That the Sorted List Is Non-Decreasing Under the Comparator

~~~java
List<Student> ordered = students.stream()
    .sorted(PRIORITY_ORDER)
    .toList();

for (int i = 1; i < ordered.size(); i++) {
    if (PRIORITY_ORDER.compare(
            ordered.get(i - 1), ordered.get(i)) > 0) {
        throw new AssertionError("Result is out of order");
    }
}
~~~

The invariant is that adjacent pairs are **not inverted** under the comparator. This test catches unsorted output, but it must be paired with GPA/credits/name/code policy tests; a completely backwards comparator would still produce a list that is "sorted" according to the wrong comparator.

## 18. Extension Exercises with Suggested Solutions

### Exercise A — Scholarship-Eligible Students

**Prompt:** select students with GPA at least 3.75 and at least 55 credits, sort by priority policy, and take at most four students.

~~~java
List<String> scholarshipCodes = students.stream()
    .filter(s -> s.gpa() >= 3.75)
    .filter(s -> s.credits() >= 55)
    .sorted(PRIORITY_ORDER)
    .limit(4)
    .map(Student::code)
    .toList();

System.out.println(scholarshipCodes);
// [S02, S06, S08, S04]
~~~

S09 has a 4.00 GPA but **only 40 credits**, so S09 is filtered out by the scholarship rule. The 3.9 GPA students with 58 credits come before the 3.8 group. This reminds us that **filter conditions are not sorting criteria**.

### Exercise B — Finding the Highest-Priority Student in a Major

**Prompt:** find the top-ranked student in the IT major according to `PRIORITY_ORDER`. Do not call `get()` directly if none is found.

~~~java
import java.util.Optional;

Optional<Student> bestCntt = students.stream()
    .filter(s -> s.major().equals("IT"))
    .min(PRIORITY_ORDER);

System.out.println(
    bestCntt.map(Student::code).orElse("None")
); // S09
~~~

Because `PRIORITY_ORDER` places **higher-priority** students **earlier** (smaller in comparator sign), `min(PRIORITY_ORDER)` returns the top student. This is easy to get backwards when comparators are reversed.

### Exercise C — Student Count Statistics by Major

**Prompt:** count students by major, then sort summary lines by **count descending**, breaking ties by **major name ascending**.

~~~java
Map<String, Long> counts = students.stream()
    .collect(Collectors.groupingBy(
        Student::major,
        Collectors.counting()
    ));

List<Map.Entry<String, Long>> sortedCounts =
    counts.entrySet().stream()
        .sorted(
            Map.Entry.<String, Long>comparingByValue()
                .reversed()
                .thenComparing(Map.Entry.comparingByKey())
        )
        .toList();

sortedCounts.forEach(entry ->
    System.out.println(entry.getKey() + ": " + entry.getValue())
);
~~~

Sample data output:

~~~text
IT: 7
Economics: 2
Languages: 1
~~~

This example switches from `Stream<Student>` to `Stream<Map.Entry<String, Long>>`. The comparator still chains multiple criteria like the main lesson, but the **compared fields changed**: count and major name.

### Exercise D — Finding the Student with the Most Credits

**Prompt:** without sorting the whole list, find only the student with the highest credit count.

~~~java
Optional<Student> mostCredits = students.stream()
    .max(Comparator.comparingInt(Student::credits)
        .thenComparing(Student::code));

System.out.println(
    mostCredits.map(Student::code).orElse("None")
); // S10
~~~

`max` finds the greatest element under the supplied comparator. When only a single extremum is needed, it is usually preferable to sorting the entire source with `sorted(...).findFirst()`.

## 19. Code Review: Spot the Bugs Before Shipping

The snippet below **intentionally contains flaws**:

~~~java
// Code for analysis, not a correct solution.
List<Student> result = students.parallelStream()
    .sorted(
        Comparator.comparingDouble(Student::gpa)
            .thenComparingInt(Student::credits)
            .thenComparing(Student::name)
            .reversed()
    )
    .limit(3)
    .toList();
~~~

Identify the issues:

1. `reversed()` applies to the **entire comparator**, causing secondary criteria to become descending as well.
2. There is no student code tie-breaker after name, so tied students may depend on encounter order.
3. No GPA validation if the data model allows `NaN` or infinity.
4. `parallelStream()` lacks performance justification; `sorted` is stateful and must organize elements globally.
5. If the goal is the top 3 students of **one major**, a `filter` before `sorted` is missing.
6. Using `String.compareTo` may not match locale-specific Vietnamese name sorting rules.
7. `limit(3)` does not guarantee `sorted` inspects only three elements.

Fixed version for the **school-wide top 3** policy:

~~~java
List<Student> corrected = students.stream()
    .sorted(PRIORITY_ORDER)
    .limit(3)
    .toList();

System.out.println(
    corrected.stream().map(Student::code).toList()
); // [S09, S02, S06]
~~~

The code is easier to review because **the sorting policy is named** and reused across screens, rather than repeating a long comparator expression prone to misplaced reversals.

## 20. Completion Checklist

| Check Question | Sign of Readiness |
|---|---|
| Have you defined the **field priority order**? | GPA ↓, credits ↓, name ↑, code ↑ |
| Is each sort direction reversed in the **right scope**? | No `reversed()` accidentally flipping the whole chain |
| Is the comparator consistent and independent of external state? | Only reads validated fields |
| Does input handling guard against `NaN` and infinite GPAs? | Rejection or normalization policy exists |
| Can name and code be `null`? | Model or comparator handles nulls explicitly |
| Is the source list protected from unintended mutation? | Uses `stream().sorted(...).toList()` |
| Does Top N filter properly **before** limiting? | Pipeline matches business wording |
| Are there tests for tied GPA, tied credits, and tied names? | Tests order of S02/S06/S08 and S07/S03 |
| Are **row positions** distinguished from **tied ranks**? | Ranking policy confirmed separately |
| Is linguistic Vietnamese name sorting required? | Collation chosen and tested against requirements |
| Are empty lists or majors with zero students handled? | Returns empty List/Optional meaningfully |
| Does large data make `sorted` expensive? | Measure before optimizing; consider top-k |
| If parallel is enabled, is it justified and still accurate? | Tested and benchmarked on representative workload |
| Does the result API specify list mutability? | Chooses `toList`/`toCollection` appropriately |

## 21. Self-Check Questions

1. Does `Stream.sorted(comparator)` mutate the input List? — **No**, it produces a sorted result pipeline; the original List order is unchanged.
2. Which score does `Comparator.comparingDouble(Student::gpa).reversed()` prioritize? — **Higher GPA**.
3. Why use `thenComparing(Comparator.comparingInt(Student::credits).reversed())`? — To reverse **only the credits criterion** without flipping GPA or prior criteria.
4. When does `thenComparing` execute? — When all preceding comparisons return 0.
5. Must `Comparator.compare(a, b)` return exactly `-1`, `0`, or `1`? — **No**, only negative/0/positive sign matters.
6. Does the `Student` record automatically support no-arg `sorted()`? — **No**, records do not implement `Comparable` by default.
7. Does `String.CASE_INSENSITIVE_ORDER` guarantee linguistically accurate Vietnamese sorting? — **No**; a locale-aware `Collator` may be needed.
8. Does `sorted().limit(3)` inspect only three elements? — **No**, sorting generally must inspect the entire finite source.
9. Does `filter(...).sorted().limit(5)` mean the same thing as `sorted().limit(5).filter(...)`? — **No**.
10. Can you call `add` on the List returned by `Stream.toList()`? — **No**, the returned list is unmodifiable.
11. Does `sorted` remove duplicates? — **No**, duplicate elements are retained.
12. Does `distinct` automatically deduplicate records by `code`? — **No**, it uses element `equals`/`hashCode`.
13. Does `min(PRIORITY_ORDER)` return the lowest-priority or highest-priority student? — **Highest-priority**, because the comparator orders higher-priority students as smaller.
14. Does an unordered `HashSet` guarantee the order of tied elements after `sorted`? — **No** if the comparator does not distinguish them.
15. Should you enable `parallelStream` on 10 sample students expecting it to be faster? — **No**, coordination overhead can outweigh any gain.
16. Why add student code as the final criterion? — It makes display order **deterministic** among distinct records when codes are unique.

## 22. Summary: Prefer Explicit Policies Over Clever One-Liners

Sorting a student list by multiple criteria tests more than `sorted` syntax. The crucial skill is **translating business rules into a Comparator with a clear priority hierarchy**, then ensuring both the data and Stream operations truly honor those rules.

Formula to remember:

~~~java
Comparator<Student> order =
    Comparator.comparingDouble(Student::gpa).reversed()
        .thenComparing(
            Comparator.comparingInt(Student::credits).reversed()
        )
        .thenComparing(
            Student::name,
            String.CASE_INSENSITIVE_ORDER
        )
        .thenComparing(Student::code);

List<Student> result = students.stream()
    .sorted(order)
    .toList();
~~~

As applications grow, check **tie-breakers**, **null/invalid GPAs**, **filter and limit ordering**, **rank definitions**, **output mutability**, and **global sorting cost**. When grouping by major, use `groupingBy` with a sorting downstream; when only one best element is needed, prefer `min` or `max` over sorting everything.

Keeping these rules explicit helps you write Java Stream API pipelines that are accurate, maintainable, and testable, preparing you for advanced topics like `collect`, custom collectors, `Spliterator`, parallel Streams, and Stream Gatherers.
