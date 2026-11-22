# Distinguishing Finding a Matching Bundle from Looking Up a Key in the Parent Chain

## 1. The Problem: One Term "Fallback", Two Different Operations

In Java, `ResourceBundle` provides resources by locale. When an application writes:

```java
ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);
String value = bundle.getString("button.save");
```

Java performs **two distinct tasks**:

1. **Finding a matching bundle:** `getBundle(...)` determines which bundle in the `Messages` resource family can be used for the requested locale, based on the candidate list, classpath/module, fallback mode, and which resources actually exist.
2. **Looking up a key in the parent chain:** once a bundle is obtained, `getString("button.save")` searches for the key's value in the held bundle; if absent, it walks the linked `parent` bundles.

The two operations are easily confused because both can move from specific to general content. Yet they differ in **starting point, question answered, timing, and error behavior**.

| Criterion | Finding a matching bundle | Looking up a key in the parent chain |
| --- | --- | --- |
| Common API | `ResourceBundle.getBundle(...)` | `bundle.getString(key)` / `bundle.getObject(key)` |
| Question | "Is there a resource bundle suitable for this locale?" | "In this bundle or its parents, where is this key?" |
| Primary inputs | Base name, locale, module/class loader, `Control` (if supported) | A loaded bundle and a key |
| Search unit | Bundle / file / resource class | Key/value in the current bundle and its parents |
| Result | `ResourceBundle` instance | Object or string value of the key |
| Typical error | `MissingResourceException` when no suitable bundle is found | `MissingResourceException` when the key is not found |
| Uses JVM default locale? | Possibly, per the bundle loading mechanism | Does not switch to the default locale just because a key is missing |
| Path to base bundle | Final candidate in the bundle selection process | A parent that may supply a missing key |

**Most important point:** If the `Messages_vi_VN` bundle is found and then the `button.save` key is missing, Java **does not re-run bundle selection to find an English bundle that has the key**. It uses the *parent chain of the already-selected bundle*.

## 2. Resource Chain by Specificity

Suppose the resource set on the classpath is:

```text
Messages.properties
Messages_vi.properties
Messages_vi_VN.properties
Messages_en_US.properties
```

- `Messages.properties`: base bundle (bundle with no locale suffix).
- `Messages_vi.properties`: shared resources for Vietnamese.
- `Messages_vi_VN.properties`: specialized resources for Vietnamese in Vietnam.
- `Messages_en_US.properties`: a different bundle for English in the United States.

For a simple `vi-VN` locale, Java builds a candidate list ordered by specificity:

```text
Messages_vi_VN
      |
      v
Messages_vi
      |
      v
Messages (base)
```

When `Messages_vi_VN` is found, the broader bundles that actually exist can be linked into a parent chain:

```text
held bundle
  Messages_vi_VN
      parent --> Messages_vi
                      parent --> Messages (base)
```

**The two arrows mean different things at different times:**

- At **load time**, Java selects a matching bundle and sets up `parent` relationships to less specific bundles.
- At **key lookup time**, Java searches the current bundle first and then walks the existing parents. A parent is an **actual resource** loaded by the algorithm, not automatically every suffix one can imagine.

If `Messages_vi_VN.properties` is missing while `Messages_vi.properties` exists, the returned bundle can be `Messages_vi` with base as its parent. `bundle.getLocale()` reports the locale of the **returned bundle**, which can be `vi` even though the requested locale was `vi-VN`.

### 2.1. Filenames and Language Tags

`Locale.forLanguageTag("vi-VN")` uses BCP 47 with a hyphen `-`. `ResourceBundle` file suffixes use the naming convention `Messages_vi_VN.properties` with an underscore `_`. Do not confuse the filename string with a language tag or the base bundle name.

The sequence `vi_VN → vi → base` applies to language/region examples without scripts or variants. For `zh-Hant-TW` or locales with variants, the candidate list can be longer and ordered differently; do not assume there are always only three levels.

## 3. Phase A: Finding and Loading a Matching Bundle

In Java, a typical call is:

```java
Locale requested = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle = ResourceBundle.getBundle("Messages", requested);
```

Conceptually, Java needs to:

1. Build the **candidate locales** list for `requested`, from specific to less specific, including base.
2. Search for the corresponding bundle in available resource sources, typically a `ListResourceBundle` class or a `.properties` file on the classpath; class-based bundles may take precedence over properties by default.
3. If a sufficiently specific matching bundle is found, select it and link existing parents.
4. If no non-base bundle is found for the requested locale, the default strategy may retry with the **JVM default locale**; the base bundle serves as the last-resort resource.
5. If no suitable bundle exists at all, throw `MissingResourceException`.

