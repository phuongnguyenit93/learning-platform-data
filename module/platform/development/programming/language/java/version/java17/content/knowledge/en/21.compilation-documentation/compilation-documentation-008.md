# DocLint and Fixing Link and Parameter Documentation Errors in Java 17

## 1. How does DocLint help check API documentation?

Javadoc does more than convert comments into HTML pages. While generating documentation, the tool also analyzes comment structure, tags, references to classes/methods, and parts of HTML syntax to catch errors that can make documentation hard to read or leave links broken.

In JDK 17, this checking mechanism is called **DocLint**. It can detect issues such as:

- References in `{@link ...}` that do not resolve to an element.
- `@param` tags naming a parameter absent from the declaration.
- Missing documentation comments or tags according to enabled check groups.
- Javadoc tags placed in invalid positions or using invalid syntax.
- Invalid HTML inside comments or accessibility issues.
- Documentation tags and content mismatching the method/class declaration.

DocLint catches structural defects in API documentation right inside the build pipeline. It does not judge whether an explanation is domain-accurate, readable enough, or faithful to runtime behavior. Authors remain responsible for ensuring descriptions are accurate.

In Java 17, use the `javadoc` tool bundled with the JDK and configure DocLint to match your project's strictness level. No external plugin is required to enable basic checks.

After this lesson, learners should be able to:

1. Understand which error categories DocLint checks.
2. Run Javadoc with `-Xdoclint` and resolve warnings/errors.
3. Write `{@link}` and `@see` pointing accurately to classes, methods, constructors, or fields.
4. Fix links to overloaded methods using exact parameter signatures.
5. Write complete `@param`, `@return`, and `@throws` tags matching declarations.
6. Configure links to external Javadoc using `-link` or `-linkoffline`.
7. Integrate documentation checks into build/CI pipelines without hiding warnings.

## 2. DocLint in JDK 17

### 2.1. DocLint runs during Javadoc generation

Simple example:

~~~bash
javadoc -d build/docs -Xdoclint:all -sourcepath src/main/java -subpackages com.example
~~~

This command instructs Javadoc to generate documentation for packages under `com.example` with all DocLint check groups enabled. If the source tree contains malformed comments, Javadoc reports warnings or errors with exact locations so authors can fix them.

DocLint is built into the Javadoc tool. It is not a runtime library that applications import into source code.

### 2.2. Check groups

JDK 17 supports the following DocLint groups:

| Group | Scope |
|---|---|
| `accessibility` | Certain accessibility issues in HTML/Javadoc content |
| `html` | HTML syntax and structure inside comments |
| `reference` | References to symbols, classes, members, and related tags |
| `syntax` | Syntax of Javadoc block tags and inline tags |
| `missing` | Missing documentation comments or tags |

By default, Javadoc runs all check groups except `missing`. To enforce stricter checks, use:

~~~bash
javadoc -Xdoclint:all ...
~~~

To temporarily exclude `missing` while keeping the other checks active:

~~~bash
javadoc -Xdoclint:all,-missing ...
~~~

In projects with substantial legacy code, the `missing` group can produce a large volume of warnings. You can enable it incrementally to pay down documentation debt, yet you should not disable DocLint completely just to silence the build.

### 2.3. Disabling DocLint

The option:

~~~bash
javadoc -Xdoclint:none ...
~~~

turns off DocLint checks. This is not a fix. Use it only for a specific operational reason with an alternative verification plan; for new projects or public APIs, keep checks enabled.

### 2.4. Checking by package

Javadoc provides `-Xdoclint/package:` to scope DocLint checks by package. Group and package syntax must match JDK 17 rules:

~~~bash
javadoc -Xdoclint:all -Xdoclint/package:com.example.api ...
~~~

When adopting DocLint on a large codebase, start with public API packages and expand outward. Keep configuration consistent in CI so results do not depend on a developer's local machine.

## 3. Generating Javadoc with strict configuration

### 3.1. Basic command example

Given source tree:

~~~text
src/main/java/
  com/example/api/
    Calculator.java
    UserService.java
