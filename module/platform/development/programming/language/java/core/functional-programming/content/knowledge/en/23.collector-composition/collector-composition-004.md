# flatMapping() to Flatten Within Each Group Using Composed Collectors

## 1. The Problem: Each Source Element Has Multiple Child Elements

In the Java Stream API, many data models have a **one-to-many** relationship: an order has multiple line items, an article has multiple tags, an employee has multiple skills, or a project has multiple tasks. When grouping parent objects by a key, we often want to **combine all child elements of each group** instead of receiving a nested list.

Suppose each article has a content category and a list of tags:

~~~java
record Article(String category, List<String> tags) {}
~~~

This is an illustrative record declaration that requires importing **java.util.List**.

The desired result has the form:

~~~text
guide -> [java, stream, collector]
news  -> [jdk, release]
faq   -> []
~~~

If you use **Collectors.groupingBy(Article::category, Collectors.mapping(Article::tags, Collectors.toList()))**, the result type will be **Map<String,List<List<String>>>**: within each group, there is still a separate tag list for each article. To directly obtain **Map<String,List<String>>**, you need a **flatten** operation at the downstream level.

Since Java 9, **Collectors.flatMapping(...)** solves this exact problem:

~~~java
Map<String, List<String>> byCategory = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        article -> article.tags().stream(),
                        Collectors.toList())));
~~~

This is an illustrative snippet; it assumes **articles** does not contain null and each **tags()** returns a non-null List. Requires importing **Map**, **List**, and **Collectors**.

A very important distinction:

- **groupingBy** decides **which group** a parent element goes into.
- **flatMapping** turns **one parent element** into **0, 1, or more child elements** and passes each child element to the downstream collector **within that same group**.
- **toList** decides how the child elements are accumulated: a flat list within each group.

**In short:** `flatMapping` is a **downstream collector adapter**. It is not a standalone `Stream.flatMap()` operation, but is used as a component of a composed collector, especially useful together with `groupingBy`, `partitioningBy`, or another collector.

## 2. Signature and Meaning of Collectors.flatMapping

General signature of the API:

~~~java
public static <T, U, A, R> Collector<T, ?, R> flatMapping(
        Function<? super T, ? extends Stream<? extends U>> mapper,
        Collector<? super U, A, R> downstream)
~~~

This is an **explanatory signature** from `java.util.stream.Collectors`, not a standalone program. These generic type parameters clearly separate three layers of responsibility:

| Component | Role |
| --- | --- |
| **T** | Type of element entering the collector, for example **Article** |
| **U** | Type of child element after flattening, for example **String** tag |
| **mapper** | Function taking a T and returning **Stream<? extends U>** |
| **downstream** | Collector receiving each U, for example **toList()**, **toSet()**, **counting()**, or **summingLong(...)** |
| **R** | Final result type of the downstream, for example **List<String>**, **Set<String>**, **Long** |
| **Collector<T,?,R>** | New collector accepting input T and returning result R |

A very common mistake: **mapper must return a Stream**, not directly a **List** or **Optional**.

~~~java
// VALID, assuming Article.tags() returns List<String>:
article -> article.tags().stream()

// NOT SUITABLE for flatMapping:
// article -> article.tags()          // returns List, not Stream
~~~

This is an illustrative snippet; the variables/type names are not declared in a standalone program.

If an object has at most one optional tag, the mapper can return `Optional<String>.stream()` (since Java 9), but **do not** pass an Optional directly in place of a Stream:

~~~java
article -> article.primaryTag().stream()
~~~

The snippet above assumes `primaryTag()` returns a **non-null Optional<String>**.

**Processing timing:** When a T element enters the collector, the mapper is called to obtain Stream<U>; each U is passed to the downstream collector. The resulting Stream returned by the mapper is closed after its elements are fed into the downstream. If the mapper returns null instead of a Stream, the contract of **Collectors.flatMapping** treats it as an **empty Stream**; however, you should return **Stream.empty()** explicitly so that the mapper's contract is easy to understand and reduces the risk of errors elsewhere.

## 3. Comparing flatMapping and mapping: Difference at the Data Layer

**Collectors.mapping(f, downstream)** performs a **one-T-to-one-U** mapping, then passes that one U to the downstream. If U is List<String>, the downstream toList will receive **one List<String> per article**.

~~~java
Map<String, List<List<String>>> nested = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.mapping(
                        Article::tags,
                        Collectors.toList())));
~~~

This is an illustrative snippet. A group with two articles, containing three tags and one tag respectively, will produce a result like:

~~~text
guide -> [[java, stream, java], [collector]]
~~~

In contrast, **flatMapping** iterates through the elements of the child Stream and gives:

~~~text
guide -> [java, stream, java, collector]
~~~

| Intent | Suitable downstream | Value type per group |
| --- | --- | --- |
| Keep each tag list intact | **mapping(Article::tags, toList())** | **List<List<String>>** |
| Combine tags into one list | **flatMapping(a -> a.tags().stream(), toList())** | **List<String>** |
| Combine and remove duplicate tags | **flatMapping(..., toSet())** | **Set<String>** |
| Combine and preserve first-seen order | **flatMapping(..., toCollection(LinkedHashSet::new))** | **LinkedHashSet<String>** |
| Combine and sort tags alphabetically | **flatMapping(..., toCollection(TreeSet::new))** | **TreeSet<String>** |
| Count total tags in each group | **flatMapping(..., counting())** | **Long** |

**Not every problem should be flattened.** If the task is to know which tags each article has, a nested list may be right. If the task is to build a tag dictionary by category, a flat list or Set is usually easier to use.

### 3.1. Combining with filtering

When you need to exclude empty or invalid tags, there are two ways:

~~~java
Collectors.flatMapping(
        a -> a.tags().stream()
                .filter(tag -> tag != null && !tag.isBlank()),
        Collectors.toList())
~~~

or:

~~~java
Collectors.flatMapping(
        a -> a.tags().stream(),
        Collectors.filtering(
                tag -> tag != null && !tag.isBlank(),
                Collectors.toList()))
~~~

These are illustrative collector expressions; **Collectors.filtering** was also added in Java 9. The first approach filters inside the child Stream created by the mapper. The second approach uses another downstream collector adapter, making the layers of the collector explicit.

**In practice:** If you do not need to reuse the rule, filtering inside the mapper is usually shorter. If the architecture is combining multiple downstream collectors or has a reusable rule, filtering can make responsibilities clearer. Do not use filter to silently drop corrupt data when business requirements demand reporting an error.

## 4. Java 17 Program: Grouping Articles and Flattening Tags

Create the file **FlatMappingGroupsDemo.java**:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

record Article(String category, List<String> tags) {}

public class FlatMappingGroupsDemo {
    public static void main(String[] args) {
        List<Article> articles = List.of(
                new Article("guide",
                        List.of("java", "stream", "java")),
                new Article("news", List.of("jdk")),
                new Article("guide", List.of("collector")),
                new Article("faq", List.of()),
                new Article("news", List.of("release"))
        );

        Map<String, List<String>> allTags = articles.stream()
                .collect(Collectors.groupingBy(
                        Article::category,
                        TreeMap::new,
                        Collectors.flatMapping(
                                a -> a.tags().stream(),
                                Collectors.toList())));

        Map<String, LinkedHashSet<String>> uniqueTags =
                articles.stream()
                        .collect(Collectors.groupingBy(
                                Article::category,
                                TreeMap::new,
                                Collectors.flatMapping(
                                        a -> a.tags().stream(),
                                        Collectors.toCollection(
                                                LinkedHashSet::new))));

        System.out.println("All: " + allTags);
        System.out.println("Unique: " + uniqueTags);
        System.out.println("FAQ size: " + allTags.get("faq").size());
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 FlatMappingGroupsDemo.java
java FlatMappingGroupsDemo
~~~

Stdout:

~~~text
All: {faq=[], guide=[java, stream, java, collector], news=[jdk, release]}
Unique: {faq=[], guide=[java, stream, collector], news=[jdk, release]}
FAQ size: 0
~~~

**Exact explanation:**

1. **groupingBy(Article::category, TreeMap::new, downstream)** groups the articles and returns a Map whose category keys are naturally sorted by **TreeMap**: faq, guide, news.
2. **flatMapping(a -> a.tags().stream(), toList())** puts each tag into the category's list, keeping even the repeated "java" tag.
3. **flatMapping(..., toCollection(LinkedHashSet::new))** replaces the downstream with LinkedHashSet, removing duplicate tags while preserving the encounter order of unique tags in a sequential pipeline.
4. The **faq** category still has **one source article**, even though that article has an empty tag list. Because groupingBy processes the article before the downstream flatMapping flattens the tags, the **faq key is still created**, with an empty collection.
5. **TreeMap** is chosen so that stdout is deterministic by key. The two-argument `groupingBy` does not guarantee the Map type or key iteration order by default, so you should not write expected stdout that depends on a specific HashMap.

**Key takeaway:** `flatMapping` does not make a group that already has a parent element disappear just because the child Stream is empty. This differs from flattening all elements first and then grouping, where a parent with no children can vanish completely.

## 5. How Does It Differ from Stream.flatMap() Before groupingBy?

The two approaches may look similar, but they can **differ in result structure**.

**Approach A: Group parents first, then flatten within each group**

~~~java
Map<String, List<String>> byCategory = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.toList())));
~~~

