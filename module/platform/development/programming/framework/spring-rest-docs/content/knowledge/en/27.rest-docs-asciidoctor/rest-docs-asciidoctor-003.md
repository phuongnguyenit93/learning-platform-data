# Including Snippets Using Relative Paths

## 1. Why Do You Need to Understand How Include Paths Are Resolved?

Spring REST Docs generates `.adoc` snippets from HTTP tests using MockMvc, WebTestClient, or REST Assured. Asciidoctor merges those snippets into the main document using the `include::` macro. When a project has multiple source directories, builds run from different working directories, or includes are nested multiple levels deep, relative paths can easily point to the wrong place.

For example:

```asciidoc
include::{snippets}/books-get/http-request.adoc[]
```

The include statement only works if `{snippets}` has been assigned the exact directory containing `books-get/http-request.adoc`. If writing a relative path directly such as `include::../../build/generated-snippets/...[]`, the path must be calculated from the exact source document containing that macro.

The important principle is: **relative include paths are resolved relative to the location of the current document (the document processing the include), within Asciidoctor's base directory context; you should not assume it is always relative to the terminal working directory**. For nested included documents, the path of a subsequent include must be calculated from the file currently containing that macro. Inspect the file location and `base_dir`/`docdir` configuration when diagnosing issues.

## 2. Distinguishing Project Directory, Source Directory, and Snippets Directory

A common Gradle structure:

```text
spring-rest-docs/
├── build.gradle
├── src/
│   ├── main/java/...
│   ├── test/java/...
│   └── docs/
│       └── asciidoc/
│           ├── index.adoc
│           └── operations/
│               └── books.adoc
└── build/
    ├── generated-snippets/
    │   └── books-get/
    │       ├── http-request.adoc
    │       └── http-response.adoc
    └── docs/asciidoc/html5/index.html
```

There are three different locations here:

| Location | Example | Purpose |
| --- | --- | --- |
| Project directory | `spring-rest-docs/` | Contains `build.gradle` and `src/`. |
| AsciiDoc source directory | `src/docs/asciidoc/` | Contains `index.adoc`, operation files, and team-authored documents. |
| Generated snippets directory | `build/generated-snippets/` | Where HTTP tests write snippets. |

The file `index.adoc` is located in `src/docs/asciidoc/`. To reach `build/generated-snippets/`, the relative path from `index.adoc`'s location is:

```text
../../build/generated-snippets/
```

Because you need to go up two levels from `src/docs/asciidoc/` to the project root, then enter `build/generated-snippets/`.

## 3. Writing Includes Directly Using Relative Paths

With the structure in section 2, `src/docs/asciidoc/index.adoc` can be written as:

```asciidoc
= Books API

== Get book

=== HTTP request
include::../../build/generated-snippets/books-get/http-request.adoc[]

=== HTTP response
include::../../build/generated-snippets/books-get/http-response.adoc[]
```

The path `../../build/...` is calculated from the directory containing `index.adoc`, not from whatever location the user happened to run the `gradle` command in the terminal. If `index.adoc` is moved to another directory, the number of `../` levels must be recalculated.

This is a direct and easy-to-understand approach for small documents. However, if there are dozens of operations, repeating long paths makes the document hard to maintain. The `{snippets}` attribute helps separate path configuration from include content.

## 4. Using the `snippets` Attribute to Shorten Paths

In `index.adoc`, you can declare:

```asciidoc
= Books API
:snippets: ../../build/generated-snippets

== Get book

=== HTTP request
include::{snippets}/books-get/http-request.adoc[]

=== HTTP response
include::{snippets}/books-get/http-response.adoc[]
```

`{snippets}` is an Asciidoctor document attribute. The value `../../build/generated-snippets` is still resolved relative to the location of the document where the attribute is declared/used in the document context. If the project already uses `spring-restdocs-asciidoctor`, the extension can automatically configure this attribute to the generated snippets directory according to the build tool; in that case, there is no need to declare it again unless you want to override it.

With the default convention:

| Build tool | Commonly used snippets directory |
| --- | --- |
| Gradle | `build/generated-snippets` |
| Maven | `target/generated-snippets` |

If using the attribute provided by the plugin, the include syntax remains the same:

```asciidoc
include::{snippets}/orders-create/http-request.adoc[]
```

The difference lies in where the `snippets` value is assigned: the source file, build configuration, or the Spring REST Docs extension.

## 5. Paths When Including Nested Operation Files

Large documents are often split into a main file and operation files:

```text
src/docs/asciidoc/
├── index.adoc
├── common/
│   └── authentication.adoc
└── operations/
    ├── books-list.adoc
    └── books-get.adoc
```

