# ResourceBundle Caching and clearCache in Java

## 1. Why Does the UI Still Show Old Content After the Translation File Changed?

`java.util.ResourceBundle` is Java's standard mechanism for organizing localization resources such as messages, UI labels, and text across multiple `Locale`s. An application typically calls:

~~~java
ResourceBundle messages = ResourceBundle.getBundle(
        "i18n.Messages", Locale.forLanguageTag("vi-VN"));
String title = messages.getString("page.title");
~~~

**This is a snippet placed inside a Java method**, requiring imports of `java.util.ResourceBundle` and `java.util.Locale`, and the real application must have a bundle with base name `i18n.Messages` on the resource loading path. A **standalone Java example that runs immediately without needing properties files** is in section 8.

A familiar scenario: the application loads `Messages_vi.properties`, a developer updates a translation string in the file, yet the next request still receives the old string. One possible reason is the **ResourceBundle cache**. `getBundle(...)` is not required to search/re-read the resource source on every call; Java **caches ResourceBundle instances by default** and may return the same object on repeated lookups.

Caching provides clear benefits:

- Reduces repeated lookups and reads of `.properties` files or instantiations of `ListResourceBundle` classes.
- Reduces the cost of candidate locale lookup, fallback, and building parent bundle relationships.
- Useful for web applications where many requests share the same set of translation keys.

However, caching raises questions about **when updates become visible**, **invalidation scope**, **class loader/module lifecycle**, **concurrency**, and **multi-server deployments**.

**Opening takeaway:** `ResourceBundle.clearCache` **removes entries from the selected internal cache**; it does not edit file contents, does not mutate bundle objects already held by the application, and does not guarantee that every external cache layer is also refreshed.

## 2. The ResourceBundle Loading Model and Cache Scope

A resource bundle family shares a **base name** and has multiple versions by `Locale`:

~~~text
src/main/resources/
└── i18n/
    ├── Messages.properties
    ├── Messages_en.properties
    ├── Messages_vi.properties
    └── Messages_vi_VN.properties
~~~

**This is an illustrative project structure diagram**, not files created by the program in this article.

For example, when calling `getBundle("i18n.Messages", new Locale("vi", "VN"))`, Java searches for suitable **candidate locales**, picks an available bundle, and sets up the parent chain as needed. A key missing in a specific bundle can be fetched from a parent. Candidate lookup may also fall back to the default locale depending on the API and `Control` in use.

### 2.1. ResourceBundle Is an Object, Not Just a File

A `ResourceBundle` can be:

- A `PropertyResourceBundle` reading `.properties` data.
- A Java-class-based `ListResourceBundle`.
- A custom subclass; on the classpath/unnamed module, `ResourceBundle.Control` can implement special formats, such as storing translations in a database or external resource.

The cache stores **bundle instances** and the information needed to reuse them during `getBundle`. A `ResourceBundle` can have a **parent bundle**. Therefore, when a key is retrieved from a parent, the observed result may depend on both the child bundle and the parent bundle that were loaded/cached.

### 2.2. Same Name Does Not Mean Same Instance in Every Case

Cache lookup is influenced by multiple details in the load request, such as:

- The base name of the bundle family.
- The locale used in the lookup and the actual candidates/fallback.
- The associated `Module` or `ClassLoader`.
- Cache state, time-to-live, and the data source currently being loaded.

Do not claim that every call to `getBundle("i18n.Messages")` across all class loaders, modules, and JVMs returns **one** global instance. Each runtime has its own loading context; resources with the same name in two class loaders can even be **two different sets of files**.

**Nor should a `Control` object be treated as an independent cache namespace.** According to Java documentation, `getFormats` and `getCandidateLocales` must remain consistent when loading the same base name; swapping a `Control` does not necessarily invalidate old cache entries. Custom configurations must be designed consistently with an explicit clear/reload strategy.

## 3. Default Caching: Benefits and Consequences

