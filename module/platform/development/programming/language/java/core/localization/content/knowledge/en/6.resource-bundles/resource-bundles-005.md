# ResourceBundle.getString, getObject, getStringArray, and Resource Types

## 1. The Problem to Solve

A multilingual application must not only find the right resource by `Locale`, it must also **read data with the right type**. For example, a screen might need:

- A greeting message: `"Xin chào"` — a `String` value.
- Multiple menu labels: `["Mở", "Lưu"]` — a `String[]` value.
- A UI configuration parameter: `3` — an `Integer` value.
- Another application-defined object, if there is a genuine reason to treat it as a localized resource.

Java provides three methods on `java.util.ResourceBundle`:

```java
String getString(String key);
String[] getStringArray(String key);
Object getObject(String key);
```

All three search by **`String` key** in the current bundle and the **parent bundle** hierarchy. The crucial difference lies in the return type and the possibility of cast errors.

This lesson explains resource types, how to retrieve data with each method, the differences between `PropertyResourceBundle` and `ListResourceBundle`, key fallback, exceptions, and how to design runnable examples with Java 17+.

## 2. What Does ResourceBundle Store and How Is It Looked Up?

`ResourceBundle` is an abstract class representing a set of `key → value` pairs selected by a base name and a `Locale`. A bundle family might have members such as:

```text
Messages          ← root bundle
Messages_vi       ← Vietnamese
Messages_en       ← English
Messages_en_US    ← US English
```

A typical load call:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);
```

In this example Java searches for an appropriate bundle using candidate locales for `vi-VN`, potentially selecting `Messages_vi` when `Messages_vi_VN` does not exist. If a key is missing in the Vietnamese bundle, the resource lookup can search in **parents** such as `Messages`. This is part of the fallback mechanism to avoid repeating every key in every localization.

Distinguish two operations:

1. **Selecting a bundle** via `ResourceBundle.getBundle(baseName, locale)`: uses candidate strategy, default locale, and base bundle. Which candidate is selected depends on existing bundles, `Control`/providers, and the environment.
2. **Looking up a key** via `getString`, `getStringArray`, or `getObject` on the selected bundle: checks the current bundle, then parents until a value is found.

Do not assume "missing translation" means returning an empty string, `null`, or English automatically. If **no suitable bundle** exists, `getBundle` can throw `MissingResourceException`; if **no key** exists in the bundle/parent chain, the getters also throw `MissingResourceException`.

### Keys and Values Are Different

- A **key** must be a `String` and is case-sensitive: `"welcome"` differs from `"Welcome"`.
- A **value** in a `ResourceBundle` in general can be an `Object`; the **actual runtime value type** depends on the bundle format and how the bundle was created.
- The three getters are methods on `ResourceBundle`; they **do not automatically convert** numbers to strings, CSV strings to arrays, or objects to translations.

## 3. Comparing the Three Methods

| Method | Return Type | Appropriate When | What to Remember |
| --- | --- | --- | --- |
| `getString("key")` | `String` | Messages, titles, labels, formatter patterns | Actual value must be a `String` |
| `getStringArray("key")` | `String[]` | A resource is truly an array of strings | Actual value must be a **`String[]`**, not a comma-separated string |
| `getObject("key")` | `Object` | Value has a type other than `String`/`String[]` or requires dynamic handling | Caller must check/cast to the right type |

Conceptually, the two specialized methods are equivalent to casting:

```java
String text = (String) bundle.getObject("welcome");
String[] menu = (String[]) bundle.getObject("menu");
```

Therefore:

- `getString("welcome")` succeeds if the actual value is a `String`.
- `getStringArray("menu")` succeeds if the actual value is a `String[]`.
- `getObject("menu")` still returns an `Object` whose runtime type is `String[]`.
- `getString("maxAttempts")` does not call `toString()` on an integer; it throws `ClassCastException`.
- `getStringArray("menu")` does not parse `"Home,Settings"` or `"Mở|Lưu"`; that string remains a `String` and casting to `String[]` fails.

Both `getString` and `getStringArray` are `final` on `ResourceBundle`. When developing custom bundles, implement data retrieval through the subclass's dedicated API (such as `getContents` on `ListResourceBundle`), rather than overriding these getters.

## 4. Resource Type Depends on the Bundle Source

### 4.1. `PropertyResourceBundle`: Every Value Is a `String`

With a `.properties`-file bundle such as **`messages_vi.properties`**:

```properties
welcome=Xin chào
button.save=Lưu
button.cancel=Hủy
menu=Mở,Lưu
maxAttempts=3
```

`PropertyResourceBundle` loads all of these values as **`String`**:

| Key | Java Type When Read | Value |
| --- | --- | --- |
| `welcome` | `String` | `"Xin chào"` |
| `button.save` | `String` | `"Lưu"` |
| `menu` | `String` | `"Mở,Lưu"`, still a single string |
| `maxAttempts` | `String` | `"3"`, not `Integer` |

Example:

```java
ResourceBundle b = ResourceBundle.getBundle(
        "messages", Locale.forLanguageTag("vi"));

