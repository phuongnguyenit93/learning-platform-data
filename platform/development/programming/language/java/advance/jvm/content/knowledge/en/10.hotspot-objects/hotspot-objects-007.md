# Compact Strings, string interning, and string deduplication: three mechanisms, three different purposes

`String` is an immutable type and appears at very high density in Java programs: JSON keys, HTTP headers, log messages, field names, status codes, configuration values, and text rows from databases. When observing the **HotSpot** heap, we commonly encounter three String-related optimization mechanisms:

1. **Compact Strings** reduces the memory used to **represent characters inside a String object** when the content can be encoded in Latin-1.
2. **String interning** provides a **canonical String object** for strings with the same content, through the literal/constant pool and the `String.intern()` API.
3. **String deduplication** is a garbage collector optimization: **String objects remain distinct**, but can **share the underlying character data array** when the arrays are identical.

These three mechanisms **do not replace each other**. Compact Strings does not turn two String objects into the same object; interning changes the reference the caller receives back; and deduplication operates inside the runtime and **does not turn the expression `a == b` from `false` to `true`** for two separate objects.

The content below distinguishes **public Java semantics** from **HotSpot implementation details**, explains JVM memory layout within bounds, illustrates with **runnable Java 17+**, and guides measurement-based inspection/optimization rather than relying on guesswork.

## 1. First: String is immutable, while references have identity

In Java, each variable of type `String` holds a **reference** to a String object, or `null`. The sequence of characters that a String represents is **immutable** by API contract: a call such as `concat`, `replace`, or `toUpperCase` does not modify the character content of an existing String.

```java
String first = "cache";
String second = first;
String third = new String("cache");
```

Here:

- `first == second` is `true` because both hold the **same reference**.
- `first.equals(third)` is `true` because the two Strings represent the **same content**.
- `first == third` is `false` because `new String(...)` created a separate String object.
- Immutable string content allows the runtime to share backing storage safely **as long as it does not alter observable Java semantics**.

**`==` on two String references checks object identity**, not text. In business code, use `equals` when the goal is to compare content, even if the application enables interning or string deduplication.

### 1.1. Two different "units of sharing"

```text
Strings A and B with content "cache"

A) Separate String objects, separate backing arrays:
   a ──► String@A ──► byte[] #1 = "cache"
   b ──► String@B ──► byte[] #2 = "cache"
        a != b       arrays contain identical bytes

B) Interning (if the caller uses the reference returned by intern):
   a.intern() ──┐
                ├──► canonical String@C ──► backing array #C
   b.intern() ──┘
        same String object when comparing the resulting references

C) Deduplication:
   a ──► String@A ──┐
                    ├──► same backing byte[] #D
   b ──► String@B ──┘
        a != b, but data storage can be shared
```

This diagram is a **conceptual model of modern HotSpot**, not a memory format that the Java Language Specification requires every JVM to use.

## 2. Compact Strings: reducing the data size of EACH string

### 2.1. From `char[]` to `byte[]` with encoding information

Before JDK 9, many OpenJDK `java.lang.String` implementations used a backing `char[]`, with each element being 16 bits. **JEP 254 — Compact Strings** (JDK 9) switched HotSpot/OpenJDK String to a more efficient internal representation, conceptually:

```text
String object in HotSpot JDK 17 (illustrative)
┌───────────────────────────────────┐
│ object header and other fields    │
│ "value" reference ───────────┐    │
│ coder = LATIN1 or UTF16      │    │
└───────────────────────────────┼────┘
                                ▼
                          byte[] value
                          LATIN1 / UTF16 encoding
```

- If all **UTF-16 code units** in the String can be represented in the range `U+0000..U+00FF`, HotSpot can use the **LATIN1 coder**, approximately **1 byte per code unit** in the backing data.
- If it cannot be represented in LATIN1, HotSpot uses the **UTF16 coder**, approximately **2 bytes per UTF-16 code unit** in the backing data.
- The internal fields `byte[] value` and `byte coder` are **HotSpot/OpenJDK implementation details**, not a public Java API or a mandatory layout for every JVM.
- Regardless of the coder, the Java API of `String` still follows **UTF-16 semantics**: `length()` and `charAt` are based on code units; they do not switch to byte units just because the internal representation is LATIN1.

"Compact" here does **not** mean String switches to UTF-8 universally for all content. LATIN1 in HotSpot is a 1-byte mode for UTF-16 code units with values up to 255; if other characters are needed, an internal UTF16 representation is used.

### 2.2. Examples of Latin-1, Asian characters, and emoji