~~~

Run:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -sourcepath src/main/java \
  -Xdoclint:all \
  -subpackages com.example.api
~~~

Explanation:

- `--release 17`: generate documentation against target Java version/APIs 17.
- `-d build/docs`: output directory for generated HTML.
- `-sourcepath`: root directory for source packages.
- `-Xdoclint:all`: enable all DocLint groups, including missing comments/tags.
- `-subpackages`: select the root package and its subpackages to document.

The output directory must be writable. When generating documentation in a build pipeline, clean old output via the build tool before regenerating so stale HTML for deleted classes is not left behind.

### 3.2. Turning warnings into build errors

Javadoc supports `-Werror` to fail the build on any warning:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -sourcepath src/main/java \
  -Xdoclint:all \
  -Werror \
  -subpackages com.example.api
~~~

This is helpful in CI once existing warnings are resolved. Enabling `-Werror` immediately on a codebase with many legacy warnings can cause widespread failures; clean up documentation debt within clear scopes before enforcing strict failure.

### 3.3. Dependencies on classpath or module path

If Javadoc needs to resolve types from dependencies:

- For classpath dependencies, provide `-classpath`.
- For modular dependencies, provide `--module-path` and matching module options.

Example:

~~~bash
javadoc --release 17 \
  -classpath "lib/dependency.jar" \
  -d build/docs \
  -Xdoclint:all \
  -sourcepath src/main/java \
  -subpackages com.example
~~~

If a dependency is missing, references in comments may fail to resolve even when class names look correct. Verify Javadoc runs with the project's real dependency graph.

## 4. Writing parameter descriptions with @param

### 4.1. Names in @param must match declarations

Method example:

~~~java
/**
 * Finds a profile by its identifier.
 *
 * @param userId unique identifier of the user
 * @return the profile if found, or {@code null} if absent
 */
public UserProfile findUser(String userId) {
    // ...
}
~~~

The name `userId` in `@param` must match the parameter name in the declaration. If the parameter is renamed to `id` without updating Javadoc, DocLint warns that `@param` does not exist.

Incorrect:

~~~java
/**
 * Finds a profile.
 * @param userID the user identifier
 */
public UserProfile findUser(String userId) {
    // ...
}
~~~

`userID` and `userId` are distinct identifiers. Java is case-sensitive; Javadoc requires exact casing too.

### 4.2. Every parameter needs a meaningful description

Avoid repeating the parameter name:

~~~java
/**
 * @param timeout timeout
 */
~~~

Better descriptions state meaning, units, valid ranges, or rules:

~~~java
/**
 * @param timeout maximum wait time in milliseconds; {@code 0} means no limit
 */
~~~

Do not invent a rule like "`0` means infinite" unless the API actually behaves that way. Descriptions must match the method's real contract.

### 4.3. Generic type parameters use angle brackets

For generic classes:

~~~java
/**
 * A container holding a single typed value.
 *
 * @param <T> the type of stored value
 */
public final class Box<T> {
    // ...
}
~~~

For generic methods:

~~~java
/**
 * Returns the first element of the list.
 *
 * @param <T> the element type in the list
 * @param values the list to inspect
 * @return the first element
 * @throws IllegalArgumentException if the list is empty
 */
public static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values is empty");
    }
    return values.get(0);
}
~~~

`@param <T>` documents the type parameter; `@param values` documents the method parameter. Never omit `<` and `>` when documenting generic type parameters.

### 4.4. Constructors also use @param

~~~java
/**
 * Creates a client with a configured timeout.
 *
 * @param endpoint service base URI to connect to
 * @param timeout maximum wait duration per request
 * @throws NullPointerException if {@code endpoint} or {@code timeout} is null
 * @throws IllegalArgumentException if timeout is non-positive
 */
public ApiClient(URI endpoint, Duration timeout) {
    // ...
}
~~~

Constructors do not have `@return` because they have no method return value.

## 5. Writing @return and @throws accurately against contracts

### 5.1. @return for methods producing a value