String welcome = b.getString("welcome");
String menu = b.getString("menu");
String attempts = b.getString("maxAttempts");
int number = Integer.parseInt(attempts);
```

This is a **snippet**; it requires `import java.util.Locale;` and `import java.util.ResourceBundle;` along with the properties file on the classpath. `Integer.parseInt` is an **explicit type-conversion step in application code** and can throw `NumberFormatException` if the data is not a valid integer.

**Do not call `b.getStringArray("menu")` here**: because `"Mở,Lưu"` is a `String`, the call will throw `ClassCastException`. If you need a set of labels from properties files, it is usually better to store them as **separate independent keys** (`menu.open`, `menu.save`) so each string is translated in proper context. Use `split(",")` only when the application explicitly defines a delimited data format with escaping rules, handling for commas inside text, and clear validation.

In Java 9+, `ResourceBundle` can read properties using UTF-8 with compatibility handling; ensure consistent encoding between files and build tools. For Java 17+ examples, save files as UTF-8.

### 4.2. `ListResourceBundle`: Values Can Be `Object`

`ListResourceBundle` is a subclass of `ResourceBundle`. Each bundle class provides `Object[][]` pairs via `protected Object[][] getContents()`. Keys must still be `String`, while values can be:

```java
{"welcome", "Welcome"}               // String
{"menu", new String[] {"Open", "Save"}}  // String[]
{"maxAttempts", Integer.valueOf(3)}    // Integer
```

Not every object makes sense to localize. Most UI messages only need `String`; `String[]` is useful for a set of options genuinely belonging to one resource; structured objects are appropriate only when developers control their definition, data type, and lifecycle.

**Design considerations:**

- Values in `ListResourceBundle` can be a true `String[]`, giving `getStringArray` a valid basis to work.
- Choose the getter by **runtime type**, not by key name. A key named `"count"` does not turn its value into a number.
- Do not return a mutable object and mutate it from multiple threads. `ResourceBundle` instances are reused/cached; an array or object obtained from `getObject` may be shared. If you need to modify an array, copy it: `bundle.getStringArray("menu").clone()`.
- If one translation uses `String` and another uses `String[]` for the **same key**, code will work only for some locales. Maintain a **consistent type contract** across all bundles in the same family.

### 4.3. Extensible Resource Sources

`ResourceBundle` can also be implemented via custom subclasses/providers. `getObject` still returns `Object`; actual types depend on the implementation. Never assume a value will automatically convert to the desired type. `PropertyResourceBundle`, `ListResourceBundle`, and custom loaders should follow a documented and tested contract.

## 5. Runnable Java 17+ Example: `String`, `String[]`, and `Integer`

Create three Java files in the **same directory**, in the **default package** (no `package` declaration). No `.properties` files are needed in this example.

**File `Messages.java`** — default resource:

```java
import java.util.ListResourceBundle;

public class Messages extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"welcome", "Welcome"},
                {"menu", new String[] {"Open", "Save"}},
                {"maxAttempts", Integer.valueOf(3)}
        };
    }
}
```

**File `Messages_vi.java`** — Vietnamese translation overriding only two keys:

```java
import java.util.ListResourceBundle;

