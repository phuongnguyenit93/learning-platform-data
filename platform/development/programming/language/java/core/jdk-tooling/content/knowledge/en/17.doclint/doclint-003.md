# Handling Javadoc Tag Errors with DocLint

Javadoc comments describe Java APIs and are converted into HTML documentation by the **javadoc** tool. A misspelled tag name, a misplaced tag, a nonexistent reference, or invalid HTML can produce warnings or errors when generating documentation. **DocLint** is Javadoc's built-in checker that helps detect most common mistakes before documentation is published.

This lesson uses JDK 17 or later. It focuses on identifying block tag and inline tag errors, fixing incorrect parameter names or references, handling HTML characters, understanding DocLint's check groups, and integrating Javadoc checks into the build process.

## 1. What Are Javadoc Comments and Tags?

A Javadoc comment is a comment that starts with **/**\*** and is placed immediately before the declaration it describes, such as a module, package, class, interface, constructor, method, or field.

Example:

~~~java
/**
 * Converts a message to uppercase.
 */
public String upper(String message) {
    return message.toUpperCase();
}
~~~

Regular comments starting with **/* ** or **//** are not treated as Javadoc comments for a declaration.

A Javadoc comment typically has two parts:

1. Main description: the primary description appearing before the first block tag.
2. Tag section: block tags that provide structured information such as parameters, return values, exceptions, versions, or links.

The first sentence of the main description should be a concise summary that clearly describes the purpose of the API. Once the first block tag appears, the main description ends; do not continue writing the main description afterward.

## 2. Distinguishing Block Tags and Inline Tags

### 2.1. Block Tags

A block tag begins with the **@** character at the start of a line, following the comment's leading asterisk and whitespace. The tag's content extends until the next block tag or the end of the comment.

Example:

~~~java
/**
 * Calculates the total price.
 *
 * @param unitPrice price of one item
 * @param quantity number of items
 * @return the total price
 */
public long total(long unitPrice, int quantity) {
    return unitPrice * quantity;
}
~~~

Common mistakes:

- Writing **@param** in the middle of a line and expecting it to be recognized as a block tag.
- Misspelling a tag name, such as **@returns** instead of **@return**.
- Placing a tag in the main description while forgetting a line break.
- Typing a parameter name that differs from the one in the method declaration.
- Using a tag on a declaration kind that does not support it.

If you want to start a description line with the **@** character without creating a tag, use the HTML entity **&#064;** or place the character inside an appropriate inline tag.

### 2.2. Inline Tags

An inline tag appears within the description text and is enclosed in curly braces.

Example:

~~~java
/**
 * Returns the {@code String} representation of this value.
 * See {@link #toString()} for the textual form.
 */
~~~

Commonly used inline tags:

| Inline tag | Purpose |
|---|---|
| **{@code ...}** | Displays text in code font without parsing its content as HTML or nested tags |
| **{@literal ...}** | Displays text literally without using code font |
| **{@link ...}** | Creates an inline link to a class, method, field, or API |
| **{@linkplain ...}** | Creates a link with its display label rendered in plain text |
| **{@inheritDoc}** | Inserts inherited Javadoc content from a superclass or interface method |
| **{@value}** | Inserts the value of an applicable constant |
| **{@docRoot}** | Relative path to the root of the generated documentation |

A common mistake is omitting the curly braces—for example, writing **@code String** instead of **{@code String}**—or closing the inline tag in the wrong place. Always check the braces, the tag name, and the tag content.

## 3. Placing Tags on the Right Declarations

Not every tag can be used on every kind of declaration.

| Tag | Primary usage | Required information |
|---|---|---|
| **@param** | Class/type parameter, method, constructor | Parameter name or **&lt;T&gt;** for a type parameter |
| **@return** | Method with a return value | Description of the returned value |
| **@throws** | Method, constructor | Exception type and the condition under which it is thrown |
| **@see** | Various declarations | API name, URL, or reference text |
| **@since** | Module, package, type, member | Version in which the API was introduced |
| **@deprecated** | Type or member marked deprecated | Reason and replacement API |
| **@author** | Overview, module, package, type | Author name; displayed when **-author** is used |
| **@version** | Overview, module, package, type | Version info; displayed when **-version** is used |
| **@serial** | Serializable class, package, or field per the corresponding rules | Serialized form guidance |
| **@provides**, **@uses** | Module declaration | Service provided or used |

