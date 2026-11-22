# @Deprecated in Java: since, forRemoval, and the Javadoc @deprecated Tag

When a Java API is no longer recommended for use, the library author needs to inform callers **which API is obsolete, from which version it was marked, whether it is intended to be removed, and which API to migrate to**. Java supports this with the `@Deprecated` annotation and the `@deprecated` Javadoc tag.

The two mechanisms complement each other:

- `@Deprecated` is a **Java annotation** attached to a declaration, providing metadata for the compiler and tools to recognize; since Java 9, it has two elements, `since` and `forRemoval`.
- `@deprecated` is a **tag placed inside a Javadoc `/** ... */` block**, used to explain the reason and migration path. It is not a Java annotation.

Most deprecated APIs **still exist and remain callable** in the current version. Deprecation is a signal to consider migrating, not an instruction that automatically disables a method.

## 1. What Does @Deprecated Communicate?

The standard `java.lang.Deprecated` annotation has existed since Java 5; starting in Java 9, it supports:

```java
@Deprecated(since = "2.1", forRemoval = true)
public void oldOperation() {
    // Legacy API
}
```

This is a **method illustration snippet**, which must be placed inside an appropriate class if you want to compile it. Meaning:

- `since = "2.1"`: the API author indicates that the element **began being marked deprecated in version 2.1**. For custom-built libraries, this can be the library version, not necessarily the JDK version.
- `forRemoval = true`: the author **intends to remove the API in a future version**. Consumers should prioritize migrating.
- If `forRemoval` is omitted, the default value is `false`. If `since` is omitted, the default value is the empty string `""`.

The `since` information helps trace history; `forRemoval` helps assess the urgency of migration. Neither attribute removes the method itself or sets a removal date.

### Case-by-Case Interpretation Table

| Declaration | `since()` | `forRemoval()` | Interpretation |
| --- | --- | --- | --- |
| `@Deprecated` | `""` | `false` | Deprecated without specifying a starting version; no intent to remove declared at the time of marking |
| `@Deprecated(since = "2.0")` | `"2.0"` | `false` | Deprecated since 2.0; usage should be discontinued |
| `@Deprecated(forRemoval = true)` | `""` | `true` | Intended for removal without recording the version in which it was marked |
| `@Deprecated(since = "3.0", forRemoval = true)` | `"3.0"` | `true` | Deprecated since 3.0 and planned for later removal |

`false` **does not guarantee that the API will exist forever**. It only indicates that at the time of declaration there was no specific intent to remove it. The library's policy may change in later releases, and users should still look for a replacement.

## 2. since Is the Version Deprecation Began, Not the Version the API Was Created

Two milestones are very easy to confuse:

- **Introduced**: When did the API first appear?
- **Deprecated**: From which version did the author begin advising against using it?

For example, a method released in version 1.0, but only deprecated in version 2.4:

```java
/**
 * Generates an identifier in the legacy format.
 *
 * @since 1.0
 * @deprecated Since version 2.4, use {@link #newId()}.
 */
@Deprecated(since = "2.4")
public String oldId() {
    return "OLD-01";
}

public String newId() {
    return "NEW-01";
}
```

This is a **method illustration snippet** belonging to the same class; the two methods are used together. In the example:

- `@since 1.0` is a **Javadoc tag**: the API was introduced in 1.0.
- `@Deprecated(since = "2.4")` is **annotation metadata**: the API began being deprecated in 2.4.
- `@deprecated ...` explains how to switch to `newId()`.

Both `@since` and `@deprecated` are written inside the Javadoc comment. They are completely different from `since()` on the `@Deprecated` annotation.

`since` is version-descriptive data (of type `String`); Java does not automatically compare it against the running JDK version, nor does it enforce a migration deadline. When maintaining a library, standardize on a versioning convention and record the exact release version in which the deprecated status first appeared.

### Relation to Java Versions

`@Deprecated` has existed since Java 5, but **the two attributes `since` and `forRemoval` were only added in Java 9**. If you must compile with JDK 8, the syntax `@Deprecated(since = "9")` is invalid because the annotation definition in Java 8 does not yet have that element. For the learning examples below, use JDK 17 or later.

## 3. forRemoval: Distinguishing Ordinary Deprecation from Deprecation for Removal

`forRemoval` is a `boolean`. It determines how the compiler categorizes warnings when other code uses a deprecated element:

| Status | Terminology | Warning from `javac` |
| --- | --- | --- |
| `forRemoval = false` | Ordinary deprecation | `deprecation` |
| `forRemoval = true` | Terminal deprecation / deprecated for removal | `removal` |