public class Messages_vi extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"welcome", "Xin chào"},
                {"menu", new String[] {"Mở", "Lưu"}}
        };
    }
}
```

**File `BundleTypesDemo.java`** — reading resource types and handling exceptions:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class BundleTypesDemo {
    public static void main(String[] args) {
        ResourceBundle bundle = ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("vi-VN"));

        String welcome = bundle.getString("welcome");
        String[] menu = bundle.getStringArray("menu");
        Object rawMenu = bundle.getObject("menu");
        Object rawLimit = bundle.getObject("maxAttempts");

        System.out.println("Bundle locale: " + bundle.getLocale().toLanguageTag());
        System.out.println("getString: " + welcome);
        System.out.println("getStringArray: " + Arrays.toString(menu));
        System.out.println("getObject menu is String[]: " + (rawMenu instanceof String[]));
        System.out.println("getObject maxAttempts: " + rawLimit);
        System.out.println("maxAttempts type: " + rawLimit.getClass().getSimpleName());
        System.out.println("parent key exists: " + bundle.containsKey("maxAttempts"));

        try {
            bundle.getString("maxAttempts"); // Integer, not String
        } catch (ClassCastException e) {
            System.out.println("wrong getString: " + e.getClass().getSimpleName());
        }

        try {
            bundle.getStringArray("welcome"); // String, not String[]
        } catch (ClassCastException e) {
            System.out.println("wrong getStringArray: " + e.getClass().getSimpleName());
        }

        try {
            bundle.getObject("does.not.exist");
        } catch (MissingResourceException e) {
            System.out.println("missing key: " + e.getClass().getSimpleName());
        }
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac -encoding UTF-8 Messages.java Messages_vi.java BundleTypesDemo.java
java BundleTypesDemo
```

**Expected stdout:**

```text
Bundle locale: vi
getString: Xin chào
getStringArray: [Mở, Lưu]
getObject menu is String[]: true
getObject maxAttempts: 3
maxAttempts type: Integer
parent key exists: true
wrong getString: ClassCastException
wrong getStringArray: ClassCastException
missing key: MissingResourceException
```

Explanation:

1. `getBundle("Messages", vi-VN)` finds no `Messages_vi_VN` class, so it loads `Messages_vi`; the selected bundle's `getLocale()` is `vi`.
2. `getString("welcome")` reads the Vietnamese string from `Messages_vi`.
3. `getStringArray("menu")` returns the `String[]` array defined by `Messages_vi`. `Arrays.toString` is only used to print the array readably.
4. `getObject("menu")` returns an object whose runtime type is `String[]`; the `instanceof` check yields `true`.
5. `Messages_vi` lacks key `maxAttempts`, so `getObject("maxAttempts")` checks parent `Messages` and receives `Integer(3)`. `containsKey` checks the parent as well.
6. The two calls using the **wrong getter type** throw `ClassCastException`, while the missing key throws `MissingResourceException`. The exceptions are caught solely for demonstration; do not swallow all such errors in real applications.

**Run note:** the three public classes must be saved with matching filenames and on the same classpath. Avoid having `Messages.properties` or `Messages_vi.properties` with the same name in the directory, as they can complicate explaining which bundle gets selected if the environment differs from the example. All files use UTF-8 so Vietnamese characters display properly; the console must use a compatible encoding.

## 6. Exceptions and Proper Handling

| Situation | Exception / Result | Reason |
| --- | --- | --- |
| `getString("unknown")`, key absent in bundle and parent | `MissingResourceException` | Key not found |
| `getObject("unknown")`, key absent in bundle and parent | `MissingResourceException` | `getObject` does not return `null` when a key is missing |
| `getStringArray("unknown")` | `MissingResourceException` | Missing key, checked before type check |
| `getString("maxAttempts")` when value is `Integer` | `ClassCastException` | Cannot cast to `String` |
| `getStringArray("welcome")` when value is `String` | `ClassCastException` | Cannot cast to `String[]` |
| `getStringArray("menu")` when value is `Object[]` of strings | `ClassCastException` | Runtime array type is `Object[]`, not `String[]` |
| `getString(null)`, `getObject(null)`, or `getStringArray(null)` | `NullPointerException` | Key cannot be `null` |
| `getBundle("missingFamily", locale)` with no valid bundle | `MissingResourceException` | No bundle available from which to read keys |

**Do not catch `ClassCastException` to return an empty message and hide resource bugs.** For application-owned bundles, this is usually a configuration bug or broken type contract, so it should be caught early in tests and logged with base bundle name, key, locale, and expected type.

