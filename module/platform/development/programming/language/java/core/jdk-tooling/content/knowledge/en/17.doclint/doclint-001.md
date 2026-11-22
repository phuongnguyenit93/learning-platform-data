# What Is Doclint?

**Doclint** is a Javadoc comment quality checker built into the JDK's **javadoc** tool. It analyzes documentation comments in Java source code to detect issues such as invalid tag syntax, invalid HTML, links to non-existent types or members, inaccessible HTML content, and missing API documentation.

Doclint helps teams catch documentation errors at build time instead of waiting for readers to open published Javadoc pages only to find broken links or malformed code examples. You can think of Doclint as a static check dedicated to the documentation portion of your source code.

Command to explicitly check Doclint categories:

~~~bash
javadoc -Xdoclint:all -Werror \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Where:

- **javadoc** reads the source and generates HTML documentation.
- **-Xdoclint:all** enables all Doclint check categories, including checking for missing documentation.
- **-Werror** turns warnings into build errors.
- **-d build/docs** specifies the output directory for the generated Javadoc.

Doclint does not replace the compiler, unit tests, or content review. It checks the structure and references of documentation comments; developers still must verify that the descriptions match the actual behavior of the API.

## 1. Why Do We Need Doclint?

Javadoc is part of the public API. Library users often rely on the documentation to know what a method does, what its parameters mean, what it returns, and what exceptions may be thrown.

A comment can look reasonable while still containing errors:

~~~java
/**
 * Returns the display name.
 * @param user the account to display
 * @return the display name
 * @throws IOException if the account is missing
 */
public String displayName(User user) {
    return user.name();
}
~~~

If the method does not declare or cannot throw `IOException`, the `@throws` tag may be an invalid reference. If a comment contains a link to a non-existent type, readers will end up with a documentation page containing a broken link. If HTML opens a tag without closing it properly, the generated page structure can break.

Doclint helps detect issues in the following categories:

- **Syntax:** syntax of documentation comments and inline/block tags.
- **HTML:** HTML structure, tags, and attributes within comments.
- **Reference:** references to types, packages, fields, constructors, methods, or related documentation.
- **Accessibility:** accessibility issues in the HTML generated from comments.
- **Missing:** required comments or documentation elements that have not been provided.

These checks are useful for libraries, SDKs, frameworks, and any project that treats Javadoc as part of the product.

## 2. Where Does Doclint Run?

Doclint is built into the **Javadoc tool**, not a standalone command that developers typically invoke separately.

Typical workflow:

1. Developers write source code and documentation comments.
2. The compiler checks Java source when building the application.
3. Javadoc reads the source and parses declarations and comments.
4. Doclint checks the comments according to the enabled categories.
5. The standard doclet generates HTML pages if processing succeeds.
6. CI evaluates the exit code and warnings according to the build configuration.

Command to generate documentation and check it at the same time:

~~~bash
javadoc -Xdoclint:all \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

If you only want to run checks without keeping the HTML output, you can write the output to a temporary build directory and delete that directory in the pipeline's clean step. Javadoc still performs documentation processing to produce the output.

Doclint is not automatically invoked by every `javac` command. A successful `javac` run does not mean Javadoc comments are valid. To check documentation, you need to run `javadoc` or a build task that invokes it.

## 3. Which Documentation Comments Does Doclint Check?

Java has several kinds of comments:

~~~java
// Single-line comment

/* Ordinary block comment */

/**
 * Documentation comment.
 */
~~~

A documentation comment starts with `/**` and is placed before the declaration it describes. The Javadoc tool reads this type of comment to generate documentation.

Example:

~~~java
/**
 * Converts a name to uppercase.
 *
 * @param name the input name
 * @return the uppercase name
 */
public String uppercase(String name) {
    return name.toUpperCase();
}
~~~

Comments starting with `//` or `/*` are not Javadoc comments and are not exported into API documentation.

