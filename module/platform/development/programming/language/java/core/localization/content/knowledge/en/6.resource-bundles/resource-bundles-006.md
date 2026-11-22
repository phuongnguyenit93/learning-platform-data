# ResourceBundle: `containsKey()`, `keySet()`, and Accessing Parent Resources

When a Java application has multiple translations, each language/region typically declares only the messages that need to change. For example, the `vi-VN` resource set has its own greeting, `vi` has general translations, and the root set holds untranslated strings. `ResourceBundle` enables looking up values along a **parent resource chain (parent chain)**, allowing a key missing at a specific level to still resolve from a more general level.

This lesson accurately answers three questions:

1. Does `containsKey(key)` check keys **of the current bundle only or also parent bundles**?
2. Which set of keys does `keySet()` return, and how does it differ from `handleKeySet()`?
3. How do `getString()/getObject()` traverse the parent chain when a key is missing or overridden?

The key answer: **`containsKey` and `keySet` both include keys inherited from parents**, while value lookup prioritizes the most specific bundle before checking parents. Thus, a key appearing in `keySet()` does not prove that the key is defined directly in the specific translation file being inspected.

## 1. The Parent Bundle Model in Java

A *bundle family* consists of resources sharing a *base name*, such as `messages`:

~~~text
messages_vi_VN.properties      (most specific: Vietnamese in Vietnam)
          ↓ parent
messages_vi.properties         (general Vietnamese)
          ↓ parent
messages.properties            (root, no locale attached)
~~~

When `vi-VN` is requested, the standard loading mechanism can link the specific bundle to existing less-specific bundles. If `messages_vi_VN.properties` does not contain `logout`, Java checks `messages_vi.properties`, then `messages.properties`. A key declared in a child **overrides/shadows** the same key's value in a parent, while keys present only in parents remain accessible.

Illustrative data:

| Key | `messages.properties` | `messages_vi.properties` | `messages_vi_VN.properties` |
| --- | --- | --- | --- |
| `app.name` | Sample App | — | — |
| `greeting` | Hello | Xin chào | Chào bạn |
| `logout` | Sign out | — | — |
| `thanks` | — | Cảm ơn | — |
| `region` | — | — | Việt Nam |

The dash "—" means **not declared in that bundle**, not an empty string. When reading from the `vi-VN` bundle, the effective results are:

| Key | Returned Value | Actual Source |
| --- | --- | --- |
| `app.name` | Sample App | Root bundle |
| `greeting` | Chào bạn | `vi-VN` bundle override |
| `logout` | Sign out | Root bundle |
| `thanks` | Cảm ơn | `vi` bundle |
| `region` | Việt Nam | `vi-VN` bundle |

This table shows **per-key fallback on an already-established parent chain**, which differs from bundle-selection fallback when `ResourceBundle.getBundle(...)` cannot find a candidate for the requested locale. Do not conflate the two processes.

### How Is the Parent Linked?

`ResourceBundle.getBundle(baseName, locale)` automatically resolves the matching bundle and links parent bundles according to the lookup mechanism. Custom subclasses of `ResourceBundle` also have a `protected` `setParent(parent)` method to set the parent. In most applications using `.properties` files, you **do not call `setParent` yourself**: the loader does it.

The parent chain is a **relationship between `ResourceBundle` object instances**, not a Java class inheritance hierarchy. A bundle can inherit values even if its concrete class does not `extend` the parent bundle's class.

## 2. `containsKey(String key)`: Local or Inherited Keys

Method contract:

~~~java
boolean exists = bundle.containsKey("logout");
~~~

`containsKey` returns `true` when the key resides in the current bundle **or any parent bundle**; `false` if it does not exist anywhere in the chain. With the model above, called on the `vi-VN` bundle:

~~~java
bundle.containsKey("greeting"); // true: present directly in vi-VN
bundle.containsKey("thanks");   // true: inherited from vi
bundle.containsKey("logout");   // true: inherited from root
bundle.containsKey("unknown");  // false: absent everywhere
~~~

This is an illustrative snippet, where `bundle` is a `ResourceBundle` already loaded and parent-linked as in the example.

