# Reference Errors in Javadoc DocLint

In Javadoc, a *reference* is the name of a Java element mentioned in a documentation comment: a package, class, interface, constructor, method, field, parameter, or exception. When a name is misspelled, does not exist, cannot be resolved, or does not match the actual declaration, Javadoc may generate a broken link or report an error.

DocLint includes the `reference` check group to detect these issues. This check group covers references in `@see`, `{@link ...}`, `{@linkplain ...}`, and names declared in tags such as `@param` or `@throws`.

This lesson uses JDK 21 as the baseline, focusing on how to read diagnostics, fix reference syntax, configure source/class/module paths, and verify links to external APIs.

## 1. What is a reference error?

A reference error occurs when Javadoc cannot identify the element a comment is pointing to, or when a tag describes an element that does not match the Java declaration.

Example:

~~~java
/**
 * Finds a product.
 *
 * @see #findById(String)
 */
public Optional<Product> find(String id) {
    // ...
}
~~~

If the class does not have a `findById(String)` method, Javadoc cannot create a valid link. This is a reference error even though the Java program can still compile and run normally.

Common errors include:

- Misspelling a class, package, method, or field name.
- Using the right method name with the wrong parameter type list.
- Pointing to a non-existent overload or failing to specify the required overload.
- Specifying a `@param` name that differs from the parameter in the declaration.
- Omitting angle brackets in `@param` for a type parameter, for example writing `@param T` instead of `@param <T>`.
- Specifying a `@throws` exception name that does not exist or cannot be thrown by the method.
- A dependent class or module is not on the source path, class path, or module path.
- Referencing an external API without configuring the corresponding Javadoc link.

A reference error can cause Javadoc to terminate with an error, failing the documentation build, especially when CI uses `-Werror`.

## 2. The reference group in DocLint

DocLint divides documentation comment checks into groups:

| Group | Description |
|---|---|
| `accessibility` | Checks accessibility issues such as images missing `alt` attributes |
| `html` | Checks common HTML errors such as block tags inside inline tags or missing closing tags |
| `missing` | Checks missing comments or tags such as `@param`, `@return` |
| `reference` | Checks references to Java API elements and names in tags |
| `syntax` | Checks Javadoc syntax, HTML entities, and invalid tags |

`reference` focuses on whether the mentioned name matches the actual API. For example, `{@link}` pointing to a non-existent method, or `@param` specifying a parameter name that is not in the method signature.

DocLint is enabled by default when running `javadoc`. You can explicitly specify which groups to check:

~~~bash
# Check only reference issues
javadoc -Xdoclint:reference -sourcepath src -d docs com.example.catalog

# Enable all check groups
javadoc -Xdoclint:all -sourcepath src -d docs com.example.catalog

# Enable all groups except missing checks
javadoc -Xdoclint:all,-missing -sourcepath src -d docs com.example.catalog

# Disable all DocLint checks (not recommended in CI)
javadoc -Xdoclint:none -sourcepath src -d docs com.example.catalog
~~~

`-Werror` turns warnings into errors so the build fails when documentation does not meet quality policies:

~~~bash
javadoc -Xdoclint:all -Werror -sourcepath src -d docs com.example.catalog
~~~

Do not disable DocLint just to hide an invalid reference. Fix the target name or configure the search paths so that the documentation accurately reflects the API.

## 3. Javadoc reference syntax

The general form of a reference to a Java element is:

~~~text
module/package.Class#member
~~~

Where:

- `module/` is the module name, which can be omitted if the context already determines it.
- `package.` is the full package name.
- `Class` is the class or interface name, which may be a nested class.
- `#member` is a constructor, method, annotation member, field, or enum constant.

Leading parts can be omitted when Javadoc can infer them from context. When referencing a member within the same class where the comment is written, `#member` is usually sufficient.

Example:

~~~java
/**
 * Uses {@link java.util.Optional} to represent an optional result.
 *
 * <p>Call {@link ProductCatalog#find(String)} to search active products.
 *
 * @see java.util.Map
 */
~~~

### 3.1. Method references and overloads

If a method is not overloaded and its name does not collide with a field or enum constant, the parameter list can be omitted. When overloads exist, explicitly specify the parameter type list:

~~~java
/**
 * Calls {@link #find(String)} for an active product.
 * Use {@link #find(String, boolean)} to include archived products.
 */
