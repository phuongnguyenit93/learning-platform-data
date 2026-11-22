# Reading language, country, script, variant, and extensions of `Locale` in Java

## 1. Lesson Objectives

A `java.util.Locale` contains more than just “language” and “country”. It can include **language**, **country/region**, **script** (writing system), **variant**, and **extensions** (additional information, such as calendar type or numbering system). Reading these fields correctly helps a program choose language resources, represent locales in logs, display user-friendly names, and respect user preferences.

After this lesson, you should know how to:

- Distinguish `getLanguage()`, `getCountry()`, `getScript()`, and `getVariant()`.
- Read extensions via `getExtensionKeys()` and `getExtension(char)`.
- Read individual parts of the Unicode locale extension `u` using `getUnicodeLocaleAttributes()`, `getUnicodeLocaleKeys()`, and `getUnicodeLocaleType(String)`.
- Distinguish **empty string**, **`null`**, and **empty set** return values when a field is undeclared.
- Understand BCP 47 representation and how to create, validate, and store a `Locale` in Java 17+.

This lesson is about **reading `Locale` structure**. Do not treat these fields as proof of a transaction's actual address, nationality, time zone, or currency code.

## 2. Anatomy of a BCP 47 Language Tag

Java supports creating a `Locale` from a BCP 47 language tag, for example:

```text
en-Latn-US-posix-u-ca-japanese-nu-thai-x-demo
│  │    │  │     │ │           │       │
│  │    │  │     │ │           │       └── extension x, private use = demo
│  │    │  │     │ │           └────────── Unicode keyword nu = thai
│  │    │  │     │ └────────────────────── Unicode keyword ca = japanese
│  │    │  │     └──────────────────────── extension u
│  │    │  └────────────────────────────── variant = posix
│  │    └───────────────────────────────── country/region = US
│  └────────────────────────────────────── script = Latn
└───────────────────────────────────────── language = en
```

| Part | Example | Role |
| --- | --- | --- |
| Language | `en`, `vi`, `zh` | Selects the language; code is usually lowercase. |
| Script | `Latn`, `Cyrl`, `Hans`, `Hant` | Identifies the writing system; ISO 15924 code, usually title-cased. |
| Country/region | `US`, `VN`, `419` | Identifies the region; two letters or three digits per BCP 47. |
| Variant | `posix` | Specific variant per the tag's conventions. |
| Extension | `u-...`, `x-...` | Additional preferences and private-use section. |

Not every tag contains all five components. `"vi"` is a valid tag without a region, script, or extension; `"vi-VN"` declares a region but still does not declare a script. **An absent field means unspecified**, not that the user's script or region “does not exist”.

Parsing manually with `tag.split("-")` is very error-prone: script and country are optional, variant can have multiple subtags, and the `u` extension itself contains multiple keywords. Java provides getters to read this structure more safely.

## 3. Four Basic Getters

| API | Example Result for `en-Latn-US-posix` | Type | When Absent |
| --- | --- | --- | --- |
| `locale.getLanguage()` | `"en"` | `String` | `""` |
| `locale.getCountry()` | `"US"` | `String` | `""` |
| `locale.getScript()` | `"Latn"` | `String` | `""` |
| `locale.getVariant()` | `"posix"` | `String` | `""` |

Java returns **identifier codes** rather than natural names: `getLanguage()` is `"vi"`, while `getDisplayLanguage(Locale.ENGLISH)` can be used to obtain the English language name for the UI. Similarly, `getCountry()` returns the region code `"VN"`, unlike `getDisplayCountry(...)`.

### 3.1. Language — `getLanguage()`

