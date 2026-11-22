# Standard Tags in Javadoc

Javadoc uses tags in documentation comments to describe Java APIs and generate structured HTML documentation. Tags help readers understand parameter meanings, return values, exceptions, API versions, relationships between types, and usage examples. The Javadoc tool also uses tags to generate links to other classes or methods, mark deprecated APIs, and present special content such as code snippets.

This article uses the **JDK 24 standard doclet** as the reference baseline when listing standard tags. Some tags have existed since the earliest Java versions; others are only available in modern JDKs. When using an older JDK, check whether a tag is supported.

## 1. Documentation comments and Javadoc tags

A documentation comment is a special comment attached to a Java declaration. The traditional form starts with `/**` and ends with `*/`:

~~~java
/**
 * Short description of the class or method.
 *
 * This section can explain in more detail, including multiple paragraphs,
 * lists, links, and examples.
 *
 * @since 1.0
 */
public class Example {
}
~~~

Javadoc recognizes a comment when it is placed immediately before the declaration it describes, with no other declaration or comment in between. Documentation comments can be used for modules, packages, classes, interfaces, constructors, methods, annotation elements, enum members, and fields.

Regular comments starting with `//` or `/*` are not treated as documentation comments. Therefore, if you want to generate API documentation, use the proper `/** ... */` syntax.

### Structure of a documentation comment

A comment typically has two parts:

1. **Main description:** the main descriptive section placed before the first block tag.
2. **Block tags:** tags starting with `@` at the beginning of a line, providing structured information such as `@param`, `@return`, or `@throws`.

Example:

~~~java
/**
 * Converts the input string into a normalized form.
 *
 * Removes leading and trailing whitespace and collapses consecutive whitespace
 * into a single space.
 *
 * @param input the string to normalize
 * @return the normalized string
 * @throws IllegalArgumentException if input is null
 * @since 1.0
 */
public String normalize(String input) {
    // ...
}
~~~

The first line should be a short, meaningful summary sentence that can stand alone in the API summary page. Block tags must start at the beginning of a line, after `*` and optional whitespace. A tag's content extends until the next block tag or the end of the comment.

The main description ends at the first block tag. Do not continue writing the main description after `@param` or `@return`.

### Block tags and inline tags

Javadoc has two forms of tags:

| Type | Syntax | Typical position | Example |
|---|---|---|---|
| Block tag | @tag content | Beginning of a line in a documentation comment | @param input the input string |
| Inline tag | {@tag content} | Inside a sentence or descriptive paragraph | {@code String}, {@link String#strip()} |

A block tag creates a dedicated information section in the documentation. An inline tag inserts content, links, or formatting right where it appears.

## 2. Common block tags

### @param — describing parameters

Use `@param` to describe each parameter of a method or constructor. The tag must use the exact parameter name from the declaration.

~~~java
/**
 * Finds an item by code.
 *
 * @param code the code to search for
 * @param ignoreCase true to ignore case differences
 * @return the matching item, or null if not found
 */
public Item find(String code, boolean ignoreCase) {
    // ...
}
~~~

For generic type parameters, place the type name inside angle brackets:

~~~java
/**
 * Converts a value to the target type.
 *
 * @param <T> the result type
 * @param value the input value
 * @param type the class representing the target type
 * @return the converted value
 */
public <T> T convert(Object value, Class<T> type) {
    // ...
}
~~~

Notes:

- Each parameter should have a corresponding `@param`.
- Names must match the declaration, including case sensitivity.
- For type parameters, use the `@param <T>` form.
- Describe valid conditions, special values, and null handling when relevant.

### @return — describing return values

Use `@return` for methods with a non-void return type.

~~~java
/**
 * Computes the sum of two integers.
 *
 * @param first the first number
 * @param second the second number
 * @return the sum of the two numbers
 */
public int add(int first, int second) {
    return first + second;
}
~~~

Do not use `@return` for constructors or `void` methods. The description should clearly state what the return value represents, whether it can be null, and any special values to note.

### @throws — describing exceptions

Use `@throws` to describe exceptions that a method or constructor may throw. The exception name must reference a valid exception type.

~~~java
/**
 * Divides two integers.
 *
 * @param dividend the dividend
 * @param divisor the divisor
 * @return the integer quotient
 * @throws ArithmeticException if divisor is 0
 */
public int divide(int dividend, int divisor) {
    return dividend / divisor;
}
~~~

You can declare multiple `@throws` tags if a method has multiple error conditions. Describe the specific situation that causes the exception rather than merely repeating the exception name.

**`@exception`** is an older tag name with the same meaning as `@throws`. Prefer `@throws` in new documentation to stay consistent with current conventions.

### @see — related documentation

`@see` adds a See Also section at the end of the documented element's page. The tag supports references to Java elements, URLs, or a text string.

~~~java
/**
 * Returns the normalized name.
 *
 * @see String#strip()
 * @see java.text.Normalizer
 * @see "Project naming conventions"
 */
public String normalizedName() {
    // ...
}
~~~

Common forms:

- `@see ClassName`: links to a class.
- `@see #methodName(Type)`: links to a method in the same class.
- `@see package.Class#field`: links to a field.
- `@see "text"`: adds reference text without creating a link.
- `@see <a href="URL">label</a>`: creates a link to a URL.

If a method is overloaded, include the parameter type list so Javadoc resolves the exact link target.

### @since — version where the API was introduced

`@since` indicates which product version introduced the API or feature.

~~~java
/**
 * Returns the unique identifier.
 *
 * @return the identifier
 * @since 2.1
 */
public String id() {
    // ...
}
~~~

The value after `@since` is free-form text, but you should follow a consistent versioning convention across the entire project. Do not confuse `@since` with `@version`: `@since` states when the API first existed, whereas `@version` states the current version of the component or software.

### @deprecated — marking discouraged APIs

`@deprecated` explains why an API should no longer be used and points to an alternative.

It should be used together with the `@Deprecated` annotation:

~~~java
/**
 * Returns the name using the legacy rules.
 *
 * @deprecated Since version 2.0, use {@link #normalizedName()}.
 */
@Deprecated(since = "2.0")
public String legacyName() {
    // ...
}
~~~

The `@deprecated` content should:

- State the version in which the API was deprecated.
- Specify the concrete replacement API.
- Use `{@link ...}` to link to the replacement.
- Explain the reason or migration timeline if applicable.

The `@Deprecated` annotation helps the compiler and tools detect usage of old APIs. The `@deprecated` tag provides the explanatory text for the Javadoc page. Both have distinct roles and should appear together.

### @author and @version

`@author` records the author or development team:

~~~java
/**
 * Text processing utility suite.
 *
 * @author Java Platform Team
 */
public class TextTools {
}
~~~

`@version` records the current version of the class or component:

~~~java
/**
 * Text processing utility suite.
 *
 * @version 1.4.0
 */
public class TextTools {
}
~~~

These two tags are only included in the HTML documentation when running Javadoc with the corresponding options:

~~~bash
javadoc -author -version ...
~~~

Multiple `@author` or `@version` tags may be used. In many modern projects, author and version metadata are managed in external systems; use these two tags only when they add real value for API readers.

## 3. Specialized block tags

### @hidden — hiding elements from API documentation

`@hidden` instructs the standard doclet to omit the marked element from the generated API documentation.

~~~java
/**
 * Internal helper class for the initialization process.
 *
 * @hidden
 */
public class InternalBootstrap {
}
~~~

This tag was introduced in JDK 9. Use it only when a declaration must remain in source code or the binary API without appearing in generated documentation. Do not use `@hidden` as a substitute for proper package/module design.

### @provides and @uses — describing services in modules

These two tags are used only in the documentation comment of a module declaration.

- `@provides service-type description` describes a service implementation provided by the module.
- `@uses service-type description` describes a service used by the module.

Example `module-info.java`:

~~~java
/**
 * Module providing format converters.
 *
 * @provides com.example.spi.Formatter
 *     The module provides a JSON implementation for the Formatter service.
 * @uses com.example.spi.Extension
 *     The module can use extensions registered at runtime.
 */
module com.example.formatter {
    requires com.example.spi;
    provides com.example.spi.Formatter
        with com.example.formatter.JsonFormatter;
    uses com.example.spi.Extension;
}
~~~

These tags help readers understand the module's service role. They supplement the `provides` and `uses` directives with documentation; they do not replace the directives in `module-info.java`.

### @spec — referencing external specifications

`@spec` links part of an API to an external specification document:

~~~java
/**
 * Encodes data according to the rules described in the specification.
 *
 * @spec https://www.rfc-editor.org/rfc/rfc8259 RFC 8259
 */
public String encode(Object value) {
    // ...
}
~~~

`@spec` is supported starting in JDK 20. The URL and title must be consistent if the same URL is referenced in multiple places across the documentation.

### @serial — documenting Serializable classes and fields

`@serial` serves the Serialized Form page for classes implementing `Serializable`. It can be used to describe a serialized field or control whether a class is included in the serialized form page.

Forms:

~~~java
@serial field-description
@serial include
@serial exclude
~~~

Example describing a field:

~~~java
/**
 * User ID stored in the serialized form.
 *
 * @serial Unique identifier of the user.
 */
private long userId;
~~~

At the class or package level, `include`/`exclude` can control whether an element is included in the serialized form page according to the standard doclet rules. A class-level tag can override a package-level setting.

### @serialField — describing serialPersistentFields

`@serialField` describes each `ObjectStreamField` entry in the `serialPersistentFields` field of a `Serializable` class.

Syntax:

~~~java
@serialField field-name field-type field-description
~~~

Example:

~~~java
/**
 * Fields persisted in the serialized form.
 *
 * @serialField userId long User identifier.
 * @serialField displayName String Display name.
 */
private static final ObjectStreamField[] serialPersistentFields = {
    new ObjectStreamField("userId", long.class),
    new ObjectStreamField("displayName", String.class)
};
~~~

Use this tag only when the class actually declares `serialPersistentFields` under the Java Serialization mechanism.

### @serialData — describing data written/read during serialization

`@serialData` describes the types and order of data written by serialization methods such as `writeObject` or `writeExternal`.

~~~java
/**
 * Writes additional data to the stream.
 *
 * @serialData Writes the version number first, then writes the user name string.
 */
private void writeObject(java.io.ObjectOutputStream out)
        throws java.io.IOException {
    out.defaultWriteObject();
    out.writeInt(1);
    out.writeUTF(displayName);
}
~~~

This tag is only appropriate for serialization methods defined by Javadoc, such as `readObject`, `writeObject`, `readExternal`, `writeExternal`, `readResolve`, and `writeReplace`.

## 4. Standard inline tags

### {@code} — displaying code text

`{@code ...}` displays content in a monospace font and does not interpret its contents as HTML or Javadoc tags.

~~~java
/**
 * Returns {@code true} if the list is empty.
 */
public boolean isEmpty() {
    return size() == 0;
}
~~~

Use it for class names, methods, variables, expressions, generic types, and commands. You can write `<` and `>` directly inside `{@code ...}` without escaping them as HTML entities.

### {@literal} — displaying literal text

`{@literal ...}` preserves character rendering without interpreting HTML or nested tags, but does not use a code font.

~~~java
/**
 * The valid condition is {@literal value < limit}.
 */
public boolean isBelowLimit(int value, int limit) {
    return value < limit;
}
~~~

Distinction:

- `{@code ...}`: literal text in a code font.
- `{@literal ...}`: literal text in the regular text font.

### {@link} — inline links

`{@link reference label}` creates an inline link within a sentence to a class, package, field, constructor, or method.

~~~java
/**
 * Uses {@link String#strip()} to remove leading and trailing whitespace.
 *
 * @return the processed string
 */
public String clean(String value) {
    return value.strip();
}
~~~

Common reference syntax:

- `{@link String}`: links to the `String` class.
- `{@link #clean(String)}`: links to a method in the same class.
- `{@link java.util.List#size()}`: links to a method of another class.
- `{@link #clean(String) clean}`: uses a custom display label.

If a label is provided, the part after the reference is used as the displayed text.

### {@linkplain} — links with a plain-text label

`{@linkplain}` works like `{@link}`, except the label is rendered in the regular text font instead of a code font.

~~~java
/**
 * See {@linkplain #clean(String) the string cleaning method}
 * before saving data.
 */
public void save(String value) {
    // ...
}
~~~

Use `{@link}` when you want the API name rendered as code; use `{@linkplain}` when the label is a natural phrase in a sentence.

### {@inheritDoc} — inheriting documentation from an overridden method

`{@inheritDoc}` inserts the corresponding documentation from the method in a superclass or superinterface.

~~~java
interface Formatter {
    /**
     * Converts a value to a string.
     *
     * @param value the input value
     * @return the converted string
     */
    String format(Object value);
}

final class JsonFormatter implements Formatter {
    /**
     * {@inheritDoc}
     */
    @Override
    public String format(Object value) {
        return String.valueOf(value);
    }
}
~~~

This tag is used only in documentation comments of overridden methods, in the main description or inside `@param`, `@return`, or `@throws`. If the parent method lacks the corresponding documentation section, Javadoc cannot inherit that part.

Since JDK 22, you can specify the supertype as the inheritance source using `{@inheritDoc SuperType}`. The no-argument form lets Javadoc automatically locate the matching method in the inheritance hierarchy.

### {@docRoot} — path to the documentation root

`{@docRoot}` is replaced by the relative path from the current page to the root directory of the generated Javadoc documentation.

~~~java
/**
 * See <a href="{@docRoot}/legal/license.html">terms of use</a>.
 */
public class LicenseInfo {
}
~~~

This tag is useful when linking to shared resources such as licenses, images, or guide pages placed in the output root directory.

### {@index} — adding keywords to the index

`{@index word description}` creates an entry in the Javadoc index. You can index a single word or a phrase.

~~~java
/**
 * This section explains the {@index "thread safety" safety under concurrent access}
 * of the object.
 */
public class ConcurrentCache {
}
~~~

For multi-word phrases, enclose the phrase in double quotes. A short description helps readers understand what concept the index entry refers to.

### {@summary} — specifying the summary sentence

`{@summary ...}` explicitly defines the content used as the API summary instead of letting Javadoc automatically extract the first sentence.

~~~java
/**
 * {@summary Cache that stores computation results for reuse.}
 *
 * The cache supports expiration times and an element count limit.
 */
public class ResultCache {
}
~~~

This tag was introduced in JDK 10 and is only meaningful when placed at the start of the main description.

### {@systemProperty} — marking system properties

`{@systemProperty property.name}` identifies the name of a Java system property in documentation.

~~~java
/**
 * Reads configuration from {@systemProperty app.region}.
 */
public String region() {
    return System.getProperty("app.region", "local");
}
~~~

The property name should be a dotted identifier with no spaces. This tag ensures system property names are recognized and presented consistently in the documentation.

### {@value} — displaying constant values

`{@value}` displays the value of a `static` field that is a compile-time constant. You can specify a field by reference.

~~~java
/**
 * Maximum number of characters allowed.
 */
public static final int MAX_LENGTH = 120;

/**
 * The current limit is {@value #MAX_LENGTH} characters.
 */
public void validate(String input) {
    // ...
}
~~~

Use `{@value}` without a reference inside the field's own comment to display that field's value. Use `{@value #CONSTANT}` to reference another constant. Since JDK 20, the tag supports a format string appropriate for the constant's data type.

### {@snippet} — embedding code examples

`{@snippet}` embeds a code snippet into the generated documentation. Introduced in JDK 18, it supports content written directly in the comment or pulled from an external file.

Inline example:

~~~java
/**
 * Usage example:
 *
 * {@snippet :
 *     List<String> names = List.of("An", "Binh");
 *     names.forEach(System.out::println);
 * }
 */
public void printNames() {
    // ...
}
~~~

Example pulling a snippet from an external file:

~~~java
/**
 * Input processing example:
 *
 * {@snippet file="Example.java" region="parse"}
 */
public void parse() {
    // ...
}
~~~

External files can be placed in a `snippet-files` directory following the package structure or on a path supplied via the `--snippet-path` option. Markup such as `@start`, `@end`, `@highlight`, `@replace`, and `@link` can be used in line comments of the code snippet to select regions or customize rendering.

Notes when using inline snippets in traditional documentation comments:

- Do not include the character sequence `*/`, because it will close the Java comment.
- Curly braces must be balanced so Javadoc can determine where the inline tag ends.
- Snippets are documentation content; if you need to ensure examples actually compile, verify them via a separate build/test or use external snippets backed by tested source files.

### {@return} — declaring the return description directly in the main description

Since JDK 16, the inline tag `{@return ...}` can be used at the start of a method's main description. Javadoc uses that content for both the opening sentence and the Returns section.

~~~java
/**
 * {@return the current number of elements}
 */
public int size() {
    return 0;
}
~~~

This tag is only for methods. If `{@return ...}` is used, do not add a `@return` block tag for the same content. For complex methods, the traditional `@return` block tag remains clearer and easier to read.

## 5. Standard tags by declaration context

Not every tag can be used everywhere. Some tags are only for methods, while others are only for modules or serialization.

| Context | Typical tags |
|---|---|
| Module | @provides, @uses, @since, @spec, @see |
| Package | @author, @version, @since, @serial, @see |
| Class/interface/record | @param for type parameters, @author, @version, @since, @deprecated, @hidden, @serial |
| Constructor | @param, @throws, @deprecated, @see, @since |
| Method | @param, @return, @throws, @inheritDoc, @deprecated, @since |
| Field | @value, @serial, @deprecated, @since |
| Special serialization method | @serialData |
| serialPersistentFields field | @serialField |

Inline tags such as `{@code}`, `{@link}`, `{@linkplain}`, `{@literal}`, `{@summary}`, `{@snippet}`, `{@systemProperty}`, `{@value}`, and `{@docRoot}` are used across many kinds of documentation comments, subject to each tag's rules.

Before placing a tag in a comment, verify that the tag is valid for the declaration kind being documented. For example, `@return` is not for constructors; `@uses` and `@provides` are only for module declarations.

## 6. Standard tags and custom tags

The JDK 24 standard doclet recognizes a set of standard tags defined in the Javadoc specification. Some familiar tags in JDK documentation—such as `@apiNote`, `@implSpec`, and `@implNote`—are typically configured as **custom tags** in the JDK documentation build process. They are not part of the default standard tag list in the JDK 24 standard doclet specification.

A simple custom block tag can be declared using the `-tag` option:

~~~bash
javadoc -tag 'todo:a:To Do:' ...
~~~

You can write a Taglet when complex formatting or processing is needed. The `-taglet` option loads a Taglet implementation; `-tagletpath` specifies where to find Taglet classes.

Do not use custom tags without configuring Javadoc. If the standard doclet does not recognize a tag, the tool may report an unknown tag or a warning. To avoid colliding with future standard tags, give project-specific tags their own namespace, such as `@com.example.todo`.

## 7. Complete example: writing and generating Javadoc documentation

Create `src/com/example/TextTools.java`:

~~~java
package com.example;

/**
 * Text normalization utility suite.
 *
 * This class provides simple operations to normalize input
 * before storing or comparing it.
 *
 * @author Example Team
 * @version 1.0
 * @since 17
 */
public final class TextTools {

    /**
     * Maximum number of characters in the normalized string.
     */
    public static final int MAX_LENGTH = 120;

    private TextTools() {
    }

    /**
     * Normalizes a string and limits the result length.
     *
     * Removes leading and trailing whitespace, collapses consecutive
     * whitespace into a single space, and truncates the result if it
     * exceeds {@value #MAX_LENGTH}.
     *
     * @param input the input string to normalize
     * @return the normalized string; the result is no longer than
     *     {@value #MAX_LENGTH} characters
     * @throws IllegalArgumentException if input is null
     * @see String#strip()
     * @since 1.0
     */
    public static String normalize(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }

        String result = input.strip().replaceAll("\\s+", " ");
        if (result.length() > MAX_LENGTH) {
            return result.substring(0, MAX_LENGTH);
        }
        return result;
    }

    /**
     * Returns the name using legacy compatibility rules.
     *
     * @deprecated Since version 2.0, use {@link #normalize(String)}.
     */
    @Deprecated(since = "2.0")
    public static String legacyNormalize(String input) {
        return normalize(input);
    }
}
~~~

