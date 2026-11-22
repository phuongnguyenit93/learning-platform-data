# Controlled DocLint Suppression in Javadoc

## 1. What Is DocLint?

**DocLint** is the documentation comment quality checker used by the **javadoc** tool when generating API documentation. It detects issues such as malformed HTML, links to nonexistent symbols, invalid Javadoc syntax, and missing required documentation sections.

Example:

~~~java
/**
 * Adds two numbers.
 * @param left first value
 * @param right second value
 * @return the sum
 */
public int add(int left, int right) {
    return left + right;
}
~~~

DocLint checks both the content inside comments and certain documentation requirements attached to Java declarations. As a result, Javadoc can catch errors before HTML documentation is published.

In legacy projects, there may be many incomplete comments or legacy HTML that is no longer valid. When you need to keep the build running while gradually fixing documentation, you can disable a check group or limit the suppression to a specific package.

The goal of **controlled DocLint suppression** is to target the exact check causing the block, keep valuable checks active, and make the scope of exempted sources explicit.

## 2. DocLint Belongs to javadoc, Not javac

It is important to distinguish the two tools:

| Tool | Role |
|---|---|
| javac | Compiles Java source into bytecode and checks language errors, data types, symbols, and compilation conditions. |
| javadoc | Reads source and documentation comments to generate HTML API documentation; DocLint checks comments during this process. |

For example, the command:

~~~bash
javac --release 17 -d out src/demo/Calculator.java
~~~

compiles the source. DocLint options are not a way to disable `javac` type checking or Java syntax errors.

The command:

~~~bash
javadoc -d docs src/demo/Calculator.java
~~~

generates HTML documentation and performs the corresponding documentation checks.

If `javadoc` fails due to a broken link, invalid HTML, or missing documentation tags, changing `javac` options will not address the root cause. You need to adjust `javadoc` options or fix the documentation comment.

## 3. DocLint Check Groups

Modern JDKs provide the following check groups:

| Group | Content |
|---|---|
| accessibility | Checks certain accessibility issues in the HTML content of the documentation. |
| html | Checks HTML tags, attributes, and HTML structure in documentation comments. |
| missing | Checks for missing documentation comments or required documentation tags, such as `@param` and `@return`. |
| reference | Checks references such as `@see`, `{@link}`, `{@linkplain}`, `{@value}`, and links to types/members. |
| syntax | Checks Javadoc syntax, including inline tags and invalid tags. |

The **all** keyword represents all check groups. The **none** keyword disables DocLint groups.

An HTML error such as an unclosed tag may be reported under the `html` group. A reference to a nonexistent class belongs to the `reference` group. A method missing `@return` or `@param` belongs to the `missing` group.

Distinguishing groups helps avoid disabling all of DocLint when only one category of comments needs to be addressed.

## 4. DocLint Control Syntax

DocLint options are passed directly to `javadoc`:

~~~bash
-Xdoclint
-Xdoclint:all
-Xdoclint:none
-Xdoclint:<group>
-Xdoclint:all,-<group>
~~~

Meaning:

- **-Xdoclint:** enables the recommended checks.
- **-Xdoclint:all:** enables all check groups.
- **-Xdoclint:none:** disables all DocLint check groups.
- **-Xdoclint:html:** enables only the `html` group.
- **-Xdoclint:all,-missing:** enables all groups except `missing`.
- **-Xdoclint:all,-reference:** enables all groups except `reference`.

Multiple groups can be selected, separated by commas:

~~~bash
javadoc -Xdoclint:html,syntax -d docs src/demo/Calculator.java
~~~

The command above enables only HTML and Javadoc syntax checks during that documentation run.

To keep most checks while temporarily skipping reference checks:

~~~bash
javadoc -Xdoclint:all,-reference -d docs src/demo/Calculator.java
~~~

A minus sign before a group name disables that group within the selected check set. Group syntax can be combined with the package-scoping option covered later.

Options starting with `-X` are extended options, not a standard interface guaranteed to remain stable long-term. Check **javadoc -X** on the exact JDK used for the build.

## 5. Disabling Only the missing Group

A common scenario is legacy source that does not yet have complete `@param`, `@return`, or documentation comments for every public API. If HTML and references are already in good shape, you can disable only the `missing` group:

~~~bash
javadoc -Xdoclint:all,-missing -d docs src/demo/api/Calculator.java
~~~

This keeps the following checks active:

- HTML.
- Reference.
- Syntax.
- Accessibility.

Only the `missing` group is excluded from that check run.

Example source:

~~~java
package demo.api;

/**
 * Performs a calculation.
 */
public class Calculator {
    /**
     * Adds two numbers.
     */
    public int add(int left, int right) {
        return left + right;
    }
}
~~~

The `add` method does not yet have `@param` and `@return`. With `-Xdoclint:all,-missing`, Javadoc can generate documentation without emitting `missing`-group warnings for this method; the remaining check groups still run.

Verification command:

~~~bash
javadoc -Xdoclint:all,-missing -d docs src/demo/api/Calculator.java
~~~

Verification result with JDK 24.0.2: the command finishes with exit code 0 and generates `docs/demo/api/Calculator.html`.

This is a suitable option when a team is adding documentation incrementally while still wanting to maintain HTML, reference, and syntax checks.

You should not permanently disable `missing` by default for the entire API. `@param`, `@return`, and `@throws` tags help users understand a method's contract, especially for public libraries.

## 6. Disabling DocLint for a Specific Package

If only one legacy package has non-compliant comments, you can limit the suppression scope using the package option:

~~~bash
-Xdoclint/package:<packages>
~~~

To disable DocLint for the **com.example.legacy** package:

~~~bash
javadoc -Xdoclint:all \
    -Xdoclint/package:-com.example.legacy \
    -d docs \
    src/com/example/legacy/LegacyApi.java
~~~

A minus sign before the package name disables checks for that package. Other packages in the same run can still be fully checked.

Example legacy source with old HTML:

~~~java
package com.example.legacy;

/**
 * <p>Old documentation with <b>an unclosed tag.
 * @see MissingType
 */
public class LegacyApi {
    /**
     * Returns a value.
     */
    public String value() {
        return "ok";
    }
}
~~~

Package-scoped suppression command:

~~~bash
javadoc -Xdoclint:all \
    -Xdoclint/package:-com.example.legacy \
    -d docs \
    src/com/example/legacy/LegacyApi.java
~~~

With JDK 24.0.2, testing package suppression successfully generates HTML and exits with code 0 even though comments in the package contain DocLint errors.

If you want to apply it to subpackages, use a package prefix with **.* **:

~~~bash
-Xdoclint/package:-com.example.legacy.*
~~~

To specify packages where checks should be enabled, omit the minus sign:

~~~bash
-Xdoclint/package:com.example.api.*
~~~

Package names must be fully qualified. The package filter applies only to packages included in that `javadoc` run; it does not replace selecting the input sources/packages.

## 7. Disabling All of DocLint with -Xdoclint:none

When you need to generate temporary documentation from legacy source that has too many issues, you can disable all DocLint groups:

~~~bash
javadoc -Xdoclint:none -d docs src/com/example/legacy/LegacyApi.java
~~~

This option disables DocLint checks for accessibility, HTML, missing, reference, and syntax.

It should only be used in clearly scoped cases, such as:

- Generating temporary documentation for migration purposes.
- Producing internal artifacts while fixing a large volume of legacy Javadoc.
- Separating documentation generation from quality checks in a time-boxed transition pipeline.

**-Xdoclint:none does not disable every javadoc diagnostic.** Javadoc may still report warnings or errors belonging to other mechanisms. For example, testing on JDK 24.0.2 shows that an unfound reference can still be reported as a warning when DocLint is disabled.

This option also does not ignore source reading errors, option errors, doclet errors, or errors required to generate documentation. Therefore, you must not assume that using `-Xdoclint:none` guarantees every Javadoc generation run will succeed.

If you only need to skip warnings for missing `@param`/`@return`, choose `-Xdoclint:all,-missing`. If only one legacy package has issues, use package-scoped suppression. Use `-Xdoclint:none` only when you genuinely need to skip all of DocLint within a defined build scope.

## 8. Do Not Confuse DocLint Suppression with Other Options

Some `javadoc` options appear related to warnings or output but do not have the same effect:

| Option | Actual Effect |
|---|---|
| -Xdoclint:none | Disables DocLint check groups. |
| -Xdoclint:all,-missing | Disables only the `missing` group and keeps the other groups. |
| -quiet | Suppresses `javadoc` status messages; diagnostics may still appear. |
| -Werror | Fails with an error if there are warnings; does not disable checks. |
| -Xmaxwarns <number> | Limits the number of printed warnings; does not eliminate warnings in source. |
| -Xmaxerrs <number> | Limits the number of printed errors; does not fix or disable the root cause. |