`getLanguage()` reads the language code, typically an ISO 639 code per BCP 47 rules. The tags `en`, `en-US`, and `en-Latn-US` all have language `en`.

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale english = Locale.forLanguageTag("en-US");
System.out.println(vietnamese.getLanguage()); // vi
System.out.println(english.getLanguage());    // en
```

*This is an illustrative Java snippet inside a method, not a standalone program.*

`getLanguage()` only describes the language; it does not guarantee the application has translations for that language. `Locale.ROOT.getLanguage()` is `""`.

### 3.2. Country / Region — `getCountry()`

`getCountry()` reads the region code. It is commonly a two-letter code like `US` or `VN`, though per BCP 47 it can also be a three-digit region code such as `419`.

```java
Locale a = Locale.forLanguageTag("en-US");
Locale b = Locale.forLanguageTag("es-419");
System.out.println(a.getCountry()); // US
System.out.println(b.getCountry()); // 419
```

The tag `vi-US` has `getLanguage()` equal to `"vi"` and `getCountry()` equal to `"US"`; this combination only describes locale context. **Do not compute time zones from the country** (a single country can span multiple time zones), and do not alter the actual currency unit of data based on country. For money and time formatting, manage `Currency` and `ZoneId` according to separate requirements.

### 3.3. Script — `getScript()`

Script is an ISO 15924 writing system code, such as `Latn` (Latin), `Cyrl` (Cyrillic), `Hans` (Chinese Simplified), or `Hant` (Chinese Traditional). The same language can have multiple scripts.

| Tag | Language | Script | Country |
| --- | --- | --- | --- |
| `sr-Latn-RS` | `sr` | `Latn` | `RS` |
| `sr-Cyrl-RS` | `sr` | `Cyrl` | `RS` |
| `zh-Hans-CN` | `zh` | `Hans` | `CN` |
| `zh-Hant-TW` | `zh` | `Hant` | `TW` |
| `vi-VN` | `vi` | `""` | `VN` |

Relying solely on `getLanguage()` can pick the wrong writing system (for example Latin versus Cyrillic in `sr`). However, `getScript()` returns `""` when the tag does not specify a script; do not infer backward that the user's text has no script.

### 3.4. Variant — `getVariant()`

Variant describes a specific variant or convention, such as `posix` in `en-US-posix`:

```java
Locale locale = Locale.forLanguageTag("en-US-posix");
System.out.println(locale.getVariant()); // posix
```

In BCP 47, a variant subtag typically has 5–8 alphanumeric characters or exactly four characters starting with a digit; multiple variants may exist. Some `Locale` objects created via legacy Java constructors contain legacy variants with underscores. Therefore, do not split or concatenate variants manually when exchanging language tags. Use `toLanguageTag()` to export identifiers in BCP 47 syntax and `Locale.Builder` when per-component validation is needed.

Script describes the *writing system*, while variant describes a *variant*; they are not interchangeable. In typical applications, variant may be absent.

## 4. Extensions — Reading by Key

Beyond the four base components, a `Locale` can contain extensions. Each extension begins with a singleton key (a letter or digit), followed by subtags. Java provides:

- `getExtensionKeys()` — returns a `Set<Character>` of present keys, such as `['u', 'x']` if written as a list for readability.
- `getExtension('u')` — returns the entire content of extension `u` (excluding the `u-` prefix).
- `getExtension('x')` — returns the private-use portion after `x-`.
- `getExtension(key)` — returns `null` if the key is absent.

**Do not assume `Set` iteration order is fixed.** Use a `TreeSet` if you need to print keys in sorted order for testing or comparing results.

### 4.1. Unicode Locale Extension `u`

The tag `en-US-u-ca-japanese-nu-thai` contains two Unicode locale keywords:

- `ca=japanese`: Japanese calendar type.
- `nu=thai`: Thai numbering system.

For a `Locale` created from this tag:

```java
Locale locale =
        Locale.forLanguageTag("en-US-u-ca-japanese-nu-thai");

String rawExtension = locale.getExtension('u');
// "ca-japanese-nu-thai"

String calendar = locale.getUnicodeLocaleType("ca");
// "japanese"

String numbering = locale.getUnicodeLocaleType("nu");
// "thai"
```

Getters specialized for `u`:

| Getter | Effect | Example |
| --- | --- | --- |
| `getUnicodeLocaleKeys()` | Keyword keys inside extension `u` | `ca`, `nu` |
| `getUnicodeLocaleType("ca")` | Type of keyword `ca` | `japanese` |
| `getUnicodeLocaleType("nu")` | Type of keyword `nu` | `thai` |
| `getUnicodeLocaleAttributes()` | Unicode attributes inside extension `u` | `attr` in `en-u-attr-ca-gregory` |

**Attributes differ from keywords:** in `en-u-attr-ca-gregory`, `attr` is an attribute (no type), whereas `ca` is a keyword with type `gregory`. Accordingly, `getUnicodeLocaleAttributes()` contains `"attr"` and `getUnicodeLocaleType("ca")` returns `"gregory"`.

Extensions express preferences or context; they do not guarantee every Java formatter automatically applies all preferences. For example, `ca=japanese` does not automatically force every `DateTimeFormatter` to switch to the Japanese calendar; you must check the chronology used by the API and configure it explicitly when needed. Similarly, check actual locale data support before expecting digits formatted per `nu`.

### 4.2. Private-Use Extension `x`

`en-US-x-demo` has `getExtension('x')` equal to `"demo"`. `x` is reserved for private agreement and has no universal meaning understood identically by all Java applications. Do not interpret `x-demo` as a country, script, personal info, or built-in feature unless the system defines its own convention.

### 4.3. Absent Extensions

With `Locale.forLanguageTag("vi-VN")`:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
System.out.println(locale.getExtensionKeys().isEmpty()); // true
System.out.println(locale.getExtension('u') == null);    // true
System.out.println(locale.getUnicodeLocaleKeys().isEmpty()); // true
```

