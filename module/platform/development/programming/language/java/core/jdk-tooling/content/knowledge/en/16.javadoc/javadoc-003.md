# Doc Comments and Javadoc in Java

## Objectives

After this lesson, you will be able to distinguish regular comments from documentation comments; place doc comments properly for classes, fields, constructors, and methods; use block tags and inline tags to describe APIs; generate HTML documentation using the `javadoc` tool; check for errors using DocLint; organize documentation for packages and modules; and use Markdown comments and code snippet features in the appropriate JDK versions.

## 1. What Is a Doc Comment?

A **doc comment (documentation comment)** is a structured comment placed next to a Java declaration to describe the usage, meaning, preconditions, and results of that API. The **javadoc** tool reads doc comments along with their declarations in the source code and generates API documentation, which defaults to HTML pages.

Doc comments help library users understand:

- What a class or interface is used for.
- Under what conditions a constructor creates an object.
- What parameters a method accepts and what value it returns.
- What exceptions a method may throw and under what circumstances.
- What value a field or constant represents.
- Which version introduced the API or whether it has been deprecated.
- How methods relate to one another.

Doc comments are part of source documentation. Their content does not change program logic, does not automatically enforce contracts at runtime, and does not replace writing tests. A description stating that a method does not accept `null` does not cause the JVM to automatically reject `null`; the code must enforce that condition if the API requires it.

## 2. Distinguishing Comment Types

Java has regular comments and documentation comments:

| Syntax | Name | Processed by Javadoc as API documentation? |
|---|---|---|
| // ... | Line comment | No |
| /* ... */ | Traditional comment | No |
| /** ... */ | Traditional documentation comment | Yes |
| /// ... | Markdown documentation comment | Yes, starting in JDK 23 |

Examples of regular comments:

~~~java
// Calculate the sum of two numbers.
int total = 2 + 3;

/*
 * This section explains a block of code.
 */
~~~

The two comments above are only for readers of the source code. The `javadoc` tool does not use them to generate API descriptions.

A traditional doc comment begins with a slash and two asterisks:

~~~java
/**
 * Adds two integers and returns their sum.
 *
 * @param left first addend
 * @param right second addend
 * @return the sum of the two values
 */
public static int add(int left, int right) {
    return left + right;
}
~~~

Javadoc recognizes a doc comment when it appears immediately before the declaration being described. The comment should precede annotations, modifiers, keywords, or the declaration name. If multiple doc comments appear before the same declaration, only the one closest to the declaration is used. A comment placed after a declaration has already started will not be attached to that declaration.

Doc comments can apply to modules, packages, classes, interfaces, constructors, methods, annotation elements, enum members, and fields. Do not use a doc comment to describe a local variable or an arbitrary statement inside a method.

## 3. Writing Well-Structured Traditional Doc Comments

A traditional doc comment typically has the following form:

~~~java
/**
 * Main description: briefly explains what this declaration does.
 *
 * Usage notes, preconditions, examples, and remarks can be added here.
 *
 * @param name parameter description
 * @return return value description
 * @throws IllegalArgumentException description of when the exception is thrown
 * @since 1.0
 */
~~~

The content before the first block tag is called the **main description**. It cannot continue after block tags have started. Additional information is written using block tags on separate lines.

### Writing the First Summary Sentence

The first sentence of the main description should be a short, complete sentence that accurately describes the declaration. Javadoc commonly uses this first sentence in summary tables, indexes, and places where a brief description is needed.

Good example:

~~~java
/**
 * Converts a temperature from Celsius to Fahrenheit.
 */
~~~

Poor example:

~~~java
/**
 * This method. It does some conversion.
 */
~~~

Avoid opening with generic phrases like "This method does something". Describe the specific behavior, inputs, or key results.

If you want to specify the summary sentence explicitly rather than relying on how Javadoc detects the first sentence, you can use the `{@summary ...}` inline tag at the start of the main description:

~~~java
/**
 * {@summary Adds two integers and returns their sum.}
 *
 * The method uses normal Java integer arithmetic.
 */
~~~

### Writing Paragraphs and HTML

Traditional doc comments support plain text, inline tags, and HTML. You can use HTML5 elements such as:

- `p` to separate paragraphs.
- `ul` and `li` for lists.
- `pre` to preserve block formatting.
- `a` to create links.
- `code` to display API names or short code snippets.

Example:

~~~java
/**
 * Reads a configuration value.
 *
 * <p>The method checks the supplied key before returning its value.
 *
 * <ul>
 *   <li>Keys are case-sensitive.</li>
 *   <li>A missing key returns the default value.</li>
 * </ul>
 */
~~~

Do not use malformed HTML. When writing special characters such as less-than, greater-than, or ampersand in descriptions, use appropriate HTML entities or inline tags so Javadoc does not misinterpret them as markup.

If you write HTML headings inside a doc comment, choose a heading level appropriate for the declaration's position so the generated HTML page structure remains valid. For classes, packages, and modules, headings inside comments typically start at level 2; for methods, fields, and members, they typically start at level 4. Markdown documentation comments have their own heading rules.

## 4. Important Block Tags

A block tag starts with the `@` character at the beginning of a line, after the main description. Tag names and the targets they describe must match the declaration.

### @param

Used to describe each parameter of a method or constructor. Every formal parameter should have a corresponding tag:

~~~java
/**
 * Returns the larger of two values.
 *
 * @param first first value to compare
 * @param second second value to compare
 * @return the larger value
 */
public static int max(int first, int second) {
    return Math.max(first, second);
}
~~~

For generic methods, type parameters are also documented with `@param`. The type parameter name must be enclosed in angle brackets:

~~~java
/**
 * Returns the supplied value.
 *
 * @param <T> type of the value
 * @param value value to return
 * @return the same value
 */
public static <T> T identity(T value) {
    return value;
}
~~~

Here there are two kinds of parameters to distinguish: `<T>` is a type parameter, while `value` is a formal parameter.

### @return

Used for methods with a return type other than `void`. Describe the meaning and conditions of the return value, rather than merely repeating the type name.

~~~java
/**
 * Calculates the area of a rectangle.
 *
 * @param width rectangle width
 * @param height rectangle height
 * @return the rectangle area
 */
public static double area(double width, double height) {
    return width * height;
}
~~~

Methods returning `void` do not use the `@return` block tag. If a method returns a `boolean`, clearly describe what `true` and `false` mean.

### @throws and @exception

Used to describe exceptions that a method or constructor may throw:

~~~java
/**
 * Divides one integer by another.
 *
 * @param numerator number being divided
 * @param denominator divisor
 * @return integer quotient
 * @throws IllegalArgumentException if denominator is zero
 */
public static int divide(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException("denominator must not be zero");
    }
    return numerator / denominator;
}
~~~

`@exception` is an older equivalent tag name, but `@throws` should be preferred.

Exception descriptions must clearly state the condition under which the exception occurs. You do not need to list every error that could happen in the JVM; focus on cases that are meaningful to the API contract.

Checked exceptions appearing in the `throws` clause should be documented. Unchecked exceptions might not appear in the `throws` clause, but can still be documented with `@throws` if API users need to know about them.

### @see

Used to refer to a related class, method, field, package, or document:

~~~java
/**
 * Returns the absolute value of a number.
 *
 * @param value input value
 * @return absolute value
 * @see Math#abs(int)
 */
public static int absolute(int value) {
    return Math.abs(value);
}
~~~

If you want to insert a link directly inside a descriptive sentence, use the `{@link ...}` or `{@linkplain ...}` inline tag.

### @since

Indicates the version in which the API was introduced:

~~~java
/**
 * Returns a normalized identifier.
 *
 * @param value identifier to normalize
 * @return normalized identifier
 * @since 2.1
 */
~~~

`@since` should reflect the actual product or library version. Do not write a JDK version if the API belongs to an application version and has no direct connection to it.

### @deprecated

Used to warn that an API is no longer recommended and to point to its replacement. Combine this tag with the `@Deprecated` annotation:

~~~java
/**
 * Adds two values using the legacy method name.
 *
 * @deprecated since 2.0; use {@link #add(int, int)} instead.
 */
@Deprecated(since = "2.0")
public static int sumLegacy(int left, int right) {
    return add(left, right);
}
~~~

The first sentence of the deprecated section should state the deprecation version and the replacement API. If there are compatibility or maintenance reasons, add them in subsequent sentences.

### @author and @version

- `@author` records the author or responsible team.
- `@version` records the version of the software or component being described.

These two tags are only displayed when the corresponding options, such as `-author` and `-version`, are used. Do not add tags just to fill space; follow your project's documentation conventions.

### Serialization and Module Tags

Some tags have specialized scopes:

| Tag | Purpose |
|---|---|
| @serial | Describes a serializable field or serialized state |
| @serialField | Describes a field in `serialPersistentFields` |
| @serialData | Describes data written by serialization methods |
| @uses | Documents a service used by a module |
| @provides | Documents a service provider supplied by a module |

The `@uses` and `@provides` tags are only used in the doc comment of a module declaration. They help module documentation express JPMS service relationships.

## 5. Common Inline Tags

Inline tags have the form `{@tag ...}` and can appear inside descriptive sentences.

| Inline tag | Purpose |
|---|---|
| {@code text} | Displays text in code font without processing nested HTML or tags |
| {@literal text} | Displays text verbatim without using code font |
| {@link reference} | Creates a link to an API in code font |
| {@linkplain reference} | Creates a link in normal text font |
| {@value} | Displays the value of a compile-time constant |
| {@inheritDoc} | Inherits the corresponding documentation from an overridden method |
| {@summary text} | Explicitly specifies the summary sentence |
| {@docRoot} | Relative path to the root directory of the generated documentation |
| {@snippet ...} | Inserts a formatted code snippet |

### @code and @literal

Use `@code` for class names, method names, values, or expressions:

~~~java
/**
 * Returns {@code true} when the collection is empty.
 */
~~~

Use `@literal` when you need verbatim text without code font:

~~~java
/**
 * The text {@literal <unknown>} is used when no name is available.
 */
~~~

`@code` is useful when text contains `<` or `>` because the content is rendered as code and not interpreted as an HTML tag.

### @link and @linkplain

Link to an API directly within a sentence:

~~~java
/**
 * Use {@link String#isBlank()} to check whether a string contains
 * only whitespace characters.
 *
 * See also {@linkplain java.util.Objects Objects}.
 */
~~~

A reference typically has the form:

~~~text
package.Class#member(parameterTypes)
~~~

If a method is overloaded, include the parameter type list so Javadoc resolves the right method. You can also supply a label to customize the displayed link text.

### @value

Used to insert the value of a static field that is a compile-time constant:

~~~java
/**
 * Default retry count: {@value}.
 */
public static final int DEFAULT_RETRIES = 3;
~~~

`@value` does not invoke getters or evaluate runtime expressions. It is intended for constants whose values Javadoc can determine at compile time.

### @inheritDoc

When overriding a method, you can inherit the description from the superclass or interface method:

~~~java
/**
 * {@inheritDoc}
 */
@Override
public String toString() {
    return "Calculator";
}
~~~

You can add your own content if the implementation has specific conditions or behavior. When an overriding method changes only certain parameters or exceptions, check what can be inherited and what must be documented anew.

### @snippet

The `@snippet` tag was added in JDK 18 to make embedding code examples in documentation more convenient than using only `@code` and `pre`:

~~~java
/**
 * Example:
 *
 * {@snippet :
 * int total = Calculator.add(7, 5);
 * System.out.println(total);
 * }
 */
~~~

Snippets can be written inline inside the comment, loaded from an external file, or combined as a hybrid of both. External snippets are useful when long examples need to be compiled and tested separately in the source tree.

An external snippet can be placed in a `snippet-files` directory per package or located via the `--snippet-path` option. Markup comments inside a snippet can mark regions, highlight lines, or link code segments.

Note: Javadoc includes snippets in the documentation and assists with presentation; do not assume that every snippet is automatically compiled and tested. Set up tests for important examples in your build.

## 6. Markdown Documentation Comments from JDK 23

Starting in JDK 23, Javadoc supports writing doc comments in Markdown under JEP 467. The syntax uses a sequence of consecutive lines starting with three slashes:

~~~java
/// # Calculator
///
/// Provides integer arithmetic operations.
///
/// Use the method [add(int, int)][#add(int, int)] to add two values.
///
/// @since 1.0
public final class Calculator {
    // declarations
}
~~~

Markdown comments support:

- Headings, paragraphs, lists, and fenced code blocks.
- CommonMark links and simple GFM pipe tables.
- Javadoc inline tags and block tags.
- Convenient links to program elements in the API.

Every line belonging to the same Markdown doc comment, including blank lines, must start with `///`. A completely blank line terminates the comment sequence. If you need a blank line, write `///` on that line.

Example:

~~~java
/// This comment contains two paragraphs.
///
/// The second paragraph is part of the same doc comment.
public void run() {
}
~~~

Avoid writing:

~~~java
/// This comment ends here.

