# The javadoc Command in Java

**`javadoc`** is a command-line tool included with the JDK that reads documentation in Java source code and generates API documentation in HTML format. The tool parses *documentation comments* (doc comments), type names, methods, fields, packages, and modules, then generates linked pages for developers to browse.

Javadoc helps library authors describe API usage, parameters, return values, exceptions, versions, and compatibility notes. Library consumers can read the documentation without opening the implementation source code.

## 1. What is Javadoc used for?

When building a library or an application with a shared API, class and method names alone are often not enough for others to understand how to use it. Javadoc helps answer questions such as:

- What problem does this class or interface solve?
- What parameters does the method take, and what does each parameter mean?
- What value does the method return?
- Under what conditions can an exception be thrown?
- Since which version has the API been available?
- Is the API deprecated, or is there an alternative?
- Are there rules, limitations, or notes regarding thread safety, performance, or data ownership?

Example of a method declaration:

```java
public int divide(int dividend, int divisor)
        throws ArithmeticException
```

Javadoc can explain the meaning of `dividend`, `divisor`, the return value, and the condition that throws `ArithmeticException`.

Javadoc is commonly used to:

- Generate documentation for libraries and SDKs.
- Publish internal APIs or customer-facing APIs.
- Create reference documentation for Java projects.
- Validate comment quality and links to types/methods.
- Keep documentation consistent with source code as the API evolves.

## 2. Checking and invoking the javadoc command

`javadoc` is a JDK tool. Open a terminal and verify:

```bash
java -version
javac -version
javadoc --version
```

If the system does not recognize `javadoc`:

- Check that a full JDK is installed on the machine.
- Check that the JDK's `bin` directory is in `PATH`.
- Check that `JAVA_HOME` points to the JDK root directory.
- Open a new terminal after changing environment variables.

View the options help:

```bash
javadoc --help
```

Javadoc does not replace `javac`. This tool generates documentation from source code and resolvable metadata; it does not produce `.class` bytecode files like the compiler does.

## 3. What is a documentation comment?

Javadoc recognizes documentation comments by syntax starting with three slashes/asterisks (`/**`):

```java
/**
 * Description of a class, method, or field.
 */
```

A doc comment is usually placed immediately before the declaration it describes.

Example:

```java
/**
 * Calculates the sum of two integers.
 *
 * @param left the first integer
 * @param right the second integer
 * @return the sum of the two numbers
 */
public static int add(int left, int right) {
    return left + right;
}
```

Distinguish between comment types:

| Comment type | Syntax | Processed by Javadoc |
| --- | --- | --- |
| Documentation comment | `/** ... */` | Used to generate documentation |
| Regular block comment | `/* ... */` | Not used as a doc comment |
| Line comment | `// ...` | Not used as a doc comment |

Javadoc attaches a doc comment to the immediately following declaration, such as a class, interface, constructor, method, field, package, or module. Placing the comment in the right position ensures the documentation is attached to the correct API element.

## 4. Structure of a documentation comment

A doc comment typically consists of three parts:

1. **Main description:** briefly explains the purpose of the element.
2. **Detailed description:** explains how it works, limitations, examples, or notes.
3. **Block tags:** structured information such as parameters, return value, exceptions, and version.

Example:

```java
/**
 * Divides an integer dividend by a divisor.
 *
 * <p>Division follows Java's integer division rules,
 * so the fractional part is truncated.</p>
 *
 * @param dividend the integer dividend
 * @param divisor the integer divisor
 * @return the quotient after integer division
 * @throws ArithmeticException if divisor is 0
 * @since 1.0
 */
public static int divide(int dividend, int divisor) {
    return dividend / divisor;
}
```

Javadoc supports HTML content inside doc comments. Use appropriate tags such as `<p>`, `<ul>`, `<li>`, `<pre>`, and `<code>`; ensure the HTML is valid and tags are properly closed.

For characters that have special meaning in HTML, use entities or inline tags. For example, write `{@code List<String>}` to display generic code without it being misinterpreted as an HTML tag.

