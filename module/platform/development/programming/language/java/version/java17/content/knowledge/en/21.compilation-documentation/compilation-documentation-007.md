# @since, --since, and --since-label in API Documentation

The `@since` tag records the release version in which an API was introduced. Javadoc displays this tag under the Since section of the generated documentation page.

At the tool level, newer Javadoc versions add the --since and --since-label options to generate summary pages of new APIs. These two options must be distinguished from the @since tag.

## 1. What is the @since tag?

**@since** is a block tag inside documentation comments used to record which release introduced an API element. Javadoc displays the tag's content under the **Since** heading on the generated documentation page.

~~~java
/**
 * Represents a request accepted by the service.
 *
 * @since 17
 */
public final class ServiceRequest {
}
~~~

The tag can appear in documentation comments on modules, packages, classes, interfaces, constructors, methods, fields, and the overview page. This tag has been supported since JDK 1.1.

### 1.1. Syntax and meaning

~~~text
@since since-text
~~~

**since-text** is descriptive version text. Javadoc does not parse this content into a numerically ordered version structure; it renders it as text.

~~~java
/**
 * Returns the normalized identifier.
 *
 * @return normalized identifier
 * @since 17
 */
public String normalizedId() {
    return id.trim().toLowerCase(Locale.ROOT);
}
~~~

For Java platform APIs, the **@since** value denotes the Java API specification version in which the element was introduced. It is not necessarily when source code was committed to a reference implementation repository. For private libraries, teams typically use the first version number in which the API was published, following the library's versioning convention.

## 2. Where should @since be placed?

Place **@since** wherever readers need to know when an API appeared.

### 2.1. New APIs inside an existing class

Suppose a class was introduced in Java 11, while a new method was added in release 17:

~~~java
/**
 * Provides information about a service.
 *
 * @since 11
 */
public class ServiceInfo {
    /**
     * Returns the service name.
     */
    public String name() {
        return name;
    }

    /**
     * Returns the service health state.
     *
     * @since 17
     */
    public Health health() {
        return health;
    }
}
~~~

The class carries **11**, whereas **health()** carries **17**. Whenever a member appears later than its enclosing class, tag that member separately.

### 2.2. Packages, modules, fields, and constructors

Package comment:

~~~java
/**
 * Public API for service monitoring.
 *
 * @since 17
 */
package com.example.monitoring;
~~~

Module comment:

~~~java
/**
 * Provides service monitoring APIs.
 *
 * @since 17
 */
module com.example.monitoring {
    exports com.example.monitoring;
}
~~~

Fields and constructors can also carry their own tags:

~~~java
public final class RetryPolicy {
    /**
     * Default maximum number of attempts.
     *
     * @since 17
     */
    public static final int DEFAULT_ATTEMPTS = 3;

    /**
     * Creates a policy with the given attempt limit.
     *
     * @param attempts maximum number of attempts
     * @since 17
     */
    public RetryPolicy(int attempts) {
        this.attempts = attempts;
    }
}
~~~

## 3. Distinguishing @since, @version, and @Deprecated(since)

These three items relate to versions yet answer different questions:

| Element | Question answered | Example |
| --- | --- | --- |
| **@since 17** | Since which release has the API existed? | Method introduced in Java SE 17 |
| **@version 2.4** | Which version is the doc or software component describing? | Current version of the library |
| **@Deprecated(since = "18")** | Since which release was the API marked deprecated? | API deprecated starting in Java 18 |

**@since** does not mean an API is still recommended. A method can be introduced in Java 11 and later deprecated in Java 17.

~~~java
/**
 * Sends a request using the old transport.
 *
 * @deprecated Use {@link #sendWithClient(Request)} instead.
 * @since 11
 */
@Deprecated(since = "17", forRemoval = false)
public Response send(Request request) {
    // ...
}
~~~

Here, **@since 11** states the method appeared in release 11; **@Deprecated(since = "17")** states it was deprecated in release 17; **@deprecated** explains the deprecation status and guides users to the replacement API. Use the @deprecated tag and @Deprecated annotation together so documentation content and compiler metadata stay consistent.

## 4. How does Javadoc display @since?

When running the standard doclet, each **@since** tag renders as a **Since** section on the corresponding API page. The tag does not by itself generate a summary page of all new APIs in a release.

~~~java
/**
 * Returns the current status.
 *
 * @since 17
 */
public Status status() {
    // ...
}
~~~

Javadoc provides the **-nosince** option to omit Since sections from generated documentation:

~~~bash
javadoc -nosince -d docs com.example.api
~~~

This option affects only whether Since sections appear in the output. It does not remove tags from source code or alter API history in source. Normally, public API documentation should retain Since information because it helps users verify compatibility across versions.

## 5. --since and --since-label arrived in JDK 18

Important version distinction for this topic:

| Javadoc tool | @since | --since | --since-label |
| --- | --- | --- | --- |
| JDK 17 | Yes | Not supported | Not supported |
| JDK 18 and later | Yes | Yes | Yes |

JDK 17's Javadoc supports the **@since** tag and **-nosince** option, yet the JDK 17 command reference does not list **--since** or **--since-label**. Those two options appear in tool documentation starting in JDK 18.

Consequently, running:

~~~bash
javadoc --since 17 --since-label "New API in Java SE 17" ...
~~~

with JDK 17's **javadoc** executable reports an invalid option. To use those two options, run the Javadoc tool from JDK 18 or later.

**The version of the Javadoc executable determines which options are supported.** Targeting Java 17 in source code or passing **--release 17** does not add options missing from the JDK 17 executable.

## 6. What is --since used for?

**--since** instructs the standard doclet to generate a summary page of APIs newly added or newly deprecated in the specified releases.

Syntax:

~~~text
--since release[,release]*
~~~

Example:

~~~bash
javadoc --since 17 -d docs com.example.api
~~~

If an element's documentation comment contains a **@since** tag exactly matching a specified release, Javadoc includes that element and its introduction release on the **New API** page.

The option also reads **java.lang.Deprecated** annotation metadata: if the Deprecated API page is generated and the annotation's **since** value matches a specified release, the release in which the element was deprecated is included on the Deprecated API page.

### 6.1. How are release values compared?

Javadoc compares releases as case-sensitive strings, not by numeric version parsing:

| Value in source | Value passed to --since | Match? |
| --- | --- | --- |
| @since 17 | --since 17 | Yes |
| @since 17 | --since 17,18 | Yes |
| @since 17 | --since 17.0 | No |
| @since 17 | --since Java 17 | No |
| @since 17 | --since 17-ea | No |

Keep version string conventions uniform across source and build commands. For Java platform releases, use concise tokens like **17** or **18**. For private libraries, pick a clear convention such as **2.4** and pass that exact string to the command.

### 6.2. Multiple releases in one run

You can specify multiple releases separated by commas:

~~~bash
javadoc --since 17,18,21 -d docs com.example.api
~~~

Javadoc aggregates APIs whose tags or deprecation metadata match the selected releases. Commas separate values within a single argument; do not pass each release as a separate argument after the option.

## 7. What is --since-label used for?

**--since-label** sets the heading text on the **New API** page generated by **--since**. It customizes the display label without altering release filtering.

Syntax:

~~~text
--since-label text
~~~

Example:

~~~bash
javadoc --since 17 --since-label "New API in Java SE 17" -d docs com.example.api
~~~

Labels can describe the release or documentation scope:

~~~bash
javadoc --since 17,18 --since-label "New API in releases 17 and 18" -d docs com.example.api
~~~

**--since-label** changes only the heading. It does not alter @since values in source, the selected releases, string matching, Since sections on individual class/member pages, or @Deprecated(since = ...) metadata.

If no custom heading is needed, omit **--since-label** and use the standard doclet's default label.

## 8. Complete example: tagging APIs and generating the New API page

Suppose a library has a class existing since release 11 and a new method added in release 17:

~~~java
package com.example.api;

/**
 * Provides information about a service.
 *
 * @since 11
 */
public final class ServiceInfo {
    /**
     * Returns the service name.
     *
     * @return service name
     */
    public String name() {
        return "orders";
    }

    /**
     * Returns the current health state.
     *
     * @return health state
     * @since 17
     */
    public Health health() {
        return Health.UP;
    }
}
~~~

An enum added in the same release:

~~~java
package com.example.api;

/**
 * Health state of a service.
 *
 * @since 17
 */
public enum Health {
    UP,
    DEGRADED,
    DOWN
}
~~~

Documentation can be generated with JDK 17:

~~~bash
javadoc --release 17 -d docs src/main/java/com/example/api/*.java
~~~

The output contains API pages and per-tag Since sections. JDK 17 has no New API summary page generated via **--since**.

If using JDK 18 or later to run Javadoc while still documenting the API against Java 17:

~~~bash
javadoc --release 17 --since 17 --since-label "New API in Java SE 17" -d docs src/main/java/com/example/api/*.java
~~~

Here:

- JDK 18+ provides the executable supporting **--since** and **--since-label**.
- **--release 17** tells Javadoc to analyze sources using the Java 17 platform API model.
- **@since 17** in comments supplies the metadata for the New API page to include elements added in release 17.

Do not confuse **--release 17** with **--since 17**: the former chooses the Java platform release used for compiling/analyzing; the latter selects the API milestone for generating summary pages.

## 9. Combining @since with @Deprecated(since)

Since Java 9, the **@Deprecated** annotation has **since** and **forRemoval** elements:

~~~java
@Deprecated(since = "17", forRemoval = false)
~~~

- **since** records the release in which the element was marked deprecated.
- **forRemoval = false** indicates the API is discouraged while no concrete removal plan is declared at the time of marking.
- **forRemoval = true** indicates the API is scheduled for future removal.

To explain why and point to replacements in Javadoc, include the **@deprecated** tag:

~~~java
/**
 * Opens a legacy connection.
 *
 * @deprecated Use {@link #openClient()} instead.
 * @since 11
 */
