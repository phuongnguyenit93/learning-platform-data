# Reading Spring REST Docs Version Requirements

## Lesson Objectives

When upgrading **Spring REST Docs**, the first step is not changing the dependency version number and running a build. You need to determine which JDK, Spring Framework, Spring Boot, build tool, and test integration versions the target release requires; read the release notes, migration notes, and API changes; and then verify everything on a small upgrade branch.

This lesson belongs to the **Upgrade** chapter of the **SPRING_REST_DOCS** module: generating verifiable REST API documentation through HTTP tests with **MockMvc**, **WebTestClient**, or **REST Assured**; producing snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation; and integrating it into the build and CI.

After this lesson, you will be able to:

- Accurately identify the current and target versions of Spring REST Docs.
- Read the relevant release notes, migration guides, Javadocs, and dependency metadata.
- Check compatibility with JDK, Spring Framework, Spring Boot, Gradle/Maven, and test integrations.
- Identify breaking changes, deprecated APIs, and template/snippet changes.
- Create a verifiable upgrade plan with a clear rollback path.
- Compare pre-upgrade and post-upgrade snippets to catch unintended changes.
- Update documentation and CI after upgrading.

## 1. Why Read Version Requirements First?

Spring REST Docs runs alongside your application's test framework and build system. A new version may:

- Change the minimum Java version or require a newer framework version.
- Update APIs across the core and integration modules.
- Change transitive dependencies, the Asciidoctor plugin, or how snippets are configured.
- Remove APIs deprecated in earlier versions.
- Adjust templates, snippet names, or output formatting.
- Change how it integrates with JUnit, Spring Test, or test clients.

If you only bump the dependency version without checking these requirements, errors can surface at compile time, test runtime, during the documentation generation task, or when rendering Asciidoctor.

A safe process starts by asking: **what does the target version require, what is the project currently using, and which parts of the pipeline are affected?**

## 2. Identifying the Currently Used Version

Before reading release notes, determine the actual resolved version of the entire REST Docs dependency group. Do not just look at a single line in the build file, because versions may be managed via a BOM, version catalog, property, or dependency management.

### 2.1. With Gradle

Check `build.gradle` or `build.gradle.kts`, `gradle/libs.versions.toml`, plugin management, and dependency constraints. For example:

~~~groovy
dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc:3.0.3'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor:3.0.3'
}
~~~

This is an illustrative example, not a recommendation to pin a single fixed version for every project. If using a version catalog:

~~~toml
[versions]
springRestDocs = "3.0.3"

[libraries]
spring-restdocs-mockmvc = {
  module = "org.springframework.restdocs:spring-restdocs-mockmvc",
  version.ref = "springRestDocs"
}
~~~

Check the resolved dependencies:

~~~powershell
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
~~~

`dependencyInsight` shows which version was selected and why, even when another dependency pulls REST Docs in transitively. Make sure to inspect the exact configuration of the tests that generate snippets.

### 2.2. With Maven

Check `pom.xml`, the parent POM, BOM imports, properties, and `dependencyManagement`. For example:

~~~xml
<properties>
    <spring-restdocs.version>3.0.3</spring-restdocs.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-mockmvc</artifactId>
        <version>3.0.3</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Check the dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.restdocs
~~~

Also identify the version of the Asciidoctor Maven/Gradle plugin and libraries declared in separate configurations. A build may compile tests successfully while the Asciidoctor task still fails due to an incompatible extension or plugin.

### 2.3. Recording a Baseline

Before upgrading, create a baseline table:

| Component | Value to Record |
| --- | --- |
| JDK | Version used to compile and run tests |
| Spring Boot | Plugin/BOM version if the project uses Boot |
| Spring Framework | Actual resolved version |
| Spring REST Docs | Versions of core and integration modules |
| JUnit/Spring Test | Version running the HTTP tests |
| Gradle or Maven | Actual wrapper/version |
| Asciidoctor plugin | Plugin and version |
| Test integration | MockMvc, WebTestClient, or REST Assured |
| Current output | Snippet IDs, file names, template format, and output directory |

