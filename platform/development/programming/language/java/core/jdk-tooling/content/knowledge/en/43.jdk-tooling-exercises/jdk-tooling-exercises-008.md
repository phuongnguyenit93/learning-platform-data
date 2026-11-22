# Generating API Documentation with Javadoc

**Javadoc** is the JDK tool used to read documentation comments in Java source code and generate HTML documentation for packages, classes, interfaces, records, modules, and API members. A good set of Javadoc helps users understand the purpose of an API, how to call methods, return values, potential errors, limitations, and compatibility requirements without having to read the entire implementation.

Javadoc is not just about running a command to generate HTML. Documentation quality depends on how comments are written in source code, toolchain configuration, link checking, HTML error detection, and integrating documentation into the build/release process.

This lab uses Java 17+ and JDK 24 to generate Javadoc directly via the CLI, integrate with Maven and Gradle, write package/module documentation, check with doclint, and package a Javadoc JAR.

## 1. What does Javadoc generate?

Javadoc reads source files and generates a structured set of HTML files:

~~~text
build/apidocs/
├── index.html
├── allclasses-index.html
├── allpackages-index.html
├── index-all.html
├── help-doc.html
├── overview-tree.html
└── com/
    └── acme/
        └── api/
            ├── package-summary.html
            ├── package-tree.html
            ├── Customer.html
            └── CustomerService.html
~~~

Depending on the JDK version, the structure may also include a search index, CSS, JavaScript, module summary, and usage pages.

Documented components:

- Package: group of related types.
- Module: set of packages and JPMS dependencies.
- Class/record: purpose, state, instantiation, and invariants.
- Interface: contract that implementations must adhere to.
- Constructor: input preconditions and exceptions.
- Method: parameters, result, side effects, thread-safety, and errors.
- Field/constant: meaning and units.
- Type parameter: bounds and role of the generic type.
- Deprecated API: reason for replacement and migration path.

Javadoc is typically distributed alongside a library as a Javadoc JAR so that IDEs can display documentation as soon as a developer uses the dependency. For an API website, the HTML directory can be published as a static site.

### How does Javadoc differ from the Java compiler?

- `javac` checks and compiles source code into class files.
- `javadoc` reads source code and comments to generate HTML.
- Javadoc can detect errors in references, HTML, and tags through doclint.
- Generating Javadoc does not replace unit tests or runtime behavior checks.

You can run `javac` and `javadoc` in the same pipeline, but they are two distinct steps.

## 2. Documentation comment syntax

A Javadoc comment starts with `/**` and ends with `*/`. The comment must be placed immediately before the declaration it describes:

~~~java
/**
 * Looks up a customer by its stable identifier.
 */
public interface CustomerService {
}
~~~

A comment usually begins with a short, complete sentence. The first sentence is used as the summary in package, class, and method pages.

Write a summary that can stand on its own:

~~~java
/**
 * Returns the customer associated with the given identifier.
 */
Optional<Customer> find(String id);
~~~

Avoid vague summaries:

~~~java
/**
 * This method.
 */
Optional<Customer> find(String id);
~~~

A detailed description can continue after a blank line:

~~~java
/**
 * Returns the customer associated with the given identifier.
 *
 * <p>The lookup is case-sensitive and does not modify stored data.</p>
 */
Optional<Customer> find(String id);
~~~

### Javadoc comments vs. regular comments

~~~java
// Internal implementation note.

/*
 * Multi-line source comment.
 */

/**
 * Public API documentation.
 */
~~~

Only documentation comments are processed by Javadoc to generate API documentation. Regular `//` and `/* ... */` comments do not appear in the HTML output.

### Documenting by contract

A method should answer:

- What does the method do?
- Which parameters are accepted?
- Is `null` allowed?
- Can the result be absent?
- Which exceptions can be thrown and under what conditions?
- Are there side effects?
- Is it thread-safe?
- Are there any performance limits or ordering guarantees?

Do not simply repeat the method name in prose without explaining the contract. For example, "Gets the customer" is not enough; clarify lookup by ID, case sensitivity, and behavior when not found.