| Content | Java `length()` | Code points | HotSpot Compact Strings typically chooses | Illustrative character data |
| --- | ---: | ---: | --- | --- |
| `"Hello"` | 5 | 5 | LATIN1 | About 5 bytes |
| `"café"` (é = U+00E9) | 4 | 4 | LATIN1 | About 4 bytes |
| `"雪"` (U+96EA) | 1 | 1 | UTF16 | About 2 bytes |
| `"😀"` (U+1F600) | 2 | 1 | UTF16 | About 4 bytes |

The numbers in the last column only estimate the **backing array payload**; they **do not include** the String object header, byte array header, alignment, reference fields, compressed oops, or other objects. Therefore, one must not say the string `"Hello"` occupies 5 bytes of heap in total.

An emoji has one Unicode code point outside the Basic Multilingual Plane but occupies **two UTF-16 code units** (a surrogate pair); this is the clearest example of why `length()` cannot be equated with the number of displayed characters.

### 2.3. What can a Java 17 program observe?

Create the file **`CompactTextDemo.java`**:

```java
public class CompactTextDemo {
    public static void main(String[] args) {
        String latin = "café";
        String cjk = "雪";
        String emoji = "😀";

        System.out.println("latinLength=" + latin.length());
        System.out.println("cjkLength=" + cjk.length());
        System.out.println("emojiLength=" + emoji.length());
        System.out.println("emojiCodePoints=" +
                emoji.codePointCount(0, emoji.length()));
        System.out.println("latinCharAt3=" + latin.charAt(3));
        System.out.println("cjkCharAt0=" + cjk.charAt(0));
    }
}
```

Run with JDK 17+ in a terminal environment that supports Unicode:

```bash
javac --release 17 -encoding UTF-8 CompactTextDemo.java
java -Dfile.encoding=UTF-8 CompactTextDemo
```

**Stdout according to Java content (assuming the terminal displays Unicode correctly):**

```text
latinLength=4
cjkLength=1
emojiLength=2
emojiCodePoints=1
latinCharAt3=é
cjkCharAt0=雪
```

What this example **proves via API** is how `String.length()` / `charAt` / `codePointCount` behave, not "measuring `byte[] value` directly". Java does not expose a public method to ask whether a String is currently assigned the LATIN1 or UTF16 coder by HotSpot. Inspecting the internal layout requires specialized tools/JVM knowledge and respecting module constraints; do not rely on `--add-opens` reflection as a stable API.

### 2.4. Why does `getBytes(StandardCharsets.UTF_8)` not tell us the internal coder?

`getBytes` **encodes text into a new byte array according to the charset requested by the caller**. It does not mean returning the String's internal `value` directly. For example, an internally LATIN1 String can still produce more UTF-8 bytes for the character `é`.

```java
import java.nio.charset.StandardCharsets;

String text = "café";
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
int utf16Bytes = text.getBytes(StandardCharsets.UTF_16BE).length;
// UTF-8: 5 bytes; UTF-16BE: 8 bytes for this example.
```

This is an **illustrative code snippet**, not a standalone runnable file. `"café"` uses 4 UTF-16 code units, but in UTF-8 the character `é` occupies two bytes. Do not infer HotSpot's backing `byte[]` from a `getBytes` result.

### 2.5. Costs and limitations of Compact Strings

Commonly expected benefits:

- For applications containing many Latin-1 strings, reduces payload from approximately 2 bytes/code unit down to 1 byte/code unit.
- Fewer bytes to copy/scan and less heap pressure in suitable scenarios.
- HotSpot String functions/intrinsics support both LATIN1 and UTF16 to preserve Java semantics.

Limitations:

- A String with **at least one code unit > U+00FF** requires the UTF16 coder in this mechanism; it does not compress half the string as Latin-1 and the remaining half as UTF16 in the same backing value.
- String objects and byte-array headers still have overhead.
- Some operations need coder checks/conversions and have CPU cost; performance gains must be measured per workload.
- Compact Strings **does not deduplicate across String objects**; multiple independently constructed `"same"` Strings can still hold multiple backing arrays without a separate dedup mechanism.

### 2.6. The HotSpot `-XX:-CompactStrings` flag

On supporting HotSpot/OpenJDK builds (including JDK 17), Compact Strings is enabled by default and has a diagnostic flag to **disable** it:

```bash
java -XX:-CompactStrings -cp . CompactTextDemo
```

Java API behavior and example stdout **must remain unchanged**; what changes is HotSpot's internal encoding/data layout choice. Do not use this flag to "fix" Unicode characters or file charsets: console encoding and I/O codec issues must be resolved in their respective places.

