# DocLint in CI

## Objectives

After this lesson, you will be able to explain what DocLint checks in documentation comments; enable all check groups; turn Javadoc warnings into build errors; integrate checks into Maven, Gradle, and CI; handle HTML, reference, missing tag, and accessibility errors; manage controlled exceptions; and distinguish API documentation checks from HTML, content, and code example checks.

## 1. What is DocLint?

**DocLint** is a checker built into the JDK to detect common issues in Java documentation comments. It analyzes doc comments, Javadoc tags, links to APIs, and the markup used to generate documentation.

DocLint helps catch errors early, such as:

- Missing doc comments or missing required tags on APIs.
- Parameter names in @param not matching the method declaration.
- @link or @see pointing to a non-existent class or member.
- Using Javadoc tags with invalid syntax.
- Unescaped <, >, or & characters.
- Improperly nested HTML or missing closing tags.
- Images without alternative descriptions or tables lacking accessibility information.

**DocLint in CI** means that every automated build runs API documentation checks. If the documentation has errors or warnings covered by the project's quality policy, the pipeline fails. As a result, documentation bugs are caught in the pull request that introduced them, rather than only surfacing when publishing Javadoc.

DocLint does not modify source code, does not auto-generate missing content, and does not prove that an API description is business-accurate. It checks consistency, syntax, and a set of quality requirements that can be analyzed automatically.

## 2. Which groups does DocLint check?

DocLint divides checks into five groups:

| Group | What it checks | Example |
|---|---|---|
| accessibility | Issues affecting accessibility | img tag missing alt; table missing an appropriate caption or summary |
| html | Common HTML structure | Placing a block element inside an inline element; missing required end tag |
| missing | Missing doc comments or tags | Class without a description; method missing @param or @return |
| reference | References to Java APIs | @link cannot find method; wrong name in @param or @throws |
| syntax | Low-level doc comment syntax | Unescaped <, >, &; invalid Javadoc tag |

Examples of errors by group:

**accessibility**

~~~java
/**
 * <img src="diagram.png">
 */
public class DiagramView {
}
~~~

The image has no alt text describing its content. Users of assistive technologies may not understand what the image represents.

**html**

~~~java
/**
 * <p><div>Invalid nesting for a paragraph.</div></p>
 */
public class HtmlExample {
}
~~~

A block element is placed inside an inappropriate paragraph structure.

**missing**

~~~java
/**
 * Adds two numbers.
 */
public static int add(int left, int right) {
    return left + right;
}
~~~

The method has two parameters, but the documentation does not describe them. When the missing group is enabled, DocLint can warn about missing @param and @return tags.

**reference**

~~~java
/**
 * Uses {@link String#notExisting()}.
 */
public class LinkExample {
}
~~~

The linked method does not exist on the String type.

**syntax**

~~~java
/**
 * Returns a List<String> value.
 */
public class SyntaxExample {
}
~~~

Angle brackets can be interpreted as HTML markup. In doc comments, generic types should be written using {@code List<String>}.

Severity depends on the type of issue. HTML or syntax errors can cause the generated HTML to be invalid; missing descriptions are usually reported as warnings; broken references can produce misleading documentation. In CI, you can use -Werror so that every warning causes the Javadoc command to fail.

## 3. How is DocLint enabled?

### When running javadoc

Javadoc enables recommended DocLint checks by default. You can select specific groups or request all groups.

| Option | Meaning |
|---|---|
| -Xdoclint | Enables the recommended checks |
| -Xdoclint:all | Enables all five groups |
| -Xdoclint:html,syntax | Enables only the two listed groups |
| -Xdoclint:all,-missing | Enables all groups except missing |
| -Xdoclint:none | Disables DocLint |
| -Werror | Turns warnings into Javadoc command errors |

The recommendation for new projects is to explicitly enable all groups and treat warnings as errors:

~~~bash
javadoc -Xdoclint:all -Werror -d build/apidocs src/main/java/com/example/api/*.java
~~~

Writing the options explicitly keeps the CI policy readable and independent of the defaults of a specific JDK version.

The missing group can detect APIs that lack documentation comments or required tags. If a legacy project cannot fix everything immediately, you can temporarily use -Xdoclint:all,-missing during the transition period, then set a goal to re-enable it. Do not disable DocLint entirely just to hide HTML or reference errors.

### When running javac

javac also supports DocLint, though DocLint is disabled by default in the compiler. You can enable it during compilation:

~~~bash
javac --release 17 -Xdoclint:all -Werror -d build/classes src/main/java/com/example/api/CountParser.java
~~~

This command checks documentation comments while compiling the source. It does not generate a Javadoc website.

To verify API documentation and generate HTML, run the javadoc tool. A pipeline can run both compilation and Javadoc to get two layers of checking.

### Scope of checked declarations

Javadoc checks documentation comments for declarations within the scope of the generated documentation. By default, the standard doclet primarily generates documentation for public and protected APIs. The -package or -private options expand the scope.

If a project wants to check package-private or private APIs as well, configure the appropriate visibility level. Keep in mind that enabling -private includes many internal members in the documentation and may produce additional missing warnings.

## 4. Running DocLint directly in the terminal

Create the file src/main/java/com/example/api/CountParser.java:

~~~java
package com.example.api;

/**
 * Parses positive integer values for application configuration.
 *
 * <p>Leading and trailing whitespace is ignored.
 *
 * @since 1.0
 */
public final class CountParser {

    private CountParser() {
    }

    /**
     * Parses a positive integer from the supplied text.
     *
     * @param text text containing a base-10 integer
     * @return the parsed positive integer
     * @throws IllegalArgumentException if text is null, blank, invalid,
     *         or represents a value that is not positive
     */
    public static int parsePositive(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("text must not be blank");
        }

        final int value;
        try {
            value = Integer.parseInt(text.trim());
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(
                    "text must contain an integer", exception);
        }

        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }

        return value;
    }

    /**
     * Runs a small parsing example.
     *
     * @param args command-line arguments; not used
     */
    public static void main(String[] args) {
        System.out.println("count=" + parsePositive(" 42 "));
    }
}
~~~

### Compiling and running the program

Use JDK 17 or later:

~~~bash
javac --release 17 -d build/classes src/main/java/com/example/api/CountParser.java
java -cp build/classes com.example.api.CountParser
~~~

Exact output:

~~~text
count=42
~~~

### Generating Javadoc and enabling all DocLint groups

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -d build/apidocs src/main/java/com/example/api/CountParser.java
~~~

If the command succeeds, the build/apidocs directory contains the HTML API documentation. You can open index.html or com/example/api/CountParser.html in a browser.

Option breakdown:

- --release 17: uses the Java SE 17 API when analyzing source.
- -Xdoclint:all: enables accessibility, html, missing, reference, and syntax.
- -Werror: exits with an error status if any warning is emitted.
- -d build/apidocs: sets the output directory for the documentation.
- Source path: specifies the Java file to document.

### Triggering an intentional error

Rename the parameter in the source to input while keeping the old tag:

~~~java
/**
 * Parses a positive integer.
 *
 * @param text input text
 * @return parsed value
 */
public static int parsePositive(String input) {
    return Integer.parseInt(input);
}
~~~

The @param text tag does not match the input parameter name. The reference group can detect this inconsistency. When running Javadoc with -Werror, the resulting warning causes the command to fail.

Fix the tag to @param input and run it again. CI should only turn green when the source and documentation are in sync.

## 5. Integrating DocLint with Maven

The Maven Javadoc Plugin generates API documentation using the JDK's javadoc tool. In a Maven project, you can configure the plugin in build/plugins to run javadoc:javadoc directly in CI.

Example pom.xml:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>count-parser</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.12.0</version>
                <configuration>
                    <doclint>all</doclint>
                    <failOnError>true</failOnError>
                    <failOnWarnings>true</failOnWarnings>
                    <encoding>UTF-8</encoding>
                    <docencoding>UTF-8</docencoding>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Key configuration settings:

- doclint = all requests all DocLint groups.
- failOnError = true fails the build when Javadoc encounters an error.
- failOnWarnings = true fails the build when Javadoc emits a warning.
- encoding and docencoding keep source and HTML in UTF-8.
- The plugin version is pinned so CI machines use the same configuration.

Maven Javadoc Plugin 3.12.0 does not fail the build on warnings alone by default; therefore, enable failOnWarnings if your policy requires warnings to be resolved.

Run the check:

~~~bash
mvn --batch-mode --no-transfer-progress clean verify javadoc:javadoc
~~~

The javadoc:javadoc goal generates documentation in target/apidocs. If you want to package Javadoc into a separate artifact, you can run:

~~~bash
mvn --batch-mode --no-transfer-progress clean verify javadoc:jar
~~~

In multi-module projects, consider the javadoc:aggregate goal to generate unified documentation. Verify the classpath/module path and inter-module links before using aggregate mode.

### Distinguishing build plugins from reporting plugins

You can declare the Maven Javadoc Plugin in build/plugins or reporting/plugins:

- build/plugins is used for direct goals such as mvn javadoc:javadoc or mvn javadoc:jar.
- reporting/plugins is used when generating a Maven Site with mvn site.

These two locations have different configuration behavior. If the goal is to block pull requests when documentation has errors, configure the goal explicitly invoked in the pipeline so results do not depend on whether someone runs mvn site.

## 6. Integrating DocLint with Gradle

Gradle uses the Javadoc task to generate API documentation. You can configure all Javadoc tasks to check every group and fail the build on warnings or errors.

### Groovy DSL: build.gradle

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(Javadoc).configureEach {
    failOnError = true
    options.addBooleanOption('Xdoclint:all', true)
    options.addBooleanOption('Werror', true)
}
~~~

### Kotlin DSL: build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.javadoc.Javadoc

plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<Javadoc>().configureEach {
    isFailOnError = true
    options.addBooleanOption("Xdoclint:all", true)
    options.addBooleanOption("Werror", true)
}
~~~

The Gradle Javadoc task uses the javadoc tool from the Java toolchain if configured. This keeps the tool version consistent between developer machines and CI.

Run:

~~~bash
./gradlew clean check javadoc
~~~

The check task typically runs tests and other verification tasks; the javadoc task is invoked explicitly to ensure API documentation is also checked in the pipeline.

Do not set failOnError = false in required CI checks. That configuration allows the task to ignore Javadoc errors and defeats the purpose of the quality check.

## 7. GitHub Actions workflow example

For a Maven project, you can create .github/workflows/verify.yml:

~~~yaml
name: Verify Java API documentation

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Run tests and DocLint
        run: mvn --batch-mode --no-transfer-progress clean verify javadoc:javadoc
~~~

Because the Maven Javadoc Plugin is configured with doclint = all and failOnWarnings = true, the CI command will fail if the documentation contains errors or warnings.

A good workflow should:

1. Check out the exact commit of the pull request.
2. Install the JDK version required by the project.
3. Run the build and tests.
4. Run Javadoc with DocLint.
5. Save logs on failure so the author can fix the right file.
6. Allow merging only after the required job succeeds.

If using Gradle, replace the last step with:

~~~bash
./gradlew --no-daemon clean check javadoc
~~~

Use the Gradle Wrapper and Maven Wrapper so CI runs the exact build tool version pinned by the project.

## 8. Reading and handling DocLint output

When DocLint detects an issue, its message typically reports:

- The source file name.
- The line number and error position.
- The group or issue category.
- A snippet of the relevant source line.
- A caret indicator pinpointing the region to fix.

Resolution workflow:

1. Identify the reported file and declaration.
2. Read the doc comment along with the class/method signature.
3. Determine the error group: accessibility, html, missing, reference, or syntax.
4. Fix the source comment or class/member reference.
5. Re-run the javadoc command locally.
6. Inspect the generated HTML page if the change affects markup or links.
7. Commit the source and let CI run again.

### Common errors