This model describes classpath/unnamed modules under the default loading strategy. In named modules, Java enforces additional resource access and provider rules; do not infer everything from classpath examples.

**Watch Step 4:** An existing `Messages.properties` file is not necessarily returned immediately when no bundle matches the requested locale. For instance, if `fr-FR` is requested, the JVM default is `en-US`, and `Messages_en_US.properties` exists, Java may select the English bundle for the JVM default before falling back to base. This is still **bundle lookup**, occurring before `getString(key)` is ever called.

When Java selects `Messages_en_US` because no French bundle exists, the parent chain is built for that selected bundle branch. It does not construct a global tree spanning all languages.

### 3.1. `getBundle` Does Not Inspect the Keys You Will Read

The call `getBundle("Messages", viVN)` takes no `key` parameter. It does not know whether you will later call `getString("button.save")` or `getString("menu.exit")`.

A `Messages_vi_VN` bundle containing **only a single key** can still be selected. Translation quality and completeness are the responsibility of content management and testing, not criteria `getBundle` uses to reject a bundle.

### 3.2. Observing Exact Candidate Locales

The standalone Java 17 example below lists the candidate locales for `vi-VN` without creating any resource files.

File `CandidatesDemo.java`:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class CandidatesDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        for (Locale candidate :
                control.getCandidateLocales("Messages", locale)) {
            System.out.println(
                    candidate.equals(Locale.ROOT)
                            ? "(base)"
                            : candidate.toLanguageTag());
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 CandidatesDemo.java
java CandidatesDemo
```

Stdout:

```text
vi-VN
vi
(base)
```

`getCandidateLocales` only shows **the candidates that can be tried**. It does not guarantee that all corresponding files exist, does not tell you which keys are present, and does not itself represent the fallback step to the JVM default locale.

## 4. Phase B: Reading a Key in the Bundle and Parent Chain

Once you hold the object:

```java
String savedLabel = bundle.getString("button.save");
```

`getString` essentially obtains the result of `getObject(key)` and casts it to `String`. Per the `ResourceBundle` specification, `getObject`:

1. Queries the **current bundle** using `handleGetObject(key)`.
2. If no value exists in this bundle and it has a parent, calls `parent.getObject(key)`.
3. Repeats up the parent chain until a value is found.
4. If the chain is exhausted without finding one, throws `MissingResourceException`.

There is no step that spontaneously searches `Messages_en_US` when a key is missing in `Messages_vi_VN`. If `Messages_en_US` is a "sibling" belonging to another locale and **not in the held parent chain**, keys in it are not considered at all.

When a key exists in both `Messages_vi_VN` and `Messages_vi`, the value in the **more specific bundle** wins. This is **shadowing/overriding** a key with a more specific translation.

Several APIs are commonly misunderstood:

| API | Includes parents? | Key thing to remember |
| --- | --- | --- |
| `getString(key)` | Yes | Returns value from the nearest bundle containing the key |
| `getObject(key)` | Yes | Returns object, or throws when missing |
| `getStringArray(key)` | Yes | Value must be of type `String[]` |
| `containsKey(key)` | Yes | `true` does not prove the current bundle owns the key |
| `keySet()` | Yes | Set of keys visible across the bundle and its parents |
| `getKeys()` | Yes | Enumerates keys from the bundle and its parents |
| `getLocale()` | Not a key lookup | Reports the locale of the returned bundle, **not which file a key came from** |

With `getString(key)`, if the key exists but its value is not a `String`, you may get a `ClassCastException`. If the key is `null`, you get a `NullPointerException`. Distinguish those errors from "bundle not found".

### 4.1. Two Different Ways of Being "Missing"

- **Missing bundle:** `getBundle("NoSuchBase", locale)` finds no usable bundle family at all → throws `MissingResourceException` right at load time.
- **Missing key:** `getBundle("Messages", locale)` succeeded, but `getString("does.not.exist")` finds no key in any parent → also throws `MissingResourceException`, but at **key lookup time**.

You can log context to diagnose the two errors separately: base name, requested locale, resolved bundle locale, and key; do not rely solely on the fact that both throw the same exception class.

## 5. Complete Example: Each Key Comes from a Different Level

Create four files in the **same directory**:

```text
BundleChainDemo.java
Messages.properties
Messages_vi.properties
Messages_vi_VN.properties
```

**`Messages.properties`**

```properties
title=Base title
button.save=Save
help=Base help
```

**`Messages_vi.properties`**

```properties
title=Tiêu đề tiếng Việt
button.save=Lưu
```

**`Messages_vi_VN.properties`**

```properties
title=Tiêu đề dành cho Việt Nam
```

**`BundleChainDemo.java`**

```java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class BundleChainDemo {
    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("vi-VN");

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle bundle =
                ResourceBundle.getBundle("Messages", requested, control);

        System.out.println("requested=" + requested.toLanguageTag());
        System.out.println("selected=" + bundle.getLocale().toLanguageTag());
        System.out.println("title=" + bundle.getString("title"));
        System.out.println("button.save=" + bundle.getString("button.save"));
        System.out.println("help=" + bundle.getString("help"));
        System.out.println("has.help=" + bundle.containsKey("help"));
        System.out.println("has.unknown=" + bundle.containsKey("unknown"));

        try {
            bundle.getString("unknown");
        } catch (MissingResourceException ex) {
            System.out.println("unknown=MissingResourceException");
        }
    }
}
```

Run with JDK 17+ on the classpath; save the `.properties` and `.java` files as UTF-8:

```bash
javac -encoding UTF-8 BundleChainDemo.java
java -cp . BundleChainDemo
```

Stdout when the terminal displays UTF-8 Unicode:

```text
requested=vi-VN
selected=vi-VN
title=Tiêu đề dành cho Việt Nam
button.save=Lưu
help=Base help
has.help=true
has.unknown=false
unknown=MissingResourceException
```

Explanation:

- `requested` is the requested locale `vi-VN`.
- `selected` is also `vi-VN` because `Messages_vi_VN.properties` exists. That is the **bundle lookup result**.
- `title` is directly in `Messages_vi_VN`, so it shadows the same key in `Messages_vi` and base.
- `button.save` is absent in `vi_VN`; `getString` looks in parent `Messages_vi`, returning `Lưu`.
- `help` is in neither `vi_VN` nor `vi`; it is in base, returning `Base help`.
- `bundle.containsKey("help")` is `true` because the API includes parents. Do not interpret this result as "`Messages_vi_VN.properties` contains the `help` key".
- `unknown` is absent at every level; `containsKey` gives `false` and `getString` throws `MissingResourceException`.

We can summarize **the source of each key** in this scenario:

| Key | Nearest file containing the key | Value |
| --- | --- | --- |
| `title` | `Messages_vi_VN.properties` | `Tiêu đề dành cho Việt Nam` |
| `button.save` | `Messages_vi.properties` | `Lưu` |
| `help` | `Messages.properties` | `Base help` |
| `unknown` | Absent from chain | Throws `MissingResourceException` |

**Important distinction:** `bundle.getLocale()` still returns `vi-VN` across all four calls. It does not change to `vi` when reading `button.save`, nor to `Locale.ROOT` when reading `help`.

Since Java 9, `.properties` files are read by `PropertyResourceBundle` with UTF-8 support by default (with a Latin-1 compatibility fallback); manage file and terminal encodings consistently so Vietnamese text displays properly.

## 6. When the Specific Bundle Does Not Exist: Bundle Selection Changes, Key Lookup Stays the Same

Keep the Section 5 example but **omit** `Messages_vi_VN.properties`; only base and `Messages_vi.properties` remain. Running the same code changes the outcome:

- `getBundle("Messages", vi-VN, control)` returns `Messages_vi`, because it is the most specific available bundle.
- `bundle.getLocale().toLanguageTag()` is `vi`.
- `title` now becomes `Tiêu đề tiếng Việt` from the `vi` bundle.
- `button.save` is still `Lưu` from `vi`.
- `help` still comes from base through the parent chain.

There is no way `getString("title")` magically finds `Messages_vi_VN` "somewhere"; that specialized bundle was already absent in the first step. Conversely, if the specific bundle **does exist** while missing the `title` key, it can still be selected, and then `getString` looks up `title` in its parent.

Two easily confused scenarios:

```text
Scenario A — missing Messages_vi_VN file:
  getBundle(vi-VN)  -> returns Messages_vi
  getString(title) -> reads from Messages_vi