## 5. Commonly used block tags

Block tags start with the `@` character and are usually placed at the end of a doc comment.

| Tag | Meaning | Applies to |
| --- | --- | --- |
| `@param` | Describes a parameter | Method, constructor, type parameter |
| `@return` | Describes the return value | Method with a return value |
| `@throws` | Describes an exception that may be thrown | Method, constructor |
| `@exception` | Equivalent to `@throws` | Method, constructor |
| `@see` | References related documentation or elements | Various declarations |
| `@since` | Version in which the API appeared | Class, method, field, package |
| `@deprecated` | Marks an API as no longer recommended | Class, method, field, constructor |
| `@author` | Author | Class, interface, package |
| `@version` | Version information | Class, interface |
| `@serial` | Documents a field for serialization | Serializable class/field |
| `@serialField` | Documents a field in a serializable class | Field |
| `@serialData` | Describes data written by serialization methods | Related method |
| `@implSpec` | Describes requirements on the implementation | API with an implementation contract |
| `@implNote` | Notes about implementation details | API with implementation notes |
| `@apiNote` | Additional notes for API users | API |

Example using `@param`, `@return`, and `@throws`:

```java
/**
 * Finds the position of a character in a string.
 *
 * @param text the string to search
 * @param target the character to find
 * @return the first index, or -1 if not found
 * @throws NullPointerException if text is null
 */
public static int find(String text, char target) {
    return text.indexOf(target);
}
```

For generic methods, you can document a type parameter using the `@param <T>` syntax:

```java
/**
 * Returns the first element in the list.
 *
 * @param <T> the element type
 * @param values the input list
 * @return the first element
 */
public static <T> T first(java.util.List<T> values) {
    return values.get(0);
}
```

The type parameter name must be enclosed in angle brackets in the tag, for example `@param <T>`. For methods with multiple parameters, each parameter needs a corresponding description.

## 6. Commonly used inline tags

Inline tags appear directly within a description sentence and have the form `{@tag ...}`.

| Inline tag | Purpose |
| --- | --- |
| `{@code ...}` | Displays content as source code |
| `{@literal ...}` | Displays text verbatim without processing it as HTML |
| `{@link ...}` | Creates a link to a class, method, or API element |
| `{@linkplain ...}` | Creates a link with a plain-text display label |
| `{@value ...}` | Displays the value of an applicable constant |
| `{@inheritDoc}` | Inherits documentation content from a parent declaration |
| `{@docRoot}` | Relative path to the documentation root directory |
| `{@index ...}` | Adds a term to the search index |

Example:

```java
/**
 * Returns the maximum number of elements to process.
 *
 * <p>Use {@code MAX_SIZE} to limit input data.
 * See also {@link #validate(int)} before processing.</p>
 *
 * @return the element limit
 */
public static int maxSize() {
    return MAX_SIZE;
}
```

`{@link #validate(int)}` creates a link to a method in the same class. You can link to an element in another class using its fully qualified name or a relative name within Javadoc's resolution scope.

Example using `{@literal}`:

```java
/**
 * The expression has the form {@literal x < y}.
 */
```

If you write `<` directly in HTML without escaping, the documentation generator may misinterpret it as the start of an HTML tag.

## 7. Writing documentation for classes, methods, and constructors

### Class documentation

A class doc comment should describe the purpose, role, how to instantiate, and how to use the class. If there are constraints regarding thread safety, mutable state, or resources, state them clearly.

```java
/**
 * Provides basic integer arithmetic operations.
 *
 * <p>This class contains only static utility methods.</p>
 *
 * @since 1.0
 */
public final class Calculator {
    // ...
}
```

### Method documentation

A method should document its behavior, parameters, return value, and significant exceptions.

```java
/**
 * Adds two integers.
 *
 * @param left the first operand
 * @param right the second operand
 * @return the sum of the two operands
 */
public static int add(int left, int right) {
    return left + right;
}
```