Under Java SE 17, `ResourceBundle` instances are **cached by default**. As long as a bundle remains valid in the cache, multiple calls to `getBundle` may return the **same instance**.

~~~java
ResourceBundle first = ResourceBundle.getBundle(
        "i18n.Messages", Locale.forLanguageTag("vi-VN"));

ResourceBundle second = ResourceBundle.getBundle(
        "i18n.Messages", Locale.forLanguageTag("vi-VN"));
~~~

This is an illustrative snippet assuming the classpath already has the corresponding resources. Under stable caching conditions, `first == second` **may** be true. Do not rely on this identity check as a contract across class loaders, applications, or JDK upgrades.

### 3.1. Caching Does Not Mean Keeping an Object Forever

Although `ResourceBundle.Control.getTimeToLive` returns `TTL_NO_EXPIRATION_CONTROL` by default, cached bundles **can be evicted from the cache due to memory conditions**. Therefore:

- Do not use `==` on bundles as an immutable identity check.
- Do not expect a call to `getBundle` to necessarily read a file or invoke a constructor only once over the entire lifetime.
- The cache exists for resource optimization, not as a business data store.
- A `ResourceBundle` reference held by the program has an **independent** lifetime from its entry in the cache.

Translation resources are typically static data per release. Default caching fits the **build -> package JAR -> redeploy application** model. For hot-reloading translations, a more explicit design is required.

### 3.2. Missing Lookups Are Also Cached

When looking up a non-existent candidate bundle, loading via `ResourceBundle.Control` can cache a **dummy bundle** as a marker that the resource does not exist, avoiding repeated failed file searches. The dummy is also subject to the Control's TTL rules.

Consequence: if a new locale file is added after a failed lookup, Java may not detect it right away even though the file is present, due to the cached **missing** state. You may need to invalidate the relevant cache or wait for TTL/`needsReload`; at the same time, verify that the file loading path/class loader can actually see the new resource.

Do not treat `MissingResourceException` as definitive proof that "the newly added file does not exist" without checking the cache and packaging mechanism.

## 4. clearCache(): What Does It Clear, and What Doesn't It Clear?

Java SE 17 provides two overloads:

~~~java
ResourceBundle.clearCache();
ResourceBundle.clearCache(classLoader);
~~~

This is an **illustrative snippet**; `classLoader` must be a valid `ClassLoader`, typically obtained from the corresponding module or application class.

| API | Scope described in Java SE 17 |
| --- | --- |
| `ResourceBundle.clearCache()` | Clears cached bundles loaded by the **caller's module** |
| `ResourceBundle.clearCache(ClassLoader loader)` | Clears cached bundles loaded using the **passed-in class loader** |

**Do not equate the two overloads.** In environments with named modules, multiple class loaders, application servers, or plugin class loaders, claiming "`clearCache()` always clears every bundle of every plugin" is false.

### 4.1. What Actually Happens When Clearing the Cache

~~~text
Call 1: getBundle(...) -> creates bundle A, stores in cache
Call 2: getBundle(...) -> may reuse A
             |
             v
       clearCache(loader)
             |
             v
Call 3: getBundle(...) -> looks up again -> may create bundle B

Variables still referencing bundle A continue holding A.
~~~

`clearCache(loader)` **does not mutate the data inside bundle A**. If a service holds:

~~~java
private static final ResourceBundle MESSAGES = /* loaded bundle */;
~~~

then clearing the cache does not automatically change the value of `MESSAGES`; the service must **call `getBundle` again and replace the reference** per its own policy. The snippet above is an illustrative declaration, not a standalone Java file.

`clearCache` also does not:

- Delete resource files, edit `.properties`, write new files, or validate updated contents.
- Remove copies held by the application in a `Map`, `LoadingCache`, `ThreadLocal`, or custom singleton.
- Refresh `MessageFormat` instances, HTML templates, or formatted UI strings stored separately.
- Force other JVMs/nodes in a cluster to invalidate their caches.
- Close class loaders or immediately free all objects.
- Guarantee that the running classpath/JAR can see the newly modified version of a file.