Scenario B — Messages_vi_VN file exists, but key title is missing:
  getBundle(vi-VN)  -> returns Messages_vi_VN
  getString(title) -> looks up in Messages_vi (parent)
```

In both scenarios, the screen may show the same string, yet **the origin and diagnosis differ**. `getLocale()` helps identify the selected bundle, though **it does not pinpoint the exact file containing each key**.

## 7. Sibling Bundles Are Not in the Parent Chain

Another example:

```text
Messages.properties
Messages_vi.properties
Messages_vi_VN.properties
Messages_en_US.properties
```

Suppose the `account.delete` key exists only in `Messages_en_US.properties`, and is absent from the other three files. After loading `Messages_vi_VN` and calling:

```java
bundle.getString("account.delete");
```

Java does **not** search `Messages_en_US` just because it is the only place with the key. `Messages_en_US` is a bundle for a different locale, not a parent of `Messages_vi_VN` in the `vi_VN → vi → base` chain. The result is `MissingResourceException`.

If the system wants a key to fall back to English, you must **design a policy** so the content fallback chain fits: for example, place default keys in an English base bundle, or have an application-layer message resolver actively query multiple sources. Do not claim that Java searches every language by default until it finds a key.

Similarly, if `Messages_fr.properties` and `Messages_de.properties` exist, a missing key in `fr` does not trigger trying `de`. Java walks `fr`'s parent chain; it does not scan arbitrarily across all existing translations.

## 8. One More Kind of Fallback: JVM Default During Bundle Selection

To separate this even more clearly, consider requesting `fr-CA` when no French files exist. The JVM default locale is `en-US`, and the resource set is:

```text
Messages.properties
Messages_en_US.properties
```

With the default overload:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("fr-CA"));
```

