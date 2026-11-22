# Hashtable, Dictionary, and Properties in Legacy Code

## 1. Read the Role Correctly Before Replacing a Class

When maintaining a long-lived Java application, you may encounter `Dictionary` in method signatures, `Hashtable` in shared data areas, and `Properties` where configuration is loaded.

These three names have an inheritance relationship, but they do not share the same purpose:

| Component | Role to Identify |
| --- | --- |
| Dictionary<K,V> | Legacy abstract class representing a key–value mapping |
| Hashtable<K,V> | A synchronized hash table implementation that also implements the Map interface |
| Properties | String-based property set with configuration read/write support and a default value mechanism |

If you treat all three as simply "an old Map", you might replace code that still compiles but changes null handling, synchronization, iteration behavior, or default value lookup.

The goal when reading legacy code is to identify the contract the code relies on. Only then should you decide whether to keep a compatibility boundary, migrate to `Map`, or continue using `Properties` for its proper configuration job.

The term "legacy" here does not mean all three classes carry the `@Deprecated` annotation. In the Java 17 API, `Dictionary` is described as obsolete; `Hashtable` and `Properties` remain available APIs for use and compatibility. The `Properties.save` method is a specific example that is marked deprecated.

This article uses Java 17+ and four standalone programs. Each example includes its filename, run command, and stdout; none rely on the arbitrary iteration order of a hash table.

## 2. Relationship Between Dictionary, Hashtable, Map, and Properties

The type hierarchy can be read as follows:

```text
Object
└── Dictionary<K,V>
    └── Hashtable<K,V>  implements Map<K,V>
        └── Properties  extends Hashtable<Object,Object>
```

### 2.1. Dictionary Is an Abstract Class, Not Another Name for Map

`Dictionary` has basic operations such as `get`, `put`, `remove`, `size`, `isEmpty`, and two methods `keys`/`elements` returning `Enumeration`.

It does not declare that it implements `Map`. Therefore, a variable of type `Dictionary` does not automatically have `keySet` or `entrySet` just because the underlying runtime object might be a `Hashtable`.

Conversely, an arbitrary `Map` is not automatically a `Dictionary`. You cannot change all occurrences of `Dictionary` to `Map` on one side and assume every legacy caller will still accept the right type.

The [Java 17 Dictionary documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Dictionary.html) directs new implementations to `Map` rather than extending `Dictionary`.

### 2.2. Hashtable Acts as a Bridge via Type Relationships

A `Hashtable` object can be viewed through a `Dictionary` variable or a `Map` variable without copying data.

All three variables pointing to the same object still view the same table. Changing the reference variable type does not turn a `Hashtable` into a `HashMap`, does not remove synchronization, and does not allow `null`.

Conversely, creating a new `HashMap` and copying the mappings creates a separate table. The copy does not update automatically when the source table changes.

### 2.3. Properties Inherits a Broader Surface Than Configuration Semantics

`Properties` extends `Hashtable<Object,Object>`, not `Hashtable<String,String>`.

Its configuration API expects both property names and values to be `String`. However, inherited APIs like `put(Object,Object)` still exist, so the compiler does not block every case of inserting the wrong type.

This is a point that must be read by API intent, not just by which methods can be called.

## 3. Dictionary and Enumeration: Reading a Legacy API with Control

### 3.1. Basic Iteration

`Enumeration` has two familiar methods:

| Enumeration | Meaning |
| --- | --- |
| hasMoreElements() | Whether there are remaining elements to retrieve |
| nextElement() | Retrieves the next element; may throw NoSuchElementException if none remain |

To read each pair from a `Dictionary`, you can iterate over `keys` and call `get(key)`. There is no need for raw casts or assuming the two streams `keys` and `elements` can be paired position-by-position.

An `Enumeration` does not directly provide a `remove` operation like `Iterator`. Java 9+ provides `asIterator` to adapt to code that expects an `Iterator`; the default adapter's `remove` operation is unsupported. Do not interleave the original `Enumeration` and that `Iterator` to control the same traversal. See [Java 17 Enumeration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Enumeration.html).

### 3.2. Example 1: Same Object vs. a Copy

Save as **LegacyDictionaryBridge.java**:

```java
import java.util.Dictionary;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.Hashtable;
import java.util.Map;
import java.util.TreeMap;

public class LegacyDictionaryBridge {
    static <K, V> Map<K, V> copyEntries(Dictionary<K, V> source) {
        Map<K, V> copy = new HashMap<>();
        Enumeration<K> keys = source.keys();
        while (keys.hasMoreElements()) {
            K key = keys.nextElement();
            copy.put(key, source.get(key));
        }
        return copy;
    }

    public static void main(String[] args) {
        Hashtable<String, Integer> table = new Hashtable<>();
        Dictionary<String, Integer> dictionary = table;
        Map<String, Integer> alias = table;
        dictionary.put("alpha", 10);
        dictionary.put("beta", 20);

        Map<String, Integer> copy;
        synchronized (table) {
            copy = copyEntries(dictionary);
        }
        System.out.println("dictionary alpha: " + dictionary.get("alpha"));
        System.out.println("contains beta as value: " + table.contains("beta"));
        System.out.println("containsKey beta: " + table.containsKey("beta"));
        System.out.println("contains value 20: " + table.contains(20));
        System.out.println("copy before update: " + new TreeMap<>(copy));

        table.put("alpha", 99);
        System.out.println("alias alpha after update: " + alias.get("alpha"));
        System.out.println("copy alpha after update: " + copy.get("alpha"));

        try {
            table.put(null, 1);
        } catch (NullPointerException expected) {
            System.out.println("null key: rejected");
        }
        try {
            table.put("gamma", null);
        } catch (NullPointerException expected) {
            System.out.println("null value: rejected");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LegacyDictionaryBridge.java
java LegacyDictionaryBridge
```

Stdout:

```text
dictionary alpha: 10
contains beta as value: false
containsKey beta: true
contains value 20: true
copy before update: {alpha=10, beta=20}
alias alpha after update: 99
copy alpha after update: 10
null key: rejected
null value: rejected
```

The programs in this article are compiled with `--release 17` and run on OpenJDK 24.0.2. The `--release` flag selects the target language/API level and bytecode version; it does not change the executing JVM version.

### 3.3. Why Does `alias` See 99 While `copy` Remains 10?

The variables `dictionary`, `table`, and `alias` all point to the same `Hashtable` object. Therefore, updating `alpha` through `table` is visible through `alias`.

The `copy` variable is a new `HashMap` containing the mappings read earlier. Changing the `alpha` binding in the source table does not change the `alpha` binding in the copy.

This is a copy of the mappings, not a deep copy of every key/value object. If a value is a shared mutable object, both tables can still see the same value object.

`TreeMap` in the print statement only keeps stdout ordering deterministic by `String` key. It is not evidence that `Hashtable` or `HashMap` preserves alphabetical order.

### 3.4. Synchronization When Copying Depends on the Actual Source Object

The `copyEntries` method does not by itself provide a safe copy transaction for every `Dictionary` implementation.

In the example, the actual source is a `Hashtable`, and the caller wraps the entire traversal in `synchronized(table)`. This uses the same monitor object as `Hashtable`'s synchronized operations; no other modifications in the program interleave with it.

For a different `Dictionary` implementation, you must read its concurrency contract. Putting `synchronized` on an arbitrary reference variable does not guarantee that all writers coordinate on the same lock.

## 4. Hashtable Characteristics That Frequently Change Maintenance Outcomes

### 4.1. Neither Null Keys Nor Null Values Are Accepted

`Hashtable` rejects `put(null, value)` and `put(key, null)`. Lookups like `get(null)` are also not a way to query for a valid null key.

In a valid state with no null values, `get` returning `null` means there was no mapping for the queried key at the time of that access.

Do not turn this into a guarantee that the mapping remains absent afterward when other threads are updating the table.

The [Java 17 Hashtable documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Hashtable.html) specifies the null policy and key `equals`/`hashCode` requirements.

### 4.2. `contains` in Legacy Code Searches Values

The name `contains(Object)` is easily misread as "does this key exist". On `Hashtable`, it checks values, having the same functional meaning as `containsValue`.

In the example:

- `contains`("beta") is `false` because there is no `String` value `"beta"`.
- `containsKey`("beta") is `true` because the key `beta` exists.
- `contains`(20) is `true` because `beta` is mapped to value `20`.

When migrating code to `Map`, translate the intent accurately to `containsValue` or `containsKey`. Do not replace based on similar-looking method names.

### 4.3. No Iteration Order Guarantee

`Hashtable` provides no contract for insertion order or sorted key order.

If a test compares an entire `toString` output containing multiple keys, the result may depend on unnecessary implementation details. When order is a real requirement, express that requirement using an appropriate structure or sorting step.

Keys still require consistent `equals`/`hashCode`. Being `synchronized` does not fix a key whose hash-determining fields are mutated while it resides in the table.

### 4.4. Enumeration and Iterator Do Not Share the Same Contract

With `Hashtable`:

| Traversal Method | What to Remember |
| --- | --- |
| keys()/elements() returning Enumeration | Not fail-fast; if structurally modified during traversal, the result is undefined by contract |
| Iterator from collection views | Best-effort fail-fast behavior for structural modifications outside permitted paths |
| Single traversal with multiple calls | Not automatically an atomic operation just because individual map methods are synchronized |

Not receiving a `ConcurrentModificationException` does not prove that an `Enumeration` is traversing safely. A fail-fast exception is also not a protection mechanism for shared data.