From the project directory, generate HTML documentation using JDK 17 or later:

~~~bash
javadoc --release 17 -Xdoclint:all -encoding UTF-8 -author -version -d docs src/com/example/TextTools.java
~~~

Explanation:

- `--release 17` selects Java 17 source and API compatibility.
- `-Xdoclint:all` enables all documentation content check groups.
- `-encoding UTF-8` reads source files containing Vietnamese with the correct encoding.
- `-author` and `-version` request displaying the corresponding tags.
- `-d docs` selects the directory for HTML output.
- The Java file at the end of the command is the source used to generate documentation.

If you want warnings to fail the build, add `-Werror`:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -encoding UTF-8 -author -version -d docs src/com/example/TextTools.java
~~~

After running, open `docs/index.html` or the corresponding class page in the `docs` directory. Javadoc generates HTML pages for classes and members, along with summaries, Parameters, Returns, Throws, Since, See Also sections, and deprecation information based on the declared tags.

## 8. Doclint and common errors

Javadoc does not merely turn comments into HTML; it also analyzes references, tag syntax, and HTML structure. Depending on the version, doclint can catch many errors before documentation is published.

### Missing @param

A method has parameters, but the documentation does not describe all of them. Add `@param` for every parameter, including type parameters if present.

### Missing @return

