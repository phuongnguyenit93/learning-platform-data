# Checking Javadoc Quality in Java

Checking Javadoc is the process of verifying that API documentation is generated properly, is complete, has valid links, and accurately describes the behavior observable by library users. Running the `javadoc` command successfully is only the first step. Reliable API documentation must also pass checks for syntax, tags, HTML, references, API scope, consistency with source code, and visual inspection of the generated HTML output.

Verification can be divided into four layers:

1. **Automated checks with Javadoc/DocLint:** detect problematic comments, tags, HTML, and references.
2. **API scope checks:** ensure the right public packages, classes, and members are included in the documentation.
3. **Content checks:** cross-check descriptions, parameters, return values, exceptions, nullability, thread-safety, and examples against actual behavior.
4. **Generated HTML checks:** inspect the overview page, navigation, links, accessibility, and documentation version.

Javadoc cannot prove on its own that every descriptive sentence matches program logic. Combining DocLint with code review, tests, and HTML inspection reduces the risk of releasing inaccurate or incomplete documentation.

The toolchain used to verify this article reports `javadoc 24.0.2`. Options may differ between JDKs; check `javadoc --version`, `javadoc --help`, and `javadoc --help-extra` in your actual build environment.

## 1. What Do Javadoc and DocLint Check?

`javadoc` reads documentation comments in source files and generates HTML using the standard doclet. DocLint is a built-in set of checks in this tool that helps detect issues in documentation comments and HTML.

Commonly used DocLint groups:

| Group | What it checks | Example error |
|---|---|---|
| `accessibility` | Certain HTML accessibility requirements | Table missing proper header structure, image missing description |
| `html` | HTML syntax and structure | Invalid tag, improperly nested or unclosed element |
| `missing` | Missing documentation or required block tags | Public method missing description, missing `@param` or `@return` |
| `reference` | References to types/members | `{@link}` pointing to a nonexistent method or wrong overload |
| `syntax` | Documentation comment and tag syntax | Malformed tag, unclosed inline tag |

Enable all groups:

~~~text
javadoc -Xdoclint:all ...
~~~

Enable only specific groups:

~~~text
javadoc -Xdoclint:html,reference,syntax ...
~~~

Exclude a group:

~~~text
javadoc -Xdoclint:all,-missing ...
~~~

Only disable a check group when the project has a clear reason and a documented exception. For public APIs, keep `missing`, `reference`, `html`, and `syntax` checks enabled in regular builds.

Group names and detailed options may vary by JDK. Consult the help output of your exact toolchain rather than assuming all versions support the same flags.

## 2. Turning Warnings into Errors with `-Werror`

By default, Javadoc may continue generating HTML even when warnings are found. This is useful when migrating a legacy codebase, but it is not suitable if CI needs to prevent flawed documentation from reaching a release.

Use `-Werror` to turn warnings into a failed run:

~~~text
javadoc -Xdoclint:all -Werror ...
~~~

Combining both options means:

- `-Xdoclint:all`: enables all documentation check groups.
- `-Werror`: exits with an error status if any warnings remain.

You can use `-Xmaxerrs` and `-Xmaxwarns` to adjust the number of errors/warnings printed when investigating a large run. They do not fix the content and do not replace addressing the root cause.

When introducing DocLint to a long-lived project, you can start with `-Xdoclint:all` to inventory issues, fix them by group, and then enable `-Werror` once the desired quality bar is met. Avoid keeping a configuration that ignores warnings indefinitely without a remediation plan.

## 3. Checking for Missing Documentation

A public API can compile cleanly even without Javadoc. Therefore, a successful `javac` build does not prove that API docs are complete.

Check the following elements:

- Public classes, interfaces, enums, and records have a description stating their role.
- Public constructors explain object creation preconditions and inputs.
- Public methods explain behavior, parameters, return values, and exceptions.
- Generic type parameters have `@param <T>` or an appropriate description.
- Public constants have a description of their meaning and units, if applicable.
- Packages have package-level documentation if the package is part of the API.
- Modules have descriptions and appropriate export information when the project is modular.

### 3.1. Checking Tags Against the Method Signature

Example method:

~~~java
/**
 * Searches for a product by its SKU.
 *
 * @param sku the exact SKU to search for
 * @return the matching product, or an empty result if none exists
 * @throws NullPointerException if {@code sku} is {@code null}
 */
public Optional<Product> findBySku(String sku) {
    // implementation
}
~~~