Do not add `@return` for `void` methods. Do not add `@param` if the method takes no parameters. Exception descriptions should reflect the actual conditions under which the API can throw them.

### Constructor documentation

A constructor should describe the initial state of the object and the meaning of its parameters.

```java
/**
 * Creates a counter starting from the specified value.
 *
 * @param initialValue the initial value
 */
public Counter(int initialValue) {
    this.value = initialValue;
}
```

### Field documentation

Public or protected fields should be documented if API users need to understand the meaning, unit, or bounds of the value.

```java
/**
 * Maximum number of retry attempts.
 */
public static final int MAX_RETRIES = 3;
```

## 8. Package and module documentation

You can place package-level documentation in a **`package-info.java`** file.

Example:

```java
/**
 * Provides arithmetic utilities for the application.
 *
 * <p>Classes in this package support basic integer
 * operations.</p>
 */
package com.example.math;
```

Javadoc uses this comment to generate the package description page, typically `package-summary.html`.

For modular applications, you can write a doc comment before the module declaration in `module-info.java`:

```java
/**
 * Provides computation APIs for other modules.
 */
module com.example.math {
    exports com.example.math;
}
```

Module documentation describes the module's purpose and dependencies. When generating Javadoc for modules, use the appropriate module path or module source path options.

## 9. Complete example: generating documentation for an API

The following example creates the `com.example.math` package with the `Calculator` class, along with a `Main` class to test the program.

Directory structure:

```text
project/
  src/
    com/
      example/
        math/
          package-info.java
          Calculator.java
        app/
          package-info.java
          Main.java
  docs/
  out/
```

Create **`src/com/example/math/package-info.java`**:

```java
/**
 * Provides arithmetic utilities for the application.
 *
 * <p>This package demonstrates how to write API documentation with Javadoc.</p>
 */
package com.example.math;
```

Create **`src/com/example/math/Calculator.java`**:

```java
package com.example.math;

/**
 * Provides basic integer arithmetic operations.
 *
 * <p>Operations follow Java's integer arithmetic rules.</p>
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
     * @see #divide(int, int)
     * @since 1.0
     */
    public static int add(int left, int right) {
        return left + right;
    }

    /**
     * Divides an integer dividend by a divisor.
     *
     * <p>The result follows Java's integer division,
     * with the fractional part truncated toward zero.</p>
     *
     * @param dividend the integer dividend
     * @param divisor the integer divisor
     * @return the quotient after integer division
     * @throws ArithmeticException if divisor is 0
     * @since 1.0
     */
    public static int divide(int dividend, int divisor) {
        return dividend / divisor;
    }
}
```

Create **`src/com/example/app/package-info.java`**:

```java
/**
 * Contains a sample program demonstrating how to use the arithmetic API.
 */
package com.example.app;
```

Create **`src/com/example/app/Main.java`**:

```java
package com.example.app;

import com.example.math.Calculator;

/**
 * Runs an example using {@link Calculator}.
 */
public final class Main {

    private Main() {
    }

    /**
     * Entry point of the program.
     *
     * @param args command-line arguments
     */
    public static void main(String[] args) {
        System.out.println("sum=" + Calculator.add(7, 5));
        System.out.println("quotient=" + Calculator.divide(17, 5));
    }
}
```

### Step 1: Create output directories

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force docs, out | Out-Null
```

**macOS/Linux:**

```bash
mkdir -p docs out
```

### Step 2: Generate HTML documentation with javadoc

Run from the `project` root directory:

```bash
javadoc -d docs -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -sourcepath src -subpackages com.example
```

Explanation:

- `-d docs`: writes HTML documentation to the `docs` directory.
- `-encoding UTF-8`: reads source code and doc comments using UTF-8.
- `-docencoding UTF-8`: uses UTF-8 for generated HTML files.
- `-charset UTF-8`: declares the charset in the HTML documentation.
- `-sourcepath src`: specifies the root directory of the source code.
- `-subpackages com.example`: generates documentation for the `com.example` package and its subpackages.

Javadoc parses the packages found under `com.example`, including `com.example.math` and `com.example.app`.

### Step 3: Inspect the generated documentation

The output structure looks like:

```text
docs/
  index.html
  allclasses-index.html
  allpackages-index.html
  com/
    example/
      math/
        package-summary.html
        Calculator.html
      app/
        package-summary.html
        Main.html