Doclint focuses on documentation comments and the references that Javadoc resolves from them. It does not thoroughly evaluate method body logic, performance, thread safety, or business correctness.

A comment can pass Doclint and still describe behavior inaccurately. For example, the comment may state that a method always returns a non-null value when the implementation can return `null`. That is a content error that requires review or testing, not a syntax error that Doclint can reliably catch.

## 4. The Five Doclint Check Categories

Javadoc supports five main categories. You can enable all of them with `-Xdoclint:all` or select individual categories.

| Category | What It Checks | Example Issues |
|---|---|---|
| syntax | Comment and tag syntax | Unclosed inline tag, tag used in the wrong place |
| html | HTML tags, attributes, and structure | Invalid tag, improper tag nesting |
| reference | References in Javadoc | Link to a non-existent class or method |
| accessibility | Accessibility of HTML content | Image missing alternative text |
| missing | Missing documentation | API requiring documentation has no comment or required tag |

### Syntax

The `syntax` category checks the structure of Javadoc comments and how block tags and inline tags are written.

Example of an error:

~~~java
/**
 * Returns the account name.
 * See {@link User
 */
public String name() {
    return "Ada";
}
~~~

The `link` inline tag is not closed with a curly brace. Fix:

~~~java
/**
 * Returns the account name.
 * See {@link User} for account details.
 */
public String name() {
    return "Ada";
}
~~~

Another syntax error is placing a block tag in an invalid position or writing incorrect tag parameter syntax.

### HTML

Javadoc comments can contain HTML for formatting content. The `html` category checks HTML issues recognized by Doclint.

Example of a list structure:

~~~java
/**
 * Supported formats:
 * <ul>
 *   <li>JSON</li>
 *   <li>XML</li>
 * </ul>
 */
public void export() {
}
~~~

Use valid HTML tags, close tags that require closing, and nest elements properly. For simple inline content, Javadoc tags such as `{@code ...}` are often easier to read and safer than manual HTML.

### Reference

The `reference` category checks links and references to declarations in source code or documentation that Javadoc can resolve.

Example:

~~~java
/**
 * Parses a value using {@link #parse(String)}.
 *
 * @see java.time.LocalDate
 */
public Result parseValue(String value) {
    return parse(value);
}
~~~

If the `parse` method does not exist or its signature is written incorrectly, Doclint can report an unresolved reference.

### Accessibility

The `accessibility` category checks certain accessibility issues in Javadoc HTML content.

For example, images need alternative text:

~~~html
<img src="diagram.png" alt="Diagram of the request flow">
~~~

For tables, headers and content structure need to be clear so assistive technologies can understand the relationships between parts. Avoid using HTML purely for visual styling while ignoring semantics.

### Missing

The `missing` category helps detect missing documentation for APIs or missing required documentation elements within the checked scope.

Example:

~~~java
public class AccountService {
    public Account find(String id) {
        return null;
    }
}
~~~

When `missing` checks are enabled, Javadoc can warn about undocumented public declarations. For methods, provide an appropriate description and tags such as `@param`, `@return`, or `@throws` where meaningful.

The scope of `missing` checks depends on access levels and the elements Javadoc is configured to document. The `-public`, `-protected`, `-package`, and `-private` options affect which declarations are included in the documentation.

## 5. Enabling and Disabling Doclint

Doclint options are extended options of the Javadoc tool. They use the `-X` prefix, and the JDK documentation notes that such options are subject to change between versions.

### Enabling recommended checks

~~~bash
javadoc -Xdoclint -d build/docs src/com/example/api/Greeter.java
~~~

`-Xdoclint` enables the set of checks recommended by Javadoc. If you need consistent builds across machines and want to explicitly check the `missing` category as well, specify `-Xdoclint:all`.

### Enabling all categories

~~~bash
javadoc -Xdoclint:all -d build/docs src/com/example/api/Greeter.java
~~~