**Common pitfall:** `containsKey("logout") == true` does **not** mean a Vietnamese translation exists. It only states that a key lookup will find an effective resource along the parent chain.

A few notes:

- Keys are `String` values and are case-sensitive: `"logout"` differs from `"Logout"`.
- Passing `null` to `containsKey` throws `NullPointerException`; validate input first if keys are user-supplied.
- `containsKey` is a **presence check**; it does not verify value type, translation quality, language correctness, or whether the string is non-empty.
- In standard bundles, defined resources should not have `null` values; in `ResourceBundle`, `handleGetObject(key)` returns `null` to indicate that a key was **not found in the current bundle**, allowing parent lookup to proceed.

If calling `containsKey` before `getString`, understand that they are two separate queries. For resources immutable after load, this pattern is reasonable; when building custom dynamic bundles, ensure thread safety and clearly defined update semantics. Do not use `containsKey` to detect whether a specific translation file has finished translating a key.

## 3. `keySet()`: Effective Keys Across the Whole Parent Chain

`bundle.keySet()` returns a `Set<String>` containing **all keys from the bundle and its parents**, deduplicated by key name. A key defined at multiple levels still appears **once** in the set because a `Set` holds no duplicates.

With the data from section 1:

~~~java
Set<String> keys = bundle.keySet();
// As a set: app.name, greeting, logout, thanks, region
~~~

Do not assume an iteration order from `keySet()`: `Set` makes no stable ordering guarantee. If you need reproducible output in logs, tests, or QA tools, copy into a `TreeSet`:

~~~java
Set<String> sorted = new TreeSet<>(bundle.keySet());
System.out.println(sorted);
// [app.name, greeting, logout, region, thanks]
~~~

Both snippets above are illustrative; they require importing `java.util.Set` and `java.util.TreeSet` alongside an existing `bundle` variable.

**`keySet` contains no information about "where this key came from."** The set `["greeting", "logout"]` does not reveal whether `greeting` lives in `vi-VN` or `logout` comes from the root bundle. To audit missing translations, you need a local key source at each level or must read the corresponding resource file directly.

### Comparing `keySet()`, `getKeys()`, and `handleKeySet()`

| API | Scope | Visibility | Result |
| --- | --- | --- | --- |
| `keySet()` | Current bundle **and parents** | `public` | `Set<String>` |
| `getKeys()` | Current bundle **and parents** | `public` | `Enumeration<String>` |
| `handleKeySet()` | **Only keys of the current bundle** | `protected` | `Set<String>` |

`handleKeySet()` is designed primarily for implementing `ResourceBundle` subclasses, **not as a public API for arbitrary external services to call directly**. By default, Java determines local keys from keys yielding non-null values from `handleGetObject`; subclasses like `ListResourceBundle` can provide a more efficient implementation.

Inside a subclass, you can expose a package/helper method for testing tools:

~~~java
class InspectableBundle extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"message", "Hello"}
        };
    }

    Set<String> localKeys() {
        return handleKeySet(); // Only keys of this instance
    }
}
~~~

This is only a standalone class example when placed in a Java file importing `java.util.ListResourceBundle` and `java.util.Set`. It has no parent chain on its own. For a `PropertyResourceBundle` returned by `getBundle`, you cannot call `bundle.handleKeySet()` from a normal service because of `protected` visibility.

Do not attempt to deduce local keys via `keySet(child) - keySet(parent)`: any key overridden by the child also exists in the parent and gets removed by set subtraction, even though the **child actually defines that key**.

## 4. Accessing a Key Along the Parent Chain

When calling:

~~~java
String text = bundle.getString("logout");
~~~

`ResourceBundle.getString()` invokes resource retrieval and checks the current instance first. If the resource is absent in the child, it checks the parent, then the grandparent, until a value is found or the chain ends. For non-string values there is `getObject(key)`; for string arrays there is `getStringArray(key)`.

General rule:

~~~text
getString("greeting")
   vi-VN: present -> return "Chào bạn"             (stop)

getString("thanks")
   vi-VN: absent
       vi: present -> return "Cảm ơn"              (stop)

