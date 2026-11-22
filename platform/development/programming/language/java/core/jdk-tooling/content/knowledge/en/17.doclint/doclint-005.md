# Enabling DocLint in Javadoc

**DocLint** is a built-in checker in the JDK that detects issues in Java documentation comments before or while generating API documentation with Javadoc. DocLint checks for errors such as missing descriptions, incorrect parameter names, links to non-existent APIs, invalid HTML, unescaped special characters, and certain accessibility issues.

Enabling DocLint helps teams catch documentation errors directly during the build process. This is especially useful for libraries and modules with a public API, where Javadoc is part of the contract that other developers rely on.

In JDK 24, Javadoc enables DocLint by default for comments within the scope of the generated documentation. It can be enabled explicitly with **-Xdoclint**, or you can request all check groups with **-Xdoclint:all**. When you want the build to fail if any warnings remain, combine it with **-Werror**.

## 1. What is DocLint?

DocLint is a documentation comment checker integrated into the **javadoc** tool and can also be invoked from **javac**. It analyzes special comments starting with /** and reports issues that could make the generated documentation incorrect, incomplete, or hard to access.

DocLint focuses on the content quality and markup of Javadoc. It does not fix comments, does not automatically generate missing descriptions, and does not replace a full HTML conformance validator.

Common types of issues detected:

- Missing documentation comments on declarations that should be documented publicly.
- Missing tags such as @param or @return.
- A name after @param that does not match the actual parameter.
- A reference in @see or {@link ...} that cannot be found.
- Improperly nested HTML, missing closing tags, or invalid structure.
- Incorrectly used <, >, or & characters in comments.
- Images missing an alt attribute or tables missing descriptions for accessibility.
- Invalid Javadoc tags or incorrect tag syntax.

### What does DocLint check?

When running Javadoc, DocLint checks documentation comments that fall within the scope of the documentation Javadoc is generating. Therefore, options that determine which elements are included in the documentation also affect the checking scope.

For example, Javadoc displays public and protected APIs by default. If -private is used, private members are also included in the documentation and their corresponding comments can be checked.

Common options for selecting declaration scope:

| Javadoc Option | Scope |
|---|---|
| -public | Only public types and members |
| -protected | Public and protected types and members; this is the default |
| -package | Includes package-private along with public/protected |
| -private | Includes all members, including private |

DocLint does not necessarily check every comment in a repository. It checks comments belonging to elements included in the processing scope, along with special cases that the standard doclet needs to document, such as Serialized Form.

## 2. Enabling DocLint from the Command Line

DocLint can be enabled when generating HTML documentation with the javadoc command.

### Enabling the default checking mode

~~~bash
javadoc -Xdoclint -d docs src/com/example/TextService.java
~~~

The -Xdoclint option enables the recommended checks. In JDK 24, this is also Javadoc's default behavior unless disabled by another option. Writing the option explicitly in build scripts helps readers recognize the checking goal.

### Enabling all check groups

~~~bash
javadoc -Xdoclint:all -d docs src/com/example/TextService.java
~~~

-Xdoclint:all requests enabling all check groups:

- accessibility
- html
- missing
- reference
- syntax

This is an explicit configuration for thoroughly checking comments before releasing API documentation.

### Turning warnings into build errors

~~~bash
javadoc -Xdoclint:all -Werror -d docs src/com/example/TextService.java
~~~

-Werror tells Javadoc to report an error if any warning occurs. When used in CI, the command returns a failure status if there are still warnings to address.

It is important to distinguish:

- **-Xdoclint:all** enables the check groups.
- **-Werror** changes how warnings are handled by turning them into errors.
- -Werror can apply to warnings from other parts of Javadoc, not just DocLint.

You should start by fixing real errors first, and then enable -Werror to keep documentation quality consistent.

### Disabling DocLint

~~~bash
javadoc -Xdoclint:none -d docs src/com/example/TextService.java
~~~

-Xdoclint:none disables all DocLint check groups. Use this only when there is a specific reason, such as needing to temporarily generate documentation from legacy sources that cannot be fixed immediately. You should not disable checks as a way to hide warnings in a release pipeline.

## 3. The Five DocLint Check Groups

DocLint divides checks into five groups. You can enable individual groups to focus on addressing one kind of issue.

### accessibility — accessibility support

This group detects certain issues that can make documentation difficult to use with assistive technologies.

Examples:

- An img tag without an alt attribute.
- A table missing a caption or appropriate description.
- HTML content that does not provide the necessary information for readers using screen readers.

Example of a problematic comment:

~~~java
/**
 * Architecture diagram:
 * <img src="architecture.png">
 */