This configuration enables `syntax`, `html`, `reference`, `accessibility`, and `missing`.

### Disabling all categories

~~~bash
javadoc -Xdoclint:none -d build/docs src/com/example/api/Greeter.java
~~~

Disabling Doclint can be useful when dealing with a legacy codebase that has many non-compliant comments, but it should not be used as a long-term fix. Turning off checks does not make the comments correct.

### Enabling specific categories

~~~bash
javadoc -Xdoclint:syntax,html,reference \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

The example above enables only three categories: `syntax`, `html`, and `reference`.

### Enabling all except one category

~~~bash
javadoc -Xdoclint:all,-missing \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

This form is useful when a project wants to check structure, HTML, links, and accessibility, but is not yet ready to require comments on all legacy APIs.

### Disabling a specific category

~~~bash
javadoc -Xdoclint:all,-html \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

This disables only `html` while keeping the other categories active. You should document the reason for the exception and plan to fix it if malformed HTML affects readers.

### Checking specific packages

Javadoc also supports package scoping:

~~~bash
javadoc -Xdoclint:all \
    -Xdoclint/package:com.example.api.* \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

A package specifier can be a full package name or a prefix ending with `.*` to include subpackages. You can prefix a package specifier with a minus sign to exclude that package from this scoped check.

Use package filters when a project is migrating incrementally. Check the help output of your JDK version to confirm the syntax and how filters combine with check categories.

## 6. Distinguishing -Xdoclint and -Werror

These two options do two different things:

- **-Xdoclint:** determines which kinds of issues in Javadoc comments are checked.
- **-Werror:** determines whether warnings fail the build.

Example:

~~~bash
javadoc -Xdoclint:all -Werror \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

If Doclint detects a warning, `-Werror` causes Javadoc to exit with an error status instead of just printing the warning and continuing as a build that tolerates warnings.

Not every issue is a warning. Some syntax or reference problems may be reported directly by Javadoc as errors. `-Werror` is especially useful for turning remaining warnings into a CI-blocking condition.

You can use `-Xmaxwarns` and `-Xmaxerrs` to limit the number of warnings/errors printed:

~~~bash
javadoc -Xdoclint:all -Xmaxwarns 100 -Xmaxerrs 100 \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Limiting the number of displayed lines does not mean the remaining errors are fixed. When working through a large codebase, fix issues in batches and re-run to verify.

## 7. Writing Javadoc to Avoid Doclint Errors

A good documentation comment should explain the contract of the declaration, not merely repeat the method name.

Example:

~~~java
/**
 * Creates a greeting for the supplied name.
 *
 * <p>The method trims leading and trailing whitespace before
 * constructing the greeting.
 *
 * @param name the name to include; must not be null or blank
 * @return a greeting that starts with {@code Hello,}
 * @throws IllegalArgumentException if name is null or blank
 * @since 1.0
 */
public static String greet(String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("name must not be blank");
    }
    return "Hello, " + name.trim() + "!";
}
~~~

Key points to keep in mind:

- Every tag has valid syntax.
- `@param` uses the exact parameter name.
- `@return` describes the return value for non-`void` methods.
- `@throws` references a valid exception and describes the throw condition.
- `{@code ...}` marks inline code snippets.
- HTML paragraphs are structured properly.
- The description does not claim behavior that contradicts the implementation.

### @param for generic types

For generic declarations, document type parameters using angle-bracket syntax:

~~~java
/**
 * Stores a value of the requested type.
 *
 * @param <T> the type of value stored
 */
public final class Box<T> {
}
~~~

If you omit the angle brackets or misspell the type parameter name, Javadoc may report a tag error or missing documentation.

### @return and @throws

Methods that return a value should have `@return` describing the meaning of that value:

~~~java
/**
 * Returns the number of active users.
 *
 * @return the number of active users; never negative
 */
public int activeCount() {
    return 0;
}
~~~