## 3. String interning: sharing a CANONICAL String OBJECT

### 3.1. Contract of `intern()`

`String.intern()` is a **public Java API** that returns the canonical representation of a string. According to the `java.lang.String` documentation:

- If the intern pool already contains a String with the same content according to `equals`, `intern()` returns a reference to the canonical String in the pool.
- Otherwise, the String is added to the pool and a canonical reference is returned.
- For two Strings `s`, `t`: **`s.intern() == t.intern()` if and only if `s.equals(t)`**.
- **String literals** and the results of string-valued constant expressions are interned according to language rules.

This is a **contract about the identity of the intern result**, not an automatic mechanism that rewires local variables already pointing to other objects.

Example:

```java
String a = new String("same");
String b = new String("same");

boolean content = a.equals(b);         // true
boolean identity = (a == b);           // false
boolean canonical = (a.intern() == b.intern()); // true
```

Even after calling `intern()`, variables `a` and `b` still point to the **original objects**; `intern()` does not "rewrite references in variables" or turn all existing String objects into one.

### 3.2. Literals, constant expressions, and runtime concatenation

```java
String literalA = "hello";
String literalB = "he" + "llo";
String runtime = new StringBuilder().append("he").append("llo").toString();
```

- `"he" + "llo"` is a **compile-time constant expression**, so it represents the same canonical value as the literal `"hello"`; `literalA == literalB` is `true`.
- `runtime` has content equal to `"hello"` but is constructed at runtime, so it is not required to point to the literal object.
- `runtime.intern()` returns the canonical String with content `"hello"`, which the literal already provided, so `== literalA` is `true`.

**Do not assume every `+` operation creates a new String**: constant folding can happen at compile time; the optimizer can also simplify runtime expressions when it does not change observable behavior. When teaching object identity, use an explicit `new String` example, where the constructor call forces a new object to be created according to `new` semantics.

### 3.3. Runnable program with deterministic stdout

Create the file **`InterningDemo.java`**:

```java
public class InterningDemo {
    public static void main(String[] args) {
        String literal = "shared";
        String folded = "sha" + "red";
        String a = new String("shared");
        String b = new String(new char[] {'s','h','a','r','e','d'});

        System.out.println("literal==folded=" + (literal == folded));
        System.out.println("a.equals(b)=" + a.equals(b));
        System.out.println("a==b=" + (a == b));
        System.out.println("a==literal=" + (a == literal));

        String ca = a.intern();
        String cb = b.intern();

        System.out.println("ca==cb=" + (ca == cb));
        System.out.println("ca==literal=" + (ca == literal));
        System.out.println("a==b after intern=" + (a == b));
    }
}
```

Commands:

```bash
javac --release 17 InterningDemo.java
java InterningDemo
```

**Exact stdout:**

```text
literal==folded=true
a.equals(b)=true
a==b=false
a==literal=false
ca==cb=true
ca==literal=true
a==b after intern=false
```

The last line is crucial: after calling `intern`, **only `ca` and `cb` hold the canonical result**. Interning does not switch `a` and `b` to the same object while we still hold the two old references.

### 3.4. Does the intern pool reside in the Java heap?

There is a difference between **API semantics** and memory layout details across JDK releases. In modern HotSpot, canonical `String` objects are Java objects managed on the heap; HotSpot has a StringTable/handles structure for lookup. **Do not** mechanically apply the old HotSpot generation model of "interned strings always live in Permanent Generation and exist forever" to Java 17.

Do not depend on hash table addresses/design, GC entry reclamation behavior, or specific class loader optimizations to determine the semantics of `intern()`. The public contract is **canonical identity by content when using the intern result**.

### 3.5. When should you actively intern?

It can be considered when:

- There is a **small, heavily repeated, and relatively stable vocabulary**: for example status names, event types, key schemas, or type labels.
- You have **measured with a profiler/heap dump** and seen many duplicate String objects that cannot be easily reused through better domain data structures.
- There is an appropriate retention/throughput management strategy to avoid putting excessive pressure on the StringTable.

Do not by default intern all uncontrolled input from HTTP requests, log lines, UUIDs, session tokens, random identifiers, or high-cardinality strings. Many unique values cause high lookup/housekeeping overhead while having **few** objects to share.

**Interning is not a way to encode Strings**, not a public "free memory" API, and should not be used as a replacement for `equals` or a cache structure with a clear lifecycle/eviction policy.

## 4. String deduplication: sharing BACKING ARRAYS, not merging objects

