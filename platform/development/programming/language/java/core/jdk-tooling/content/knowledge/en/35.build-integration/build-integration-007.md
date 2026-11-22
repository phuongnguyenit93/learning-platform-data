# Javadoc Task in Build Integration

The **Javadoc task** is the build step that generates HTML documentation for a Java API from source code and documentation comments. When integrated into Gradle or Maven, this task enables teams to publish API documentation alongside software releases, automatically verify Javadoc quality, and package documentation for sharing with library consumers.

Javadoc is useful when developing libraries, SDKs, frameworks, or any module with a public API. A build can compile and pass tests while still producing API documentation with missing descriptions, broken links, or malformed HTML. Integrating the Javadoc task into CI helps catch these issues before release.

## 1. How do the Javadoc tool and Javadoc task differ?

The **Javadoc tool** is the `javadoc` program bundled with the JDK. It reads Java declarations, documentation comments, and input options, then uses a doclet to generate documentation. By default, the standard doclet generates HTML for packages, classes, interfaces, constructors, methods, and fields within the selected visibility scope.

The **Javadoc task** is the unit of work managed by a build tool. This task selects the source set, classpath, JDK tool, Javadoc options, output directory, and dependencies with other tasks.

| Component | Role |
| --- | --- |
| `javadoc` | JDK tool for generating HTML API documentation |
| Standard doclet | Default processor that generates HTML pages |
| Documentation comment | API description content located inside Java source code |
| DocLint | Checks syntax, HTML, references, and other issues in Javadoc |
| Gradle `Javadoc` task | Integrates documentation generation into a Gradle build |
| Maven Javadoc Plugin | Provides Javadoc goals for Maven |

Javadoc does not replace the compiler or unit tests. It validates and exports documentation from source code; compilation, dependency, or test failures remain the responsibility of their respective build steps.

## 2. Documentation generation lifecycle

A typical Javadoc generation workflow includes the following steps:

1. Select the source files or packages to document.
2. Provide the classpath/module path to resolve referenced types.
3. Read declarations and documentation comments.
4. Check tags, links, HTML, and DocLint rules.
5. Generate pages for packages, classes, members, hierarchy, index, and search.
6. Write HTML, CSS, JavaScript, and resources to the target directory.
7. Depending on the build, package the documentation into a Javadoc JAR or include it in a site.

Diagram:

```text
Java source + Javadoc comments
            |
            v
Build tool selects sources and classpath
            |
            v
Javadoc tool + Standard Doclet + DocLint
            |
            v
HTML API documentation
            |
            +----> build/docs/javadoc or target/reports/apidocs
            |
            v
Optional Javadoc JAR / published documentation
```

By default, Javadoc typically documents `public` and `protected` APIs. You can adjust the visibility scope using `-public`, `-protected`, `-package`, or `-private`. For libraries, consider publishing only the API that consumers are actually meant to use; documenting the entire implementation can expose internal details and create maintenance overhead.

## 3. Writing documentation comments properly

A Javadoc comment starts with `/**` and ends with `*/`. The comment should be placed immediately before the declaration it describes.

Example:

```java
package com.example.api;

/**
 * Creates greeting messages for callers of the public API.
 *
 * <p>See {@link String} for the text representation used by this class.
 *
 * @since 1.0
 */
public final class Greeting {
    private final String prefix;

    /**
     * Creates a greeting service.
     *
     * @param prefix non-null text placed before each name
     * @throws IllegalArgumentException if {@code prefix} is blank
     */
    public Greeting(String prefix) {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException("prefix must not be blank");
        }
        this.prefix = prefix;
    }

    /**
     * Builds a greeting for the supplied name.
     *
     * @param name the name to greet
     * @return a greeting beginning with the configured prefix
     * @throws IllegalArgumentException if {@code name} is null or blank
     * @since 1.0
     */
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return prefix + ", " + name + "!";
    }
}
```

A good documentation comment includes:

- A first sentence summarizing behavior, which appears in the summary section.
- Complete descriptions of input conditions, results, side effects, and limitations.
- `@param` for each parameter.
- `@return` for methods with a return value.
- `@throws` for exceptions meaningful to the caller.
- `@since` for the API version in which it was added.
- Links to related types or methods when they help readers understand quickly.