getString("logout")
   vi-VN: absent
       vi: absent
           root: present -> return "Sign out"      (stop)

getString("unknown")
   vi-VN: absent
       vi: absent
           root: absent -> MissingResourceException
~~~

If the key is not found anywhere in the parent chain, `getString`/`getObject` throws `MissingResourceException` — **never returning an empty string or `null` to signal a missing key**. Reading with the wrong type (e.g., calling `getString` when the value is `String[]`) can throw `ClassCastException`.

Once a key is found in the child, the parent's value with the same name **is no longer used**. Override rules are based on **key name**, without partial merging of complex values or blending two strings together. If a child message lacks a placeholder or has broken grammar, Java cannot automatically patch it with the parent's translation.

### What If the Child Declares an Empty String?

For example:

~~~properties
# messages_vi_VN.properties
logout=
~~~

`logout` in the child bundle **does exist** with an empty string value. Therefore:

- `containsKey("logout")` is `true`.
- `getString("logout")` returns `""`.
- Java **does not** skip the empty string to fetch `logout=Sign out` from the parent.

To treat empty strings as "untranslated," you must add resource-validation rules or custom application logic; the safer approach is catching them during build/QA rather than silently altering the meaning of a valid value.

## 5. Single-File Java 17+ Example Illustrating Parents and Local Keys

To observe `handleKeySet()` (which is `protected`) without creating multiple files, this example constructs `ListResourceBundle` instances directly and links parents with `setParent`. This is a **teaching model demonstrating `ResourceBundle`'s lookup mechanics**, not how `.properties` bundles are loaded in real applications.

Create **`ParentKeysDemo.java`**:

~~~java
import java.util.ListResourceBundle;
import java.util.MissingResourceException;
import java.util.ResourceBundle;
import java.util.Set;
import java.util.TreeSet;

public class ParentKeysDemo {

    static final class Messages extends ListResourceBundle {
        private final Object[][] entries;

        Messages(ResourceBundle parent, Object[][] entries) {
            this.entries = entries;
            if (parent != null) {
                setParent(parent);
            }
        }

        @Override
        protected Object[][] getContents() {
            return entries;
        }

        // Used only within the subclass to observe local keys.
        Set<String> localKeys() {
            return handleKeySet();
        }
    }

    public static void main(String[] args) {
        Messages root = new Messages(null, new Object[][] {
                {"app.name", "Sample App"},
                {"greeting", "Hello"},
                {"logout", "Sign out"}
        });

        Messages vi = new Messages(root, new Object[][] {
                {"greeting", "Xin chao"},
                {"thanks", "Thanks"}
        });

        Messages viVN = new Messages(vi, new Object[][] {
                {"greeting", "Chao ban"},
                {"region", "Vietnam"}
        });

        System.out.println("Local: "
                + new TreeSet<>(viVN.localKeys()));
        System.out.println("Visible: "
                + new TreeSet<>(viVN.keySet()));

        System.out.println("Inherited key: "
                + viVN.containsKey("logout"));
        System.out.println("Absent key: "
                + viVN.containsKey("missing"));

        System.out.println("Greeting: "
                + viVN.getString("greeting"));
        System.out.println("Thanks: "
                + viVN.getString("thanks"));
        System.out.println("Logout: "
                + viVN.getString("logout"));
        System.out.println("App: "
                + viVN.getString("app.name"));

        try {
            viVN.getString("missing");
        } catch (MissingResourceException ex) {
            System.out.println("Missing: " + ex.getKey());
        }
    }
}
~~~

Compile and run with Java 17 or higher:

~~~bash
javac -encoding UTF-8 ParentKeysDemo.java
java ParentKeysDemo
~~~

**Stdout** (verified against runtime behavior):

~~~text
Local: [greeting, region]
Visible: [app.name, greeting, logout, region, thanks]
Inherited key: true
Absent key: false
Greeting: Chao ban
Thanks: Thanks
Logout: Sign out
App: Sample App
Missing: missing
~~~

Detailed explanation:

1. `root` defines three keys: `app.name`, `greeting`, `logout`. `vi` declares `greeting` and `thanks`, while `viVN` declares `greeting` and `region`.
2. `viVN.localKeys()` calls `handleKeySet()` in the subclass, so it contains only `greeting` and `region`.
3. `viVN.keySet()` is the union across **all three layers**: five distinct keys. Key `greeting` appears only once even though all three layers declare it.
4. `containsKey("logout")` is still `true` because `logout` exists in `root`, even though not in `viVN`.
5. `getString("greeting")` prioritizes `Chao ban` from `viVN`, rather than `Xin chao` from `vi` or `Hello` from `root`.
6. `getString("thanks")` comes from `vi`; `getString("logout")` and `getString("app.name")` come from `root`.
7. `getString("missing")` throws `MissingResourceException`, which the program catches and prints `getKey()`.

The program uses ASCII values so stdout does not depend on console configuration. In real translations, values can certainly be Unicode Vietnamese; key inheritance behaves identically.

**Example note:** `setParent` is called **once during object construction**. In real applications, do not arbitrarily change the parent of a bundle actively shared across threads. With normal `ResourceBundle.getBundle`, the API manages loading and parent linking automatically.

## 6. Practical Usage with `.properties` Files

Suppose the classpath directory contains these exact three files, saved in UTF-8 encoding:

**`messages.properties`**

~~~properties
app.name=Sample App
greeting=Hello
logout=Sign out
~~~

**`messages_vi.properties`**

~~~properties
greeting=Xin chào
thanks=Cảm ơn
~~~

**`messages_vi_VN.properties`**

~~~properties
greeting=Chào bạn
region=Việt Nam
~~~

Save them in the same classpath location (such as `src/main/resources/` in standard Gradle/Maven projects). Specify `baseName` as `messages` and request `vi-VN`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

ResourceBundle bundle = ResourceBundle.getBundle(
        "messages",
        Locale.forLanguageTag("vi-VN"),
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES)
);

System.out.println(bundle.getString("greeting")); // Chào bạn
System.out.println(bundle.getString("logout"));   // Sign out
System.out.println(bundle.containsKey("logout")); // true
~~~

**This is an illustrative snippet** placed inside a method of a classpath or unnamed-module program that imports both classes. `getNoFallbackControl(FORMAT_PROPERTIES)` is used here to **disable fallback to the JVM's default locale during bundle resolution** and search only properties files. It **does not disable accessing parent bundles by locale**: the `vi-VN → vi → root` chain still works with the provided files.

The `ResourceBundle.Control` mechanism belongs to bundle loading models supporting the `Control` parameter (typically classpath/unnamed modules). Overloads taking `Control` **are not supported this way in named modules**; for named modules, use the resource bundle/module/provider mechanism per Java documentation. Do not apply this snippet mechanically to every JPMS deployment.

### Why Does the Example Include a Root Bundle?

The root bundle `messages.properties` commonly serves as the fallback message source for unlocalized keys. If a key exists at none of the layers, retrieval still fails. If no suitable bundle can be loaded at all, `ResourceBundle.getBundle(...)` can throw `MissingResourceException` at bundle lookup time; that error differs from **loading a bundle successfully yet missing a key**.

With `PropertyResourceBundle` on Java 17, properties files loaded along standard paths are read as UTF-8, with backward-compatible ISO-8859-1 fallback on invalid byte sequences depending on system property settings. Save files consistently as UTF-8, verify build/resource copy paths, and test accented characters.

## 7. Two Kinds of Fallback That Are Easily Confused

`ResourceBundle` has at least two stages to distinguish:

### A. Selecting a Bundle When Loading with `getBundle()`

For instance, `vi-VN` is requested, but `messages_vi_VN.properties` does not exist. Java locates a suitable bundle from less specific candidate names and may use `messages_vi.properties` or `messages.properties`.

With default `ResourceBundle.getBundle(baseName, locale)`, the process may also evaluate the **JVM's default locale** under loading rules depending on available files. If exact product-defined fallback behavior is required, configure an appropriate bundle lookup strategy rather than assuming all applications always jump straight to root or always switch to the server's language.

### B. Looking Up a Key Once a Bundle and Parent Chain Exist

