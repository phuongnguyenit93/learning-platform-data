# `substring`, `intern`, and String Optimization Details Can Vary Across JDK Versions

## 1. Separating the API contract from implementation details

`String` is a core Java class: immutable, representing a sequence of UTF-16 code units, and providing operations such as `substring()`, `equals()`, and `intern()`. However, how the JVM lays out memory, reuses character storage, stores the intern table, or eliminates duplicate copies has changed several times across JDK versions.

When studying or optimizing `String`, you must separate **two layers**:

- **Language/API contract:** `substring(begin, end)` extracts the exact character slice; `equals` compares content; `intern` returns the canonical representation of that content in the pool. Programs must rely on these rules.
- **Implementation mechanism:** whether `String` uses `char[]` or `byte[]`, whether a substring shares a backing array, which memory region holds the pool, and whether the JIT/GC eliminates duplicates. These are choices made by the JDK version, JVM vendor, and runtime flags; do not treat them as an immutable API.

An optimization that made sense on an older JDK may be obsolete on a newer one; conversely, program correctness must never depend on assumptions about backing arrays, object size, or internal allocation counts.

| Topic | Stable guarantee for writing programs | JDK/JVM-dependent detail |
| --- | --- | --- |
| `substring` | Returns content from begin index (inclusive) to end index (exclusive) | Whether data is copied or backing storage is shared; allocation cost |
| `String.intern` | For strings equal under `equals`, `intern()` returns the same canonical reference | Pool table structure, storage location, GC, lookup speed |
| `String` immutability | String content cannot be modified after creation | Whether objects share an internal data array |
| `length` and `charAt` | Operate in UTF-16 `char` code units | Whether the string is stored in a compact byte array or a char array |
| String optimizations | Content and API behavior remain unchanged | Deduplication, compact storage, JIT, GC, concatenation strategy |

## 2. substring: same result, different storage strategies

Two common overloads:

```java
String substring(int beginIndex)
String substring(int beginIndex, int endIndex)
```

`beginIndex` is included in the result; `endIndex` is **excluded**. Indices are measured in UTF-16 `char` units, not Unicode code points.

```java
String source = "abcdef";
String part = source.substring(2, 5);

System.out.println(part);                    // cde
System.out.println(part.length());           // 3
System.out.println(part.equals("cde"));      // true
```

Invalid ranges such as `beginIndex < 0`, `endIndex > source.length()`, or `beginIndex > endIndex` throw `IndexOutOfBoundsException`. The API specifies **the sliced string's content**; it does not promise that every call allocates a brand-new `String` object and independent backing array.

### History: array sharing in older JDKs

In older OpenJDK/HotSpot implementations **prior to JDK 7u6**, `String` used a `char[]` array together with `offset`/`count` fields. A small `substring` could allocate a new `String` object yet **share the same large character array** with the parent string. The advantage was avoiding data copying; the trade-off was the risk of keeping a huge array alive solely because one short substring remained reachable.

Example of the historical scenario:

```text
Very long original string: [........ millions of characters ........]
                                    |
Substring takes only:              "id"

Old array-sharing implementation:
Small " id " still references the large backing char[].
When the original string is no longer used, the large backing array
may still not be freed because the substring remains alive.
```

Common point of confusion: this is called **unintended memory retention**, not a mutation of `String` content or a violation of immutability by the JVM.

Starting in **JDK 7u6**, the common implementation changed: `substring` could allocate character storage sized to the extracted slice instead of always sharing the full large array via `offset`/`count`. Because of that, the old trick `new String(large.substring(...))` to force a copy and drop the backing-array reference **should not be applied mechanically on modern JDKs**. The `String(String original)` constructor does not guarantee a separate copied backing array today; immutable `String` semantics allow sharing backing data whenever beneficial.

**Design takeaway:** use `substring` to slice text as needed. When you genuinely have concerns about memory retention or throughput, check the **actual target JDK/JVM** using a heap profiler and benchmarks rather than applying blanket rules like "substring is always O(1)" or "substring always copies" across all versions. When slicing huge numbers of strings, allocation cost still needs measurement.

### UTF-16 and the risk of splitting surrogate pairs

Even when internal storage uses compact bytes, the `substring` API still uses **UTF-16 indices**. For example, the emoji `🚀` is one Unicode code point yet requires two `char` values:

```java
String value = "A🚀B";
System.out.println(value.length());                    // 4
System.out.println(value.codePointCount(0, value.length())); // 3
System.out.println(value.substring(1, 3));             // 🚀
```

