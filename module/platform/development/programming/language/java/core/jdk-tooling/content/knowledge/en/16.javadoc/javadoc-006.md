# Package Documentation with Javadoc

Package documentation is the package-level description that helps readers understand the purpose of a group of classes and interfaces and how those types work together. It answers broader questions than individual class documentation: what capabilities the package provides, where to start, how components relate to one another, and which rules apply across the package.

In Java, the standard way to provide this documentation is to write a documentation comment in `package-info.java`. The `javadoc` tool reads that comment and includes it on the package's `package-summary.html` page.

## 1. How Does Package Documentation Differ from Class Documentation?

Each documentation level has a distinct responsibility:

| Documentation Level | Where to Write | What to Focus On |
|---|---|---|
| Module | `module-info.java` | Module purpose, dependencies, exported packages, services used/provided |
| Package | `package-info.java` | Package purpose, conceptual model, relationships between types, general rules |
| Class/interface | The type's `.java` file | Type responsibility, state, how to instantiate and use it |
| Constructor/method/field | Comment immediately before the member | Behavior, parameters, return values, exceptions, and conditions |

For example, in the `com.example.orders` package:

- Package documentation explains the order creation flow, order states, and the relationships among `Order`, `OrderItem`, and `OrderService`.
- `OrderService` documentation explains that specific service and its public methods.
- `OrderService.submit(...)` documentation describes parameters, results, and errors that may occur.

A package comment should not merely repeat the list of classes. It should help readers understand how to use the package as a cohesive unit.

## 2. The package-info.java File

The source tree typically places this file in the directory corresponding to the package:

~~~text
src/
└── com/
    └── example/
        └── text/
            ├── package-info.java
            ├── TextNormalizer.java
            └── TextValidator.java
~~~

The `package-info.java` file contains a documentation comment immediately before the package declaration:

~~~java
/**
 * Provides utilities for normalizing and validating user-visible text.
 *
 * <p>The package separates normalization from validation:
 * normalization produces a canonical representation, while validation
 * checks whether the resulting text satisfies application rules.
 *
 * <h2>Usage model</h2>
 * <p>Normalize input before comparing or storing it. Apply validation
 * after normalization when a canonical representation is required.
 *
 * <h2>Related types</h2>
 * <p>{@link com.example.text.TextNormalizer} performs normalization.
 * {@link com.example.text.TextValidator} checks application constraints.
 *
 * @since 1.0
 * @see java.text.Normalizer
 */
package com.example.text;
~~~

Key points:

1. Use a `/** ... */` comment, not `/* ... */` or `//`. Javadoc only recognizes documentation comments.
2. The comment must be placed immediately before the package declaration.
3. The package name must match the package containing the source files.
4. The first sentence should be a short, complete summary that accurately describes the package.
5. You can use valid HTML, inline tags such as `{@link ...}`, and block tags such as `@since`.
6. `package-info.java` is the appropriate place to keep package annotations alongside package documentation.

The JLS recommends using `package-info.java` instead of the legacy `package.html` file. This file typically contains only the package declaration, annotations, and documentation comment; classes or application logic should not be placed here.

## 3. Writing Useful Package Comment Content

A good package comment tells readers what the package does and how to use it. You can organize the content around the following topics, depending on the package's complexity:

### 3.1. Summary Sentence and Purpose

The first sentence is used by Javadoc as the summary on the package page and overview/listing pages. Write this sentence as a standalone description:

- Good: "Provides classes for parsing, validating, and formatting application configuration."
- Too vague: "This package contains some useful classes."
- Too narrow: "Provides the ConfigParser class."

Do not place headings, long introductions, or unrelated opening sentences before the summary sentence. If the package has multiple capabilities, state the core capability in the first sentence and explain the rest in subsequent paragraphs.

### 3.2. Concepts and Usage Model

Explain the terminology and mental model readers need before calling the API. For example:

- Which objects are inputs and which are outputs?
- What role does each class play in a workflow?
- Does API call ordering matter?
- Are there states or lifecycles that must be followed?
- Does the package have general conventions for null handling, thread safety, resource ownership, or error handling?