**Approach B: Flatten parent-child first, then group each child**

~~~java
record TagEntry(String category, String tag) {}

Map<String, List<String>> byCategory = articles.stream()
        .flatMap(a -> a.tags().stream()
                .map(tag -> new TagEntry(a.category(), tag)))
        .collect(Collectors.groupingBy(
                TagEntry::category,
                Collectors.mapping(
                        TagEntry::tag,
                        Collectors.toList())));
~~~

These are **two independent illustrative snippets** for comparison; they require the relevant imports and placing the record in a valid scope. Approach B needs a **TagEntry** to carry the parent's category along with each child tag.

Differences:

- **Approach A** keeps the grouping logic on the **source Articles**. A category that has an article with an empty tag list still appears with an empty result list.
- **Approach B** creates a Stream<TagEntry>. An article with no tags produces **0 TagEntry** instances; a category with only such articles will **not appear** in the groupingBy result.
- **Approach A** does not need to create an intermediate TagEntry object for each tag.
- **Approach B** is suitable when you need to transform data into a child entity with explicit parent information for multiple independent processing steps before grouping.
- When all articles have tags and there are no special rules, both approaches can produce equivalent tag contents per key, though they still differ in data flow and cost.

**Do not apply a rule to “always flatMap before groupingBy”** when business requirements need to preserve empty groups or preserve the exact set of parent elements that were grouped.

## 6. Empty Groups: An Easy-to-Miss Distinction

Consider the groups:

~~~text
Article(category="faq", tags=[])
Article(category="guide", tags=["java"])
~~~

If using **groupingBy + flatMapping**, the faq group is created by the parent Article, and the downstream receives 0 tags:

~~~text
faq   -> []
guide -> [java]
~~~

If using **Stream.flatMap() before groupingBy**, the faq Article emits no TagEntry, so groupingBy has no record with the key faq:

~~~text
guide -> [java]
~~~

**Why is there a difference?** groupingBy must receive an element to create a group. When groupingBy runs on **Article**, the faq article is present. When groupingBy runs on **TagEntry**, faq can only appear if there is at least one TagEntry for faq.

Real-world scenarios:

- Reporting skill counts by department: a department with no skills still needs to display **0**.
- Listing tags by category: a category that has articles without tags still needs to display **[]**.
- Collecting expense items by project: an existing project with no expense lines still needs to appear in the report.

**Exception to distinguish:** If there is **no parent Article at all** belonging to the faq category, even groupingBy + flatMapping will not automatically create the faq key. If the report must always include **every predefined category**, you need to merge with a standard category list or initialize missing keys according to a policy outside the collector.

## 7. Do Not Limit the Downstream to toList()

`flatMapping` turns one T into Stream<U>, and then the downstream can process those U elements in many different ways.

### 7.1. Deduplicating with toSet()

~~~java
Map<String, Set<String>> tagsByCategory =
        articles.stream().collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.toSet())));
~~~

This is an illustrative snippet requiring Map, Set, and Collectors imports. **Set** removes duplicates, but `Collectors.toSet()` does not guarantee a specific implementation or iteration order. Do not use Set if business logic requires keeping all occurrences.

### 7.2. Preserving First-Seen Order with LinkedHashSet

~~~java
Collectors.flatMapping(
        a -> a.tags().stream(),
        Collectors.toCollection(LinkedHashSet::new))
~~~

This is an illustrative downstream expression requiring LinkedHashSet and Collectors imports. With a Stream source that has encounter order and normal collection, LinkedHashSet iterates in the insertion order of distinct values.

### 7.3. Sorting with TreeSet

~~~java
Collectors.flatMapping(
        a -> a.tags().stream(),
        Collectors.toCollection(TreeSet::new))
~~~

Illustrative snippet requiring TreeSet and Collectors imports. It chooses TreeSet; the result in each group is sorted according to String's natural ordering and deduplicated by the comparator/natural ordering.

**Caution:** For child object types that are not Comparable or have a comparator returning 0 for two different values, TreeSet may throw ClassCastException or drop unintended records. The choice of downstream determines the semantics of the result as well.

### 7.4. Counting Child Elements with counting()

~~~java
Map<String, Long> tagCountByCategory =
        articles.stream().collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.counting())));
~~~

This is an illustrative snippet. **counting()** counts **each emitted child element**, including duplicate values. If one article has three tags and another has one tag, the total tags in the group is 4. Do not confuse this with **Collectors.counting() directly after groupingBy**, which counts **the number of parent Articles**.