`index.adoc` can include:

```asciidoc
include::common/authentication.adoc[]
include::operations/books-get.adoc[]
```

Then `operations/books-get.adoc` contains snippet includes:

```asciidoc
== Get book by ID

include::../../../../build/generated-snippets/books-get/http-request.adoc[]
include::../../../../build/generated-snippets/books-get/http-response.adoc[]
```

Here `books-get.adoc` is in `src/docs/asciidoc/operations/`; you need to go up four levels to return to the project root and then into `build/generated-snippets`. This path differs from the path used in `index.adoc` because the two files are in different directories.

If using the `snippets` attribute, includes in the operation file can be shorter:

```asciidoc
include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/http-response.adoc[]
```

When a file is included into another document, includes inside the included file must be verified relative to the location of the file currently containing that macro. Do not only check the path from `index.adoc` and assume all nested includes are valid.

## 6. Comparing Relative Paths and Absolute Paths

| Declaration style | Example | Advantages | Risks |
| --- | --- | --- | --- |
| Direct relative | `../../build/generated-snippets/books-get/http-request.adoc` | No attribute needed; relative location is explicit. | Error-prone when moving files or changing folder structure. |
| Relative via attribute | `{snippets}/books-get/http-request.adoc` with `:snippets: ../../build/generated-snippets` | Short includes, easy to change in one place. | Requires understanding where the attribute is declared and its resolution context. |
| Absolute | `/workspace/project/build/generated-snippets/...` | May work reliably on one specific machine. | Not portable across developers, CI agents, and operating systems. |
| Build-provided attribute | `{snippets}/books-get/http-request.adoc` | Build decides the output directory; CI-friendly. | Plugin/extension must be configured accurately. |

Normally, you should use the `snippets` attribute provided by the Spring REST Docs/Asciidoctor integration or passed from the build. Direct relative paths are suitable when the documentation is small and the structure is stable. Avoid committing absolute paths from a personal machine.

## 7. Configuring the Path with Gradle Instead of Hard-Coding in Source Files

Gradle example:

```groovy
plugins {
    id 'java'
    id 'org.asciidoctor.jvm.convert' version '3.3.2'
}

configurations {
    asciidoctorExt
}

def snippetsDir = layout.buildDirectory.dir('generated-snippets')

dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

tasks.named('test') {
    outputs.dir snippetsDir
    useJUnitPlatform()
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    configurations 'asciidoctorExt'
    attributes 'snippets': snippetsDir.get().asFile
}
```

With this configuration, the source file only needs:

```asciidoc
include::{snippets}/books-get/http-request.adoc[]
```

The build provides the path computed from the Gradle layout instead of forcing `.adoc` files to know where the project root is. Keep the output directory where Spring REST Docs tests actually write synchronized with this `snippetsDir`. If the Spring REST Docs extension sets the `snippets` attribute automatically, inspect the plugin configuration/version and avoid setting two conflicting values.

## 8. Maven Configuration and `target/generated-snippets`

With Maven, the default output is usually `target/generated-snippets`. If the source document is at `src/docs/asciidoc/index.adoc`, the direct relative path to snippets is:

```asciidoc
:snippets: ../../target/generated-snippets

include::{snippets}/books-get/http-request.adoc[]
```

When configuring `spring-restdocs-asciidoctor` in the Asciidoctor Maven Plugin, the extension can provide the `snippets` attribute according to the Maven convention. If the plugin does not pick up the extension or uses a custom output path, assign the attribute via plugin configuration, for example:

```xml
<attributes>
    <snippets>${project.build.directory}/generated-snippets</snippets>
</attributes>
```

Ensure tests run before the documentation authoring phase and write to `target/generated-snippets`. With multi-module Maven builds, pay attention to which module generates the snippets and which module runs Asciidoctor; the path may need to point to the test module's output instead of the docs module's `target`.

## 9. Notes When Using Paths on Windows and Linux

AsciiDoc include paths should use `/` to keep the syntax portable:

```asciidoc
include::{snippets}/books-get/http-request.adoc[]
```

Avoid writing Windows-style backslashes:

```asciidoc
// Not recommended
include::..\..\build\generated-snippets\books-get\http-request.adoc[]
```

Things to check:

- **Case sensitivity:** Linux typically distinguishes `Books-Get` from `books-get`; Windows may not. Identifiers and included filenames must match exactly.
- **Spaces in paths:** can cause macros or attributes to be parsed unexpectedly; prefer folder names without spaces. If you must use them, follow the quoting/escaping syntax supported by Asciidoctor and verify with an actual build.
- **Unicode characters:** accented filenames may work, but identifier-generated snippet names should use stable ASCII to avoid filesystem differences.
- **Absolute paths:** do not embed `C:\Users\...` or `/home/...` in source files.
- **Separator:** use `/` even when building on Windows.