Describe the relationships between key types rather than copying method summaries from class pages.

### 3.3. Package-Level Rules and Contracts

Document conventions that apply across multiple types in the package, such as:

- Data normalization before comparison.
- Encoding, locale, or timezone rules.
- Who is responsible for closing resources.
- Which objects can be shared across threads.
- How errors or invalid data are represented.
- Limitations, assumptions, and compatibility conditions.

Only document rules that API users need to know. Internal implementation details belong in separate design documentation.

### 3.4. Examples and Related Documentation

Include a short usage flow if it helps readers understand the package. For large packages, link to external tutorials, architecture guides, or specifications rather than cramming all documentation onto one page.

You can use:

- `{@link com.example.text.TextNormalizer}` to link to a type in the same API.
- `@see java.text.Normalizer` to create a See Also entry.
- `@since 1.0` to record the version in which the package was introduced.

Package documentation is the starting point; class and method documentation remains responsible for describing the detailed contract of each API.

## 4. Javadoc Tags Used at the Package Level

Not every Javadoc tag can be used in a package comment.

| Tag | Valid for package? | Purpose |
|---|---|---|
| `@since` | Yes | Records the version in which the package/API was introduced |
| `@see` | Yes | Links to related types, packages, or documentation |
| `{@link ...}` | Yes | Creates an inline link in the description text |
| `{@linkplain ...}` | Yes | Creates an inline link with a plain-text label |
| `{@code ...}` | Yes | Displays an API name or code snippet in code font |
| `@author` | Yes | Lists authors/contributors if the project uses that convention |
| `@serial include` / `@serial exclude` | Yes | Controls whether classes in the package are included on the serialized form page |
| `@param` | No | Used for class, constructor, or method parameters |
| `@return` | No | Used for methods |
| `@throws` | No | Used for constructors or methods |
| `@provides` / `@uses` | No | Used in module documentation comments |

### 4.1. Linking Types and Members

Example:

~~~java
/**
 * This package uses {@link java.util.Optional} to represent
 * values that may be absent.
 *
 * <p>See {@link java.util.Objects#requireNonNull(Object)}
 * when a non-null argument is required.
 *
 * @see java.util.function.Function
 * @since 2.0
 */
package com.example.mapping;
~~~

When documentation references external APIs that are not generated in the same run, you can use `-link` or `-linkoffline` to create external links to published Javadoc sets.

### 4.2. Package Serialization

If a package contains serializable classes, `@serial include` or `@serial exclude` can control whether those classes appear on the serialized form page:

~~~java
/**
 * Provides internal implementation types for the persistence layer.
 *
 * @serial exclude
 */
package com.example.persistence.internal;
~~~

Class-level tags can override a package-level `@serial` rule. Only use this tag when the project actually generates and maintains serialized-form documentation.

### 4.3. Avoid Misplaced Tags

For example, `@param` and `@return` make no sense in a package comment because a package is neither a method nor a constructor. Placing tags in the wrong context can cause DocLint errors or produce unexpected documentation.

The `@provides` and `@uses` tags describe module service dependencies, so they belong in `module-info.java` comments.

## 5. Package Annotations in package-info.java

In addition to documentation, `package-info.java` can declare annotations for the package. This is one of the main reasons to prefer this file over `package.html`.

An annotation used on a package must declare `@Target(ElementType.PACKAGE)`. For a given package, there may be at most one annotated package declaration. If the annotation needs to be read at runtime, the annotation type must use `@Retention(RetentionPolicy.RUNTIME)`.

Annotation example:

~~~java
package com.example.text;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Associates a package with a short descriptive label.
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackageLabel {
    /**
     * Returns the label assigned to the package.
     *
     * @return the package label
     */
    String value();
}
~~~

Combining an annotation and documentation in `package-info.java`:

~~~java
/**
 * Provides small utilities for normalizing application text.
 *
 * <p>Use these utilities before comparing or storing user input.
 *
 * @since 1.0
 * @see java.text.Normalizer
 */
@PackageLabel("text utilities")
package com.example.text;
~~~