### 4.2. clearCache Is Not an API to Invalidate a Single Key

Java `ResourceBundle` has no `clearCache(baseName, locale)` overload in the standard API. `clearCache(ClassLoader)` affects **all bundles loaded by that loader**, not just one base name, so it can trigger reload overhead across many modules/features.

In large systems, do not call `clearCache` on every request just to pick up one changed label. If data must hot-reload per tenant/locale, consider an application-level cache with namespaces/versions and an invalidation mechanism designed for that scope.

### 4.3. Why Does the Class Loader Parameter Matter?

In application servers, plugins, OSGi, or multi-loader systems, the same bundle name can exist in different contexts. Clearing the cache using class A's loader does not guarantee entries loaded by loader B are cleared.

Illustrative example:

~~~java
ClassLoader loader = MyApplication.class.getClassLoader();
ResourceBundle.clearCache(loader);
~~~

This snippet requires class `MyApplication` to actually exist in the project. In the standalone program in section 8, we use `BundleCacheDemo.class.getClassLoader()` directly so no external class is needed.

**Do not pass null**: `clearCache((ClassLoader) null)` throws `NullPointerException` per JDK documentation.

## 5. TTL: Proactively Controlling Cache Lifetime

`ResourceBundle.Control` allows configuring `getTimeToLive(baseName, locale)` and `needsReload(...)` with `getBundle` overloads that accept a `Control`.

Key constants to remember:

| Return value from `getTimeToLive` | Meaning |
| --- | --- |
| `TTL_NO_EXPIRATION_CONTROL` | Cache does not control expiration by TTL (default) |
| `TTL_DONT_CACHE` | Do not place the loaded instance into the cache |
| `0L` | When retrieving from cache again, **check** whether a reload is needed |
| A positive number, e.g. `5_000L` | Duration in **milliseconds** before re-checking |

**TTL expiration does NOT automatically mean a reload occurs.** Per the `getBundle` contract, after the TTL expires, `Control.needsReload` is queried to see if the resource source has changed:

- Returns `true`: the cached bundle is discarded and reloaded.
- Returns `false`: the bundle can be retained, its TTL timestamp updated, and it continues to be reused.

Therefore, if `getTimeToLive` returns `0L` while `needsReload` always returns `false`, you **do not** achieve "create a new instance on every call." If the real goal is to skip caching, use `TTL_DONT_CACHE` for the corresponding bundle; however, weigh the I/O cost and stability impact.

### 5.1. A Control with Per-Base-Name TTL

~~~java
ResourceBundle.Control policy = new ResourceBundle.Control() {
    @Override
    public long getTimeToLive(String baseName, Locale locale) {
        return baseName.equals("i18n.HotMessages")
                ? 2_000L
                : TTL_NO_EXPIRATION_CONTROL;
    }
};
~~~

This snippet can be placed inside a Java method; `Locale` and `ResourceBundle` must be imported. It **only sets when checks occur**; it does not guarantee reloading if `needsReload` still evaluates the source resource as unchanged.

### 5.2. What Data Does needsReload Rely On?

Signature:

~~~java
boolean needsReload(String baseName, Locale locale,
        String format, ClassLoader loader, ResourceBundle bundle,
        long loadTime)
~~~

This is an illustrative signature, not a complete method. `loadTime` is the load timestamp in milliseconds since the Unix epoch; by default the JDK compares resource modification times when possible. For custom formats (database, REST, JSON, XML…), you usually need to **define** how changes are detected (version, ETag, or modified time) and how the new bundle is loaded in `newBundle`.

Do not make expensive network or database calls every time the TTL expires under heavy request load. You can use a lighter metadata/version cache and rate-limit refreshes; design for concurrency, loading errors, and fallbacks when the source is temporarily unavailable.