Do not extrapolate this table to all subclasses: `Properties` has its own iterator description in Java 17.

### 4.5. Synchronization Is a Property, Not an Answer for Every Operation

`Hashtable` protects its individual operations with synchronization. That does not automatically make an application-written sequence of calls an uninterruptible operation.

Nor is there any guarantee that internal fields of a mutable value stored in the table are protected if the application mutates them outside the map.

During maintenance, you must identify the protected data, operation boundaries, and all sites accessing the same data.

## 5. Example 2: Why Can Two Individually Safe Calls Still Lose Updates?

### 5.1. An Interleaving Schedule That Causes the Bug

To increment `hits`, two threads can both read the same value `0` and then each write back `1`:

| Step | Thread A | Thread B |
| --- | --- | --- |
| 1 | get receives 0 | |
| 2 | | get receives 0 |
| 3 | put 1 | |
| 4 | | put 1 |

Neither `get` nor `put` needs to corrupt the table's internal structure. The bug lies in the "read, increment, then write" intent not being protected as a single unit.

The program below uses a `CyclicBarrier` to force both threads to finish reading before writing. Thus, the result `1` in the first part is produced deterministically, rather than hoping a race condition happens by chance.

### 5.2. Complete Program

Save as **HashtableCompoundActions.java**:

```java
import java.util.Hashtable;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class HashtableCompoundActions {
    static int separatedReadWrite(ExecutorService pool) throws Exception {
        Hashtable<String, Integer> counter = new Hashtable<>();
        counter.put("hits", 0);
        CyclicBarrier bothRead = new CyclicBarrier(2);
        Callable<Void> increment = () -> {
            int before = counter.get("hits");
            bothRead.await(5, TimeUnit.SECONDS);
            counter.put("hits", before + 1);
            return null;
        };
        Future<Void> first = pool.submit(increment);
        Future<Void> second = pool.submit(increment);
        first.get(5, TimeUnit.SECONDS);
        second.get(5, TimeUnit.SECONDS);
        return counter.get("hits");
    }

    static int protectedIncrements(ExecutorService pool, boolean useMerge)
            throws Exception {
        Hashtable<String, Integer> counter = new Hashtable<>();
        counter.put("hits", 0);
        Runnable increment = () -> {
            for (int i = 0; i < 1000; i++) {
                if (useMerge) {
                    counter.merge("hits", 1, Integer::sum);
                } else {
                    synchronized (counter) {
                        int before = counter.get("hits");
                        counter.put("hits", before + 1);
                    }
                }
            }
        };
        Future<?> first = pool.submit(increment);
        Future<?> second = pool.submit(increment);
        first.get(5, TimeUnit.SECONDS);
        second.get(5, TimeUnit.SECONDS);
        return counter.get("hits");
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            System.out.println("two separated increments: " + separatedReadWrite(pool));
            System.out.println("locked increments: " + protectedIncrements(pool, false));
            System.out.println("merge increments: " + protectedIncrements(pool, true));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 HashtableCompoundActions.java
java HashtableCompoundActions
```

Stdout:

```text
two separated increments: 1
locked increments: 2000
merge increments: 2000
```

### 5.3. Two Appropriate Protection Approaches for This Example

The `synchronized(counter)` block keeps both `get` and `put` within the same synchronization scope. With the same `Hashtable` instance and properly coordinating callers, one increment completes in full before another enters that section.

The `merge` approach uses an appropriate update operation instead of two separate calls. In the OpenJDK 17 implementation, `Hashtable` overrides `merge` as a synchronized method; you can cross-check [Hashtable.java](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Hashtable.java).

The example uses a short summing function that does not modify the map from within the passed function. Do not generalize this to "every `merge` on every `Map` is atomic": you must read the contract of the specific implementation.

Two threads in each protected section perform 1,000 increments each, so the final result is 2,000. The timeouts on the barrier and `Future` help the experiment fail with an error if it does not finish; they do not determine output order.

### 5.4. Replacing Hashtable with ConcurrentHashMap Still Requires Choosing the Right Operation

`ConcurrentHashMap` provides concurrent update operations with their own contracts. It does not automatically combine an application-written `get` followed by `put` into an atomic increment.

If the requirement is per-key incrementing, you must use the appropriate operation or a suitable protection model. If the requirement involves multiple keys at once, you must also consider invariants across the whole group.

The [Java 17 ConcurrentHashMap documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) is the basis for evaluating a replacement, rather than merely matching the phrase "thread-safe".

## 6. Properties Is String-Based Configuration Data with a Defaults Layer

### 6.1. The Recommended API Pair Is setProperty/getProperty

A configuration property has a `String` name and a `String` value. For example, `port` is the string `"8080"` while still in the configuration-reading layer; the application parses and validates it into an integer at the appropriate boundary.