/// This becomes a separate comment.
public void run() {
}
~~~

In the incorrect example, the blank line without `///` breaks the Markdown doc comment sequence.

Markdown doc comments can combine Javadoc tags and HTML when needed. Do not place Javadoc tags inside literal code spans or fenced code blocks, because they are treated as code content there.

If a project needs to support JDK 17 or 21, use traditional `/** ... */` comments for compatibility. Markdown documentation comments require JDK 23 or later.

## 7. Doc Comments for Packages and Modules

### package-info.java

Use `package-info.java` to describe a package's purpose, main APIs, usage conventions, and relationships with other packages.

~~~java
/**
 * Provides reusable arithmetic utilities.
 *
 * <p>Public classes in this package are intended for application code.
 */
package com.example.math;
~~~

This file may contain package annotations and import statements. This is the recommended approach for modern package documentation; `package.html` is only supported for historical compatibility.

### module-info.java

Modules can have their own doc comments:

~~~java
/**
 * Provides mathematical utilities for client applications.
 *
 * @uses java.util.spi.ToolProvider
 */
module com.example.math {
    exports com.example.math;
}
~~~

When a module provides or uses a service, you can document it with `@provides` and `@uses` in the module doc comment. These tags explain service contracts and provider/service behavior for module users.

### doc-files

You can add supplementary documentation for a package in a `doc-files` directory:

~~~text
src/
└── com/example/math/
    ├── package-info.java
    ├── Calculator.java
    └── doc-files/
        ├── usage.md
        └── architecture.html
~~~

Javadoc can process HTML or Markdown files inside `doc-files`. Use them for long guides, diagrams, multi-step examples, or documentation that does not fit directly in a single declaration's comment.

## 8. Complete Example: Writing Doc Comments and Generating Javadoc

Create the file `src/com/example/Calculator.java`:

~~~java
package com.example;

/**
 * Provides small integer arithmetic utilities.
 *
 * <p>Use {@link #add(int, int)} to add values and
 * {@link #divide(int, int)} for integer division.
 *
 * @since 1.0
 * @see java.lang.Math
 */
public final class Calculator {

    /**
     * Default number of retry attempts used by examples.
     */
    public static final int DEFAULT_RETRIES = 3;

    private Calculator() {
    }

    /**
     * Adds two integers.
     *
     * @param left first addend
     * @param right second addend
     * @return sum of left and right
     * @since 1.0
     */
    public static int add(int left, int right) {
        return left + right;
    }

    /**
     * Divides one integer by another using integer division.
     *
     * @param numerator value being divided
     * @param denominator divisor
     * @return quotient rounded toward zero
     * @throws IllegalArgumentException if denominator is zero
     */
    public static int divide(int numerator, int denominator) {
        if (denominator == 0) {
            throw new IllegalArgumentException(
                    "denominator must not be zero");
        }
        return numerator / denominator;
    }

    /**
     * Returns the supplied value after checking that it is not null.
     *
     * @param <T> type of the supplied value
     * @param value value to validate
     * @param name parameter name used in the exception message
     * @return the same value
     * @throws IllegalArgumentException if value is null
     */
    public static <T> T requireValue(T value, String name) {
        if (value == null) {
            throw new IllegalArgumentException(
                    name + " must not be null");
        }
        return value;
    }

    /**
     * Adds two values using the legacy method name.
     *
     * @deprecated since 2.0; use {@link #add(int, int)} instead.
     */
    @Deprecated(since = "2.0")
    public static int sumLegacy(int left, int right) {
        return add(left, right);
    }

    /**
     * Runs a small demonstration of the arithmetic methods.
     *
     * @param args command-line arguments; not used by this example
     */
    public static void main(String[] args) {
        System.out.println("sum=" + add(7, 5));
        System.out.println("quotient=" + divide(9, 2));
        System.out.println("value=" + requireValue("Java", "language"));
    }
}
~~~

Compile the program with JDK 17 or later:

~~~bash
javac --release 17 -d out src/com/example/Calculator.java
~~~

Run:

~~~bash
java -cp out com.example.Calculator
~~~

Exact output:

~~~text
sum=12
quotient=4
value=Java
~~~

Generate HTML documentation with `javadoc`:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -d docs src/com/example/Calculator.java
~~~

After a successful run, the `docs` directory contains the HTML API pages, including:

~~~text
docs/
├── index.html
├── allclasses-index.html
└── com/
    └── example/
        └── Calculator.html