~~~

In a reference, write the parameter types in declaration order. Do not include variable names:

~~~java
// Correct
{@link #find(String, boolean)}

// Incorrect: references do not accept variable names
{@link #find(String id, boolean includeArchived)}

// Incorrect: parameter types do not match the signature
{@link #find(String, int)}
~~~

You can use fully qualified types when simple names are ambiguous:

~~~java
{@link java.util.Map#get(Object)}
{@link java.nio.file.Files#readString(java.nio.file.Path)}
~~~

Useful rules:

- Use `String` rather than `java.lang.String` when the context is clear; both forms work when valid.
- Use exact primitive types such as `int`, `boolean`, `long`.
- Use `String[]` for arrays.
- Use nested type names such as `Outer.Inner`.
- Constructors are referenced using the class name followed by the parameter list, for example `{@link ProductCatalog#ProductCatalog()}`.
- For generic methods, write the actual parameter types as declared and use the reference form supported by Javadoc.

### 3.2. Module references

When you need to specify a module, use `/` between the module and the package:

~~~java
/**
 * Uses {@link java.base/java.util.Optional} for optional values.
 */
~~~

This is useful when multiple modules have similar package or type names. The module name does not replace the package name; the part after `/` is still the package and class.

### 3.3. Member references and URI fragments

A single `#` is used to point to a member:

~~~java
{@link ProductCatalog#find(String)}
~~~

A double `##` is used to point to an arbitrary fragment in the documentation page, such as a heading with an id:

~~~java
{@link ProductCatalog##search-examples Search examples}
~~~

Do not use `##` in place of `#method(...)`. The two syntaxes serve different purposes.

## 4. Fixing errors in {@link}, {@linkplain}, and @see

### 4.1. {@link} and {@linkplain}

`{@link}` creates an inline link whose label is typically rendered in code font:

~~~java
/**
 * Use {@link java.util.Optional#orElse(Object)} to provide a fallback.
 */
~~~

`{@linkplain}` creates an inline link whose label is rendered in normal text font:

~~~java
/**
 * Read the {@linkplain java.util.Optional API documentation}
 * before choosing a fallback strategy.
 */
~~~

Both tags share the same reference syntax. If the target is wrong, switching to `{@linkplain}` will not fix the error; you need to fix the reference itself.

### 4.2. Three forms of @see

Reference to a Java element:

~~~java
/**
 * @see java.util.Optional
 * @see ProductCatalog#find(String)
 */
~~~

HTML link to a URL:

~~~java
/**
 * @see <a href="https://docs.oracle.com/">Oracle documentation</a>
 */
~~~

Plain text, without creating a link:

~~~java
/**
 * @see "Internal catalog design document"
 */
~~~

If you want to link to a Java class or method, use the reference form. If you want an external URL, use an HTML anchor or an appropriate link tag. Do not put a web URL in the Java element reference position and expect DocLint to recognize it as a URL.

### 4.3. Class names and imports

Javadoc evaluates references within the scope of the compilation unit; imports in the source file are taken into account when resolving class and interface names.

Example:

~~~java
package com.example.catalog;

import java.util.Optional;

/**
 * Returns an {@link Optional} result.
 */
public class ProductCatalog {
}
~~~

If an import is missing, class names collide, or the reference is hard to read, use the fully qualified name:

~~~java
{@link java.util.Optional}
~~~

This also helps reviewers identify the exact API the comment refers to.

## 5. Errors in @param and @throws

Not all reference errors occur inside `{@link}`. DocLint also checks names in block tags.

### 5.1. @param must match the declaration

The name in `@param` must match the method or constructor parameter name exactly:

~~~java
/**
 * Finds a product by its identifier.
 *
 * @param id product identifier
 * @return matching product, if present
 */
public Optional<String> find(String id) {
    return Optional.empty();
}
~~~

If the method takes `id` but the comment writes `@param productId`, DocLint may report an invalid parameter name.

For a generic type parameter, you must enclose the name in angle brackets:

~~~java
/**
 * Converts a value to a target type.
 *
 * @param <T> target type
 * @param value source value
 * @return converted value
 */
public <T> T convert(Object value) {
    return (T) value;
}
~~~

`@param T` is incorrect when documenting type parameter `T`; you must use `@param <T>`.

### 5.2. @throws must point to a valid exception

The exception name in `@throws` must be an exception that the method or constructor can throw. Use the exact class name and describe the condition under which it occurs:

~~~java
/**
 * Reads a catalog file.
 *
 * @param path path to the catalog file
 * @return file contents
 * @throws IOException if reading the file fails
 */
public String read(Path path) throws IOException {
    return Files.readString(path);
}
~~~

If using an exception from another package, import the type or write its fully qualified name. Verify the method signature and logic before adding the tag.

Javadoc automatically includes checked exceptions declared in the `throws` clause in the Throws section if no descriptive tag is present. Adding `@throws` helps explain the conditions that trigger it and how callers should handle it.

## 6. Reference targets must be locatable

A syntactically valid reference can still fail if Javadoc cannot find the target class or module.

Distinguish between the four search sources:

| Option | Used to locate |
|---|---|
| `-sourcepath` / `--source-path` | Source files of dependent packages and classes |
| `-classpath` / `--class-path` / `-cp` | Non-modular classes and JARs |
| `--module-path` / `-p` | Compiled named modules or modular JARs |
| `--module-source-path` | Source trees of modules |

Project example:

~~~text
project/
├── src/
│   └── com/example/catalog/
│       ├── ProductCatalog.java
│       └── Product.java
├── lib/
│   └── validation-api.jar
└── docs/
~~~

Generating Javadoc for the package:

~~~bash
javadoc -encoding UTF-8 \
  -sourcepath src \
  --class-path lib/validation-api.jar \
  -d docs \
  -Xdoclint:reference \
  com.example.catalog
~~~

If `ProductCatalog.java` references `validation-api.jar`, Javadoc needs to locate the types in that JAR. Merely adding `-link` to the library's HTML documentation does not put the JAR on the class path.

On Windows, when specifying multiple paths in the class path, the separator is a semicolon:

~~~powershell
javadoc -sourcepath src -classpath "lib/a.jar;lib/b.jar" -d docs -Xdoclint:reference com.example.catalog
~~~

On Linux/macOS, the separator is a colon:

~~~bash
javadoc -sourcepath src \
  -classpath "lib/a.jar:lib/b.jar" \
  -d docs \
  -Xdoclint:reference \
  com.example.catalog
~~~

### 6.1. Modular projects

If a dependency is a named module, place it on the module path. If you are generating documentation for module sources, specify the module source path:

~~~bash
javadoc \
  --module-source-path src \
  --module-path mods \
  -d docs \
  --module com.example.catalog
~~~

If a dependent module is not resolved or not read in the module graph, references to types in that module may remain unresolved. Check `requires`, the module path, and the modules passed to the Javadoc command.

## 7. Linking to external library Javadoc

There are two separate tasks:

1. Making types locatable by Javadoc so it can verify references.
2. Generating hyperlinks from the generated documentation to the library's published Javadoc pages.

The class path/module path solves the first task. `-link` and `-linkoffline` solve the second task.

### 7.1. Using -link

`-link` takes the root URL of the external Javadoc set. That URL directory must contain an `element-list` or `package-list` file generated by Javadoc.

Example linking to the Java SE 21 API:

~~~bash
javadoc \
  -sourcepath src \
  -d docs \
  -link https://docs.oracle.com/en/java/javase/21/docs/api/ \
  com.example.catalog
~~~

Javadoc uses `element-list` to determine which modules/packages exist in the external documentation and constructs the corresponding URLs. The URL must point to the root directory of the Javadoc set, not directly to a specific class's HTML file.

### 7.2. Using -linkoffline

Use `-linkoffline` when the build machine cannot access the website or when the `element-list`/`package-list` file is stored in a different location.

Syntax:

~~~text
-linkoffline url1 url2
~~~

- `url1`: URL written into the hyperlinks in the output HTML.
- `url2`: local directory containing `element-list` or `package-list`.

Example:

~~~bash
javadoc \
  -sourcepath src \
  -d docs \
  -linkoffline https://docs.example.org/catalog/api/ tools/catalog-api-docs \
  com.example.catalog
~~~

In this example, `tools/catalog-api-docs` must contain an `element-list` or `package-list` matching the linked documentation set.

Do not use `-linkoffline` as a replacement for `--class-path` or `--module-path`. It only configures links to external HTML documentation.

## 8. Reading and handling DocLint messages

An error may appear in the following form:

~~~text
ProductCatalog.java:18: error: reference not found
 * {@link #find(String, int)}
           ^
~~~

This is an illustrative message; the exact wording and caret position depend on the JDK and source code.

When encountering an error, follow this sequence:

1. Read the reported file and line number.
2. Identify the tag or block containing the reference.
3. Separate the reference from the display label. In `{@link reference label}`, the part before the label is the target to be resolved.
4. Compare the target against the actual declaration: package, class, member, and parameter types.
5. Check imports and fully qualified names.
6. If the target belongs to a dependency, verify the source/class/module path.
7. If the target resolves but the external page link is broken, check `-link`, `-linkoffline`, and `element-list`.
8. Re-run the `reference` group, then run all of DocLint.

### 8.1. Quick triage

| Message/Issue | Check first |
|---|---|
| `reference not found` in `{@link}` | Class/member name and parameter type list |
| `@param` has an invalid name | Parameter name in method/constructor; `< >` brackets for type parameters |
| `@throws` has an invalid name | Exception class, package/import, and whether the exception can be thrown |
| Reference to a type in an external library not found | `--class-path` or `--module-path` |
| Reference is valid but has no hyperlink to external API | `-link`/`-linkoffline` and `element-list`/`package-list` |
| Only one overload fails | Types, order, and number of parameters of the overload |

Do not try to fix it by changing the label after the reference. The label is only display text; the target is what determines the link.

## 9. Complete example with Java 17+

The example below includes two overloads to demonstrate accurate references, `@param`, `@return`, and `@throws`.

### 9.1. Project structure

~~~text
project/
└── src/
    ├── com/example/catalog/
    │   └── ProductCatalog.java
    └── com/example/app/
        └── Main.java
~~~

### 9.2. ProductCatalog.java

File `src/com/example/catalog/ProductCatalog.java`:

~~~java
package com.example.catalog;

import java.util.Optional;

/**
 * Looks up products by their identifiers.
 *
 * <p>Use {@link #find(String)} to find active products.
 * Use {@link #find(String, boolean)} when archived products
 * should also be considered.
 *
 * @see java.util.Optional
 */
public final class ProductCatalog {
    private ProductCatalog() {
    }

    /**
     * Finds an active product by identifier.
     *
     * @param id product identifier; must not be blank
     * @return the product name when it exists
     * @throws IllegalArgumentException if id is null or blank
     */
    public static Optional<String> find(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        if (id.equals("A-100")) {
            return Optional.of("Keyboard");
        }

        return Optional.empty();
    }

    /**
     * Finds a product, optionally including archived entries.
     *
     * @param id product identifier; must not be blank
     * @param includeArchived whether archived products are eligible
     * @return the matching product name when it exists
     * @throws IllegalArgumentException if id is null or blank
     * @see #find(String)
     */
    public static Optional<String> find(
            String id, boolean includeArchived) {
        if (includeArchived && "A-099".equals(id)) {
            return Optional.of("Legacy mouse");
        }

        return find(id);
    }
}
~~~

In the class comment, `{@link #find(String)}` points to the single-parameter overload; `{@link #find(String, boolean)}` points to the two-parameter overload. `@param` matches `id` and `includeArchived`; `@throws` describes the actual exception that can be thrown.

### 9.3. Main.java

File `src/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.catalog.ProductCatalog;

public class Main {
    public static void main(String[] args) {
        System.out.println(
                ProductCatalog.find("A-100").orElse("not found"));

        System.out.println(
                ProductCatalog.find("A-099", true).orElse("not found"));
    }
}
~~~

### 9.4. Compile and run

Run from the `project` directory:

~~~bash
mkdir -p out docs

javac -encoding UTF-8 -d out \
  src/com/example/catalog/ProductCatalog.java \
  src/com/example/app/Main.java

java -cp out com.example.app.Main
~~~

Exact stdout:

~~~text
Keyboard
Legacy mouse
~~~

### 9.5. Generate Javadoc and check references

Still in the `project` directory:

~~~bash
javadoc -encoding UTF-8 \
  -sourcepath src \
  -d docs \
  -Xdoclint:reference \
  -link https://docs.oracle.com/en/java/javase/21/docs/api/ \
  com.example.catalog
~~~

To run all check groups and treat warnings as errors:

~~~bash
javadoc -encoding UTF-8 \
  -sourcepath src \
  -d docs \
  -Xdoclint:all \
  -Werror \
  -link https://docs.oracle.com/en/java/javase/21/docs/api/ \
  com.example.catalog
~~~

The result is an HTML documentation set in the `docs` directory, including `docs/com/example/catalog/ProductCatalog.html`. Open that page to verify the two overload links, as well as the Parameters, Returns, and Throws sections.

This example uses Java 17 APIs such as `String.isBlank()` and `Optional`; the Javadoc command uses JDK 21-compatible syntax.

## 10. Common anti-patterns and fixes

| Incorrect | Correct | Reason |
|---|---|---|
| `{@link #find(String, int)}` | `{@link #find(String, boolean)}` | Parameter types must match the overload |
| `{@link #find(String id)}` | `{@link #find(String)}` | References take parameter types, not variable names |
| `@param productId` when declared as `String id` | `@param id` | Name must match the declaration |
| `@param T` for a generic type parameter | `@param <T>` | Type parameters must be enclosed in angle brackets |
| `@see java.util.Optional#missing()` | `@see java.util.Optional#empty()` | Member must exist |
| Adding only `-link` when missing a class in a JAR | Add the JAR to `--class-path` | External links do not provide dependencies for type resolution |
| Using a URL in `{@link https://...}` | Use `@see <a href="...">...</a>` or an HTML anchor | `{@link}` points to a Java element |
| Using `-link` with a URL to a class HTML file | Use the root directory URL containing `element-list`/`package-list` | Javadoc needs the package/module list to construct links |

## 11. Should you suppress reference warnings?

DocLint supports `@SuppressWarnings("doclint:reference")` on a declaration to ignore messages belonging to the `reference` group. Example:

~~~java
@SuppressWarnings("doclint:reference")
public class LegacyAdapter {
    // ...
}
~~~

Only use this when there is a specific reason and the documentation limitation is documented. A suppress annotation only hides the message; it does not fix an invalid target, supply a missing class, or make a broken hyperlink work.

If the target API has been removed, update the comment to point to the replacement API. If a dependency is missing from the build, fix the path configuration. If a reference only has the wrong signature, fix the parameter types. Suppression should not be the default solution.

## 12. Verification workflow in a project

You can integrate reference checking into CI in the following order:

1. Select the exact JDK that the project uses to publish documentation.
2. Run `javadoc -Xdoclint:reference` to detect Java element linking errors.
3. Verify that source dependencies are on `-sourcepath`.
4. Verify that non-modular JARs are on `--class-path`.
5. Verify that named modules are on `--module-path` and module sources are on `--module-source-path`.
6. Configure `-link` or `-linkoffline` for external API docs.
7. Run `javadoc -Xdoclint:all -Werror` to check all groups and fail on warnings per CI policy.
8. Open a few generated HTML pages to verify hyperlinks and final rendered content.

DocLint checks comments in source files and reports locations close to the error. It is not a full validator for all generated HTML output and does not automatically fix comments. When you need to verify the reader experience, also inspect the generated HTML using an appropriate link checker or HTML validator.

## 13. Key takeaways

- DocLint's `reference` group checks Java element names mentioned in Javadoc.
- `{@link}`, `{@linkplain}`, and `@see` use reference syntax; overloads require exact parameter type lists.
- `@param` must match parameter names; generic type parameters use `@param <T>`.
- `@throws` must describe a valid exception that the method or constructor can throw.
- `-sourcepath`, `--class-path`, and `--module-path` help Javadoc locate source and type dependencies.
- `-link` and `-linkoffline` create hyperlinks to external Javadoc; they do not replace the class path or module path.
- Run `-Xdoclint:reference` when investigating reference errors and `-Xdoclint:all -Werror` in documentation verification pipelines.
- Only suppress when there is a clear reason; fixing the reference or dependency path is the proper solution.

References:

- [The javadoc Command — Java SE 21: DocLint and reference checks](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javadoc.html)
- [Documentation Comment Specification for the Standard Doclet — Java SE 21: References, @link, @see, @param and @throws](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html)
- [The javac Command — Java SE 21: class path and module path](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