@Deprecated(since = "17", forRemoval = false)
public Connection openConnection() {
    // ...
}
~~~

When running a Javadoc tool that supports **--since 17**, deprecated release information can appear on the Deprecated API page if generated and matching the annotation value. **@since 11** still records when the API was originally introduced.

Never overwrite **@since** with the deprecation release. Those two milestones mean different things and must be preserved separately.

## 10. Project conventions for release strings

For **--since** to work reliably, teams should follow a consistent convention:

1. Use one simple release token per API introduction, such as **17** or **2.4**.
2. Keep identical spelling across source, build scripts, and release docs.
3. Avoid descriptive prefixes or suffixes like **Java 17** or **v2.4 release** in tags if matching via **--since**.
4. Tag at the class/package/module level when an entire API group is introduced together.
5. Tag individual members separately when added in a later release.
6. When deprecating, update **@Deprecated(since = ...)** and write a **@deprecated** description.
7. Never change an older **@since** milestone simply because the current version increased; it represents API history.

### 10.1. Do not treat @since as a changelog

**@since** is not a list of every edit made to an API. If a method existed since release 11 and had its implementation modified in release 17, **@since** stays 11.

Bug fixes, behavioral updates, new constraints, or migration notes belong in release notes, migration guides, or relevant API descriptions. Update or add **@since** only when an API element is newly introduced in a release.

### 10.2. Do not tag with build dates

Do not use build dates, CI numbers, or patch build identifiers in **@since** when users expect API versions. This milestone must follow the published release/versioning contract of the library.

## 11. Limitations and common misconceptions

| Misconception | Reality |
| --- | --- |
| JDK 17 supports --since because it supports @since | No. JDK 17 supports the tag; the two command-line options arrived in JDK 18. |
| --since 17 filters all docs to Java 17 APIs only | It generates a New API summary page for the chosen release; other API pages remain in output. |
| --since compares versions numerically | No. Release values are matched as case-sensitive strings. |
| --since-label modifies @since tags | No. It changes only the heading on the New API page. |
| @since records when source code was committed | For Java platform APIs, it denotes the API specification version; for private libraries, it follows the library's release convention. |
| @since and @Deprecated(since) record the same milestone | No. One records API introduction; the other records deprecation release. |
| @since automatically generates a New API page | No. The tag creates a Since section on element pages; the summary page requires a Javadoc tool supporting --since. |
| Running javadoc --release 17 adds JDK 18 options | No. --release does not upgrade the executable's own version. |
| --since-label filters releases | No. It only customizes the display heading. |

## 12. Self-check questions

**1. What does the @since tag record?**  
The release version in which an API or element was introduced.

**2. Can @since be used with JDK 17 Javadoc?**  
Yes. It is a standard tag available since JDK 1.1.

**3. In which documentation comments is @since valid?**  
Overview, module, package, class, interface, constructor, method, and field comments.

**4. Does @since automatically generate a New API page?**  
No. It renders a Since section on element pages; summary pages require the --since option in a newer Javadoc tool.

**5. Does JDK 17 support --since and --since-label?**  
No. Those two options were introduced in JDK 18.

**6. What output does --since produce?**  
A New API summary page listing APIs added in specified releases, plus matching deprecation release entries where applicable.

**7. How does --since accept multiple releases?**  
As a single comma-separated argument, such as --since 17,18,21.

**8. Does @since 17 match --since 17.0?**  
No. Javadoc matches release strings literally without version number parsing.

**9. What does --since-label change?**  
The heading text of the New API page; it does not alter release metadata or filtering.

**10. What is the difference between @since and @Deprecated(since = ...)?**  
@since records when the API was introduced; @Deprecated(since = ...) records when the API was deprecated.

**11. When using JDK 18 Javadoc to document a Java 17 API, can --release 17 be combined with --since 17?**  
Yes. The JDK 18 tool provides the option; --release 17 selects the Java 17 platform API model.

**12. Should @since 11 be changed to @since 17 when upgrading a library version to 17?**  
No, unless the API was genuinely introduced in release 17. @since records introduction history, not the current version.

## Official references

- [Java SE 17 — Documentation Comment Specification, @since](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html): syntax, valid locations, and meaning of the @since tag.
- [Java SE 17 — The javadoc Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): Javadoc options in JDK 17; includes -nosince, without --since or --since-label.
- [Java SE 18 — The javadoc Command](https://docs.oracle.com/en/java/javase/18/docs/specs/man/javadoc.html): documentation defining --since and --since-label, including release matching rules.
- [Java SE 17 API — Deprecated](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Deprecated.html): the since and forRemoval elements of the @Deprecated annotation.