### 5.1. Reading Package Annotations at Runtime

An annotation with `RUNTIME` retention is stored in `package-info.class`. You can access it through the `Package` object of a class belonging to that package:

~~~java
Package pkg = TextNormalizer.class.getPackage();
PackageLabel label = pkg.getAnnotation(PackageLabel.class);
~~~

If the package does not have the corresponding annotation or the annotation is not retained at runtime, the result may be `null`. Check for null before using it.

Example:

~~~java
if (label != null) {
    System.out.println(label.value());
}
~~~

A package annotation is package metadata. It does not replace a Javadoc comment and does not automatically generate package description text.

## 6. package.html and doc-files

### 6.1. package.html — The Legacy Approach

For historical compatibility, Javadoc still supports `package.html` in the package source directory. The documentation content is the portion between the `<body>` and `</body>` tags:

~~~html
<html>
<body>
<p>Provides utilities for parsing application configuration.</p>
<p>The package supports loading, validation, and conversion.</p>
</body>
</html>
~~~

Points to remember:

- `package.html` only contains HTML content and Javadoc tags; it cannot declare package annotations.
- References to Java types in this file should use fully qualified names.
- Choose `package-info.java` for new projects or when package annotations are needed.
- When migrating from `package.html` to `package-info.java`, consolidate the content into a single documentation source to avoid duplication and drift.

### 6.2. doc-files — Supplementary Documentation

If a package needs diagrams, images, HTML examples, or supporting documents, place them in a `doc-files` directory alongside the source files:

~~~text
src/
└── com/example/text/
    ├── package-info.java
    ├── TextNormalizer.java
    └── doc-files/
        ├── normalization-flow.svg
        └── usage-guide.html
~~~

The Standard Doclet copies resources in `doc-files` to the corresponding package output directory. You can link to them from the package comment using relative paths, for example:

~~~html
<p><a href="doc-files/usage-guide.html">Usage guide</a></p>
<img src="doc-files/normalization-flow.svg"
     alt="Text normalization flow">
~~~

If there are subdirectories inside `doc-files`, use `-docfilessubdirs` to tell Javadoc to copy them recursively. For images, always provide `alt` text for accessibility.

## 7. Generating Package Documentation with javadoc

General syntax:

~~~text
javadoc [options] [packagenames] [sourcefiles] [@argfiles]
~~~

A basic command to generate documentation for the `com.example.text` package:

~~~bash
javadoc -encoding UTF-8 \
  -d docs \
  -sourcepath src \
  -Xdoclint:all \
  com.example.text
~~~

Meaning:

- `-encoding UTF-8` specifies the encoding of the source files being read.
- `-d docs` specifies the directory where HTML output is saved.
- `-sourcepath src` specifies the source root for Javadoc to locate packages.
- `-Xdoclint:all` enables all documentation check groups.
- `com.example.text` is the package to document.

You can generate documentation for all subpackages under `com.example`:

~~~bash
javadoc -encoding UTF-8 \
  -d docs \
  -sourcepath src \
  -subpackages com.example
~~~

`-subpackages` traverses subpackages recursively. It is useful when a project adds new packages and you want them included in the next documentation build. You can combine it with `-exclude` to omit packages that are not part of the public documentation.

### 7.1. Adjusting API Visibility Scope

By default, Javadoc generates documentation for `public` and `protected` APIs. Common options:

| Option | Scope |
|---|---|
| `-public` | Public only |
| `-protected` | Public and protected; default |
| `-package` | Adds package-private |
| `-private` | All members, including private |

For APIs released to library users, choose a visibility scope that matches the public contract. Internal documentation can use `-private` if truly needed, but should be kept clearly separate from the supported public API.

### 7.2. Generating Documentation for Modules

In modular projects, a module can have its own comment in `module-info.java` and each package can have a comment in `package-info.java`.

Example:

~~~bash
javadoc --module-source-path src \
  -d docs \
  --module com.example.library
~~~

Here `src` is the module source path. Javadoc generates separate module summary and package summary pages. Module documentation describes dependencies, services, and exports; package documentation describes how to use the types within each package.