public class Architecture {
}
~~~

An alternative description should be provided:

~~~java
/**
 * Architecture diagram:
 * <img src="architecture.png" alt="Diagram of modules and dependencies">
 */
public class Architecture {
}
~~~

The alt text should describe the meaning of the image in context. If an image is purely decorative, consider an appropriate presentation so assistive technologies do not read unnecessary content.

### html — HTML structure

The html group detects common HTML errors in documentation comments, for example:

- Placing a block element inside an inline element inappropriately.
- Missing a closing tag for an element that requires one.
- Nesting elements against the rules.
- Using invalid markup that causes browsers to render differently from expected.

Example of a missing closing tag:

~~~java
/**
 * <b>Important: read the guide before calling the API.
 */
public void execute() {
}
~~~

Fix it to:

~~~java
/**
 * <b>Important:</b> read the guide before calling the API.
 */
public void execute() {
}
~~~

DocLint only checks common errors and structures that it supports. It is not a validator for the entire HTML Living Standard.

### missing — missing comments or tags

The missing group finds missing documentation parts, for example:

- A class or method that needs documentation but has no documentation comment.
- A method with parameters that is missing @param.
- A method with a return value that is missing @return.
- Certain documentable elements that have not been described.

Example:

~~~java
/**
 * Finds a user by ID.
 *
 * @param id the user ID
 */
public User findUser(String id) {
    return null;
}
~~~

The method has a return value but is missing @return. Add it:

~~~java
/**
 * Finds a user by ID.
 *
 * @param id the user ID
 * @return the matching user, or null if not found
 */
public User findUser(String id) {
    return null;
}
~~~

Issues in the missing group are usually reported as warnings because they normally do not make the generated HTML syntactically invalid, yet they still leave the API documentation incomplete.

### reference — invalid references

The reference group checks names and links to Java elements.

Examples:

- {@link ...} pointing to a class or method that does not exist.
- @see using an incorrect class name.
- A parameter name after @param not matching the declaration.
- An invalid exception type after @throws.

Example:

~~~java
/**
 * Normalizes a string.
 *
 * @param text the input string
 * @return the normalized string
 * @see String#stripWhitespace()
 */
public String normalize(String input) {
    return input.strip();
}
~~~

Here, the parameter name in the comment is text, whereas the actual name is input; the reference String#stripWhitespace() also does not exist.

Fix it to:

~~~java
/**
 * Normalizes a string.
 *
 * @param input the input string
 * @return the normalized string
 * @see String#strip()
 */
public String normalize(String input) {
    return input.strip();
}
~~~

Invalid references are generally considered serious errors because they can produce broken links or mislead readers about the API.

### syntax — documentation comment syntax

The syntax group detects invalid low-level tag or markup syntax, such as:

- Using an invalid Javadoc tag.
- Writing < or > as HTML text without escaping.
- Using the & character improperly.
- Incorrect inline tag syntax.

Example:

~~~java
/**
 * Returns true if value < limit.
 */
public boolean isBelow(int value, int limit) {
    return value < limit;
}
~~~

In HTML, the < character can be interpreted as starting a tag. You should use {@code} or {@literal}:

~~~java
/**
 * Returns true if {@code value < limit}.
 */
public boolean isBelow(int value, int limit) {
    return value < limit;
}
~~~

If you need to write HTML directly, you can use entities such as &lt;, &gt;, and &amp;.

### Group Summary Table

| Group | Checks | Example |
|---|---|---|
| accessibility | Markup supporting accessibility | img missing alt |
| html | HTML structure | Missing closing tag, invalid nesting |
| missing | Missing comments/tags | Missing @param or @return |
| reference | API names and links | Invalid {@link}, wrong @param name |
| syntax | Javadoc/HTML syntax | Unescaped < character, invalid tag |