~~~

Depending on the JDK version and standard doclet configuration, the directory may also contain CSS, JavaScript, search index files, and navigation pages.

This example demonstrates:

- Doc comments on a class and methods.
- `@param` for regular parameters and type parameters.
- `@return` and `@throws`.
- `@since`, `@see`, and `@deprecated`.
- Inline links to other methods.
- A constant field that can be referenced with `{@value}`.
- A program that can be compiled and executed independently of the documentation generation step.

## 9. Common javadoc Options

| Option | Purpose |
|---|---|
| -d docs | Specifies the output directory for HTML documentation |
| -sourcepath src | Specifies the directory containing source packages |
| -subpackages com.example | Generates docs for the package and its subpackages |
| -public | Generates documentation only for the public API |
| -protected | Generates documentation for public and protected APIs; this is the default |
| -package | Includes package-private APIs as well |
| -private | Includes private APIs as well |
| -author | Displays `@author` |
| -version | Displays `@version` |
| -link URL | Links to Javadoc of an external library or API |
| -Xdoclint:all | Enables all DocLint check groups |
| -Werror | Treats warnings as errors |

Generate documentation for an entire package and its subpackages:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example
~~~

If the documentation references external Java SE APIs, you can link to the JDK Javadoc:

~~~bash
javadoc --release 17 -d docs -link https://docs.oracle.com/en/java/javase/17/docs/api/ -sourcepath src -subpackages com.example
~~~

The URL passed to `-link` must point to the root directory of the external Javadoc documentation containing a matching `element-list` or `package-list`, not the URL of a single class page.

### DocLint Options

DocLint helps detect common errors in doc comments. Main check groups:

| Group | Content |
|---|---|
| accessibility | Accessibility issues, such as missing `alt` attributes or captions |
| html | Malformed HTML or missing closing tags |
| missing | Missing doc comments or required tags |
| reference | Invalid links to classes, methods, parameters, or exceptions |
| syntax | Invalid tag syntax or unescaped HTML characters |

`javadoc` enables DocLint by default for generated documentation. In CI, you can specify it explicitly:

~~~bash
javadoc -Xdoclint:all -Werror -d docs src/com/example/Calculator.java
~~~

- `-Xdoclint:all` enables every check group.
- `-Werror` causes the build to fail if any warnings occur.

Do not disable DocLint just to make a build pass when there are reference or HTML errors. Fix the underlying content. DocLint is not a complete HTML validator; after generating documentation, projects can still use HTML/accessibility validators to check the final output.

## 10. Guidelines for Writing Quality Doc Comments

A good doc comment answers the API user's questions rather than merely repeating the method name.

### Describe Behavior and Contracts

Document:

- Valid input conditions.
- Default values or limits.
- What the return value means.
- Side effects, if any.
- Possible exceptions and their causes.
- Thread-safety or immutability, if relevant.
- Resource lifecycle: who opens, who closes, and who owns the resource.

For example, instead of writing "Gets user", explain that the method looks up a user by ID, returns `Optional.empty` when not found, and throws an exception when the ID is invalid if that is the actual contract.

### Avoid Inaccurate or Vague Descriptions

Avoid descriptions such as:

- "Returns the result" without explaining what the result is.
- "Throws exception on error" without stating the condition.
- "Fast method" without measurement context.
- "Thread-safe" when the implementation does not guarantee it.
- "Never null" when the code can still return `null`.

If an API behaves differently depending on inputs or object state, clearly describe each case.

### Keep Documentation Synchronized with Code

When renaming parameters, changing return types, exceptions, default values, or behavior, update the doc comment in the same change. Do not leave documentation describing an outdated API.

If an overriding method inherits its contract from an interface, use `@inheritDoc` where appropriate. If the implementation has additional conditions, clearly document the differences.

### Write Verifiable Examples

Code examples should:

- Use accurate packages/imports and current APIs.
- Have output that matches the code.
- Not depend on unstated environment assumptions.
- Be compiled or executed in tests whenever possible.
- Clearly state the minimum JDK version if using newer features.

For long examples, prefer `@snippet` and separate source files so the code can be tested as part of the project.

## 11. Common Pitfalls and How to Fix Them

### Using /* ... */ Instead of /** ... */

**Symptom:** The comment appears in source code but not in the API documentation.

**Cause:** Regular comments are not treated as documentation comments by the standard doclet.

