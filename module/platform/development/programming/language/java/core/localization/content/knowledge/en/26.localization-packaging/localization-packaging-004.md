# ResourceBundle.Control: Candidates, Formats, and Time-to-Live in Java

## 1. What Does ResourceBundle.Control Control?

In Java, `ResourceBundle` selects translations and resources based on `Locale`. If an application has files such as:

~~~text
Messages.properties
Messages_fr.properties
Messages_fr_CA.properties
~~~

then `ResourceBundle.getBundle("Messages", Locale.CANADA_FRENCH)` can locate resources for Canadian French and inherit keys from more general resources.

`java.util.ResourceBundle.Control` is the nested class `ResourceBundle.Control`, which lets you customize the **lookup**, **format selection**, **loading**, **fallback**, and **caching** policies of a bundle when calling the `ResourceBundle.getBundle` overload that accepts a `Control`.

Key questions:

1. **Candidates (candidate locales):** in what order are `fr_CA`, `fr`, and root searched?
2. **Formats:** try `.class`-based bundles first or `.properties` files first; should `.xml` sources be allowed?
3. **Time-to-Live (TTL):** when must a cached bundle be revalidated? Does TTL expiration imply reloading?
4. **Fallback:** if no candidate is found for the requested locale, should the JVM default locale be tried?
5. **Reloading:** what determines that the source changed and a new instance is needed?

**Important limitation upfront:** `ResourceBundle.Control` is designed for applications running on the **classpath / unnamed module**. When code calls a `ResourceBundle.getBundle(..., Control)` overload **from a named module**, Java 9+ throws `UnsupportedOperationException`. For Java Modules (JPMS) applications, look at `java.util.spi.ResourceBundleProvider` and the provider mechanism instead of building new solutions on `Control`.

Most examples in this article target **Java 17+ running on the classpath**, without `module-info.java`. This is a prerequisite to properly understand the behavior and run the demonstration programs.

## 2. ResourceBundle.Control API Map

| Method/Constant | Role | Key points to remember |
| --- | --- | --- |
| `getCandidateLocales(baseName, locale)` | Generates the priority list of candidate locales | Earlier entries are more specific; usually ends with `Locale.ROOT` |
| `getFormats(baseName)` | Returns the ordered list of allowed bundle formats | Defaults to class first, properties second |
| `getFallbackLocale(baseName, locale)` | Picks another locale to try if no match is found | Default may use the JVM default locale |
| `newBundle(baseName, locale, format, loader, reload)` | Instantiates a specific bundle from class/file or custom source | `reload` indicates the reload path |
| `getTimeToLive(baseName, locale)` | Determines cache TTL in millis or sentinel constants | Expiration typically triggers `needsReload` |
| `needsReload(..., bundle, loadTime)` | Determines whether an expired bundle truly needs reloading | Default checks source modification timestamp when possible |
| `toBundleName(baseName, locale)` | Converts base name + locale into a bundle name | E.g., `Messages_fr_CA` |
| `toResourceName(bundleName, suffix)` | Converts a bundle name into a resource path | E.g., `com/example/Messages_fr.properties` |
| `FORMAT_DEFAULT` | `["java.class","java.properties"]` | Class -> properties order |
| `FORMAT_CLASS` | Only `["java.class"]` | Ignores properties files |
| `FORMAT_PROPERTIES` | Only `["java.properties"]` | Ignores class bundles |
| `TTL_DONT_CACHE` | Do not store the bundle in the cache | Not equivalent to TTL equal to 0 |
| `TTL_NO_EXPIRATION_CONTROL` | Cache without expiration control | Default return value of `getTimeToLive` |

A `Control` object collaborates with `ResourceBundle.getBundle`; it is not "a bundle holding key/value pairs." `Control` primarily governs **how a bundle is found and how long it lives**, while actual translations live inside `PropertyResourceBundle`, `ListResourceBundle`, or a custom bundle.

## 3. getCandidateLocales: Order from Specific to General

For locale `fr-CA`, the default candidate list is typically:

~~~text
fr-CA -> fr -> ROOT
~~~

With base name `Messages`, the derived resource names are:

~~~text
Messages_fr_CA.properties
Messages_fr.properties
Messages.properties
~~~

**Candidate order is not the order in which keys are read:** the loader first identifies which bundles exist and constructs the appropriate parent chain. When `getString(key)` is called, if the key is missing from a specific bundle, it can be resolved from a parent.

### Example 1 — Printing Candidate Locales and Formats