## 3. Commonly used block tags

Block tags start with the `@` character and are usually placed after the description.

| Tag | Purpose |
|---|---|
| @param | Describes a parameter or type parameter |
| @return | Describes the return value |
| @throws | Describes an exception that may be thrown |
| @exception | Alternative name for `@throws` |
| @see | References another API or document |
| @since | Version in which the API was introduced |
| @deprecated | Explains a deprecated API and its replacement |
| @author | Author, if the project requires displaying it |
| @version | Documentation/implementation version if used by the project |
| @serial | Describes serialization of a class/field |
| @serialField | Describes a field in the serialized form |
| @serialData | Describes data written by a serialization method |

### @param

Describes each parameter by name:

~~~java
/**
 * Finds a customer.
 *
 * @param id stable customer identifier; must not be blank
 */
Optional<Customer> find(String id);
~~~

For generic types, use angle brackets in the tag:

~~~java
/**
 * Converts an input value.
 *
 * @param <T> type of the input value
 * @param input value to convert
 * @return converted value
 */
<T> String describe(T input);
~~~

### @return

Used for methods that return a value:

~~~java
/**
 * Returns the number of active customers.
 *
 * @return a non-negative count
 */
int count();
~~~

Do not use `@return` for methods returning `void`.

### @throws

Describes the condition under which an exception is thrown:

~~~java
/**
 * Finds a customer.
 *
 * @param id identifier to search for
 * @return matching customer, or an empty result
 * @throws IllegalArgumentException if id is blank
 */
Optional<Customer> find(String id);
~~~

Document observable behavior. Do not list all internal exceptions that are not part of the API contract.

### @see

Creates a reference to a class, method, or URL:

~~~java
/**
 * Provides customer lookup operations.
 *
 * @see Customer
 * @see java.util.Optional
 */
public interface CustomerService {
}
~~~

### @since

Used to record the version in which the API first appeared:

~~~java
/**
 * Returns the customer's display name.
 *
 * @return display name
 * @since 1.2
 */
String displayName();
~~~

Keep the format consistent with your library's versioning policy.

### @deprecated

When replacing an old API, explain why and how to replace it:

~~~java
/**
 * Returns the old customer code.
 *
 * @deprecated since 2.0; use {@link #id()} instead.
 */
@Deprecated(since = "2.0", forRemoval = true)
public String oldCode() {
    return id;
}
~~~

The `@Deprecated` annotation affects compiler warnings and tooling. The `@deprecated` block tag explains it to human readers. Use both when an API is genuinely deprecated.

### @inheritDoc

When overriding a method, you can inherit documentation from the parent class/interface method:

~~~java
/**
 * {@inheritDoc}
 */
@Override
public Optional<Customer> find(String id) {
    // implementation
}
~~~

Use this when the contract does not change. If the implementation adds specific constraints or behaviors, add a dedicated description instead of just copying a generic comment.

### Record components and constructors

A record can document its components at the record level:

~~~java
/**
 * An immutable customer record.
 *
 * @param id stable identifier
 * @param displayName name shown to users
 */
public record Customer(String id, String displayName) {
}
~~~

If you write separate Javadoc for the canonical constructor, you also need to document the constructor's parameters. With strict doclint, omitting `@param` on the constructor can produce warnings even if the record already documents the components at the type level.

## 4. Inline tags and content formatting

Inline tags appear within sentences, in the form `{@tag ...}`.

| Inline tag | Purpose |
|---|---|
| {@code ...} | Displays inline code and escapes HTML characters |
| {@literal ...} | Displays literal content without HTML processing |
| {@link ...} | Creates a hyperlink to an API |
| {@linkplain ...} | Creates a hyperlink with plain text |
| {@value ...} | Displays the value of a constant |
| {@inheritDoc} | Inherits description from the parent declaration |
| {@docRoot} | Relative path to the root of the generated docs |

Example:

~~~java
/**
 * Use {@code Optional.empty()} when no value exists.
 * See {@link java.util.Optional} for the result container.
 * The expression {@literal <T>} represents a type parameter.
 */