A baseline helps distinguish pre-existing issues from errors introduced by the upgrade.

## 3. Finding Official Documentation for the Target Version

Prioritize sources in the following order:

1. **Release notes/changelog** of Spring REST Docs for the versions from current to target.
2. **Migration guide** if the project or version branch provides conversion documentation.
3. **Reference documentation** for the exact version.
4. **Javadoc/API documentation** for the artifact at the exact version.
5. Dependency metadata/POM to confirm framework requirements and transitive dependencies.
6. Issue tracker or release discussions when release notes do not fully explain a change.

Do not read the `current` documentation and assume it matches the API of the version you are running. Documentation URLs may point to the latest release while the project is still on an older version. Open the Javadoc and reference docs for the exact version or check against the actually resolved artifacts.

### 3.1. How to Read Release Notes

For every release between the current version and the target version, look for these information groups:

- New features: do new features require configuration changes?
- Improvements: have default behaviors or outputs changed?
- Deprecations: which APIs are marked deprecated and what are their replacements?
- Breaking changes: have APIs been removed, had their signatures changed, or changed behavior?
- Dependency updates: are there new requirements for JDK/Spring/JUnit/REST Assured/Asciidoctor?
- Bug fixes: is the project relying on an old buggy behavior?

Do not skip release notes for intermediate versions when upgrading across multiple minor/major releases. A breaking change might appear in an intermediate release and then be explained in the migration notes of the next release.

### 3.2. Recording Evidence for Each Change

Create a change table in the pull request or ticket:

| Topic | Source/Version | Project Impact | Action Required |
| --- | --- | --- | --- |
| Java requirement | Release notes/POM | Does the current CI JDK meet it? | Upgrade JDK or pick a different version |
| MockMvc integration | Javadoc/changelog | Has the configuration API changed? | Update test setup |
| Snippet template | Reference/release notes | Have snippet names/formats changed? | Update AsciiDoc/Markdown includes |
| Asciidoctor | Dependency metadata | Are the plugin/extensions compatible? | Update plugin or configuration |
| Deprecated API | Javadoc | Which APIs are tests calling? | Switch to replacement APIs |

Include specific links and version numbers so reviewers can verify them. Avoid vague notes like "checked release notes".

## 4. Checking Compatibility Across the Entire Stack

Spring REST Docs does not operate in isolation. Check compatibility across these layers:

| Component | What to Confirm |
| --- | --- |
| JDK | Minimum version and bytecode target |
| Spring Framework | Compatibility with Spring Test, Web MVC/WebFlux |
| Spring Boot | Whether the BOM and dependency management select the right REST Docs version |
| JUnit | Whether the extension/rule and test lifecycle in use are compatible |
| MockMvc | Artifact and documentation configuration API |
| WebTestClient | WebFlux/Spring Test and documentation configurer |
| REST Assured | Filter API and REST Assured version |
| Gradle/Maven | Wrapper, plugin DSL, and toolchain |
| Asciidoctor | Plugin, extension, and snippet attribute |
| Markdown renderer | Current template format or assembly step |

Not every project needs to use the exact same versions of these components. What matters is matching the official requirements of the target REST Docs version against the versions resolved in your own project.

## 5. Distinguishing Artifact Versions

Spring REST Docs provides artifacts for core and each test integration. Common artifact names include:

| Artifact | Role |
| --- | --- |
| spring-restdocs-core | Core API and underlying mechanisms |
| spring-restdocs-mockmvc | MockMvc integration |
| spring-restdocs-webtestclient | WebTestClient integration |
| spring-restdocs-restassured | REST Assured integration |
| spring-restdocs-asciidoctor | Extension supporting Asciidoctor integration |