### 7.5. Summing Numbers with summingLong

If an order has multiple line amounts, the downstream can sum `amountCents()` of each line:

~~~java
Collectors.flatMapping(
        order -> order.lines().stream(),
        Collectors.summingLong(Line::amountCents))
~~~

This is an illustrative expression, assuming compatible **Line** and **Order** records/classes. Here **R = Long**, not a List or Set. The "flatten within each group" problem can end with a total number, without necessarily producing a new collection.

**Choose the right downstream for the reporting need**, avoiding creating a large intermediate list only to iterate over it again to count or sum when an aggregating collector already suffices.

## 8. Java 17 Program: Flattening and Summing Amounts by Region

Create the file **FlatMappingTotalsDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

record Line(String sku, long amountCents) {}
record Order(String region, List<Line> lines) {}

public class FlatMappingTotalsDemo {
    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("North", List.of(
                        new Line("A", 120),
                        new Line("B", 30))),
                new Order("South", List.of(
                        new Line("C", 80))),
                new Order("North", List.of(
                        new Line("D", 50))),
                new Order("West", List.of())
        );

        Map<String, Long> totals = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::region,
                        TreeMap::new,
                        Collectors.flatMapping(
                                order -> order.lines().stream(),
                                Collectors.summingLong(
                                        Line::amountCents))));

        Map<String, Long> lineCounts = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::region,
                        TreeMap::new,
                        Collectors.flatMapping(
                                order -> order.lines().stream(),
                                Collectors.counting())));

        System.out.println("Totals: " + totals);
        System.out.println("Lines: " + lineCounts);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FlatMappingTotalsDemo.java
java FlatMappingTotalsDemo
~~~

Stdout:

~~~text
Totals: {North=200, South=80, West=0}
Lines: {North=3, South=1, West=0}
~~~

**Result explanation:**

- North has three lines: A=120, B=30, and D=50; total **200** and count **3**.
- South has one line C=80; total **80** and count **1**.
- West has **one Order but no Line**, yet still appears in the Map, with total 0 and count 0.
- `groupingBy(Order::region,...)` creates groups by region from the **parent Order** before flatMapping flattens the order lines.
- Each downstream `summingLong` and `counting` receives individual **child Lines**, not parent Orders.

**Currency units:** the `amountCents` numbers are an example of the smallest unit. `summingLong` can overflow the long range; for real currency, you must choose appropriate units and bounds checks. Do not use Long to claim overflow is impossible.

An operational note: the program above creates **two new streams from the same List** to get two independent results. If the source is a single-read cursor or an expensive I/O pipeline, you can design a composite downstream using `Collectors.teeing` (Java 12+) to produce multiple metrics in a single pass, but only do so when genuinely needed.

## 9. Using Optional.stream() When Each Parent Element Has at Most One Child Value

Not every one-to-many relationship needs a List. If an account has **0 or 1 referral code**, you can represent it with Optional<String> and use **Optional.stream()** to produce a 0/1-element Stream.

Create the file **FlatMappingOptionalDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

record Account(String team, Optional<String> referralCode) {}