With Java 17+, when code calls an API with `forRemoval = true`, `javac` typically displays a `[removal]` warning even in default mode because the `-Xlint:removal` category is enabled by default. With ordinary deprecation, a basic compilation command may only display a summary note; use `-Xlint:deprecation` to see details at the call site.

Useful commands:

```bash
javac -Xlint:deprecation -Xlint:removal Consumer.java
javac -Xlint:-deprecation Consumer.java
javac -Xlint:-removal Consumer.java
```

The commands above are **syntax to illustrate compiler options**; a `Consumer.java` file containing a corresponding program is required to run them. You can use the two lint-enabling flags independently in a single compilation. You should not disable warnings across an entire project just because you have not had time to migrate.

### true Does Not Mean “Remove Immediately”

Consider `@Deprecated(since = "3.0", forRemoval = true)`. Java does not schedule the API for removal in version 3.1, 4.0, or on any fixed date. It only communicates the maintainer's **intent**. In the currently running version, the method can still exist and function normally.

When the API is actually removed in a new library version:

- Source code calling the old API may fail to compile because the corresponding class or method no longer exists.
- Previously compiled bytecode may fail when linking or running against the new library version, for example with `NoSuchMethodError`, depending on the specific change.
- Annotations and Javadoc do not automatically migrate old calls to the new API.

Therefore, removal warnings should be addressed earlier than ordinary deprecation warnings, especially in foundational library code reused by multiple modules.

## 4. Relationship Between the @Deprecated Annotation and the @deprecated Javadoc Tag

The two lines look almost identical in spelling, yet they belong to **two different processing layers**:

```java
/**
 * Processes using the old algorithm.
 *
 * @deprecated Use {@link #modern()} because the new algorithm is clearer.
 */
@Deprecated(since = "2.0", forRemoval = false)
public String legacy() {
    return "legacy";
}

public String modern() {
    return "modern";
}
```

These are **two illustration methods in the same class**, not a standalone Java file.

**The `@Deprecated` annotation:**

- Has an uppercase `D`; sits outside Javadoc, before the declaration.
- Recorded as Java annotation metadata; `@Deprecated` has `RUNTIME` retention.
- Allows `javac`, IDEs, reflection, and analysis tools to know the deprecated status, including `since` and `forRemoval`.
- Does not contain domain explanations or specific replacement guidance.

**The `@deprecated` Javadoc tag:**

- Has a lowercase `d`; is solely a special tag inside a `/** ... */` block.
- Provides the **reason**, impact, replacement API, and migration notes for documentation readers.
- Used by `javadoc` when generating HTML documentation, typically highlighted in the description of the deprecated element.
- Not an annotation type; does not have the `since()` and `forRemoval()` elements and cannot be retrieved via `getAnnotation()`.

**Convention to follow: declare a deprecated API with both.** If `@Deprecated` is present without Javadoc `@deprecated`, tools will still detect the deprecation, but users may not know what to replace it with. If `@deprecated` is in Javadoc without the annotation, modern `javac` may emit a `[dep-ann]` warning because the documentation and metadata are inconsistent.

One should not say that the Javadoc tag alone is “completely invisible to the compiler”: some tools, including `javac`, also inspect doc comment contents to emit consistency warnings. However, **Java's standard mechanism for marking deprecation and providing `since/forRemoval` values remains the annotation**.

### Example Comparing Four Cases

| Declaration | Compiler / Tools | Documentation for Readers |
| --- | --- | --- |
| Only `// deprecated` | Just an ordinary comment; does not mark as deprecated | Does not generate a deprecation tag |
| Only Javadoc `@deprecated` tag | A `dep-ann` warning may appear due to the missing annotation | Includes notice/reason in the documentation |
| Only `@Deprecated` annotation | Has deprecated metadata and corresponding usage warnings | Lacks replacement explanation in the documentation tag |
| Both present | Metadata and warnings are defined by the annotation | Includes reason, guidance, and new API in Javadoc |

### Writing a Good @deprecated Notice

The Javadoc tag should answer:

1. **Why is it deprecated?** Unsafe, inaccurate, ambiguous behavior, superseded by a new API, or architectural change?
2. **What replaces it?** Point to the new method/class using `{@link ...}` where applicable.
3. **Are there behavioral differences?** Unit changes, `null` handling, data formatting, exceptions, or state.
4. **When is migration needed?** You may state the library's policy and removal warning, but do not promise a removal version unless a plan has been announced.

An example better than the vague description “Do not use”:

```java
/**
 * Returns the duration value in seconds, rounded down.
 *
 * @deprecated Since 2.5, use {@link #durationMillis()} to avoid
 *             precision loss when the value is less than one second.
 *             Unit conversion: seconds = milliseconds / 1000.
 */
@Deprecated(since = "2.5")
public long durationSeconds() {
    return durationMillis() / 1000;
}

public long durationMillis() {
    return 1500;
}
```

In the illustration above, the old API and the new API use different units. Migrators need to review the calling code; **you should not mechanically replace the method name while keeping all calculations unchanged**.

## 5. Standalone Java 17+ Example: Reading since and forRemoval with Reflection

Create a **`DeprecationDemo.java`** file containing all of the following code. The example intentionally **does not call the deprecated methods directly**; it reads the metadata using reflection and calls the replacement API. This makes stdout easy to verify without confusing it with compilation warnings.

```java
import java.lang.reflect.Method;

/**
 * Demonstrates API deprecation status.
 */
public class DeprecationDemo {

    static class LegacyApi {

        /**
         * Returns the old name format.
         *
         * @since 1.0
         * @deprecated Since version 2.0, use {@link #modernName()}.
         */
        @Deprecated(since = "2.0")
        public String oldName() {
            return "old";
        }

        /**
         * Returns an experimental name format that is no longer suitable.
         *
         * @deprecated Since 3.0, use {@link #modernName()}.
         *             This method is marked for removal in a future release.
         */
        @Deprecated(since = "3.0", forRemoval = true)
        public String fragileName() {
            return "fragile";
        }

        /**
         * Replacement API to use.
         *
         * @return name in the new format
         */
        public String modernName() {
            return "modern";
        }
    }

    private static void inspect(String methodName)
            throws NoSuchMethodException {
        Method method = LegacyApi.class.getDeclaredMethod(methodName);
        Deprecated deprecated = method.getAnnotation(Deprecated.class);

        if (deprecated != null) {
            System.out.println(methodName
                    + ": since=" + deprecated.since()
                    + ", forRemoval=" + deprecated.forRemoval());
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        inspect("oldName");
        inspect("fragileName");
        System.out.println(new LegacyApi().modernName());
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 DeprecationDemo.java
java DeprecationDemo
```

**Exact** stdout of the `java DeprecationDemo` command:

```text
oldName: since=2.0, forRemoval=false
fragileName: since=3.0, forRemoval=true
modern
```

Line-by-line explanation:

1. `oldName` specifies `@Deprecated(since = "2.0")`; since `forRemoval` is omitted, reflection reads `false`.
2. `fragileName` specifies both `since` and `forRemoval = true`, so reflection reads those exact two values.
3. `modernName()` is the normal active API; the `modern` result comes from the method body.

The `@Deprecated` annotation has runtime retention, so it can be queried via reflection. **Reflection cannot retrieve the content of the `@deprecated` Javadoc tag** with `method.getAnnotation()`. Javadoc exists in the source code for documentation tools to process.

Generate HTML pages to view the `@deprecated` tags and replacement links:

```bash
javadoc -private -encoding UTF-8 -docencoding UTF-8 -d docs DeprecationDemo.java
```

The `-private` option allows the documentation to include the nested `LegacyApi` class, which is not declared `public` in the example. The documentation generator command may print notes or warnings depending on the JDK; those messages **are not the stdout of `DeprecationDemo`**.

### What Happens When Calling the Old API?

The following snippet only illustrates **a usage site in other code**, not a direct replacement for the contents of the standalone example file above:

```java
// Assume api is a LegacyApi instance from the example.
api.oldName();      // ordinary deprecation
api.fragileName();  // removal warning
```

If you compile that call site with `-Xlint:deprecation -Xlint:removal`, the compiler may report warnings on the corresponding calls. Warnings are **compile-time diagnostics**, not runtime exceptions, and they do not automatically stop the method from executing.

## 6. Warnings and @SuppressWarnings During API Migration

For code consuming a library, the two warning categories are handled independently:

```java
@SuppressWarnings("deprecation")
public void stillUsingOrdinaryDeprecation() {
    // Calls to ordinarily deprecated APIs inside
    // can be exempted from "deprecation" warnings.
}

@SuppressWarnings("removal")
public void temporarilyUsingRemovalApi() {
    // Exempts only "removal" warnings within the method scope.
}
```

The two methods above are **syntax illustrations** and do not yet contain real API calls. `@SuppressWarnings("deprecation")` does not automatically suppress `removal` warnings, and vice versa. You can use `@SuppressWarnings({"deprecation", "removal"})` if both are genuinely needed, but there should be a valid reason and a plan to remove the legacy code.

Sound approaches in order of priority:

- Find the replacement API and inspect differences in behavioral contracts.
- Write tests covering important cases before and after migration.
- For `forRemoval = true`, prioritize planning the migration because the API may no longer exist in a later version.
- Only temporarily suppress warnings in a narrow scope when compatibility must be preserved; do not treat suppression as proof that the API is safe.

In large applications, `jdeprscan` can be used to scan bytecode for usage of **deprecated JDK APIs**; it is not a general-purpose tool for detecting every deprecated annotation across all third-party libraries. To check custom libraries, combine lint options, dependency checks, and the appropriate analysis tools.

## 7. Caveats to Remember When Designing and Releasing Libraries

**Deprecation is not API removal.** Libraries should retain the old API for a transition period consistent with their compatibility policy. Only mark `forRemoval = true` when there is intent to remove; such an intent should be communicated in the release notes.

**Keep descriptions accurate.** If the first version in which an API was marked deprecated is 2.0, do not set `since = "1.0"` just because the API existed since 1.0. This value indicates **when it was first deprecated**, not when it first existed.

**Do not misinterpret the meaning of forRemoval.** Marking `true` does not set a JVM-enforced expiration date. Nor does it automatically create a replacement; the `@deprecated` tag still needs to state clearly how to migrate.

**Use proper Javadoc.** Writing `// @deprecated` or `/* @deprecated ... */` as ordinary comments does not produce a valid Javadoc tag. The `@deprecated` tag must reside inside a `/** ... */` comment with descriptive text immediately following the tag.

**Use the annotation and documentation tag together.** The annotation is for the compiler and tools; the documentation tag is for API users. Omitting either leaves information incomplete, and omitting the annotation when the tag is present can trigger a `dep-ann` warning.

**Understand library versioning.** When applied to a custom-built Java module, `since = "4.0"` refers to the version of that library itself if the development team follows that convention; it does not have to be Java 4.0 (and Java 4.0 is not a modern language baseline anyway).

## 8. Common Mistakes and How to Recognize Them

| Misconception | Correct Fact to Remember |
| --- | --- |
| “`@Deprecated` makes the API uncallable” | The API can still run as long as the element exists; the compiler warns about the risk |
| “`since` is the version when the method was created” | It is the version in which deprecation began |
| “`forRemoval = true` deletes the method on the next build” | It only indicates intent to remove in a future version |
| “`forRemoval = false` guarantees it will never be removed” | There is no guarantee of permanent existence |
| “`@deprecated` in Javadoc is the annotation itself” | It is a documentation tag, with a lowercase `d` |
| “Writing only the annotation is enough to guide users through migration” | Javadoc is needed with the reason, link, and behavioral differences |
| “`@SuppressWarnings("deprecation")` suppresses removal warnings as well” | `"removal"` is needed for that separate warning category |
| “Reflection will retrieve the `@deprecated` description text” | Reflection reads runtime annotations, not doc comments |
| “Java 8 supports the annotation's `since`/`forRemoval`” | These two elements were introduced in Java 9 |

## 9. Self-Check Questions

**Question 1.** In `@Deprecated(since = "5.0")`, is `5.0` the version the API was created or when it was first deprecated?

**Answer:** It is the first version in which the API was marked deprecated.

**Question 2.** Is a method with `@Deprecated(forRemoval = true)` disabled by the JVM?

**Answer:** No. It can still exist and function; `true` is metadata signaling intent to remove in the future.

**Question 3.** How do `@deprecated` inside `/** ... */` and `@Deprecated` before a method differ?

**Answer:** The Javadoc tag describes the reason and replacement path; the annotation marks metadata for the compiler and tools to recognize. Both should be used.

**Question 4.** Should a `[removal]` warning be suppressed with `"deprecation"` or `"removal"`?

**Answer:** `"removal"`, if there is a legitimate reason to temporarily suppress it.

**Question 5.** How should an API released in 1.0 and deprecated in 3.0 be documented?

**Answer:** If recording the time of introduction is needed, use Javadoc `@since 1.0`; for the annotation, use `@Deprecated(since = "3.0")`. Add Javadoc `@deprecated` to describe the new API.

## References

- [Java 21 Standard Javadoc: java.lang.Deprecated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Deprecated.html).
- [Oracle Java 17 Core Libraries Developer Guide: Enhanced Deprecation](https://docs.oracle.com/en/java/javase/17/core/enhanced-deprecation1.html).

Try changing `forRemoval` in the example to `false`, compiling, and observing reflection; then generate the Javadoc documentation to compare the two information channels. When working with real-world APIs, read both the annotation and the `@deprecated` explanation before deciding on the urgency and migration path.