Calling `substring(1, 2)` takes only half of the surrogate pair; a Java `String` can still hold an unpaired code unit, though it may not render as the intended character. When processing by code points, compute indices with `offsetByCodePoints` or iterate with `codePoints()`; do not confuse a `char` with a user-perceived character.

## 3. intern(): stable contract, changing pool location

`String.intern()` returns a canonical object for the content; for any two strings where `a.equals(b)` is `true`, `a.intern() == b.intern()` is also `true`. String literals and compile-time constant String expressions are interned. How the JVM stores and manages canonical objects can change as long as that contract holds.

```java
String literal = "java";
String created = new String("java");
System.out.println(created == literal);          // false
System.out.println(created.equals(literal));      // true
System.out.println(created.intern() == literal);  // true
```

Historically in **HotSpot**, interned strings resided in **PermGen** on JDK 6 and earlier. **Starting in JDK 7**, interned `String` objects live on the **regular Java heap**; JDK 8 removed PermGen and introduced **Metaspace** for metadata, rather than moving application `String` objects into Metaspace. Different JDK/GC releases can change the pool's lookup table structure, lifetimes, or collection policies.

That **does not** mean interning is free or that interned objects live forever. For low-repetition sets such as UUIDs, session IDs, or random URLs, placing every input into the pool can add management overhead. Measure duplication rate, data lifetime, and heap profile before using `intern()` as an optimization.

The **Constant Pool and the Role of Constable/ConstantDesc** article details the differences between the String pool, class-file constant pool, and constant descriptor APIs. This section focuses on **implementation shifts and consequences when upgrading JDKs**.

## 4. String layout changes across JDK generations

| OpenJDK/HotSpot implementation era | Typical content storage | Upgrade implication to verify |
| --- | --- | --- |
| Many releases prior to Java 9 | `char[]` in UTF-16 units | Do not assume modern JDK footprints apply |
| Java 9+ with Compact Strings (JEP 254) | `byte[]` in LATIN1 or UTF16 format | Strings whose code units all fall in U+0000–U+00FF can save data bytes |

For example, `"Xin chào"` has `à` belonging to Latin-1, so it **can** be compact-eligible even though it is Vietnamese. A single character outside U+00FF causes the whole `String` to use UTF16 under this strategy. Nevertheless, `length()` still counts UTF-16 code units, and `getBytes(StandardCharsets.UTF_8)` still produces UTF-8 interchange bytes.

This is an implementation matter, not a Java SE requirement across all JVMs. Do not access `value`/`coder` via reflection to reason about application correctness. For a detailed analysis of coder selection, the impact of `-XX:-CompactStrings`, and memory overhead, see the **Compact Strings** article and the **Object Cost, Backing Arrays, and Temporary Strings** article.

## 5. String Deduplication: sharing data without merging objects

**JEP 192 — String Deduplication in G1**, introduced in HotSpot JDK 8u20 with the G1 GC, aims to reduce memory when many distinct `String` objects hold identical content. Under eligible conditions, the GC can make those `String` objects **share the same backing data array** while remaining **two separate `String` objects**.

```text
String object A ----\
                     > shared "AB" data (when GC deduplicates)
String object B ----/

A and B remain two distinct object references.
```

This is **not** `intern()`:

| Mechanism | Canonicalizes the String object itself? | Primary goal | Observable behavior in Java code |
| --- | --- | --- | --- |
| `intern()` | Yes: returns one canonical object per content | Identity canonicalization when called explicitly | Two `intern` results for equal strings compare `true` with `==` |
| GC String Deduplication | No: may share the **content array** while keeping separate Strings | Reduce duplicate backing arrays | `equals` remains true; `==` between two separate objects remains `false` |

On a supporting HotSpot/JDK, you can test the following options in a **measurement environment**:

```bash
java -XX:+UseG1GC -XX:+UseStringDeduplication YourApp
```

Effectiveness depends on duplicate content volume, object lifetimes, the GC, memory pressure, and CPU overhead. There is no guarantee that any specific `String` will be deduplicated immediately or that an application will always run faster with the option enabled. Supported flags and collectors can vary by JDK; check the `java`/`-XX` documentation for your target runtime before using in production.

**Do not use `a == b` to measure deduplication.** When two `String` objects are created separately, their identities stay distinct even after the GC shares their backing data. Verify via heap/GC metrics or a profiler, not Java reference equality.

## 6. Other optimizations that also depend on JVM version

Beyond `substring`, `intern`, compact storage, and deduplication, allocation and performance behavior are also shaped by:

- **JIT and escape analysis:** the runtime compiler can transform, optimize, or eliminate unobservable allocations, though it does not guarantee every `new String` or concatenation is eliminated.
- **Concatenation with `+`:** compilers/JVMs can use different strategies; since Java 9, JEP 280 introduced an `invokedynamic`-based strategy for `javac` string concatenation bytecode. Never assume `a + b` produces the same `StringBuilder` count or allocation count across every JDK.
- **GC and heap sizing:** object management/relocation algorithms, collector choice, and reclamation behavior yield different timings and footprints even with identical source code.
- **Unicode versions and case-handling rules:** upgrading the JDK can update Unicode data in related APIs; if logic relies on character properties or case-mapping rules, re-test with real datasets.

Each change can improve many workloads, yet there is no "single best flag" for every application. Avoid drawing conclusions from a single run on a developer workstation.

## 7. Java 17+ example with stable results across implementations

Save to `StringVersionDemo.java`:

```java
public class StringVersionDemo {

    public static void main(String[] args) {
        String parent = "abcdef";
        String piece = parent.substring(2, 5);

        System.out.println("substring = " + piece);
        System.out.println("substring length = " + piece.length());
        System.out.println("substring content = " + piece.equals("cde"));

        String literal = "java";
        String created = new String("java");
        System.out.println("new equals literal = " + created.equals(literal));
        System.out.println("new == literal = " + (created == literal));
        System.out.println("intern == literal = " + (created.intern() == literal));

        String folded = "ja" + "va";
        System.out.println("constant == literal = " + (folded == literal));

        String runtime = new StringBuilder()
                .append("ja")
                .append("va")
                .toString();
        System.out.println("runtime equals literal = " + runtime.equals(literal));
        System.out.println("runtime intern == literal = " + (runtime.intern() == literal));

        String first = new String(new char[] {'A', 'B'});
        String second = new String(new char[] {'A', 'B'});
        System.out.println("equal objects = " + first.equals(second));
        System.out.println("different references = " + (first != second));
        System.out.println("interned references = " + (first.intern() == second.intern()));

        String rocket = "\uD83D\uDE80";
        System.out.println("rocket UTF16 units = " + rocket.length());
        System.out.println("rocket code points = "
                + rocket.codePointCount(0, rocket.length()));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 StringVersionDemo.java
java StringVersionDemo
```

Output:

```text
substring = cde
substring length = 3
substring content = true
new equals literal = true
new == literal = false
intern == literal = true
constant == literal = true
runtime equals literal = true
runtime intern == literal = true
equal objects = true
different references = true
interned references = true
rocket UTF16 units = 2
rocket code points = 1
```

This program tests **observable contracts** rather than backing-array sizes:

- `substring` returns the right content without asserting whether the data array was copied.
- `new String("java")` produces a different reference from the literal while matching its content.
- `intern` returns a canonical representation; calling `intern` on equal strings yields the same reference.
- Two distinct `String` instances created from separate `char` arrays with content `"AB"` remain two objects; GC deduplication does not alter their identity check.
- `length()` still counts in UTF-16 regardless of whether Compact Strings is used internally.

Do not write unit tests asserting memory addresses, internal `value` fields, exact byte footprint, or `substring` speed. Those characteristics require benchmarks/profilers and can shift even across patch versions.

## 8. How to verify optimizations on the exact JDK you run

### Step 1: record the environment precisely

Check the current JDK and JVM:

```bash
java -version
javac -version
```

Record the vendor, update build, operating system, CPU architecture, heap size, collector, and relevant JVM flags. Saying "Java 17" alone is not enough to establish that two processes have identical footprints and optimization strategies.

### Step 2: measure the actual problem

Before optimizing, identify the metric:

- If you care about **heap footprint**, use a heap dump/profiler to inspect `String` counts, backing data sizes, and retaining references.
- If you care about **allocation rate/GC**, use Java Flight Recorder (JFR), GC monitoring tools, or an appropriate allocation profiler.
- If you care about **throughput/latency** of slicing and concatenation, use a benchmark with warm-up and representative data; [JMH](https://github.com/openjdk/jmh) is OpenJDK's dedicated tool. Do not wrap `System.nanoTime()` around a single `substring` call to draw conclusions.
- If you care about **intern/dedup**, measure duplicate value counts, lifetimes, and pool/GC overhead. Never infer memory savings from `==`.

### Step 3: compare one variable at a time

Run the same workload with the target JDK version/JVM flags, hold data and resources constant, and measure multiple runs; account for GC cost and side effects. For instance, only test `-XX:+UseStringDeduplication` when your runtime supports it and measurements show substantial duplicate strings. Do not blindly pass legacy flags like `-XX:MaxPermSize` on JDKs that removed PermGen.

### Step 4: prioritize correctness before micro-optimization

When code is clear and fits its data bounds, usually keep standard `substring`, `equals`, and ordinary string creation. Add caches, `intern`, or JVM flags only after proving a bottleneck and verifying with regression tests. Performance can also shift when upgrading a JDK patch, switching collectors, or changing production data volume.

## 9. Easily mistaken claims

| Claim | Assessment and accurate understanding |
| --- | --- |
| "`substring` always creates a view sharing the parent array." | False for many modern JDKs; that was the behavior of some older implementations prior to JDK 7u6. |
| "`substring` must always copy and takes O(n) on every JVM." | Not an API guarantee; performance, edge cases, and JIT optimizations depend on the implementation. |
| "`new String(s)` always allocates a new backing array, so call it after `substring`." | False on modern JDKs; avoid obsolete historical workarounds. |
| "All interned Strings live in PermGen." | False since JDK 7 in HotSpot; interned objects reside on the regular heap. |
| "JDK 8 Metaspace is where the String pool is stored." | False; Metaspace replaced part of PermGen's metadata role, not where Java strings live. |
| "`intern` makes `equals` faster for every string." | False; maintaining the pool has overhead and does not replace content comparison rules. |
| "String Deduplication turns `a == b` into true." | False; it can share internal backing data without merging String objects. |
| "JDK 9+ always uses UTF-8 for String because of Compact Strings." | False; compaction uses Latin-1 or UTF-16 in supporting implementations, not API UTF-8 encoding. |
| "Every accented character must take two bytes in Compact Strings." | False; characters in Latin-1 such as `é` can use one byte in compact form. |
| "Changing JDKs does not affect memory optimizations." | False; layout, JIT, GC, and flags evolve. Re-measure whenever optimization matters. |

## 10. Self-check exercises

**Exercise 1.** Can you write code assuming `big.substring(0, 3)` always keeps a reference to `big`'s entire backing data array?

**Answer:** No. That was a detail of some older JDKs. The API contract only guarantees the sliced content and valid index handling.

**Exercise 2.** Why does the following print `true` then `false`?

```java
String literal = "abc";
String copy = new String("abc");

System.out.println(literal.equals(copy));
System.out.println(literal == copy);
```

**Answer:** `equals` compares content whereas `==` compares identity; `new String(...)` creates a new `String` object.

**Exercise 3.** What does `a.intern() == b.intern()` tell you if `a.equals(b)` is `true`?

**Answer:** Both strings with equal content map to the same canonical representation in the pool. It does not prove they were originally the same object before calling `intern`.

**Exercise 4.** Two `String` instances `a` and `b` are distinct objects with identical content. After GC String Deduplication, does `a == b` become `true`?

**Answer:** No. Deduplication may share internal backing data, while each `String` object keeps its own identity.

**Exercise 5.** Why can `"café"` be stored compactly on a JVM supporting Compact Strings, while `"漢字"` needs a different representation?

**Answer:** All characters in `"café"` lie in Latin-1; `"漢字"` contains characters outside Latin-1. This is JEP 254's data storage strategy and does not change the Unicode/UTF-16 semantics provided by the `String` API.

## References

- [Java SE 17 — `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): contracts for `substring`, `intern`, immutability, and the UTF-16 model.
- [Oracle — Java Virtual Machine Enhancements in JDK 7](https://docs.oracle.com/javase/8/docs/technotes/guides/vm/enhancements-7.html): change in location of interned strings in HotSpot starting in JDK 7.
- [Oracle — JDK 9 Enhancements, JEP 254 Compact Strings](https://www.oracle.com/java/technologies/javase/9-enhancements.html): `byte[]` + Latin-1/UTF-16 coder layout and the `CompactStrings` option.
- [OpenJDK — JEP 192 String Deduplication in G1](https://openjdk.org/jeps/192): sharing duplicate String backing data and heap reduction goals since JDK 8u20.
- [OpenJDK — JEP 280 Indify String Concatenation](https://openjdk.org/jeps/280): string concatenation implementation changes starting in Java 9.
- [Aleksey Shipilëv — java.lang.String Catechism (2014)](https://2014.jokerconf.com/presentations/shipilev-string.pdf): visual analysis of `substring` history and memory cost of pre-JDK 7u6 array sharing.

**Guiding principle:** write Java based on standard `String` semantics; measure `substring`, `intern`, and memory optimizations on the **actual JDK/JVM running your application**. Rules of thumb about backing arrays, pools, allocations, or GC always belong in the context of a specific version.