### 4.1. The idea behind JEP 192 and HotSpot G1

**String Deduplication** (JEP 192, introduced into HotSpot G1 since the JDK 8 line) detects multiple `String` objects carrying **identical backing data content** and attempts to have them share the backing storage.

In JDK 8 when the feature was introduced, Strings were typically stored in `char[]`. In **HotSpot JDK 17 after Compact Strings**, the content resides in **`byte[] value`**, so explanations for JDK 17 should refer to **backing byte arrays**, rather than saying every modern String still uses `char[]`.

```text
BEFORE deduplication:
  reference a ──► String@A ──► byte[] #1 = [72,101,108,108,111]
  reference b ──► String@B ──► byte[] #2 = [72,101,108,108,111]
                            (two arrays containing identical bytes)

AFTER deduplication (if GC selects two eligible objects):
  reference a ──► String@A ──┐
                             ├──► byte[] #1 = [72,101,108,108,111]
  reference b ──► String@B ──┘
  byte[] #2 may no longer be retained by those Strings.

  a == b is still FALSE; a.equals(b) is still TRUE.
```

**What is shared is the data array**, not turning `String@B` into `String@A`. If the GC automatically merged object identities, Java logic using `==`, object monitors, or `System.identityHashCode` could observe changes; that is not the goal of String Deduplication.

### 4.2. Is every duplicate string guaranteed to be deduplicated?

**No.** This is an **implementation/GC optimization**, not a mandatory Java semantic feature.

In HotSpot G1, the GC typically filters **candidate String objects** by age conditions and processing phases, then performs lookup/insertion into a separate dedup table. Deduplication can run **concurrently** and depends on GC cycles, object liveness, duplication rate, and thresholds.

Consequences:

- Two identical Strings may **not yet** be deduplicated right after creation.
- There is no standard Java API `String.isDeduplicated()` for an application to know the backing array state.
- `System.gc()` **is only a request/hint** to the GC, not a guarantee that all candidates are deduplicated before the call returns.
- The same program can produce different dedup metrics across two runs, two heap sizes, or two JVM configs.
- Dedup helps reduce heap live set when many identical backing arrays remain alive; it also consumes CPU, metadata/table processing, and has trade-offs.

### 4.3. Enabling on HotSpot JDK 17 with G1

According to the JDK 17 `java` command documentation, the options:

- **`-XX:+UseStringDeduplication`** enables string deduplication.
- On JDK 17 HotSpot, the mechanism is documented as supported with **G1 GC**, so enable `-XX:+UseG1GC` explicitly.
- This option is **disabled by default** on JDK 17.
- **`-Xlog:stringdedup*=debug`** requests Unified Logging to output string deduplication information, though output/format depends on the JVM and GC activity.

```bash
java -XX:+UseG1GC -XX:+UseStringDeduplication -Xlog:stringdedup*=debug DedupWorkload
```

This is a command specific to **HotSpot JDK 17**. Other JVMs/GCs or later releases may have different support/default flags; verify `java -version` and the documentation for the exact version in use. Enabling the flag does **not** guarantee a fixed memory-saving number.

### 4.4. A program that creates many String objects with duplicate content

Create the file **`DedupWorkload.java`**:

```java
public class DedupWorkload {
    private static volatile String[] keepAlive;

    public static void main(String[] args) {
        String[] values = new String[200_000];

        for (int i = 0; i < values.length; i++) {
            String content = "status-" + (i % 8);
            values[i] = new String(content.toCharArray());
        }

        keepAlive = values;
        System.out.println("objects=" + values.length);
        System.out.println("contentEqual=" + values[0].equals(values[8]));
        System.out.println("sameObject=" + (values[0] == values[8]));

        System.gc();
        System.out.println("gcRequested");
    }
}
```

Compile:

```bash
javac --release 17 DedupWorkload.java
```

Run normally:

```bash
java DedupWorkload
```

**Stdout from application code (excluding additional JVM logs):**

```text
objects=200000
contentEqual=true
sameObject=false
gcRequested
```

Explanation:

1. There are **200,000 String references** in an array kept reachable via `keepAlive`.
2. There are only **8 distinct contents**: `status-0` through `status-7`.
3. `new String(content.toCharArray())` creates separate String objects from char data; when Compact Strings is enabled, they typically use LATIN1 payload, but initially have the opportunity to hold many duplicate backing arrays.
4. `values[0]` and `values[8]` have equal content but are **two separate objects**. String dedup, if it occurs, does not change `==`.
5. `System.gc()` is not a wait guarantee that dedup has completed; `gcRequested` only confirms the code **invoked the GC hint**.

