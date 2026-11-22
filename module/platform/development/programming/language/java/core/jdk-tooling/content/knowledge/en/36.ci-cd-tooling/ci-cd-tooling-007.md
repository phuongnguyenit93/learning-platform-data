# Javadoc in CI: quality checks and API documentation generation

Javadoc in CI turns API documentation into part of build quality. Every pull request can be checked for missing comments, incorrect `@param`/`@return` tags, unresolved links, invalid HTML, or documentation that cannot be generated with the target JDK. When the check fails, CI blocks the merge just like a failed compile task or test task.

Javadoc is the tool that generates HTML from documentation comments in Java source code. DocLint checks for many common mistakes in comments; the `-Werror` option turns warnings into errors. Maven, Gradle, and Ant can all invoke Javadoc during a build. The task must be configured as a real quality gate: it must run as part of a required CI command, return a non-zero exit code on errors, and retain the output for reviewers to inspect.

The commands and configurations below were tested with Zulu/OpenJDK 24.0.2, Maven 3.9.12, Maven Javadoc Plugin 3.12.0, Gradle 9.2.1, and Ant 1.10.15. The source examples are Java 17 compatible.

## 1. What role does Javadoc play in CI?

Javadoc helps library users understand the public API without reading the implementation. CI checks documentation at the exact time the API changes, while the author still has the context to fix it.

A Javadoc gate typically handles four responsibilities:

1. **Generating documentation:** reading source roots, resolving types/references, and generating HTML.
2. **Checking comments:** detecting syntax errors, HTML issues, reference errors, accessibility problems, and missing documentation according to policy.
3. **Checking links:** creating links to external APIs or documentation of dependent modules.
4. **Producing artifacts:** storing HTML for review, or packaging a Javadoc JAR alongside binary and source JARs upon release.

The Javadoc task does not replace compilation, testing, or inspecting the generated HTML output. A pipeline can be organized as follows:

~~~text
Checkout source
      |
      v
Select JDK / restore dependencies
      |
      v
Compile source -------------------+
      |                           |
      v                           v
Unit tests                 Generate Javadoc
      |                           |
      v                           v
Test quality gates         DocLint + -Werror
      |                           |
      +-------------+-------------+
                    |
                    v
               Verify / Check
                    |
          +---------+----------+
          |                    |
          v                    v
   Store HTML artifact    Package / Publish
                          Javadoc JAR
~~~

For internal-only application projects, documentation can be an artifact for the development team to reference. For libraries or SDKs, Javadoc is part of the public API contract and should be strictly checked before release.

## 2. Distinguishing Javadoc comments from regular comments

Javadoc only reads documentation comments in the form `/** ... */` attached to a declaration. Regular `//` and `/* ... */` comments do not become API descriptions.

Example:

~~~java
// This is a normal implementation comment.

/*
 * This is also a normal comment.
 */

/**
 * Calculates a price for the requested quantity.
 */
public final class PriceCalculator {
}
~~~

Javadoc uses the first sentence of a comment as the summary in API tables, indexes, and overview pages. Therefore, the first sentence should clearly describe the behavior, rather than starting with generic phrasing like “This class is a class”.

You can use `{@summary ...}` to explicitly specify the summary sentence when the natural first sentence is not suitable.

Comments should explain:

- Observable behavior for callers.
- Input preconditions and constraints.
- Return values, units of measurement, and how to interpret them.
- Exceptions that may be thrown.
- Side effects, thread safety, lifecycle, or ordering requirements if any.
- Important differences between the current implementation and the API contract.

Do not copy the implementation verbatim into Javadoc. The goal is to describe how to use the API and its guarantees.

## 3. Common tags in documentation comments

Example of a method with complete documentation:

~~~java
/**
 * Calculates the total amount for a quantity and unit price.
 *
 * <p>The result uses the same minor currency unit as {@code unitPrice}.</p>
 *
 * @param quantity number of items; must be non-negative
 * @param unitPrice price of one item in minor currency units
 * @return the total amount in minor currency units
 * @throws IllegalArgumentException if an input is negative
 * @throws ArithmeticException if the result overflows a {@code long}
 * @since 1.0
 */