Java can try candidates `fr_CA`, `fr`; when no matching non-base bundle exists, it tries candidates for the JVM default locale `en-US` and selects `Messages_en_US`. Later, when calling `bundle.getString(key)`, Java looks up the key in `Messages_en_US` and then that bundle's parent chain (typically base). It **does not return to the `fr_CA → fr` chain** when reading a key.

This is **bundle-lookup fallback**, distinct from key fallback. The distinction matters in practice: relying on the server's `Locale.getDefault()` can cause the same request to display different languages across two deployment environments.

If the app already selects a supported locale before calling `getBundle` and provides complete files, the JVM fallback step may never occur. For applications wishing to avoid JVM default fallback entirely on the classpath, Java provides a dedicated `Control`:

```java
ResourceBundle.Control noJvmDefaultFallback =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle =
        ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("fr-CA"),
                noJvmDefaultFallback);
```

`getNoFallbackControl` makes `Control.getFallbackLocale(...)` return `null`, meaning **it will not try the JVM default locale**. It **does not disable** the `fr_CA → fr → base` candidates, nor does it **disable** parent key lookup. With the files above and a base bundle present, this method returns base. If no bundle exists at all, it can still throw `MissingResourceException`.

**Java Module System limitation:** The `ResourceBundle.getBundle(..., ResourceBundle.Control)` overloads are intended for code in unnamed modules / on the classpath; calling them from a named module is unsupported and can throw `UnsupportedOperationException`. For named modules, check `ResourceBundleProvider` and the appropriate module resource mechanisms. The `Control` examples here are designed to run on the classpath.

## 9. Runnable Example: "Key Only in a Sibling" Cannot Rescue the Request

Create the files:

```text
SiblingDemo.java
Catalog.properties
Catalog_vi.properties
Catalog_en_US.properties
```

**`Catalog.properties`**

```properties
title=Catalog
```

**`Catalog_vi.properties`**

```properties
title=Danh mục
```

**`Catalog_en_US.properties`**

```properties
title=Catalog for US
action.checkout=Checkout
```

**`SiblingDemo.java`**

```java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class SiblingDemo {
    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle bundle =
                ResourceBundle.getBundle("Catalog", vietnamese, control);

        System.out.println("selected=" + bundle.getLocale().toLanguageTag());
        System.out.println("title=" + bundle.getString("title"));
        System.out.println("has.checkout=" +
                bundle.containsKey("action.checkout"));

        try {
            System.out.println(bundle.getString("action.checkout"));
        } catch (MissingResourceException ex) {
            System.out.println("checkout=MissingResourceException");
        }

        ResourceBundle us =
                ResourceBundle.getBundle("Catalog", Locale.US, control);
        System.out.println("us.checkout=" + us.getString("action.checkout"));
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 SiblingDemo.java
java -cp . SiblingDemo
```

Stdout when the terminal displays UTF-8:

```text
selected=vi
title=Danh mục
has.checkout=false
checkout=MissingResourceException
us.checkout=Checkout
```

Read the output strictly as two phases:

1. For `vi-VN`, `Catalog_vi_VN` is missing, so **bundle lookup** selects `Catalog_vi`.
2. In `Catalog_vi`'s parent chain there is base `Catalog`, yet neither has `action.checkout`. **Key lookup** fails.
3. `Catalog_en_US` does have that key, but it is a **sibling**, not in `Catalog_vi`'s parent chain.
4. Only when making a **separate** `getBundle("Catalog", Locale.US, control)` call does the application load the English bundle and obtain `Checkout`.

This is why "the key exists in some translation file" should not be used as proof that every supported locale can display that key.

## 10. Analyzing API Names and the Scope of Information They Provide

### `bundle.getLocale()`

Returns the locale of the selected bundle. Useful for verifying whether Java used `vi_VN`, `vi`, base, or JVM fallback. However, if a key is read from a parent, `getLocale()` **still returns the locale of the current bundle object**; the API does not change locale per key.

### `bundle.containsKey(key)`

Returns `true` if the key is in this bundle **or a parent**. Do not use it as a test asserting "the dedicated `vi_VN` translation contains the key". If you need to verify completeness of individual translation files, read/compare the raw resource contents or use dedicated validation tooling. `keySet()` and `getKeys()` also include parents.

### `getString(key)` and `getObject(key)`

They read values along the parent chain; they take no locale parameter and do not trigger another bundle lookup simply because a key is missing. `getString` requires the value type to be `String`, whereas `getObject` can return other types if the bundle stores objects.

### `ResourceBundle.Control.getCandidateLocales(...)`

Shows the *candidate* locales of the bundle-lookup phase, not the list of bundles actually present, and certainly not the list of parents traversed by a given key. Candidate generation becomes more complex when a locale has scripts/variants. `Control` also lets you customize formats and fallback locales on the classpath, though a custom control must guarantee consistency and thread-safety.

### Caching and Resource Sources

`ResourceBundle` normally caches loaded bundles. If `.properties` files are modified while the application is running, subsequent calls may return cached instances; `clearCache`, TTL, or redeployment must be managed properly. Caching **does not merge** bundle selection and key lookup into a single phase.

## 11. Implications for Multilingual Application Development

### 11.1. Separate the Application Locale from the Selected Bundle

The application determines the display locale from user preferences, supported lists, and product fallback rules. Once `uiLocale` is decided, call `getBundle(..., uiLocale)`. If it returns the `vi` bundle for `uiLocale=vi-VN`, that does not mean you must downgrade formatter locales to `vi`: you can still use `vi-VN` for numbers and dates, and a separate `ZoneId` for time.

Do not call `Locale.setDefault(...)` on each HTTP request because it changes the JVM-wide default and can affect other requests. Pass the locale explicitly.

### 11.2. Control Translation Coverage per Locale

For critical UIs, "bundle loaded successfully" does **not** mean translations are complete. A specialized bundle might not even contain any key for the current screen; the entire screen could end up rendered from a parent.

Verify that:

- All critical UI keys exist in base and required translations have sufficient coverage.
- Placeholders like `{0}`, `{1}` are compatible across locales, without missing or altered semantics.
- Policy clearly defines which keys may inherit from a parent and whether mixed-language screens are acceptable.
- When a key is missing at all levels, the application records the error at key lookup rather than silently displaying the raw key if the product has not defined that behavior.
- Script, region, and server default locale cases are tested against the actual supported regions.

### 11.3. Distinguish "Fallback by Design" from "Leaked Content from Base"

For example, `Messages.properties` is in English and `Messages_vi.properties` is incompletely translated. When `getString("button.save")` returns "Save" on a `vi-VN` screen, that is **key inheritance from base**, not Java choosing the `en-US` locale. If the product requires full Vietnamese, the fix is to add the key in the Vietnamese bundle or fail validation at build time. Changing `uiLocale` to match `bundle.getLocale()` will not fix the root cause.

### 11.4. Observe Errors with Enough Context

When catching `MissingResourceException`, log context by category:

```text
BUNDLE_NOT_FOUND
  baseName=Messages
  requestedLocale=vi-VN
  source=ResourceBundle.getBundle(...)

KEY_NOT_FOUND
  baseName=Messages
  requestedLocale=vi-VN
  resolvedBundleLocale=vi
  key=button.save
  source=bundle.getString(...)
```

This is a **suggested log format**, not an error Java automatically generates with those exact field names. Avoid logging personal data or full user payloads for diagnostics.

## 12. Common Misconceptions