~~~

Use `{@code}` for class names, method names, constants, options, and code expressions. Use `{@literal}` when you need to print special characters such as `<`, `>`, or `{` without Javadoc interpreting them as HTML/tags.

### Linking to a specific method

~~~java
/**
 * Uses {@link CustomerService#find(String)} for lookup.
 */
~~~

The reference must point to an existing declaration with the exact signature. If a method is overloaded, specify parameter types to avoid ambiguous links.

### Links with readable labels

~~~java
/**
 * See {@linkplain CustomerService customer lookup API}.
 */
~~~

`{@link}` typically renders the API name in code style. `{@linkplain}` renders the label as regular text.

### Displaying constants with @value

~~~java
public final class Limits {
    /** Default retry count: {@value}. */
    public static final int DEFAULT_RETRIES = 3;

    private Limits() {
    }
}
~~~

Javadoc replaces `{@value}` with the constant's value. You can reference another constant using its qualified name.

## 5. HTML in Javadoc

Modern Javadoc generates HTML5. You can use valid HTML tags such as:

- `<p>` for paragraphs.
- `<ul>` and `<li>` for lists.
- `<pre>` and `<code>` for examples.
- `<strong>` or `<b>` for emphasis.
- `<a>` for external links when needed.
- `<table>`, `<tr>`, `<th>`, `<td>` for tables.

Example:

~~~java
/**
 * Validates the request.
 *
 * <p>Validation occurs in this order:</p>
 * <ol>
 *   <li>Check the identifier.</li>
 *   <li>Check the payload.</li>
 *   <li>Check authorization.</li>
 * </ol>
 */
~~~

Do not place block tags such as `@param` inside an unclosed HTML tag. Close tags properly and avoid obsolete HTML such as `<font>` or `<center>`.

### Java 17-compatible code blocks

~~~java
/**
 * Example:
 * <pre>{@code
 * CustomerService service = createService();
 * service.find("C-100").ifPresent(System.out::println);
 * }</pre>
 */
~~~

`{@code}` escapes HTML characters inside the code block.

### Snippet tag from JDK 18+

JDK 18 and later support `{@snippet}` to display source snippets with syntax highlighting and region highlighting capabilities:

~~~java
/**
 * Example:
 * {@snippet :
 * CustomerService service = ...;
 * service.find("C-100").ifPresent(System.out::println);
 * }
 */
~~~

You can place snippets in a separate file and reference them via the `file` attribute, using `--snippet-path` to specify the directory where snippets are located.

If your project must generate documentation using JDK 17's Javadoc, use `<pre>{@code ...}</pre>` instead of `{@snippet}` because JDK 17 does not support the snippet tag.

Snippets are displayed in the documentation; they do not automatically replace compile tests for examples. If examples must be runnable, keep code samples in source/test and verify them via the build.

## 6. Package, module, and project-wide documentation

### package-info.java

Create a `package-info.java` file in the package source directory:

~~~java
/**
 * Public API for customer lookup and validation.
 *
 * <p>Types in this package are intended for application integration.</p>
 *
 * @since 1.0
 */
package com.acme.api;
~~~

Javadoc generates `package-summary.html`. This is the place to explain the package's purpose, relationships between types, and shared conventions.

Do not only describe each class individually; package documentation helps readers understand the API as a cohesive group.

### module-info.java

With JPMS, you can write a Javadoc comment before the module declaration:

~~~java
/**
 * Customer API module.
 *
 * <p>Exports the public customer lookup contract.</p>
 */
module com.acme.customer.api {
    exports com.acme.api;
}
~~~

Javadoc can generate `module-summary.html` and package pages inside the module.

### overview.html

An overview file can describe the entire library:

~~~html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Customer API</title>
</head>
<body>
    <h1>Customer API</h1>
    <p>Public API for customer data access.</p>
</body>
</html>
~~~

Pass it with `-overview overview.html` when running `javadoc`. This file adds a project-level overview.

### doc-files