```

Names and some index files may vary depending on the JDK version and the standard doclet. The key pages to check are the class, package, and index pages.

Open `docs/index.html` in a browser. Select the `com.example.math` package, open the `Calculator` class, and verify the class, method, parameter, return value, and exception descriptions.

### Step 4: Compile and run the program

Javadoc only generates documentation. To test the program, compile separately with `javac`:

```bash
javac -d out -sourcepath src src/com/example/app/Main.java
```

Run:

```bash
java -cp out com.example.app.Main
```

Exact output:

```text
sum=12
quotient=3
```

The example uses integer division: `17 / 5` yields `3` because the fractional part is truncated toward zero.

## 10. Important javadoc options

| Option | Purpose |
| --- | --- |
| `-d <directory>` | Directory to store generated documentation |
| `-sourcepath <path>` | Where to find Java source files |
| `-subpackages <packages>` | Generates documentation for packages and subpackages |
| `-classpath` / `--class-path` | Where to find classes or libraries needed for resolution |
| `-private` | Includes private members |
| `-package` | Includes package-private and wider access levels |
| `-protected` | Only public and protected; this is the default |
| `-public` | Only public |
| `-author` | Includes `@author` content in the documentation |
| `-version` | Includes `@version` content in the documentation |
| `-encoding` | Encoding of input source files |
| `-docencoding` | Encoding of output HTML files |
| `-charset` | Charset declared in HTML |
| `-overview <file>` | HTML file describing the documentation overview |
| `-link <url>` | Links to external API documentation |
| `-tag` | Declares a custom block tag |
| `-Xdoclint` | Checks doc comment syntax, HTML, and references |
| `-Werror` | Exits with an error status if warnings occur |
| `-quiet` | Reduces messages during documentation generation |
| `-notimestamp` | Omits the timestamp from the top of generated pages |

The default visibility level is public and protected. Use `-private` when generating internal documentation that includes private members; avoid using it for public API documentation if you do not want to expose implementation details.

Example generating documentation including private members and author/version information:

```bash
javadoc -d docs-internal -private -author -version -sourcepath src -subpackages com.example
```

## 11. Checking documentation quality with doclint

Javadoc can inspect doc comments to detect issues such as:

- Malformed HTML or unclosed tags.
- References to nonexistent classes, methods, or fields.
- Invalid tags or tags used in the wrong place.
- Missing or incorrect parameter and return value descriptions in checked cases.
- Incorrect doc comment syntax.

Usage:

```bash
javadoc -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example
```

Meaning:

- `-Xdoclint:all` enables checks for all supported doclint groups.
- `-Werror` causes documentation generation to fail if any warning is reported.
- `-d docs` specifies the output directory.

You can specify particular check groups with `-Xdoclint:<group>`. Common groups include:

| Group | Checks |
| --- | --- |
| `accessibility` | Certain accessibility requirements in HTML content |
| `html` | HTML syntax and structure |
| `reference` | References to members and types |
| `syntax` | Javadoc syntax and tags |
| `missing` | Missing documentation within the checked scope |

Example disabling the `missing` check while keeping all other groups enabled:

```bash
javadoc -Xdoclint:all,-missing -d docs -sourcepath src -subpackages com.example
```

Do not disable doclint completely just to silence warnings. Read the diagnostics, fix the doc comments, or choose intentional exclusions when the project has a clear reason.

## 12. Linking to external API documentation

When your project's documentation references standard Java APIs, you can use the `-link` option to generate links to published JDK documentation.

Example with Java SE 17:

```bash
javadoc -d docs -sourcepath src -subpackages com.example -link https://docs.oracle.com/en/java/javase/17/docs/api/
```

References such as `{@link java.util.List}` or `{@link java.time.LocalDate}` can then link to the corresponding API pages when Javadoc resolves the type and the target documentation is accessible.

To link to third-party library documentation, use the root URL of that library's API docs. The target documentation version must match the dependency version supported by your project.

If the build environment has no network access, you can use offline linking with `-linkoffline` and a downloaded copy of the API documentation. See `javadoc --help` for the syntax and the package list/element list structure required by your JDK version.

## 13. Generating documentation for modular applications

For Java modules, Javadoc can read a module source path and generate documentation for the specified modules.

Example structure:

```text
src/
  com.example.math/
    module-info.java
    com/example/math/
      package-info.java
      Calculator.java