Important rules:

- **@param** is not used on fields.
- **@return** is only used on methods; do not use it on constructors or **void** methods.
- **@throws** is used on methods and constructors, not as a general exception description on a class.
- **@param &lt;T&gt;** is used for generic type parameters; angle brackets are required.
- **@deprecated** should accompany the **@Deprecated** annotation on the declaration itself.
- **@exception** is an older equivalent of **@throws**; prefer **@throws**.

When a method overrides or implements another method, the standard doclet can inherit the main description and any missing **@param**, **@return**, and **@throws** tags from the superclass/interface method when the corresponding source is available. You can use **{@inheritDoc}** to explicitly insert inherited content. This tag is only valid in supported positions on methods with an inheritance relationship; do not use it on constructors or fields.

## 4. Fixing Common Block Tag Errors

### 4.1. Wrong Name in @param

Declaration:

~~~java
public String greet(String recipient) {
    return "Hello, " + recipient;
}
~~~

Incorrect:

~~~java
/**
 * Greets a recipient.
 *
 * @param name person to greet
 * @return greeting text
 */
~~~

Correct:

~~~java
/**
 * Greets a recipient.
 *
 * @param recipient person to greet
 * @return greeting text
 */
~~~

The name after **@param** must match the actual parameter. For a generic type parameter:

~~~java
/**
 * Wraps a value.
 *
 * @param <T> type of the wrapped value
 * @param value value to wrap
 */
public <T> T identity(T value) {
    return value;
}
~~~

**@param T** and **@param &lt;T&gt;** are not equivalent; generic type parameters must be enclosed in angle brackets.

### 4.2. Missing or Misplaced @return

A method that returns data should describe its result:

~~~java
/**
 * Returns the number of characters in a message.
 *
 * @param message message to measure
 * @return number of UTF-16 code units in the message
 */
public int length(String message) {
    return message.length();
}
~~~

Do not add **@return** to a constructor or a **void** method. For methods returning **boolean**, describe the true and false conditions rather than just writing “the result”.

### 4.3. Wrong Type in @throws

Use a valid exception type name and describe the condition that triggers it:

~~~java
/**
 * Parses a positive integer.
 *
 * @param text text to parse
 * @return parsed integer
 * @throws NumberFormatException if text is not a valid integer
 * @throws IllegalArgumentException if the parsed value is not positive
 */
public int parsePositive(String text) {
    int value = Integer.parseInt(text);
    if (value <= 0) {
        throw new IllegalArgumentException("value must be positive");
    }
    return value;
}
~~~

The name after **@throws** must resolve to an exception type in Javadoc. You can document unchecked exceptions even if they do not appear in the method signature's **throws** clause. Do not document a regular class that does not extend **Throwable**.

### 4.4. Duplicate or Extra Tags

Check that every tag corresponds to the declaration:

- Do not write two **@return** tags for the same method.
- Do not repeat **@param** for the same parameter.
- Do not add **@param** for a nonexistent parameter name.
- Do not add **@throws** for a misspelled type name.
- Do not put **@return** on a constructor or a **void** method.

Duplicate tags or extraneous information can produce warnings; malformed tags or invalid references can produce errors. The best fix is to update the comment to match the actual API signature.

## 5. Fixing Inline Tag and API Reference Errors

### 5.1. Linking Syntax with {@link}

A member reference typically has the form:

~~~text
{@link package.Class#method(Type) label}
~~~

You can omit the package or class when referencing a member in the same class:

~~~java
/**
 * Formats a message. Use {@link #normalize(String) normalize}
 * before storing user input.
 */
public String format(String text) {
    return normalize(text);
}

/**
 * Normalizes whitespace.
 *
 * @param text input text
 * @return normalized text
 */
private String normalize(String text) {
    return text.trim();
}
~~~

If there are overloads, specify the parameter types so Javadoc selects the right method. If a class or member name fails to resolve, check:

1. Whether the package and class names are accurate.
2. Whether the member name has the exact casing.
3. Whether the parameter type list matches the signature.
4. Whether the reference is missing **#**, parentheses, or commas.
5. Whether the referenced type is in sources/APIs that Javadoc can locate.

If the class belongs to an external API, use **-link** or **-linkoffline** to create hyperlinks to external Javadoc sets. **-link** requires a URL to a documentation directory containing **element-list** or **package-list**; **-linkoffline** is useful when the list file is available locally but the target documentation is not reachable during the build.

### 5.2. {@link} and {@linkplain}

Both create links to an API. **{@link}** renders the label in code style; **{@linkplain}** renders the label as plain text.

Example:

~~~java
/**
 * Converts the input using {@link String#strip()}.
 * See {@linkplain String#trim() the trim method} for related behavior.
 */
~~~

If a link does not work, check the member reference syntax and the reachability of external documentation. Do not replace a link with plain text just to hide a broken reference.

### 5.3. Misplaced {@inheritDoc}

**{@inheritDoc}** inserts the description from an overridden or implemented method. Use it in the main description or in the body of **@param**, **@return**, or **@throws** on an eligible method.

Example:

~~~java
interface MessageSource {
    /**
     * Loads a message for a key.
     *
     * @param key message key
     * @return resolved message
     */
    String load(String key);
}

final class DefaultMessageSource implements MessageSource {
    /**
     * {@inheritDoc}
     */
    @Override
    public String load(String key) {
        return key;
    }
}
~~~

If a method does not override or implement a method that has documentation to inherit, Javadoc cannot find matching content. In that case, write the description directly or place **{@inheritDoc}** on a method with a valid inheritance relationship.

## 6. Handling HTML Characters and Code Content

Javadoc comments can contain HTML. The characters **&lt;**, **&gt;**, and **&amp;** have special meaning in markup; if used as plain text, they must be escaped or placed inside an appropriate inline tag.

Incorrect:

~~~java
/**
 * Returns true if size < limit and size > 0.
 */
~~~

Correct using **{@code}**:

~~~java
/**
 * Returns true if {@code size < limit && size > 0}.
 */
~~~

Or using HTML entities:

~~~java
/**
 * Returns true if size &lt; limit and size &gt; 0.
 */
~~~

Notes:

- Use **{@code ...}** for class names, expressions, commands, and short code snippets.
- Use **{@literal ...}** when you need to preserve characters literally without code font.
- Escape an ampersand as **&amp;** when it is plain text.
- Close HTML elements that require an end tag.
- Do not nest block elements inside inline elements.
- Use valid HTML5 markup.
- For **&lt;img&gt;**, provide meaningful **alt** text.
- For tables, add a caption or appropriate information to support accessibility.

A block tag can also be misrecognized if a description line starts with **@**. In that case, use the **&#064;** entity or place the content inside **{@code}**.

## 7. What Does DocLint Check?

In JDK 17, DocLint is enabled by default when running the **javadoc** tool. It checks common categories of issues in documentation comments.

| Group | Checks | Example errors |
|---|---|---|
| **accessibility** | Accessibility issues in HTML | Table missing a caption or image missing appropriate alt text |
| **html** | HTML structure and element nesting | Missing closing tag or placing a block element inside an inline element |
| **missing** | Missing Javadoc comments or required tags | Missing class description, **@param**, or **@return** |
| **reference** | References to Java elements | **@see** or **{@link}** pointing to a nonexistent member; wrong **@param** name |
| **syntax** | Javadoc syntax and special characters | Invalid tag, unescaped **&lt;** or **&amp;** |

DocLint is not a full HTML validator and does not fix comments automatically. It helps catch most common errors; generated documentation should still be inspected further if strict HTML/accessibility requirements apply.

### 7.1. Enable All Check Groups

~~~powershell
javadoc -Xdoclint:all -d docs -sourcepath src com.example
~~~

JDK 17 enables DocLint by default, but explicitly passing **-Xdoclint:all** in the build makes the checking intent clearer.

### 7.2. Select Check Groups

Check only HTML, syntax, and accessibility:

~~~powershell
javadoc -Xdoclint:html,syntax,accessibility -d docs -sourcepath src com.example
~~~

Disable the **missing** group while keeping the rest:

~~~powershell
javadoc -Xdoclint:all,-missing -d docs -sourcepath src com.example
~~~

Disable DocLint completely:

~~~powershell
javadoc -Xdoclint:none -d docs -sourcepath src com.example
~~~

Only disable a group when you understand which warnings are being skipped and have an alternative review process in place. **-Xdoclint:none** does not fix comments; it only stops reporting DocLint issues.

### 7.3. Turn Warnings into Errors in CI

Use **-Werror** to fail the build if Javadoc emits any warnings:

~~~powershell
javadoc -Xdoclint:all -Werror -d docs -sourcepath src com.example
~~~

This is useful in CI because documentation warnings are not silently ignored. If a project has many existing warnings, clean them up group by group before enabling **-Werror** across the entire build.

### 7.4. Choose the Scope of Checked Declarations

By default, Javadoc generates documentation for public and protected APIs. Visibility options affect which declarations are included in the output and checked:

| Option | Scope |
|---|---|
| **-public** | Public only |
| **-protected** | Public and protected; this is the default |
| **-package** | Public, protected, and package-private |
| **-private** | All, including private |

If errors only appear when checking internal documentation, run with **-private** to widen the scope.

**javac** also supports **-Xdoclint** to check comments during compilation, though it is not enabled by default in **javac**. Generating documentation with **javadoc** remains necessary to verify the HTML output.

## 8. Complete Example: Valid and Runnable Javadoc

Create the structure:

~~~text
project/
└── src/
    └── com/
        └── example/
            ├── package-info.java
            └── TextFormatter.java
~~~

Contents of **src/com/example/package-info.java**:

~~~java
/**
 * Public API for formatting short messages.
 */
package com.example;
~~~

Contents of **src/com/example/TextFormatter.java**:

~~~java
package com.example;

import java.util.Objects;

/**
 * Combines a prefix and a value into a message.
 *
 * <p>Use {@link #format(String,String) format} to create a message.
 */
public final class TextFormatter {

    /**
     * Creates a formatter.
     */
    public TextFormatter() {
    }

    /**
     * Joins a prefix and a value.
     *
     * @param prefix text placed before the value
     * @param value text placed after the prefix
     * @return the combined message
     * @throws java.lang.NullPointerException if prefix or value is null
     * @since 1.0
     */
    public String format(String prefix, String value) {
        return Objects.requireNonNull(prefix)
                .concat(Objects.requireNonNull(value));
    }

    /**
     * Prints a sample formatted message.
     *
     * @param args command-line arguments; not used
     */
    public static void main(String[] args) {
        System.out.println(new TextFormatter().format("Hello, ", "Java!"));
    }
}
~~~

From the **project** directory, generate documentation with all DocLint groups and treat warnings as errors:

~~~powershell
javadoc -Xdoclint:all -Werror -d docs -sourcepath src com.example
~~~

Compile and run the example:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac -d out src/com/example/TextFormatter.java
java -cp out com.example.TextFormatter
~~~

Exact stdout:

~~~text
Hello, Java!
~~~

This example includes a package comment, class comment, constructor comment, **@param**, **@return**, **@throws**, **@since**, and **{@link}**. All parameter names and references match their declarations, making it a solid template for a DocLint-enabled build.

## 9. Reading Diagnostics and Locating Errors

When an issue is detected, Javadoc typically prints a message, the relevant source line, and a **^** caret pointing to the error location. Exact message wording may vary across JDK versions.

Error-reading workflow:

1. Read the file name and line number first.
2. Check the DocLint group if stated in the diagnostic.
3. Inspect the tag or HTML right at the indicated position.
4. Compare the tag against the method/type signature.
5. Fix the root cause and re-run the same command.

Common diagnostic patterns you may encounter:

| Error pattern | What to check |
|---|---|
| Invalid tag or unknown tag | Spelling, block/inline syntax, and whether a custom tag is registered |
| Invalid **@param** | Parameter name or **&lt;T&gt;** syntax |
| Missing **@return** | Method has a return value but lacks a return description |
| Reference not found | Class/member name, overload signature, imports, and external links |
| End tag missing | Unclosed HTML element |
| Unescaped **&lt;** or **&amp;** | Use **{@code}**, **{@literal}**, or an HTML entity |
| Missing comment | Declaration is within the generated scope but lacks a Javadoc comment |
| Invalid use of **{@inheritDoc}** | Method has no matching parent/interface comment or tag is placed in an invalid position |

Do not fix comments merely to silence the message. Make sure the updated description still accurately reflects the API's behavior.

## 10. Distinguishing Warnings and Errors

DocLint can report warnings or errors depending on how severely the issue affects the generated documentation.

- Warnings typically relate to missing content, duplicate information, or unnecessary comments that do not yet render the HTML invalid.
- Errors typically relate to invalid Javadoc syntax, broken references, or HTML that can produce invalid output.

If a build succeeds with warnings, documentation may still be generated. However, warnings on public APIs are usually a sign of incomplete documentation or drift from the code. For published libraries, resolve warnings rather than ignoring them.

**-Werror** turns warnings into build errors. Enable it once existing warnings are cleaned up to prevent new documentation issues from slipping into a release.

## 11. Custom Tags and Taglets

Projects may use custom tags for internal workflows. If Javadoc encounters a tag outside the standard doclet, register it using the **-tag** option or implement a taglet using **-taglet**.

General syntax:

~~~text
-tag name:locations:header
~~~

Fields are separated by **:**. **name** is the tag name, **locations** specifies where the tag is allowed, and **header** is the label displayed in the documentation.

If a project uses custom tags, standardize their definitions in the build so Javadoc recognizes them. When complex rendering logic or multi-argument inline tags are needed, use an appropriate Taglet.

Do not convert a standard tag like **@param** into a custom tag. For standard tags, fix their syntax and usage according to the specification.

## 12. Workflow for Fixing Javadoc Tag Errors

When a Javadoc build fails:

1. Re-run the exact **javadoc** command and keep the full diagnostic output.
2. Categorize the error into **syntax**, **html**, **reference**, **missing**, or **accessibility**.
3. Verify that the Javadoc comment starts with **/**\*** and sits immediately before the declaration.
4. Cross-check **@param**, **@return**, and **@throws** against the method signature.
5. Fix tag names, inline tag braces, and **{@link}**/**@see** references.
6. Escape HTML characters and fix element structure.
7. If using custom tags, register them with **-tag** or a taglet.
8. Re-run **javadoc -Xdoclint:all**.
9. Once no actionable warnings remain, enable **-Werror** in CI.
10. Open a few generated HTML pages to verify content, links, and readability.

If you only want to find issues in one category, use selective DocLint options. After fixing them, re-run all groups to ensure no errors remain elsewhere.

## 13. Pre-Release Javadoc Checklist

- [ ] Javadoc comments use **/**\* ... */** and are placed immediately before declarations.
- [ ] Main descriptions have a clear summary sentence.
- [ ] Block tags start at the beginning of a line and are not mixed into plain text.
- [ ] Every **@param** matches the exact parameter name; generic parameters use **&lt;T&gt;**.
- [ ] **@return** is used only on methods with a return value.
- [ ] **@throws** points to a valid exception type and describes the triggering condition.
- [ ] **{@link}** and **@see** point to existing classes/members.
- [ ] **{@inheritDoc}** is used only on methods with an appropriate inheritance relationship.
- [ ] Inline tags have matching curly braces.
- [ ] Characters **&lt;**, **&gt;**, and **&amp;** are escaped or placed inside **{@code}**/**{@literal}**.
- [ ] HTML elements are properly closed and nested; tables/images have appropriate accessibility info.
- [ ] Custom tags are registered in the build.
- [ ] **javadoc -Xdoclint:all** succeeds.
- [ ] Important warnings are resolved; CI uses **-Werror** where appropriate.
- [ ] Generated HTML has been checked in a browser or required validator.

Javadoc tag errors usually stem from the wrong tag kind, misplacement, mismatched parameter names, nonexistent API references, or invalid HTML. Read DocLint's diagnostics, align comments with the Java declarations, and re-run **javadoc -Xdoclint:all**. Use **-Werror** in CI to ensure documentation warnings are addressed before release.

## References

- Oracle, The javadoc Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html
- Oracle, Documentation Comment Specification for the Standard Doclet, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html
- Oracle, The javac Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html