## 4. Enabling Individual Groups or Excluding Groups

You can specify groups in the -Xdoclint option.

Enable the html, syntax, and accessibility groups:

~~~bash
javadoc -Xdoclint:html,syntax,accessibility -d docs src/com/example/TextService.java
~~~

You can write multiple separate options:

~~~bash
javadoc -Xdoclint:html -Xdoclint:syntax -Xdoclint:accessibility -d docs src/com/example/TextService.java
~~~

Enable all groups but exclude the missing group:

~~~bash
javadoc -Xdoclint:all,-missing -d docs src/com/example/TextService.java
~~~

This configuration still checks HTML, reference, syntax, and accessibility; it only suppresses reporting issues in the missing group. This can be a transitional step for a legacy codebase, but you should plan to add the missing documentation rather than keeping the exclusion permanently.

Common usage patterns:

| Configuration | Meaning |
|---|---|
| -Xdoclint | Enable recommended checks |
| -Xdoclint:all | Enable all groups |
| -Xdoclint:none | Disable all DocLint checks |
| -Xdoclint:html,syntax | Specify the HTML and syntax groups |
| -Xdoclint:all,-missing | All except missing |

When you need exact control over the set of groups, specify them in an explicit configuration and verify the results using the exact JDK version of your project.

## 5. Limiting Checks by Package

Javadoc provides the -Xdoclint/package: option to restrict or exclude packages to be checked.

Check the com.example package and its subpackages:

~~~bash
javadoc -Xdoclint:all "-Xdoclint/package:com.example.*" -d docs src/com/example/TextService.java
~~~

Check a specific package:

~~~bash
javadoc -Xdoclint:all -Xdoclint/package:com.example.api -d docs src/com/example/TextService.java
~~~

You can prepend a minus sign to a package specifier to exclude that package from the checking scope:

~~~bash
javadoc -Xdoclint:all "-Xdoclint/package:-com.example.legacy" -d docs src/com/example/TextService.java
~~~

A package specifier can be a full package name or a prefix name ending with .* to expand to subpackages.

This is a scope-control tool, not a substitute for fixing errors. If you exclude a legacy package, document the reason and avoid leaving that package permanently unchecked.

## 6. Intentionally Suppressing a Warning

You can use the @SuppressWarnings annotation to suppress DocLint messages on a declaration or an enclosing scope.

Suppress only the missing group:

~~~java
@SuppressWarnings("doclint:missing")
public void legacyExtensionPoint() {
}
~~~

Suppress multiple groups:

~~~java
@SuppressWarnings({
    "doclint:missing",
    "doclint:reference"
})
public void compatibilityHook() {
}
~~~

Suppress all DocLint messages on a declaration:

~~~java
@SuppressWarnings("doclint")
public void generatedBridge() {
}
~~~

Use the narrowest scope possible. If a public API is missing documentation, prefer writing proper comments instead of suppressing warnings. If a comment is auto-generated or cannot be fixed immediately, explain why in code review or internal documentation so the team understands why the suppression exists.

An annotation on a declaration can affect messages on that declaration and enclosed declarations according to DocLint rules. An annotation on a module or package declaration affects only that declaration itself; it does not automatically suppress comments in all source files belonging to the package.

## 7. Complete Example: Generating Javadoc with DocLint

Create the source tree:

~~~text
doclint-demo/
└── src/
    └── com/
        └── example/
            └── TextService.java
~~~

Contents of src/com/example/TextService.java:

~~~java
package com.example;

/**
 * Provides text normalization operations.
 *
 * <p>Methods of this class process input strings according to consistent
 * rules so applications can store and compare data.
 *
 * @since 17
 */
public class TextService {

    /**
     * Creates a text processing service.
     */
    public TextService() {
    }

    /**
     * Removes leading and trailing whitespace from a string.
     *
     * <p>If the string is empty after processing, the result is an empty string.
     *
     * @param input the string to normalize
     * @return the string with leading and trailing whitespace removed
     * @throws IllegalArgumentException if input is null
     * @see String#strip()
     */
    public String normalize(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        return input.strip();
    }