Compare the documentation with the signature:

| Element | What to check |
|---|---|
| `@param sku` | Name must match the actual parameter; description accurately states format and input preconditions |
| `@return` | Accurately describes the result, including empty/null cases |
| `@throws` | States actual conditions under which the exception can be thrown |
| Description | Describes behavior, search rules, and side effects if any |

For `void` methods, do not write `@return`. For constructors, do not write `@return`. For generic methods, check both type parameters and regular parameters.

### 3.2. Checking Parameter and Type Parameter Names

A common mistake is renaming a parameter in source code while forgetting to update `@param`, or writing `@param <T>` when the type parameter has a different name.

Example source:

~~~java
public Product find(String productSku) {
    // implementation
}
~~~

The documentation must use `@param productSku`, not `@param sku`.

When refactoring an API signature, recheck block tags, examples, snippets, and all links pointing to that overload.

### 3.3. Checking Exception Descriptions

Do not merely list exception names. Describe the conditions that trigger them and the information callers need to handle them.

Example:

~~~java
/**
 * Opens a catalog file.
 *
 * @param path the path to the catalog file
 * @return the loaded catalog
 * @throws IOException if the file cannot be read or parsed
 * @throws NullPointerException if {@code path} is {@code null}
 */
public Catalog open(Path path) throws IOException {
    // implementation
}
~~~

Cross-check against the implementation and tests. If the method actually throws `IllegalArgumentException` on invalid format as well, the documentation should reflect that if it is part of the committed API behavior.

## 4. Checking Javadoc Links and References

References commonly appear in `{@link}`, `{@linkplain}`, `@see`, `{@value}`, and `{@inheritDoc}`.

Example of valid links:

~~~java
/**
 * Uses {@link Product#sku()} to identify the product.
 *
 * @see Catalog#findBySku(String)
 */
public final class ProductIndex {
}
~~~

Errors to look for:

- Incorrect class or package name.
- Nonexistent or renamed member.
- Link to the wrong overload due to missing parameter types.
- Reference to a private member that is inappropriate for public API documentation.
- `{@inheritDoc}` used where no suitable parent/interface documentation exists.
- External link pointing to the wrong documentation version.

The DocLint `reference` group helps catch many invalid internal references. When an error occurs, check the package, class name, member name, and signature. For overloads, specify parameter types explicitly:

~~~text
{@link Catalog#findBySku(String)}
{@link Catalog#findById(long)}
~~~

### 4.1. Checking Links to External Documentation

Use `-link` to link to published Javadoc:

~~~text
javadoc --release 17 -link https://docs.oracle.com/en/java/javase/17/docs/api/ ...
~~~

Javadoc needs the package/element list metadata at the documentation URL to generate links. For offline builds, use `-linkoffline` with a pre-downloaded metadata directory:

~~~text
javadoc -linkoffline https://docs.example.com/api/ external-api-docs ...
~~~

Verify that the URL matches the library or Java SE version, the metadata belongs to the right documentation set, the generated HTML points to the expected target pages, and CI either has access to the target documentation or uses offline metadata.

DocLint does not replace checking all external HTTP links. A URL can be syntactically valid while the server has moved, requires login, or no longer exists. Use a link checker suited to your documentation workflow to verify URLs after HTML generation.

## 5. Checking HTML and Accessibility

Javadoc generates HTML from descriptions, inline tags, and block tags. DocLint can catch many HTML errors, but you still need to inspect the resulting pages.

Check that:

- Headings follow a logical order without arbitrary level jumps.
- Tables have clear header rows and column descriptions.
- Lists are formatted properly as list elements.
- Code blocks are readable and not truncated.
- HTML contains no invalid tags or unsafe markup.
- Links have meaningful labels rather than just "click here".
- Custom images or icons have alternative text when needed.
- Pages remain readable on small screens and when zoomed.
- Keyboard navigation and assistive technologies work to the required level.

If the project adds custom stylesheets, scripts, headers, footers, or a custom doclet, check those as well. Errors can appear in custom templates even when source comments are valid.

You can use a standalone HTML validator or accessibility checker in the documentation pipeline if release standards require it. Interpret results against the HTML standard that Javadoc is currently generating; avoid mistaking warnings from an outdated validator for real bugs in a modern standard doclet.

## 6. Checking the API Scope Included in Documentation

Javadoc has different visibility levels. By default it typically shows public and protected APIs; `-public` shows only public, while `-private` also shows private members.

| Option | Scope |
|---|---|
| `-public` | Public types/members only |
| `-protected` | Public and protected; typically the default |
| `-package` | Public, protected, and package-private |
| `-private` | All, including private |

For an API reference aimed at library users, avoid using `-private` unless you specifically intend to publish internal documentation. Doing so can expose implementation structure, internal component names, or details that are not part of a supported contract.

Check the packages passed to the command:

~~~text
javadoc -sourcepath src -subpackages com.example.publicapi -d docs
~~~

`-subpackages` recurses through the specified package and its subpackages. If a package is omitted, the overview page may miss APIs users expect even when source comments are complete.

For named modules, review `--module`, `--module-path`, `--module-source-path`, and `--show-packages`, `--show-types`, `--show-members`, `--show-module-contents`. Ensure the public documentation accurately reflects the packages exported in `module-info.java`.

## 7. Checking Semantic Accuracy

This part requires a reviewer who understands the API. DocLint checks structure and references, but cannot tell whether a descriptive sentence matches the business logic.

Cross-check each description against code and tests:

| Topic | Questions to verify |
|---|---|
| Input | Is null accepted? Are strings case-sensitive? Are there length limits? |
| Output | Can it return empty/null? Is the result stable or ordered? |
| Mutability | Is the returned object mutable? Is it a snapshot or a live view? |
| Side effects | Does the method mutate state, write files, send requests, or update a cache? |
| Exceptions | What conditions trigger checked/unchecked exceptions? |
| Thread-safety | Can it be called concurrently? Must the caller synchronize? |
| Resources | Who owns the stream, connection, or executor? Who must close it? |
| Performance | Are there blocking calls, retries, timeouts, or notable costs to be aware of? |
| Compatibility | Since which version has the API existed? Is it deprecated or has behavior changed? |

For example, if the documentation states that a method returns an immutable snapshot, verify that the implementation actually makes a copy. If the documentation says lookup is case-insensitive, check both the implementation and tests with SKUs in different cases.

Do not document temporary implementation details as though they were a stable contract. Conversely, do not omit observable behavior that callers must rely on.

## 8. Checking Examples and Code Snippets

Code in Javadoc usually takes three forms:

- Inline code using `{@code ...}`.
- Inline or external snippets using `{@snippet ...}`.
- Longer examples stored in separate files and included via a snippet path or guide documentation.

Javadoc does not automatically guarantee that every code block in a comment is a standalone compilable program. For instructional examples, verify them with the compiler/tests or run them in a sample project.

Checklist for each example:

1. Imports are complete, or omitted packages/imports are clearly noted.
2. Class names, method names, and parameters exist in the documented API version.
3. The code compiles with the target Java release.
4. Stdout or illustrated results match the program.
5. Deprecated APIs are not used without explanation.
6. Important exceptions or resource cleanup are not omitted.
7. The example does not rely on undocumented files, services, or environment variables.

If long snippets are stored separately, verify those files are included in the build and updated alongside the API. Avoid letting Javadoc examples and test code drift into two divergent copies.

## 9. Workflow to Generate and Check Javadoc for Java 17

The following example creates a small catalog library. We will compile the source code, generate API docs with strict DocLint, and inspect the generated HTML.

Project structure:

~~~text
project/
  src/
    com/
      example/
        catalog/
          package-info.java
          Product.java
          Catalog.java
        app/
          Main.java
  out/
  docs/
~~~

### 9.1. Package Documentation

File `src/com/example/catalog/package-info.java`:

~~~java
/**
 * Public API for product catalog lookup.
 *
 * <p>Use {@link com.example.catalog.Catalog} to search for products.
 *
 * @since 1.0
 */
package com.example.catalog;
~~~

### 9.2. Product Class

File `src/com/example/catalog/Product.java`:

~~~java
package com.example.catalog;

import java.util.Objects;

/**
 * Represents a product identified by a stock keeping unit (SKU).
 *
 * <p>The SKU and name are immutable after construction.
 *
 * @since 1.0
 */
public final class Product {
    private final String sku;
    private final String name;

    /**
     * Creates a product.
     *
     * @param sku the non-blank stock keeping unit
     * @param name the non-blank display name
     * @throws NullPointerException if either argument is {@code null}
     * @throws IllegalArgumentException if either argument is blank
     */
    public Product(String sku, String name) {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(name, "name");
        if (sku.isBlank() || name.isBlank()) {
            throw new IllegalArgumentException("values must not be blank");
        }
        this.sku = sku;
        this.name = name;
    }

    /**
     * Returns this product's SKU.
     *
     * @return the stock keeping unit
     */
    public String sku() {
        return sku;
    }

    /**
     * Returns this product's display name.
     *
     * @return the display name
     */
    public String name() {
        return name;
    }
}
~~~

### 9.3. Catalog Class

File `src/com/example/catalog/Catalog.java`:

~~~java
package com.example.catalog;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * Provides read-only lookup operations for a collection of products.
 *
 * <p>The catalog rejects duplicate SKUs and does not change after construction.
 *
 * @since 1.0
 */
public final class Catalog {
    private final Map<String, Product> products;

    /**
     * Creates a catalog from the supplied products.
     *
     * @param initialProducts products to include
     * @throws NullPointerException if the collection or an element is {@code null}
     * @throws IllegalArgumentException if two products have the same SKU
     */
    public Catalog(Collection<Product> initialProducts) {
        Objects.requireNonNull(initialProducts, "initialProducts");
        Map<String, Product> index = new HashMap<>();
        for (Product product : initialProducts) {
            Objects.requireNonNull(product, "product");
            if (index.putIfAbsent(product.sku(), product) != null) {
                throw new IllegalArgumentException(
                        "duplicate SKU: " + product.sku());
            }
        }
        this.products = Map.copyOf(index);
    }

    /**
     * Finds a product by its exact SKU.
     *
     * <p>The lookup is case-sensitive and does not modify this catalog.
     *
     * @param sku the SKU to search for
     * @return the matching product, or an empty result if none exists
     * @throws NullPointerException if {@code sku} is {@code null}
     * @see Product#sku()
     */
    public Optional<Product> findBySku(String sku) {
        return Optional.ofNullable(
                products.get(Objects.requireNonNull(sku, "sku")));
    }

    /**
     * Returns the number of products in this catalog.
     *
     * @return the number of products
     */
    public int size() {
        return products.size();
    }
}
~~~

### 9.4. Sample Program

File `src/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.catalog.Catalog;
import com.example.catalog.Product;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        Catalog catalog = new Catalog(List.of(
                new Product("A-100", "Keyboard"),
                new Product("B-200", "Mouse")));

        System.out.println("Catalog size: " + catalog.size());
        Product found = catalog.findBySku("A-100").orElseThrow();
        System.out.println("Found: " + found.sku() + " - " + found.name());
        System.out.println("Missing: " + catalog.findBySku("X-999").isEmpty());
    }
}
~~~

Compile from the `project` directory:

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out, docs | Out-Null
javac --release 17 -encoding UTF-8 -d out `
    src\com\example\catalog\package-info.java `
    src\com\example\catalog\Product.java `
    src\com\example\catalog\Catalog.java `
    src\com\example\app\Main.java
~~~

macOS/Linux:

~~~sh
mkdir -p out docs
javac --release 17 -encoding UTF-8 -d out \
    src/com/example/catalog/package-info.java \
    src/com/example/catalog/Product.java \
    src/com/example/catalog/Catalog.java \
    src/com/example/app/Main.java
~~~

Run the program:

~~~text
java -cp out com.example.app.Main
~~~

Stdout:

~~~text
Catalog size: 2
Found: A-100 - Keyboard
Missing: true
~~~

### 9.5. Generating Javadoc with Strict Checks

From the `project` directory:

~~~text
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example.catalog
~~~

Explanation:

- `--release 17`: uses the Java 17-compatible platform APIs and source level.
- `-encoding UTF-8`: reads source files as UTF-8.
- `-docencoding UTF-8`: writes HTML as UTF-8.
- `-charset UTF-8`: declares the charset in HTML.
- `-Xdoclint:all`: enables documentation check groups.
- `-Werror`: fails the build if any warnings remain.
- `-d docs`: output directory.
- `-sourcepath src`: root of the source tree.
- `-subpackages com.example.catalog`: generates documentation for the catalog package and its subpackages.

The command generates documentation only for the catalog package. The application package `com.example.app` is not a published API in this example.

## 10. Inspecting the Generated HTML

After the Javadoc command finishes, check the main files:

~~~text
docs/index.html
docs/com/example/catalog/package-summary.html
docs/com/example/catalog/Product.html
docs/com/example/catalog/Catalog.html
~~~

Auxiliary filenames and index pages may differ across JDK versions or doclet configurations. Check the pages actually generated in the output.

On Windows PowerShell:

~~~powershell
Get-ChildItem -Recurse docs | Select-Object FullName, Length
~~~

macOS/Linux:

~~~sh
find docs -type f -print
~~~

Open `docs/index.html` in a browser and check:

- The overview page displays the expected package.
- The package page includes the description from `package-info.java`.
- The `Product` page includes the constructor, `sku()`, and `name()`.
- The `Catalog` page includes the constructor, `findBySku(String)`, and `size()`.
- The `Product#sku()` reference navigates to the right member.
- Summaries render properly in both summary and detail sections.
- Block tags render properly under Parameters, Returns, Throws, and Since where present.
- There are no encoding issues with Vietnamese diacritics or broken code blocks.

Do not check only the exit code. A run can produce HTML while still missing packages due to an incorrect `-sourcepath` or `-subpackages`.

## 11. Testing Error Detection with Intentional Mistakes

To understand DocLint, try introducing a small documentation mistake and re-running the check command.

Example of documentation not matching the signature:

~~~java
/**
 * Finds a product.
 *
 * @param product the product SKU
 * @return the product if found
 */
public Optional<Product> findBySku(String sku) {
    // implementation
}
~~~

Here `@param product` does not match the parameter name `sku`. Depending on the check and JDK, DocLint may report a missing tag for the real parameter or an unmatched tag.

Example of a broken link:

~~~java
/**
 * Uses {@link Product#skuCode()} to identify a product.
 */
public final class Catalog {
}
~~~

If `skuCode()` does not exist, the `reference` group will detect the invalid reference.

Example of invalid HTML:

~~~java
/**
 * <p>Returns a product from the catalog.
 * <ul>
 *   <li>Searches by SKU.
 * </p>
 */
public Optional<Product> findBySku(String sku) {
    // implementation
}
~~~

Invalid list and paragraph structure can be caught by the `html` group.

After fixing them, change `@param product` to `@param sku`, change the link to `{@link Product#sku()}`, and close the HTML elements properly. Re-run the command with `-Xdoclint:all -Werror`. The goal is zero documentation-related warnings or errors.

## 12. Checking with Maven and Gradle

In projects using a build tool, integrate Javadoc checks into CI so every API change is verified.

### 12.1. Maven

Use the Maven Javadoc Plugin to generate API docs:

~~~text
mvn javadoc:javadoc
~~~

Generate a Javadoc JAR for distribution alongside the library:

~~~text
mvn javadoc:jar
~~~

In the plugin configuration, set release, UTF-8, DocLint, and fail-on-warning according to the plugin version in use. An example configuration may include:

~~~xml
<configuration>
    <release>17</release>
    <encoding>UTF-8</encoding>
    <docencoding>UTF-8</docencoding>
    <charset>UTF-8</charset>
    <doclint>all</doclint>
    <failOnWarnings>true</failOnWarnings>
</configuration>
~~~

Check the documentation of the plugin version you use to confirm parameter names and how Javadoc options are passed; do not assume all plugin versions support the same configuration.

### 12.2. Gradle

With the Gradle Java plugin, the `javadoc` task generates HTML. You can configure the standard doclet:

~~~kotlin
tasks.withType<Javadoc>().configureEach {
    options.encoding = "UTF-8"
    (options as StandardJavadocDocletOptions).apply {
        addBooleanOption("Xdoclint:all", true)
        addBooleanOption("Werror", true)
    }
}
~~~

Run:

~~~text
./gradlew javadoc
~~~

On Windows:

~~~text
gradlew.bat javadoc
~~~

Output is typically located in `build/docs/javadoc`. Paths and configuration APIs may vary by Gradle version.

## 13. Checking Documentation Across API Versions

When releasing multiple versions of a library, verify the documentation against the exact binary artifact:

- Javadoc is generated from the same source revision as the binary.
- `@since` reflects the first version in which the API appeared.
- Deprecated APIs have the annotation, a reason, and a replacement API.
- Older documentation remains archived if users need to reference it.
- External links point to the right dependency versions.
- The Javadoc JAR accompanies the matching library version.
- Release notes do not contradict behavior described in the API docs.

You can use the `--since` option to generate documentation highlighting new or deprecated APIs in specified releases. Check your JDK's `javadoc --help` before adding this option to a pipeline.

When changing method signatures, type parameters, exceptions, or semantics, review the documentation as part of the API compatibility review. A source change may compile while breaking links or examples in Javadoc.

## 14. Automating Checks in CI

A documentation pipeline can run in this order:

1. Check out the exact commit.
2. Install the JDK supported by the project.
3. Compile source and tests.
4. Run Javadoc with `-Xdoclint:all -Werror`.
5. Verify the output directory contains the expected index and API pages.
6. Run a link checker or HTML/accessibility validator if required by the project.
7. Archive the HTML/Javadoc JAR as a build artifact.
8. Publish the right version after the release is approved.

Example basic check command:

~~~text
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -d build/apidocs -sourcepath src -subpackages com.example.publicapi
~~~

Pin the JDK and plugin versions so results are reproducible. Record tool versions in CI logs; when upgrading the JDK, review new warnings instead of immediately disabling DocLint.

You can add an output file existence check:

Windows PowerShell:

~~~powershell
if (-not (Test-Path build\apidocs\index.html)) {
    throw "Javadoc index.html was not generated"
}
~~~

macOS/Linux:

~~~sh
test -f build/apidocs/index.html
~~~

This only checks that output exists; you still need to verify package/type pages and link content.

## 15. Troubleshooting Javadoc Checks

### `reference not found`

**Cause:** `{@link}` or `@see` points to a nonexistent type/member, wrong package, or wrong overload.

**Fix:** check the signature, package name, imports, and module/class path. For overloads, specify parameters explicitly.

### `no @param for ...`

**Cause:** missing `@param` or tag name does not match the parameter in source code.

**Fix:** compare with the method/constructor signature and update each tag. For generic methods, also check `@param <T>`.

### `no @return`

**Cause:** the method returns a value, but the documentation does not describe the result within the checked scope.

**Fix:** add `@return`, clearly stating empty/null cases and special states. Do not add `@return` for `void` methods or constructors.

### `invalid HTML`

**Cause:** invalid HTML tag, improper nesting, or missing closing tag.

**Fix:** fix the markup, use simple HTML, and re-run the `html` group or `-Xdoclint:all`.

### Javadoc finishes with warnings even though HTML is generated

**Cause:** warnings are still permitted in the current configuration.

**Fix:** enable `-Werror` in CI so new warnings are not accepted.

### Package or member is missing

**Cause:** package is not included in `-subpackages`, wrong source path, or unsuitable visibility filter.

**Fix:** check `-sourcepath`, input packages, `-public`/`-protected`/`-private`, and module exports.

### External link does not open

**Cause:** URL has the wrong version, metadata is missing, or the build machine cannot reach the host.

**Fix:** use the right URL and `-linkoffline` for offline builds; run a link checker on the generated HTML.

### Examples in Javadoc do not run

**Cause:** snippets are not compiled/tested as part of the build, APIs changed, or examples lack imports/setup.

**Fix:** turn important examples into compiled tests/example sources in CI and keep them synchronized with the documentation.

### Javadoc build differs between local and CI

**Cause:** different JDK, locale, encoding, plugin, or dependencies on the classpath/module path.

**Fix:** pin toolchain, encoding, release, and plugin versions; log `javadoc --version` and the command line.

## 16. Pre-Publish Verification Checklist

- [ ] Confirmed JDK/Javadoc version and target release.
- [ ] Ran `-Xdoclint:all`.
- [ ] CI enables `-Werror` when policy requires zero warnings.
- [ ] Zero `reference`, `html`, or `syntax` errors remain.
- [ ] Supported public APIs have complete descriptions.
- [ ] `@param`, `@return`, and `@throws` match signatures and behavior.
- [ ] Links to classes, methods, and overloads are accurate.
- [ ] Package/module documentation is generated with the right scope.
- [ ] Private/internal APIs are not accidentally published.
- [ ] Important code snippets and examples have been compiled or tested.
- [ ] HTML output contains the required index, package, and type pages.
- [ ] Navigation, search, encoding, code blocks, and accessibility have been reviewed.
- [ ] External links and dependency versions have been verified.
- [ ] Javadoc HTML/Javadoc JAR matches the source revision and binary release.
- [ ] CI archives logs, command line, and artifacts for reproducibility.

Effective Javadoc checking requires both tooling and content review. DocLint catches many syntax, tag, HTML, and reference issues; `-Werror` enforces standards in CI; and cross-checking against the implementation, tests, and generated HTML confirms users receive accurate, complete, and useful API documentation.