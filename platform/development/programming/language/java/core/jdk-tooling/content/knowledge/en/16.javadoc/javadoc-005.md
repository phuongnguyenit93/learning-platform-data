# Links in Javadoc

Javadoc generates HTML documentation from documentation comments in Java source code. **Links in Javadoc** help readers navigate from an API to a related class, method, field, package, module, or reference document. A good link tells the reader what the target is, works when documentation is generated as multiple separate sets, and does not lead to missing pages.

There are two main scopes:

- **Internal links**: point to declarations documented in the same Javadoc run, such as another method in the class or another class in the project.
- **External links**: point to APIs or documentation sets generated elsewhere, such as the Java SE API or the Javadoc of a dependency library.

Javadoc provides inline tags such as **{@link}** and **{@linkplain}**, the **@see** block tag, and the **-link** and **-linkoffline** command-line options to connect independent documentation sets.

## 1. Commonly Used Link Types

| Syntax | Location | Purpose |
|---|---|---|
| **{@link reference}** | Within a sentence or description paragraph | Creates a link to a module, package, class, or member |
| **{@linkplain reference label}** | Within a sentence or description paragraph | Creates a link with a label displayed in plain text |
| **@see reference** | Block tag at the end of a documentation comment | Adds a link entry in the See Also section |
| **@see HTML anchor** | Block tag | Adds a link to an external URL |
| **{@docRoot}** | Inline tag | Gets the relative path from the current page to the root of the documentation set |
| **-link URL** | javadoc option | Connects links to an external Javadoc set that has package/module list metadata |
| **-linkoffline URL1 URL2** | javadoc option | Connects links to an external documentation set when metadata is stored elsewhere or the build machine cannot access the URL |

Choose the syntax based on context. Use {@link} when mentioning an API directly in a sentence; use @see when you want to group related documentation into a dedicated section; use -link or -linkoffline when generating documentation for multiple independent libraries or modules.

## 2. API Reference Syntax

A reference in Javadoc can point to a module, package, class/interface, constructor, method, annotation member, field, enum constant, or record component.

Common general form:

~~~text
[module/][package.]Class#member(parameter-types)
~~~

The leading parts can be omitted when Javadoc can infer them from the location of the documentation comment.

Examples:

| Reference | Target |
|---|---|
| **{@link #normalize(String)}** | The normalize method in the current class |
| **{@link #DEFAULT_LOCALE}** | The DEFAULT_LOCALE field in the current class |
| **{@link NameFormatter}** | The NameFormatter class in the current scope |
| **{@link NameFormatter#normalize(String)}** | The normalize method of NameFormatter |
| **{@link java.lang.String}** | The String class in the java.lang package |
| **{@link java.lang.String#trim()}** | The trim method of String |
| **{@link java.base/java.lang.String#trim()}** | The trim method of String, explicitly specifying the java.base module |
| **{@link #NameFormatter()}** | The NameFormatter constructor in the current class |

For members, the **#** symbol separates the class name from the member name. For methods or constructors, you can include the parameter type list in parentheses to distinguish overloads.

### Linking to overloaded methods

Suppose a class has two methods:

~~~java
public String format(String value) {
    return value.trim();
}

public String format(String value, int width) {
    return value.trim();
}
~~~

Explicitly reference the overload to use:

~~~java
/**
 * Uses {@link #format(String)} for the default format.
 * For fixed-width output, use {@link #format(String, int)}.
 */
~~~

If you only write {@link #format}, Javadoc may be unable to determine the intended member or may emit a warning depending on the case. When a class has overloads, include the full parameter list.

You can use a simple type name if the type is in import scope or in the same package. When there are name collisions or complex references, use a fully qualified name such as java.lang.String to reduce ambiguity.

### Linking to fields, constructors, and nested types

Example:

~~~java
/**
 * Creates a formatter using {@link #NameFormatter()}.
 * The default width is {@link #DEFAULT_WIDTH}.
 * Builder options are available in {@link Builder}.
 */
~~~

#NameFormatter() points to the constructor; #DEFAULT_WIDTH points to the field; Builder points to the nested type if Javadoc can resolve it in the current scope.

## 3. {@link} and {@linkplain}

Both inline tags create links to the same kinds of API references, but they differ in how the label is rendered.

### {@link}

{@link} creates an inline link. When the label is the declaration name or no custom label is provided, Javadoc typically renders it in code style, which fits class, method, and field names.

Example:

~~~java
/**
 * Call {@link #normalize(String)} before comparing names.
 * The result is compatible with {@link java.lang.String#trim()}.
 */
~~~

In the HTML page, readers can click the method name to open the corresponding documentation section.

You can provide a custom label after the reference:

~~~java
/**
 * See {@link #normalize(String) the normalization method}.
 */
~~~

### {@linkplain}

{@linkplain} works like {@link}, except the label is rendered in a normal text font instead of code style. Use it when the label is a natural-language phrase:

~~~java
/**
 * Read {@linkplain #normalize(String) the normalization rules}
 * before passing user input to this method.
 */
~~~

### Quick Comparison

| Tag | When to use | Label rendering |
|---|---|---|
| **{@link #save()}** | Mentioning the method name directly | Code style suited for API identifiers |
| **{@linkplain #save() save operation}** | Writing a natural sentence | Plain text |
| **@see #save()** | Adding the method to the See Also section | A separate link entry |

You do not need to link every occurrence of a term. Only add a link when the target helps the reader understand or use the API better.

## 4. @see: the See Also Section

@see is a block tag. Javadoc groups these tags into the **See Also** section of the generated page.

There are three main forms.

### Referencing a program element

~~~java
/**
 * Normalizes the input before processing.
 *
 * @see #isEmpty(String)
 * @see java.lang.String#trim()
 * @see java.util.List
 */
~~~

Javadoc generates a link to the corresponding method, class, or type if the reference resolves.

### Linking to a URL with an HTML anchor

~~~java
/**
 * See the
 * @see <a href="https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html">String API documentation</a>
 */
~~~

This form is useful when pointing to a specific web page, such as a guide, specification, or documentation not generated by Javadoc.

### Plain-text entries without a link

~~~java
/**
 * @see "Internal migration notes maintained by the platform team"
 */
~~~

When the content starts with a quotation mark, Javadoc displays a text entry without creating a hyperlink. Use this form when you want to cite a document or reference that does not have a URL.

You can declare multiple @see tags in the same documentation comment. Keep entries concise and directly relevant to the class or member being described.

## 5. Linking to Classes and Members in the Same Documentation Set

When classes are included in the same Javadoc run, Javadoc can generate internal links without needing the -link option.

Example structure:

~~~text
src/
  com/example/api/
    NameFormatter.java
    NameValidator.java
~~~

In NameFormatter.java:

~~~java
package com.example.api;

/**
 * Formats user-facing names.
 * Use {@link NameValidator} to validate input and
 * {@link #normalize(String)} to normalize whitespace.
 *
 * @see NameValidator#isValid(String)
 */
public final class NameFormatter {

    private NameFormatter() {
    }

    /**
     * Removes leading and trailing whitespace.
     *
     * @param input text to normalize
     * @return normalized text, or an empty string when input is null
     * @see #isBlank(String)
     */
    public static String normalize(String input) {
        return input == null ? "" : input.trim();
    }

    /**
     * Checks whether the supplied text is blank.
     *
     * @param input text to inspect
     * @return true if input is null or blank
     */
    public static boolean isBlank(String input) {
        return input == null || input.isBlank();
    }
}
~~~

In NameValidator.java:

~~~java
package com.example.api;

/**
 * Validates user-facing names.
 */
public final class NameValidator {

    private NameValidator() {
    }

    /**
     * Checks whether a name contains non-whitespace text.
     *
     * @param value name to inspect
     * @return true when the name is valid
     */
    public static boolean isValid(String value) {
        return value != null && !value.isBlank();
    }
}
~~~

Generate Javadoc for the entire package:

~~~bash
javadoc -d docs -sourcepath src -subpackages com.example.api
~~~

When both classes are in the same run, references such as NameValidator, NameValidator#isValid(String), and #normalize(String) are generated as internal links in HTML.

The HTML files are typically placed under:

~~~text
docs/
  com/
    example/
      api/
        NameFormatter.html
        NameValidator.html
  index.html
  allclasses-index.html
~~~

The exact structure depends on the Javadoc version and doclet configuration. Open the generated class page to confirm that links point to the right members.

## 6. Linking to the External Java SE API

When source code uses JDK classes such as String, List, Map, or Path, Javadoc knows the types from the compiler, but generating hyperlinks to Java SE documentation published at a separate URL requires configuring external links.

The **-link** option takes the URL of the root directory containing the external Javadoc documentation:

~~~bash
javadoc -d docs -sourcepath src -subpackages com.example.api -link https://docs.oracle.com/en/java/javase/17/docs/api/
~~~

In this example, the URL is the root of the Java SE 17 API docs. Javadoc uses the metadata at that directory to identify linkable modules/packages, then creates links from references such as java.lang.String or java.util.List.

Several important points:

- Pass the URL to the root directory of the documentation set, not the URL of an individual class page.
- The external documentation directory must contain the Javadoc-generated metadata file, typically **element-list** for modular documentation or **package-list** for legacy documentation.
- You can pass multiple -link options in a single run to link to multiple documentation sets.
- Choose the URL matching the Java release the project targets.
- The URL must point to a published documentation set that is reachable from the build environment.

For example, source code can include:

~~~java
/**
 * Returns an immutable view.
 * See {@link java.util.List} and {@link java.lang.String#trim()}.
 */
~~~

When Javadoc is generated with -link pointing to the Java SE API, external references can link to the corresponding official API pages.

## 7. Linking to External Libraries or Documentation Sets with -link

Suppose the Acme Model library has published Javadoc at:

~~~text
https://docs.example.com/acme-model/api/
~~~

In the application source code, there is a reference:

~~~java
/**
 * Converts a model using {@link com.acme.model.Customer}.
 */
~~~

To link to the Acme Model documentation, add:

~~~bash
javadoc -d docs -sourcepath src -subpackages com.acme.app -link https://docs.example.com/acme-model/api/
~~~

Javadoc reads the element-list or package-list file in that documentation directory to discover available modules and packages. It can then generate hyperlinks to the corresponding classes.

If the external documentation set was generated using the module system, element-list describes the modules/packages. For older non-modular documentation sets, you may encounter package-list.

Do not manually create or edit element-list/package-list to force Javadoc to recognize packages. These are metadata files generated by Javadoc when building the source documentation set.

## 8. -linkoffline When the Build Cannot Access External Documentation

Use **-linkoffline** when the documentation URL is known, but the build machine cannot access it directly to fetch metadata, or when the metadata file is stored in a different location.

Syntax:

~~~bash
javadoc -linkoffline URL1 URL2
~~~

Where:

- **URL1** is the URL embedded into hyperlinks in the generated HTML.
- **URL2** is the path or URL to the directory containing the element-list or package-list file that Javadoc can read during the build.

Example local directory layout:

~~~text
project/
  src/
  docs-cache/
    element-list
~~~

Generate documentation:

~~~bash
javadoc -d docs -sourcepath src -subpackages com.example.api -linkoffline https://docs.example.com/acme-model/api/ docs-cache
~~~

Javadoc uses the metadata in docs-cache to resolve packages/classes, while the generated hyperlinks still point to the published Acme Model URL.

Common suitable scenarios:

- CI builds running on an internal network without internet access.
- Dependency documentation is pre-downloaded or cached.
- The public documentation URL does not serve the metadata file directly, but the team has a matching copy of the metadata.
- You want deterministic documentation builds that do not depend on network connectivity on every run.

URL1 must point to the exact root of the published documentation. URL2 must contain metadata matching that exact documentation set; using an element-list from a different version can produce broken links.

## 9. Linking to Static Documentation with {@docRoot}

Not every page you want to link to is a class or method. A project may include installation guides, architecture diagrams, or operational runbooks published alongside Javadoc.

The **{@docRoot}** inline tag is replaced with the relative path from the current page to the root of the generated documentation set.

Example:

~~~java
/**
 * Read the
 * <a href="{@docRoot}/guides/installation.html">installation guide</a>
 * before configuring the runtime.
 */
~~~

If the current page is nested deep inside a package directory, Javadoc computes the appropriate relative path back to the root.

Use {@docRoot} when linking to an HTML page or resource located within the same generated documentation set. For API declarations, prefer {@link} or {@linkplain} because Javadoc can automatically compute paths to classes/members.

Make sure the target file is actually copied into the output directory. {@docRoot} only generates the relative path; it does not create or verify the contents of the target HTML page.

## 10. Reference Resolution and Overload Handling

References are evaluated in the context of the documentation comment. The compilation unit's imports are taken into account when Javadoc resolves class/interface names.

Example:

~~~java
package com.example.api;

import java.util.List;

/**
 * Returns a {@link List} of results.
 */
public class SearchService {
}
~~~

Because List is imported, Javadoc can resolve this reference to java.util.List.

When names collide across packages, use fully qualified names:

~~~java
/**
 * Uses {@link java.util.Date} for legacy timestamps and
 * {@link java.time.LocalDate} for date-only values.
 */
~~~

For overloaded methods, specify the full parameter list:

~~~java
/**
 * @see #find(String)
 * @see #find(String, int)
 */
~~~

If the method is in another class:

~~~java
/**
 * Delegates to {@link SearchService#find(String)}.
 */
~~~

When a reference cannot be resolved, check:

1. Whether the class, method, or field name has the correct casing.
2. Whether the method has the exact number and types of parameters.
3. Whether parameter types need fully qualified names to avoid ambiguity.
4. Whether the class is on the source path, classpath, or module path used by Javadoc.
5. If the target is in another documentation set, whether -link or -linkoffline is configured.

## 11. HTML, Special Characters, and Link Labels

Documentation comments allow HTML markup, but the content must follow valid HTML syntax. When writing direct HTML links, provide a label that describes the destination.

Example:

~~~java
/**
 * See <a href="https://docs.example.com/security/">security guide</a>
 * for the deployment requirements.
 */
~~~

Characters that have special meaning in HTML must be properly escaped:

| Character | How to write it literally |
|---|---|
| < | &lt; or {@literal <} |
| > | &gt; or {@literal >} |
| & | &amp; |
| Braces inside an inline tag | Use the appropriate entity if you need to represent the tag-closing character |

To display code or generic types, prefer {@code}:

~~~java
/**
 * Accepts a {@code List<String>} as input.
 */
~~~

{@literal} renders content without interpreting it as HTML or nested Javadoc tags. {@code} also renders literal content, but in a code font.

Inside an inline tag's label, a closing curly brace } terminates the tag. If you need to display this character in a label, use the entity &#125;.

Do not nest links or create overlapping HTML anchors. Use a single clear link for a single target.

## 12. Validating Links When Generating Javadoc

The **-Xdoclint:all** option enables all documentation comment check groups, including tag syntax, HTML, and references. You can combine it with **-Werror** to treat warnings as errors in a pipeline.

Example:

~~~bash
javadoc -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example.api -link https://docs.oracle.com/en/java/javase/17/docs/api/
~~~

If Javadoc reports a reference error:

- Check which class/member was reported as not found.
- Verify the package/imports and signature.
- Confirm the source or dependency is present in the build environment.
- Confirm the -link URL points to the documentation root and the metadata file is present.
- For offline builds, verify URL1/URL2 of -linkoffline.

Doclint catches many documentation comment and reference errors, but it does not replace checking every URL on the internet. A metadata file can tell Javadoc that a package exists in a documentation set without guaranteeing that the server is serving every HTML page as expected. For important web links, include a URL verification or link-checker step in CI.

### Inspecting the HTML Output

After generating documentation, open a class page:

~~~text
docs/com/example/api/NameFormatter.html
~~~

Verify:

- Internal links open the intended class or member.
- Links to the Java SE API open the right release.
- Links to dependencies open the right library version.
- Link labels read naturally in sentences.
- No links point to renamed files or packages.
- Static pages referenced via {@docRoot} actually exist.

## 13. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Javadoc reports reference not found | Incorrect class/member name or target missing from source/classpath | Check the reference and resolution environment |
| Link points to wrong or ambiguous overload | Parameter list not specified | Write the full signature in the reference |
| Class name is displayed without an external link | -link/-linkoffline not configured or metadata does not recognize the package | Check the URL and element-list/package-list |
| -link reports package-list/element-list not found | URL does not point to the documentation root or metadata is missing | Use the correct root URL or -linkoffline with local metadata |
| External link has wrong base path | Passed URL to a class page instead of the root directory | Pass the URL of the directory containing the Javadoc set |
| CI build cannot generate external links | Build environment has no internet access | Cache metadata and use -linkoffline |
| Static link returns 404 | HTML page not copied to output or wrong relative path | Check the target file and the path using {@docRoot} |
| HTML renders incorrectly | Special characters unescaped or invalid markup | Use valid HTML, {@code}, or {@literal} |
| Confusing link text | Default label does not describe the destination | Add a meaningful label or use {@linkplain} |
| Javadoc emits warnings even though source compiles | Documentation comment has issues independent of the Java compiler | Run Javadoc with doclint and fix warnings |

## 14. Workflow for Setting Up Links in a Project

1. Identify the classes, methods, fields, and packages readers need to navigate to.
2. Use {@link} for API identifiers mentioned in sentences.
3. Use {@linkplain} when you want the label to be a natural-language phrase.
4. Use @see for related references at the end of a comment.
5. Include packages/classes from the same project in one Javadoc run to get internal links.
6. Add -link for accessible external Javadoc sets that provide metadata.
7. Use -linkoffline if metadata is cached on the build machine or network access is restricted.
8. Use {@docRoot} for static guide pages in the same output.
9. Run -Xdoclint:all and consider -Werror in CI.
10. Open the generated HTML and check internal links and important external links before publishing.

## 15. Key Takeaways

- {@link} creates an inline hyperlink to a module, package, class, or member.
- {@linkplain} creates a similar link but renders the label in normal text font.
- @see places references in the See Also section; it can point to program elements, URLs, or unlinked text.
- References to overloaded methods should include full parameter types; use fully qualified names when ambiguous.
- Javadoc generates internal links automatically when the target is included in the same documentation set.
- -link connects to external documentation that has element-list or package-list at its root directory.
- -linkoffline uses a target URL and a separate metadata location, suited for offline builds.
- {@docRoot} helps build relative paths to static pages within the same documentation set.
- -Xdoclint:all helps detect tag, HTML, and reference errors; -Werror can fail the build on warnings.
- Always inspect the output HTML and critical URLs; a generated link does not guarantee that an external page remains available.

## Official References

- [Documentation Comment Specification — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html)
- [The javadoc Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html)
- [How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html)
- [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/)