`setProperty` accepts two `String` arguments. `getProperty` returns a `String` or a fallback value per its contract. This pair expresses intent more clearly than the inherited `put`/`get` API.

Because it extends `Hashtable<Object,Object>`, `Properties` still allows a call like `put("port", 9090)` to compile. That inserts an `Integer` into a data structure expected to hold strings.

Do not treat the ability to call a method as proof that the data type fits the entire `Properties` API. The [Java 17 Properties documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) recommends `setProperty` and describes failures when storing a property set containing mistyped entries.

### 6.2. Defaults Are a Fallback Source, Not putAll

A `Properties` instance can accept another `Properties` instance as `defaults`. `getProperty` searches the current layer and continues through the `defaults` chain when needed.

Default entries are not automatically copied into the current table. Consequently, `get`, `containsKey`, and `size` on the direct mappings do not have the same meaning as an effective configuration lookup via `getProperty`.

| Reading Method | Scope to Understand |
| --- | --- |
| get(key) | Direct mapping in the current object; returns Object |
| containsKey(key), size() | Direct mappings in the current object |
| getProperty(name) | Looks up a String property including the defaults chain |
| getProperty(name, fallback) | Checks the defaults chain first; if absent, returns the provided fallback |
| stringPropertyNames() | Set of string property names, including eligible names from defaults |
| propertyNames() | Enumeration of names including defaults; may fail if a non-String key was inserted |

Removing an override from the current layer can cause the default value to reappear. `remove` does not mean the property name disappears from the entire fallback chain.

### 6.3. Defaults May Still Be Shared

If the application retains a reference to the `defaults` object and mutates it, lookup results on the child object can change accordingly.

It is a link to a default source, not a promise that an independent snapshot was created when the constructor ran.

When a stable configuration is needed for a running instance, you can read the effective values, validate them, and build a separate immutable/stable data structure. Do not let accidental object sharing dictate when configuration changes.

## 7. Example 3: get, getProperty, Defaults, and Type Mismatches

Save as **PropertiesDefaultsAndTypes.java**:

```java
import java.io.StringReader;
import java.io.StringWriter;
import java.util.Map;
import java.util.Properties;
import java.util.TreeMap;
import java.util.TreeSet;

public class PropertiesDefaultsAndTypes {
    public static void main(String[] args) throws Exception {
        Properties defaults = new Properties();
        defaults.setProperty("host", "localhost");
        defaults.setProperty("mode", "safe");
        defaults.setProperty("port", "8080");

        Properties config = new Properties(defaults);
        config.setProperty("mode", "fast");
        System.out.println("get host: " + config.get("host"));
        System.out.println("getProperty host: " + config.getProperty("host"));
        System.out.println("containsKey host: " + config.containsKey("host"));
        System.out.println("local size: " + config.size());
        System.out.println("effective names: " + new TreeSet<>(config.stringPropertyNames()));

        config.remove("mode");
        System.out.println("mode after remove override: " + config.getProperty("mode"));
        config.setProperty("mode", "fast");
        defaults.setProperty("host", "server");
        System.out.println("host after defaults change: " + config.getProperty("host"));

        Map<String, String> effective = new TreeMap<>();
        for (String name : config.stringPropertyNames()) {
            effective.put(name, config.getProperty(name));
        }
        System.out.println("effective copy: " + effective);

        StringWriter writer = new StringWriter();
        config.store(writer, null);
        Properties reloaded = new Properties();
        try (StringReader reader = new StringReader(writer.toString())) {
            reloaded.load(reader);
        }
        System.out.println("reloaded mode: " + reloaded.getProperty("mode"));
        System.out.println("reloaded host: " + reloaded.getProperty("host"));
        System.out.println("reloaded names: " + new TreeSet<>(reloaded.stringPropertyNames()));

        config.put("port", 9090);
        System.out.println("raw port type: " + config.get("port").getClass().getSimpleName());
        System.out.println("getProperty port: " + config.getProperty("port"));
        try {
            config.store(new StringWriter(), null);
        } catch (ClassCastException expected) {
            System.out.println("store non-string value: rejected");
        }
        config.put(7, "bad-key");
        try {
            config.propertyNames();
        } catch (ClassCastException expected) {
            System.out.println("propertyNames non-string key: rejected");
        }
        System.out.println("string names after pollution: "
                + new TreeSet<>(config.stringPropertyNames()));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 PropertiesDefaultsAndTypes.java
java PropertiesDefaultsAndTypes
```

Stdout:

```text
get host: null
getProperty host: localhost
containsKey host: false
local size: 1
effective names: [host, mode, port]
mode after remove override: safe
host after defaults change: server
effective copy: {host=server, mode=fast, port=8080}
reloaded mode: fast
reloaded host: null
reloaded names: [mode]
raw port type: Integer
getProperty port: 8080
store non-string value: rejected
propertyNames non-string key: rejected
string names after pollution: [host, mode, port]
```