Do not merely repeat the method name. For example, `Gets the name` is usually unhelpful when the method is already named `getName()`. Describe the contract that API consumers need to know, including nullability, ordering, units, thread safety, or error conditions where relevant.

## 4. Commonly used block tags and inline tags

### Block tags

| Tag | Purpose |
| --- | --- |
| `@param name description` | Describes a parameter or type parameter |
| `@return description` | Describes the return value |
| `@throws Type description` | Describes an exception that may be thrown |
| `@since version` | Version in which the API was introduced |
| `@deprecated description` | Warns that an API is deprecated and suggests a replacement |
| `@see reference` | Adds a reference to another API or document |
| `@author name` | Records the author when project policy uses it |
| `@version text` | Records the documentation version if needed by the project |
| `@apiNote text` | Note intended for API consumers |
| `@implSpec text` | Describes requirements/contract for implementations |
| `@implNote text` | Note about specific implementation details |

Deprecated API example:

```java
/**
 * Returns the old display label.
 *
 * @deprecated Use {@link #displayName()} instead.
 */
@Deprecated(since = "2.0", forRemoval = false)
public String oldLabel() {
    return displayName();
}
```

The `@deprecated` tag describes the reason and migration path; the `@Deprecated` annotation marks the API in source code so the compiler and IDE recognize it. Keep the replacement information clear and consistent in both places.

### Inline tags

| Tag | Purpose |
| --- | --- |
| `{@link Type#method()}` | Creates a link displaying the API name |
| `{@linkplain Type#method()}` | Creates a link styled as plain text |
| `{@code expression}` | Displays code without interpreting HTML |
| `{@literal text}` | Displays literal characters |
| `{@inheritDoc}` | Inherits Javadoc content from the parent declaration |
| `{@value}` | Displays the value of an eligible constant |

Use `{@code}` for class names, method names, variables, and expressions. Use `{@link}` when readers may want to navigate to the referenced API. For generics or expressions containing angle brackets, `{@code}` prevents them from being parsed as HTML.

## 5. Package documentation and module documentation

You can document a package using a `package-info.java` file:

```java
/**
 * Public client APIs for the greeting service.
 *
 * <p>Types in this package are intended for application developers.
 */
package com.example.api;
```

Javadoc includes the package description on the package summary page.

For projects using Java modules, you can place a documentation comment before the `module` declaration in `module-info.java`:

```java
/**
 * Provides the greeting service API.
 */
module com.example.greeting {
    exports com.example.api;
}
```

When generating documentation for named modules, verify `--module`, `--module-path`, `--module-source-path`, and your package export policy. Module API documentation typically focuses on exported packages; internal packages should not become part of the public contract unintentionally.

## 6. Running Javadoc directly with the JDK

You can run Javadoc standalone to verify source files before integrating it into the build.

Example:

```bash
javadoc --release 17 -encoding UTF-8 -charset UTF-8 -docencoding UTF-8 -Xdoclint:all -Werror -link https://docs.oracle.com/en/java/javase/17/docs/api/ -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
```

Option meanings:

| Option | Role |
| --- | --- |
| `--release 17` | Uses the Java 17 API/platform when processing source code |
| `-encoding UTF-8` | Encoding of the source files |
| `-charset UTF-8` | Charset declared in the generated HTML |
| `-docencoding UTF-8` | Encoding of the HTML output |
| `-Xdoclint:all` | Enables all DocLint check groups |
| `-Werror` | Treats warnings as errors |
| `-link URL` | Links to external Javadoc |
| `-d directory` | Output directory for HTML files |
| `-sourcepath path` | Directory containing source packages |
| `-subpackages name` | Documents a package and its subpackages |

For documentation containing non-ASCII characters (such as Vietnamese), configure UTF-8 encoding consistently for both source and output. For APIs referencing types from external dependencies, provide the appropriate classpath so Javadoc can resolve those references.

You can pass a list of source files directly instead of `-subpackages`. You can also use `-overview` to add an overview page, `-private` to include private members in the documentation, or `@files` to store options in an argument file.

### Linking to external Javadoc

`-link` generates links to published API documentation. Javadoc reads `element-list` or `package-list` from the target URL to map types.

If the build has no Internet access, use `-linkoffline` and provide a local directory containing the corresponding package/module list:

```bash
javadoc -linkoffline https://docs.oracle.com/en/java/javase/17/docs/api/ local-jdk17-docs -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
```