You can place images, diagrams, or static documents in a `doc-files` directory inside the package source. Javadoc copies those resources to the corresponding output directory. Use `-docfilessubdirs` if you want to copy subdirectories recursively.

Keep paths relative in HTML so resources continue to work after publishing.

## 7. Generating Javadoc directly via CLI

Suppose the project structure is:

~~~text
javadoc-demo/
├── src/
│   └── main/
│       └── java/
│           └── com/acme/api/
│               ├── package-info.java
│               ├── Customer.java
│               └── CustomerService.java
├── overview.html
└── build/
~~~

Basic command:

~~~bash
javadoc -d build/apidocs src/main/java/com/acme/api/*.java
~~~

For projects with subpackages, use `-sourcepath` and `-subpackages`:

~~~bash
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -notimestamp -d build/apidocs -sourcepath src/main/java -subpackages com.acme.api
~~~

Explanation:

| Option | Meaning |
|---|---|
| --release 17 | Uses Java 17-compatible API/source model |
| -encoding UTF-8 | Source file encoding |
| -docencoding UTF-8 | Generated HTML file encoding |
| -charset UTF-8 | Charset declared in HTML |
| -Xdoclint:all | Checks HTML, references, and tags |
| -Werror | Treats warnings as errors |
| -notimestamp | Omits hidden timestamps from output |
| -d | Output directory |
| -sourcepath | Where to find Java sources |
| -subpackages | Generates docs for the package and subpackages |

JDK 24 can generate documentation targeting release 17 using `--release 17`. This does not compile the source into class files; it selects the API/release context for the tool.

### Choosing visibility

Common options:

- `-public`: public API only.
- `-protected`: public and protected, usually the default.
- `-package`: adds package-private.
- `-private`: includes private members as well.

For documentation released to consumers, use `public` or `protected` according to your contract. Only use `-private` for internal documentation because it can expose implementation details that are not part of the public API.

### Classpath and module path

If the source depends on external libraries:

~~~bash
javadoc --class-path "lib/customer-model.jar;lib/validation.jar" ...
~~~

On Windows, semicolons separate path entries. Linux/macOS use colons.

For modular projects:

~~~bash
javadoc --release 17 --module-source-path src --module com.acme.customer.api -d build/apidocs
~~~

If you need to document multiple modules, list them with `--module` or configure the module source path accordingly.

### Linking to JDK and external libraries

You can link to dependency Javadoc:

~~~bash
javadoc -link https://docs.oracle.com/en/java/javase/17/docs/api/ ...
~~~

For offline environments, use `-linkoffline` and a pre-downloaded package list:

~~~bash
javadoc -linkoffline https://docs.oracle.com/en/java/javase/17/docs/api/ local-jdk17-docs ...
~~~

Ensure the URL and package list match the exact version. External links let readers navigate from your project's API to dependency documentation without copying all docs into the project.

### Overview and options file

You can use:

~~~bash
javadoc -overview overview.html ...
~~~

When the command is long, save options and source paths in a file and invoke:

~~~bash
javadoc @javadoc.options
~~~

This keeps build scripts readable and avoids command-line length limits on some shells.

## 8. Doclint and documentation quality

Doclint checks documentation comments, including HTML and links/tags. With modern JDKs, enable it explicitly:

~~~bash
-Xdoclint:all
~~~

Combine with:

~~~bash
-Werror
~~~

to fail the build if any warnings remain. This is a good way to prevent broken documentation from being published.

Commonly detected issues:

- Unclosed or improperly nested HTML tags.
- `@param` not matching a parameter.
- Missing return or exception descriptions in strict documentation.
- `{@link}` pointing to a non-existent symbol.
- Method reference with an incorrect signature.
- Unrecognized tag.
- Comment containing invalid markup.

### Separating content warnings from build warnings

Some projects may not be able to fix all warnings immediately. You can start with an appropriate doclint level and gradually raise the strictness. However, do not disable doclint entirely to hide link or HTML errors.

`-Xdoclint:all,-missing` can skip certain documentation completeness checks during a migration phase while keeping other checks active. Use this only when there is a plan to add the missing comments.

### Custom tags

Not every tag starting with `@` is automatically recognized by the Standard Doclet. If your project uses custom tags, register them with `-tag` or implement a `Taglet`.

Example of registering two custom block tags:

~~~bash
javadoc -tag 'apiNote:a:API Note:' -tag 'implSpec:a:Implementation Requirements:' ...
~~~

The syntax consists of the tag name, applicable locations, and displayed heading. For more complex logic, write a `Taglet` and provide it via `-taglet`/`-tagletpath`.

If a tag is not registered, Javadoc may report an unknown tag. For small projects, standard HTML headings or regular paragraphs are often more portable.

## 9. Integrating Javadoc with Maven

The Maven Javadoc Plugin generates HTML and a Javadoc JAR.

### Plugin configuration

In `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.11.2</version>
            <configuration>
                <release>17</release>
                <doclint>all</doclint>
                <failOnWarnings>true</failOnWarnings>
                <encoding>UTF-8</encoding>
                <docencoding>UTF-8</docencoding>
                <charset>UTF-8</charset>
                <notimestamp>true</notimestamp>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

### Generating HTML

~~~bash
mvn clean javadoc:javadoc
~~~

By default, the plugin generates HTML in:

~~~text
target/reports/apidocs/
~~~

Open `target/reports/apidocs/index.html` to view the result.

### Generating a Javadoc JAR

~~~bash
mvn javadoc:jar
~~~

The artifact is attached to the Maven project:

~~~text
target/javadoc-demo-1.0.0-javadoc.jar
~~~

You can publish the Javadoc JAR alongside the binary JAR in a release/deploy workflow:

~~~bash
mvn clean verify
mvn deploy
~~~

To ensure `mvn deploy` always attaches the Javadoc JAR, configure an execution of the `jar` goal in the appropriate lifecycle or invoke the goal in the release pipeline. Do not assume `mvn package` automatically creates a Javadoc JAR if the plugin is not bound.

### Linking the JDK API

You can configure:

~~~xml
<configuration>
    <links>
        <link>https://docs.oracle.com/en/java/javase/17/docs/api/</link>
    </links>
</configuration>
~~~

Check the build agent's network access or use an offline link package list if the build runs in an environment without Internet access.

## 10. Integrating Javadoc with Gradle

The Gradle Java Plugin creates the `javadoc` task. With `java-library`, you can attach a Javadoc JAR to the component publication.

### Configuring build.gradle

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.acme'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withJavadocJar()
}

tasks.withType(Javadoc).configureEach {
    options.encoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.docEncoding = 'UTF-8'
    options.addBooleanOption('Xdoclint:all', true)
    options.addBooleanOption('Werror', true)
}
~~~

### Running Javadoc

~~~bash
./gradlew clean javadoc
~~~

HTML output:

~~~text
build/docs/javadoc/index.html
~~~

Generate Javadoc JAR:

~~~bash
./gradlew javadocJar
~~~

Output:

~~~text
build/libs/javadoc-demo-1.0.0-javadoc.jar
~~~

`withJavadocJar()` creates the Javadoc JAR task and attaches the artifact to the Java component.

### Publishing with the Maven Publish Plugin

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.acme'
version = '1.0.0'

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

`from components.java` can publish the binary, sources, and Javadoc variants attached to the component. Configure repository/credentials according to your specific release environment.

### Checking tasks

~~~bash
./gradlew tasks --all
./gradlew javadoc --info
~~~

If the task reports `NO-SOURCE`, verify that sources are in `src/main/java` or that the source set is configured properly. Do not conclude Javadoc succeeded if the project had no sources to document.

## 11. Designing Javadoc for public APIs

### Describing behavior, not just the signature

Signature:

~~~java
Optional<Customer> find(String id);
~~~

A useful comment should clarify:

- Is the lookup case-sensitive?
- If not found, does it return `Optional.empty()` or throw an exception?
- Is `null` allowed?
- Are there caches or side effects?
- Are results guaranteed to be consistent across calls?

### Describing units and boundaries

For numeric APIs, state units and ranges clearly:

~~~java
/**
 * Sets the timeout.
 *
 * @param timeoutMillis timeout in milliseconds; must be positive
 */