### 7.1. `host` Exists in Configuration Terms, Not in the Current Table

`config` only has the `mode` override, so `local size` is `1`. `get`("host") returns `null` and `containsKey`("host") returns `false`.

`getProperty`("host") still finds `"localhost"` from `defaults`. `stringPropertyNames` includes `host`, `mode`, and `port`.

After removing the `mode` override, `getProperty` sees `"safe"` again. After updating `host` in `defaults`, `config` sees `"server"`.

These results show why you cannot mechanically replace `getProperty` with `get` followed by a cast.

### 7.2. Copying Effective Values Differs from Copying Direct Entries

The `stringPropertyNames`/`getProperty` loop builds a `String`–`String` map containing effective values under the example's condition where no one concurrently modifies the configuration.

This is a clear choice for transferring loaded configuration data to a layer that uses `Map`. `new HashMap<>(config)` copies only the direct `Object`–`Object` mappings; it does not perform the same `defaults` lookup.

If concurrent changes can occur or a consistent configuration version is required, the multi-call loop must be placed inside an appropriate configuration publishing/reading workflow. Do not treat it as an atomic snapshot in all cases.

### 7.3. `store` Does Not Automatically Save All Defaults

`config` writes only the direct `mode` entry to the stored output. When reloaded into a new `Properties` without `defaults`, `mode` is still `fast` but `host` is absent.

If you want a file containing all effective values, you must explicitly flatten the `defaults` chain, build a clean string property set, and store that set.

If you want the file to store only overrides so that a runtime default source can still be used, the current behavior is what you want to preserve. Do not silently change the policy during maintenance.

### 7.4. Mistyped Entries Can Produce Misleading Behavior

After `put("port", 9090)`, `get` returns an `Integer`. In this example, `getProperty` still returns the string `"8080"` from `defaults` instead of converting `Integer` `9090` to a `String`.

The [OpenJDK 17 Properties.java source](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Properties.java) shows that `getProperty` accepts only `String` values in the current layer before falling back to `defaults`.

Do not use that behavior as a configuration technique. It illustrates how a mistyped entry can be masked by a fallback value, causing raw-reading code and property-reading code to see different data.

`store` rejects a property set containing a non-`String` value. `propertyNames` rejects when an `Integer` key is present. `stringPropertyNames` skips mistyped entries and can still include `port` from `defaults` in the result.

The set of string names is not a validation that the entire object contains no mistyped data. Mistyped entries must be prevented or checked at the input boundary.

## 8. The .properties Format and Encoding: Seeing the Two Processing Layers Clearly

### 8.1. Bytes to Characters, Then Characters to Properties

When reading a file, there are two distinct tasks:

1. Decoding bytes into characters according to a character encoding.
2. Parsing property lines, delimiters, and escapes.

`load`(InputStream) has its own ISO-8859-1 rule. It does not automatically become UTF-8 just because the current Java environment has UTF-8 as its default charset.

`load`(Reader) receives characters already decoded by the `Reader`. To read a UTF-8 file, create a `Reader` explicitly with UTF-8, such as via `Files.newBufferedReader` or `InputStreamReader`.

[Java 17 Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) describes `Reader`/`Writer` APIs with a `Charset`; [Java 17 Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) specifies the byte and character overloads.

### 8.2. A Real Data Sample, Not a Java String Literal

Below is the property content after constructing the string in the program, equivalent to the contents of a UTF-8 file:

```properties
# Example properties
message=Chào bạn
path=C:\\temp\\data
joined=first\
  second
escaped\ key:some\:value
empty=
bare
quoted="hello"
duplicate=old
duplicate=new
```

In this format:

- Comment lines have `#` or `!` at an appropriate starting position.
- Names and values can be separated by `=`, `:`, or unescaped whitespace according to the syntax rules.
- Whitespace or delimiters belonging to a name must be escaped when they would otherwise be ambiguous.
- A line with a name and no value part produces an empty string value.
- Quotes do not create JSON-like quoting syntax; quote characters in the value can be preserved literally.
- Backslashes are involved in escaping and line continuation, rather than always being preserved literally.

The `joined` line has a line-continuation backslash. That backslash, the line terminator, and leading whitespace on the next line are stripped; no space is automatically inserted between `first` and `second`.

### 8.3. Watch Out for Paths and Double Escaping

To make a property value contain a single backslash, a `.properties` file generally must represent it with two backslashes.

If you write that file content inside a Java string literal, you also have to handle Java's own escaping layer. That is why the Java snippet in the program has more backslashes than the file content shown above.

Do not adjust the number of backslashes solely because they look excessive. Determine whether you are reading Java source code, `.properties` text, or the parsed value.