### 4.5. Reading logging properly

Run with G1 + dedup logging:

```bash
java -XX:+UseG1GC -XX:+UseStringDeduplication -Xlog:stringdedup*=debug DedupWorkload
```

The **application stdout** still has the four lines above, but **JVM logs do not have a fixed format or line count**; output can be larger and appear before/between printed lines. Depending on object age, GC cycles, and execution time, significant bytes saved may not necessarily be visible by the time the program exits.

If proper benchmarking is needed:

- Keep the set of String objects alive long enough across multiple GC cycles according to workload conditions.
- Use multiple runs and the same JDK/GC/heap settings when comparing enabled vs. disabled.
- Read heap snapshots/histograms and appropriate GC metrics; distinguish retained heap, total allocations, and pause/CPU costs.
- Do not treat a reduction in String object count as the primary goal of dedup: **object count may not change**, whereas backing byte arrays/retained memory is what decreases.
- Do not force repeated `System.gc()` calls in production just to trigger this mechanism.

## 5. Comparison table of the three mechanisms by exact unit of savings

| Criterion | Compact Strings | `intern()` | String deduplication |
| --- | --- | --- | --- |
| Mechanism layer | HotSpot/String internal representation | Public `String.intern()` + JVM literal canonicalization | HotSpot GC optimization |
| Goal | Reduce **bytes per backing value** when content fits Latin-1 | Reuse the **same String object** for equal content | Reuse the **same backing array** across separate String objects |
| When it occurs | When a String is created/converted to the appropriate representation | When processing literals/constants or caller invokes `intern()` | When GC identifies and processes candidates |
| Requires proactive caller code? | No for default HotSpot behavior | Yes to actively intern runtime Strings; literals auto-intern | Usually enabled via VM flag, no Java source changes |
| Changes `a == b` of two original objects? | No | Does not alter two old refs automatically; **result `a.intern() == b.intern()` is true by content** | No |
| Reduces String object headers? | No by Compact Strings itself | Opportunity to reuse **one** canonical object when application keeps the result | No |
| Reduces duplicated backing arrays? | Shrinks each array's size, **does not merge** duplicate arrays | When using canonical object, uses that object's backing array | **Can** share the same byte[] across multiple objects |
| Semantics/API | Does not change public String behavior | Canonical identity of the result is observable | **Does not change Java-level identity/equality results** |
| Trade-off | Coder handling/encoding, layout-specific overhead | StringTable lookup, retention, GC/throughput | Candidate scanning, dedup table CPU/memory, GC work |
| Positioning for JDK 17 | JEP 254 / HotSpot default | Java `String` API, JLS literals | JEP 192, G1 with `UseStringDeduplication` |

**Distinguish "object count" from "data size":** one million short Strings with the same content can save memory in two very different ways. Interning returns the same object so many references point to **one String**. Deduplication does not change the total number of String instances, but seeks to reduce the **number of backing arrays holding identical content**.

### 5.1. Illustrative memory example

Suppose there are 100,000 String objects, each with Latin-1 content of 40 UTF-16 code units, and temporarily **ignoring all headers, alignment, and overhead**:

- When using 16-bit data per code unit: one array's payload is about **80 bytes**, total payload of 100,000 arrays is about **8 MB**.
- With Compact Strings LATIN1: one array's payload is about **40 bytes**, total about **4 MB** if each String still has its own backing array.
- If String dedup can let all Strings with the exact same content share one array: duplicate payload can drop sharply; however, **100,000 String object headers still remain**.
- If the application replaces references with the `intern()` result for the same content, it can retain **one canonical String object** instead of duplicate objects that are no longer reachable; actual memory depends on lifecycle, GC, and other references.

This is only an **illustrative payload calculation** to show the different units, **not a prediction of RSS, committed heap, retained size, or the byte counts a GC log will report**.

## 6. Do combining Compact Strings, interning, and dedup conflict?

In principle, they can **coexist** in HotSpot:

```text
Java application
  │
  ├── creates Strings
  │      └── Compact Strings chooses appropriate LATIN1/UTF16 backing payload
  │
  ├── calls intern() when wanting canonical String
  │      └── caller uses reference returned from StringTable
  │
  └── GC with string dedup enabled
         └── tries to identify identical Strings/backing arrays
             then reduces duplicated backing storage where possible

Unchanged boundaries:
  - equals() compares content;
  - == compares object identity;
  - public String API does not directly expose coder/byte[] identity;
  - JVM and GC may choose internal optimizations.
```