### 5.3. newBundle(..., reload) and Other Cache Layers

When a reload is decided, `ResourceBundle.Control.newBundle` receives the `reload` flag. For resources behind a `URL`/`URLConnection`, underlying caches may hold an old copy even after the `ResourceBundle` cache has been cleared. Custom implementations must **re-read the actual source**; in some situations `URLConnection` caching must be disabled when opening the connection for a reload.

Remember too that class-based bundles loaded by an existing class loader **cannot necessarily "reload a new class version"** merely with `ResourceBundle.clearCache`. Changing class bytecode generally requires a new class loader or an appropriate deployment mechanism.

## 6. Designing Hot Translation Updates: Choosing a Solution Based on Requirements

### 6.1. Applications Updating Translations Only on Deployment

The most common setup:

1. Place `Messages*.properties` files in resources.
2. Build the JAR and deploy by version.
3. Let default `ResourceBundle` caching keep lookups fast.
4. When new translations arrive, rebuild/redeploy instead of requiring the system to hot-read modified classpath files.

Advantages: simple, consistent between code and translation keys, and low risk of the runtime reading a mix of old and new translations.

### 6.2. Applications with Translation Files Outside the JAR

If translation files can be updated while the server is running:

1. Specify the source directory and how the loader/`Control` locates resources.
2. Choose a suitable TTL or a version-change event mechanism.
3. On refresh, validate encoding, data integrity, and missing keys.
4. Swap bundle references at request/transaction boundaries; do not update arbitrarily mid-page render.
5. If additional application caches store formatted data, invalidation must cover those layers as well.
6. Have tests verifying **the new translations can be found by the active loader**; do not assume editing a file on disk suffices.

If the source directory is not on the `ClassLoader`'s search path or the JAR was not replaced, `clearCache` will not automatically add it to the loading path.

### 6.3. Multi-JVM or Multi-Node Applications

`ResourceBundle.clearCache` only affects **the calling JVM**. If the service runs across multiple nodes:

- Track the resource version/release batch.
- Distribute invalidation events to the nodes that need refreshing.
- Ensure all nodes can read the same source version.
- Keep a single request's UI consistent against one resource snapshot.
- Have a rollback plan when translations are corrupt, missing keys, or fail QA.

Do not assume a Java call on node A cleared node B's cache.

## 7. ResourceBundle.Control and Named Modules

An important architectural limitation in the **Java Platform Module System (JPMS)**:

- `ResourceBundle.Control` is designed for applications in the **unnamed module/classpath**.
- Calling `ResourceBundle.getBundle(..., Control)` **from a named module** may throw `UnsupportedOperationException` per the Java SE 17 contract.
- For named-module architectures, Java supports `ResourceBundleProvider`/service providers and module-aware `getBundle` overloads; do not assume every `Control` customization can be carried over unchanged from classpath to module path.

The demo program in section 8 is compiled/run **on the classpath** using standard `javac` and `java` commands, so applying `Control` is a valid Java 17 example.

### 7.1. clearCache Scope in Modules

On Java 17, `ResourceBundle.clearCache()` clears cached bundles **loaded by the caller's module**. `ResourceBundle.clearCache(loader)` clears by the specified class loader. The two overloads have distinct scopes, and named modules enforce additional resource/encapsulation rules.

If an application uses JPMS, clearly identify the **caller module**, loader, how resources are declared/opened, and how lookup is performed. When unsure, write an integration test using the real runtime packaging rather than only running on the IDE classpath.

## 8. Complete Java 17 Program: Cache, DONT_CACHE, and clearCache

This example creates bundles **in memory**, without needing `.properties` files or a network. Each new bundle receives an incrementing value `v1`, `v2`,… making it easy to observe **when Java actually creates a new instance**.

**File `BundleCacheDemo.java`:**

~~~java
import java.io.IOException;
import java.util.List;
import java.util.ListResourceBundle;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.concurrent.atomic.AtomicInteger;