~~~java
/**
 * Adds two integers.
 *
 * @param left the first operand
 * @param right the second operand
 * @return the sum of the two operands
 */
public int add(int left, int right) {
    return left + right;
}
~~~

`@return` descriptions should explain what the result means rather than simply writing "the return value". For methods returning collections or Optionals, clarify empty/null behavior and whether returned collections are modifiable if part of the contract.

### 5.2. Never add @return to void methods

Incorrect:

~~~java
/**
 * Logs a message.
 *
 * @return nothing
 */
public void log(String message) {
    // ...
}
~~~

`void` methods return nothing; omit `@return`. If the method has significant side effects, describe them in the main comment text.

### 5.3. @throws describes triggering conditions

~~~java
/**
 * Divides two integers.
 *
 * @param dividend the numerator
 * @param divisor the denominator
 * @return integer quotient of the division
 * @throws ArithmeticException if {@code divisor} is zero
 */
public int divide(int dividend, int divisor) {
    return dividend / divisor;
}
~~~

`@throws` should describe the actual condition causing the exception. Document unchecked exceptions too, even though they do not appear in the `throws` clause, whenever they are a significant part of the API contract.

Do not document an exception solely because a particular implementation happens to throw it outside the public contract, unless API consumers need to rely on that behavior and it is guaranteed.

### 5.4. @throws and the throws clause are distinct

- `throws IOException` in the declaration is part of the method signature and affects callers and compilation.
- `@throws IOException` in Javadoc explains when the API throws that exception.

Both should stay consistent, yet neither replaces the other.

## 6. Fixing internal links with @link

### 6.1. Linking to a class or interface

~~~java
/**
 * Request processor backed by {@link java.net.http.HttpClient}.
 */
public final class RequestProcessor {
}
~~~

If the type is already imported, you can use the simple name in the reference when Javadoc can resolve it:

~~~java
import java.net.http.HttpClient;

/**
 * Request processor backed by {@link HttpClient}.
 */
~~~

For public API documentation, qualified names clarify the type's origin and avoid confusion with same-named classes in other packages.

### 6.2. Linking to a member of the current class

~~~java
/**
 * Calls {@link #connect()} before sending a request.
 *
 * @see #close()
 */
public void send() {
    // ...
}
~~~

`#connect()` points to a member of the current class. Use `#` for members instead of writing names as plain text.

### 6.3. Linking to a member of another class

~~~java
/**
 * Uses {@link java.time.Duration#ofSeconds(long)} to build a timeout.
 */
public Duration timeout() {
    return Duration.ofSeconds(5);
}
~~~

References consist of the owning type, member name, and parameter types when needed to disambiguate overloads.

### 6.4. Linking to a specific overload

When a class has multiple methods with the same name, specify the parameter types:

~~~java
/**
 * See {@link String#substring(int, int)} to extract a slice of characters.
 */
~~~

If you write only `{@link String#substring}`, Javadoc may fail to disambiguate overloads or link to an unintended one. For overloaded APIs, always supply full parameter types so references are unambiguous.

Parameter types in references must follow Javadoc reference syntax using resolvable package/type names. Whenever ambiguous, use fully qualified type names.

### 6.5. Adding a display label

~~~java
/**
 * See {@link java.util.Optional#orElse(Object) how to provide a default value}.
 */
~~~

Text after the reference becomes the display label for readers. Use `{@linkplain ...}` if you want the label rendered in regular body font instead of code style.

### 6.6. Linking to a field or constructor

Example:

~~~java
/**
 * The default value is stored in {@link #DEFAULT_TIMEOUT}.
 *
 * @see #ApiClient(URI, Duration)
 */
~~~

For constructors, use the class name and parameter list. For fields, use the field name; if multiple contexts share a field name, qualify with the owning class.

## 7. Using @see and related inline tags

### 7.1. @see

`@see` generates a See Also entry at the bottom of the Javadoc page:

~~~java
/**
 * Reads configuration from a UTF-8 file.
 *
 * @see java.nio.file.Files#readString(java.nio.file.Path, java.nio.charset.Charset)
 */
~~~