## 10. Safe Includes and Path Restrictions

Asciidoctor has safe modes that control includes and file access. When building documentation, `safe`/`secure` mode or plugin configuration may restrict include paths to within `base_dir` or an allowed region. Consequently, an include that works locally may be rejected in CI if snippets lie outside the allowed area.

When encountering safe-mode errors:

1. Check the Asciidoctor log to see whether the include path is blocked or the file genuinely does not exist.
2. Verify `base_dir` and the document root directory used by the plugin.
3. Place generated snippets within the allowed build area or configure the plugin/base directory safely.
4. Only relax safe mode when you understand the impact and control the document sources; do not disable restrictions arbitrarily.

Do not use include paths taken directly from external or user-provided data. Documents and snippets should be artifacts controlled by the repository/build.

## 11. How to Diagnose a Missing Include

When Asciidoctor reports `include file not found`, proceed step by step:

1. Open the snippets directory to confirm the file actually exists after tests run.
2. Check whether the identifier in `document("books-get", ...)` matches the `books-get` directory.
3. Check whether the snippet name, such as `http-request.adoc`, matches the exact generated file.
4. Identify which directory holds the `.adoc` file containing `include::`.
5. Calculate the relative path from that exact location; do not calculate from the project root out of habit.
6. Check the final value of `{snippets}` and whether the plugin/extension is loaded.
7. Check `base_dir` and safe mode if the path exists yet is still rejected.
8. Run a clean build to rule out stale snippets or ungenerated output.

Comparison example:

```text
File include:
  src/docs/asciidoc/index.adoc

Snippet:
  build/generated-snippets/books-get/http-request.adoc

Relative path:
  ../../build/generated-snippets/books-get/http-request.adoc
```

If the include file is moved to `src/docs/asciidoc/operations/books-get.adoc`, the direct path changes to `../../../../build/...`; whereas if using a properly configured `snippets` attribute, the macro content does not need to change.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `include file not found` | Relative path calculated incorrectly or snippet file not yet generated. | Identify the location of the file containing the macro and inspect current output. |
| Include works on developer machine but fails in CI | Using an absolute path or different working directory. | Use a build-provided attribute and portable paths. |
| File is in `build/generated-snippets` but Asciidoctor searches in `src/docs/...` | Attribute is not configured or path is declared incorrectly. | Check the `spring-restdocs-asciidoctor` extension and the `{snippets}` value. |
| Include in an operation file fails | Using a path calculated from index instead of the operation file containing the macro. | Recalculate relative to the current file location or use the root attribute. |
| Works on Windows but fails on Linux | Case mismatch or separator difference. | Match filename case exactly and use `/`. |
| Include path blocked by safe mode | Snippet lies outside the allowed base directory region. | Arrange output/base directory or configure safe mode in a controlled way. |
| Included file is empty or stale | Tests did not run, failed, or output was not cleaned. | Run tests cleanly to pass before rendering. |
| Using `operation::` does not work | Missing Spring REST Docs Asciidoctor extension. | Add `spring-restdocs-asciidoctor` to the proper plugin/configuration. |

## 13. Practice Checklist

- [ ] Identified which `.adoc` file contains `include::`.
- [ ] Identified exactly where tests write snippets.
- [ ] If using direct paths, calculated relative to the directory of the including file.
- [ ] If using `{snippets}`, the attribute is properly configured in the file or build.
- [ ] Operation identifier and snippet name match actual files.
- [ ] Nested includes verified in each source file.
- [ ] Used `/`, matched case, and avoided personal-machine absolute paths.
- [ ] Checked `base_dir`/safe mode if includes are rejected.
- [ ] Build runs HTTP tests before Asciidoctor and uses snippets from the current build.
- [ ] Final HTML/PDF renders successfully with all request, response, and descriptor snippets.

Relative paths help Spring REST Docs documentation work across machines without depending on a personal workspace. Identify where the AsciiDoc file resides, where snippets are generated, and the Asciidoctor context used to resolve includes. For projects with many operations or multi-level source files, using the build-configured `{snippets}` attribute is usually easier to maintain than repeating multiple `../` levels in every include.

## References

- [Asciidoctor – Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/)
- [Asciidoctor – Document Attributes](https://docs.asciidoctor.org/asciidoc/latest/attributes/document-attributes/)
- [Asciidoctor – Safe Modes](https://docs.asciidoctor.org/asciidoc/latest/safe-modes/)
- [Spring REST Docs – Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html)
- [Spring REST Docs – Reference Documentation](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