Methods that can throw exceptions should describe the conditions:

~~~java
/**
 * Loads an account.
 *
 * @param id account identifier
 * @return the matching account
 * @throws IllegalArgumentException if id is null or blank
 * @throws AccountNotFoundException if no account matches id
 */
public Account load(String id) {
    // implementation
}
~~~

Doclint can check type and tag references; it does not prove that exception conditions hold on every execution path. That still requires review and testing.

### @deprecated

When an API should no longer be used, clearly state the replacement:

~~~java
/**
 * Returns the old account label.
 *
 * @deprecated Use {@link #displayName()} instead.
 */
@Deprecated
public String oldLabel() {
    return displayName();
}
~~~

The `@Deprecated` annotation affects the compiler and tooling. The `@deprecated` tag provides an explanation for Javadoc readers. Both complement each other.

## 8. Checking HTML in Javadoc

HTML in documentation comments helps create paragraphs, lists, tables, and diagrams. However, a comment is not an arbitrary HTML page: Javadoc processes content according to the rules and HTML version supported by the standard doclet.

List example:

~~~java
/**
 * Supported transports:
 * <ul>
 *   <li>HTTP</li>
 *   <li>HTTPS</li>
 * </ul>
 */
public void connect() {
}
~~~

Table example:

~~~java
/**
 * <table>
 *   <caption>Retry policy</caption>
 *   <tr>
 *     <th scope="col">Attempt</th>
 *     <th scope="col">Delay</th>
 *   </tr>
 *   <tr>
 *     <td>1</td>
 *     <td>100 ms</td>
 *   </tr>
 * </table>
 */
public void retry() {
}
~~~

To reduce errors:

- Use HTML tags supported in Javadoc.
- Close tags and nest elements properly.
- Use `{@code ...}` for inline code.
- Use `{@literal ...}` when you want to display characters that have HTML meaning without interpreting them as markup.
- Avoid obsolete HTML tags or invalid attributes.
- Use `alt` text for images.
- Use headings in a logical order; do not use headings just to make text larger.
- Use `caption` and headers for tables when appropriate.

`{@literal}` example:

~~~java
/**
 * The expression {@literal <T>} represents a type parameter.
 */
public void describeType() {
}
~~~

Doclint checks the structure it recognizes, but it cannot replace visually inspecting the HTML pages in a browser or performing a full accessibility audit with dedicated tools.

## 9. Checking Links and References

Javadoc supports linking to declarations using inline tags:

~~~java
/**
 * Uses {@link java.time.LocalDate} to represent a calendar date.
 */
public void dateExample() {
}
~~~

Linking to a member in the same class:

~~~java
/**
 * Parses the supplied text. See {@link #parseStrict(String)}.
 */
public Result parse(String text) {
    return parseStrict(text);
}
~~~

Link with a custom display label:

~~~java
/**
 * See {@link java.time.LocalDate LocalDate documentation}.
 */
public void dateExample() {
}
~~~

Related tags:

- **`{@link ...}`:** creates an inline link.
- **`{@linkplain ...}`:** creates an inline link rendered in plain text font.
- **`{@see ...}`:** creates a See Also section.
- **`@throws`:** references an exception that may be thrown.
- **`@param`:** references a parameter or type parameter.
- **`@return`:** describes the return value.

If a link points to an overloaded method, include a clear enough signature for Javadoc to resolve it:

~~~java
/**
 * Delegates to {@link #parse(String, boolean)}.
 */
public Result parse(String text) {
    return parse(text, false);
}
~~~

If linking to external documentation, you can configure links with `-link` or `-linkoffline`. These options control how Javadoc locates external reference documentation; they do not fix broken internal links.

Example:

~~~bash
javadoc -Xdoclint:all \
    -link https://docs.oracle.com/en/java/javase/17/docs/api/ \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

When building offline or using downloaded API documentation, use `-linkoffline` with the documentation URL and the location of the `package-list` or `element-list` matching the linked documentation set.