When declaring multiple artifacts, keep versions synchronized according to the release guidelines. Avoid mixing core and integration modules across different versions unless explicitly instructed by the maintainers.

If using Spring Boot dependency management, identify which BOM manages each artifact. Adding an explicit version directly to one dependency can override the version selected by the BOM and produce an untested combination.

## 6. Checking API Changes and Deprecations

When reading Javadocs/release notes, look for:

- Deprecated classes or methods.
- Constructors with changed visibility or replacements.
- Method signatures with changed parameter or return types.
- Renamed packages or classes moved to another module.
- Changed default behavior.
- Integration filters/configurers with changed initialization patterns.

For example, tests might currently configure documentation directly inside `document(...)`, whereas the newer version recommends placing default preprocessing in a configurer. Only switch once the new API has been verified in the Javadoc for the target version.

Do not rely on blog posts or old Q&A answers to conclude that a method still exists. Use IDE navigation, test compilation, and the Javadoc for the exact artifact.

## 7. Checking Snippet and Template Changes

An upgrade may not fail tests yet still alter the generated documentation:

- Different snippet names or file extensions.
- Different HTTP request/response formatting.
- Different field table ordering or content.
- Changes in JSON pretty-printing.
- Differences in which headers are displayed or omitted.
- Default templates or custom templates needing updates.

Before upgrading, save a representative baseline set of snippets for each operation type:

~~~text
baseline-snippets/
├── orders-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   └── response-fields.adoc
└── orders-create/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
~~~

After upgrading, regenerate snippets into a clean output directory and compare. Classify the diff:

1. Intentional changes introduced by the release.
2. Changes caused by fixtures/tests or API contracts.
3. Formatting/template changes that do not affect content.
4. Unexpected changes that require investigation.

Do not overwrite the baseline just to make the diff disappear. Every change should have a reason and reviewers must understand its impact.

## 8. Planning a Step-by-Step Upgrade

A verifiable plan:

1. Record the baseline versions and current build results.
2. Choose the target version based on JDK/framework requirements and project support policies.
3. Read all release notes/migration notes between the current and target versions.
4. List deprecated APIs, breaking changes, and artifacts to synchronize.
5. Update dependencies/plugins in a clearly scoped change.
6. Run compilation and REST Docs tests.
7. Compare baseline snippets with newly generated snippets.
8. Render Asciidoctor/Markdown documentation and verify links/output.
9. Run CI on the JDK and build environment supported by the project.
10. Document the changes and how to roll back if issues occur.

If you are crossing multiple major versions, consider upgrading through documented intermediate milestones. Stepping incrementally makes it easier to pinpoint which release caused a failure.

## 9. Example: Checking Versions in Gradle

Suppose the project manages versions through a version catalog:

~~~toml
[versions]
springRestDocs = "3.0.3"

[libraries]
spring-restdocs-mockmvc = {
  module = "org.springframework.restdocs:spring-restdocs-mockmvc",
  version.ref = "springRestDocs"
}
~~~

When upgrading, update the version in one single place to a version confirmed to be compatible:

~~~toml
[versions]
springRestDocs = "VERSION_TARGET"
~~~

`VERSION_TARGET` is only a placeholder. Do not copy placeholders into a real build. Select a specific version from the release notes and verify compatibility before committing.

Then verify:

~~~powershell
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
./gradlew clean test
./gradlew asciidoctor
~~~

If the build has separate tasks for WebTestClient or REST Assured, run those tests/tasks as well. `clean test` alone does not prove that Asciidoctor or custom Markdown assembly works.

## 10. Example: Checking Versions in Maven

With Maven, managing the version via a property enables centralized updates:

~~~xml
<properties>
    <spring-restdocs.version>3.0.3</spring-restdocs.version>
</properties>
~~~

After selecting a specific version:

~~~bash
mvn clean test
mvn verify
mvn dependency:tree -Dincludes=org.springframework.restdocs
~~~