Create `CandidatePolicyDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.stream.Collectors;

public class CandidatePolicyDemo {
    static String describe(List<Locale> locales) {
        return locales.stream()
                .map(locale -> locale.equals(Locale.ROOT)
                        ? "ROOT" : locale.toLanguageTag())
                .collect(Collectors.joining(" -> "));
    }

    public static void main(String[] args) {
        ResourceBundle.Control control =
                ResourceBundle.Control.getControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        Locale frenchCanada = Locale.forLanguageTag("fr-CA");
        Locale serbianLatin =
                Locale.forLanguageTag("sr-Latn-RS");

        System.out.println("Formats: "
                + control.getFormats("Messages"));
        System.out.println("fr-CA: " + describe(
                control.getCandidateLocales(
                        "Messages", frenchCanada)));
        System.out.println("sr-Latn-RS: " + describe(
                control.getCandidateLocales(
                        "Messages", serbianLatin)));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CandidatePolicyDemo.java
java CandidatePolicyDemo
~~~

Verified output on a modern JDK:

~~~text
Formats: [java.properties]
fr-CA: fr-CA -> fr -> ROOT
sr-Latn-RS: sr-Latn-RS -> sr-Latn -> sr-RS -> sr -> ROOT
~~~

### Reading the Output

- `fr-CA`: tries the Canada region first, then general French, and finally the root bundle.
- `sr-Latn-RS`: the locale has the **Latin script** and Serbia region, so Java has additional steps. This is why you should not hand-roll an algorithm by naively stripping trailing parts of a BCP 47 tag.
- `Locale.ROOT` represents the unsuffixed bundle: `Messages.properties`.
- There are special cases in the Javadoc such as Chinese (`zh` with `Hans`/`Hant` script derived from region) and legacy language codes. **Do not assume every candidate chain always consists only of language-country-root**.

In this program, `getControl(FORMAT_PROPERTIES)` only selects the **properties format**; it does not alter the default candidate locale generation rules.

## 4. Candidate Chain vs. Fallback Locale

Two concepts that are easily confused:

A **Candidate chain** is the sequence of variants derived from the requested locale, for example:

~~~text
Request: fr-CA
Candidates: fr-CA -> fr -> ROOT
~~~

A **Fallback locale** is **another requested locale** that `getBundle` may use to continue searching when the associated candidates fail to yield a result bundle under the lookup conditions; the default implementation usually tries the JVM's default locale if it differs from the locale just searched.

Example assuming the JVM default locale is `en-US`:

~~~text
Request: ja-JP
  candidates: ja-JP -> ja -> ROOT
If no suitable translation is found along the requested branch,
  fallback locale en-US may be tried
  then candidates: en-US -> en -> ROOT
Finally, root may be used if available
~~~

**Note on the exact algorithm:** the root bundle plays a special role during result selection; do not interpret the diagram above as a simple loop that "always returns root at the third step and never tries the default locale." The `ResourceBundle.getBundle` Javadoc specifies the exact search and root/default selection algorithm. The diagram is meant to distinguish the two **sources of candidates**, not to enumerate every parent-chain case.

### getNoFallbackControl Does Not Mean No Parent

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
~~~

This is a **code fragment inside a method**, requiring `import java.util.ResourceBundle`.

`getNoFallbackControl` makes `getFallbackLocale` return `null`: it does not automatically try an additional fallback locale such as the default locale. However, the **candidate list for the original locale** still includes `fr-CA`, `fr`, and `Locale.ROOT`. Therefore, the parent/root within the same candidate chain **still works**.

This is especially important when testing: "no fallback" in this API does not mean "only ever read `Messages_fr_CA.properties`." If you want to omit even the root parent, you must design a different candidate chain or key lookup policy, and understand the risk of losing general fallback resources.

## 5. Example 2 — Loading Bundles and Key Inheritance Across Candidates

Create four files in the **same classpath directory**, such as `bundle-demo`:

~~~text
bundle-demo/
  BundleLookupDemo.java
  Messages.properties
  Messages_fr.properties
  Messages_fr_CA.properties
~~~

Contents of `Messages.properties`:

~~~properties
app=Base app
origin=root
~~~

Contents of `Messages_fr.properties`:

~~~properties
greeting=Bonjour
~~~

Contents of `Messages_fr_CA.properties`:

~~~properties
region=CA
~~~

Create `BundleLookupDemo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleLookupDemo {
    public static void main(String[] args) {
        Locale requested = Locale.CANADA_FRENCH;

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle bundle = ResourceBundle.getBundle(
                "Messages", requested, control);

        System.out.println("Resolved: "
                + bundle.getLocale().toLanguageTag());
        System.out.println("Region: "
                + bundle.getString("region"));
        System.out.println("Greeting: "
                + bundle.getString("greeting"));
        System.out.println("App: " + bundle.getString("app"));
        System.out.println("Fallback locale: "
                + control.getFallbackLocale("Messages", requested));
    }
}
~~~