`local-jdk17-docs` must contain the list file that Javadoc needs to read. The first URL is still the URL written into the HTML hyperlinks. Ensure the target URL exists and matches the API version your project intends to reference.

## 7. DocLint and documentation quality

DocLint checks for common mistakes in documentation comments. Its check groups include:

- `syntax`: invalid tag syntax, unescaped `<`, `>`, and `&`.
- `html`: HTML structure inside comments.
- `reference`: references to non-existent classes, members, or tags.
- `accessibility`: accessibility issues in HTML content, such as missing alt text.
- `missing`: required comments or tags that have not been provided.

You can explicitly enable all groups:

```bash
javadoc -Xdoclint:all -Werror -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
```

`-Werror` fails the build if any warning occurs. This works well for CI in libraries with a stable API. When adding Javadoc to a legacy codebase, you can enable DocLint first to inventory issues, fix them incrementally, and then enable `-Werror` as a quality gate.

Avoid disabling all checks with `-Xdoclint:none` just to make the build pass. If a specific check group does not fit the project, exclude it intentionally—such as `-Xdoclint:all,-missing`—while keeping syntax, HTML, and reference checks active.

DocLint is not a comprehensive HTML validator. After generating docs, projects with high quality requirements may still need a link checker, accessibility checker, or output HTML inspection.

## 8. Integrating the Javadoc task with Gradle

When applying the Java Plugin or Java Library Plugin, Gradle creates a `javadoc` task of type `Javadoc` for the `main` source set. The task uses the production sources and compile classpath of that source set, and generates documentation in `build/docs/javadoc` by default.

Groovy DSL configuration:

```groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
    withJavadocJar()
}

tasks.named('javadoc', Javadoc) {
    options.encoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.docEncoding = 'UTF-8'
    options.source = '17'
    options.addBooleanOption('Xdoclint:all', true)
    options.addBooleanOption('Werror', true)
    options.links('https://docs.oracle.com/en/java/javase/17/docs/api/')
}
```

Run the task:

```bash
./gradlew javadoc
```

Or using an installed Gradle distribution:

```bash
gradle javadoc
```

The `javadoc` task depends on `classes`, so Gradle runs any necessary prerequisite steps before generating docs. Once the task succeeds, open:

```text
build/docs/javadoc/index.html
```

`options.source = '17'` sets the source level accepted by Javadoc in Gradle. To ensure Javadoc uses the exact platform API of your target release, configure a JDK toolchain matching that target release. With the standalone JDK command or the Maven plugin, you can use `--release`/`release` to constrain the API version.

### Creating a Javadoc JAR with Gradle

Inside `java { ... }`, call:

```groovy
withJavadocJar()
```

Gradle registers the `javadocJar` task and builds an archive with the `javadoc` classifier. Run:

```bash
./gradlew javadocJar
```

The archive is typically located at:

```text
build/libs/<project>-<version>-javadoc.jar
```

The Javadoc variant is registered with the Java component. When using `maven-publish` or `ivy-publish`, this variant can be included in the publication so consumers can download API documentation alongside the binary artifact.

### Creating a separate task for test sources

When documentation is needed for test utilities, you can register a dedicated task:

```groovy
tasks.register('testJavadoc', Javadoc) {
    source = sourceSets.test.allJava
    classpath = sourceSets.test.compileClasspath
    destinationDirectory = layout.buildDirectory.dir('docs/testJavadoc')
}
```

A custom task must specify `source`; otherwise it has no source files to document. Provide the appropriate classpath to resolve references to test dependencies.

## 9. Integrating Javadoc with Maven

Maven uses the **Maven Javadoc Plugin** to invoke the Javadoc tool. Explicitly declare the plugin version to ensure reproducible build results across machines.

Example `pom.xml`:

```xml
<project>
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>greeting-api</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-javadoc-plugin</artifactId>
        <version>3.12.0</version>
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
          <charset>UTF-8</charset>
          <docencoding>UTF-8</docencoding>
          <failOnWarnings>true</failOnWarnings>
          <links>
            <link>https://docs.oracle.com/en/java/javase/17/docs/api/</link>
          </links>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Commonly used commands:

```bash
mvn javadoc:javadoc
mvn javadoc:jar
```

| Maven goal | Output |
| --- | --- |
| `javadoc:javadoc` | Generates HTML API docs |
| `javadoc:jar` | Generates docs and packages them into a Javadoc JAR |
| `javadoc:aggregate` | Aggregates Javadoc across multiple modules in a Maven reactor |
| `javadoc:aggregate-jar` | Creates an archive for aggregated documentation |
| `javadoc:test-javadoc` | Generates docs for test sources |

With standard configuration, HTML output is placed in `target/reports/apidocs`. The Javadoc JAR is created in `target` with the `javadoc` classifier, for example `target/greeting-api-1.0.0-javadoc.jar`.

### Javadoc in Maven Site

To include API documentation as a report in `mvn site`, declare the plugin inside the `<reporting>` section:

```xml
<reporting>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-javadoc-plugin</artifactId>
      <version>3.12.0</version>
    </plugin>
  </plugins>