Key point to remember: when language/country/script/variant is missing, the getter returns `""`; when an extension/type is missing, the getter returns `null`; when keys/attributes are missing, the getter returns an **empty set**. Do not call `getExtension('u').isEmpty()` without handling the possibility of `null`.

## 5. Standalone Runnable Java 17+ Example Reading All Parts

Create the file **`LocalePartsDemo.java`** with the contents below. So that results can be compared deterministically, the example uses `TreeSet` when printing sets of keys and attributes.

```java
import java.util.Locale;
import java.util.TreeSet;

public class LocalePartsDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag(
                "en-Latn-US-posix-u-ca-japanese-nu-thai-x-demo");

        System.out.println("tag=" + locale.toLanguageTag());
        System.out.println("language=" + locale.getLanguage());
        System.out.println("country=" + locale.getCountry());
        System.out.println("script=" + locale.getScript());
        System.out.println("variant=" + locale.getVariant());

        System.out.println("extensionKeys="
                + new TreeSet<>(locale.getExtensionKeys()));
        System.out.println("extension_u=" + locale.getExtension('u'));
        System.out.println("extension_x=" + locale.getExtension('x'));
        System.out.println("unicodeKeys="
                + new TreeSet<>(locale.getUnicodeLocaleKeys()));
        System.out.println("calendar="
                + locale.getUnicodeLocaleType("ca"));
        System.out.println("numbering="
                + locale.getUnicodeLocaleType("nu"));

        Locale attributes = Locale.forLanguageTag(
                "en-u-attr-ca-gregory");
        System.out.println("attributes="
                + new TreeSet<>(attributes.getUnicodeLocaleAttributes()));

        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        System.out.println("missingScriptIsEmpty="
                + vietnamese.getScript().isEmpty());
        System.out.println("missingExtensionIsNull="
                + (vietnamese.getExtension('u') == null));
    }
}
```

Using JDK 17 or newer, run in the directory containing the file:

```bash
javac -encoding UTF-8 LocalePartsDemo.java
java LocalePartsDemo
```

**Exact output:**

```text
tag=en-Latn-US-posix-u-ca-japanese-nu-thai-x-demo
language=en
country=US
script=Latn
variant=posix
extensionKeys=[u, x]
extension_u=ca-japanese-nu-thai
extension_x=demo
unicodeKeys=[ca, nu]
calendar=japanese
numbering=thai
attributes=[attr]
missingScriptIsEmpty=true
missingExtensionIsNull=true
```

### Explaining the Output

1. `getLanguage()` only returns `en`, not the entire language tag; `getScript()` returns `Latn`, and `getCountry()` returns `US`.
2. `getVariant()` is `posix`; extension information does not leak into variant.
3. `getExtensionKeys()` returns the singletons `u` and `x`; it does not directly return the Unicode keywords `ca` or `nu`.
4. `getExtension('u')` returns `ca-japanese-nu-thai`, without the `u-` prefix; `getExtension('x')` returns `demo`, without `x-`.
5. `getUnicodeLocaleKeys()` returns `ca` and `nu`; each specific value is retrieved via `getUnicodeLocaleType(...)`.
6. `getUnicodeLocaleAttributes()` for `en-u-attr-ca-gregory` returns the attribute `attr`, not the keyword `ca`.
7. Locale `vi-VN` contains no script or extensions, so both `isEmpty()` for script and `== null` for the extension evaluate to `true`.

This example only reads and prints structural information. It does not call `Locale.setDefault(...)`, so it does not alter the shared JVM default locale.

## 6. Creating a Locale Properly So Getters Have Meaning

### `Locale.forLanguageTag(...)`

This is a convenient API for reading identifiers stored or transmitted across system boundaries:

```java
Locale locale = Locale.forLanguageTag("zh-Hant-TW");
System.out.println(locale.getLanguage()); // zh
System.out.println(locale.getScript());   // Hant
System.out.println(locale.getCountry());  // TW
```

