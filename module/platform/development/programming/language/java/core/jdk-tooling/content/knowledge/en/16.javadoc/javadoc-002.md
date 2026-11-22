# Generating API Documentation with Javadoc

Javadoc is a tool in the JDK used to generate API documentation from Java source code. The tool reads **documentation comments** placed before package, module, class, interface, record, constructor, field, and method declarations; it then generates HTML documentation including an overview page, package pages, type pages, member details, indexes, and cross-links between APIs.

API documentation helps library users understand what an API is for, how to call it, and the meaning of its parameters, return values, possible exceptions, input preconditions, limitations, side effects, version of introduction, and deprecation status. Good documentation describes the contract callers can rely on, matches actual behavior, and is verified as part of the build process.

The toolchain used to verify this guide reports `javadoc 24.0.2`. Options may vary across JDKs; check `javadoc --version`, `javadoc --help`, and `javadoc --help-extra` in your actual build environment.

## 1. How Does Javadoc Work?

A documentation comment is a Java comment that begins with a slash and two asterisks (`/**`). Javadoc reads comments attached to declarations and parses tags such as `@param`, `@return`, `@throws`, `@see`, `@since`, and `@deprecated`. The JDK's standard doclet converts the content into HTML.

Example:

~~~java
/**
 * Represents a product in the catalog.
 */
public final class Product {
}
~~~

Basic flow:

~~~text
Java source files
      |
      v
Documentation comments
      |
      v
     javadoc
      |
      +--> Parse declarations and tags
      +--> Resolve links and references
      +--> Check HTML and documentation rules
      |
      v
Generated API documentation (HTML)
~~~

Javadoc does not execute your program to infer API semantics, nor does it automatically know business rules. The author must accurately describe the behavior, preconditions, and limitations of the API.

## 2. Structure of a Documentation Comment

A comment typically has two parts:

1. **Description:** the main descriptive text, written before block tags.
2. **Block tags:** structured information sections starting with `@tag`.

Example:

~~~java
/**
 * Finds a product by its SKU.
 *
 * <p>The lookup is case-sensitive and does not modify the catalog.
 *
 * @param sku the exact SKU to search for
 * @return the matching product, or an empty result if no product exists
 * @throws NullPointerException if {@code sku} is {@code null}
 * @since 1.0
 */
public Optional<Product> findBySku(String sku) {
    // ...
}
~~~

The description should begin with a short sentence clearly stating the purpose. Javadoc uses the first sentence to build summaries on package pages, class pages, and method tables. The summary must stand on its own when displayed in isolation. After the first sentence, you can add explanatory paragraphs, examples, or lists; block tags are typically placed after the description.

### 2.1. Writing Good Summaries

Good summary:

~~~java
/**
 * Returns the number of products in this catalog.
 */
public int size() {
    // ...
}
~~~

Vague summary:

~~~java
/**
 * Gets the size.
 */
public int size() {
    // ...
}
~~~

Clearly state the value returned or the action performed. Avoid starting with “This method is used to...” because it adds no useful information. If you need to specify a summary explicitly, you can use the `{@summary ...}` inline tag on supported JDKs.

## 3. Common Block Tags

| Tag | Used for | Meaning |
|---|---|---|
| `@param name description` | Method, constructor, generic type | Describes a parameter or type parameter |
| `@return description` | Method returning a value | Describes the return value |
| `@throws Type description` | Method, constructor | Describes an exception and the conditions under which it is thrown |
| `@exception Type description` | Method, constructor | Alternative name for `@throws` |
| `@see reference` | Various declarations | Links to a related API or external resource |
| `@since version` | API | The first version in which the API appeared |
| `@deprecated explanation` | Legacy API | Reason for deprecation and replacement API |
| `@author name` | Type/package | Author; requires `-author` to be displayed |
| `@version text` | Type/package | Version; requires `-version` to be displayed |
| `@apiNote text` | API | Notes for API consumers |
| `@implSpec text` | Methods with an implementation contract | Rules that implementations/subclasses must follow |
| `@implNote text` | API | Notes about how the implementation works |
| `@serial`, `@serialField`, `@serialData` | Serializable API | Describes the serial form and serialization data |

### 3.1. `@param`

Used for each parameter; the name must match the declaration exactly:

~~~java
/**
 * Adds a product to the catalog.
 *
 * @param product the product to add
 */
public void add(Product product) {
    // ...
}
~~~