public long total(int quantity, long unitPrice) {
    // implementation
}
~~~

Main tags:

| Tag | Purpose |
|---|---|
| `@param name` | Describes a method/constructor parameter |
| `@param <T>` | Describes a type parameter |
| `@return` | Describes the result of a value-returning method |
| `@throws` / `@exception` | Describes an exception and the conditions under which it is thrown |
| `@since` | The version in which the API was introduced |
| `@deprecated` | Describes a deprecated API and its replacement |
| `@see` | References a related API or document |
| `@author` | Author, if the project has a policy to display it |
| `@version` | Documentation version, if used by the project |

Useful inline tags:

- `{@code expression}` displays literal code, preventing HTML from interpreting `<`, `>`, or `&`.
- `{@link Type#method}` creates a link to a declaration.
- `{@linkplain Type#method}` creates a link with normal display text.
- `{@literal text}` displays literal text.
- `{@inheritDoc}` inherits the description from a parent class/interface method when appropriate.
- `{@value #CONSTANT}` displays the value of a supported constant.

For generic APIs, document type parameters properly:

~~~java
/**
 * Finds an item by its identifier.
 *
 * @param <T> type of the item
 * @param id identifier to find
 * @return the matching item, or {@code null} if absent
 */
public <T> T find(String id) {
    return null;
}
~~~

Do not add `@return` to a `void` method, do not document non-existent parameters, and do not list `@throws` for an exception that the method contract cannot throw. DocLint can detect several of these discrepancies.

## 4. Documenting classes, constructors, packages, and modules

Javadoc does not apply only to methods. A public class should describe its purpose, scope of use, and important constraints. A public constructor is also a separate declaration; under strict missing-doc checks, an implicitly generated default constructor can trigger a warning.

Example:

~~~java
/**
 * Represents an amount in minor currency units.
 *
 * @since 1.0
 */
public final class Money {
    private final long minorUnits;

    /**
     * Creates a non-negative amount.
     *
     * @param minorUnits amount in the smallest currency unit
     * @throws IllegalArgumentException if the amount is negative
     */
    public Money(long minorUnits) {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("minorUnits must be non-negative");
        }
        this.minorUnits = minorUnits;
    }

    /**
     * Returns the amount in minor currency units.
     *
     * @return the amount in minor currency units
     */
    public long minorUnits() {
        return minorUnits;
    }
}
~~~

Use `package-info.java` to document a package, shared conventions, or package-level annotations:

~~~java
/**
 * Public API for monetary calculations.
 *
 * <p>All amounts in this package use minor currency units.</p>
 *
 * @since 1.0
 */
package com.example.api;
~~~

For named modules, `module-info.java` can contain a documentation comment describing the module, its purpose, and exported APIs. When generating Javadoc for multiple modules, use the appropriate module path/module source path for the JPMS structure.

## 5. DocLint and check groups

DocLint is the built-in checker in Javadoc. On modern JDKs, DocLint is enabled by default for comments included in the generated documentation; it should be configured explicitly in CI so the policy is easy to read and does not rely on assumptions.

Check groups:

| Group | Checks |
|---|---|
| `html` | HTML tags, structure, and attributes |
| `syntax` | Comment syntax, special characters, and invalid tags |
| `reference` | Links and references to declarations |
| `accessibility` | Accessibility issues such as `alt` on images or table captions |
| `missing` | Missing documentation on declarations included in the documentation |

Enable all groups:

~~~text
-Xdoclint:all
~~~

Enable all except missing-comment checks:

~~~text
-Xdoclint:all,-missing
~~~

The transitional `all,-missing` configuration is useful for large codebases gradually adding documentation. You can enable a strict missing-doc gate for new packages or standardized public APIs, then expand coverage after clearing the backlog.

To turn warnings into errors:

~~~text
-Werror
~~~

With `-Werror`, a DocLint warning can cause Javadoc to exit with a non-zero exit code. CI will receive a build failure instead of merely printing a warning and continuing.

### 5.1. How should a strict policy be enabled?