    /**
     * Checks whether a value is less than a limit.
     *
     * @param value the value to check
     * @param limit the comparison limit
     * @return true if value is less than limit
     */
    public boolean isBelow(int value, int limit) {
        return value < limit;
    }
}
~~~

From the doclint-demo directory, run Javadoc using JDK 17 or later:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -encoding UTF-8 -d docs src/com/example/TextService.java
~~~

Explanation:

- --release 17 sets the Java source and API compatibility level.
- -Xdoclint:all enables all five check groups.
- -Werror turns warnings into errors so CI rejects substandard documentation.
- -encoding UTF-8 ensures comments containing Unicode characters are read properly.
- -d docs places the HTML output into the docs directory.
- The path at the end of the command is the source file to document.

If there are no errors or warnings, Javadoc generates documentation in docs. You can open docs/index.html and docs/com/example/TextService.html to inspect the content.

The example above includes comments for the class, constructor, and public methods; parameter names match the source; the String#strip() reference exists; and the HTML uses valid paragraphs. This is a suitable configuration as a starting point for a small API.

## 8. Error Example and Reading DocLint Output

Suppose you have a method:

~~~java
/**
 * Validates a string.
 *
 * @param text the string to validate
 * @return true if valid
 * @see String#isBlankValue()
 */
public boolean isValid(String input) {
    return input != null && !input.isBlank();
}
~~~

There are at least two issues:

1. @param specifies text, but the actual declaration uses input.
2. String#isBlankValue() is not a valid method on String.

When running Javadoc, DocLint points out the source location, the problematic line, and the message type. The exact diagnostic wording may vary by JDK version, but the fix is:

~~~java
/**
 * Validates a string.
 *
 * @param input the string to validate
 * @return true if valid
 * @see String#isBlank()
 */
public boolean isValid(String input) {
    return input != null && !input.isBlank();
}
~~~

When reading the output, pay attention to:

- The file name and line number to locate the source comment.
- The group name or error type in the diagnostic.
- The printed source line with a caret indicating the position.
- Whether it is a warning or an error.
- The exit code of the Javadoc process in CI.

Do not only look at the final line “1 error” or “warnings found”. Fix the root cause in the comment, re-run the same command, and confirm clean output.

## 9. DocLint and javac

DocLint can be invoked from Javadoc or from the Java compiler.

**Javadoc** generates HTML and checks comments within the scope of the generated documentation. This is the primary step when publishing API documentation.

**javac** also has an -Xdoclint option to check documentation comments during compilation. When invoked from javac, the scope of checked comments depends on the -Xdoclint options passed to the compiler; it does not match the exact scope of elements included in HTML by the standard doclet.

A pipeline can use:

~~~bash
javac -Xdoclint:all -d out src/com/example/TextService.java
javadoc -Xdoclint:all -Werror -d docs src/com/example/TextService.java
~~~

The javac command helps catch issues during compilation. The javadoc command checks and generates HTML documentation. If a project only has a single Javadoc generation step, checking can be performed directly in the javadoc command.

## 10. Integrating DocLint into CI

For DocLint to provide lasting value, include the Javadoc command in the build pipeline rather than running it manually only before a release.

A simple workflow:

1. Compile the source with the target JDK and release.
2. Run Javadoc with -Xdoclint:all.
3. Enable -Werror once the codebase has resolved existing warnings.
4. Save the HTML output as an artifact or publish it according to your documentation workflow.
5. Inspect a few generated HTML pages to ensure content and links render properly.