public class BundleCacheDemo {
    private static final AtomicInteger CREATED = new AtomicInteger();

    private static final ResourceBundle.Control CONTROL =
            new ResourceBundle.Control() {
        @Override
        public List<String> getFormats(String baseName) {
            return List.of("demo.memory");
        }

        @Override
        public Locale getFallbackLocale(
                String baseName, Locale locale) {
            return null;
        }

        @Override
        public long getTimeToLive(String baseName, Locale locale) {
            return baseName.equals("demo.Fresh")
                    ? TTL_DONT_CACHE : TTL_NO_EXPIRATION_CONTROL;
        }

        @Override
        public ResourceBundle newBundle(String baseName, Locale locale,
                String format, ClassLoader loader, boolean reload)
                throws IOException {
            if (!"demo.memory".equals(format)) {
                return null;
            }
            String content = "v" + CREATED.incrementAndGet();
            return new ListResourceBundle() {
                @Override
                protected Object[][] getContents() {
                    return new Object[][] {{"message", content}};
                }
            };
        }
    };

    private static ResourceBundle load(String name, ClassLoader loader) {
        return ResourceBundle.getBundle(
                name, Locale.ROOT, loader, CONTROL);
    }

    public static void main(String[] args) {
        ClassLoader loader = BundleCacheDemo.class.getClassLoader();

        ResourceBundle first = load("demo.Cached", loader);
        ResourceBundle second = load("demo.Cached", loader);
        System.out.println("first=" + first.getString("message"));
        System.out.println("cachedSameObject=" + (first == second));
        System.out.println("createdAfterCache=" + CREATED.get());

        ResourceBundle fresh1 = load("demo.Fresh", loader);
        ResourceBundle fresh2 = load("demo.Fresh", loader);
        System.out.println("noCacheValues="
                + fresh1.getString("message") + ","
                + fresh2.getString("message"));
        System.out.println("noCacheSameObject=" + (fresh1 == fresh2));

        ResourceBundle.clearCache(loader);
        ResourceBundle afterClear = load("demo.Cached", loader);
        System.out.println("afterClear="
                + afterClear.getString("message"));
        System.out.println("oldReference="
                + first.getString("message"));
        System.out.println("sameAfterClear=" + (first == afterClear));
        System.out.println("createdTotal=" + CREATED.get());
    }
}
~~~

**Compile and run on Java 17+:**

~~~bash
javac -encoding UTF-8 BundleCacheDemo.java
java BundleCacheDemo
~~~

**Verified stdout** on a JDK with corresponding Java SE 17 behavior:

~~~text
first=v1
cachedSameObject=true
createdAfterCache=1
noCacheValues=v2,v3
noCacheSameObject=false
afterClear=v4
oldReference=v1
sameAfterClear=false
createdTotal=4
~~~

Explanation:

1. The first load of `demo.Cached` creates `v1`; the next load receives the **same instance** because `Control` returns `TTL_NO_EXPIRATION_CONTROL`.
2. After two cached loads, the bundle creation counter is `1`.
3. `demo.Fresh` is assigned `TTL_DONT_CACHE`, so two loads produce `v2` and `v3` respectively. Those two references do not point to the same object.
4. `ResourceBundle.clearCache(loader)` invalidates cache entries tied to `loader`; reloading `demo.Cached` creates `v4`.
5. `first` still points to `v1` even though its cache entry was cleared. `clearCache` **does not mutate already-referenced bundles**.
6. A total of four instances were created.

The `ListResourceBundle` in this program **creates no files and makes no network calls**; `Control.newBundle` constructs the resource directly to illustrate caching. This is **a controlled demonstration**, not a production hot-reloading translation file reader. `AtomicInteger` increments the counter safely if the demo is extended across threads; that does not make every arbitrary `Control` implementation automatically thread-safe.