For public libraries or SDKs, use `-Xdoclint:all -Werror` to require complete API documentation. For internal applications with a lot of legacy code, start with `-Xdoclint:all,-missing -Werror`, then establish a roadmap to address missing docs.

Do not disable DocLint entirely just because one group of warnings is hard to handle. If a declaration has a genuine exception, you can use `@SuppressWarnings("doclint")` or a specific group on that declaration, accompanied by a reason in code review. Do not place suppressions at the package/root level to hide errors across the entire API.

DocLint catches common errors in comments, but it does not evaluate the correctness of business explanations, does not check grammar, and does not replace a full HTML conformance validator for all generated HTML.

## 6. Running Javadoc directly in CI via CLI

Project example:

~~~text
src/
  main/
    java/
      com/example/api/
        package-info.java
        Money.java
        PriceCalculator.java
~~~

Strict gate command for Java 17:

~~~text
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -notimestamp -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
~~~

Option meanings:

| Option | Meaning |
|---|---|
| `--release 17` | Uses source/API rules corresponding to Java 17 |
| `-encoding UTF-8` | Encoding of source files |
| `-docencoding UTF-8` | Encoding of HTML output |
| `-charset UTF-8` | Charset declared in HTML |
| `-Xdoclint:all` | Enables all DocLint groups |
| `-Werror` | Fails the build on warnings |
| `-notimestamp` | Omits hidden timestamps in HTML for more stable output |
| `-d build/docs/javadoc` | Output directory |
| `-sourcepath` | Root containing source packages |
| `-subpackages` | Generates documentation for packages and subpackages |

By default, Javadoc generates documentation for public/protected APIs. You can use `-private` if you need to document every declaration, but you should not publish private implementation docs as an API artifact if library consumers do not need them.

Replace `com.example` with the actual root package. `-subpackages` ensures new packages are automatically included in documentation as the source tree grows.

You can pass a classpath when sources reference dependencies:

~~~text
javadoc --release 17 -classpath "build/classes;lib/api.jar" -Xdoclint:all -Werror -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
~~~

The classpath path separator is `;` on Windows and `:` on Linux/macOS. For modules, use `--module-path` and `--module-source-path` according to the project structure.

## 7. Linking to external Javadoc

When comments reference classes in the JDK or other libraries, Javadoc can generate links to external API documentation.

Example linking to Java SE 17:

~~~text
javadoc --release 17 -link https://docs.oracle.com/en/java/javase/17/docs/api/ -Xdoclint:all -Werror -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
~~~

Use a fully qualified name or a valid import in `{@link ...}`. An unresolved link usually indicates an incorrect type/method name, a missing classpath entry, or external API documentation lacking the required package list.

`-link` may require network access to read the target documentation's metadata. This makes the build dependent on the network and external services. For offline CI or builds requiring high stability, download/provide controlled Javadoc metadata and use `-linkoffline <url> <local-doc-directory>`.

Some newer JDKs use `element-list` instead of `package-list`; use the metadata file appropriate for the linked documentation version. Do not link to unstable URLs or unpublished documentation.

## 8. Maven: integrating Javadoc into `verify`

The Maven Javadoc Plugin invokes the Javadoc tool and supports most of its options. Configuring the plugin under `build/plugins` allows invoking the goal directly; to turn it into a CI gate, bind the goal to a lifecycle phase that the pipeline always runs, such as `verify`.

Example configuration in `pom.xml`:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>17</release>
      </configuration>
    </plugin>

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-javadoc-plugin</artifactId>
      <version>3.12.0</version>
      <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
        <docencoding>UTF-8</docencoding>
        <charset>UTF-8</charset>
        <doclint>all</doclint>
        <failOnError>true</failOnError>
        <failOnWarnings>true</failOnWarnings>
        <notimestamp>true</notimestamp>
        <additionalOptions>
          <additionalOption>-Werror</additionalOption>
        </additionalOptions>
      </configuration>
      <executions>
        <execution>
          <id>javadoc-quality-gate</id>
          <phase>verify</phase>
          <goals>
            <goal>javadoc</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Run in CI:

~~~text
./mvnw -B -ntp verify
~~~