For a **truly optional** key, you can check `containsKey` first and then apply an application-defined default. However, `containsKey` does not check types; a key may exist with the wrong type.

Example when using only `getObject` without guaranteed value types:

```java
Object item = bundle.getObject("menu");

if (item instanceof String[] items) {
    for (String label : items) {
        System.out.println(label);
    }
} else {
    throw new IllegalStateException("Resource menu must be String[]");
}
```

This is a **snippet** using an already-created `bundle` variable; `instanceof String[] items` is pattern matching available in Java 17. Do not cast directly from `Object` without checking when data could be supplied by another provider.

## 7. Resource Types: Common Pitfalls When Migrating Between `.properties` and Java

Compare two values that look similar:

**In `labels.properties`:**

```properties
choices=Yes,No
```

**In `ListResourceBundle`:**

```java
{"choices", new String[] {"Yes", "No"}}
```

Both might be rendered like "Yes,No", yet their Java types are completely different:

| Source | `getObject("choices")` | `getString("choices")` | `getStringArray("choices")` |
| --- | --- | --- | --- |
| `PropertyResourceBundle` | `String` | Succeeds | `ClassCastException` |
| `ListResourceBundle` with `new String[]` | `String[]` | `ClassCastException` | Succeeds |
| `ListResourceBundle` with `new Object[] {"Yes", "No"}` | `Object[]` | `ClassCastException` | `ClassCastException` |

Therefore, **changing the storage format** from properties files to Java classes can accidentally break the type contract. When refactoring, test all keys and getters used by callers. Never infer a type from how a value prints on screen.

If you just need to display two independent labels, a cleaner design is:

```properties
choice.yes=Yes
choice.no=No
```

Then call `getString("choice.yes")` and `getString("choice.no")`. For long lists whose contents vary across locales, consider whether order, item count, and option IDs are business data; retrieving display labels from translations should preserve **business identifiers** when a user selects an option.

## 8. Key Fallback Does Not Mean Fallback on Type Mismatch

Suppose parent `Messages` contains:

```java
{"retryLabel", "Retry"}
```

While `Messages_vi` contains:

```java
{"retryLabel", new String[] {"Thử lại"}}
```

Calling `bundle.getString("retryLabel")` on the Vietnamese bundle finds the key in the child bundle and then **casts the child's value** to `String`. Because the key already has a value there, the method **does not skip it to fall back to `"Retry"` in the parent**. The result is `ClassCastException`. Key fallback resolves **absent keys**, not **wrongly typed values**.

Thus, to manage contracts across languages:

1. For any key, define a **consistent value type** across all locales.
2. Use clear naming conventions, such as `message.login.success` (string) and `navigation.labels` (array if truly needed).
3. Write tests accessing all essential keys in every supported locale, rather than only testing that the bundle loads.
4. If missing keys are permitted, clearly identify which parent they inherit from and verify that the post-fallback wording still fits the context.
5. When strong typing is needed for a resource set, consider a wrapper with methods like `requireText(key)` and `requireTextArray(key)` that include key name and locale in error messages.

Note that `getObject` is `final` on `ResourceBundle` and performs lookup via `handleGetObject` on subclasses, then parents if needed. It does not auto-fix type errors and does not automatically coerce `Integer` to `String`.

## 9. `ResourceBundle` and Separating Data from the Application

In large applications, choose resource types by purpose:

- **UI messages:** use `String` and `getString`; if dynamic arguments `{0}`, `{1}` are present, process them with `MessageFormat` using the appropriate locale. Do not concatenate message fragments in English word order.
- **Fixed label groups:** `String[]` and `getStringArray` in `ListResourceBundle` can be used, provided order and type stay identical across all locales; multiple clearly named keys are often easier to maintain.
- **Structured data or business configuration:** place in a proper configuration/schema system if it is not truly localized content. `getObject` can read objects, but it performs no schema validation and does not replace proper validation logic.
- **Standard internationalization rules:** dates, numbers, and currencies should go through dedicated formatters (`DateTimeFormatter`, `NumberFormat`) rather than hardcoding region formatting rules inside bundles.

Do not place references to sensitive data, tokens, or secrets in translation resources. Resource values may be packaged, inspected, or served in many places; access to translation strings is not a secret-protection mechanism.

