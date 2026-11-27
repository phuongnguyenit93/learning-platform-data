# Packaging Snippets into Artifacts or Release Documentation

## 1. Distinguishing Intermediate Snippets from Release Documentation

Spring REST Docs generates **snippets** from HTTP tests. Files such as `http-request.adoc`, `http-response.adoc`, `request-fields.adoc`, and `curl-request.adoc` are inputs for compiling documentation. They usually reside in `build/generated-snippets` (Gradle) or `target/generated-snippets` (Maven).

Release documentation is typically the rendered output, such as HTML or PDF. Artifact generation flow:

~~~text
MockMvc / WebTestClient / REST Assured tests
                    |
                    v
        generated-snippets/
                    |
                    v
       AsciiDoc source + includes
                    |
                    v
             Asciidoctor
                    |
                    v
        rendered API documentation
                    |
                    v
          release artifact / CI
~~~

These two types of outputs serve different purposes:

| Output | What Is It Used For? | Suitable for API Consumers? |
| --- | --- | --- |
| Generated snippets | Intermediate data for compiling, inspecting, or reusing | Generally should not be published standalone |
| HTML | Direct reference, hosted on a website or portal | Yes |
| PDF | Downloadable documentation, archival, or bundled with releases | Yes |
| Source AsciiDoc | Maintaining rebuildable documentation | Suitable for development teams |
| JAR/ZIP containing docs | Distributing documentation alongside the application version | Yes, if structure and access method are clear |

In the **SPRING_REST_DOCS** module, HTTP tests are the verification source for requests/responses; snippets are compiled into Asciidoctor/Markdown documentation and integrated into build/CI. When packaging, decide which artifacts serve API consumers and which serve internal teams rebuilding documentation.

## 2. Choosing What to Include in an Artifact

Before configuring Gradle or Maven, determine the distribution goal.

### 2.1. Publishing HTML Only

This is appropriate when documentation is hosted on the web or an internal portal. Readers open `index.html` and navigate through API pages.

~~~text
api-docs/
├── index.html
├── images/
├── css/
└── ...
~~~

The artifact only needs to contain the rendered HTML directory and accompanying assets. There is no need to bundle all snippets into the ZIP/JAR if users only need to read the documentation.

### 2.2. Publishing PDF

PDF works well for documentation that needs to be downloaded or archived with a release. PDFs must be rendered from AsciiDoc using a PDF-capable backend/toolchain, and the resulting PDF file placed in the artifact. Do not rename an HTML file extension to PDF; these are two different rendering steps.

### 2.3. Publishing Snippets or Source AsciiDoc

Snippets are useful when integration teams want to view AsciiDoc or curl request/response examples, when development teams want to reuse snippets to compile aggregated documentation, or when test evidence needs to be archived.

In those cases, package snippets as a ZIP or separate internal artifact, preserving the directory structure by document identifier. Do not release scattered snippets without guidance on version, paths, and how to include them.

Source AsciiDoc can be stored alongside the artifact if recipients need to rebuild the documentation. Provide the required assets and configuration; sending just a single `.adoc` file without its includes and images will not be enough to reproduce the documentation.

## 3. Gradle: Creating a ZIP Artifact for HTML Documentation

Suppose the `asciidoctor` task renders documentation into `build/docs/asciidoc`. You can create a dedicated ZIP task:

~~~groovy
def apiDocsDir = layout.buildDirectory.dir('docs/asciidoc')