public class FlatMappingOptionalDemo {
    public static void main(String[] args) {
        List<Account> accounts = List.of(
                new Account("A", Optional.of("R1")),
                new Account("B", Optional.empty()),
                new Account("A", Optional.of("R2")),
                new Account("C", Optional.empty())
        );

        Map<String, List<String>> codes = accounts.stream()
                .collect(Collectors.groupingBy(
                        Account::team,
                        TreeMap::new,
                        Collectors.flatMapping(
                                account -> account.referralCode().stream(),
                                Collectors.toList())));

        System.out.println(codes);
        System.out.println("B present: " + codes.containsKey("B"));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 FlatMappingOptionalDemo.java
java FlatMappingOptionalDemo
~~~

Stdout:

~~~text
{A=[R1, R2], B=[], C=[]}
B present: true
~~~

**Explanation:**

1. `Optional.of("R1").stream()` emits one String "R1".
2. `Optional.empty().stream()` emits 0 Strings.
3. Groups B and C still appear because they have parent Accounts, even though each Account carries no referralCode.
4. `TreeMap` fixes the key order A, B, C when printing.
5. With data that has no Account in group D, no key D will be created automatically.

**Do not confuse:** `Optional.stream()` is only safe when `account.referralCode()` returns a **non-null Optional**. If the Optional field itself is null, calling `stream()` on it still throws NPE. In API design, a method declared to return Optional should return **Optional.empty()** when a value is absent, not null.

## 10. Null and Invalid Data: Guarding at the Right Layer

There are at least four null cases to consider:

1. **Null parent element:** `groupingBy(Article::category)` will cause an NPE when calling the accessor on null.
2. **Null grouping key:** `groupingBy` in the JDK requires non-null classification keys; if the classifier returns null, collect throws NullPointerException.
3. **Null child list:** `article.tags().stream()` will throw NPE if tags() returns null.
4. **Null child element:** if the child Stream contains null, `toList()` can accumulate null, whereas `TreeSet`, `EnumSet`, or a dereferencing downstream may not accept it.

An explicit null-safe mapper:

~~~java
Collectors.flatMapping(
        article -> article.tags() == null
                ? Stream.<String>empty()
                : article.tags().stream()
                        .filter(Objects::nonNull),
        Collectors.toList())
~~~

This is an illustrative expression requiring Stream, Objects, and Collectors imports, assuming Article.tags() returns a possibly null List<String>. It turns a **null tags list** into **no tags**; each null tag inside the list is filtered out individually. However, this is a **data policy**, not a universal bug-fixing operation.

**Consider the semantics:**

- A null list might mean “no tags”: `Stream.empty()` is appropriate.
- A null list might be an error because the system failed to load tags: it should not be silently treated as empty.
- A null child might be a corrupt record that needs auditing: filtering would hide the trace, so a validation/reporting mechanism is needed.
- A null key does not only fail downstream: decide whether the classifier must return a non-null key or replace it with a group such as **"UNKNOWN"** by policy.

Do not expect `flatMapping` to handle all kinds of null on its own. The JDK treats a **mapper returning a null Stream** as empty, but **a mapper calling a getter on a null parent** can throw before a Stream exists; nulls inside the child Stream itself are also not automatically filtered out.

### 10.1. Checking for null before grouping

~~~java
articles.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.toList())));
~~~

This is an illustrative snippet. The `filter(Objects::nonNull)` step guards against **null Articles**, but does not guarantee non-null category or tags. A safe pipeline must examine **every data boundary** according to its contract.

If the problem requires all Articles to be valid, it is better to validate and throw an error at the data ingestion point rather than dropping elements unrecorded, because dropping Articles can skew statistics.

## 11. Java 17 Program: Null-Safe, Normalization, and Ordered Set

Create the file **FlatMappingNullSafeDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

record Employee(String department, List<String> skills) {}

public class FlatMappingNullSafeDemo {
    static Stream<String> validSkills(Employee employee) {
        if (employee.skills() == null) {
            return Stream.empty();
        }
        return employee.skills().stream()
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(s -> !s.isEmpty());
    }

    public static void main(String[] args) {
        List<Employee> people = Arrays.asList(
                new Employee("IT", Arrays.asList(
                        " Java ", null, "SQL", "Java")),
                new Employee("HR", List.of()),
                new Employee("IT", null),
                new Employee("HR", List.of("Interview", "Payroll")),
                new Employee("Ops", List.of())
        );

        Map<String, TreeSet<String>> skillsByDepartment =
                people.stream()
                        .collect(Collectors.groupingBy(
                                Employee::department,
                                TreeMap::new,
                                Collectors.flatMapping(
                                        FlatMappingNullSafeDemo::validSkills,
                                        Collectors.toCollection(
                                                TreeSet::new))));

        System.out.println(skillsByDepartment);
        System.out.println("IT count: "
                + skillsByDepartment.get("IT").size());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FlatMappingNullSafeDemo.java
java FlatMappingNullSafeDemo
~~~

Stdout:

~~~text
{HR=[Interview, Payroll], IT=[Java, SQL], Ops=[]}
IT count: 2
~~~

**Analysis:**

- `Arrays.asList` allows null elements in IT's skill list; the Employee record itself is still non-null.
- `validSkills` converts a null skills List to Stream.empty(), filters out null Strings, strips whitespace, and removes empty strings.
- `TreeSet` deduplicates **Java** and sorts the remaining values in natural ordering.
- **HR** has one Employee with no skills and one Employee with two skills, so the HR group has two values.
- **IT** has skills "Java", "SQL", "Java"; TreeSet yields **[Java, SQL]**.
- **Ops** has one Employee with an empty skills list, so the Ops key still appears with an empty TreeSet.
- `TreeMap` makes the display order of departments HR, IT, Ops.

**Scope of the example:** the policy of **dropping null skills data** is only appropriate when that data is optional or corrupt data that may be discarded by requirement. If anomalous data fields need to be flagged, include a separate validation step and error output before the collector.

## 12. Can It Be Combined with partitioningBy?

Yes. **Collectors.partitioningBy(predicate, downstream)** splits the source into **two Boolean groups**: true and false. A `flatMapping` downstream can flatten child elements **within each side**.

Conceptual example:

~~~java
Map<Boolean, List<String>> tags = articles.stream()
        .collect(Collectors.partitioningBy(
                Article::published,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.toList())));
~~~

This is an illustrative snippet, assuming Article has a **published() method returning boolean**, tags() returning List<String>, and appropriate imports. The result includes:

- Key **true**: all tags of published Articles.
- Key **false**: all tags of unpublished Articles.

Unlike `groupingBy`, **partitioningBy** has a contract to return both Boolean partitions, even if one partition has no elements; the downstream returns the appropriate empty value for that partition. This is useful when a report needs both sides explicitly present.

**Do not use partitioningBy for multi-key grouping** such as department or category; use groupingBy for that requirement.

## 13. Counting Parents and Children Are Two Different Operations

Suppose in the "guide" category there are:

~~~text
Article A: tags = [java, stream]
Article B: tags = []
Article C: tags = [collector]
~~~

The number of parent articles is **3**, the number of child tags is **3** (if counting all occurrences), and the number of distinct tags is also 3 in this example.

If you add "java" to Article C, the article count remains 3, the child tag count becomes 4, and the distinct tag count remains 3.

How to count articles:

~~~java
Map<String, Long> articleCount = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.counting()));
~~~