- `doclint=all`: requires all DocLint groups.
- `failOnError=true`: fails when the Javadoc command fails.
- `failOnWarnings=true`: the Maven plugin fails the build when Javadoc produces warnings.
- `additionalOptions/-Werror`: turns warnings into errors directly inside the Javadoc tool.
- `notimestamp=true`: omits timestamps in HTML.
- `phase=verify`: ensures `mvn verify` always invokes the Javadoc gate.

The Maven Javadoc Plugin can generate standalone documentation or package a Javadoc JAR. Run:

~~~text
./mvnw -B -ntp javadoc:javadoc
./mvnw -B -ntp javadoc:jar
~~~

The `javadoc:jar` goal creates an artifact with the `javadoc` classifier, for example:

~~~text
target/my-library-1.0-javadoc.jar
~~~

In a release profile, you can bind the `jar` goal so the Javadoc JAR is published alongside binary and source artifacts. Only publish artifacts after the quality gate and other release steps succeed.

### 8.1. Multi-module Maven

In a Maven reactor, each module can generate its own Javadoc. If you want a unified documentation set across multiple modules, use the `aggregate` or `aggregate-jar` goal from the appropriate aggregator/parent.

Ensure module dependencies and sources are resolved before aggregating. If the Javadoc goal is bound to `verify` in every module, consider how aggregation is structured to avoid generating the same documentation multiple times or publishing duplicate artifacts.

## 9. Gradle: binding `javadoc` to `check`

The Gradle Java Plugin creates a `javadoc` task of type `Javadoc` for the main source set. The task supports Javadoc tool options via `StandardJavadocDocletOptions`.