An invalid escape for an ordinary character may simply have its backslash dropped by the `Properties` reader; it does not always report an error like the Java compiler. A malformed Unicode escape, however, can throw `IllegalArgumentException`.

`Properties` also does not automatically expand environment variables or evaluate expressions just because a value has a special-looking syntax. If a framework adds such a mechanism, distinguish it from `java.util.Properties`.

### 8.4. Complete Program Testing UTF-8, Escapes, and Reloading

Save as **PropertiesTextAndEncoding.java**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class PropertiesTextAndEncoding {
    public static void main(String[] args) throws Exception {
        String text = "# Example properties\n"
                + "message=Chào bạn\n"
                + "path=C:\\\\temp\\\\data\n"
                + "joined=first\\\n"
                + "  second\n"
                + "escaped\\ key:some\\:value\n"
                + "empty=\n"
                + "bare\n"
                + "quoted=\"hello\"\n"
                + "duplicate=old\n"
                + "duplicate=new\n";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

        Properties fromReader = new Properties();
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(utf8), StandardCharsets.UTF_8)) {
            fromReader.load(reader);
        }
        Properties fromBytes = new Properties();
        try (ByteArrayInputStream input = new ByteArrayInputStream(utf8)) {
            fromBytes.load(input);
        }

        System.out.println("UTF-8 Reader message: "
                + "Chào bạn".equals(fromReader.getProperty("message")));
        System.out.println("byte overload message: "
                + "Chào bạn".equals(fromBytes.getProperty("message")));
        System.out.println("path: " + fromReader.getProperty("path"));
        System.out.println("joined: " + fromReader.getProperty("joined"));
        System.out.println("escaped key: " + fromReader.getProperty("escaped key"));
        System.out.println("empty length: " + fromReader.getProperty("empty").length());
        System.out.println("bare length: " + fromReader.getProperty("bare").length());
        System.out.println("quoted: " + fromReader.getProperty("quoted"));
        System.out.println("duplicate: " + fromReader.getProperty("duplicate"));

        try (StringReader reader = new StringReader("duplicate=latest\n")) {
            fromReader.load(reader);
        }
        System.out.println("second load keeps path: " + fromReader.containsKey("path"));
        System.out.println("second load duplicate: " + fromReader.getProperty("duplicate"));

        StringWriter writer = new StringWriter();
        fromReader.store(writer, null);
        Properties writerRoundTrip = new Properties();
        try (StringReader reader = new StringReader(writer.toString())) {
            writerRoundTrip.load(reader);
        }
        System.out.println("Writer round-trip message: "
                + "Chào bạn".equals(writerRoundTrip.getProperty("message")));

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        fromReader.store(output, null);
        Properties byteRoundTrip = new Properties();
        try (ByteArrayInputStream input = new ByteArrayInputStream(output.toByteArray())) {
            byteRoundTrip.load(input);
        }
        System.out.println("byte round-trip message: "
                + "Chào bạn".equals(byteRoundTrip.getProperty("message")));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 PropertiesTextAndEncoding.java