## 8. Generated Output

For a package not in a named module, the output structure might look like this:

~~~text
docs/
├── index.html
├── allpackages-index.html
├── help-doc.html
└── com/
    └── example/
        └── text/
            ├── package-summary.html
            ├── PackageLabel.html
            ├── TextNormalizer.html
            └── doc-files/
                ├── normalization-flow.svg
                └── usage-guide.html
~~~

`package-summary.html` is the overview page for the package. It contains the list of documented types and the package description taken from `package-info.java`.

If the package belongs to a named module, the output directory tree is placed under the module's directory, for example:

~~~text
docs/
└── com.example.library/
    └── com/
        └── example/
            └── text/
                └── package-summary.html
~~~

Do not confuse the package summary page with a class page: the package summary helps readers choose a type and understand the overall model, while a class page contains detailed documentation for a single type.

## 9. Complete Walkthrough with Java 17+

Let's create the `com.example.text` package with package documentation and a runtime package annotation.

### 9.1. Project Structure

~~~text
project/
└── src/
    ├── com/example/text/
    │   ├── package-info.java
    │   ├── PackageLabel.java
    │   └── TextNormalizer.java
    └── com/example/app/
        └── Main.java
~~~

### 9.2. Creating the PackageLabel Annotation

File `src/com/example/text/PackageLabel.java`:

~~~java
package com.example.text;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Associates a package with a short descriptive label.
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackageLabel {
    /**
     * Returns the label assigned to the package.
     *
     * @return the package label
     */
    String value();
}
~~~

### 9.3. Creating package-info.java

File `src/com/example/text/package-info.java`:

~~~java
/**
 * Provides utilities for trimming and preparing application text.
 *
 * <p>The package offers a small normalization API that can be used
 * before validating or comparing user input.
 *
 * <h2>Usage model</h2>
 * <p>Call {@link TextNormalizer#trim(String)} before applying
 * application-specific validation rules.
 *
 * @since 1.0
 * @see java.text.Normalizer
 */
@PackageLabel("text utilities")
package com.example.text;
~~~

### 9.4. Creating the TextNormalizer Class

File `src/com/example/text/TextNormalizer.java`:

~~~java
package com.example.text;

/**
 * Provides basic text-normalization operations.
 */
public final class TextNormalizer {
    private TextNormalizer() {
    }

    /**
     * Removes leading and trailing whitespace.
     *
     * @param text the input text; null is treated as an empty string
     * @return the trimmed text, or an empty string if text is null
     */
    public static String trim(String text) {
        return text == null ? "" : text.strip();
    }
}
~~~

### 9.5. Creating the Main Program