After the bundle is loaded, `getString("logout")` searches from the specific bundle through its parents along the established chain. `containsKey` and `keySet` reflect **effective keys in that chain**. Their outputs do not report which candidate locales Java tried before choosing the bundle.

Two different questions:

- "Which bundle was loaded for a `fr-CA` request?" — check `getBundle` policy, `bundle.getLocale()`, and available resources.
- "Can the selected bundle read key `logout`?" — use `containsKey`, `keySet`, and `getString`, which consider parents.

`bundle.getLocale()` reveals the locale of the **returned bundle**, not which layer in the parent chain holds a **specific key**.

## 8. Checking Translation Coverage: Do Not Use `keySet()` Naively

Suppose the `vi-VN` translation lacks `logout` while root has `logout=Sign out`. Code like:

~~~java
if (bundle.containsKey("logout")) {
    System.out.println("Translated");
}
~~~

prints `Translated`, even though it is actually pulling English from the root. This is the mistake of equating **"readable"** with **"translated in this locale."**

To build a translation QA tool:

1. Define the **required key set** from a schema, root bundle, or canonical catalog.
2. Read the **keys actually defined in each locale file**, rather than calling `keySet()` on a parent-linked bundle.
3. Compare local keys against required keys to find untranslated keys, extra keys, and typos.
4. Validate contents: non-empty when required, matching `{0}` parameters, valid `MessageFormat` syntax, proper language, and no placeholder/temp strings.
5. Test runtime access with `ResourceBundle.getBundle` to verify actual fallback behavior works properly.

For `.properties` files, a build tool can parse each file directly to extract local keys. For custom subclasses, you can expose a QA-specific local inspection method or inspect the subclass source data. Do not use reflection to read the `parent` field or JDK `handleKeySet` just to bypass `protected`; that runs into module encapsulation and produces brittle code.

If your goal is simply **listing values that can be retrieved**, `keySet()` is the right API. If your goal is **measuring translation completeness**, you must inspect per-locale sources.

## 9. Handling Missing Keys in Applications

There are two common approaches, depending on how critical the content is.

### Optional Keys

For optional tooltips or labels, you can choose an application-defined fallback:

~~~java
String caption = bundle.containsKey("optional.caption")
        ? bundle.getString("optional.caption")
        : "Optional information";
~~~

This is an illustrative snippet with an existing `ResourceBundle bundle` variable. Note that `containsKey` still includes parents: if a parent contains the key, the parent's value is returned rather than the manual fallback string.

If the application needs to know whether **the selected bundle itself declares the key directly**, the snippet above cannot answer that; you must inspect local data as analyzed earlier.

### Required Keys

For indispensable titles, checkout buttons, or legal text, let `getString` throw `MissingResourceException` and handle it at an appropriate boundary; better yet, catch missing keys at build/test time. Silently rendering the raw key name (`"payment.submit"`) in the UI can help debugging but is usually inappropriate in a finished product.

**Do not call `getString(key)` unless you know the resource is a `String`.** A `ResourceBundle` can contain `Object` or `String[]` values, whereas `PropertyResourceBundle` normally manages strings. Code mixing bundle types must enforce a clear type schema.

## 10. Technical Details to Keep in Mind

### Key Ordering and Performance

`keySet()` returns a `Set` with no guaranteed order. Do not write tests comparing `Set.toString()` directly if you expect deterministic ordering. Use `new TreeSet<>(bundle.keySet())` or `new ArrayList<>(...)` and sort.

During normal UI rendering, you usually **already know the keys you need** and do not iterate all keys to inspect each one. For QA tools or debug screens, iterating `keySet` is reasonable; if repeated across many requests, cache the prepared structure instead of rebuilding and sorting lists continually.

### Keys Are Locale-Invariant, Values Are Locale-Specific

Keys are typically stable technical identifiers like `login.button`, `payment.total`, or `error.invalidEmail`. **Keys are case-sensitive**, while values vary by locale. Renaming a key in just one locale file lets the parent hide the missing-key bug behind a default value.

### Bundle Caching and Runtime Updates