How to count tags:

~~~java
Map<String, Long> tagCount = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.counting())));
~~~

These are illustrative snippets. In **articleCount**, counting receives **Article** so it counts parents. In **tagCount**, counting receives each **String tag** after flatMapping so it counts children.

When presenting dashboards or reports, use specific names such as **articleCount**, **tagOccurrences**, **distinctTagCount**; just writing "Count" easily causes confusion between record count and child element count.

## 14. Does flatMapping Create an Intermediate List?

Not necessarily. If the downstream is **summingLong**, **counting**, **toSet**, or **toCollection(TreeSet::new)**, each U element is passed directly to the downstream's corresponding accumulator. There is no requirement to build an **intermediate List<U>** only to iterate over it afterward.

Example:

~~~java
Collectors.flatMapping(
        order -> order.lines().stream(),
        Collectors.summingLong(Line::amountCents))
~~~

This is an illustrative expression. Each Line can be added directly to the group's total. The benefits are clear:

- Avoids creating a large **Map<String,List<Line>>** only to iterate over each List to compute the sum.
- Directly expresses the collector's intent: flatten the Lines in each region and sum them.
- The downstream can be an application-defined Collector when specialized business results are needed.

**Even so, the child Stream is still a Stream with a lifecycle**, not a copied list. Do not return the same already-consumed Stream across multiple mapper calls; create a fresh Stream from the child collection each time the mapper runs.

## 15. Child Streams, Resources, and Lifecycle

The **Collectors.flatMapping** contract has special handling for the Stream returned by the mapper: after transferring the contents of the child Stream to the downstream, that Stream is **closed**. This is helpful when the mapper creates a Stream with associated resources, but **it does not mean every external resource API is managed for you**.

Considerations:

1. **Do not reuse a child Stream that has been closed/consumed.** Each mapper invocation must return a usable Stream.
2. **Do not store a child Stream in a field for multiple parent elements to return.** A Stream can only be consumed once; this shared structure easily causes IllegalStateException.
3. **If the child Stream represents I/O**, consider lifecycle, checked exceptions, and error policy. Standard Java APIs accepting Function do not declare arbitrary checked exceptions.
4. **If the mapper returns a null Stream**, flatMapping treats it as an empty Stream; however, code is clearer when returning `Stream.empty()`.
5. **Do not use the child Stream to update the source collection being traversed**: adhere to Stream non-interference.
6. **Do not keep a reference to a consumed stream to reuse after collect**. Once collect finishes, the resulting data resides in the downstream container, not in an open Stream.

**Do not confuse closing a Stream with closing everything that the elements inside reference.** Stream.close() runs the Stream's own registered close handlers; other application-managed resources must have their own contracts.

## 16. Collector Characteristics, Ordering, and Parallel Streams

For a sequential pipeline on a List, `toList` collecting tags in encounter order is usually predictable. When running in parallel, you need to understand the guarantee boundaries:

- `groupingBy` is a collector that may create and merge intermediate maps/containers; do not assume a fixed number of mapper calls or a fixed execution schedule order.
- `flatMapping` feeds each child Stream into the group's downstream. **Do not use side effects in the mapper or child Stream** for mandatory audit logging.
- `toList` preserves encounter order if the Stream is ordered and the collect contract requires preserving encounter order; however, `HashMap` by default does not guarantee iteration order of **group keys**.
- `toSet` and `TreeSet` have different ordering rules. If a downstream collector is **UNORDERED**, do not rely on encounter order as business semantics.
- `groupingByConcurrent` is a concurrent grouping variant but may have the **UNORDERED** characteristic. Do not replace `groupingBy` with `groupingByConcurrent` if child list order matters without checking the contract.
- Thread-safety of the resulting collection **does not arise automatically** merely from collecting a parallel stream.
- `parallel()` is not always faster: there is splitting/merging overhead, and child Streams may be small, making overhead significant.

**Recommendation:** When results require stable ordering, keep a source with encounter order, choose a downstream with clear semantics, and only use parallel after testing and measuring with real workloads. Do not rely on per-mapper logs as proof of final data order.

### 16.1. Mutable Objects and Side Effects

If tag, Line, or Employee is a mutable object, the resulting Set/List may hold references to those objects. Creating a new List with a Collector **does not deep-copy** the elements. If a Comparator in a TreeSet depends on a mutable field and that field changes after collect, the TreeSet's sorting/lookup behavior may no longer be consistent.

Avoid modifying the child List while `a.tags().stream()` is being traversed. This can cause ConcurrentModificationException or violate non-interference rules.

## 17. Deeper Composition: mapping, filtering, collectingAndThen

One of the strengths of **Composed Collectors** is being able to assemble multiple adapters into a downstream pipeline:

~~~java
Map<String, List<String>> cleanTags = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.mapping(
                                String::toLowerCase,
                                Collectors.filtering(
                                        s -> !s.isBlank(),
                                        Collectors.toList())))));
~~~

This is an illustrative snippet, assuming non-null tags. Each child String is converted to lowercase, filtered to be non-blank, and collected into a list by category.

**But do not force every step into an overly deep collector.** A clear mapper can also do the equivalent work:

~~~java
Collectors.flatMapping(
        a -> a.tags().stream()
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(s -> !s.isEmpty()),
        Collectors.toList())
~~~

This is an illustrative snippet importing Objects. It keeps the filtering/transformation operations on tags close to where the child Stream is created; easier to set breakpoints and read when you do not need to reuse standalone collector adapters.

You can use **collectingAndThen(downstream, finisher)** if you want to convert each group's result into another type after collection. For example, creating an unmodifiable list from a temporary list:

~~~java
Collectors.flatMapping(
        a -> a.tags().stream(),
        Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf))
~~~

This is an illustrative snippet. **List.copyOf** does not accept null elements, so you must ensure tags are non-null if using this approach. Additionally, the resulting list is **structurally** unmodifiable but does not create deep copies of element objects.

**Criteria for choosing how to write it:** prioritize clarity of element types before/after each step, null handling, ordering, mutability, and group semantics over crafting the longest functional expression.

## 18. Common Mistakes

| Mistake / Misconception | Consequence | Fix |
| --- | --- | --- |
| Passing a List directly to flatMapping's mapper | Type mismatch; mapper must return Stream | Use `list.stream()` |
| Replacing flatMapping with mapping when a flat list is needed | Unwanted `List<List<U>>` | Use flatMapping to pass each U to the downstream |
| Calling flatMap on everything before groupingBy when empty child groups must be kept | Groups with a parent but 0 children disappear | groupingBy parent then downstream flatMapping |
| Assuming groups are created automatically even without a parent | Keys with no input do not appear | Add standard group categories separately |
| Assuming counting always counts parents | With flatMapping, counting counts child U elements | Distinguish counting before and after flattening |
| Using toSet and expecting duplicate counts to be kept | Set removes duplicates | Choose toList or counting |
| Using toSet and expecting stable tag order | Set does not guarantee order | Choose LinkedHashSet/TreeSet as required |
| TreeSet comparator only compares a non-unique attribute | Elements considered equal are dropped | Add a tie-breaker or choose List |
| Not checking for a null tags list | NPE from `tags().stream()` | Validate or return Stream.empty by policy |
| Grouping by a classifier that returns null | `groupingBy` throws NPE | Validate or normalize the key |
| Assuming flatMapping automatically filters child nulls | Downstream may receive null | Filter/validate each U |
| Reusing the same child Stream | Stream already consumed/closed | Create a fresh stream on each mapper call |
| Performing mandatory side effects inside the mapper | Parallelism/optimizations make behavior unpredictable | Separate side effects into their own process |
| Using groupingByConcurrent and relying on encounter order | Hard to preserve intentional order | Choose an order-preserving collector |
| Thinking collect creates a deep copy | U elements may still be mutable | Explicitly clone/map if needed |
| Using List.copyOf on results containing null | NPE when the finisher runs | Filter/report null per contract |