A method returns a value, but the comment does not describe the result. Add `@return` or use `{@return ...}` if appropriate for the JDK version.

### Missing @throws or exception description

A method declares a checked exception without an explanation. Add `@throws` with the trigger condition and meaning of the exception. Do not document unrelated exceptions just to pad the documentation.

### Non-existent reference

For example, `{@link #findById(String)}` when the actual method has a different name or parameter type. Check the class name, package, overloads, and parameter type list. For overloaded methods, always write the full signature when needed.

### Misplaced block tag

A block tag must start a line. If `@param` is written in the middle of a descriptive sentence, Javadoc may misinterpret it or fail to process it as expected. Use inline tags when inserting formatting inside a sentence.

### Using a tag on the wrong declaration kind

For example, `@return` in a constructor or `@uses` in a class comment. Check the valid tag placement table in the Javadoc specification.

### Invalid HTML

HTML tags that are unclosed, improperly nested, or use inappropriate attributes can produce broken pages or warnings. Prefer valid HTML5 and use `{@code}`/`{@literal}` for characters that should be displayed literally.

### Unregistered custom tag

Tags like `@todo` or `@implSpec` may report an unknown tag if `-tag` or `-taglet` is not configured. Confirm whether a tag is built-in or custom in your project's toolchain.

### Using new tags with an older JDK