```

`module-info.java`:

```java
/**
 * Provides the arithmetic API.
 */
module com.example.math {
    exports com.example.math;
}
```

Generate documentation:

```bash
javadoc --module-source-path src -d docs --module com.example.math
```

Where:

- `--module-source-path src`: location of the module source directory tree.
- `--module com.example.math`: the module to document.
- `-d docs`: the output directory.

With multiple modules, you can specify a list of modules using the syntax supported by the JDK. Module descriptors, exported packages, and dependencies must be valid so Javadoc can resolve references.

For public module documentation, verify the exported packages and the APIs accessible to module consumers. Internal documentation may require different visibility levels and appropriate configuration.

## 14. Documenting deprecated APIs

When an API is no longer recommended, mark it with the `@Deprecated` annotation and document it with the `@deprecated` tag.

Example:

```java
/**
 * Returns the name in the legacy format.
 *
 * @deprecated Use {@link #displayName()} instead.
 */
@Deprecated(since = "2.0", forRemoval = false)
public String oldName() {
    return displayName();
}
```

The two parts serve different roles:

- `@Deprecated` is a source-code annotation that lets the compiler and tools recognize that the API is deprecated.
- `@deprecated` is a block tag that provides an explanation in the Javadoc documentation.

When deprecating an API, state the reason, the version since it was deprecated, and the replacement option. Avoid removing the API immediately if the library needs to maintain backward compatibility.

## 15. Customizing documentation titles and content

You can add an overview page using `-overview`:

```bash
javadoc -d docs -overview overview.html -sourcepath src -subpackages com.example
```

The overview file usually contains HTML introducing the library, its goals, installation instructions, or general examples.

Other presentation options:

- `-doctitle`: main title of the documentation.
- `-windowtitle`: browser window or tab title.
- `-header`: header content.
- `-footer`: footer content.
- `-bottom`: content at the bottom of the page.
- `-use`: generates pages showing where types are used.
- `-splitindex`: splits the index into multiple pages when needed.

Example:

```bash
javadoc -d docs -doctitle "Calculator API" -windowtitle "Calculator API Reference" -sourcepath src -subpackages com.example
```

These options affect the generated HTML documentation. For large projects, keep title and overview configurations in the build script so every documentation build produces a consistent format.

## 16. Generating documentation in Maven and Gradle

In real-world projects, you should not have to remember and run a long Javadoc command manually on every release. Build tools can integrate documentation generation into the build pipeline.

### Maven

Maven projects can use the Maven Javadoc Plugin. Example plugin configuration in `pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.11.2</version>
        </plugin>
    </plugins>