For generic type parameters, use `@param <T>`:

~~~java
/**
 * Converts a value to a textual representation.
 *
 * @param <T> the value type
 * @param value the value to convert
 * @return the textual representation
 */
public static <T> String describe(T value) {
    return String.valueOf(value);
}
~~~

For records, `@param` can describe each record component in the record's documentation comment.

### 3.2. `@return`

Used for methods that return a value; do not use for constructors or `void` methods.

~~~java
/**
 * Returns the number of products currently stored.
 *
 * @return the number of products
 */
public int size() {
    return products.size();
}
~~~

If the result can be empty, `null`, or represent a special state, describe it accurately. For `Optional<T>`, clarify when `Optional.empty()` is returned.

### 3.3. `@throws` and `@exception`

Describe the condition that causes the exception rather than merely repeating the exception name:

~~~java
/**
 * Finds a product by its SKU.
 *
 * @param sku the SKU to search for
 * @return the product, or an empty result if it is absent
 * @throws NullPointerException if {@code sku} is {@code null}
 */
public Optional<Product> findBySku(String sku) {
    return Optional.ofNullable(products.get(
            Objects.requireNonNull(sku, "sku")));
}
~~~

Only document exceptions that the API can actually throw under the stated conditions. For checked exceptions, explain the situation in which they occur and what it means so callers can handle them properly.

### 3.4. `@since` and `@deprecated`

Use `@since` to record the version in which the API was introduced:

~~~java
/**
 * Returns a stable identifier for this product.
 *
 * @return the product identifier
 * @since 1.2
 */
public String id() {
    return id;
}
~~~

When an API is no longer recommended, use both the `@Deprecated` annotation and the `@deprecated` block tag:

~~~java
/**
 * Returns the legacy product code.
 *
 * @deprecated Use {@link #sku()} instead.
 */
@Deprecated(since = "2.0", forRemoval = true)
public String productCode() {
    return sku;
}
~~~

The annotation helps compilers, IDEs, and tooling recognize deprecated APIs. The tag explains why and points to the replacement. Do not just write “deprecated”; state the replacement API, any behavioral differences, and the removal plan if the project has announced one.

### 3.5. `@apiNote`, `@implSpec`, and `@implNote`

These three tags separate content meant for different audiences:

- `@apiNote`: notes for API users.
- `@implSpec`: the contract that implementations must obey, especially for overridable methods.
- `@implNote`: information about how a specific implementation works.

~~~java
/**
 * Returns an immutable snapshot of the current products.
 *
 * @apiNote The returned list can be safely retained by the caller.
 * @implSpec The list must not reflect later changes to the catalog.
 * @implNote The current implementation copies the values into a new list.
 * @return an immutable snapshot
 */
public List<Product> snapshot() {
    return List.copyOf(products.values());
}
~~~

Only include implementation details when they are valuable to readers or maintainers. Do not turn `@implNote` into a line-by-line narration of internal code.

## 4. Inline Tags and Links in Documentation

Inline tags are placed directly inside the description or block tags.

| Inline tag | Purpose |
|---|---|
| `{@link Type#method()}` | Links to an API and renders the reference name in code font |
| `{@linkplain Type#method()}` | Links to an API but renders as plain text |
| `{@code expression}` | Renders inline code |
| `{@literal text}` | Renders literal text without parsing it as HTML or tags |
| `{@value}` | Displays the value of an eligible constant |
| `{@inheritDoc}` | Inherits documentation from an overridden method |
| `{@docRoot}` | Relative path to the root directory of the generated documentation |
| `{@snippet ...}` | Inserts a code snippet; supported since JDK 18 |

Example:

~~~java
/**
 * Adds a product if its {@link Product#sku()} is not already present.
 *
 * <p>See {@linkplain Catalog#findBySku(String) the lookup method}.
 */
public void add(Product product) {
    // ...
}
~~~

Use `{@code}` for variable names, expressions, commands, and short code fragments. Use `{@literal}` when you need to display angle brackets or strings that might otherwise be interpreted as HTML or Javadoc tags.

### 4.1. Linking to Specific Members

You can link to classes, constructors, fields, or methods:

~~~text
{@link Product}
{@link Product#sku()}
{@link Product#Product(String, String)}
{@link Catalog#findBySku(String)}
~~~

When a method is overloaded, include the parameter types to link to the exact overload. For APIs in other packages, use the fully qualified name or an appropriate qualified reference.

### 4.2. `{@value}` for Constants

~~~java
/**
 * Default maximum number of results.
 */
public static final int DEFAULT_LIMIT = 50;

/**
 * Returns the default result limit, currently {@value #DEFAULT_LIMIT}.
 *
 * @return the default limit
 */
public int defaultLimit() {
    return DEFAULT_LIMIT;
}
~~~

`{@value}` is useful when a constant's value should be shown directly in the explanation. Do not use it for fields that are not eligible constants.

### 4.3. `{@inheritDoc}` for Overridden Methods

When overriding a method, you can inherit the description from the superclass or interface method:

~~~java
/**
 * {@inheritDoc}
 *
 * <p>This implementation performs the lookup in memory.
 */
@Override
public Optional<Product> findBySku(String sku) {
    // ...
}
~~~

`{@inheritDoc}` avoids duplicating contracts already defined in the parent API. If the implementation adds specific constraints or behavior, add a separate explanation.

### 4.4. Code Snippets with `{@snippet}`

JDK 18+ supports the snippet tag in documentation comments:

~~~java
/**
 * Creates a catalog and looks up a product:
 *
 * {@snippet :
 * Catalog catalog = new Catalog(List.of(product));
 * Optional<Product> result = catalog.findBySku("A-100");
 * }
 */
public final class Catalog {
}
~~~

For longer examples, you can store snippets in external files and configure `--snippet-path`. This allows you to reuse examples and validate them independently. Ensure that snippets accurately reflect the current API.

## 5. Writing Javadoc for Classes, Interfaces, Records, Constructors, and Methods

### 5.1. Classes and Interfaces

Type documentation should explain the main role and responsibilities, how to create or obtain instances, the invariants maintained by the type, how it interacts with related types, thread-safety and mutability if relevant to callers, and any notable usage conditions or limitations.

~~~java
/**
 * Provides lookup operations for a collection of products.
 *
 * <p>A catalog rejects duplicate SKUs and exposes immutable lookup results.
 *
 * @since 1.0
 */
public final class Catalog {
}
~~~

### 5.2. Constructors

A constructor's documentation should describe how the object is initialized, its parameters, input preconditions, and exceptions:

~~~java
/**
 * Creates a catalog containing the supplied products.
 *
 * @param products initial products; the collection must not be {@code null}
 * @throws NullPointerException if the collection or an element is {@code null}
 * @throws IllegalArgumentException if two products have the same SKU
 */
public Catalog(Collection<Product> products) {
    // ...
}
~~~

Do not include `@return` on constructors.

### 5.3. Methods

A method's documentation should describe its action, parameters, return value, exceptions, and side effects:

~~~java
/**
 * Removes a product from the catalog.
 *
 * @param sku the SKU of the product to remove
 * @return {@code true} if a product was removed; {@code false} if none matched
 * @throws NullPointerException if {@code sku} is {@code null}
 */
public boolean remove(String sku) {
    // ...
}
~~~

If a method mutates state, performs I/O, blocks, retries, caches, invokes callbacks, or has concurrency behavior, describe those aspects whenever they affect the caller.

### 5.4. Fields and Generic Types

Public and protected fields are part of the API. Document their meaning, units, valid range, and mutability if applicable:

~~~java
/**
 * Default maximum number of products returned by a search.
 */
public static final int DEFAULT_LIMIT = 50;
~~~

When an API uses generics, document the meaning of each type parameter:

~~~java
/**
 * Maps an input value to a result.
 *
 * @param <I> the input type
 * @param <O> the output type
 */
public interface Mapper<I, O> {

    /**
     * Converts one input value.
     *
     * @param input the value to convert
     * @return the converted value
     */
    O map(I input);
}
~~~

Type parameter names should be meaningful—such as `T`, `K`, `V`, `I`, or `O` depending on context—and the documentation should explain their roles whenever they are not self-evident.

## 6. Package and Module Documentation

An API is more than individual classes. Package and module documentation help readers understand how types fit together.

### 6.1. `package-info.java`

Create `package-info.java` inside the package directory:

~~~java
/**
 * Public API for product catalog lookup and management.
 *
 * <p>Use {@link com.example.catalog.Catalog} to search products and
 * {@link com.example.catalog.Product} to represent catalog entries.
 *
 * @since 1.0
 */
package com.example.catalog;
~~~

`package-info.java` can contain package documentation and package annotations. Javadoc uses this content for the package summary page. If a package contains multiple types, explain their collective role, coordination rules, and the entry points users should read first.

### 6.2. `module-info.java`

For named modules, you can place a documentation comment before the module declaration:

~~~java
/**
 * Provides the product catalog API.
 *
 * <p>The module exports the public catalog package.
 */
module com.example.catalog {
    exports com.example.catalog;
}
~~~

When generating module documentation, use options such as `--module-path`, `--module-source-path`, and `--module`. Module/package/type visibility options determine the level of detail in the generated documentation.

### 6.3. Overview Page with `overview.html`

You can create a separate HTML overview file and pass it via `-overview`:

~~~text
javadoc -overview overview.html -d docs -sourcepath src -subpackages com.example
~~~

The overview page is well suited for introducing the library, its goals, main packages, quick-start examples, and links to guides outside the API reference.

## 7. Generating API Documentation with the `javadoc` Command

General syntax:

~~~text
javadoc [options] [packagenames] [sourcefiles] [@files]
~~~

Commonly used options:

| Option | Purpose |
|---|---|
| `-d directory` | Output directory for generated HTML |
| `-sourcepath path` | Root of the source tree |
| `-subpackages package` | Recursively documents a package and its subpackages |
| `-classpath path` / `--class-path` | Locates dependent classes |
| `--module-path path` | Locates modules |
| `--module module` | Specifies the module(s) to document |
| `--release version` | Target source/API platform compatibility level |
| `-encoding UTF-8` | Source file encoding |
| `-docencoding UTF-8` | Output HTML encoding |
| `-charset UTF-8` | Charset declared in the generated HTML |
| `-private` | Includes private members |
| `-protected` | Includes protected and public members (default) |
| `-public` | Includes only public members |
| `-author` | Displays `@author` tags |
| `-version` | Displays `@version` tags |
| `-link URL` | Links to external Javadoc documentation |
| `-linkoffline URL PATH` | Links to external docs using local offline metadata |
| `-overview file` | Includes an overview page |
| `-windowtitle text` | Sets the browser window/tab title |
| `-quiet` | Suppresses status messages |
| `-verbose` | Prints detailed diagnostic messages |

### 7.1. Generating Documentation for a Package

Given the structure:

~~~text
project/
  src/
    com/
      example/
        catalog/
          package-info.java
          Product.java
          Catalog.java
  docs/
~~~

Run from the `project` root directory:

~~~text
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -d docs -sourcepath src -subpackages com.example.catalog
~~~

Javadoc searches `src`, picks up `com.example.catalog` and its subpackages, and writes HTML files into `docs`.

If you only want to document specific files, pass the source files directly:

~~~text
javadoc --release 17 -d docs -sourcepath src src/com/example/catalog/Product.java src/com/example/catalog/Catalog.java
~~~

When passing files directly, ensure dependent types and package documentation can still be resolved via the appropriate source path and classpath.

### 7.2. Inspecting the Generated HTML

After a successful run, open `docs/index.html`. Typical generated files include:

- `index.html`: overview page.
- Package index page: list of packages.
- `com/example/catalog/package-summary.html`: package documentation.
- `com/example/catalog/Catalog.html`: class page.
- `index-all.html`: member index when generated.
- `element-list`: list of modules/packages used for external Javadoc linking.
- CSS, JavaScript, search index, and supporting pages generated by the standard doclet.

Exact filenames and the set of generated files may vary depending on the JDK version and doclet options. Inspect the index page, package pages, type pages, and member links rather than merely verifying that the `docs` directory exists.

## 8. Complete Example: Generating API Documentation for a Catalog Library

This example uses Java 17 and includes package documentation, two public classes, constructors, methods, links, and standard tags.

Directory structure:

~~~text
project/
  src/
    com/
      example/
        catalog/
          package-info.java
          Product.java
          Catalog.java
  docs/
~~~

### 8.1. `package-info.java`

~~~java
/**
 * Public API for product catalog lookup and management.
 *
 * <p>Use {@link com.example.catalog.Catalog} to search products and
 * {@link com.example.catalog.Product} to represent catalog entries.
 *
 * @since 1.0
 */
package com.example.catalog;
~~~

### 8.2. `Product.java`

~~~java
package com.example.catalog;

import java.util.Objects;

/**
 * Represents a product identified by a stock keeping unit (SKU).
 *
 * <p>The SKU and display name are immutable after construction.
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
     * @throws NullPointerException if {@code sku} or {@code name} is {@code null}
     * @throws IllegalArgumentException if either value is blank
     */
    public Product(String sku, String name) {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(name, "name");
        if (sku.isBlank() || name.isBlank()) {
            throw new IllegalArgumentException("sku and name must not be blank");
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

### 8.3. `Catalog.java`

~~~java
package com.example.catalog;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * Provides lookup operations for products.
 *
 * <p>A catalog is immutable after construction. Each SKU is unique.
 *
 * @apiNote Use {@link #findBySku(String)} to look up a product.
 * @since 1.0
 */
public final class Catalog {
    private final Map<String, Product> products;

    /**
     * Creates a catalog from the supplied products.
     *
     * @param initialProducts products to add to the catalog
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
     * @return the matching product, or {@link Optional#empty()} if no product exists
     * @throws NullPointerException if {@code sku} is {@code null}
     * @see Product#sku()
     * @since 1.0
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

### 8.4. Generating HTML and Checking for Documentation Errors

From the `project` directory, run:

~~~text
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example.catalog
~~~

Explanation:

- `--release 17`: checks source compatibility against Java 17.
- `-encoding UTF-8`: reads source files as UTF-8.
- `-docencoding UTF-8` and `-charset UTF-8`: generates HTML with UTF-8 encoding declarations.
- `-Xdoclint:all`: enables all documentation check groups.
- `-Werror`: treats warnings as errors so the build fails if any warning remains.
- `-d docs`: writes generated HTML to the `docs` directory.
- `-sourcepath src`: specifies the source root.
- `-subpackages com.example.catalog`: generates documentation for the package and its subpackages.

Once the command finishes, open:

~~~text
docs/index.html
docs/com/example/catalog/package-summary.html
docs/com/example/catalog/Product.html
docs/com/example/catalog/Catalog.html
~~~

The `Catalog.html` page should display the class description, constructor, `findBySku(String)`, `size()`, parameters, return values, thrown exceptions, and the link to `Product#sku()`. This example uses `Map.copyOf` and `Optional`, both of which are available in Java 17. Each source snippet is shown separately by file; save them with the matching file and package names before running the command.

## 9. Doclint: Checking Documentation Quality

Doclint detects errors in documentation comments and HTML. Run:

~~~text
javadoc -Xdoclint:all -d docs -sourcepath src -subpackages com.example
~~~

Common check groups:

| Group | What it checks |
|---|---|
| `accessibility` | Certain accessibility issues |
| `html` | Invalid HTML or malformed HTML structure |
| `missing` | Missing documentation or tags within the checked scope |
| `reference` | Invalid references to types or members |
| `syntax` | Syntax of documentation comments and tags |

You can enable or disable individual groups:

~~~text
javadoc -Xdoclint:all,-missing -d docs -sourcepath src -subpackages com.example
~~~

`-Xdoclint` is an extended option of the standard doclet; exact check groups and behavior may vary across JDKs. Check `javadoc --help-extra` for your toolchain.

### 9.1. Turning Warnings into Errors

Combine with `-Werror` to prevent a build from succeeding when warnings remain:

~~~text
javadoc -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example
~~~

This works well in CI because broken links, invalid HTML, and tag mistakes are caught immediately when source code changes. Do not disable doclint entirely just to get a green build; if a specific group does not fit project conventions, exclude it deliberately and document why.

## 10. Linking to External Javadoc

APIs frequently reference types from Java SE or third-party libraries. Use `-link` to link to published documentation:

~~~text
javadoc --release 17 -link https://docs.oracle.com/en/java/javase/17/docs/api/ -d docs -sourcepath src -subpackages com.example
~~~

References like `{@link java.util.Optional}` will point to the corresponding API page if Javadoc can locate the package/element list metadata at the given URL.

For offline builds, use `-linkoffline` with the target documentation URL and a locally downloaded copy of its package list or element list:

~~~text
javadoc -linkoffline https://docs.example.com/api/ external-api-docs -d docs -sourcepath src -subpackages com.example
~~~

`external-api-docs` is the directory containing the offline link metadata matching the target documentation. Avoid linking to temporary URLs or unstable documentation hosts. When upgrading dependency versions, check external API links to avoid broken or version-mismatched links.

## 11. Custom Tags and Taglets

If a project has custom metadata, you can register a custom block tag with `-tag`:

~~~text
javadoc -tag "quality:a:Quality:" -d docs -sourcepath src -subpackages com.example
~~~

Then use it in comments:

~~~java
/**
 * Performs a catalog lookup.
 *
 * @quality Stable API
 */
public Optional<Product> findBySku(String sku) {
    // ...
}
~~~

The `-tag` syntax specifies the tag name, allowed locations, and display heading. Check the JDK help for valid location characters. For more complex rendering, you can write a custom Taglet and register it with `-taglet` and `-tagletpath`.

Only add custom tags when a project convention genuinely requires them. If you use custom tags, configure them consistently across local builds, IDEs, and CI so documentation does not lose content when generated by a different command.

## 12. Documenting Modules

For modular projects, Javadoc can generate documentation per module. Example source layout:

~~~text
src/
  com.example.catalog/
    module-info.java
    com/
      example/
        catalog/
          package-info.java
          Product.java
          Catalog.java
~~~

`module-info.java`:

~~~java
/**
 * Provides product catalog APIs.
 */
module com.example.catalog {
    exports com.example.catalog;
}
~~~

With multiple modules, use `--module-source-path` and specify the module(s) to document:

~~~text
javadoc --release 17 --module-source-path src --module com.example.catalog -d docs
~~~

For compiled modules or modules on the module path, use `--module-path` and `--module` according to your project layout. For named modules, default visibility focuses on exported APIs; options such as `--show-packages`, `--show-types`, `--show-members`, and `--show-module-contents` let you adjust the scope.

Ensure exported packages have proper documentation. Non-exported internal packages can still be documented when broader visibility options are selected, but internal documentation should not be mistaken for supported public APIs.

## 13. Integrating Javadoc into Maven and Gradle

In real-world projects, integrate API documentation generation into the build so public API changes are always reflected in the docs.

### 13.1. Maven

Use the Maven Javadoc Plugin, for example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.11.2</version>
    <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
        <docencoding>UTF-8</docencoding>
        <charset>UTF-8</charset>
        <doclint>all</doclint>
        <failOnWarnings>true</failOnWarnings>
    </configuration>
</plugin>
~~~

Generate Javadoc:

~~~text
mvn javadoc:javadoc
~~~

Generate a Javadoc JAR for publishing alongside the artifact:

~~~text
mvn javadoc:jar
~~~

The plugin version shown in the example is illustrative; projects should use a tested plugin version managed consistently in the parent or build configuration.

### 13.2. Gradle

With the Gradle Java plugin, the `javadoc` task generates HTML from the main source set. You can configure it as follows:

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

The default output is typically located in `build/docs/javadoc`. Check the Gradle configuration for your version, as the `StandardJavadocDocletOptions` API can vary across Gradle releases.

## 14. Publishing and Versioning API Documentation

A library can publish Javadoc per version:

~~~text
https://docs.example.com/library/1.0/
https://docs.example.com/library/1.1/
https://docs.example.com/library/2.0/
~~~

Keep documentation versions aligned with binary artifacts. Users need to know that the documentation page matches the exact JAR or module version they are using.

When releasing:

- Generate Javadoc from the exact source revision and recorded JDK/toolchain.
- Inspect the overview, package, and public type pages.
- Verify internal and external links.
- Attach a Javadoc JAR if the library is published for developers.
- Retain documentation for older versions if users still need to reference them.
- Mark deprecated APIs and clearly indicate their replacements.
- Include documentation generation in the release pipeline alongside source JARs and binary artifacts.

Do not publish documentation containing internal APIs, sensitive information, developer machine paths, or unapproved notes.

## 15. Principles for Writing Usable, Maintainable API Documentation

Useful API documentation should answer practical questions:

- **Behavior:** what does the method do, does it mutate state, and does it perform I/O or block?
- **Input:** can parameters be `null`, what formats or units are valid, and what size or range limits apply?
- **Output:** what value is returned, can it be empty, and is the returned object mutable or immutable?
- **Failure:** which exceptions can occur and under what conditions? How should callers handle them?
- **Concurrency:** is the object thread-safe, can the method be called concurrently, and must callers synchronize externally?
- **Lifecycle:** who owns the resource, when must it be closed, and can methods be called after closing?
- **Compatibility:** in which version was the API added, is it deprecated, or has its behavior changed?

There is no need to describe implementation details if API users do not need to know them. However, observable characteristics such as result ordering, stability, precision, timeouts, retries, and side effects must be stated clearly when they affect usage.

### 15.1. Avoiding Common Documentation Mistakes

- Repeating the method name in the description: “Gets the name” for `getName()`.
- Missing `@param` tags or descriptions that do not match the parameter's type or meaning.
- `@return` descriptions that fail to explain empty or `null` cases.
- `@throws` tags that only list the exception without stating the condition.
- Links pointing to the wrong overload or a nonexistent class.
- Unclosed HTML tags or improperly structured headings.
- Examples that do not compile against the current API.
- Documenting implementation details as if they were a stable contract.
- Failing to update Javadoc when changing a public signature or behavior.
- Using `@deprecated` without specifying a replacement.

## 16. Troubleshooting Javadoc

### `error: reference not found`

**Cause:** `{@link}` or `@see` points to an invalid class or member, a dependency is missing, or an overload signature does not match.

**Resolution:** check the type name, package, signature, and classpath/module path. For overloaded methods, specify the parameter list explicitly.

### `warning: no @param for ...`

**Cause:** a method or constructor has a parameter, but the documentation is missing the corresponding `@param` tag or the tag name does not match.

**Resolution:** add `@param` for each parameter and update descriptions whenever the method signature changes.

### `warning: no @return`

**Cause:** a method returns a value, but the documentation is missing `@return` within the checked scope.

**Resolution:** document the return value and any special states such as empty, `null`, or default values.

### `invalid HTML`

**Cause:** HTML in a documentation comment has syntax errors, missing closing tags, or invalid element nesting.

**Resolution:** fix the markup, prefer simple HTML, and re-run with `-Xdoclint:all`.

### Garbled Non-ASCII / Unicode Characters

**Cause:** inconsistent source or output encoding.

**Resolution:** use `-encoding UTF-8`, `-docencoding UTF-8`, and `-charset UTF-8`, and save source files in UTF-8.

### Package Page Has No Description

**Cause:** `package-info.java` is missing, or the source path does not locate the package documentation file.

**Resolution:** create `package-info.java` in the right package and verify `-sourcepath` points to the source root directory.

### Expected Members Are Missing

**Cause:** the member is outside the selected visibility level, or the module/package is not exported.

**Resolution:** check `-public`, `-protected`, `-package`, `-private`, the module descriptor, and `--show-*` options.

### External Links Do Not Work

**Cause:** the target documentation URL lacks a matching package list or element list, the build is offline, or the documentation version is wrong.

**Resolution:** use the documentation URL for the exact version; for offline builds, use `-linkoffline` with pre-downloaded metadata.

### Javadoc Build Fails After Upgrading the JDK

**Cause:** stricter doclint checks, tags or HTML that are no longer valid, or changed APIs/doclet options.

**Resolution:** read the first warning or error, run `javadoc --version`, inspect `--help` and `--help-extra`, update comments to comply with current standards, and only then consider compatibility options.

## 17. API Documentation Completion Checklist

- [ ] Public classes, interfaces, and records have summaries that accurately state their role.
- [ ] Public constructors describe object creation and input preconditions.
- [ ] Public methods document behavior, parameters, return values, and exceptions appropriately.
- [ ] Generic type parameters are explained where needed.
- [ ] Nullability, mutability, thread-safety, side effects, and resource lifecycle are stated when they affect callers.
- [ ] Links to classes and members use the exact signature and overload.
- [ ] `@since` matches the API version.
- [ ] Deprecated APIs have the `@Deprecated` annotation, a reason, and a replacement API.
- [ ] Packages have `package-info.java`.
- [ ] Modules have documentation in `module-info.java` if the project is modular.
- [ ] Examples and snippets match the current API.
- [ ] Source and output encodings are UTF-8.
- [ ] The Javadoc build runs with `-Xdoclint:all`.
- [ ] CI uses `-Werror` if project policy requires zero warnings.
- [ ] `index.html`, package pages, and class/member pages have been opened and verified.
- [ ] External links, version numbers, and the Javadoc JAR are checked before release.

Javadoc turns documentation comments in source code into browsable, cross-linked API reference documentation. When you document contracts accurately, use tags consistently, validate with doclint, and generate docs in your build pipeline, library users can understand how to call your API without having to read the implementation to guess its behavior.
