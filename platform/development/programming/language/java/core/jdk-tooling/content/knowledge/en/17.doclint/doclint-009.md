# Invalid Javadoc Documentation and How to Fix It

## 1. What Is Invalid Javadoc Documentation?

Javadoc generates HTML documentation from documentation comments in Java source code. A comment may look fine as plain text and still be invalid due to malformed HTML structure, misused block tags, references to nonexistent types or members, or missing information required by documentation check rules.

Common issues include:

- HTML tags that are opened but not closed, improperly structured, or using invalid attributes.
- Using `@param`, `@return`, or `@throws` on the wrong kind of declaration.
- Specifying a parameter name that does not exist or omitting a parameter description.
- `{@link ...}` or `@see` pointing to an unresolvable class, method, or package.
- Inline tags missing braces or using invalid syntax.
- Images missing alternative text, or HTML tables missing a caption.
- Public APIs missing documentation comments or required tags.
- Using custom tags that have not been registered with the Javadoc tool.

Some issues cause Javadoc to fail with an error; others are reported as warnings. When a project requires clean documentation, warnings should also be resolved before release.

## 2. Distinguishing Java Errors from Javadoc Errors

`javac` checks Java source code to produce bytecode. Javadoc reads declarations and documentation comments to generate HTML documentation. The two tasks are related, but they check different things.

| Error Type | Example | Detecting Tool |
|---|---|---|
| Java syntax error | Missing `;`, mismatched data type | `javac` and the compiler used by Javadoc |
| Comment structure error | Invalid inline link syntax | Javadoc / DocLint |
| HTML error | Unclosed `b` tag | Javadoc / DocLint |
| Reference error | `@see MissingType` does not exist | Javadoc / DocLint |
| Missing documentation | Public method has no comment | DocLint `missing` group |
| Accessibility error | `img` missing `alt`, `table` missing `caption` | DocLint `accessibility` group |

A project can compile successfully with `javac` and still produce Javadoc errors. Conversely, valid comments cannot compensate for Java source code that fails to compile.

Javadoc may still generate partial HTML when it encounters errors, but it can insert diagnostic markers and return a non-zero exit code. Do not publish documentation generated from a failed run.

## 3. What Does DocLint Check?

**DocLint** is the documentation comment checker built into the Javadoc tool. It detects common errors before documentation is delivered to readers.

Check groups:

| Group | What It Checks | Example |
|---|---|---|
| `html` | HTML structure and usage in comments | Unclosed tags, invalid HTML structure |
| `accessibility` | HTML accessibility | Images missing `alt`, tables missing `caption` |
| `missing` | Missing documentation or required tags | Public class or method with no comment |
| `reference` | References to Java elements | `@see` or `{@link}` not found |
| `syntax` | Documentation tag syntax and usage | Tag in the wrong place, malformed inline tag |

These groups can be enabled or disabled individually. `-Xdoclint` enables the recommended checks; `-Xdoclint:all` enables all groups, including `missing`.

In many modern JDK configurations, DocLint checks are enabled by default, but the `missing` group is not. If you want to enforce that public APIs have complete comments and tags, explicitly enable `-Xdoclint:all`.

`-Xdoclint` is an extended option of Javadoc. Its syntax and details can vary across JDK releases, so check `javadoc --help-extra` on your exact build version.

## 4. HTML Errors in Documentation Comments

Javadoc treats description text as HTML content. Mismatched opening and closing tags can cause DocLint to report an error.

Invalid example:

~~~java
/**
 * Returns a value <b>without closing the element.
 */
public int value() {
    return 10;
}
~~~

DocLint may report:

~~~text
error: element not closed: b
~~~

Fix by closing the tag:

~~~java
/**
 * Returns a <b>valid</b> value.
 */
public int value() {
    return 10;
}
~~~

Or use the `{@code ...}` inline tag when you only want to display variable names, types, expressions, or Java statements:

~~~java
/**
 * Pass a positive value to {@code calculate(int)}.
 */
~~~

Other common HTML errors:

- Nesting tags in an invalid order.
- Placing a block tag in the middle of an open HTML element.
- Using attributes not supported by the HTML version used by Javadoc.
- Using `<` or `>` in plain text without escaping.
- Writing an HTML `table` or `list` with incomplete structure.

If you want to display HTML characters as literal text, use `{@literal ...}`, `{@code ...}`, or the appropriate HTML entity. For example:

~~~java
/**
 * The expression {@code a < b} is true when a is smaller than b.
 * The literal text {@literal <T>} represents a type parameter.
 */
~~~

Avoid raw HTML when an inline tag expresses the meaning more clearly.

## 5. Accessibility Errors in HTML

API documentation also needs to be readable with screen readers and assistive technologies. DocLint's `accessibility` group detects several common HTML issues.