void setTimeout(long timeoutMillis);
~~~

Do not leave users guessing between milliseconds or seconds, inclusive or exclusive.

### Describing thread-safety

If a class is shared across multiple threads, state clearly:

- Thread-safe.
- Immutable.
- Not thread-safe.
- Caller must synchronize.
- Whether methods can be called concurrently.

Do not claim thread-safety if the implementation or its dependencies do not guarantee it.

### Describing exceptions by condition

Instead of writing only:

~~~text
@throws IllegalArgumentException on error
~~~

write:

~~~text
@throws IllegalArgumentException if the identifier is blank
~~~

This helps callers know how to handle errors.

### Documenting generics and callbacks

Explain type parameters and callback contracts, including nullability, invocation count, thread context, and exception propagation if those factors are part of the API.

### Public API vs. internal API

Public documentation should be stable, easy to understand, and independent of implementation details. Internal documentation can use `-private` or a separate site; do not accidentally publish private implementation details.

## 12. Publishing and hosting Javadoc

There are two common distribution methods:

1. **Javadoc JAR:** published alongside the library in a Maven repository so IDEs can download it automatically.
2. **HTML site:** published as the full HTML directory to static hosting, an internal developer portal, or a documentation website.

For a Javadoc JAR, verify that the file contains `index.html`, package pages, search index, stylesheets, and required assets.