From the `bundle-demo` directory, compile and run on the classpath:

~~~bash
javac -encoding UTF-8 BundleLookupDemo.java
java -cp . BundleLookupDemo
~~~

Output:

~~~text
Resolved: fr-CA
Region: CA
Greeting: Bonjour
App: Base app
Fallback locale: null
~~~

### Analyzing the Parent Chain

- `region` is in `Messages_fr_CA.properties`.
- `greeting` is absent at the `fr_CA` level, so it is resolved from `Messages_fr.properties`.
- `app` is absent in both bundles above, so it is resolved from `Messages.properties`.
- `getFallbackLocale == null` does not block **key inheritance from parents** in the same candidate chain.

If `Messages_fr_CA.properties` does not exist, the lookup may select `fr` as the bundle's locale; if a key does not exist in any bundle or parent, `getString` throws `MissingResourceException`. That differs from when **no bundle at all can be found** for the base name: `getBundle` throws `MissingResourceException` during loading.

## 6. getFormats: Class, Properties, and Custom Formats

By default, `Control.FORMAT_DEFAULT` consists of:

~~~text
[java.class, java.properties]
~~~

For each candidate locale, Java may try class-based resources first, then properties. Format names `java.class` and `java.properties` are JDK-defined format identifiers, not literal file extensions in every scenario.

| Configuration | Meaning |
| --- | --- |
| `FORMAT_DEFAULT` | Try `ListResourceBundle` class first, then `.properties` |
| `FORMAT_CLASS` | Class-based bundles only |
| `FORMAT_PROPERTIES` | `.properties`-based bundles only |
| `getControl(FORMAT_PROPERTIES)` | Factory returning a built-in Control for properties-only |
| Override `getFormats` | Needed for other formats, such as `xml` |

Example:

~~~java
ResourceBundle.Control propertiesOnly =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle = ResourceBundle.getBundle(
        "Messages", Locale.FRENCH, propertiesOnly);
~~~

This is a **code fragment inside a method**, requiring imports of `ResourceBundle` and `Locale`.

### Format Order and Cache Warning

`ResourceBundle` uses a **cache**, so if the first lookup for a base name and class loader uses a control permitting only `java.class`, a subsequent call using a control permitting only `java.properties` is not guaranteed to "forget" the earlier class bundle. The Javadoc stresses that **the formats and candidate lists must stay consistent across calls for the same base bundle** to avoid unexpected results.

Values returned from `getFormats` must be non-empty, contain no unsupported formats, and **not be mutated after returning**. Custom formats must not use the `"java."` prefix, as that namespace is reserved by Java.

### Custom Formats Must Have a Matching newBundle

Simply writing:

~~~java
@Override
public List<String> getFormats(String baseName) {
    return List.of("xml");
}
~~~

is a **code fragment inside a `Control` subclass**, insufficient by itself to read XML. You must also override `newBundle` to build the resource name, decode, parse the file, and construct a `ResourceBundle`. Otherwise, the default `newBundle` implementation may throw `IllegalArgumentException` when encountering an unknown format.

## 7. Example 3 — ResourceBundle from XML via a Custom Control

`java.util.Properties.loadFromXML(InputStream)` supports the XML format for properties. This example uses it as a data source and exposes a `ResourceBundle` with `handleGetObject` and `getKeys`.

Prepare:

~~~text
xml-demo/
  XmlControlDemo.java
  Messages.xml
~~~

Contents of `Messages.xml` (UTF-8):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
<properties>
    <entry key="hello">Hello XML</entry>
</properties>
~~~