## 10. Scope of Checked Declarations

Javadoc has options that determine the access level of declarations included in the documentation:

| Option | Documentation Scope |
|---|---|
| -public | Only `public` |
| -protected | `public` and `protected`; this is the common default |
| -package | `public`, `protected`, and package-private |
| -private | All, including `private` |

Example:

~~~bash
javadoc -private -Xdoclint:all \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

When expanding the scope to `private`, Javadoc processes many more internal declarations. This can produce many more `missing` warnings if the project does not document private members.

Declaration scope and Doclint categories are two separate configuration axes:

- Doclint categories determine which kinds of issues to check.
- Visibility options determine which declarations are included in the documentation.
- Package filters limit which packages are checked.

When setting up CI, explicitly specify all three so every developer has the same expectations for the results.

## 11. Complete Practical Example with Java 17+

This example creates a small API with valid Javadoc, generates HTML, and runs a program to verify behavior. The same source is used for both `javac` and `javadoc`.

Structure:

~~~text
doclint-demo/
└── src/
    └── com/
        └── example/
            └── doclint/
                ├── Greeter.java
                └── Main.java
~~~

### Greeter.java

~~~java
package com.example.doclint;

/**
 * Creates simple greeting messages.
 *
 * <p>This class is a small example of an API with complete
 * documentation comments.
 *
 * @since 1.0
 */
public final class Greeter {

    private Greeter() {
    }

    /**
     * Creates a greeting for the supplied name.
     *
     * <p>Leading and trailing whitespace are removed before
     * the greeting is returned.
     *
     * @param name the name to include; must not be null or blank
     * @return a greeting that starts with {@code Hello,}
     * @throws IllegalArgumentException if name is null or blank
     * @see String#trim()
     * @since 1.0
     */
    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }
}
~~~

### Main.java

~~~java
package com.example.doclint;

/**
 * Runs the greeting example.
 */
public final class Main {

    private Main() {
    }

    /**
     * Prints a greeting for the first command-line argument.
     *
     * @param args command-line arguments; the first item is a name
     */
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Greeter.greet(name));
    }
}
~~~

### Compile the source

From the `doclint-demo` root directory:

~~~bash
mkdir -p build/classes
javac --release 17 -d build/classes \
    src/com/example/doclint/Greeter.java \
    src/com/example/doclint/Main.java
~~~

### Run the program

~~~bash
java -cp build/classes com.example.doclint.Main Java
~~~

Exact output:

~~~text
Hello, Java!
~~~

### Run Javadoc with full Doclint

~~~bash
javadoc --release 17 \
    -Xdoclint:all \
    -Werror \
    -d build/docs \
    src/com/example/doclint/Greeter.java \
    src/com/example/doclint/Main.java
~~~

If the comments are valid and there are no other warnings, the command exits successfully and generates documentation in `build/docs`.

Some output files:

~~~text
build/docs/
├── index.html
├── allclasses-index.html
├── allpackages-index.html
└── com/
    └── example/
        └── doclint/
            ├── Greeter.html
            ├── Main.html
            └── package-summary.html
~~~

The exact set of files may vary depending on the JDK version and Javadoc options. Open `Greeter.html` to inspect the actual content, links, and formatting.

## 12. Examples of Erroneous Comments and How to Fix Them

### Link to a non-existent declaration

Erroneous comment:

~~~java
/**
 * Uses {@link #formatName(String)}.
 */
public String displayName(String name) {
    return name.trim();
}
~~~

If there is no `formatName(String)` method, the `reference` category may report an unresolved link.

Fix by pointing to an actual method:

~~~java
/**
 * Uses {@link #displayName(String)}.
 */
public String displayName(String name) {
    return name.trim();
}
~~~

Or describe the behavior without creating a link if no link is needed.

### Wrong parameter name

Erroneous comment:

~~~java
/**
 * Returns the greeting.
 *
 * @param username the name
 */
public String greet(String name) {
    return "Hello, " + name;
}
~~~

The name in `@param` must match the actual parameter. Fix:

~~~java
/**
 * Returns the greeting.
 *
 * @param name the name
 * @return the greeting
 */
public String greet(String name) {
    return "Hello, " + name;
}
~~~

### Missing return documentation

If the `missing` category is enabled, a public method that returns a value without describing the result may trigger a warning. Add `@return` with a specific meaning, not just `"the result"`.

### HTML missing accessibility information

Comment with an image:

~~~java
/**
 * <img src="architecture.png">
 */
public void start() {
}
~~~

Add `alt` text:

~~~java
/**
 * <img src="architecture.png" alt="Application component architecture">
 */
public void start() {
}
~~~

`alt` text should describe the purpose or information of the image in context. If the image is purely decorative, the appropriate handling may differ depending on the content and accessibility requirements.

### Improperly nested HTML

Erroneous comment:

~~~java
/**
 * <ul>
 *   <p>Supported modes</p>
 *   <li>Fast</li>
 * </ul>
 */
public void modes() {
}
~~~

A list should contain list items. Fix:

~~~java
/**
 * Supported modes:
 * <ul>
 *   <li>Fast</li>
 *   <li>Safe</li>
 * </ul>
 */
public void modes() {
}
~~~

Specific messages may differ across JDKs, but the principle is to use valid, semantic HTML structure.

## 13. Integrating Doclint into Builds and CI

Doclint should run as a dedicated step in the documentation generation pipeline. Example:

~~~text
Checkout source
      |
      v
Compile Java source
      |
      v
Run unit tests
      |
      v
Run Javadoc + Doclint
      |
      v
Publish documentation artifact
~~~

If Javadoc fails, the pipeline should stop before publishing the documentation.

### Maven

The Maven Javadoc Plugin can configure Doclint via plugin configuration. Conceptual configuration example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.11.2</version>
    <configuration>
        <doclint>all</doclint>
        <failOnWarnings>true</failOnWarnings>
    </configuration>
</plugin>
~~~

Parameter names and option mappings can depend on the plugin version. Check the documentation for the Maven Javadoc Plugin version you use and run the `javadoc` goal to confirm the options are actually passed to the Javadoc tool.

You can run:

~~~bash
mvn javadoc:javadoc
~~~

If the project generates Javadoc for multiple modules or multiple executions, the plugin configuration must be placed in the right execution and profile.

### Gradle

With the Gradle Java plugin, the `Javadoc` task can receive options via `StandardJavadocDocletOptions`:

~~~groovy
tasks.withType(Javadoc).configureEach {
    options.addBooleanOption("Xdoclint:all", true)
    options.addBooleanOption("Werror", true)
}
~~~

Option syntax depends on the Gradle version and how `StandardJavadocDocletOptions` represents options. Check task output or run Javadoc directly to be sure the JDK receives the expected options.

Another approach is passing options via `options.addStringOption` when the plugin expects a value. Do not configure multiple option forms simultaneously in a way that causes duplicate arguments.

### CI

In CI, you should:

- Use the JDK version supported by the project.
- Run Javadoc with explicit check categories.
- Enable `-Werror` once the team is ready to handle warnings.
- Keep warning/error logs so developers know the source file and line number.
- Run the same configuration on developer machines and in CI.
- Save the generated documentation as an artifact if review is needed.
- Avoid disabling Doclint entirely just to make the pipeline green.

For legacy codebases, you can enable `syntax`/`html`/`reference` first, gradually address `missing` and `accessibility`, and then raise it to `all`. Record exceptions and when they will be removed.

## 14. Diagnosing Doclint Errors

### Javadoc exits with an error while javac succeeds

This is normal: the compiler checks Java source, while Javadoc/Doclint checks documentation comments and their references. Run Javadoc separately to view the errors.