`ResourceBundle.getBundle` caches bundles. Editing a properties file while the application is running does not mean the next call immediately reads the new contents. If dynamic resource updates are needed, design a proper reload and invalidation strategy; `ResourceBundle.clearCache()` and `ResourceBundle.Control` play roles in environments that support them.

### Do Not Mutate Parent Links Outside Setup

A subclass can call `setParent`, yet you should never reassign a parent between requests or share a structure being mutated across threads. Use bundle chains constructed stably and tested after initialization. For custom subclasses, `ResourceBundle`'s contract requires thread-safe implementations when accessed concurrently.

### Parent Bundles and Business Domains

You can use multiple distinct families such as `validation`, `messages`, and `errors`. A parent bundle does **not** automatically span every `.properties` file in the application: parent relationships exist only within the **same established bundle chain**. If key `notFound` lives in family `errors` while you are querying `messages`, `containsKey` will not search across families.

## 11. Practice Exercises

**Exercise 1.** With the three bundles in section 1, predict the outputs of these expressions before running:

~~~java
bundle.containsKey("logout");
bundle.containsKey("region");
bundle.containsKey("unknown");
bundle.getString("greeting");
bundle.getString("thanks");
~~~

**Answer:** `true`, `true`, `false`, `"Chào bạn"`, `"Cảm ơn"`. Both of the first two return `true`, though `logout` comes from root while `region` is in bundle `vi-VN`.

**Exercise 2.** Why is `bundle.keySet().contains("app.name")` still `true` even though `messages_vi_VN.properties` does not declare `app.name`?

**Answer:** `keySet()` returns the union of keys from the current bundle and its parents. `app.name` is inherited from root.

**Exercise 3.** If both root and `vi-VN` define `greeting`, how many times does that key appear in `keySet()`? When `getString("greeting")` is called, which value does Java choose?

**Answer:** Only once in the `Set`. Java chooses the value from the nearest bundle (`vi-VN`) and does not continue to root.

**Exercise 4.** If `messages_vi_VN.properties` contains `logout=`, will `getString("logout")` fetch `Sign out` from root?

**Answer:** No. An empty string is a defined value in the child, so it shadows the parent's value.

**Exercise 5.** A QA tool reports that every key in `bundle.keySet()` exists and concludes the `vi-VN` translation is complete. Where is the flaw in that conclusion?

**Answer:** `keySet()` includes inherited keys; you must compare keys declared **directly inside the `vi-VN` translation file** against the required key list and check value quality.

**Extension exercise.** Add the `logout` key to the `vi` bundle in the single-file program; predict that `viVN.containsKey("logout")` stays unchanged and `viVN.keySet()` stays unchanged, while `viVN.getString("logout")` switches to `vi`'s value. Then remove this key from `vi` to observe fallback returning to root.

## 12. Testing Checklist and Core Principles

When writing `ResourceBundle` tests, cover:

- Keys present directly in the child bundle.
- Keys absent in the child but present in the parent or grandparent.
- Keys defined in both child and parent: child overrides the value.
- Keys absent across the entire chain: `containsKey == false`, `getString` throws `MissingResourceException`.
- Keys with an empty value in the child: must not fall through to parent unless the application defines special logic.
- `keySet()` merges keys and deduplicates names; do not rely on iteration order.
- Keys present only in a parent remain visible through `containsKey` and `keySet`.
- Key syntax, resource types, encoding, `ResourceBundle` caching, and bundle loading rules in the target runtime environment.
- Translation coverage evaluated per locale source, not from `keySet()` of a parent-linked bundle.

**Remember:** `containsKey()` answers "can the key be found through current + parent chain?", `keySet()` answers "what is the set of all reachable keys?", and `handleKeySet()` answers "which keys does the current bundle alone define?" (`protected` access in subclasses only). `getString()/getObject()` prioritize child values before checking parents; absence across the entire chain throws `MissingResourceException`.

### Official API Documentation

- [ResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): `containsKey`, `keySet`, `handleKeySet`, `getObject`, parent chain, and bundle loading mechanics.
- [ListResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListResourceBundle.html): declaring resources in Java code.
- [PropertyResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html): `.properties` files, encoding, and file-backed bundle implementation.