Create `XmlControlDemo.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLConnection;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.Locale;
import java.util.Properties;
import java.util.ResourceBundle;

public class XmlControlDemo {
    static class XmlControl extends ResourceBundle.Control {
        @Override
        public List<String> getFormats(String baseName) {
            return List.of("xml");
        }

        @Override
        public ResourceBundle newBundle(
                String baseName, Locale locale, String format,
                ClassLoader loader, boolean reload) throws IOException {

            if (!"xml".equals(format)) {
                return null;
            }

            String bundleName = toBundleName(baseName, locale);
            String path = toResourceName(bundleName, "xml");

            InputStream stream;
            if (reload) {
                URL url = loader.getResource(path);
                if (url == null) {
                    return null;
                }
                URLConnection connection = url.openConnection();
                connection.setUseCaches(false);
                stream = connection.getInputStream();
            } else {
                stream = loader.getResourceAsStream(path);
            }

            if (stream == null) {
                return null;
            }

            Properties properties = new Properties();
            try (stream) {
                properties.loadFromXML(stream);
            }

            return new ResourceBundle() {
                @Override
                protected Object handleGetObject(String key) {
                    return properties.getProperty(key);
                }

                @Override
                public Enumeration<String> getKeys() {
                    return Collections.enumeration(
                            properties.stringPropertyNames());
                }
            };
        }
    }

    public static void main(String[] args) {
        XmlControl control = new XmlControl();
        ResourceBundle bundle = ResourceBundle.getBundle(
                "Messages", Locale.US, control);

        System.out.println("Formats: "
                + control.getFormats("Messages"));
        System.out.println("Hello: "
                + bundle.getString("hello"));
    }
}
~~~

Compile and run from the `xml-demo` directory:

~~~bash
javac -encoding UTF-8 XmlControlDemo.java
java -cp . XmlControlDemo
~~~

Verified output:

~~~text
Formats: [xml]
Hello: Hello XML
~~~

### Why Does the Example Handle reload Separately?

When `reload == true`, the example uses `ClassLoader.getResource` -> `URLConnection`, then calls `setUseCaches(false)` before opening the stream. This prevents **URL/connection-layer caching** when `ResourceBundle` requests a reload. If you only called `getResourceAsStream` in the reload branch, some providers or filesystems might return data cached at a lower layer.

This example is **for learning the mechanism**, not a production-ready XML reload solution for all data sources. In real applications, you must verify:

- Protection policies for untrusted resources, size limits, and parser restrictions.
- XML encoding/format, I/O errors, and access permissions.
- Behavior of `ClassLoader`, JARs, `URLConnection`, and external caches.
- That the software runs in an **unnamed module**.
- Thread safety of `Control` when shared across concurrent requests.
- Whether sources requiring versioning/reloading are better suited to a dedicated configuration system than a custom `ResourceBundle`.

Do not use `Properties.load(InputStream)` to read XML. `loadFromXML` is the dedicated XML API matching the XML properties format specification.

## 8. What Is ResourceBundle.Control TTL?

`ResourceBundle` caches bundles to avoid reading resources repeatedly. `Control.getTimeToLive(baseName, locale)` determines **how long a loaded bundle may remain in the cache without revalidating the source**.

Return values:

| TTL Value | Meaning | Behavior |
| --- | --- | --- |
| `TTL_NO_EXPIRATION_CONTROL` (`-2`) | No expiration control | Default; bundle may remain in the cache |
| `TTL_DONT_CACHE` (`-1`) | Do not store bundle in cache | Each lookup may need to load anew |
| `0` | Bundle TTL expires immediately; must validate on cache access | **Does not guarantee reload automatically** |
| `N > 0` | Cache can be used for `N` milliseconds before checking | Upon expiration, `needsReload` is called to decide |
| Negative other than the two sentinels | Invalid value | Do not return such values |

**Do not confuse:** `getTimeToLive` is not a "maximum lifetime of a Java object" and does not force destroying existing references to an old bundle. It only controls how `ResourceBundle.getBundle` uses and revalidates its cache on lookup.

If a variable already holds `ResourceBundle old = ...`, modifying the resource file and loading a new bundle **does not** make `old.getString(...)` switch to the new data. The old bundle remains the referenced object.

### Default TTL and Sample Constants

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

long defaultTtl = control.getTimeToLive(
        "Messages", Locale.FRENCH);
// TTL_NO_EXPIRATION_CONTROL

long neverCache = ResourceBundle.Control.TTL_DONT_CACHE;
// -1

long noExpiration =
        ResourceBundle.Control.TTL_NO_EXPIRATION_CONTROL;
// -2
~~~

This is a **code fragment inside a method**, requiring imports of `java.util.ResourceBundle` and `java.util.Locale`.

Even `TTL_NO_EXPIRATION_CONTROL` **does not guarantee the cache stays in memory forever**: the implementation may evict entries due to memory/cache conditions. "Does not expire by TTL" is different from "never evicted."

## 9. needsReload: TTL Expiration Triggers a Check, Not an Automatic Re-read

When a cache entry exceeds its TTL, the default `ResourceBundle.getBundle` mechanism typically asks:

~~~java
boolean changed = control.needsReload(
        baseName, locale, format, loader, bundle, loadTime);
~~~

This is a **signature-illustration snippet**; the variables are supplied in the callback, not a typical application call.

- If `needsReload(...)` returns **true**, the old entry can be discarded and a new bundle is loaded.
- If it returns **false**, the entry is retained and the TTL check timestamp is updated per policy.
- The default implementation attempts to compare the **source resource's modification timestamp** against `loadTime`. With custom URLs/JARs/resource loaders, modification metadata is not always reliable enough to detect every change.

Consequently, using TTL `0` without understanding `needsReload` can mislead developers into thinking files are always reloaded. In reality, the default `needsReload` may return false if the modification timestamp did not change or could not be detected.

### Callbacks Must Use Consistent Information

`needsReload` receives `format`, `locale`, `loader`, `bundle`, and `loadTime`. When customizing `newBundle`, ensure the source path and change-detection logic match; if `newBundle` reads from an HTTP API or database while `needsReload` still checks the last-modified time of an assumed file, TTL will not reflect the real data.

To demonstrate the mechanism clearly, the next section builds a `Control` that actively returns `true` at the TTL check step and counts the number of loads.

## 10. Example 4 — TTL 0 and needsReload with an In-Memory Bundle

This example requires no resource files, eliminating interference from filesystem clocks, JAR caches, and resource modification timestamps. The `Control` creates a fresh `ListResourceBundle` in `newBundle` while counting load invocations.

Create `TtlReloadDemo.java`:

~~~java
import java.util.List;
import java.util.ListResourceBundle;
import java.util.Locale;
import java.util.ResourceBundle;

public class TtlReloadDemo {
    static class CountingControl extends ResourceBundle.Control {
        private int loads;
        private int checks;

        @Override
        public List<String> getFormats(String baseName) {
            return FORMAT_PROPERTIES;
        }

        @Override
        public List<Locale> getCandidateLocales(
                String baseName, Locale locale) {
            return locale.equals(Locale.ROOT)
                    ? List.of(Locale.ROOT)
                    : List.of(locale, Locale.ROOT);
        }

        @Override
        public Locale getFallbackLocale(
                String baseName, Locale locale) {
            return null;
        }

        @Override
        public long getTimeToLive(
                String baseName, Locale locale) {
            return 0;
        }

        @Override
        public boolean needsReload(
                String baseName, Locale locale, String format,
                ClassLoader loader, ResourceBundle bundle,
                long loadTime) {
            checks++;
            return true;
        }

        @Override
        public ResourceBundle newBundle(
                String baseName, Locale locale, String format,
                ClassLoader loader, boolean reload) {
            if (!locale.equals(Locale.ENGLISH)) {
                return null;
            }

            int version = ++loads;
            return new ListResourceBundle() {
                @Override
                protected Object[][] getContents() {
                    return new Object[][] {
                            {"version", Integer.toString(version)}
                    };
                }
            };
        }
    }

    public static void main(String[] args) {
        CountingControl control = new CountingControl();
        ClassLoader loader =
                TtlReloadDemo.class.getClassLoader();

        ResourceBundle first = ResourceBundle.getBundle(
                "VirtualDemoBundle", Locale.ENGLISH, loader, control);
        ResourceBundle second = ResourceBundle.getBundle(
                "VirtualDemoBundle", Locale.ENGLISH, loader, control);

        System.out.println("First: "
                + first.getString("version"));
        System.out.println("Second: "
                + second.getString("version"));
        System.out.println("Same object: " + (first == second));
        System.out.println("Loads: " + control.loads);
        System.out.println("Reload checks: " + control.checks);
    }
}
~~~

Compile and run on the classpath:

~~~bash
javac -encoding UTF-8 TtlReloadDemo.java
java -cp . TtlReloadDemo
~~~

Verified output:

~~~text
First: 1
Second: 2
Same object: false
Loads: 2
Reload checks: 1
~~~

### Step-by-Step Explanation

1. The first call loads bundle `en`, incrementing `loads` to `1`. There are no external files because `newBundle` constructs the bundle directly.
2. `getTimeToLive == 0` marks the cached instance as expired immediately upon the next access.
3. The second call checks the cache, `needsReload(...)` returns `true`, so `newBundle` creates another instance with `version = 2`.
4. `first == second` is false, yet the `first` object still exists and still holds the value `1`.
5. `Reload checks == 1` proves that the **check step** ran in this scenario.

**Do not infer that TTL 0 always produces this exact result.** If `needsReload` returns false, the loader can keep reusing the old instance. `TTL_DONT_CACHE` is a **different** policy: it does not insert the entry into the cache in the first place.

This example follows standard JDK behavior on an unnamed module; in applications with concurrent calls or multiple class loaders, callback counts and timing can differ. Do not use the unsynchronized mutable counters from this example in a global server `Control`. Production requires explicit thread safety.

## 11. How Does TTL_DONT_CACHE Differ from TTL = 0?

### TTL_DONT_CACHE

`TTL_DONT_CACHE` states that the new bundle **is not added to the cache**. Therefore, on the next lookup for the same bundle, the runtime has no previous cache entry on which to call `needsReload` along the expired branch.

Suitable in certain cases:

- Very small resources that must be reloaded frequently.
- Tests wanting to avoid cache side effects across scenarios.
- Experimenting with a rapidly changing bundle source.

Drawbacks: can increase I/O, allocate many objects, and even repeat **non-existent resource lookups**. Do not use it for every bundle just to keep code "always fresh" without measuring performance.

### TTL = 0

`0` allows caching, but requires **checking the reload condition** on every cache access. Freshness depends on `needsReload`. It can reload data less often than `TTL_DONT_CACHE` when the source has not changed, at the cost of performing the check.

### TTL > 0

A positive TTL like `5_000L` means the cache may be used for up to roughly 5 seconds **without checking the source**, provided the cache entry still exists. Once expired, reloading is evaluated.

This is **not an absolute guarantee of a 5-second maximum update delay** for the whole system: other cache layers, old references, source availability, filesystem delays, or deployments can all affect what users see.

### TTL_NO_EXPIRATION_CONTROL

This is the default `-2`. The cached bundle has no `Control` expiration check cycle. A loaded bundle may continue being served after a file changes until the cache entry is evicted, `clearCache` is called, the class loader reloads, or another mechanism triggers a reload.

## 12. clearCache: Clearing the Cache Does Not Mutate Old Bundles

Java provides:

~~~java
ResourceBundle.clearCache();
~~~

and:

~~~java
ResourceBundle.clearCache(loader);
~~~

These are **illustrative snippets inside a method**; the second requires a `loader` variable of type `ClassLoader`.

- `clearCache()` clears the cache within the class loader scope determined by the API for the caller.
- `clearCache(ClassLoader)` clears the cache associated with the specified class loader.
- Cache scope and lookup in complex class loader/container/module environments require consulting the documentation of the overload being called.
- Clearing the cache does not make existing `ResourceBundle` variables held elsewhere in code change their contents.
- If files/JARs/resources are cached at another layer, clearing the `ResourceBundle` cache alone may not be enough to observe new bytes.

**Do not call `clearCache()` repeatedly on production requests to "force updates"** when you only want TTL control. Broad cache clearing can hurt performance or impact other bundles sharing the class loader. Define a policy suited to the source, pick an appropriate TTL/`needsReload`, and manage versions/deployments as needed.

### Negative Caching

A lookup that finds no bundle for a locale can also be cached (as a not-found marker) to avoid repeated searches. This matters when you **add a new file** at runtime: not only old bundle entries, but also cached "not found" entries can delay updates from appearing. Consider TTL, properly scoped `clearCache`, and the class loader.

## 13. Custom getCandidateLocales: Do Not Alter Arbitrarily

You can override it to change the order or set of candidate locales:

~~~java
@Override
public List<Locale> getCandidateLocales(
        String baseName, Locale locale) {
    if (locale.equals(Locale.ROOT)) {
        return List.of(Locale.ROOT);
    }
    return super.getCandidateLocales(baseName, locale);
}
~~~

This is a **code fragment inside a subclass of `ResourceBundle.Control`**, requiring imports of `java.util.List` and `java.util.Locale`.

This example preserves default behavior while reminding you that **`Locale.ROOT` must be handled properly**. If you design a custom candidate chain, you must:

- Return a **non-null** list of locales with no null elements.
- Maintain specific -> general order according to business requirements.
- Decide whether `Locale.ROOT` is needed at the end of the parent chain.
- Never mutate the returned list while `getBundle` is processing it.
- Ensure `getFormats` and `getCandidateLocales` stay **consistent across calls** for the same base bundle, especially when caching is active.
- Avoid infinite fallback loops or candidates that do not produce the expected resource names.
- Test locales with scripts and special variants; do not apply naive "strip country only" logic to all tags.

### Do Not Alter Candidates to Solve Missing Translation Keys

If `Messages_fr_CA.properties` lacks a key that `Messages_fr.properties` has, the parent chain already provides helpful inheritance. Do not strip `fr` or `ROOT` from candidates just to make "Canadian translations standalone," unless the product deliberately forbids key fallback and accepts throwing an exception or uses another policy.

## 14. Custom getFallbackLocale and Common Mistakes

By default, `Control` may return the JVM's default locale when the target locale differs from the default locale. In a multi-user server application, the default locale is typically a server setting, **not the viewer's language**. This can produce surprising results when translations are missing.

One way to prevent fallback **to the default locale**:

~~~java
ResourceBundle.Control noDefaultFallback =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
~~~

If a more specific policy is needed, you can override:

~~~java
@Override
public Locale getFallbackLocale(
        String baseName, Locale target) {
    return null;
}
~~~

This is a **code fragment inside a subclass of `Control`**, requiring `import java.util.Locale`.

**Distinguish again:**

- `getFallbackLocale() == null`: do not search an additional fallback locale.
- `getCandidateLocales()` can still generate parent locales and `ROOT`.
- `getString(key)` can still inherit values from a **parent bundle**.
- When no bundle exists at all for the base name, `getBundle` can still throw `MissingResourceException`.

If an application requires English as the default business language, manage that language policy explicitly at the calling layer or provider rather than relying on the JVM default locale being invariant across every machine.

## 15. ResourceBundle.Control and Java Modules (JPMS)

This is a critical restriction in Java 9+:

**`ResourceBundle.Control` is not supported when calling an overload taking `Control` from code inside a named module.** Calling:

~~~java
ResourceBundle.getBundle(
        "Messages", requestedLocale, customControl);
~~~

from a **named module** throws `UnsupportedOperationException` per the Javadoc. Mechanically adding `requires java.base` or tweaking the classpath is not a complete solution.

### The Right Direction When Using Named Modules

Use the `java.util.spi.ResourceBundleProvider` mechanism, following the per-base-name provider convention and `uses`/`provides` module declarations per documentation, to support bundles across modules and non-standard formats.

Overview:

~~~text
Classpath / unnamed module:
  ResourceBundle.getBundle(baseName, locale, Control)
  -> supported

Named module:
  ResourceBundle.getBundle(...) via module/provider mechanism
  -> use ResourceBundleProvider when extension is needed
  -> overloads accepting Control are not supported
~~~

`ResourceBundleControlProvider` is a different SPI that can affect `Control` in applicable cases, but **it is ignored in named modules**. Do not confuse it with `ResourceBundleProvider` used for the module mechanism.

Do not try to write a named-module demo using `Control` and treat `UnsupportedOperationException` as "missing module permission." It is an intentional API restriction.

## 16. Caching, Class Loaders, Multithreading, and Real-World Deployment

On a server, several factors can make cache behavior look different from console exercises:

**Class loader.** The same base name on different class loaders can yield different resource sets or separate cache scopes. In an application server or plugin system, understand which class loader is loading bundles.

**Caller module.** Under JPMS, different overloads follow different search paths. Do not apply classpath `Control` assumptions to every named module.

**Consistency.** Never return `getFormats` or `getCandidateLocales` dependent arbitrarily on request state, time, or current user while sharing the same base name and cache. The Javadoc warns results may be unexpected.

**Thread safety.** `ResourceBundle.getBundle` does not synchronize calls to custom `Control` callbacks. Therefore, if a `Control` is shared across threads, `getFormats`, `getCandidateLocales`, `newBundle`, `needsReload`, and `getTimeToLive` must be safe under concurrent calls. `TtlReloadDemo` uses unsynchronized mutable counters solely for single-threaded learning.

**Loading cost.** Setting TTL too short and reloading from a remote source over the network can raise latency or system load. For resources deployed inside the JAR that only change per release, keeping the default cache and replacing the class loader/restarting on release is simpler and more stable.

**Versioned sources.** If live translation updates from a database or remote config are needed, define versioning, ETags, `lastModified`, cache invalidation, and consistency guarantees. `Control` is an extension hook for resource lookup; **it does not solve distributed caching on its own**.

## 17. Error Handling and Testing

| Situation | Symptom | How to check |
| --- | --- | --- |
| Wrong base name | `MissingResourceException` at `getBundle` | Check package, resource path, classpath |
| Missing key | `MissingResourceException` from `getString` | Check key across parent chain |
| Using `FORMAT_CLASS` when only `.properties` exist | Required files not found | Choose `FORMAT_PROPERTIES` |
| Changing formats between calls | Cache may hold an old-format instance | Maintain consistent policy, test cache scope |
| `getCandidateLocales` returns null | Violates `Control` contract | Return a valid list |
| `getFormats` returns empty list | Violates `Control` contract | Include at least one valid format |
| Custom format declared without overriding `newBundle` | `IllegalArgumentException`/fails to load | Provide loader logic for the new format |
| Confusing fallback locale with parent | Root resource appears despite "disabling fallback" | Distinguish `getFallbackLocale` from candidate chain |
| TTL=0 yet file does not reload | `needsReload` returns false or metadata shows no change | Check callback and data source |
| Using `TTL_DONT_CACHE` for all bundles | High I/O, repeated lookups, slow | Measure cost, choose sensible TTL |
| Reloading JAR source misses updates | URL/ClassLoader or lower-layer cache | Check class loader, connection cache, deployment |
| Holding old bundle reference | Values unchanged despite new `getBundle` calls | Fetch fresh instance at appropriate boundaries |
| Using `Control` in a named module | `UnsupportedOperationException` | Switch to `ResourceBundleProvider` |
| Non-thread-safe custom `Control` | Race conditions on multithreaded server | Make `Control` immutable or synchronize properly |
| UTF-8 properties file with bad bytes | Bundle fails to load Unicode properly | Check Java 9+ `PropertyResourceBundle` and charset |

### Pre-Production QA Checklist

1. Determine whether the application uses **classpath/unnamed module** or **named module**.
2. Verify the actual base name, package, and class loader used.
3. Test candidate locales with language/country/script, including `Locale.ROOT`.
4. Test the order of `FORMAT_DEFAULT`, `FORMAT_CLASS`, and `FORMAT_PROPERTIES`.
5. Verify `getNoFallbackControl` **still allows the root parent**.
6. Test keys resolved from the specific bundle and keys inherited from parents.
7. If using a custom format, test `newBundle` with both `reload=false` and `reload=true`.
8. If TTL is positive or 0, test when `needsReload` is invoked and whether data truly updates.
9. Verify `clearCache` does not alter already-held references.
10. Test cache behavior when a resource is initially missing and later added.
11. Test multiple threads and multiple class loaders if applicable to the app.
12. Cross-check behavior against the Oracle Javadoc for the target JDK, not just an old blog post.

## 18. Practice Exercises

1. For `fr-CA`, print the chain using `getCandidateLocales`. Explain why `Messages.properties` can be the parent of `Messages_fr.properties`.
2. For `sr-Latn-RS`, explain why the list contains both `sr-Latn` and `sr-RS` before `sr`.
3. Create three files: `Messages.properties`, `Messages_fr.properties`, and `Messages_fr_CA.properties`. Put a distinct key in each file and verify `getString` resolves from the right parent.
4. Use `getNoFallbackControl(FORMAT_PROPERTIES)` and change the JVM default locale in a separate test. Why can `Messages.properties` still be read?
5. Create both a class bundle and a properties bundle with the same name. When using `FORMAT_DEFAULT`, what determines precedence? Does `FORMAT_PROPERTIES` meet your need?
6. Modify the XML example to use `Messages_fr.xml` and `Messages.xml`. Check the parent chain and explain the role of `toBundleName`/`toResourceName`.
7. In `TtlReloadDemo`, change `getTimeToLive` from `0` to `TTL_DONT_CACHE`. Observe the call counts for `needsReload` and `newBundle`.
8. In `TtlReloadDemo`, keep TTL=0 but return `false` from `needsReload`. Explain why the second call does not necessarily create a new version.
9. When a properties file changes at runtime, why might `ResourceBundle.clearCache()` be insufficient if the `ClassLoader`/URL cache still holds old data?
10. Why is `ResourceBundle.Control` unsuitable when code calls a `Control` overload from a named module? What extension mechanism replaces it?
11. Design a policy for reloading translations from a database: define versioning, TTL, `needsReload`, thread safety, and behavior when the source is temporarily unavailable.
12. Write a test ensuring different `getBundle` calls for the same base name use a consistent format/candidate policy.

**Key takeaway:** `ResourceBundle.Control` governs **candidate locales**, **bundle formats**, **fallback locale**, and **TTL/cache/reload** in classpath applications. `getCandidateLocales` produces a chain from specific to general; `getFormats` chooses class/properties/custom formats; `getFallbackLocale` is distinct from **parent key inheritance**. `TTL_DONT_CACHE` disables caching, `TTL_NO_EXPIRATION_CONTROL` caches without TTL expiration, and TTL 0 or positive values only trigger a `needsReload` check when the entry expires. With **named modules**, do not use `getBundle(..., Control)` overloads; use `ResourceBundleProvider`. Do not vary policies per request or ignore caching and class loaders during testing.

### References

- [Java SE 17 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html) — `getCandidateLocales`, `getFormats`, `getFallbackLocale`, `getTimeToLive`, `needsReload`, `newBundle`, and caching.
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html) — bundle lookup algorithm, parent chain, caching, `clearCache`, class loaders, and modules.
- [Java SE 17 — ResourceBundleProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleProvider.html) — SPI alternative for extensions in named modules.
- [Java SE 17 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html) — bundles from properties files and encoding.
- [Java SE 17 — Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) — `loadFromXML` used in the XML format example.