`forLanguageTag` may handle malformed input leniently, such as stopping at an invalid subtag rather than always throwing an error. Therefore, **being able to create an object does not mean the input is valid or that the locale is supported by the application**. At request boundaries, validate syntax and check the product's supported locale list if that is a system requirement.

### `Locale.Builder`

When individual components are available, use Builder to attach them explicitly and validate syntax more strictly:

```java
Locale custom = new Locale.Builder()
        .setLanguage("en")
        .setScript("Latn")
        .setRegion("US")
        .setVariant("posix")
        .setUnicodeLocaleKeyword("ca", "japanese")
        .setUnicodeLocaleKeyword("nu", "thai")
        .setExtension('x', "demo")
        .build();

System.out.println(custom.toLanguageTag());
// en-Latn-US-posix-u-ca-japanese-nu-thai-x-demo
```

The snippets in this section are illustrative code placed inside a Java method. `Locale.Builder` may throw `IllformedLocaleException` if values are syntactically invalid, though it does not check whether the application has translations for the locale.

When exchanging identifiers between systems, use `toLanguageTag()` instead of `toString()`. `Locale.toString()` uses Java's legacy representation and is not a standard BCP 47 code for passing across APIs. When human-readable names are needed, methods such as `getDisplayLanguage(...)`, `getDisplayScript(...)`, `getDisplayCountry(...)`, or `getDisplayName(...)` take another display locale to describe components, rather than using technical code getters as UI labels.

## 7. Common Mistakes and How to Avoid Them

| Mistake | Why It Is Incorrect | Better Approach |
| --- | --- | --- |
| Using `split("-")` and reading fixed positions | Script, region, and variant are all optional; extensions consist of multiple subtags. | Use `Locale` getters. |
| Treating `getCountry()` as a country name | It returns a region code, such as `VN`, `US`, or `419`. | Use `getDisplayCountry(displayLocale)` for display. |
| Comparing only language for all translations | Script can distinguish Latin, Cyrillic, Simplified, or Traditional forms. | Consider language + script + region when selecting supported locales. |
| Assuming country is always two letters | BCP 47 allows three-digit numeric region codes. | Do not enforce a two-letter regex for all cases. |
| Treating missing script as an error | Many valid language tags do not declare a script. | Check `getScript().isEmpty()`. |
| Calling `getExtension('u').isEmpty()` | When no extension exists, the getter returns `null`. | Check for `null` first. |
| Confusing Unicode keys with extension keys | `u` is the extension key; `ca` and `nu` are keywords inside it. | Use `getUnicodeLocaleKeys()` and `getUnicodeLocaleType(...)`. |
| Believing `ca=japanese` automatically changes all date formats | Formatters/chronologies may have their own rules. | Check the formatting API being used. |
| Believing a locale parsed from input means translations exist | `Locale` only describes an identifier, not product resources. | Check the application's supported locales and fallback. |
| Changing `Locale.setDefault(...)` per request | Default locale is JVM-wide shared state and can affect concurrent users. | Pass `Locale` explicitly per request. |

## 8. Self-Practice to Confirm Mastery

**Exercise 1.** For `vi-VN`, `sr-Latn-RS`, and `zh-Hant-TW`, write a function printing `getLanguage()`, `getCountry()`, `getScript()`, and `getVariant()`. Point out which fields return `""`. Why should `sr-Latn-RS` and `sr-Cyrl-RS` not be treated as identical if the product has script-specific translations?

**Exercise 2.** Parse `en-u-attr-ca-gregory-nu-latn` using `getExtension('u')`, `getUnicodeLocaleAttributes()`, `getUnicodeLocaleKeys()`, and `getUnicodeLocaleType(...)`. The output should show attribute `attr`, and keywords `ca=gregory` and `nu=latn`. Print `Set`s using `TreeSet` so the order is predictable.

**Exercise 3.** Create the same locale using `Locale.Builder` and `Locale.forLanguageTag(...)`. Check `toLanguageTag()` and `equals(...)`. Try a syntactically invalid subtag and observe how the lenient parser differs from Builder's strict checking.

**Exercise 4.** Write a method that accepts a `Locale` and returns data containing language, region, script, variant, and Unicode keywords, while properly handling empty/null fields and **without fabricating fake default values**. When the whole locale needs to be serialized, use `toLanguageTag()`.

**Completion criteria:** able to explain each getter's meaning and return type when data is absent; able to read extension `u` with attributes/keywords and section `x`; know how to create locales from language tags or Builder; and avoid confusing language codes with display names, time zones, or the application's actual translation choices.