For an HTML site:

- Preserve the directory structure.
- Publish the exact root containing `index.html`.
- Ensure relative links are not rewritten incorrectly.
- Configure a dedicated URL/version for each release.
- Retain docs for older versions if consumers still use those APIs.
- Do not overwrite documentation of an older release with documentation of a new version.

### Versioned documentation

You can publish:

~~~text
docs/
├── 2.3/
│   └── index.html
├── 2.4/
│   └── index.html
└── latest/
    └── index.html
~~~

`latest` should point to a verified release. If reproducibility is needed, build documentation from the Git tag and store the Javadoc artifact alongside the binary release.

## 13. Reproducible Javadoc generation in CI

Integrate Javadoc into the pipeline:

~~~text
Checkout source/tag
       |
       v
Compile + tests
       |
       v
Javadoc + doclint
       |
       v
Verify links and snippets
       |
       v
Create Javadoc JAR
       |
       v
Publish binary + documentation
~~~

Principles:

- Pin JDK and Maven/Gradle plugin versions.
- Use UTF-8 encoding consistently.
- Enable doclint.
- Use `-Werror` or `failOnWarnings` once warnings have been addressed.
- Use `-notimestamp` if output without hidden timestamps is needed.
- Do not depend on external documentation that can change uncontrollably.
- Keep external links and offline package lists pinned to the exact version.
- Build docs from the exact same commit/tag as the binary.
- Store the Javadoc JAR together with checksums/provenance.

### Javadoc and API compatibility checks

Javadoc helps humans understand contracts, but it does not automatically detect every breaking API change. For libraries, you can add a binary/API compatibility checker in CI. The release process should check both signatures and documentation to ensure behavior/compatibility claims are accurate.

### Do not let documentation errors slip into releases

CI should fail if there are broken internal links, malformed HTML, or invalid tags. If the build has legacy warnings, record them and reduce warnings package by package instead of disabling checks altogether.

## 14. Java 17+ Lab: creating documentation for Customer API

Create the project:

~~~text
javadoc-demo/
├── pom.xml
└── src/main/java/com/acme/api/
    ├── package-info.java
    ├── Customer.java
    └── CustomerService.java
~~~

File `package-info.java`:

~~~java
/**
 * Public API for customer lookup and validation.
 *
 * <p>Types in this package are intended for application integration.</p>
 *
 * @since 1.0
 */
package com.acme.api;
~~~

File `Customer.java`:

~~~java
package com.acme.api;

import java.util.Objects;

/**
 * An immutable customer record.
 *
 * @param id stable customer identifier
 * @param displayName name shown to users
 * @since 1.0
 */
public record Customer(String id, String displayName) {
    /**
     * Creates a customer after validating its fields.
     *
     * @param id stable customer identifier
     * @param displayName name shown to users
     * @throws NullPointerException if either field is {@code null}
     * @throws IllegalArgumentException if either field is blank
     */
    public Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(displayName, "displayName");

        if (id.isBlank() || displayName.isBlank()) {
            throw new IllegalArgumentException(
                "Customer fields must not be blank"
            );
        }
    }
}
~~~

File `CustomerService.java`:

~~~java
package com.acme.api;

import java.util.Optional;

/**
 * Looks up customer records.
 *
 * <p>Implementations must be safe for concurrent calls.</p>
 *
 * @since 1.0
 */
public interface CustomerService {
    /**
     * Finds a customer by its stable identifier.
     *
     * @param id identifier to search for; must not be {@code null}
     * @return the customer if it exists, otherwise {@link Optional#empty()}
     * @throws IllegalArgumentException if {@code id} is blank
     */
    Optional<Customer> find(String id);

    /**
     * Returns the number of known customers.
     *
     * @return a non-negative count
     * @since 1.1
     */
    int count();
}
~~~

### Compile source