File `src/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.text.PackageLabel;
import com.example.text.TextNormalizer;

public class Main {
    public static void main(String[] args) {
        Package pkg = TextNormalizer.class.getPackage();
        PackageLabel label = pkg.getAnnotation(PackageLabel.class);

        if (label == null) {
            throw new IllegalStateException("Package annotation is missing");
        }

        System.out.println("Package: " + pkg.getName());
        System.out.println("Label: " + label.value());
        System.out.println("Normalized: [" + TextNormalizer.trim("  Java  ") + "]");
    }
}
~~~

### 9.6. Compiling and Running

Run from the `project` directory:

~~~bash
mkdir -p out docs

javac -encoding UTF-8 -d out \
  src/com/example/text/PackageLabel.java \
  src/com/example/text/package-info.java \
  src/com/example/text/TextNormalizer.java \
  src/com/example/app/Main.java

java -cp out com.example.app.Main
~~~

Exact stdout:

~~~text
Package: com.example.text
Label: text utilities
Normalized: [Java]
~~~

This example confirms that a package annotation can be read through `Package` when the annotation is retained at runtime. The `package-info.java` file also holds the documentation comment so Javadoc can generate the package summary.

### 9.7. Generating HTML Documentation

Still in the `project` directory:

~~~bash
javadoc -encoding UTF-8 \
  -d docs \
  -sourcepath src \
  -Xdoclint:all \
  com.example.text
~~~

After the command completes, open:

~~~text
docs/com/example/text/package-summary.html
~~~

Verify the summary sentence, package description, link to `TextNormalizer`, `Since` section, and other descriptive sections. You can also open the class page to confirm that method documentation was generated as well.

## 10. Checking Package Documentation Quality

Javadoc includes DocLint to detect many common comment issues. In JDK 21, DocLint is enabled by default; you can also specify it explicitly:

~~~bash
javadoc -Xdoclint:all -Werror \
  -encoding UTF-8 \
  -d docs \
  -sourcepath src \
  com.example.text
~~~

`-Werror` turns warnings into errors, which is useful in CI when a project wants to maintain consistent documentation quality.

DocLint has the following check groups:

| Group | Checks |
|---|---|
| `html` | Malformed HTML structure or missing closing tags |
| `syntax` | Javadoc syntax, unescaped `<`, `>`, or `&` characters |
| `reference` | `{@link}` or `@see` pointing to nonexistent elements |
| `missing` | Missing documentation comments or required tags |
| `accessibility` | Accessibility issues such as images missing `alt` or tables missing captions |

DocLint does not replace reading the generated documentation. It catches common mistakes in comments, but it cannot judge whether the content is accurate, clear, or complete for API users.

Pre-release checklist:

- The first sentence accurately describes the package's purpose.
- The content explains the model and relationships between key types.
- General rules on data, thread safety, resources, and errors are stated where relevant.
- Links to classes, packages, and methods work.
- Block tags are used in the proper context.
- HTML is valid and headings start at the appropriate level.
- Examples compile and run if presented as complete examples.
- Important subpackages also have their own package documentation.
- The `package-summary.html` page is opened and reviewed after generation.

## 11. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| No package description appears | Missing `package-info.java` or comment not placed immediately before the package declaration | Create the proper file and use `/** ... */` |
| Package summary page only lists classes | Empty package comment or package not included in the Javadoc run | Check `-sourcepath` and the package name on the command line |
| Javadoc cannot find the package | Incorrect source root or package directory | Point `-sourcepath` to the root directory containing the package tree |
| Broken links on the package page | Wrong class/member name or missing external link | Fix `{@link}`/`@see` and check `-link` if referencing external APIs |
| Comment renders as broken HTML | HTML missing closing tags or using invalid syntax | Fix the HTML and run `-Xdoclint:all` |
| Summary cut off at the wrong place | Period in the first sentence causes a false sentence boundary | Write a simple summary and avoid unnecessary abbreviations |
| Package annotation cannot be read at runtime | Missing `@Target(PACKAGE)` or retention is not RUNTIME | Check the annotation declaration and `package-info.class` |
| Package annotation exists but is not visible from another package | Checking the wrong class loader or wrong runtime package | Use a class from the target package/code source to obtain `Package` |
| Subpackage documentation is missing | Only the parent package was specified without `-subpackages` | Add subpackages explicitly or use `-subpackages` |
| Images or supplementary guides do not appear | Files placed in the wrong location or wrong relative path | Place them in `doc-files` next to the package sources and verify output |

## 12. Key Takeaways

`package-info.java` is the standard place for package documentation and package annotations. Place the comment immediately before the package declaration; the first sentence is the summary sentence, followed by the purpose, conceptual model, relationships between types, and general rules. Javadoc uses this content to generate `package-summary.html`.

`package.html` is still supported for historical compatibility, but `package-info.java` is better suited for new projects and for package annotations. Use `doc-files` for supplementary images or long-form documents; run `javadoc` with `-sourcepath`, `-d`, and `-subpackages` to build the docs; and run DocLint and inspect the generated HTML before releasing.

References:

- [The javadoc Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javadoc.html)
- [Documentation Comment Specification for the Standard Doclet — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html)
- [Java Language Specification, Java SE 21 — §7.4 Package Declarations](https://docs.oracle.com/javase/specs/jls/se21/jls21.pdf)
- [java.lang.Package API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html)
- [How to Write Doc Comments for the Javadoc Tool — Oracle](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html)