**Fix:** Use `/** ... */` or Markdown `///` appropriate for the JDK version.

### Misplaced Doc Comment

**Symptom:** Javadoc does not attach the comment to the intended method or class.

**Cause:** An annotation, modifier, declaration, or another comment sits between the comment and the declaration.

**Fix:** Place the doc comment immediately before the annotations and declaration. Keep only one doc comment per declaration.

### Missing @param or @return

**Symptom:** DocLint warns that method documentation is missing information.

**Cause:** A tag for a parameter or return type is missing, or the parameter name in the tag does not match the source code.

**Fix:** Check each formal parameter and type parameter; add `@return` for non-`void` methods.

### Incorrect Type Parameter Name

**Symptom:** The tag does not link to the type parameter or DocLint reports a reference error.

**Cause:** Using `@param T` instead of `@param <T>`.

**Fix:** Enclose the type parameter in angle brackets, then document regular parameters using their exact declared names.

### Ambiguous Link to an Overloaded Method

**Symptom:** The link fails to resolve or points to the wrong method.

**Cause:** Omitting the parameter list when the class has multiple overloads with the same name.

**Fix:** Write the full reference such as `#add(int, int)` or use imported/fully qualified type names as appropriate.

### < and > Characters Breaking HTML

**Symptom:** Javadoc reports a syntax error or HTML renders incorrectly.

**Cause:** Using special characters as markup without escaping them.

**Fix:** Use `{@code ...}`, `{@literal ...}`, or appropriate HTML entities.

### @deprecated Without a Replacement API

**Symptom:** Users know the old API should not be used, but do not know what to use instead.

**Cause:** Missing guidance in the deprecated section.

**Fix:** Combine `@Deprecated` with `@deprecated`, state the deprecation version, and link to the replacement API.

### Broken Markdown Comment

**Symptom:** Only part of the content is recognized as a doc comment.

**Cause:** A blank line does not start with `///`, or another comment intervenes between lines.

**Fix:** Ensure every line in the Markdown doc comment sequence, including blank lines, begins with `///`. This feature requires JDK 23 or later.

### Javadoc Generates HTML but Content Errors Remain

**Symptom:** The `javadoc` command succeeds, but the generated doc pages have broken links or missing descriptions.

**Cause:** Not every content issue causes the tool to fail; DocLint also only detects certain categories of issues.

**Fix:** Use `-Xdoclint:all -Werror`, inspect the generated HTML, and review API documentation as part of code review.

## 12. Pre-Merge Checklist

- [ ] Doc comment is placed immediately before the declaration it describes.
- [ ] The first sentence is a concise and accurate summary.
- [ ] Every parameter has a corresponding `@param`.
- [ ] Generic type parameters use the `@param <T>` syntax.
- [ ] Non-`void` methods have `@return`.
- [ ] Important exceptions have `@throws` with clear trigger conditions.
- [ ] Links use accurate references, especially for overloaded methods.
- [ ] Deprecated APIs have `@Deprecated` and replacement guidance.
- [ ] `@since` accurately reflects the API version.
- [ ] HTML and inline tags have valid syntax.
- [ ] Markdown `///` is only used when the toolchain supports JDK 23+.
- [ ] Snippets are tested separately when containing important examples.
- [ ] `javadoc` runs cleanly with DocLint.
- [ ] Generated HTML documentation is reviewed alongside source changes.

## 13. Official References

- [JavaDoc Guide, Java SE 26](https://docs.oracle.com/en/java/javase/26/javadoc/index.html) — guide to using Javadoc, snippets, and Markdown documentation comments.
- [Documentation Comment Specification for the Standard Doclet, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html) — doc comment placement, main descriptions, block tags, inline tags, references, and method documentation rules.
- [The javadoc Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html) — command syntax, standard doclet, options, DocLint, and HTML generation.
- [Programmer's Guide to Snippets](https://docs.oracle.com/en/java/javase/22/javadoc/programmers-guide-snippets.html) — inline, external, and hybrid snippets, markup regions, and managing code examples.
- [JEP 467: Markdown Documentation Comments](https://openjdk.org/jeps/467) — introduces Markdown documentation comments in JDK 23.
- [How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html) — style guide for writing API documentation.

Doc comments turn source code into API documentation that can be generated and verified automatically. Accurately describe the contract of each declaration, use tags in their proper context, and run Javadoc with DocLint in your build pipeline so documentation always stays aligned with code.
