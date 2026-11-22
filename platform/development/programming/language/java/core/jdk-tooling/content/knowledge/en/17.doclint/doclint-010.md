# Testing Documentation with Doclint

**Doclint** is the documentation comment quality checker built into the `javadoc` tool. It analyzes Javadoc syntax, tags, API reference links, and HTML embedded in comments, and can also detect certain accessibility issues and missing documentation.

Doclint helps catch documentation errors right at the build step. When combined with `-Werror`, a development team can require the Javadoc generation step to fail if any warnings remain, thereby bringing documentation quality into CI.

Doclint checks the documentation structure and references that Javadoc can resolve. It does not prove that descriptions are accurate regarding business logic, does not execute Java examples, and does not replace unit tests or browser-based HTML inspection.

## 1. Why Test Documentation?

API documentation is part of the contract that other developers rely on. An incorrect comment can cause users to call a method improperly, misunderstand input preconditions, or overlook important exceptions.

Common documentation errors include:

- Wrong parameter names in `@param`.
- Missing descriptions for return values or exceptions.
- `{@link}` pointing to a non-existent method or class.
- Incorrect block tag or inline tag syntax.
- HTML with missing closing tags, improper tag nesting, or invalid attributes.
- HTML content lacking accessibility support information.
- Public APIs with overly sparse comments or no documentation at all.
- Changing a method signature without updating the corresponding Javadoc.

If you only open a few HTML pages to inspect manually, these reference and tag errors can easily be missed. Doclint automatically checks many of these issues every time the documentation is generated.

## 2. How Does Doclint Work?

When running `javadoc`, the tool reads the source code, locates documentation comments, and parses the tags and HTML inside them. Doclint checks the structure and the references it can resolve.

General workflow:

1. Javadoc selects the source files, packages, or modules.
2. The tool parses class, method, and field declarations along with doc comments.
3. Doclint checks syntax, references, HTML, accessibility, and missing documentation according to the enabled groups.
4. Javadoc displays errors or warnings.
5. If there are no blocking errors, the standard doclet generates the HTML documentation.
6. The `-Werror` option can turn warnings into run failures.

Example:

```bash
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src com.example.api
```

This command requests checks for all Doclint groups and fails if any warnings remain.

## 3. Doclint Check Groups

Javadoc provides the following check groups:

| Group | What It Checks | Example Issues |
| --- | --- | --- |
| `accessibility` | Certain accessibility requirements for HTML content | Images missing alternative text or inaccessible content structure |
| `html` | HTML syntax and structure in doc comments | Invalid tags, improper nesting, or missing closing tags |
| `reference` | References to classes, methods, fields, and API elements | `{@link}` pointing to a non-existent method |
| `syntax` | Documentation comment syntax and tag usage | Misplaced tags, malformed structure, or invalid formatting |
| `missing` | Required documentation or tags according to missing checks | Documented members missing corresponding comments or tags |

You can enable individual groups to investigate:

```bash
javadoc -Xdoclint:html -d build/docs -sourcepath src com.example.api
javadoc -Xdoclint:reference -d build/docs -sourcepath src com.example.api
javadoc -Xdoclint:syntax -d build/docs -sourcepath src com.example.api
javadoc -Xdoclint:accessibility -d build/docs -sourcepath src com.example.api
javadoc -Xdoclint:missing -d build/docs -sourcepath src com.example.api
```

When you want comprehensive checks, use `-Xdoclint:all`. To temporarily disable Doclint only for diagnostic purposes, you can use `-Xdoclint:none`; you should not turn disabling checks into a long-term build policy.

**Version note:** `-Xdoclint` is a non-standard extended option of the standard doclet and may vary across JDK versions. Run `javadoc --help-extra` on the exact JDK used by your project to confirm the supported groups and syntax.

## 4. Enabling All Checks and Adjusting the missing Group

Strict command:

```bash
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src com.example.api
```

`-Xdoclint:all` enables all groups, including `missing`. This is useful when a project wants to require complete documentation for the selected APIs.

Some legacy projects may already have comments but have not yet fully documented every member or tag. You can enable structure, HTML, and reference checks while temporarily excluding the missing group:

```bash
javadoc -Xdoclint:all,-missing -Werror -d build/docs -sourcepath src com.example.api
```

This approach still enforces checks for syntax errors, HTML, and reference links, while avoiding the requirement to complete every comment in a single migration step.

You should plan to fill in the missing documentation and then switch to `-Xdoclint:all` once the project reaches the desired baseline. Excluding the missing group does not disable the other groups.

## 5. Distinguishing error, warning, and -Werror

In Javadoc output:

- **Error:** a failure that prevents documentation generation from succeeding.
- **Warning:** an issue that needs attention but may not fail the command unless a strict policy is enabled.
- **Informational message:** status or notes that are not necessarily quality defects.

The `-Werror` option instructs Javadoc to report an error if any warnings occur:

```bash
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src com.example.api
```

Key distinctions:

- `-Xdoclint:all` determines which documentation check groups are evaluated.
- `-Werror` determines whether warnings fail the build.
- `-Werror` does not enable Doclint on its own or select which groups to check.
- `-Werror` can apply to other warnings emitted by Javadoc, not just warnings from Doclint.

Therefore, CI configurations typically combine both options.

## 6. Complete Example: Generating Documentation with Doclint Checks

Project structure:

```text
project/
  src/
    com/
      example/
        api/
          package-info.java
          Calculator.java
  build/
```

File **`src/com/example/api/package-info.java`**:

```java
/**
 * Provides the integer calculation API for the application.
 *
 * <p>This package demonstrates how to generate API documentation with Doclint checks.</p>
 */
package com.example.api;
```

File **`src/com/example/api/Calculator.java`**:

```java
package com.example.api;

/**
 * Provides basic integer arithmetic operations.
 *
 * <p>Utility methods in this class are stateless.</p>
 *
 * @since 1.0
 */
public final class Calculator {

    private Calculator() {
    }

    /**
     * Adds two integers.
     *
     * @param left the first operand
     * @param right the second operand
     * @return the sum of the two integers
     * @see #subtract(int, int)
     */
    public static int add(int left, int right) {
        return left + right;
    }

    /**
     * Subtracts the second integer from the first.
     *
     * @param left the minuend
     * @param right the subtrahend
     * @return the difference of the two integers
     */
    public static int subtract(int left, int right) {
        return left - right;
    }

    /**
     * Divides the integer dividend by the divisor.
     *
     * @param dividend the integer dividend
     * @param divisor the integer divisor
     * @return the quotient according to Java integer division rules
     * @throws ArithmeticException if divisor is 0
     */
    public static int divide(int dividend, int divisor) {
        return dividend / divisor;
    }
}
```