</reporting>
```

`<build><plugins>` and `<reporting><plugins>` serve two different configuration purposes. The build section applies when invoking Javadoc goals directly; the reporting section integrates the report into Maven Site. If you configure both, be clear on which section each goal reads its configuration from.

For multi-module projects, use `javadoc:aggregate` when you want a single combined documentation set across modules rather than separate HTML outputs.

## 10. Javadoc task in CI/CD

Javadoc should be verified before packaging and publishing a library.

A simple pipeline might include:

1. Compile source code.
2. Run unit tests.
3. Run Javadoc with DocLint.
4. Package the binary JAR and Javadoc JAR.
5. Verify the archives.
6. Publish artifacts.

With Gradle:

```bash
./gradlew clean check javadoc javadocJar
```

With Maven:

```bash
mvn clean verify javadoc:javadoc javadoc:jar
```

These commands illustrate steps that can run in CI. Depending on the project, you can bind Javadoc goals to a lifecycle phase or keep them as a separate step to control execution time and publishing conditions.

Recommended practices:

- Use a consistent JDK/toolchain between local development and CI.
- Pin Gradle wrapper and Maven plugin versions.
- Use UTF-8 for source files and HTML output.
- Enable DocLint; enable fail-on-warning once API docs reach readiness.
- Verify external links; use an offline link list in air-gapped builds.
- Package the Javadoc JAR alongside the binary artifact.
- Avoid publishing documentation for internal packages or implementations unintentionally.
- Keep source revision and binary revision aligned so hyperlinks and source lines stay accurate.

## 11. Organizing and publishing documentation

There are several ways to distribute Javadoc:

| Distribution method | When appropriate |
| --- | --- |
| HTML in the build directory | Local developer viewing or CI artifacts |
| Javadoc JAR | Publishing alongside a library on a Maven/Ivy repository |
| Maven Site | Projects with a centralized documentation/reporting portal |
| Static web hosting | SDK/API docs requiring a public URL |
| Internal documentation server | Internal APIs requiring access control |

A Javadoc JAR typically uses the `javadoc` classifier, separate from the binary JAR. This allows Maven/Gradle repositories to store both the executable artifact and the documentation artifact. Do not bundle HTML inside the binary JAR unless specifically required; keeping a separate classifier lets consumers choose the artifact type they need.

When publishing a library, verify that the Javadoc JAR uses the same version as the binary JAR. If source code changes without regenerating docs, consumers may read an outdated API contract.

## 12. Troubleshooting the Javadoc task

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `No source files for Javadoc` | Custom task has no source configured or wrong source set | Set `source` and verify the source set |
| `package ... does not exist` | Missing dependency on classpath/module path | Configure compile classpath or module path |
| `reference not found` | `@link` points to an invalid type/member or unresolved dependency | Fix the reference and verify the classpath |
| `no @param` or `no @return` | Comment is missing a block tag | Add the corresponding tag description |
| `malformed HTML` | Invalid or unescaped HTML in comment | Fix the markup; use `{@code}`/`{@literal}` |
| `invalid flag` | Incompatible JDK and option, or build tool passing an invalid option | Check `javadoc --help` and the task's option file |
| `Unknown tag` | Custom tag not declared or Taglet not loaded | Use `-tag` or configure the Taglet |
| External link not working | URL lacks `element-list`/`package-list`, network blocked, or wrong version | Verify the URL; use `-linkoffline` when appropriate |
| Non-ASCII text displays incorrectly | Inconsistent source/output encoding | Set UTF-8 for encoding, charset, and docencoding |
| Maven build fails on warning | `failOnWarnings` is enabled | Fix the warning; relax rules only with clear justification |
| Gradle task produces no docs | Custom task lacks source or output is misconfigured | Verify `source` and `destinationDirectory` |
| Javadoc JAR missing | `javadoc:jar` not invoked or `withJavadocJar()` not enabled | Enable/register the packaging task and run it |
| API docs differ from published binary | Javadoc and binary built from different revisions | Use the same source revision and version in the pipeline |

### Step-by-step diagnosis

1. Run `javadoc --version` to identify the active JDK.
2. Run `javadoc --help` or `javadoc -X` to check available options.
3. Run Javadoc directly on a single source file to separate tool errors from build integration errors.
4. For Gradle, run `./gradlew javadoc --info` and inspect the generated Javadoc options file when the task fails.
5. For Maven, run `mvn -e javadoc:javadoc` to inspect the stack trace.
6. Look at the first warning; fix the offending comment or dependency before addressing subsequent warnings.
7. Inspect `index.html` and class pages in the output directory.
8. Re-run the task and confirm the Javadoc JAR has the expected version and classifier.

## 13. Practice: generating and verifying API docs

Use the `Greeting` class shown above.

### Generating docs with the JDK

```bash
javadoc --release 17 -encoding UTF-8 -charset UTF-8 -docencoding UTF-8 -Xdoclint:all -Werror -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
```

Open `build/docs/javadoc/index.html` and locate package `com.example.api`, class `Greeting`, its constructor, and the `greet` method.

### Generating docs with Gradle

Apply the `java-library` plugin, configure the `javadoc` task, and run:

```bash
gradle javadoc
gradle javadocJar
```

Verify the generated files:

```text
build/docs/javadoc/index.html
build/libs/greeting-api-1.0.0-javadoc.jar
```

### Generating docs with Maven

Declare `maven-javadoc-plugin`, then run:

```bash
mvn javadoc:javadoc
mvn javadoc:jar
```

Verify:

```text
target/reports/apidocs/index.html
target/greeting-api-1.0.0-javadoc.jar
```

Finally, try editing a comment to remove `@return` or add a link to a non-existent method. With DocLint and fail-on-warning enabled, the task should report a warning/error and the build should fail. Restore the valid comment, re-run, and confirm the build succeeds.

## 14. Key takeaways

- `javadoc` is the JDK tool; the Gradle `Javadoc` task and Maven Javadoc Plugin integrate it into builds.
- The Java Plugin creates the `javadoc` task for the `main` source set; the task typically depends on `classes`.
- The standard doclet generates HTML API docs from declarations and documentation comments.
- Write `/** ... */` comments with a clear summary sentence and complete block tags.
- Use `{@link}`, `{@code}`, and `{@literal}` to reference APIs and format code safely.
- `package-info.java` and `module-info.java` can carry package and module documentation.
- Configure UTF-8, external links, output directory, and DocLint consistently.
- `-Xdoclint:all` and `-Werror` bring Javadoc quality checks into CI.
- Gradle `withJavadocJar()` creates the `javadocJar` task and registers the documentation variant.
- Maven `javadoc:javadoc` generates HTML; `javadoc:jar` packages documentation; `javadoc:aggregate` supports multi-module builds.
- Maven `<build>` and `<reporting>` serve different configuration roles.
- The Javadoc JAR must be built from the same revision and version as the binary artifact.
- When the task fails, check source paths, classpath, JDK options, DocLint warnings, and external links first.

Integrating the Javadoc task turns API documentation into a verifiable, packageable, and publishable part of the build pipeline. When comments accurately describe the contract and the task runs automatically in CI, library consumers receive reliable documentation while the development team catches changes that break or omit documentation early.

## References

- [The javadoc Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- [Gradle: Building Java & JVM Projects — Generating API Documentation](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle Javadoc Task DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.javadoc.Javadoc.html)
- [Gradle JavaPluginExtension — withJavadocJar](https://docs.gradle.org/current/dsl/org.gradle.api.plugins.JavaPluginExtension.html)
- [Apache Maven Javadoc Plugin — Usage](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html)
- [Apache Maven Javadoc Plugin — Plugin Information](https://maven.apache.org/components/plugins-archives/maven-javadoc-plugin-LATEST/plugin-info.html)