### 8.1. Why Is Thread.sleep Not Needed for Testing?

The example does not test millisecond-based TTLs. It uses two well-defined policies:

- `TTL_NO_EXPIRATION_CONTROL`: uses default caching behavior.
- `TTL_DONT_CACHE`: always creates a new bundle on load requests.

The result does not depend on sleep durations or machine speed. When testing positive TTLs and `needsReload`, use a fake clock/metadata test or a source with controlled version changes, avoiding brittle tests based on mtime and `Thread.sleep`.

### 8.2. Why Is the Custom Format Valid?

`getFormats` returns `List.of("demo.memory")`, and `newBundle` handles that exact format. This is a **custom-defined** format within `Control`, not a file extension searched automatically by the JDK. Because the locale is `Locale.ROOT` and fallback is disabled, the demo output does not depend on the machine's default locale.

In a real application where `Control` reads from files or a DB, ensure `getFormats`, `newBundle`, `getTimeToLive`, and `needsReload` agree on a single data-source model.

## 9. Common Mistakes

| Misconception | Consequence | Resolution |
| --- | --- | --- |
| Editing `.properties` and expecting `getBundle` to re-read immediately | Cache may return old resource | Verified TTL or clear/reload |
| Calling `clearCache` while holding a `static final ResourceBundle` field | UI still shows old strings | Call `getBundle` again and update references where needed |
| Assuming `clearCache()` clears all bundles across all loaders | Stale cache remains in other scopes | Pick the overload matching the module/loader |
| Assuming `clearCache(loader)` clears only one locale | Can affect many bundles on the same loader | Weigh scope and reload cost |
| Assuming TTL expiration guarantees a new object is created | `needsReload` may return false | Distinguish validation from reload |
| Setting TTL 0 while `needsReload` fails to detect changes | Still receives stale data | Implement proper version/mtime checks |
| Using `TTL_DONT_CACHE` for every busy request | Wastes I/O and CPU, raises service load | Design TTL/snapshots or versioned caching |
| Varying `Control` formats for the same base name per request | Cache may reuse a bundle of another format | Keep `Control` rules consistent |
| Adding a new bundle that the loader cannot see | `clearCache` cannot find the file | Inspect classpath/JAR/class loader |
| Ignoring negative-cache/dummy entries | New locale remains undetected | Handle invalidation/TTL for missing entries |
| Assuming clearing cache triggers immediate GC | Referenced objects stay alive | Drop app references when safe |
| Using the `Control` overload in a named module | May throw `UnsupportedOperationException` | Use an appropriate module/provider architecture |
| Refreshing per key mid-page render | Strings on the same page mix translation versions | Use one snapshot per request |
| One node clears cache and assumes the whole cluster is done | Other nodes still show old translations | Coordinate invalidation/deployment |
| Testing only on IDE classpath then deploying via modulepath | Different scope/loading behavior | Integration-test with actual packaging |

## 10. Tests to Include

A module using `ResourceBundle` should have these test groups:

1. **Cache hit:** two loads with the same base name/locale/loader/control before expiration return the same content without forced refetching.
2. **clearCache(loader):** after clearing, the next load via that loader receives a bundle loaded from the updated source; old references retain prior data.
3. **clearCache() module scope:** if using JPMS, verify the exact caller-module scope rather than extrapolating to the entire JVM.
4. **TTL_DONT_CACHE:** two `getBundle` calls create independent instances when the `Control` policy disables caching.
5. **Positive TTL and TTL 0:** verify expiration triggers `needsReload`, while a new bundle is created only when it returns true or under other cache conditions.
6. **Fallback:** missing key in specific locale while key exists in parent; verify behavior after refreshing parent.
7. **Negative lookup:** missing bundle, then added later; confirm the policy for detecting new bundles, including cached "missing" markers.
8. **ClassLoader:** two loaders having bundles with the same name from different sources; clearing one loader does not mix data.
9. **Multi-thread:** concurrent requests reading bundles and clearing/reloading while old references remain active; no half-updated data or crashes.
10. **Multi-node:** translation versions stay accurate per node with invalidation orchestration when required.
11. **Packaging:** compare classpath/unnamed module vs. modulepath/named module; avoid unsupported `Control` usage in named modules.
12. **Resource errors:** missing base name, missing key, properties parsing errors, invalid encoding, I/O failures; explicit error messages and policy-defined fallback.
13. **Real file modification behavior:** write a valid update, verify the loader sees the file and `needsReload` evaluates mtime/version properly, not merely "clearCache returned without throwing."
14. **Performance:** measure cache hit rate, reload latency, heap size, and source read counts, especially with short TTLs.