| Symptom | Common cause | Fix |
|---|---|---|
| Invalid @param name | Tag name differs from parameter name | Synchronize the name in source and tag |
| Missing @return | Method has a return type but is missing the tag | Document the return value |
| Reference not found | Broken link or missing dependency for resolution | Fix the reference, classpath, or module path |
| Invalid HTML | Improperly nested tags or missing end tag | Fix the HTML markup |
| Unescaped angle bracket | Writing a generic type directly in an HTML comment | Use {@code List<String>} |
| Missing alt | Image has no alternative description | Add a meaningful alt attribute |
| Missing documentation | API is in doc generation scope but lacks a doc comment | Write the API description and required tags |
| Unknown tag | Misspelled tag name or undeclared custom tag | Fix the tag or configure a taglet |
| External link unavailable | CI cannot reach external reference documentation | Use offline links or cache reference docs |

If a reference to an external class is not found, check the Javadoc classpath or module path. For links to external API documentation, configure -link or -linkoffline appropriately. Do not skip reference checks just because CI lacks a stable internet connection.

## 9. Handling legacy projects with many warnings

A long-lived codebase may have hundreds of APIs without doc comments. Enabling -Xdoclint:all -Werror immediately can cause every pull request to fail.

You can roll it out in phases:

### Phase 1: measure the baseline

Run DocLint and save the current list of warnings. Categorize them by package and error group. Do not discard logs or disable DocLint entirely just to make the pipeline green.

### Phase 2: enable critical error groups

Enable html, syntax, reference, and accessibility first if you need to address structural, link, and accessibility issues. Keep the list of missing docs as a backlog with assigned owners.

Example:

~~~bash
javadoc -Xdoclint:html,syntax,reference,accessibility -Werror -d build/apidocs src/main/java/com/example/api/*.java
~~~

### Phase 3: scope by package

You can use the package option to apply checks to new API packages or exclude a legacy package that has a separate remediation plan. Example:

~~~bash
javadoc -Xdoclint/package:com.example.api.*,-com.example.legacy.* -Xdoclint:all -d build/apidocs src/main/java/com/example/api/*.java
~~~

Verify the package selector syntax for the JDK in use. Every exception should have a reason and a target deadline.

### Phase 4: enable missing and warning-as-error

Once the baseline is reduced, enable the full configuration:

~~~bash
javadoc -Xdoclint:all -Werror -d build/apidocs src/main/java/com/example/api/*.java
~~~

Make this a mandatory quality gate. From that point on, new APIs cannot be merged with missing or invalid documentation.

Do not maintain broad exception lists indefinitely. Document the package, excluded groups, reason, owner, and target removal milestone.

## 10. Controlled warning suppression

DocLint understands the SuppressWarnings annotation with values doclint or doclint:<group>. It can be used to suppress a specific warning when there is a practical reason:

~~~java
/**
 * Legacy entry point retained for binary compatibility.
 */
@SuppressWarnings("doclint:missing")
public void legacyOperation() {
}
~~~

Valid group values are accessibility, html, missing, reference, and syntax. Multiple groups can be specified in the same annotation.

Suppression only silences the check message; it does not fix the content or make the documentation more complete. Only use it when:

- The warning cannot be fixed without breaking compatibility or changing APIs out of scope.
- There is a clear technical reason.
- The suppression scope is limited to the required declaration.
- An explanation is provided so reviewers understand why the exception exists.

Do not place @SuppressWarnings("doclint") on a package or large class to hide batches of issues. Avoid suppressing html, syntax, or reference errors that can be fixed directly.

## 11. What checks does DocLint not replace?

DocLint is useful, but it has limits.

| Task | Does DocLint do it? | Complementary tool/process |
|---|---|---|
| Check Javadoc tags | Yes | Javadoc/DocLint |
| Check API references | Yes | Proper classpath/module path |
| Check certain HTML errors | Yes | HTML validator |
| Check basic accessibility | Yes | Accessibility audit |
| Check all HTML Living Standard rules | No | HTML validator |
| Verify description matches code behavior | No | Code review and tests |
| Run examples in doc comments | Not guaranteed | Unit tests or snippet tests |
| Check if external website links are live | No | Link checker |
| Check prose quality and grammar | No | Documentation review |
| Ensure API is thoroughly documented for business logic | No | API design review |