Use `@see` when pointing readers to related APIs or resources without inserting inline links mid-sentence.

### 7.2. {@link} and {@linkplain}

- `{@link ...}` inserts an inline link formatted in code font.
- `{@linkplain ...}` inserts a link with plain text label styling.

Example:

~~~java
/**
 * Uses {@link List#size()} to obtain the count and
 * {@linkplain java.util.Collections Collections utilities} for collection operations.
 */
~~~

### 7.3. {@code} and {@literal}

Use `{@code ...}` for variable names, expressions, or short snippets:

~~~java
/**
 * The default value is {@code Duration.ofSeconds(5)}.
 */
~~~

Use `{@literal ...}` to render literal text without interpreting HTML or Javadoc markup. Example:

~~~java
/**
 * The expression must satisfy {@literal x < y}.
 */
~~~

Do not leave raw `<` or `>` characters in HTML where they could be parsed as tags. For multi-line code blocks, use:

~~~java
/**
 * <pre>{@code
 * var client = HttpClient.newHttpClient();
 * var response = client.send(request, BodyHandlers.ofString());
 * }</pre>
 */
~~~

### 7.4. {@inheritDoc}

When overriding, inherit the parent class or interface contract:

~~~java
/**
 * {@inheritDoc}
 */
@Override
public void close() {
    // ...
}
~~~

`{@inheritDoc}` works well when the parent API already specifies the full contract. If the implementation introduces additional preconditions or behaviors, document them explicitly instead of inheriting blindly.

## 8. Fixing HTML errors in Javadoc

DocLint includes an HTML check group. Javadoc comments are converted into HTML, so markup must be valid and cleanly structured.

### 8.1. Properly closed and nested tags

Incorrect:

~~~java
/**
 * Steps:
 * <ul>
 *   <li>Initialize
 *   <li>Execute
 * </ul>
 */
~~~

Correct:

~~~java
/**
 * Steps:
 * <ul>
 *   <li>Initialize</li>
 *   <li>Execute</li>
 * </ul>
 */
~~~

Modern HTML allows omitting closing tags on certain elements, yet writing explicit closing tags improves readability and avoids unnecessary markup errors. For void tags such as `<br>` or `<img>`, follow the HTML syntax accepted by Javadoc.

### 8.2. Avoid arbitrary presentational HTML tags

Prefer simple HTML tags supported by Javadoc:

- `<p>` for paragraphs.
- `<ul>` and `<ol>` for lists.
- `<code>` or `{@code ...}` for inline code.
- `<pre>{@code ...}</pre>` for code blocks.
- `<table>`, `<tr>`, `<th>`, `<td>` for tables when genuinely needed.

Avoid non-standard tags, deprecated attributes, or browser-specific markup. DocLint catches many errors yet cannot guarantee arbitrary custom HTML renders identically everywhere.

### 8.3. Alt text for images

If Javadoc includes images, provide meaningful alternative text:

~~~java
/**
 * <img src="diagram.png" alt="Request processing flow diagram">
 */
~~~

Alt text enables screen readers to convey image content and satisfies accessibility checks.

### 8.4. Avoid broken HTML escaping

To display special characters safely, use the appropriate inline tag:

~~~java
/**
 * Use {@code a < b} to compare two values.
 */
~~~

Or `{@literal ...}` to preserve characters verbatim. Never leave unclosed HTML snippets in comments expecting Javadoc to fix them.

## 9. Linking to external Javadoc

### 9.1. The -link option

When documentation references external libraries, Javadoc can generate hyperlinks to those external doc sites via `-link`:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -Xdoclint:all \
  -link https://docs.oracle.com/en/java/javase/17/docs/api/ \
  -sourcepath src/main/java \
  -subpackages com.example
~~~

The URL must point to the root of the external Javadoc containing valid package/module list metadata. Javadoc reads that metadata to construct links to matching types and members.

### 9.2. The -linkoffline option

When the build environment has no internet access, use `-linkoffline`:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -Xdoclint:all \
  -linkoffline https://library.example/docs/api/ /opt/javadoc/library-api \
  -sourcepath src/main/java \
  -subpackages com.example