`verify` only runs the plugins/tasks declared in the project lifecycle. Check `pom.xml` to confirm that the documentation generation step is actually bound to the lifecycle; do not assume Maven runs Asciidoctor automatically just because the dependency is present.

## 11. Assessing Risks and Rollback Paths

Before merging an upgrade, answer:

- If REST Docs fails to compile, which dependencies changed?
- If snippet names changed, which AsciiDoc/Markdown files need updating?
- If the Asciidoctor plugin is incompatible, can the plugin upgrade be separated from REST Docs?
- If documentation output changed, does the change reflect the contract or only formatting?
- Can you roll back to the previous version with a clean revert?

Keep the upgrade diff focused. Avoid refactoring all tests, changing templates, changing build tools, and upgrading REST Docs at the same time unless necessary. When multiple independent changes are mixed together, pinpointing the root cause of a failure becomes very difficult.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Compile failure after upgrade | Removed/changed API signature or insufficient JDK | Read migration notes/Javadoc, update call sites, or choose a compatible version |
| `NoSuchMethodError` at test runtime | Core and integration artifacts have mismatched versions or transitive override | Check `dependencyInsight`/dependency tree and synchronize versions |
| Tests pass but Asciidoctor fails | Plugin/extension or snippet path changed | Check task, extension dependency, and include paths |
| Snippet not found | Different identifier, file name, or output directory | Compare new output and intentionally update includes |
| Field table changed | Template/version or descriptor changed | Inspect diff and verify payload/descriptor |
| Local build passes, CI fails | Different JDK, wrapper, Maven/Gradle, or cache | Pin toolchain and use wrapper in CI |
| Dependency version differs from declared | BOM, constraint, or transitive dependency selected another version | Use `dependencyInsight`/tree to locate the selection source |
| Markdown rendering error | Unsupported template format or extension | Verify renderer and templates for the target version |
| Multi-version upgrade hard to debug | Skipped checking intermediate change milestones | Split steps according to release/migration guides |
| Huge snippet diff | Dynamic fixtures or changed preprocessing | Normalize fixtures, compare per operation, and classify diffs |

## 13. Hands-On Exercise

Choose a Spring REST Docs project that currently has MockMvc or REST Assured tests.

Requirements:

1. Record the current JDK, Spring Boot, Spring Framework, REST Docs, JUnit, build tool, and Asciidoctor plugin versions.
2. Pick a target REST Docs version and note the release notes/reference/Javadoc sources.
3. Create a compatibility requirements and breaking changes table for every release you need to cross.
4. Check the actual resolved versions using Gradle `dependencyInsight` or Maven `dependency:tree`.
5. Capture baseline snippets for at least one GET and one POST operation.
6. Upgrade the dependencies in an isolated change, synchronizing core and integration artifacts per official guidance.
7. Run tests, regenerate snippets, and compare diffs.
8. Render the Asciidoctor/Markdown documentation and check includes, field tables, and links.
9. Run the pipeline on the JDK/toolchain supported by the project.
10. Document the rollback procedure and any changes to carry forward to the next upgrade.

**Completion criteria:** the target version has verified sources; actual resolved dependencies are correct; both tests and documentation build; all snippet changes are explained; CI reproduces the result.

## Key Takeaways

Reading version requirements is a mandatory step before upgrading Spring REST Docs. Establish the actual baseline, read release notes and migration notes for every milestone, verify JDK/Spring/build tool/test integration compatibility, synchronize artifacts, and review deprecated APIs. Do not stop at verifying test compilation: regenerate snippets, compare outputs, and render Asciidoctor/Markdown. A solid upgrade change has a clear scope, concrete compatibility evidence, reproducible CI results, and a transparent rollback path.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs Releases](https://github.com/spring-projects/spring-restdocs/releases), [Spring REST Docs API Javadoc](https://docs.spring.io/spring-restdocs/docs/current/api/), [Spring Boot Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html), [Gradle dependencyInsight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html), and [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/).