Javadoc may generate HTML successfully while the content is still wrong or lacks examples. Conversely, a valid HTML page does not guarantee it explains how to use the API correctly.

For public libraries, combine DocLint with tests for examples, external link checks, HTML/accessibility checks, and documentation reviews in pull requests.

## 12. Integrating with multi-module builds and generated sources

In multi-module projects:

- Run Javadoc per module to pinpoint which module causes an error.
- Use the aggregate goal when a single unified documentation set is needed.
- Ensure complete module path and dependency resolution so Javadoc can find types.
- Configure inter-module links so modules can link to each other's APIs.
- Do not skip a module just because it has no standalone Javadoc site if it still provides APIs used by public modules.

If an annotation processor or plugin generates Java sources, ensure the generated sources exist before Javadoc runs. When Javadoc runs too early, it may report missing types or references even if the final compile task succeeds.

In Maven, run Javadoc after generate-sources and ensure the plugin has the required source roots. In Gradle, add generated sources to the source set and make the Javadoc task depend on the source-generating task.

For Java modules, Javadoc must be able to read module-info.java and the corresponding module path. Module errors should not be solved by disabling DocLint; fix the module/source path configuration instead.

## 13. Ensuring reproducible builds

To keep DocLint results consistent between local machines and CI:

- Pin the JDK version and vendor used to run Javadoc.
- Pin the Maven/Gradle version using the wrapper.
- Declare UTF-8 source encoding.
- Keep Javadoc options identical between local and CI.
- Do not depend on files on a developer's machine.
- Configure external API links with an offline fallback if needed.
- Save logs and HTML artifacts when checks fail.
- Do not use skip options to bypass quality gates on release branches.

Javadoc in JDK 23 and later supports Markdown documentation comments; older JDKs may not understand that syntax. If the source uses /// Markdown comments, CI must use a compatible JDK. Mismatched toolchain versions can produce warnings or errors that do not appear locally.

## 14. DocLint in CI checklist

- [ ] Choose a JDK/toolchain that matches the source and documentation.
- [ ] Use the Maven Wrapper or Gradle Wrapper.
- [ ] Set source encoding to UTF-8.
- [ ] Run Javadoc on every pull request.
- [ ] Enable -Xdoclint:all to check all five groups.
- [ ] Enable -Werror or failOnWarnings so warnings fail the build.
- [ ] Ensure Javadoc has the correct source sets, dependencies, and module path.
- [ ] Check public/protected APIs or the required documentation scope.
- [ ] Run tests for important code examples.
- [ ] Check HTML and accessibility with complementary tools when needed.
- [ ] Suppress warnings only in narrow scopes with justification.
- [ ] Save logs and HTML artifacts so reviewers can inspect them.
- [ ] Gradually remove legacy exceptions and fully enable the missing group.
- [ ] Do not bypass errors by disabling DocLint entirely.

## 15. Official references

- [The javadoc Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html) — -Xdoclint options, check groups, -Werror, and documentation generation scope.
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — enabling DocLint during compilation and check group syntax.
- [Apache Maven Javadoc Plugin 3.12.0](https://maven.apache.org/plugins/maven-javadoc-plugin/) — configuring doclint, failOnError, failOnWarnings, and Javadoc goals.
- [Maven Javadoc Plugin Usage](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html) — configuring the plugin in build/reporting and running documentation goals.
- [Gradle Javadoc DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.javadoc.Javadoc.html) — Javadoc task, toolchain, options, and failOnError.
- [Gradle CoreJavadocOptions API](https://docs.gradle.org/current/javadoc/org/gradle/external/javadoc/CoreJavadocOptions.html) — configuring options such as Xdoclint and Werror.
- [JavaDoc Guide, Java SE 26](https://docs.oracle.com/en/java/javase/26/javadoc/index.html) — guide to generating API documentation with Javadoc.

DocLint turns documentation comment quality into an automated check in the build. Enable all check groups, fix warnings at the source, and keep the JDK/toolchain consistent so pull requests only pass when API documentation has reliable structure and references.