For example, `{@snippet}` is unavailable on JDK 17 because it was introduced in JDK 18; `@spec` was introduced in JDK 20; the `{@inheritDoc SuperType}` form requires JDK 22 or later. Check the version of `javadoc` being executed, not only the Java version targeted by the application.

## 9. Rules for writing maintainable Javadoc

1. Write a short, specific first sentence that makes complete sense on its own.
2. Describe observable API behavior, including input conditions and outcomes.
3. Use `@param` for all parameters and `@return` for non-void results.
4. Document exceptions with `@throws` and state the actual conditions that trigger the error.
5. Link to related APIs with `{@link}` or `@see`.
6. Record `@since` when adding a new API or changing supported version scope.
7. Use `@Deprecated` alongside `@deprecated` and clearly state the replacement.
8. Use `{@code}` for type names, variables, methods, and short code snippets.
9. Use `{@snippet}` for longer examples when the toolchain supports it and snippets can be verified.
10. Use serialization tags only for classes that actually implement Java Serialization.
11. Keep internal notes or unfinished TODOs out of published API documentation.
12. Run Javadoc in CI with doclint to catch reference errors and missing documentation.

## 10. Quick reference table of JDK 24 standard tags

| Tag | Type | Purpose |
|---|---|---|
| @author | Block | Record the author |
| @deprecated | Block | Explain a deprecated API |
| @exception | Block | Legacy alias for @throws |
| @hidden | Block | Hide an element from generated documentation |
| @param | Block | Describe a parameter or type parameter |
| @provides | Block | Describe a module's service implementation |
| @return | Block | Describe the return value |
| @see | Block | Add a related reference |
| @serial | Block | Describe a field or serialized form scope |
| @serialData | Block | Describe serialization data |
| @serialField | Block | Describe a field in serialPersistentFields |
| @since | Block | Version where the API was introduced |
| @spec | Block | Link to an external specification |
| @throws | Block | Describe an exception |
| @uses | Block | Describe a service used by a module |
| @version | Block | Record the component version |
| {@code} | Inline | Display literal code |
| {@docRoot} | Inline | Relative path to the documentation root |
| {@index} | Inline | Add an entry to the index |
| {@inheritDoc} | Inline | Inherit method documentation content |
| {@link} | Inline | Link to an API with a code-formatted label |
| {@linkplain} | Inline | Link to an API with a plain-text label |
| {@literal} | Inline | Display literal text without a code font |
| {@return} | Inline | Declare the return description at the start of a method |
| {@snippet} | Inline | Embed a code snippet |
| {@summary} | Inline | Specify the summary sentence |
| {@systemProperty} | Inline | Mark a system property name |
| {@value} | Inline | Display a constant's value |