</build>
```

Generate documentation:

```bash
mvn javadoc:javadoc
```

Package Javadoc as a JAR for distribution with the library:

```bash
mvn javadoc:jar
```

The plugin can be further configured with encoding, doclint, source level, links, and other Javadoc options. The plugin version in the example is a specific version; projects should choose a tested and centrally managed version.

### Gradle

With Gradle using the Groovy DSL, the Java plugin provides the `javadoc` task. You can configure it as:

```groovy
tasks.named('javadoc', Javadoc) {
    options.encoding = 'UTF-8'
    options.docEncoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.addStringOption('Xdoclint:all', '-quiet')
}
```

Run:

```bash
./gradlew javadoc
```

On Windows:

```powershell
.\gradlew.bat javadoc
```

Documentation is typically generated in the module's build directory, such as `build/docs/javadoc`. The exact path depends on the project configuration.

In multi-module builds, ensure each module has a Javadoc task and the corresponding source dependencies. To fail the build on warnings, configure the `-Werror` option according to the API of your Gradle version.

## 17. Common errors when running javadoc

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `javadoc` is not recognized | JDK not installed or `PATH` missing the `bin` directory | Check `JAVA_HOME` and `PATH` |
| Package or class not found | Wrong source path, classpath, or package name | Check directory structure and `-sourcepath`, `-classpath` options |
| Package page has no description | Missing or misplaced `package-info.java` | Add a doc comment before the package declaration |
| `{@link}` link is unresolved | Wrong class/member name or missing dependency | Check the fully qualified name, method signature, and classpath/module path |
| Doclint reports HTML errors | Malformed or unclosed HTML tags | Fix the HTML in the doc comment |
| Javadoc reports missing param description | Missing `@param` tag or parameter name mismatch | Match each tag against the method declaration |
| Private members are missing | Default visibility is public/protected | Use `-private` for internal documentation |
| Author/version not shown | Corresponding options not enabled | Use `-author` or `-version` |
| Garbled non-ASCII characters in docs | Inconsistent input or output encoding | Use `-encoding UTF-8`, `-docencoding UTF-8`, `-charset UTF-8` |
| Javadoc build fails due to warnings | Warnings present while `-Werror` is enabled | Fix the warnings or adjust policy intentionally |

## 18. Best practices for writing Javadoc

- Describe the API's purpose before listing implementation details.
- Document observable behavior; do not promise guarantees that the implementation does not uphold.
- Use `@param`, `@return`, and `@throws` accurately to match the method signature and behavior.
- Use `{@link}` to connect related APIs.
- Clearly state units, value ranges, boundary conditions, and side effects when they matter.
- Document thread safety, mutability, and resource ownership where relevant to the API.
- Use `package-info.java` to describe package purposes.
- Use `module-info.java` to describe modules when using JPMS.
- Use UTF-8 consistently for source code and output documentation.
- Run doclint in CI to catch broken comments before release.
- Generate documentation from the exact source version being released.
- Never include secrets, personal information, or internal details that should not be made public in distributed Javadoc.

Public Javadoc is part of the API usage contract. When method behavior changes, update the comments and examples alongside the source code.

## 19. Recommended documentation workflow

A repeatable workflow:

1. Write doc comments for public/protected APIs.
2. Add package descriptions in `package-info.java` and module descriptions in `module-info.java` if needed.
3. Verify that block tags and inline tags match the declarations.
4. Run Javadoc with `-sourcepath`, `-subpackages`, or the appropriate module options.
5. Enable `-Xdoclint:all` to validate comments and HTML.
6. Use `-Werror` in CI if policy requires zero warnings.
7. Inspect the generated class, method, package pages, and external links.
8. Run `javac` and tests separately to confirm the source code still compiles and works.
9. Store or package the documentation alongside the released artifact version.

## 20. Summary

- `javadoc` is a JDK tool that generates HTML API documentation from doc comments in Java source code.
- Documentation comments use the `/** ... */` syntax.
- Common block tags include `@param`, `@return`, `@throws`, `@see`, `@since`, and `@deprecated`.
- Common inline tags include `{@code}`, `{@literal}`, `{@link}`, `{@linkplain}`, and `{@inheritDoc}`.
- Use `package-info.java` and `module-info.java` to document packages and modules.
- Use `-d`, `-sourcepath`, and `-subpackages` to specify the output and sources to document.
- Use `-private` when internal documentation needs to include private members.
- Use `-Xdoclint:all` and `-Werror` to enforce comment quality.
- Javadoc generates documentation; `javac` compiles source code into bytecode.

When you master `javadoc`, you can produce consistent API documentation directly from your source code, helping users understand how to call classes and methods while catching inaccurate comments or broken references early.