### Images Missing `alt`

Invalid:

~~~html
<img src="architecture.png">
~~~

DocLint may report:

~~~text
error: no "alt" attribute for image
~~~

Fix by adding alternative text that describes the content:

~~~html
<img src="architecture.png" alt="Application module diagram">
~~~

If an image is purely decorative and conveys no information, use an empty `alt` value when appropriate for accessibility:

~~~html
<img src="separator.png" alt="">
~~~

### Tables Missing `caption`

A table may be visually readable but lack contextual description:

~~~html
<table>
  <tr><th>Key</th><th>Value</th></tr>
  <tr><td>A</td><td>B</td></tr>
</table>
~~~

DocLint may report:

~~~text
error: no caption for table
~~~

Fix by adding a `caption`:

~~~html
<table>
  <caption>Sample configuration values</caption>
  <tr><th scope="col">Key</th><th scope="col">Value</th></tr>
  <tr><td>A</td><td>B</td></tr>
</table>
~~~

Use headings, lists, and tables when they help readers understand the structure. Do not insert HTML purely for decoration.

## 6. Misusing Block Tags

Block tags must match the kind of declaration being documented.

| Tag | Appropriate Usage |
|---|---|
| `@param` | Method/constructor parameter or type parameter |
| `@return` | Method that returns a value |
| `@throws` / `@exception` | Exception that a method or constructor may throw |
| `@see` | Reference to a related element or documentation |
| `@since` | Version in which the API was introduced |
| `@deprecated` | Deprecated API and its replacement |

Invalid example: placing `@return` in a class comment:

~~~java
/**
 * Represents a calculator.
 * @return the result
 */
public class Calculator {
}
~~~

DocLint reports an error similar to:

~~~text
error: invalid use of @return
~~~

`@return` is only for methods with a return value. A class does not have a return value, so the tag makes no sense there.

Valid example:

~~~java
/**
 * Multiplies a value by two.
 *
 * @param value the value to multiply
 * @return the doubled value
 */
public int twice(int value) {
    return value * 2;
}
~~~

### `@param` Must Match the Parameter Name

Invalid:

~~~java
/**
 * Adds two values.
 * @param first first value
 * @param second second value
 */
public int add(int left, int right) {
    return left + right;
}
~~~

The names in `@param` must match the declared names `left` and `right`. Fix:

~~~java
/**
 * Adds two values.
 *
 * @param left the first value
 * @param right the second value
 * @return the sum
 */
public int add(int left, int right) {
    return left + right;
}
~~~

For generic types, the type parameter name must be enclosed in angle brackets:

~~~java
/**
 * Holds a value.
 *
 * @param <T> the value type
 */
public class Box<T> {
}
~~~

### Do Not Use `@return` on `void` Methods or Constructors

`void` methods and constructors do not return a value to the caller. Describe their behavior in the main description, and use `@param` for parameters and `@throws` when needed.

## 7. Reference Errors in `@see` and `{@link}`

Javadoc can create links to classes, packages, methods, constructors, or fields. If the referenced name does not exist, has a wrong overload, or cannot be resolved in the current context, DocLint may report `reference not found`.

Invalid example:

~~~java
/**
 * Uses a helper.
 * @see MissingType
 */
public class Client {
}
~~~

Fix by referencing an existing type:

~~~java
/**
 * Uses a calculator.
 * @see Calculator
 */
public class Client {
}
~~~

You can link to a method in the same class:

~~~java
/**
 * Returns twice the input.
 *
 * @see #add(int, int)
 */
public int twice(int value) {
    return value * 2;
}
~~~

Inline link:

~~~java
/**
 * Use {@link #twice(int)} to double a value.
 */
~~~

Guidelines:

- Use the exact class and package names.
- For overloaded methods, write the full parameter type list when needed to disambiguate.
- Use `#member` for members in the same class.
- Use a fully qualified name such as `java.util.List` when a short name is ambiguous.
- Ensure the dependency or module containing the referenced element is in Javadoc's resolution environment.
- Check `@see` and `{@link}` after renaming APIs.

Do not write a link to an approximate name hoping the browser will find it. Javadoc links must point to an element that the tool can resolve.

## 8. Inline Tag and Custom Tag Syntax Errors

Inline tags appear inside the description text and have the form `{@tag ...}`. They must have matching braces and valid syntax.

Example:

~~~java
/**
 * Returns the value of {@code count}.
 * See {@link #size()} for the current size.
 * The literal token is {@literal <END>}.
 */
~~~

Common mistakes:

- Missing the closing `}` of an inline tag.
- Misspelling the tag name.
- Placing a tag that is only valid in the block section inside a sentence.
- Using `{@link}` without a reference.
- Confusing `@code` with `{@code ...}`.

Invalid example:

~~~java
/**
 * Calls {@link #size().
 */
~~~

Fix:

~~~java
/**
 * Calls {@link #size()}.
 */
~~~

### Custom Tags

If a project has custom tags such as `@implNote` or internal tags, Javadoc must know how to handle them. You can register a simple tag with `-tag` or provide a `Taglet` using `-taglet` and `-tagletpath`.

Example of a custom tag without complex content:

~~~bash
javadoc -tag note:a:Note -d docs src/demo/*.java
~~~

The `-tag` syntax specifies the tag name, allowed locations, and display header. Check `javadoc --help` and the `Taglet` documentation for your exact JDK version before adding custom tags to the build.

## 9. Missing Documentation Comments and Required Tags

The `missing` group checks for elements that should be documented but have no comment, as well as certain required tags that are missing.

Example:

~~~java
package demo;

public class MissingDocs {
    public void run(String input) {
    }
}
~~~

When `missing` checks are enabled, Javadoc may warn:

~~~text
warning: no comment
warning: use of default constructor, which does not provide a comment
warning: no comment
~~~

The fix is to write comments for published APIs, add an explicit constructor with a comment if a default constructor would otherwise appear in the documentation, and add tags matching the method contract.

Example:

~~~java
package demo;

/**
 * Runs a named operation.
 */
public class Operation {
    /** Creates an operation. */
    public Operation() {}

    /**
     * Runs the operation for the given input.
     *
     * @param input the input name
     */
    public void run(String input) {
    }
}
~~~

It is not necessary to document every private implementation detail in API Javadoc. Choose the appropriate visibility level: by default Javadoc focuses on `public` and `protected` members; `-private` extends documentation to `private` members as well.

## 10. Enabling and Configuring DocLint

### Enable All Check Groups

~~~bash
javadoc -Xdoclint:all -d docs src/demo/*.java
~~~

`all` includes `accessibility`, `html`, `missing`, `reference`, and `syntax`.

### Exclude Only `missing` Checks

~~~bash
javadoc -Xdoclint:all,-missing -d docs src/demo/*.java
~~~

This still checks HTML, accessibility, references, and syntax without requiring every API to have a comment.

### Disable DocLint

~~~bash
javadoc -Xdoclint:none -d docs src/demo/*.java
~~~

This disables DocLint checks. It does not guarantee that all standard doclet warnings disappear; other checks or warnings may still appear. Use it only when there is a specific reason and you understand which checks are being skipped.

### Check Only a Single Group

~~~bash
javadoc -Xdoclint:reference -d docs src/demo/*.java
javadoc -Xdoclint:accessibility -d docs src/demo/*.java
~~~

### Restrict Checks by Package

~~~bash
javadoc -Xdoclint/package:demo.* -d docs src/demo/*.java
~~~

The package filter syntax lets you specify a package or package prefix; prefix a package with `-` to exclude it from the specified check group.

### Turn Warnings into Build Errors

~~~bash
javadoc -Xdoclint:all -Werror -d docs src/demo/*.java
~~~

`-Werror` causes Javadoc to fail if any warnings remain. This is useful in CI to prevent broken or incomplete documentation from being released.

You can increase the number of printed diagnostics with `-Xmaxerrs` and `-Xmaxwarns` when a project has many issues.

## 11. Complete Java 17 Example: From Valid Comments to HTML

Structure:

~~~text
project/
  src/
    demo/
      Calculator.java
      Main.java
  classes/
  docs/
~~~

File `src/demo/Calculator.java`:

~~~java
package demo;

/**
 * Provides small integer calculations.
 * <p>The examples use ordinary signed {@code int} values.</p>
 */
public final class Calculator {
    /** Creates a calculator. */
    public Calculator() {}

    /**
     * Returns twice the supplied value.
     *
     * @param value the value to double
     * @return the value multiplied by two
     */
    public int twice(int value) {
        return value * 2;
    }

    /**
     * Adds two values.
     *
     * @param left the first value
     * @param right the second value
     * @return the sum of the values
     * @see #twice(int)
     */
    public int add(int left, int right) {
        return left + right;
    }
}
~~~

File `src/demo/Main.java`:

~~~java
package demo;

/** Runs a small calculation example. */
public final class Main {
    /** Creates the entry point. */
    public Main() {}

    /**
     * Starts the example.
     *
     * @param args command-line arguments (not used)
     */
    public static void main(String[] args) {
        Calculator calculator = new Calculator();
        System.out.println("twice=" + calculator.twice(6));
        System.out.println("sum=" + calculator.add(4, 5));
    }
}
~~~

Compile the source code:

~~~bash
javac --release 17 -encoding UTF-8 -d classes \
    src/demo/Calculator.java src/demo/Main.java
~~~

Run the program:

~~~bash
java -cp classes demo.Main
~~~

Exact stdout:

~~~text
twice=12
sum=9
~~~

Generate Javadoc with all checks and warnings-as-errors:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror \
    -encoding UTF-8 -d docs \
    src/demo/Calculator.java src/demo/Main.java
~~~

If the command succeeds, `docs/demo/` contains `Calculator.html` and `Main.html`, along with the package and index pages.

This example validates both the Java source and the documentation. If you delete the constructor comment, change `@param value` to `@param input`, or change `@see #twice(int)` to a nonexistent member, the Javadoc step will report a warning or error depending on the enabled check groups.

## 12. Workflow for Fixing Invalid Documentation

When Javadoc reports an issue, follow these steps in order:

1. Read the full message, file name, line number, and `^` caret position.
2. Identify the error group: HTML, accessibility, missing, reference, or syntax.
3. Open the exact documentation comment indicated.
4. Check the declaration the comment describes: class, constructor, method, or field.
5. Compare `@param`, `@return`, and `@throws` against the actual Java signature.
6. Verify every `@see`, `{@link}`, and overload.
7. Fix HTML, inline tag, and accessibility issues.
8. Re-run Javadoc with the appropriate check groups.
9. Use `-Werror` before release so no warnings are missed.

Diagnostic example:

~~~text
Calculator.java:12: error: reference not found
 * @see MissingType
        ^
~~~

Check whether `MissingType` actually exists, is imported, or resides in a module or package that Javadoc can resolve. If the intent was to link to `Calculator`, fix the reference to `@see Calculator`.

Do not simply delete tags to make the build green. Fix the comment so it accurately describes the API contract.

## 13. Integrating Javadoc Checks into CI

A basic pipeline can compile first and then generate documentation with DocLint:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes \
    src/demo/Calculator.java src/demo/Main.java

javadoc --release 17 -Xdoclint:all -Werror \
    -encoding UTF-8 -d build/docs \
    src/demo/Calculator.java src/demo/Main.java
~~~

If the project has multiple packages, use a source path or package list matching the actual source layout. Make sure Javadoc can see the dependencies, modules, and sources needed to resolve links.

Guidelines:

- Use the same JDK version locally and in CI.
- Keep `-encoding UTF-8` when source files contain Vietnamese or other Unicode characters.
- Enable `-Xdoclint:all` when you want to check for missing documentation as well.
- Enable `-Werror` when warnings must block releases.
- Disable a check group only when the reason is documented and an alternative check is in place.
- Verify both internal and external links if the build uses `-link` or `-linkoffline`.
- Save the generated HTML as a build artifact for reviewer inspection.

## 14. Common Issues and How to Handle Them

### Javadoc Still Generates HTML Despite Errors

Javadoc may continue generating some files to report multiple errors in a single run. The generated HTML can contain diagnostic markers and is not valid for release. Rely on the reported errors and exit code—do not assume success just because HTML files were written.

### `-Xdoclint:none` Still Produces Warnings

This option disables DocLint, but the standard doclet or other validation steps can still emit warnings. Read the warning text to identify its source; do not treat `none` as a mode that guarantees zero warnings.

### `-Xdoclint:all` Fails the Build Due to Missing Comments

The `missing` group checks for undocumented elements. If a project does not yet have full documentation coverage, you can use `-Xdoclint:all,-missing` during a transition period, then add comments and re-enable `all`.

### Reference Works in the IDE but Javadoc Cannot Find It

The IDE may use a different classpath or module path than the build command. Ensure the `javadoc` command receives the proper `--class-path`, `--module-path`, `--source-path`, and dependencies.

### HTML Looks Valid but DocLint Still Reports an Error

HTML may render in a browser while still violating accessibility requirements. Check `alt` on images, `caption` on tables, and heading/table structure.

### Custom Tag Is Not Recognized

Register the custom tag with `-tag`, or implement a `Taglet` and pass `-tagletpath`/`-taglet`. Check the allowed tag locations and how the tag's content is processed.

## 15. Pre-Release Javadoc Checklist

- [ ] Every class, constructor, and published API has an appropriate documentation comment.
- [ ] HTML tags are properly opened/closed and use valid structure.
- [ ] Images have descriptive `alt` text.
- [ ] Tables have clear `caption` and heading elements.
- [ ] `@param` matches parameter or type parameter names.
- [ ] `@return` is only used on methods that return a value.
- [ ] `@throws` documents appropriate exceptions.
- [ ] `@see` and `{@link}` resolve cleanly.
- [ ] Inline tags have matching braces and valid syntax.
- [ ] Custom tags are registered.
- [ ] DocLint has been run with the required check groups.
- [ ] CI uses `-Werror` if warnings must block releases.
- [ ] Generated HTML output has been inspected before distribution.