### Unsure which category a warning belongs to

Read the message and the file/line location. Try running each category individually:

~~~bash
javadoc -Xdoclint:syntax -d build/docs src/com/example/api/Greeter.java
javadoc -Xdoclint:html -d build/docs src/com/example/api/Greeter.java
javadoc -Xdoclint:reference -d build/docs src/com/example/api/Greeter.java
javadoc -Xdoclint:accessibility -d build/docs src/com/example/api/Greeter.java
javadoc -Xdoclint:missing -d build/docs src/com/example/api/Greeter.java
~~~

This helps narrow down the error type. Once fixed, re-run all categories together.

### Too many missing warnings in a legacy codebase

You can check the remaining categories first:

~~~bash
javadoc -Xdoclint:all,-missing \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Then plan to add comments for the API and enable `missing` in CI. Do not let the exception remain indefinitely.

### Links to JDK APIs are not resolved

Check that the reference has the correct package, class, and member. If external documentation is generated separately, configure `-link` or `-linkoffline` to the matching version's documentation set. Do not fix one broken link by disabling all reference checking.

### Javadoc cannot find types in dependencies

Place dependencies on the appropriate classpath or module path. Example:

~~~bash
javadoc --class-path "lib/api.jar" \
    -Xdoclint:all \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

For modular sources, use `--module-path` and the corresponding module options. Doclint does not download dependencies on behalf of your build tool.

### Warning output varies across JDKs

Doclint categories are extended options and may change. Check the help output of your current JDK:

~~~bash
javadoc -X
javadoc --help
~~~

Include the JDK version in build metadata so differences between developer environments and CI can be explained.

## 15. Limitations of Doclint

Doclint is very useful, but it is not a comprehensive evaluator of documentation quality.

It does not guarantee that:

- Descriptions in comments match actual runtime behavior.
- Code examples in comments compile or run correctly.
- Usage instructions cover all scenarios.
- Content has a clear writing style or suits the target audience.
- Links to external websites always work.
- Javadoc pages render well across all browsers.
- All website accessibility requirements are met.
- The API is well-designed or backward compatible.

Therefore, combine:

1. Doclint to catch structural errors.
2. Compiler and tests to verify behavior.
3. Content review to verify accuracy and clarity.
4. Generated HTML inspection to check links, tables, images, and layout.
5. Dedicated accessibility tools when documentation is an important user-facing interface.

Doclint is an automated safety net, not a substitute for writing useful documentation.

## 16. Workflow for Writing and Checking Javadoc Effectively

1. Write documentation comments right next to the public API.
2. Use the first sentence to describe the purpose of the declaration.
3. Describe parameters, return values, and exceptions according to the actual contract.
4. Use `@param`, `@return`, `@throws`, `@since`, and `@deprecated` in the appropriate context.
5. Use `{@code}` for identifiers or short code snippets.
6. Use `{@link}` when linking genuinely helps the reader.
7. Use structured HTML and pay attention to accessibility.
8. Run `javadoc -Xdoclint:all` during development.
9. Fix warnings and errors at the source instead of disabling check categories.
10. Use `-Werror` in CI once warnings are under control.
11. Review the generated HTML pages and check links.
12. Document the JDK version alongside the project's Doclint configuration.

Doclint helps keep Javadoc consistent with source code and catches errors before documentation is published. By understanding the five check categories, knowing how to enable/disable scopes properly, and integrating Javadoc into CI, teams can maintain reliable API documentation across many code changes.

## References

- [The javadoc Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- [Javadoc Tool User's Guide — Doclint](https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/doc-comment-spec.html)
- [Javadoc Tool User's Guide](https://docs.oracle.com/en/java/javase/24/javadoc/)
- [Maven Javadoc Plugin](https://maven.apache.org/plugins/maven-javadoc-plugin/)
- [Gradle Javadoc task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.javadoc.Javadoc.html)