java PropertiesTextAndEncoding
```

Stdout:

```text
UTF-8 Reader message: true
byte overload message: false
path: C:\temp\data
joined: firstsecond
escaped key: some:value
empty length: 0
bare length: 0
quoted: "hello"
duplicate: new
second load keeps path: true
second load duplicate: latest
Writer round-trip message: true
byte round-trip message: true
```

### 8.5. Why Does the Byte Overload Fail While the Byte Round-Trip Succeeds?

The first read passes UTF-8 bytes to the overload that assumes ISO-8859-1. The two sides do not use the same decoding rules, so the resulting Vietnamese string does not match the expected data.

In the `store(OutputStream)` step, `Properties` writes using the byte format and escaping appropriate for that API. `load`(InputStream) reads back data produced by that matching format, so the Vietnamese value is restored.

This does not mean that `load(InputStream)` will correctly read an arbitrary UTF-8 input file in all cases.

`Reader`/`Writer` also form a load–store pair at the character level. When a `Writer` is connected to an actual byte-backed file, the caller must still choose its charset.

### 8.6. `load` Merges Data; It Does Not Clear Old Configuration

The sample data has `duplicate` appearing twice; the later value overwrites the earlier one.

Then the program loads another document containing only `duplicate=latest` into the same object. `duplicate` changes to `latest`, while `path` remains present.

Therefore, "reloading" can merge/overwrite the keys read, rather than replacing the entire configuration set with the new file's contents.

When the requirement is to replace the entire configuration, reading into a new object, validating it, and then publishing the new version is usually easier to reason about than mutating an in-use object piecemeal.

## 9. Read/Write Decisions to Preserve During Maintenance

### 9.1. `store` Preserves Property Data, Not Original Text

Do not use `load` followed by `store` as a tool to preserve comments, line ordering, and formatting of the original file.

`store` may rewrite escapes and include a timestamp comment line. That is why the program checks values after reloading rather than printing the entire stored output as fixed stdout.

If a test needs to verify configuration, compare the data and storage policy within the right scope. If the requirement is to edit a file while preserving human-maintained layout, `Properties` does not provide a model that preserves all such textual details.

### 9.2. Whoever Opens a Resource Must Know Who Closes It

`load`(Reader) and `load(InputStream)` do not close the object passed to them. `store` likewise does not close the `Writer`/`OutputStream`.

Use try-with-resources at the resource owner when reading/writing real files. The streams in the example are in-memory; they keep the focus on checking data without creating external files.

`loadFromXML` is a separate API with its own rules, where the method closes the input stream passed to it. Do not infer a universal closing rule simply because all these methods belong to `Properties`.

### 9.3. XML Does Not Use the Same Read Path as the Line-Based Format

`Properties` provides `loadFromXML`/`storeToXML` for reading and writing Java's XML properties format. `storeToXML` is not just `store` with a different file extension; the default overload uses UTF-8.

If a legacy system uses XML, keep the corresponding API pair and encoding contract. Do not load XML with regular `load` expecting an XML parser to kick in.

### 9.4. `save` Is a Specific Deprecated API

`Properties.save` is an old method that can swallow `IOException`; `store` is the documented preferred path when write errors need to be surfaced.

What needs fixing in legacy code may be choosing the error-reporting API, rather than replacing `Properties` with a `HashMap` and losing formatting, `defaults`, and I/O support.

## 10. Migrating Gradually to Modern Code While Preserving Semantics

### 10.1. Separate Compatibility Boundaries from Internal Usage Models

If a legacy library requires a `Dictionary`, you may need to keep passing a suitable object at that boundary. Inside new application code, declare against `Map` when that is the contract actually needed.

Do not force an arbitrary `Map` into a `Dictionary` just to satisfy the compiler. Do not treat a copy as a live link, or a live link as an isolated copy.

If you change a public API signature, you must review callers and existing compatibility requirements. A data structure change can affect more than a few initialization lines.

### 10.2. Choose Structures by Requirements, Not by Class Name Age

| Need | Direction to Evaluate |
| --- | --- |
| Ordinary mapping without concurrent writes | An appropriate Map, typically starting with HashMap |
| Mapping updated by multiple threads | Synchronization mechanism or ConcurrentMap suited to each operation |
| A multi-step or multi-key update sequence | Business invariants and protection scope covering the whole sequence |
| Interfacing with an API requiring Dictionary | Adapter boundary with a clear contract |
| Loading/saving standard Java string configuration | Properties still has a specific role |
| Reading configuration into business logic | Parse, validate, then convert into a typed model |

Do not replace `Hashtable` with `HashMap` if the code relies on synchronization without redesigning access sites.

Conversely, do not keep `Hashtable` merely because it is "already thread-safe" when the application needs concurrent updates under different contention characteristics. Read the contract and measure actual load if performance is a requirement.

### 10.3. For Configuration, Validate Values Before Use

`getProperty` returns a `String`; it does not verify that the string is a number, within an allowed range, or a valid option.

A fallback value only handles the case where no matching property is found; it does not turn an invalid string like a non-numeric port name into a valid value.

Check for required values, empty values, whitespace, parse errors, and allowed ranges at the configuration-loading boundary. Then pass the appropriate typed data into the business logic.

Do not arbitrarily call `toString` on every mistyped `Object` to "fix" `Properties`. Doing so can hide the source of bad data and undermine configuration validation.

### 10.4. Properties Has Its Own Concurrency and Iterator Contract

The Java 17 API describes `Properties` as thread-safe. That does not mean multiple reads of related keys are always a snapshot of the same version, or that the entire `defaults` chain is locked as a transaction.

In particular, the `Properties` documentation describes collection-view iterators differently from `Hashtable`: do not mechanically conclude that every `Properties` iterator must throw `ConcurrentModificationException` upon modification.

The need for a consistent configuration to execute a business request should be solved with an appropriate load, validation, and publication workflow.

API inheritance does not guarantee that every storage layout detail, performance parameter, or traversal behavior matches the superclass.

## 11. Common Mistakes and How to Re-Read Requirements

| Assumption or Fix | What Was Missed |
| --- | --- |
| Dictionary is a legacy Map interface | It is an abstract class and does not declare Map |
| Changing a variable's type from Hashtable to Map changes the implementation | The underlying object and its policies remain |
| new HashMap is a view of the old table | It is a new table containing a copy of the mappings |
| Hashtable.contains searches for a key | This legacy method searches for a value |
| Hashtable is synchronized so get then put is an atomic increment | Two calls can be interleaved |
| Enumeration does not throw so it is safe during table modification | Not fail-fast does not create a snapshot contract or concurrency safety |
| Properties is a fully type-safe Map<String,String> | It inherits an Object–Object API and can receive mistyped entries |
| `getProperty` is always equivalent to get plus a String cast | There are also defaults and non-String value handling |
| `containsKey`/size include defaults | They reflect only direct mappings |
| `store` automatically writes defaults too | You must explicitly flatten if you want to save effective configuration |
| `load`(InputStream) automatically uses current UTF-8 | This overload has its own ISO-8859-1 rule |
| Quotes in properties work like JSON | They can be literal characters of the value itself |
| A second `load` completely replaces the first | Keys not read again can remain intact |
| `load`/store preserves a human-formatted file | It is a property data model, not a text-preserving editor |
| Legacy means all APIs are @Deprecated | You must check each class and method specifically |

## 12. Self-Check Exercises

### Exercise 1. Does Type Compatibility Create a Copy?

A `Hashtable` is assigned to both a `Dictionary` variable and a `Map` variable. Is a `put` through one variable visible through the other?

**Answer hint:** Yes, if they point to the same object. Assigning a reference does not create a new table.

### Exercise 2. What Does `contains` Search For?

A `Hashtable` has `"name"` → `"Lan"`. Does `contains`("name") mean the same thing as `containsKey`("name")?

**Answer hint:** No. `contains` searches values; `containsKey` searches keys. With this data, `contains("name")` is `false` while `containsKey("name")` is `true`.

### Exercise 3. Where Is the Bug When Two Increments Result in One?

Two threads both `get` `0` and then each `put` `1` into a `Hashtable`. Why does per-method synchronization not prevent the final result from being `1`?

**Answer hint:** The read–increment–write intent spans multiple calls. You must protect the entire sequence or use an appropriate update operation provided by the implementation.

### Exercise 4. Are Defaults Counted in `size`?

A new `Properties` only has `defaults` containing three names, with no direct `setProperty` calls yet. Must `size` and the count of `stringPropertyNames` be equal?

**Answer hint:** No. `size` reflects only direct mappings; the set of string names includes `defaults`.

### Exercise 5. Does Removing an Override Delete the Configuration?

`defaults` has `mode=safe`, and the current layer has `mode=fast`. What does `getProperty("mode")` return after `remove`("mode") on the current layer?

**Answer hint:** The string `safe`, because the override is gone and the fallback value is found again.

### Exercise 6. Is an `Integer` in `Properties` Safe?

`put`("port", 8080) compiles. Should you conclude that all `Properties` read/store APIs will accept that data?

**Answer hint:** No. Properties expect `String` names and values; `getProperty` does not convert `Object` to `String`, and `store` can reject mistyped entries.

### Exercise 7. Which Path Should a Vietnamese UTF-8 File Take?

The actual byte data is UTF-8. Does `load`(InputStream) automatically use UTF-8?

**Answer hint:** No. Create a `Reader` with UTF-8 explicitly and use `load(Reader)`, or use the byte/escape format of the byte API if that is the file contract.

### Exercise 8. Does Loading Twice Keep Old Keys?

The first load reads `a=1` and `b=2`. The second load reads only `a=9` into the same object. Does `b` disappear automatically?

**Answer hint:** No. `a` is overwritten; `b` remains unless there is a removal operation or another full-replacement policy.

### Exercise 9. Does Storing and Reloading Preserve Defaults?

An object has only local overrides, while `host` lives in `defaults`. Does `store` followed by `load` into a new `Properties` without `defaults` restore `host`?

**Answer hint:** No. If you want a complete file, you must explicitly build data containing the effective values to store.

### Exercise 10. Is Swapping `Hashtable` for `ConcurrentHashMap` Enough?

The code still performs `get` followed by `put` to increment a counter. Does simply changing the instantiated class guarantee no lost updates?

**Answer hint:** No. You must choose the right atomic operation or a protection model suitable for the entire update intent.

## 13. References

- [Dictionary — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Dictionary.html): legacy abstract class and guidance to use `Map` for new implementations.
- [Hashtable — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Hashtable.html): null policy, synchronization, `contains`, and traversal contracts.
- [Enumeration — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Enumeration.html): `hasMoreElements`, `nextElement`, and `asIterator`.
- [Properties — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html): string API, `defaults`, line format, encoding, I/O, and iterators.
- [ConcurrentHashMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): concurrent update operations and limits of atomicity conclusions.
- [Files — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): creating `Reader`/`Writer` with a `Charset`.
- [Hashtable.java — OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Hashtable.java): cross-reference for synchronized methods in the cited implementation.
- [Properties.java — OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Properties.java): cross-reference for `getProperty` path and string data. Implementation details must be tied to the version and do not replace the API contract.