If strict update ordering is required, test with **explicit version numbers** rather than comparing "newer" solely via system clock. Filesystem mtimes have varying resolutions; clock skew or updates within the same tick can make change-detection logic flaky.

## 11. Practice Exercises

1. Run `BundleCacheDemo` and point out exactly which two calls return the same instance and which two calls create new ones.
2. Remove `ResourceBundle.clearCache(loader)`; predict what `afterClear` becomes in the program and what the final counter value is.
3. Modify `getTimeToLive` so `demo.Cached` also returns `TTL_DONT_CACHE`. Check how many times `newBundle` is called and explain the trade-off.
4. Create two base names sharing the same loader with caching enabled; after `clearCache(loader)`, check the effect on both bundles.
5. Create `Messages.properties` and `Messages_vi.properties` and load `Locale.forLanguageTag("vi-VN")` with explicit fallback; update a key in the parent bundle and check the effect of refreshing.
6. Create a `Control` whose `getTimeToLive` returns 0 and `needsReload` returns false; explain why every `getBundle` call does **not** necessarily create a new instance.
7. Create a `Control` using a version number at the source (without `Thread.sleep`); when the version changes, `needsReload` returns true. Test that the bundle reloads.
8. Hold a `ResourceBundle` in a singleton field; after clearing the cache, call `getString` on both the old field and the newly fetched bundle, and explain the output.
9. Try adding a locale file in a directory **not on the classpath**; explain why clearing the cache does not help the loader find the file.
10. Use two different `ClassLoader` instances to load resources with the same base name; observe the scope of `clearCache(loader)`.
11. Write a hot-reload checklist for multi-JVM deployments: identify source of truth, versioning, notification mechanism, invalidation scope, and rollback testing.
12. Investigate `ResourceBundleProvider` in named modules and compare its differences with `Control` in unnamed modules.

## 12. Summary

`ResourceBundle` **caches loaded bundles by default** to reduce lookup and instantiation overhead. `ResourceBundle.clearCache()` clears entries for the **caller module**, whereas `clearCache(ClassLoader)` clears entries for the **passed-in loader**; neither mutates bundle objects to which application code still holds references.

When translations must be reloaded, distinguish **clearing the cache** from **whether the underlying resource source can actually be reloaded**. `ResourceBundle.Control.getTimeToLive` controls when checks happen, `needsReload` determines whether a reload is required after expiration, and `TTL_DONT_CACHE` disables caching. Missing lookups can also be cached as absent markers, and class loaders/JARs/JPMS can restrict visibility of new resources.

Choose a strategy suited to the product: **default caching + redeploy** for statically packaged resources; **TTL/versioned reload + targeted invalidation** when hot reload is genuinely needed; keep a single snapshot per request and coordinate across nodes in distributed deployments. Do not call `clearCache` indiscriminately on every request when unnecessary.

**References:**

- Java SE 17, `ResourceBundle` (Cache Management, clearCache, getBundle): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html
- Java SE 17, `ResourceBundle.Control` (getTimeToLive, needsReload, newBundle): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html
- Java SE 17, `ListResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListResourceBundle.html
- Java SE 17, `ResourceBundleProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleProvider.html