There is no formula like "enabling all three will reduce RAM by exactly 75%" for every workload. The benefit depends on Latin-1 ratio, length and duplication, lifecycle, heap size, GC, StringTable pressure, and object graph.

If the application **already actively uses canonical references for most repeated values**, fewer duplicate String objects remain, which can reduce the additional benefit from dedup. If the application needs to keep separate String objects (for example, data transfer objects holding many fields), dedup can still save backing arrays without requiring reference replacement.

### 6.1. Why should `==` not be used even when the system interns?

A piece of data can come from:

- An interned String literal.
- A JSON parser creating new objects.
- A Database/JDBC driver creating new Strings.
- Deserialization, reflection, JNI, or libraries creating separate objects.
- Runtime operations like `substring`, `replace`, `StringBuilder.toString()`.

There is no guarantee that **every producer** returns canonical objects under the same policy. If one data path forgets to intern, `==` can unexpectedly fail even when two strings have the same text. Use `equals` to compare content; rely on reference identity only when **you are genuinely managing a strictly controlled canonicalization invariant**.

### 6.2. Dedup is not automatic interning

A HotSpot G1 with `UseStringDeduplication` enabled must not change `a == b` of two `new String(...)` calls from false to true, because distinct identity is observable by a Java program. Nor does it mean `s.intern()` becomes redundant regarding the canonical references contract.

What the GC can change is the **backing byte[] referenced by the object**, not the identity of the String objects.

## 7. What `javap` can and cannot prove

Use:

```bash
javac --release 17 CompactTextDemo.java InterningDemo.java DedupWorkload.java
javap -c -p InterningDemo
javap -c -p CompactTextDemo
```

Three layers must be distinguished:

1. **Source-level behavior**: `String.intern()`, `equals()`, and `length()` are in the public API.
2. **Bytecode-level operations**: `ldc` to load a String literal from the runtime constant pool, `new` / `invokespecial` to create an object, `invokevirtual String.intern` to call the API.
3. **HotSpot internal layout and GC runtime**: `byte[] value` / `coder`, string dedup candidates/tables, and GC logs.

`javap` can show **`ldc`** in code creating literals, **`new java/lang/String`** in constructors, and **`invokevirtual String.intern`** at call sites. However, `javap -c` **is not a heap inspector**: it does not print an object's current coder or prove that two Strings have shared a backing array after GC.

If inspecting internal `String.value` via reflective access with flags like `--add-opens java.base/java.lang=ALL-UNNAMED`, that is **accessing details that are not part of the public contract**, carrying risks of differences across JDK releases. Do not turn such reflection hacks into business-logic coding guidelines.

## 8. Practical scenarios: which mechanism to consider?

### 8.1. Applications with many short, repetitive JSON field names

- Compact Strings automatically helps reduce the payload of Latin-1 field names.
- If the parser or application has a **small standard field-name table**, canonicalization/interning or a lifecycle-controlled cache can be considered.
- If many independent String objects are still created, G1 string dedup can reduce duplicated backing arrays.
- Before enabling/optimizing, check whether the parser/library has its own symbol canonicalization mechanism; doing it twice can increase overhead without helping further.

### 8.2. Servers producing many identical error or status codes

For example, `"SUCCESS"`, `"PENDING"`, `"FAILED"` appear frequently in objects. If they are literals reused directly, Java already has canonical literals. If they arrive from the network/database as new Strings, object identity is still different; intern/cache/dedup should be evaluated based on repetition rate and retention.

Regardless, using an enum or a value object with clear domain semantics is sometimes better than keeping millions of raw Strings; that is an **API design** decision, not solely HotSpot GC's responsibility.

### 8.3. Mostly unique log messages, UUIDs, and tokens

When values rarely repeat:

- Compact Strings can still reduce payload if the content is Latin-1.
- Interning is unlikely to save memory, because almost no canonical references are reused.
- String dedup can incur CPU/table overhead while finding little duplicated content.

**Do not** use `intern()` for every HTTP header value, path containing IDs, or arbitrary tokens without measurements; this can be a high-cardinality unbounded workload.

### 8.4. Multilingual Unicode, characters beyond Latin-1

If most Strings contain Chinese characters, Japanese characters, emoji, or code units beyond `U+00FF`:

- Compact Strings LATIN1 provides little benefit on those Strings; UTF16 mode is required in HotSpot's representation.
- Interning still works by **Unicode content**, independent of coder.
- Dedup can still share backing arrays **when content matches**, even with UTF16 encoding.

**Do not treat "UTF16 coder" as a Unicode correctness issue.** It is an internal data choice for characters that LATIN1 cannot represent.