~~~

The first argument is the base URL embedded in generated hyperlinks. The second argument is the local directory holding `element-list` or `package-list` metadata for the external Javadoc. That local path must exist with the structure Javadoc expects.

### 9.3. Verifying external links

`-link` tells Javadoc how to generate external hyperlinks. It does not guarantee the destination website stays live, matches your version, or keeps the same member anchors after a dependency upgrade.

When upgrading dependencies:

1. Update the corresponding documentation URL version.
2. Check package/module list metadata.
3. Regenerate Javadoc.
4. Open a few generated links to confirm targets resolve.
5. Separately verify hand-written URLs in comments.

Do not point Java 17 documentation at another JDK version's docs simply because the URL is shorter. Match the documentation version to the API version your project compiles against.

## 10. Common DocLint errors and fixes

### 10.1. `reference not found`

Example:

~~~java
/**
 * See {@link #connectNow()}.
 */
public void connect() {
}
~~~

There is no `connectNow()` member in the current class, so the reference cannot resolve.

**Fix:** verify the member name, owning class, overload signature, and dependency path. To link to an external URL, use proper HTML link syntax or valid Javadoc references rather than inventing nonexistent member names.

### 10.2. `@param name not found`

Example:

~~~java
/**
 * @param userID the user identifier
 */
public void load(String userId) {
}
~~~

**Fix:** change `userID` to `userId`, or update the tag name to match the method signature if parameters changed.

### 10.3. Missing parameter description

A tag with a name and an empty or unhelpful description lowers documentation quality and can be flagged by the missing check depending on the error form:

~~~java
/**
 * @param limit
 */
~~~

Change to:

~~~java
/**
 * @param limit maximum number of elements to return; must be greater than zero
 */
~~~

If `limit` allows zero or negative values with special semantics, document the actual rule accurately.

### 10.4. Incorrect @param syntax for type parameters

Incorrect:

~~~java
/**
 * @param T element type
 */
class Store<T> {
}
~~~

Correct:

~~~java
/**
 * @param <T> type of stored elements
 */
class Store<T> {
}
~~~

### 10.5. @return on a void method

Remove `@return` from `void` methods. Describe side effects in the opening text of the comment.

### 10.6. Ambiguous link to overloaded methods

When a method has multiple overloads, specify the signature:

~~~java
/**
 * See {@link String#substring(int, int)}.
 */
~~~

Do not rely on an unqualified reference that matches multiple methods.

### 10.7. Unclosed or improperly nested HTML tags

Verify open/close tags, nesting order, and special characters. Use code inline tags for code snippets instead of raw HTML.

### 10.8. External link missing metadata

If Javadoc cannot locate package-list/element-list, check the root URL, doc version, and `-link`/`-linkoffline` arguments. For offline builds, provide valid local metadata.

### 10.9. Flood of missing warnings

When enabling `-Xdoclint:all` on legacy codebases, many public members may lack comments or tags. Plan documentation additions by package or public API surface; do not delete tags or disable DocLint globally to mask the problem.

## 11. Complete example: fixing Javadoc for an API

### 11.1. Version with errors

~~~java
package com.example.api;

import java.time.Duration;
import java.net.URI;

/**
 * Client for the service.
 * <p>
 * See {@link #sendRequest()} to send.
 */
public final class ApiClient {
    /**
     * Creates a client.
     * @param url address
     * @param timeout
     * @return client
     */
    public ApiClient(URI endpoint, Duration timeout) {
    }

    /**
     * Sends request.
     * @param body content
     * @return
     */
    public String send(String body) {
        return body;
    }
}
~~~

Problems:

- Link `#sendRequest()` does not exist.
- `@param url` does not match parameter `endpoint`.
- `@param timeout` lacks a description.
- Constructors have no return value, so `@return` is invalid.
- `@return` on `send` lacks a description.
- Method descriptions are overly vague.

### 11.2. Fixed version

~~~java
package com.example.api;

import java.net.URI;
import java.time.Duration;