## 19. Checklist When Writing flatMapping for Each Group

1. **What is the parent object (T)?** For example Article, Order, Employee.
2. **Where does the group key come from?** Must be determined at parent or child level; can it be null?
3. **How does the mapper create Stream<U>?** Do not pass List/Optional directly in place of Stream.
4. **Can a parent emit 0 child elements?** Do empty groups need to be kept?
5. **What downstream result is chosen?** List, Set, TreeSet, counting, summingLong...
6. **Can there be duplicate or null child elements?** Choose a data policy.
7. **Is stable ordering required?** Determine encounter order, mapFactory, and target Collection.
8. **Can child data be missing or corrupt?** Distinguish valid empty from failure.
9. **Does the child Stream hold resources or is it single-use?** Return a fresh stream and manage lifecycle.
10. **Are there side effects that must be guaranteed?** Do not hide auditing/state updates inside the collector.
11. **Will it run in parallel?** Check collector characteristics, performance, and output stability.
12. **Have you tested groups with many children, one child, 0 children, and no parent?** These are the four fundamental cases.

## 20. Practice Exercises

### Exercise 1: Mapping or flatMapping?

The source consists of two Articles with the same category "guide": article A has tags ["java","stream"], article B has tags ["collector"]. Write both collectors and predict the type of each result:

~~~java
Collectors.mapping(Article::tags, Collectors.toList())
Collectors.flatMapping(a -> a.tags().stream(),
        Collectors.toList())
~~~

These are illustrative expressions. Answer types: **List<List<String>>** versus **List<String>** in each group.

### Exercise 2: Keeping Empty Groups

A category "faq" has one Article with `List.of()` tags. Compare `groupingBy(Article::category, flatMapping(...))` with converting Articles to Stream<TagEntry> first and then `groupingBy(TagEntry::category)`. Why does faq only appear in the first approach?

### Exercise 3: Tag Count and Article Count

Given category "guide" with 3 Articles having 2, 0, and 4 tags respectively. Write a collector that counts the parent Articles and a collector that counts the total of 6 child tags. Use `counting()` in the right place in each problem.

### Exercise 4: Choosing the Downstream Type

From Stream<Article>, create:
- `Map<Category, List<Tag>>` keeping all occurrences.
- `Map<Category, LinkedHashSet<Tag>>` keeping unique tags in first-seen order.
- `Map<Category, TreeSet<Tag>>` sorting tags in natural order.

Explain how the Collection type determines what counts as a duplicate element and the iteration order.

### Exercise 5: Optional.stream()

An Account has `Optional<String> referralCode`. Group by team and collect referral codes. How many elements do Accounts with Optional.empty() contribute to the downstream? Does a group with Accounts but no codes appear?

### Exercise 6: Null-Safe and Corrupt Data

An Employee has a List<String> skills that may be null or contain null elements. Design two approaches:
- Approach allowing absence: null list becomes Stream.empty, filter out null skills.
- Approach requiring data: report an error for Employees missing skills at the boundary.

Why must these two approaches not be treated as having the same business meaning?

### Exercise 7: Summing Line Amounts

An Order has a List<Line>, where each Line has `long amountCents`. Group Orders by region, using flatMapping and summingLong to compute the total. Add a region that has one Order with 0 Lines. Predict the total value for that region.

### Exercise 8: Observing Parallel Collectors

Run the same dataset sequentially and in parallel, using TreeMap + downstream toList or LinkedHashSet. Verify the final contents according to the contract instead of relying on log order inside the mapper. Explain why you should not count the number of times the Supplier is invoked to deduce the number of groups.

## 21. Key Takeaways

**`Collectors.flatMapping(mapper, downstream)`** takes each parent element **T**, uses the mapper to create **Stream<U>**, and then passes each U to the downstream **within the corresponding group**. It is very useful when combined with **groupingBy** or **partitioningBy** so you do not have to keep **List<List<U>>** or manually construct intermediate objects just to flatten data.

Put the responsibilities in the right order: **groupingBy decides the group key from the parent; flatMapping decides which child elements enter the group; downstream decides the group's result** (List, Set, sum, count, etc.). A group with a parent but 0 children can still appear with an empty accumulator; a group with no parent at all is not created automatically.

Carefully check for **null in the parent, key, child list, and individual child elements**, because flatMapping is not a tool that cures every kind of null. Choose a downstream that matches duplication, ordering, and data error rules; avoid side effects and reusing child Streams.

A question to help choose the API: **“Do I want to flatten the entire stream's data before grouping, or keep the parent groups and flatten child elements separately within each group?”** If it is the second case, `Collectors.flatMapping()` is the right tool to use.