## 9. Tracking costs in HotSpot JDK 17

Use measurement tools before/after with the same input and the same configuration:

```bash
# Baseline G1 (dedup is disabled by default on JDK 17):
java -XX:+UseG1GC DedupWorkload

# Enable dedup and view HotSpot logs:
java -XX:+UseG1GC -XX:+UseStringDeduplication -Xlog:stringdedup*=debug DedupWorkload

# Compare String API behavior, CompactStrings enabled/disabled:
java CompactTextDemo
java -XX:-CompactStrings CompactTextDemo

# Check matching flags in the HotSpot being used:
java -XX:+PrintFlagsFinal -version
```

To explain a memory metric, you must specify what is being measured:

- **Heap allocated bytes:** amount of data created over a period of time.
- **Heap live set/retained size:** data still reachable after GC at the observation point.
- **Process RSS:** includes committed heap, native allocations, stacks, code cache, and many other kinds of memory.
- **GC time/CPU:** collector cost, including string dedup overhead when enabled.
- **String object count:** number of objects, which may **not decrease due to dedup**.
- **Backing array count/size:** closer to dedup's target, but requires appropriate tools/heap dumps to see clearly.

You cannot take a single `Runtime.totalMemory() - freeMemory()` before/after and immediately infer dedup effectiveness: it is affected by GC scheduling, class loading, TLAB, JIT, string ages, and other memory.

### 9.1. Minimal benchmark procedure

1. Fix the JDK vendor/version, GC, `-Xms/-Xmx`, workload, and dataset.
2. Run sufficient warm-up and multiple iterations; keep data reachable until measurement.
3. Compare **G1 baseline** with **G1 + `UseStringDeduplication`** while keeping other parameters unchanged.
4. If evaluating Compact Strings, measure separately with `-XX:-CompactStrings`; avoid changing GC/heap size in the same experiment.
5. Read GC logs, heap histograms/dumps, and appropriate allocator/CPU metrics instead of relying on a single `System.gc()`.
6. Confirm the real application has a sufficiently high duplicate String frequency; synthetic workloads are only illustrative.
7. Measure p95/p99 latency and CPU if the application is latency-sensitive, because heap savings can trade off against throughput/CPU.
8. Document trade-offs and have a flag rollback plan when deploying to production.

## 10. Common misconceptions

1. **"Compact Strings is pooling of identical strings."** False: it is a more compact character representation **within each String**, not merging String objects.
2. **"String uses UTF-8 internally since Java 9."** False in HotSpot JDK 17; JEP 254 uses LATIN1/UTF16 via `byte[]` + coder.
3. **"LATIN1 only holds ASCII 0..127."** False: it can also represent UTF-16 code units up to `U+00FF`; for example `é`.
4. **"`length()` counts bytes of the internal value."** False: `length()` counts UTF-16 code units.
5. **"An emoji always has `length() == 1` because it is one visible character."** False: characters outside the BMP use a surrogate pair, typically `length()==2`.
6. **"`getBytes(UTF_8)` returns HotSpot's backing `byte[] value`."** False: that is a conversion according to the requested charset.
7. **"Calling `intern()` automatically turns the calling object into the same reference as the object in the pool."** False: the caller must **use the returned value**.
8. **"If two strings have the same content, `a == b` is always true."** False: use `equals` to compare content.
9. **"All runtime concatenation is auto-interned."** Not guaranteed. Literals and string-valued constant expressions are the standard cases.
10. **"Interned strings stay permanently in PermGen on Java 17."** False: do not apply old HotSpot layouts to modern HotSpot.
11. **"String deduplication merges String objects into one."** False: it targets **backing arrays**; object identities remain unchanged.
12. **"Enabling `UseStringDeduplication` guarantees all duplicates are processed immediately."** False: GC selection/timing is non-deterministic.
13. **"Dedup will turn `a == b` from false to true."** False: object identity does not change.
14. **"Dedup is enabled by default on HotSpot JDK 17 G1."** False according to the JDK 17 `java` command documentation: the option is disabled by default.
15. **"Enabling dedup always saves RAM and speeds things up."** False: it depends on duplication and CPU/GC overhead.
16. **"Calling `System.gc()` and immediately reading results proves dedup is complete."** False: GC is a hint, with no guarantee dedup is finished.
17. **"`new String("abc")` is equivalent to getting back the literal object itself."** False: it creates a separate String object; backing data may be shared depending on implementation.
18. **"If the internal byte[] is shared, two Strings must be the same object."** False: object identity and backing storage identity are different.
19. **"Toggling `-XX:-CompactStrings` will break `equals`/Unicode."** False: an internal optimization must not break the Java API contract.
20. **"You can measure the coder using `String.getBytes` to know the real layout."** False: an encoding result is not a storage inspector.