`@exception` is the legacy form; prefer `@throws` in new documentation. `@return` has both a block form and an inline `{@return ...}` form. The tag set and the version each tag was introduced should be verified against your target JDK.

## 11. Key terms to remember

| Term | Meaning |
|---|---|
| Javadoc | Tool that generates API documentation from documentation comments |
| Documentation comment | Comment starting with `/**` attached to a Java declaration |
| Standard doclet | Default doclet that generates HTML documentation |
| Block tag | Tag starting with `@` at the beginning of a line |
| Inline tag | Tag of the form `{@...}` placed inside descriptive text |
| Main description | Primary descriptive section before the first block tag |
| Summary sentence | Summary sentence used in API overview tables |
| Doclint | Suite of checks for Javadoc syntax, references, HTML, and content |
| Taglet | Extension component for handling custom tags |
| Serialized form | Data format and fields saved when an object is serialized |

Javadoc tags form the documentation contract for an API. Describe parameters, results, and exceptions accurately; use links to connect API components; record versions and deprecation status clearly; and finally run doclint to verify the documentation before release.

## References

- Oracle JDK 24 — [Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/doc-comment-spec.html)
- Oracle — [How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html)
- Oracle JDK 24 — [The javadoc Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- OpenJDK — [JDK documentation build tag configuration](https://github.com/openjdk/jdk/blob/master/make/Docs.gmk)