Example build command:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -encoding UTF-8 -d build/docs src/main/java/com/example/*.java
~~~

If the project uses Maven or Gradle, configure the Javadoc task/plugin to pass equivalent options into the documentation generation step. Use the same JDK vendor/version in local development and CI to avoid differences in tags, diagnostics, or the doclet.

### Strategy for Legacy Codebases

When enabling DocLint for the first time on a long-lived project, many pre-existing warnings may appear. You should:

- Enable -Xdoclint:all to see all issue groups.
- Categorize warnings by package and impact.
- Fix invalid references, invalid HTML, and syntax errors first.
- Add descriptions for widely used public APIs.
- If a phased transition is needed, temporarily use -Xdoclint:all,-missing while keeping the remaining groups enabled.
- Once warnings are resolved, enable -Werror to prevent new errors from appearing.

Do not disable DocLint entirely just because the initial warning count is large. You can limit package scope during the transition, but set a goal to bring those packages back under checking.

## 11. Limitations to Understand

DocLint is a useful checking layer, but it does not guarantee perfect documentation.

- It does not write missing descriptions for you.
- It does not automatically fix invalid HTML or tags.
- It is not a full HTML validator.
- It does not verify that every explanation in a comment matches runtime behavior.
- It does not guarantee that code examples in comments compile or run correctly.
- It does not replace reviewing the generated HTML pages.
- It cannot verify whether the API documentation is clear enough for users.

For example, a comment with a syntactically valid @return that describes the wrong return value can still pass DocLint. Similarly, a code snippet may render nicely yet fail to compile if not tested separately.

Therefore, combine DocLint with content reviews, code example tests, and HTML output inspection.

## 12. Common Errors When Enabling DocLint

### Unknown option or unknown flag

You may be using the wrong syntax or an older JDK. Check with:

~~~bash
javadoc --version
javadoc --help
javadoc --help-extra
~~~

Use the exact options supported by the JDK version in use.

### Javadoc reports warnings even though the source compiles successfully

Compiling Java and generating Javadoc are two different steps. The compiler may not check all links or markup that the standard doclet processes. Run the proper Javadoc command in CI to catch documentation errors.

### -Werror causes the build to fail

-Werror turns warnings into errors. Read each diagnostic and fix the comment or configure an appropriate scope. Do not remove -Werror just to make the build green if the warning reflects a real documentation issue.

### Warnings appear in legacy packages

You can use a package filter or temporarily exclude the missing group during the transition. Keep the syntax, html, reference, and accessibility groups enabled to continue catching important errors.

### @SuppressWarnings does not suppress the warning

Check that the annotation string has the exact form doclint or doclint:group; the annotation must be placed on the relevant declaration or an enclosing declaration according to the rules. An annotation on a package or module does not automatically apply to all other source files.

### DocLint does not catch content errors

DocLint checks syntax and certain structures; it does not evaluate business meaning. You need to review the documentation, verify API signatures, test snippets, and read the HTML output.

## 13. Checklist for Enabling DocLint

- Check the JDK version with javadoc --version.
- Determine the API scope to document: public, protected, package, or private.
- Enable all groups with -Xdoclint:all.
- Understand the five groups: accessibility, html, missing, reference, and syntax.
- Fix reference errors, parameter names, and HTML before releasing.
- Use {@code} or {@literal} for <, >, and expressions that should be displayed literally.
- Add alt attributes for images and appropriate captions/descriptions for tables.
- Use package filters or narrow suppressions only when there is a clear reason.
- Enable -Werror in CI after resolving existing warnings.
- Keep the same JDK version in local environments and CI.
- Inspect the generated HTML; DocLint is not a full HTML validator.
- Review content accuracy and test code snippets separately.

## 14. Key Terms to Remember

| Term | Meaning |
|---|---|
| DocLint | Built-in checker for issues in documentation comments |
| -Xdoclint | Enables recommended DocLint checks |
| -Xdoclint:all | Enables all check groups |
| -Xdoclint:none | Disables all DocLint checks |
| -Werror | Turns warnings into errors |
| accessibility | Checks for certain accessibility support issues |
| html | Checks common HTML structure |
| missing | Checks for missing comments and tags |
| reference | Checks Java element links and names |
| syntax | Checks Javadoc and markup syntax |
| -Xdoclint/package | Restricts checking by package |
| @SuppressWarnings | Suppresses DocLint messages within a declaration scope |
| Standard doclet | Javadoc's default HTML generator |

Enabling DocLint brings Javadoc quality into a repeatable build process. For libraries or modules with public APIs, enable all check groups, fix warnings and errors at the source, and use -Werror in CI to prevent new documentation from degrading in quality.

## References

- Oracle JDK 24 — [The javadoc Command: DocLint](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- Oracle JDK 24 — [JavaDoc Guide: DocLint](https://docs.oracle.com/en/java/javase/24/javadoc/javadoc-guide.pdf)
- OpenJDK — [javac documentation and -Xdoclint options](https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/man/javac.md)