## 11. Self-check with answers

**Question 1.** What does Compact Strings do for a String of 40 code units all within U+0000..U+00FF?

**Answer:** HotSpot can use a LATIN1 backing payload of about 40 bytes instead of UTF16 of about 80 bytes; total heap object size must still add headers/padding.

**Question 2.** What are `length()` and `codePointCount(0,length())` for the String `"😀"`?

**Answer:** `length() == 2`; code point count is `1`.

**Question 3.** Why can the String `"café"` use LATIN1 in HotSpot while `getBytes(UTF_8)` has length 5?

**Answer:** LATIN1 internal representation and UTF-8 external encoding are two different encodings; `é` is U+00E9 (one LATIN1 byte) but two UTF-8 bytes.

**Question 4.** `a.equals(b)==true` but `a==b==false`; after calling `a.intern()` and `b.intern()`, does `a==b` change?

**Answer:** No. If keeping the original refs, it is still false. `a.intern()==b.intern()` is what is true under the canonical pool contract.

**Question 5.** Does enabling string dedup turn two `String` objects with duplicate content into one object?

**Answer:** No. HotSpot can only let two separate objects share a backing byte array; object identities do not change.

**Question 6.** If an application has 100,000 Strings but almost all contents are different, should `intern()` be enabled indiscriminately?

**Answer:** Not by default. With little duplicate content, StringTable/cache overhead can outweigh the benefits; profiling is needed.

**Question 7.** Is data consisting entirely of Chinese characters compressed as LATIN1 by Compact Strings?

**Answer:** No, if there are code units outside U+00FF, HotSpot uses the UTF16 representation under this mechanism.

**Question 8.** Why does `DedupWorkload` stdout still show `sameObject=false` even when GC has successfully deduplicated?

**Answer:** Because GC only shares backing arrays, not merging two String objects; `==` compares identities.

**Question 9.** Which HotSpot JDK 17 flags enable string dedup on G1?

**Answer:** `-XX:+UseG1GC -XX:+UseStringDeduplication`; `-Xlog:stringdedup*=debug` can be added to view logs depending on GC activity.

**Question 10.** Why can't `javap -c` alone be used to conclude that a String is using UTF16 backing and has been deduplicated?

**Answer:** `javap` shows bytecode and the constant pool, not the runtime backing data of individual objects or GC dedup status.

## 12. Short summary in three sentences

**Compact Strings** answers: *How many bytes is a String object using to store characters under HotSpot's internal representation?*

**String interning** answers: *Can references returned by `intern()` point to the same canonical String object when contents are equal?*

**String deduplication** answers: *Can separate String objects share the same backing array to reduce heap footprint?*

```text
                     String with content "shared"
                               │
                      ┌────────┴────────┐
                      │                 │
              Compact Strings       Interning
              LATIN1 / UTF16        canonical object
              fewer bytes/array     for equal content
                      │                 │
                      └────────┬────────┘
                               │
                        GC deduplication
                      (if enabled/eligible)
                               │
                multiple separate String objects
                  can share backing data

equals(): content             == : object identity
```

All three can bring benefits together, but **choose the right tool for the right problem**: Compact Strings optimizes **encoding/storage of each value**, interning optimizes **canonical object reuse**, and dedup optimizes **duplicate backing arrays across objects**. When optimizing a real application, prioritize API semantics, measure memory/GC/CPU on a representative workload, and only change configuration or code after understanding both the benefits and the costs.

### References

- [JEP 254 — Compact Strings](https://openjdk.org/jeps/254): representing String with `byte[]` and LATIN1/UTF16 coder (Java 9+).
- [JEP 192 — String Deduplication in G1](https://openjdk.org/jeps/192): goal of sharing backing arrays of equal Strings.
- [Java SE 17 — `String.intern()` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#intern()): canonical reference contract and literals.
- [JLS Java SE 17 — String literals (`3.10.5)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.5): interned literals/constant expressions.
- [JDK 17 `java` launcher manual — `UseStringDeduplication`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): G1 option and default value.
- [HotSpot/OpenJDK JDK 17 `String.java` source](https://github.com/openjdk/jdk17/blob/master/src/java.base/share/classes/java/lang/String.java): byte[]/coder implementation details, not public ABI.
- [JDK 17 `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): observing bytecode/constant pool.