~~~bash
javac --release 17 -d build/classes src/main/java/com/acme/api/*.java
~~~

### Generate HTML via CLI

~~~bash
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -notimestamp -d build/apidocs -sourcepath src/main/java -subpackages com.acme.api
~~~

Main output:

~~~text
build/apidocs/index.html
build/apidocs/com/acme/api/package-summary.html
build/apidocs/com/acme/api/Customer.html
build/apidocs/com/acme/api/CustomerService.html
~~~

Open `build/apidocs/index.html` and verify:

- Package summary has the package description.
- `Customer` displays record components.
- Constructor displays params and throws.
- `CustomerService` displays method summary/details.
- `{@link Optional#empty()}` links to the corresponding Java API.
- No doclint warnings/errors remain.

### Generate via Maven

~~~bash
mvn clean javadoc:javadoc javadoc:jar
~~~

Verify:

~~~text
target/reports/apidocs/index.html
target/javadoc-demo-1.0.0-javadoc.jar
~~~

### Generate via Gradle

~~~bash
./gradlew clean javadoc javadocJar
~~~

Verify:

~~~text
build/docs/javadoc/index.html
build/libs/javadoc-demo-1.0.0-javadoc.jar
~~~

The commands above generate documentation from the same source. When using JDK 24 with `--release 17`, the output is generated by Javadoc 24, but the API/source model is constrained to Java 17.

## 15. Troubleshooting

### Javadoc cannot find package

Check `-sourcepath`, `-subpackages`, package declarations, and source folders. Make sure to pass the full package name, such as `com.acme.api`, instead of a filesystem path.

### Symbol not found in @link

Check whether the class/package is in the source or classpath/module path. For overloaded methods, declare full parameter types:

~~~java
{@link CustomerService#find(String)}
~~~

If the API is in another dependency, add the dependency to the classpath/module path and configure an external link when needed.

### Unknown tag

The tag might be an unregistered custom tag. Use `-tag` for simple block tags or a `Taglet` for custom logic. Check spelling and tag placement.

### Missing @param warning

The name in `@param` must match the parameter. For generic types, write `@param <T>`. For a record canonical constructor with its own Javadoc, document the constructor's parameters.

### Missing @return warning

Methods returning a value need a meaningful `@return`. Do not use this tag for `void`.

### Invalid or malformed HTML

Check opening/closing tags, nesting order, and `<` or `>` characters in prose. Use `{@code}` or `{@literal}` to escape special characters.

### Javadoc does not show private members

By default, Javadoc focuses on the public/protected API. Use `-private` for internal documentation, but review before publishing to avoid exposing implementation details.

### Snippet tag not recognized

`{@snippet}` requires Javadoc from JDK 18 or later. If the project generates docs with JDK 17, replace it with `<pre>{@code ...}</pre>` or upgrade the doc toolchain.

### Maven generates HTML but not the Javadoc JAR

Run the `javadoc:jar` goal or bind the goal to the release lifecycle. Check plugin executions and output in `target`.

### Gradle task reports NO-SOURCE

Check the source set and `src/main/java` directory. For multi-module projects, run the task on the right subproject and verify the declared sources.

### Javadoc links do not work

Check the external docs URL, version, and package-list/element-list. In offline CI, use `-linkoffline` with pre-downloaded documentation.

### Build fails due to -Werror

Read the specific warning and fix the comment, tag, or link. Do not remove `-Werror` just to make the build green if the warning reflects a public documentation error.

### HTML works locally but breaks after publishing

Check relative paths, hosting base path, `doc-files`, case-sensitive filenames, and directory structure. Keep the entire generated site intact rather than copying only `index.html`.

## 16. Pre-release Javadoc checklist

- Public API has complete documentation comments.
- Summary sentences are clear and stand on their own.
- Parameters, return values, and exceptions are documented.
- Generic type parameters are explained.
- Record components and canonical constructors are documented.
- Links to APIs use correct symbols/signatures.
- HTML tags are valid.
- Code snippets match the target JDK version.
- `package-info.java` contains package descriptions.
- `module-info.java` contains module descriptions if using JPMS.
- UTF-8 encoding is configured.
- Doclint is enabled.
- Warnings are resolved before release.
- Maven/Gradle plugin versions are pinned.
- HTML output is verified starting from `index.html`.
- Javadoc JAR is generated and has contents.
- External links are verified or have an offline fallback.
- Documentation is built from the same Git tag/commit as the binary.
- Checksums and release metadata are stored.
- Versioned documentation does not overwrite older release documentation.

## 17. Key terminology to remember

| Term | Meaning |
|---|---|
| Javadoc | Tool that generates API documentation from Java source |
| Documentation comment | Comment in the form `/** ... */` |
| Standard Doclet | Default processor that generates HTML |
| Doclint | Checker for HTML, tags, and references |
| Block tag | Tag starting with `@` inside a comment |
| Inline tag | Tag in the form `{@tag ...}` inside a sentence |
| @param | Describes a parameter/type parameter |
| @return | Describes the return value |
| @throws | Describes an exception |
| @deprecated | Guidance for a deprecated API |
| @inheritDoc | Inherits documentation from a parent API |
| {@link} | Links to an API |
| {@code} | Displays inline code |
| {@snippet} | Displays a source snippet, JDK 18+ |
| package-info.java | Package documentation |
| module-info.java | Module declaration and module documentation |
| Javadoc JAR | Archive containing HTML API documentation |
| Taglet | Extension for processing custom Javadoc tags |
| -sourcepath | Where to find Java sources |
| -link | Links to external Javadoc |
| -Xdoclint:all | Enables all doclint checks |
| -Werror | Turns warnings into errors |

Javadoc is valuable when it accurately explains the contract that consumers need to understand. Write comments close to declarations, clearly describe parameters/results/exceptions, organize package and module docs, generate HTML with the JDK toolchain, enable doclint, and publish the Javadoc JAR alongside the binary. When documentation is built from the same source tag and verified in CI, API docs become a reliable part of the release artifact.

## References

- Oracle JDK 24 — The javadoc Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html
- Oracle JDK 24 — Javadoc Tool Guide: https://docs.oracle.com/en/java/javase/24/javadoc/index.html
- Oracle JDK 24 — Documentation Comment Specification: https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/doc-comment-spec.html
- Apache Maven — Maven Javadoc Plugin: https://maven.apache.org/plugins/maven-javadoc-plugin/
- Gradle — Javadoc Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Java Library Plugin: https://docs.gradle.org/current/userguide/java_library_plugin.html
- OpenJDK — JEP 413: Code Snippets in Java API Documentation: https://openjdk.org/jeps/413