/**
 * Client that sends text requests to an HTTP service.
 *
 * <p>The client uses the endpoint supplied at construction and enforces
 * the configured timeout. See {@link java.net.http.HttpClient} for Java's
 * low-level HTTP API.
 */
public final class ApiClient {

    /**
     * Creates a client for the specified endpoint.
     *
     * @param endpoint base URI of the service; must not be {@code null}
     * @param timeout maximum wait duration per request; must be positive
     * @throws NullPointerException if endpoint or timeout is {@code null}
     * @throws IllegalArgumentException if timeout is not positive
     */
    public ApiClient(URI endpoint, Duration timeout) {
    }

    /**
     * Sends text content to the service.
     *
     * @param body request payload to send; must not be {@code null}
     * @return response body as a string
     * @throws NullPointerException if body is {@code null}
     * @throws java.io.IOException if an I/O error occurs while sending or reading the response
     * @throws InterruptedException if the waiting thread is interrupted
     * @see #ApiClient(URI, Duration)
     */
    public String send(String body)
            throws java.io.IOException, InterruptedException {
        return body;
    }
}
~~~

This example illustrates writing comments matching real signatures and references. In real implementations, exceptions and null rules must match actual code; never copy sample descriptions if method behavior differs.

### 11.3. Running DocLint

With the source tree at `src/main/java/com/example/api/ApiClient.java`:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -sourcepath src/main/java \
  -Xdoclint:all \
  -Werror \
  com.example.api
~~~

With `-subpackages`, you can generate docs for all subpackages. When Javadoc reports errors, read the file and line number, fix the source comment, and rerun. Never edit generated HTML inside `build/docs`; the next run overwrites output from source.

## 12. Organizing Javadoc in modular projects

### 12.1. Package documentation

Use `package-info.java` to describe a package:

~~~java
/**
 * Public API for sending and receiving requests.
 *
 * <p>Types in this package are designed for invocation by other modules.
 */
package com.example.api;
~~~

### 12.2. Module documentation

In modularized projects, place the module description inside `module-info.java`:

~~~java
/**
 * Module providing the client API for sending service requests.
 */
module com.example.client {
    requires java.net.http;
    exports com.example.api;
}
~~~

Module Javadoc tells consumers which packages the module exports and which module dependencies it requires. Documentation should match `requires`, `exports`, and the real API.

### 12.3. Do not confuse package docs with member docs

`package-info.java` describes package scope; it does not replace comments on public classes, constructors, and methods. Public APIs still require parameter, return, and exception descriptions on each member.

## 13. Integrating DocLint into builds and CI

### 13.1. Principles

A sound documentation pipeline should:

1. Use the same JDK 17 matching the target environment.
2. Generate Javadoc from the current build's source code.
3. Enable agreed-upon DocLint check groups.
4. Fail on warnings once the project meets its quality bar.
5. Keep output in build directories without committing generated HTML unless publishing static docs intentionally.
6. Preserve Javadoc logs so developers can locate exact lines to fix.

### 13.2. Running from the terminal

Example command:

~~~bash
javadoc --release 17 \
  -d build/docs \
  -sourcepath src/main/java \
  -Xdoclint:all \
  -Werror \
  -subpackages com.example
~~~

In PowerShell, use backticks for line continuation or put the entire command on one line. Verify source paths and root packages match your project structure.

### 13.3. Maven or Gradle

In Maven/Gradle, configure the Javadoc task/plugin to pass `-Xdoclint:all` and `-Werror` consistently rather than letting developers run ad-hoc commands. Exact configuration syntax depends on the plugin/build tool version; consult the documentation for the version pinned by your project.

Do not add custom plugins or tasks merely to suppress warnings. The goal is a reproducible build command using the same JDK and flags locally and in CI.

### 13.4. Addressing documentation debt in phases

If a codebase has many undocumented public APIs:

- Start with new packages or frequently changing APIs.
- Fix broken links and mismatched tags first because they actively mislead readers.
- Add parameter, return, and throws descriptions.
- Expand `missing` scope package by package.
- Once warnings are resolved, enable `-Werror` to prevent regressions.