### Performance and Lifecycle Considerations

`ResourceBundle.getBundle` uses caching. There is no need to reload per key; obtain the bundle for a locale and reuse it within the appropriate processing scope. With `ListResourceBundle`, objects/arrays stored in the bundle may be shared. `getStringArray` does not promise a fresh array per call; do not mutate the returned array unless you have cloned it. Hot-updating resources at runtime is a separate lifecycle/caching problem and cannot be solved by switching from `getString` to `getObject`.

Do not call `Locale.setDefault(...)` per request to pick a bundle. In multithreaded services, pass the request's `Locale` to `getBundle` and formatters; mutating the JVM default affects concurrent processing.

## 10. Testing Checklist

Test across multiple locales and source types, especially when migrating between `.properties` and `ListResourceBundle`:

| Check | Expected Outcome |
| --- | --- |
| `String` key in a specific locale | `getString` returns the exact translated text |
| `String[]` key | `getStringArray` preserves element count and order |
| `Integer` or other object key | `getObject` returns expected runtime type; caller casts safely |
| Key present only in root bundle | Accessible via parent; value still has right type |
| Key present in child bundle with wrong type | `ClassCastException`, no silent fallback to parent |
| Key completely absent | `MissingResourceException`, handled per product policy |
| `null` key | `NullPointerException` |
| `.properties` file containing `"a,b"` | Remains a `String`, not `String[]` |
| Two locales declare same key with different types | Caught by resource contract tests |
| Bundle contains mutable array/object | API consumers do not mutate shared state |
| Vietnamese resource files | Unicode diacritics render accurately without encoding corruption |
| Translation inherited from parent | Wording after fallback remains contextually and linguistically appropriate |

Distinguish API testing from content testing: a bundle with complete keys and right types can still hold contextually wrong text, wrong plurals, or awkward phrasing. Those issues must be caught via linguistic review and actual UI inspection.

## 11. Self-Check Questions

**Question 1.** Does `getString("count")` return `"3"` if the value of key `count` in `ListResourceBundle` is `Integer.valueOf(3)`?

**Answer:** No. `getString` requires a `String` value; an integer triggers `ClassCastException`. To format a number, retrieve it with `getObject`, verify its type, and format as required.

**Question 2.** A `messages.properties` file contains `colors=red,green,blue`. Will calling `getStringArray("colors")` return three elements?

**Answer:** No. `PropertyResourceBundle` reads the value as a single `String`. `getStringArray` requires runtime type `String[]`, so it throws `ClassCastException`.

**Question 3.** Why can the Vietnamese translation read key `maxAttempts` declared only in the root bundle?

**Answer:** When looking up a key in the child bundle does not find it, `ResourceBundle.getObject` queries the parent. Both `getString` and `getStringArray` benefit from this mechanism because they read through `getObject`.

**Question 4.** The parent has a `String` for a key, while the child bundle declares the same key as `String[]`. Does `getString` automatically fall back to the parent?

**Answer:** No. The key already exists in the child bundle; the cast fails with `ClassCastException`. Only absent keys trigger parent lookup.

**Question 5.** When a key does not exist in either the bundle or its parents, what does `getObject` return?

**Answer:** It throws `MissingResourceException`, rather than returning `null`.

**Question 6.** If you need to modify a list of labels obtained from `getStringArray`, how do you do so safely?

**Answer:** Copy it first using `clone()` or `Arrays.copyOf(...)`; avoid mutating the array held by the bundle directly because it may be cached and shared.

## 12. Key Takeaways

- `getString` retrieves **`String`**, `getStringArray` retrieves **`String[]`**, and `getObject` retrieves **`Object`**. Choose the getter matching the **actual value type**.
- `PropertyResourceBundle` normally stores all values as strings; `ListResourceBundle` allows providing arrays and Java objects.
- **Missing keys** cause `MissingResourceException`, **wrong types** cause `ClassCastException`, and **`null` keys** cause `NullPointerException`.
- Parent bundles support fallback when a **key is absent**, not when an existing key has the wrong type.
- The type contract must stay consistent across locales; test fallback, data types, Unicode, and missing-key behavior before release.

Official documentation references:

- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Java SE 21 — ListResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ListResourceBundle.html)