### Step 1: Create Output Directories

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force build\docs, build\classes | Out-Null
```

**macOS/Linux:**

```bash
mkdir -p build/docs build/classes
```

### Step 2: Run Javadoc with Strict Doclint

From the project root directory:

```bash
javadoc --release 17 -Xdoclint:all -Werror -encoding UTF-8 -d build/docs -sourcepath src com.example.api
```

What the command does:

- Selects the `com.example.api` package from the `src` source path.
- Uses Java 17 platform rules via `--release 17`.
- Checks all Doclint groups.
- Uses UTF-8 to read source files.
- Writes HTML output to `build/docs`.
- Exits with a failure status if any warnings remain.

With the complete example above, Javadoc will generate the documentation successfully if there are no other issues in the build environment.

### Step 3: Inspect the Generated Documentation

Open the file:

```text
build/docs/index.html
```

Verify:

- The `com.example.api` package page.
- The `Calculator` class page.
- Descriptions of the `add`, `subtract`, and `divide` methods.
- The `{@link #subtract(int, int)}` reference.
- The `@param`, `@return`, and `@throws` descriptions.

Doclint verifies many structural and reference issues before the documentation is generated; you still need to read the HTML pages to evaluate whether the content is clear and accurately conveys the API semantics.

### Step 4: Compile Source Code Separately

Javadoc does not replace the compilation step. Check the source code using `javac`:

```bash
javac --release 17 -d build/classes -sourcepath src src/com/example/api/Calculator.java
```

A successful command prints no output if there are no errors or warnings. This step checks the Java code; it does not prove that the descriptions in Javadoc are accurate regarding business logic.

## 7. Testing an Intentional Reference Error

One way to verify your Doclint configuration is to introduce a reproducible documentation error, confirm that the tool detects it, and then fix it.

In `Calculator.java`, temporarily replace:

```java
@see #subtract(int, int)
```

with:

```java
@see #substract(int, int)
```

The name `substract` is misspelled; the actual method is `subtract`.

Run:

```bash
javadoc --release 17 -Xdoclint:reference -Werror -encoding UTF-8 -d build/docs -sourcepath src com.example.api
```

Javadoc will report an unresolved reference, typically with a message similar to `reference not found`. Because `-Werror` is enabled, the warning is promoted to an error and the command exits with a failure status.

Fix it back:

```java
@see #subtract(int, int)
```

Re-run the strict command from Step 2. When the reference is valid and no warnings remain, the documentation is generated successfully.

This is an intentional test example; do not leave typos in production source code.

## 8. Checking HTML and Accessibility

Doclint can check certain HTML and accessibility issues directly inside doc comments.

Example comment containing a list:

```java
/**
 * Supported modes:
 * <ul>
 *   <li>FAST: prioritizes speed.</li>
 *   <li>SAFE: prioritizes input validation.</li>
 * </ul>
 */
```

When writing HTML in Javadoc:

- Close tags that require a closing tag.
- Nest tags according to valid HTML structure.
- Use `{@code ...}` or `{@literal ...}` when displaying characters with special HTML meaning.
- Provide appropriate alternative text for images.
- Use table structures with clear headers when presenting tabular data.
- Do not include scripts or arbitrary HTML content in comments without a valid reason and appropriate policy.

You can run these groups individually:

```bash
javadoc -Xdoclint:html -d build/docs -sourcepath src com.example.api
javadoc -Xdoclint:accessibility -d build/docs -sourcepath src com.example.api
```

Doclint does not replace full accessibility testing with dedicated tools or screen-reader testing. It only detects issues within Javadoc's checking scope.

## 9. Checking Missing Documentation with the missing Group

The `missing` group helps detect APIs that are not fully documented according to Doclint rules.

For example, if a public method has parameters but its doc comment lacks `@param`, or a member requiring documentation has no comment, the missing group can emit a corresponding warning.

Run:

```bash
javadoc -Xdoclint:missing -d build/docs -sourcepath src com.example.api
```

To check all groups while requiring zero warnings:

```bash
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src com.example.api
```

When using `-private`, the scope of members included in the documentation becomes broader. If the project enables missing checks, the number of members requiring comments may also increase. Choose a visibility level that matches your documentation goals:

- Public APIs: typically use public/protected visibility.
- Internal documentation: `-private` can be used when you want to document internal details as well.
- Do not use `-private` merely to suppress warnings if doing so would expose unwanted implementation details in the published documentation.

## 10. Selecting Check Groups Intentionally

You can combine multiple groups or temporarily exclude a group:

```bash
javadoc -Xdoclint:all,-missing -Werror -d build/docs -sourcepath src com.example.api
```

Common usages:

| Goal | Option |
| --- | --- |
| Enable all groups | `-Xdoclint:all` |
| Disable Doclint | `-Xdoclint:none` |
| Check HTML only | `-Xdoclint:html` |
| Check references only | `-Xdoclint:reference` |
| Check syntax only | `-Xdoclint:syntax` |
| Check accessibility only | `-Xdoclint:accessibility` |
| Check missing documentation | `-Xdoclint:missing` |
| Enable all, except missing | `-Xdoclint:all,-missing` |

If a group produces warnings due to legacy content, clearly document the scope and remediation plan. Avoid using `-Xdoclint:none` as a long-term workaround because it disables all Doclint checks.

## 11. Integrating Doclint into CI

A documentation pipeline can run the following steps:

1. Build source code and dependencies.
2. Generate Javadoc with `-Xdoclint:all -Werror`.
3. If Javadoc fails, mark the CI job as failed.
4. If it succeeds, archive the HTML directory as a build artifact.
5. Inspect key pages and critical links before release.

Basic CI command:

```bash
javadoc --release 17 -Xdoclint:all -Werror -encoding UTF-8 -d build/docs -sourcepath src -subpackages com.example
```

Use `-subpackages` when you want to scan an entire package tree. If you only want to publish specific packages, pass explicit package names to avoid exposing internal code in the documentation.

In Maven or Gradle, configure the same compiler/Javadoc arguments in the documentation generation task. Keep plugin and JDK versions consistent between developer machines and CI, and inspect logs to tell whether a warning comes from Javadoc, a plugin, or another step.

## 12. What Does Doclint Not Check?

Doclint is useful, but it has limitations. It does not automatically verify:

- Whether an algorithm description matches the actual behavior.
- Whether Java examples in comments compile and run successfully.
- Whether examples produce the expected results according to business requirements.
- Whether all external URLs are still active.
- Whether the HTML layout renders well across all browsers and screen sizes.
- Whether the documentation is easy to understand, has sufficient context, and suits the target audience.
- Whether an API is actually safe, efficient, or thread-safe as claimed in the comment.

For comprehensive verification, combine:

- Doclint for comment structure, tags, HTML, and references.
- `javac` or a build tool to verify source code compilation.
- Unit tests for API behavior.
- Dedicated tools for HTML/link and accessibility checking.
- Documentation content review during code review.

## 13. Common Errors When Testing Documentation

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Javadoc reports `reference not found` | `{@link}`, `@see`, or method reference has wrong name/signature | Check class name, method name, parameters, and imports |
| HTML warnings | Malformed tag syntax, missing closing tag, or invalid nesting | Fix the HTML structure in the doc comment |
| Accessibility warnings | HTML content missing accessibility support information | Add alt text and appropriate structure |
| Missing warnings | Missing doc comment or checked tag | Add the corresponding description and tag, or define a missing policy |
| Build fails after enabling `-Werror` | Warnings emitted by Javadoc or Doclint | Read the first warning, fix the root cause, and re-run |
| Warnings appear in only some packages | Different source scopes or visibility levels | Check package selection, source path, and visibility |
| Passes locally but fails in CI | Different JDK, encoding, dependencies, or Doclint configuration | Align JDK, plugins, sources, and arguments |
| Doclint misses inaccurate descriptions | Semantic error, outside Doclint's scope | Add tests, review the API, and verify examples |
| Documentation fails to build despite valid comments | Javadoc cannot resolve sources or dependencies | Check `-sourcepath`, classpath, module path, and package selection |

## 14. Recommended Documentation Testing Workflow

A repeatable workflow for each release:

1. Identify the packages or modules that need documentation.
2. Specify sources and dependencies using the appropriate `-sourcepath`, `-classpath`, or module path.
3. Run `javadoc -Xdoclint:all` to check all groups.
4. Enable `-Werror` in CI so warnings fail the build.
5. Fix HTML, syntax, reference, and accessibility errors.
6. Add missing comments and tags if the project requires the missing group.
7. Run `javac` or the build tool to verify source code independently.
8. Run unit tests for the documented behavior.
9. Open the generated HTML pages and inspect content, navigation, and encoding.
10. Store the Javadoc alongside the released artifact version.

When migrating a legacy codebase, you can start with `-Xdoclint:all,-missing`, resolve structural errors first, and then add comments and enable `-Xdoclint:all -Werror`.

## 15. Key Takeaways

- Doclint is the documentation comment checker built into Javadoc.
- The main groups are `accessibility`, `html`, `missing`, `reference`, and `syntax`.
- Use `-Xdoclint:all` to enable all check groups.
- Use `-Xdoclint:none` to disable Doclint; use this only for intentional diagnostics.
- Use `-Xdoclint:all,-missing` when you need structural checks while temporarily deferring full documentation requirements.
- Use `-Werror` to make warnings fail the documentation generation step.
- Doclint checks structure and references; it does not execute examples or verify business logic correctness.
- Combine Doclint, compilation, unit tests, and HTML review to maintain documentation quality.
- Use `javadoc --help-extra` to confirm extended options on the JDK in use.

Integrating Doclint into the build pipeline ensures documentation errors are caught early, before API documentation reaches library consumers or ships with the product.