Example:

~~~bash
javadoc -quiet -d docs src/demo/api/Calculator.java
~~~

`-quiet` only reduces progress messages such as loading sources or generating pages. It is not a command to disable DocLint.

If you use `-Werror`:

~~~bash
javadoc -Xdoclint:none -Werror -d docs src/demo/api/Calculator.java
~~~

remaining warnings from other mechanisms can still cause the command to fail. You should read the actual diagnostics instead of adding `-quiet` or increasing warning limits to hide the issue.

## 9. Example DocLint Policy Configuration for API and Legacy

Suppose a project has two source areas:

~~~text
src/
├── com/example/api/
│   └── Calculator.java
└── com/example/legacy/
    └── LegacyApi.java
~~~

Desired policy:

- The new API must comply with all DocLint groups.
- The legacy package is temporarily exempted from DocLint.
- Remaining packages are still checked.

You can run:

~~~bash
javadoc -Xdoclint:all \
    -Xdoclint/package:-com.example.legacy \
    -d docs \
    src/com/example/api/Calculator.java \
    src/com/example/legacy/LegacyApi.java
~~~

When running with multiple source files, make sure the package names in the source match the package filter. Do not add overly broad filters like **-com.example.*** when you only want to exempt one small package.

If the new API only lacks descriptive tags while other groups still need to be checked, another policy is:

~~~bash
javadoc -Xdoclint:all,-missing \
    -d docs \
    src/com/example/api/Calculator.java
~~~

The two approaches solve different problems: one scopes by package, while the other scopes by check type. Choose the narrowest approach that matches the actual cause.

## 10. Using Option Files and Build Tool Integration

When a `javadoc` command becomes long, you can place options in an argument file.

File **javadoc.options**:

~~~text
-Xdoclint:all,-missing
-encoding
UTF-8
-d
docs
src/demo/api/Calculator.java
~~~

Run:

~~~bash
javadoc @javadoc.options
~~~

Javadoc reads options and filenames from the argument file. This makes it easy to store configuration with the project, review changes, and avoid repeating long commands in CI.

### Maven

With `maven-javadoc-plugin`, pass DocLint options through the plugin's additional options configuration. Example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <configuration>
        <additionalOptions>
            <additionalOption>-Xdoclint:all,-missing</additionalOption>
        </additionalOptions>
    </configuration>
</plugin>
~~~

Parameter names and how options are forwarded depend on the plugin version. After configuring, run the Javadoc goal and inspect the actual logs to confirm the option was passed to `javadoc`.

### Gradle

With the Gradle Javadoc task, you can add options to `StandardJavadocDocletOptions`:

~~~groovy
tasks.withType(Javadoc).configureEach {
    options.addBooleanOption('Xdoclint:all,-missing', true)
}
~~~

Check the Gradle version and JDK toolchain used by the task. The JDK running the Gradle daemon and the JDK selected for the Javadoc task may differ.

Do not configure DocLint across multiple layers without knowing which option takes effect. Keep a single primary source of configuration for local builds and CI, and inspect the task's command line when diagnosing issues.

## 11. Combining DocLint with Classpath and Module Path

Some reference diagnostics occur because `javadoc` cannot find a required dependency or module. Before disabling the `reference` group, verify the symbol resolution environment.

With libraries on the classpath:

~~~bash
javadoc \
    -classpath "lib/api-dependency.jar" \
    -Xdoclint:all \
    -d docs \
    src/com/example/api/Service.java
~~~

With modules:

~~~bash
javadoc \
    --module-path mods \
    --module com.example.api \
    -Xdoclint:all \
    -d docs
~~~

If a reference points to an existing type that `javadoc` cannot find, check the classpath, module path, source path, and modules passed to the command. Disabling `reference` may let the build continue, but the generated documentation will still have missing or inaccurate links.

For links to external API documentation, check options such as `-link` or `-linkoffline` and the corresponding URLs/package lists. Do not disable `reference` just because external documentation is misconfigured.

## 12. Diagnostics, Exit Codes, and -Werror

DocLint may report errors or warnings depending on the issue type and JDK version. A severe HTML error or unresolvable reference can cause `javadoc` to exit with a non-zero exit code. Some documentation omissions may be reported as warnings.

You can instruct `javadoc` to treat all warnings as errors:

~~~bash
javadoc -Xdoclint:all -Werror -d docs src/demo/api/Calculator.java
~~~

This is a strict policy suited for APIs with standardized documentation. If migrating legacy code, you can temporarily use a specific group suppression and remove it once migration is complete.

In CI, you should record:

- JDK version and `javadoc` version.
- Enabled/disabled DocLint groups.
- Exempted packages, if any.
- The first warning/error and the related source line.
- The `javadoc` exit code.
- Generated HTML directory and published artifacts.

Do not rely solely on whether the `docs` directory exists. Javadoc can generate partial HTML and still exit with an error. The exit code and diagnostics are the key evidence to determine whether the build succeeded.

## 13. Controlled DocLint Handling Workflow

When encountering DocLint errors in a project, proceed in this order:

1. Re-run `javadoc` with sufficiently detailed logs to identify the file, line, and diagnostic type.
2. Classify the issue into `html`, `reference`, `missing`, `syntax`, or `accessibility`.
3. Check whether the error is caused by source comments or by a missing classpath/module path.
4. If possible, fix the comment or reference directly.
5. If migration is needed, select the smallest group using `-Xdoclint:all,-group`.
6. If only one legacy package has issues, limit suppression with `-Xdoclint/package:-package.name`.
7. Use `-Xdoclint:none` only when there is a valid reason to disable all of DocLint in a specific build.
8. Document the scope, owner, and timeline for removing the suppression.
9. Re-run Javadoc on the new API to confirm the remaining check groups still work.
10. Once migration is complete, remove the suppression and re-enable `-Xdoclint:all`.

A good suppression should answer three questions: why it needs to be disabled, the exact scope being disabled, and the condition for re-enabling it. This prevents temporary workarounds from becoming permanent policy.

## 14. Common Mistakes When Disabling DocLint

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `-Xdoclint:none` is set, yet warnings still appear | Warning does not belong to DocLint, e.g., Javadoc's own reference diagnostic. | Read the diagnostic category and address its specific cause. |
| `-Xdoclint:all,-missing` still reports HTML errors | Only the `missing` group is disabled; the `html` group is still active. | Fix the HTML or consider another narrow suppression if justified. |
| Legacy package is still checked | Package filter name does not match the package in source, or the filter is too narrow. | Check the fully qualified package name and use `.*` for subpackages when needed. |
| No more `@param`/`@return` warnings | The `missing` group has been disabled. | Add the documentation tags and re-enable the `missing` group. |
| Javadoc cannot find a class in `@see` | Classpath/module path or source path is incorrect. | Configure dependencies and external links before disabling `reference`. |
| `-quiet` still shows errors | `-quiet` only hides status messages. | Use the appropriate DocLint group option; do not use `quiet` as a substitute. |
| `-Werror` still fails the build | Warnings remain from enabled groups or from other Javadoc checks. | Resolve the remaining warnings or adjust the policy in a controlled way. |
| Local build succeeds but CI fails | Different JDK/plugin/toolchain or DocLint options. | Synchronize the JDK version and options in the build configuration. |
| Other packages are also exempted from checks | Package prefix is too broad. | Restrict the filter to the exact legacy package. |
| Generated documentation has missing links | Reference checks were disabled or external docs were not configured. | Restore reference checks and configure classpath/links properly. |

## 15. Checklist Before Disabling DocLint

- [ ] Identified which DocLint group the diagnostic belongs to.
- [ ] Distinguished Javadoc errors from `javac` compilation errors.
- [ ] Checked classpath, module path, and external documentation links.
- [ ] Prioritized fixing documentation comments where possible.
- [ ] Selected the exact group to disable using `-Xdoclint:all,-group`.
- [ ] Scoped by package if the issue is confined to legacy code.
- [ ] Understood that `-Xdoclint:none` only disables DocLint, not all Javadoc diagnostics.
- [ ] Avoided using `-quiet` or `-Xmaxwarns` as a way to disable checks.
- [ ] Considered the impact of `-Werror` on remaining warnings.
- [ ] Verified options on the exact JDK version used by local builds and CI.
- [ ] Documented the reason and condition for re-enabling checks.
- [ ] Planned to remove the suppression after migration is complete.

Controlled DocLint suppression allows a project to continue generating Javadoc while addressing legacy documentation. By selecting the right group or package, keeping remaining checks active, and monitoring exit codes, a team can reduce migration friction while still protecting API documentation quality.