Do not set `-Xdoclint:none` permanently merely because initial warning counts are high.

## 14. What DocLint does not verify for you

DocLint checks documentation structure, not content correctness. It cannot guarantee:

- Algorithm descriptions match implementation.
- Timeout descriptions or measurement units are accurate.
- `@throws` conditions cover every runtime path.
- Code examples produce right results or compile in every context.
- External website links remain reachable.
- Documentation never contradicts other docs.
- API descriptions satisfy user needs.

Therefore, review docs alongside source code, test important examples, and inspect generated HTML. DocLint catches machine-verifiable mistakes; explanation quality still requires authors and reviewers.

## 15. Practice exercises

### Exercise 1 — Enable DocLint

Generate Javadoc for a Java 17 package using:

~~~bash
javadoc --release 17 -Xdoclint:all -d build/docs -sourcepath src/main/java -subpackages com.example
~~~

Record warnings/errors and classify them under `html`, `reference`, `syntax`, `accessibility`, or `missing`.

### Exercise 2 — Fix @param

Create a method with parameters `userId` and `timeout`. Write a `@param` tag with mismatched casing, run DocLint, then fix the name and write meaningful descriptions for each parameter.

### Exercise 3 — Generic type parameters

Write class `Repository<T>` and method `<R> R map(...)`. Add `@param <T>`, `@param <R>`, and tags for regular parameters. Explain the difference between the two tag kinds.

### Exercise 4 — Link to overloads

Create two overloads `find(String)` and `find(String, boolean)`. Write two `{@link}` references targeting each overload explicitly. Try omitting parameter signatures and observe Javadoc's behavior.

### Exercise 5 — External links

Create docs referencing an external library API. Configure `-link` pointing to the dependency's Javadoc; then test `-linkoffline` using local metadata in an offline environment.

### Exercise 6 — @return and @throws

Write one value-returning method and one `void` method. Add valid tags for each; try adding `@return` to the `void` method and fix it per the warning.

### Exercise 7 — Strict CI

Run Javadoc with `-Xdoclint:all -Werror`. Fix warnings in a sample package until the build succeeds. Explain why disabling DocLint does not count as completing the exercise.

## 16. Completion criteria

Learners master this lesson when they can:

1. Explain the role and limitations of DocLint in JDK 17.
2. Name the groups `accessibility`, `html`, `reference`, `syntax`, and `missing`.
3. Run Javadoc with `-Xdoclint:all` and understand the effect of `-Werror`.
4. Fix `reference not found` by checking class, member, and overload signatures.
5. Write `@param` with exact names for both normal parameters and generic type parameters.
6. Write `@return` and `@throws` matching method contracts.
7. Use `{@link}`, `{@linkplain}`, `{@code}`, `{@literal}`, `{@inheritDoc}`, and `@see` properly.
8. Fix HTML/Javadoc markup and supply alt text for images.
9. Configure `-link` or `-linkoffline` for external API documentation.
10. Integrate DocLint into build/CI without treating disabled checks as fixes.

## 17. Official documentation

- [Java SE 17 Javadoc Tool Guide](https://docs.oracle.com/en/java/javase/17/javadoc/): guide to generating documentation and Javadoc options.
- [Java SE 17 Javadoc Tool — DocLint](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): `-Xdoclint` syntax, check groups, and related options.
- [Java SE 17 Javadoc Tags](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html): comment syntax, block tags, inline tags, and references.
- [Java SE 17 Javadoc Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html#references): rules for referencing program elements.
- [Java SE 17 man page — javadoc](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): `-link`, `-linkoffline`, `-Werror`, and command-line options.

**Remember:** DocLint detects syntax, HTML, reference, and tag errors in Javadoc comments. To fix broken links, verify the exact class/member and overload signature; to fix parameter docs, match declared names exactly and state real meaning. Enable `-Xdoclint:all` in builds, turn on `-Werror` when ready, and keep reviewing content because DocLint does not verify explanation accuracy.