tasks.register('apiDocsZip', Zip) {
    dependsOn tasks.named('asciidoctor')
    from(apiDocsDir)
    archiveBaseName = 'registration-api-docs'
    archiveClassifier = 'html'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

Run:

~~~bash
./gradlew clean apiDocsZip
~~~

The result looks like:

~~~text
build/distributions/
└── registration-api-docs-html.zip
~~~

The final filename also depends on the version and archive naming conventions of the Gradle project. `dependsOn` ensures `asciidoctor` runs before the ZIP task collects contents. `from(apiDocsDir)` puts the rendered documentation into the ZIP.

### 3.1. Including the ZIP in the Build Lifecycle

If you want standard builds to produce the documentation artifact automatically, wire the ZIP task to `assemble`:

~~~groovy
tasks.named('assemble') {
    dependsOn tasks.named('apiDocsZip')
}
~~~

Then:

~~~bash
./gradlew clean build
~~~

will execute the required tasks according to the dependency graph and produce the docs ZIP. Only attach it to `assemble` if every build needs this artifact; if documentation is heavy or only published during releases, keep it as a separate task so fast builds do not re-render docs every time.

### 3.2. Distributing HTML as a JAR Classifier

If your release infrastructure is geared toward Maven repositories or Gradle publications, you can package HTML documentation into a JAR with a classifier:

~~~groovy
tasks.register('apiDocsJar', Jar) {
    dependsOn tasks.named('asciidoctor')
    from(apiDocsDir)
    archiveBaseName = 'registration-api'
    archiveClassifier = 'api-docs'
}

artifacts {
    archives tasks.named('apiDocsJar')
}
~~~

Here the JAR is simply a container for distributing HTML and assets. Recipients must extract it to open `index.html`; a ZIP is generally clearer when the artifact is primarily a static website.

With modern Gradle publishing, declare the artifact inside a publication tailored to the target repository rather than relying on the legacy `archives` configuration used in older projects. Specific publication configuration depends on the `maven-publish` plugin and your team's release conventions.

## 4. Gradle: Packaging Generated Snippets Separately

If your team needs to share snippets for reuse by another docs module, you can create a separate ZIP:

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.register('snippetsZip', Zip) {
    dependsOn tasks.named('test')
    from(snippetsDir)
    archiveBaseName = 'registration-api-snippets'
    archiveClassifier = 'snippets'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

The `test` task must be configured to output to this directory, and Spring REST Docs must write snippets to the exact same location:

~~~groovy
tasks.named('test') {
    outputs.dir snippetsDir
}
~~~

Example test setup:

~~~java
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
~~~

The snippets ZIP preserves the identifier directory structure:

~~~text
registration-api-snippets.zip
└── registrations/
    └── create/
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
~~~

Do not bundle the snippets ZIP into the HTML ZIP by default. Only include snippets when consumers genuinely need intermediate data; otherwise, the release artifact becomes larger and may expose unnecessary internal test details.

## 5. Maven: Packaging HTML with the Assembly Plugin

Suppose the Asciidoctor Maven Plugin renders HTML into `target/generated-docs`. You can use the Maven Assembly Plugin to create a ZIP from that directory. Create the descriptor `src/assembly/api-docs.xml`:

~~~xml
<assembly xmlns="http://maven.apache.org/ASSEMBLY/2.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/ASSEMBLY/2.2.0
          https://maven.apache.org/xsd/assembly-2.2.0.xsd">
    <id>api-docs</id>
    <formats>
        <format>zip</format>
    </formats>
    <includeBaseDirectory>false</includeBaseDirectory>
    <fileSets>
        <fileSet>
            <directory>${project.build.directory}/generated-docs</directory>
            <outputDirectory>/</outputDirectory>
        </fileSet>
    </fileSets>
</assembly>
~~~

Declare the Assembly Plugin execution in the `package` phase or invoke the goal after Asciidoctor has run:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>${maven.assembly.plugin.version}</version>
    <executions>
        <execution>
            <id>package-api-docs</id>
            <phase>package</phase>
            <goals>
                <goal>single</goal>
            </goals>
            <configuration>
                <descriptors>
                    <descriptor>src/assembly/api-docs.xml</descriptor>
                </descriptors>
                <finalName>${project.artifactId}-${project.version}</finalName>
                <appendAssemblyId>true</appendAssemblyId>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Version properties should be managed in the POM or parent POM. Crucially, the `package` phase runs after the `prepare-package` phase in the standard lifecycle, where the Asciidoctor execution is bound to render docs.

The result may look like:

~~~text
target/
├── generated-snippets/
├── generated-docs/
└── registration-api-1.0.0-api-docs.zip
~~~

Exact paths depend on plugin configuration and artifact naming. Inspect the ZIP file after building to ensure `index.html` is at the expected root without an unintended extra wrapper directory.

## 6. Maven: Attaching Documentation as a Secondary Artifact

If your release repository uses Maven coordinates, you can attach the documentation ZIP as a secondary artifact so consumers can download it under the same groupId/artifactId/version:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>${build.helper.plugin.version}</version>
    <executions>
        <execution>
            <id>attach-api-docs</id>
            <phase>package</phase>
            <goals>
                <goal>attach-artifact</goal>
            </goals>
            <configuration>
                <artifacts>
                    <artifact>
                        <file>${project.build.directory}/${project.build.finalName}-api-docs.zip</file>
                        <type>zip</type>
                        <classifier>api-docs</classifier>
                    </artifact>
                </artifacts>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

The secondary artifact has the `api-docs` classifier so it is not confused with the application JAR. The attached filename must match the exact output of the Assembly Plugin; if the two plugins produce different names, attaching will fail.

Once configured properly, `mvn deploy` can publish the main artifact along with the secondary artifact to the Maven repository according to the lifecycle. Test packaging and local staging first before integrating into an approved release pipeline.

## 7. Integrating Documentation into the Release Pipeline

A typical pipeline:

~~~text
Compile
  |
  v
Run HTTP documentation tests
  |
  v
Generate REST Docs snippets
  |
  v
Render Asciidoctor HTML/PDF
  |
  v
Package API docs artifact
  |
  v
Verify archive contents
  |
  v
Publish with application release
~~~

CI should run tests and render documentation in the same build so the artifact accurately reflects the commit being released. For example:

~~~bash
# Gradle
./gradlew clean test asciidoctor apiDocsZip

# Maven
mvn clean verify
~~~

If Maven assembly is bound to the `package` phase, use `mvn clean package` or a later phase. If artifacts are attached and published during `deploy`, only run `mvn deploy` in a release job equipped with proper verification steps and release permissions.

### 7.1. Verifying Artifact Contents

Before publishing, confirm:

- `index.html` or PDF exists at the expected root location.
- CSS, JavaScript, images, and subpages preserve their relative directory structure.
- No pages are missing due to broken includes or skipped tests.
- The docs version/commit matches the application version.
- The artifact contains no temporary files, test logs, secrets, or environment data.
- If packaging snippets, the document identifier structure is preserved.

Include an automated archive check, such as listing ZIP contents and verifying `index.html` exists. If documentation is web-hosted, check internal links after extracting into a staging directory.

## 8. Versioning and Reproducibility

API documentation is part of the public contract. Publish it with the same version as the API or explicitly state the API commit/version described by the documentation.

1. Use the same version property as the application when naming the docs artifact.
2. Generate docs from the exact release commit/tag.
3. Do not take snippets from an older build to render documentation for a new commit.
4. Use a clean build when producing release artifacts.
5. Store release artifacts in the same release repository system so they remain retrievable.

Example artifact names:

~~~text
registration-api-1.4.0-api-docs.zip
registration-api-1.4.0-api-snippets.zip
~~~

Do not use `latest` as the sole identifier for archived documentation. A website may have a `latest` alias, but immutable artifacts should carry an explicit version.

## 9. Common Errors

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Empty ZIP | Packaging task ran before Asciidoctor or pointed to the wrong source directory | Add proper dependency/phase and inspect the output directory |
| ZIP is missing CSS/images | Copied only the raw HTML file without rendered assets | Package the entire Asciidoctor output directory |
| Archive has an unexpected nested directory | Assembly `outputDirectory` or `includeBaseDirectory` is misconfigured | Inspect ZIP structure and adjust the descriptor |
| Secondary artifact is not published | Artifact not attached or wrong classifier/file path | Check `build-helper` execution and file existence |
| Docs do not match application version | Hardcoded separate version or built from a different commit | Share the version property and build from the release tag |
| Stale snippets leak into release | Output not cleaned or tests did not regenerate all snippets | Run clean tests before rendering and packaging |
| CI produces HTML, but release has no ZIP | ZIP task is omitted from lifecycle/CI command | Add the task to the build/release pipeline |
| Internal snippets published unintentionally | Unfiltered packaging of `generated-snippets` | Publish only HTML/PDF; create a separate snippets artifact only when needed |

## 10. Practice Exercise

In a Spring REST Docs project, generate HTML documentation for the `GET /orders/{id}` endpoint and package it as a standalone artifact.

Steps:

1. Write a MockMvc test generating request/response snippets.
2. Configure Asciidoctor to render into the build output directory.
3. For Gradle, create a ZIP task depending on `asciidoctor`; for Maven, use the Assembly Plugin to package the HTML directory after the rendering phase.
4. Name the artifact using `artifactId`, `version`, and the `api-docs` classifier.
5. If distributing snippets to another docs module is required, create a separate `api-snippets` artifact preserving the identifier structure.
6. Run a clean build and verify that the archive contains `index.html`, CSS, images, and required pages.
7. Verify that the docs version matches the API release version.

**Completion criteria:** The documentation artifact is produced after tests and rendering succeed; the archive structure can be opened or hosted directly; the version matches the API; intermediate snippets are published only when explicitly required.

## References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Gradle User Manual — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Gradle User Manual — Publishing](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Apache Maven Assembly Plugin — Usage](https://maven.apache.org/plugins/maven-assembly-plugin/usage.html)
- [Build Helper Maven Plugin — Attach Artifact](https://www.mojohaus.org/build-helper-maven-plugin/attach-artifact-mojo.html)
- [Asciidoctor Maven Plugin — Usage](https://docs.asciidoctor.org/maven-tools/latest/plugin/usage/)