Example `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withJavadocJar()
}

tasks.named('javadoc', Javadoc) {
    options.encoding = 'UTF-8'
    options.docEncoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.addBooleanOption('Xdoclint:all', true)
    options.addBooleanOption('Werror', true)
    options.addBooleanOption('notimestamp', true)
    options.links('https://docs.oracle.com/en/java/javase/17/docs/api/')
}

tasks.named('check') {
    dependsOn tasks.named('javadoc')
}
~~~

Run in CI:

~~~text
./gradlew --no-daemon check
~~~

The `javadoc` task is attached to `check`, so `build` (which depends on `check`) also runs the quality gate. If you only run `compileJava` or `test`, the Javadoc task might not execute; the pipeline must invoke `check` or explicitly invoke `javadoc`.

`withJavadocJar()` creates the `javadocJar` task, which packages the output of `javadoc` with the `javadoc` classifier and registers a documentation variant. When using `maven-publish` or `ivy-publish`, this variant can be published alongside the Java component.

Run separately:

~~~text
./gradlew --no-daemon javadoc
./gradlew --no-daemon javadocJar
~~~

Default HTML output:

~~~text
build/docs/javadoc/index.html
~~~

The Java plugin's `javadoc` task processes sources in the main source set. If the project has custom source sets, test APIs, or multiple subprojects, you must configure separate tasks or aggregate according to your actual goal; do not assume the `javadoc` task automatically includes every source set.

## 10. Apache Ant: the `<javadoc>` task

Ant uses `<javadoc>` to invoke the Javadoc tool. Unlike `<javac>`, the Javadoc task typically processes all selected packages on each run; it does not have a per-file incremental mechanism like the compile task.

Example `build.xml`:

~~~xml
<project name="api-docs" default="javadoc">
  <target name="javadoc">
    <javadoc sourcepath="src/main/java"
             destdir="build/docs/javadoc"
             encoding="UTF-8"
             docencoding="UTF-8"
             charset="UTF-8"
             failonerror="true"
             failonwarning="true"
             useexternalfile="true">
      <package name="com.example.api"/>
      <arg value="-Xdoclint:all"/>
      <arg value="-Werror"/>
      <arg value="-notimestamp"/>
    </javadoc>
  </target>
</project>
~~~

Run:

~~~text
ant -noinput javadoc
~~~

- `failonerror=true`: fails when the Javadoc command returns an error.
- `failonwarning=true`: fails when output contains warnings; this attribute has been available since Ant 1.9.4.
- `useexternalfile=true`: writes command arguments to a temporary file, useful when the command line is too long.
- `<arg>`: passes Javadoc options that do not have a corresponding attribute on the Ant task.

`-notimestamp` is a Javadoc CLI option, not an attribute of Ant `<javadoc>`. Pass it using a nested `<arg>`. The Ant Javadoc task always forks a JVM because Javadoc calls `System.exit()`.

If you want to package the HTML into a JAR, run `<jar>` after the Javadoc target with `basedir="build/docs/javadoc"` and a separate `destfile`. Inspect the output before packaging to avoid releasing an empty JAR when source packages are misconfigured.

## 11. Sample CI workflow with GitHub Actions

Example workflow for Maven, running on pull requests and pushes to the main branch:

~~~yaml
name: Javadoc quality gate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  javadoc:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Compile, test and validate Javadoc
        run: ./mvnw -B -ntp verify

      - name: Store generated API documentation
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: api-javadoc
          path: target/reports/apidocs/
          if-no-files-found: error
~~~

This workflow uses the same JDK 17 for both the compiler and Javadoc, caches Maven dependencies, and makes `verify` a required gate. If Javadoc fails, the upload step does not run and the job is marked failed.

For Gradle, use:

~~~yaml
- uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: '17'
    cache: gradle

- name: Run verification including Javadoc
  run: ./gradlew --no-daemon check

- name: Store generated API documentation
  if: success()
  uses: actions/upload-artifact@v4
  with:
    name: api-javadoc
    path: build/docs/javadoc/
    if-no-files-found: error
~~~

In real-world CI:

- Run the gate on every pull request that modifies source files or Javadoc comments.
- Configure branch protection to require this job to pass before merging.
- Store the HTML artifact so reviewers can open and inspect links/content.
- Publish the documentation website or Javadoc JAR from protected branches/release tags, not from every pull request.
- Do not set `continue-on-error` on the Javadoc quality gate step.
- Preserve warning/error logs in job output so authors can fix the exact file and line.

## 12. Documentation quality policy for pull requests

An effective Javadoc gate needs an easy-to-understand policy:

**API level requiring documentation**

- Public and protected types, constructors, fields, and methods belonging to the public API.
- Package/module overviews if the package/module is meaningful to users.
- New APIs or behavior changes must update corresponding documentation.
- Private implementations only need documentation if the team has a specific requirement.

**Check level**

- DocLint `all` for APIs that already meet the standard.
- `all,-missing` during the transition period for legacy codebases.
- `-Werror` so new warnings are not ignored.
- `@link` tags must resolve against sources, classpath, and external docs.
- HTML output should be checked further if full accessibility/conformance guarantees are needed.

**Handling exceptions**

If a warning is a false positive or a comment intentionally does not apply, the suppression must be placed close to the relevant declaration and include a reason. Reviewers should treat suppressions as a policy change, not a quick way to make CI green.

You can use a separate rule for new packages: those packages enforce `-Xdoclint:all`, while legacy packages are migrated gradually. Once the backlog is cleared, raise the entire module's gate to strict mode.

## 13. Keeping output stable and reproducible

Javadoc HTML can contain timestamps, charsets, and content dependent on the JDK/locale. To make builds easy to compare between developer machines and CI:

- Pin the JDK/toolchain and build-tool versions.
- Pin Maven/Gradle plugin versions.
- Use `--release` to set the target API/source release.
- Declare source encoding, HTML encoding, and charset as UTF-8.
- Use `-notimestamp` or `<notimestamp>true</notimestamp>`.
- If packaging Maven archives, set `project.build.outputTimestamp` according to reproducible build practices.
- Use the same external API documentation metadata across all environments.
- Do not depend on unpinned, changing website links during offline build steps.

Do not cache HTML output as if it were a source input unless the build tool manages the corresponding cache key. Cache dependency/plugin downloads; let the Javadoc task determine when output needs to be regenerated.

## 14. External links, dependencies, and networking in CI

Javadoc must resolve types referenced in comments. If the API references dependencies, the corresponding compile classpath/module path must be provided. The Maven plugin usually obtains dependencies from the project model; the Gradle Javadoc task gets its classpath from the source set; Ant requires declaring a nested `<classpath>` when needed.

For external API docs:

- Use `-link` when CI has stable network access.
- Use `-linkoffline` when metadata is provided in a cache or workspace.
- Choose documentation matching the exact dependency/JDK version.
- Avoid linking to URLs that lack the corresponding `element-list`/`package-list`.
- If builds are network-restricted, do not disable DocLint/reference checks; provide appropriate offline metadata.

A `reference not found` error can be caused by an incorrect class/method name, a missing import, a dependency absent from the classpath, or unresolvable external documentation. Check each cause before adding a suppression.

## 15. Generated sources, annotation processors, and multi-module builds

If the project uses annotation processors to generate API sources, explicitly define the generated source directory and task ordering. Javadoc needs to see generated sources if those types are part of the published API. Ensure the Javadoc task runs after the generate-sources step and that the source path includes that output.

With Maven, verify that generated sources are added to the project before invoking `javadoc:javadoc`; if aggregating multiple modules, use `javadoc:aggregate` as appropriate.

With Gradle, add the generated source directory to the source set or configure the specific Javadoc task. Do not document generated files if they are merely implementation details.

With JPMS, Javadoc can use the module path and module source path. Verify which modules are exported and which packages belong to the public API. Do not include unexported internal packages in the public Javadoc artifact if users cannot access them.

## 16. Javadoc JAR and release artifacts

HTML output is useful for reviews and websites; a Javadoc JAR is useful for IDEs and Maven repositories. Both outputs can be produced from the same Javadoc task.

### Maven

~~~text
./mvnw -B -ntp javadoc:jar
~~~

The plugin creates an artifact with the `javadoc` classifier, for example:

~~~text
target/my-library-1.0-javadoc.jar
~~~

You can bind the `jar` goal to a release profile or invoke it in the release pipeline. `maven-javadoc-plugin` supports the `javadoc:jar` and `aggregate-jar` goals.

### Gradle

In the Java plugin:

~~~groovy
java {
    withJavadocJar()
}
~~~

The `javadocJar` task packages the HTML and registers a documentation variant. When combined with `maven-publish`, the Javadoc variant can be published alongside the Java component.

### Ant

Use `<jar>` after the `<javadoc>` target succeeds:

~~~xml
<target name="javadoc-jar" depends="javadoc">
  <jar destfile="build/libs/api-javadoc.jar"
       basedir="build/docs/javadoc"/>
</target>
~~~

Do not publish artifacts if the Javadoc gate fails or the output directory does not contain `index.html`.

## 17. Java 17+ example: API sources for testing in CI

Create `src/main/java/com/example/api/package-info.java`:

~~~java
/**
 * Public API for monetary calculations.
 *
 * <p>All amounts in this package use minor currency units.</p>
 *
 * @since 1.0
 */
package com.example.api;
~~~

Create `Money.java`:

~~~java
package com.example.api;

/**
 * Represents an amount in minor currency units.
 *
 * @since 1.0
 */
public final class Money {
    private final long minorUnits;

    /**
     * Creates a non-negative amount.
     *
     * @param minorUnits amount in the smallest currency unit
     * @throws IllegalArgumentException if the amount is negative
     */
    public Money(long minorUnits) {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("minorUnits must be non-negative");
        }
        this.minorUnits = minorUnits;
    }

    /**
     * Returns the amount in minor currency units.
     *
     * @return the amount in minor currency units
     */
    public long minorUnits() {
        return minorUnits;
    }
}
~~~

Create `PriceCalculator.java`:

~~~java
package com.example.api;

/**
 * Calculates totals for a quantity and unit price.
 *
 * <p>The result uses the same minor currency unit as {@code unitPrice}.</p>
 *
 * @see Money
 * @since 1.0
 */
public final class PriceCalculator {
    /**
     * Creates a calculator.
     */
    public PriceCalculator() {
    }

    /**
     * Calculates the total amount.
     *
     * @param quantity number of items; must be non-negative
     * @param unitPrice price of one item in minor currency units
     * @return the total amount in minor currency units
     * @throws IllegalArgumentException if an input is negative
     * @throws ArithmeticException if the result overflows a {@code long}
     * @see Math#multiplyExact(long, long)
     */
    public long total(int quantity, long unitPrice) {
        if (quantity < 0 || unitPrice < 0) {
            throw new IllegalArgumentException("inputs must be non-negative");
        }
        return Math.multiplyExact(quantity, unitPrice);
    }
}
~~~

This is an API source set for Javadoc tasks; it is not a standalone program with `main`. The Maven compile task compiled the three source files with `--release 17`, and then the Maven Javadoc Plugin generated HTML in the verify phase. Gradle `check` and Ant `<javadoc>` also generated documentation from the same API sample.

Verified results:

~~~text
Maven:  target/reports/apidocs/index.html
Gradle: build/docs/javadoc/index.html
Ant:    ant-docs/index.html
~~~

All three outputs contain `index.html`. Maven `javadoc:jar` and Gradle `javadocJar` also created Javadoc JARs successfully.

## 18. Testing the gate with an intentional error

To confirm that CI actually fails when Javadoc is invalid, create a fixture with a non-existent reference:

~~~java
/**
 * A class with an invalid reference.
 *
 * @see MissingMoneyType
 */
public final class BrokenApi {
}
~~~

Run:

~~~text
javadoc --release 17 -encoding UTF-8 -Xdoclint:all -Werror -d build/bad-docs -sourcepath src/main/java -subpackages com.example
~~~

Javadoc returns a non-zero exit code due to the unresolved reference. In CI, the job must remain in a failed state. After verifying the gate, remove the broken fixture from the real source tree and keep this test in a separate sandbox if you want to re-test the configuration later.

A gate that runs Javadoc without passing `-Werror` or without failing the build on warnings can still allow broken API documentation to pass through. Test both the passing case and the failing case when setting up a pipeline.

## 19. Troubleshooting Javadoc in CI

### `error: reference not found`

**Cause:** `{@link}`/`@see` uses an incorrect name, a dependency is missing from the classpath, or an external Javadoc link does not resolve.

**Resolution:** check the full type/method signature, compile classpath/module path, external docs URL, and `element-list`/`package-list`.

### `warning: no comment`

**Cause:** a public/protected declaration or constructor has no documentation under the enabled policy.

**Resolution:** write a comment describing the behavior and appropriate tags. If migrating legacy code, you can temporarily use `-Xdoclint:all,-missing` alongside a plan to address missing docs.

### Invalid `@param` or `@return`

**Cause:** parameter name does not match source, type parameter is missing `<T>`, a `void` method has `@return`, or a tag is misplaced.

**Resolution:** compare against the actual signature and only use tags that make sense for that declaration.

### HTML or special characters cause Javadoc to fail

**Cause:** using `<`, `>`, `&` as plain text, or unclosed HTML tags / missing attributes.

**Resolution:** use `{@code ...}`/`{@literal ...}` for literal text, and check HTML markup and accessibility attributes.

### `javadoc` cannot find classes from dependencies

**Cause:** Javadoc classpath/module path does not match the compile task.

**Resolution:** check Maven dependencies, Gradle Javadoc classpath, or Ant nested `<classpath>`. Ensure generated sources and compile outputs are ready.

### Maven build succeeds but Javadoc does not run

**Cause:** the plugin is declared in `build/plugins`, but the goal was not invoked or not bound to a lifecycle phase.

**Resolution:** bind `javadoc` to `verify`, or invoke `mvn javadoc:javadoc` explicitly. Verify that the pipeline actually runs `mvn verify`.

### Maven `failOnWarnings` does not fail CI

**Cause:** configuration is placed under `<reporting>` while CI only runs the build lifecycle, or the plugin config does not apply to the active execution.

**Resolution:** place the configuration in `<build><plugins>`, bind the execution to `verify`, check the plugin version, and inspect the Javadoc command line in debug logs.

### Gradle `javadoc` runs when invoked directly but not in CI

**Cause:** the pipeline only runs `compileJava`/`test`, or the `check` task does not depend on Javadoc.

**Resolution:** wire `check.dependsOn(javadoc)` or invoke `./gradlew check` with the verified task configuration.

### Ant reports warnings but the build stays green

**Cause:** `failonwarning` is not enabled, `-Werror` is not enabled, or the Ant target is not invoked in the pipeline.

**Resolution:** enable `failonerror` and `failonwarning`, pass `-Xdoclint:all`/`-Werror` via nested `<arg>`, and run the right CI target.

### External links fail in offline environments

**Cause:** `-link` needs to read metadata from an external URL.

**Resolution:** use `-linkoffline` with metadata cached or provided in the workspace, and pin the documentation version.

### HTML differs between local and CI

**Cause:** differing JDK/Javadoc versions, locale, encoding, timestamps, or external link metadata.

**Resolution:** pin toolchains/plugins, set UTF-8, use `-notimestamp`, fix the locale, and use the same source for external link metadata.

### Empty Javadoc output or missing packages

**Cause:** incorrect sourcepath/subpackages, source set contains no Java files, or packages are excluded.

**Resolution:** check source roots, package declarations, includes/excludes, and `index.html`. For multi-module builds, check which modules are being aggregated.

## 20. Pre-merge or pre-release checklist

- [ ] JDK/Javadoc version is pinned in CI.
- [ ] Java release target matches the library's baseline.
- [ ] Source encoding, HTML encoding, and charset are UTF-8.
- [ ] Public/protected APIs have appropriate class, constructor, and method documentation.
- [ ] `@param`, `@return`, `@throws`, `@since`, and `@deprecated` are accurate.
- [ ] `{@link}` and `@see` resolve properly.
- [ ] `package-info.java`/`module-info.java` are documented where needed.
- [ ] DocLint is enabled per policy (`all` or a controlled transition phase).
- [ ] `-Werror` or `failOnWarnings` fails CI when warnings appear.
- [ ] Maven `verify`, Gradle `check`, or the Ant target actually invokes Javadoc.
- [ ] External links have stable metadata or offline support.
- [ ] Generated sources and multi-module builds are included in the proper documentation scope.
- [ ] Output contains `index.html` and is saved as a CI artifact.
- [ ] Javadoc JAR is generated when releasing a library.
- [ ] Pull requests do not publish documentation to a production website.
- [ ] Reproducibility is controlled via toolchain, plugin, encoding, and timestamp settings.
- [ ] The gate has been tested with both valid sources and an intentional Javadoc error.

## 21. References

- Oracle JDK 24 — `javadoc` Command and DocLint: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html
- Oracle Java SE 24 — Javadoc Guide: https://docs.oracle.com/en/java/javase/24/javadoc/javadoc-guide.pdf
- Apache Maven Javadoc Plugin 3.12.0 — Introduction: https://maven.apache.org/plugins/maven-javadoc-plugin/
- Apache Maven Javadoc Plugin — Usage, goals `javadoc`, `javadoc:jar` and `aggregate`: https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html
- Apache Maven Javadoc Plugin — FAQ, `additionalOptions`, links and output encoding: https://maven.apache.org/plugins/maven-javadoc-plugin/faq.html
- Gradle — Building Java & JVM projects, Javadoc task: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — `CoreJavadocOptions` and `addBooleanOption`: https://docs.gradle.org/current/javadoc/org/gradle/external/javadoc/CoreJavadocOptions.html
- Gradle — `JavaPluginExtension.withJavadocJar()`: https://docs.gradle.org/current/dsl/org.gradle.api.plugins.JavaPluginExtension.html
- Apache Ant — Javadoc task, `failonwarning` and nested arguments: https://ant.apache.org/manual/Tasks/javadoc.html
- GitHub Actions — setup-java: https://github.com/actions/setup-java
- GitHub Actions — upload-artifact: https://github.com/actions/upload-artifact

Javadoc in CI should be a reproducible quality gate: same JDK/toolchain, same release target, explicit DocLint, warnings failing the build, and outputs retained for review. When the API changes, authors update the documentation directly in the pull request; when releasing a library, a Javadoc JAR is generated alongside the binary so IDEs and users can inspect the API contract.