| Misconception | Correction |
| --- | --- |
| "Java searches for a file containing the key first, then selects the bundle." | `getBundle` selects the bundle independently of keys read later. |
| "Missing `vi_VN` and missing a key in `vi_VN` are the same situation." | Missing bundle happens at load time; missing key happens during parent lookup. |
| "If `en_US` has the key, `getString` from `vi` will automatically fetch it." | No; siblings are not part of the parent chain. |
| "`getLocale()` changes to the locale of the parent that returned the key." | No; it returns the locale of the held bundle. |
| "`containsKey` indicates the key is declared in the current specific file." | It includes parents as well. |
| "`getNoFallbackControl` forbids all forms of fallback." | It blocks fallback to the locale supplied by `getFallbackLocale`, not candidates/base/parent. |
| "The base bundle is always returned before JVM default." | Under the default strategy, Java may try the JVM default bundle before choosing base. |
| "Once a bundle is loaded, a key can never be missing." | `getString` can still throw `MissingResourceException`. |
| "If multiple locales share a JVM, you can set default per request." | JVM default is process-wide; pass locale per request. |
| "Every application can use `Control`." | Overloads taking `Control` are not supported when called from a named module. |

## 13. Testing and Practice Exercises

### Scenario A — Missing Regional Bundle

Suppose only `Labels.properties` and `Labels_vi.properties` exist, and `vi-VN` is requested. Which bundle does Java select? If `Labels_vi.properties` lacks the `help` key while base has it, what happens?

**Answer:** `getBundle` normally returns `Labels_vi`; `getString("help")` retrieves it from base via the parent chain.

### Scenario B — Complete Bundle Missing One Key

`Labels_vi_VN.properties` has the `title` key, while `Labels_vi.properties` has `save`. Should you say the application switched to `vi` when the user clicks Save?

**Answer:** No. The returned bundle is `vi-VN`; the `save` key comes from parent `vi`. `bundle.getLocale()` remains `vi-VN`.

### Scenario C — Key Missing Across the Entire Chain

`Labels_en_US.properties` contains `delete`, while neither the selected `Labels_vi` bundle nor base contains `delete`. Does `getString("delete")` search `en_US`?

**Answer:** No. It throws `MissingResourceException` because `en_US` is not a parent of `vi`. To look up `en_US` separately, you must explicitly load it with separate logic.

### Scenario D — JVM Default Intervention

Server default is `en-US`, request is `fr-FR`, base and `Labels_en_US.properties` exist, and no French bundle exists. In which step can Java select `en-US`?

**Answer:** During **bundle lookup**, under the default strategy which tries the JVM default. Key lookup starts after the bundle is selected, following the resulting bundle's parent chain.

### Scenario E — Coverage Check

`bundle.containsKey("submit")` is `true` even though the specialized translation file lacks the key. How do you write a test to catch missing translations?

**Answer:** Compare the set of keys **directly declared** in each resource source against a canonical key set or coverage requirement, rather than relying solely on `containsKey`/`keySet` which include parents.

### Extended Exercise

Keep the `BundleChainDemo` example and follow these steps in order:

1. Remove `Messages_vi_VN.properties` **only from the runtime resource set**; observe `selected` change from `vi-VN` to `vi`.
2. Add the `vi_VN` file back without the `title` key; observe `selected` stays `vi-VN` while `title` comes from `vi`.
3. Add `Messages_en_US.properties` containing only the `unknown` key; verify `bundle.getString("unknown")` from `vi-VN` still throws.
4. Set different `Locale.getDefault()` values in an isolated test program and compare the default strategy with `getNoFallbackControl`; do not do this in a multi-threaded server request.

Interpret the results using **two separate questions**: "which bundle was selected?" and "at which level in the parent chain was the key found?".

## 14. Conclusion

**Finding a bundle** answers "does this resource family have a version suitable for the requested locale?". **Finding a key** answers "in the loaded bundle or its parent bundles, what is the closest value for this key?". Both phases may involve `vi_VN → vi → base`, yet a missing file and a missing key produce different behavior; keys in another language's bundle are not searched automatically.

When designing Java localization, keep application locales explicit, understand candidate/base/default-JVM fallback properly, check coverage per translation, and use `bundle.getLocale()` to diagnose the selected bundle rather than inferring the source of individual keys.

**References (Java 17):**

- [Oracle JDK 17 — `ResourceBundle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): `getBundle`, `getObject`, `getString`, `getLocale`, and bundle loading mechanism.
- [Oracle JDK 17 — `ResourceBundle.Control`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html): candidate locales, formats, and `getNoFallbackControl`.
