# Scanning Multiple Artifacts with `jdeprscan`

`jdeprscan` is a JDK tool for scanning Java bytecode and finding references to deprecated Java SE APIs. It accepts a directory containing a package tree, a JAR file, a `.class` file, or a fully qualified class name as input. You can pass **multiple targets in a single command**, allowing you to check application JARs, plugins, and compiled class directories simultaneously.

Scanning multiple artifacts is useful when a product is assembled from multiple modules or internal libraries. A single run can help detect legacy APIs inside each component before upgrading the JDK, changing the Java baseline, or shipping a new release.

Three things must be distinguished:

- **Target to scan:** the artifact placed directly at the end of the `jdeprscan` command.
- **Dependency class path:** the path that helps the tool locate classes referenced by the target; specified with `--class-path`.
- **API release:** the Java SE version used as the deprecated API dataset; selected with `--release`.

`--class-path` does not automatically turn every JAR on the class path into a scan target. To check an artifact, you must pass that artifact as a target argument.

The toolchain used to verify this guide is `jdeprscan 24.0.2`. Syntax and supported releases may vary across JDKs; check `jdeprscan --help` in your actual build environment.

## 1. What types of input can `jdeprscan` scan?

According to the JDK 24.0.2 help output, each target argument can be:

| Input type | Example | Meaning |
|---|---|---|
| Directory | `build/classes` | Root of a compiled package tree |
| JAR | `build/libs/service.jar` | Classes contained in an archive |
| Class file | `build/classes/com/acme/LegacyAdapter.class` | A specific bytecode file |
| Fully qualified class name | `com.acme.LegacyAdapter` | Class resolved via the search environment |
| Nested class | `com.acme.Outer$Inner` | Nested class name using the `$` character |

General syntax:

~~~text
jdeprscan [options] {dir|jar|class} ...
~~~

The `...` indicates that multiple targets can be passed:

~~~text
jdeprscan --release 17 build/app.jar build/plugin-a.jar build/plugin-b.jar build/classes
~~~

The command above scans all three JARs and the `build/classes` tree in a single run. Paths containing spaces must be quoted according to shell rules.

`jdeprscan` analyzes compiled bytecode. It does not read `.java` files to find calls in source code. If the source has recently changed, recompile before scanning so the report reflects the bytecode about to be released.

## 2. Why scan multiple artifacts?

A Java application typically consists of multiple components:

~~~text
application/
  app.jar
  plugins/
    billing-plugin.jar
    report-plugin.jar
  libs/
    company-api.jar
    common-utils.jar
  classes/
    com/acme/internal/
~~~

If you only scan `app.jar`, deprecated calls inside plugins or internal libraries may be missed. List the artifacts within the release scope and pass each target to the command.

Cases where scanning multiple artifacts is recommended:

- The application consists of multiple JARs developed by different teams.
- Plugins are loaded at runtime.
- Multiple modules are built into independent JARs.
- There are class directories not yet packaged into JARs.
- All outputs need to be checked before a JDK upgrade.
- Deprecated API usage needs to be compared across releases.

Include only the artifacts that actually need to be checked. You should usually exclude source JARs, Javadoc JARs, test fixtures, or intermediate artifacts that are not distributed, unless they are also within the check scope.

## 3. Scanning multiple JARs in one command

Example on Windows PowerShell:

~~~powershell
jdeprscan --release 17 `
    .\build\app.jar `
    .\build\plugins\billing-plugin.jar `
    .\build\plugins\report-plugin.jar `
    .\build\classes
~~~

On macOS/Linux:

~~~sh
jdeprscan --release 17 \
    build/app.jar \
    build/plugins/billing-plugin.jar \
    build/plugins/report-plugin.jar \
    build/classes
~~~

In both examples, each path after the options is a separate target. There is no need to run a separate `jdeprscan` process for each JAR if the number of targets is moderate.

To add dependencies for resolving referenced classes, use `--class-path`:

Windows:

~~~powershell
jdeprscan --release 17 `
    --class-path ".\libs\company-api.jar;.\libs\common-utils.jar" `
    .\build\app.jar `
    .\build\plugins\billing-plugin.jar `
    .\build\plugins\report-plugin.jar
~~~

macOS/Linux:

~~~sh
jdeprscan --release 17 \
    --class-path "libs/company-api.jar:libs/common-utils.jar" \
    build/app.jar \
    build/plugins/billing-plugin.jar \
    build/plugins/report-plugin.jar
~~~

The class path element separator is `;` on Windows and `:` on macOS/Linux. Wrap the entire class path in quotes so the shell does not interpret the separator as its own syntax.

## 4. Distinguishing targets from the dependency class path

This is the most important point when scanning multiple artifacts:

~~~text
jdeprscan --release 17 --class-path "libs/api.jar;libs/util.jar" app.jar plugin.jar
~~~

- `app.jar` and `plugin.jar` are the two targets being scanned.
- `libs/api.jar` and `libs/util.jar` are provided to resolve dependent classes.
- If you also want to scan `api.jar` and `util.jar`, add them to the target list.

Example:

~~~text
jdeprscan --release 17 --class-path "libs/api.jar;libs/util.jar" app.jar plugin.jar libs/api.jar libs/util.jar
~~~

If dependencies are missing, the tool may fail to resolve some classes or emit additional diagnostics. In that case, the report may be incomplete. Provide the necessary dependencies on the class path while ensuring each artifact to be checked is listed as a target.

Do not use the class path as a substitute for the artifact list. Placing a JAR in `--class-path` only supports class lookup; do not assume that JAR has been scanned.

## 5. Automatically scanning all JARs in a directory with PowerShell

When a build produces many JARs, you can gather the list with `Get-ChildItem` and pass the entire array to `jdeprscan`.

~~~powershell
$targets = @(
    Get-ChildItem .\build\libs -Filter *.jar -File -Recurse |
        Where-Object {
            $_.Name -notlike '*-sources.jar' -and
            $_.Name -notlike '*-javadoc.jar'
        } |
        ForEach-Object { $_.FullName }
)

if ($targets.Count -eq 0) {
    throw "No application JAR files were found."
}

& jdeprscan --release 17 @targets

if ($LASTEXITCODE -ne 0) {
    throw "jdeprscan failed with exit code $LASTEXITCODE"
}
~~~

Explanation:

- `Get-ChildItem -Recurse` searches for JARs across the entire build directory.
- `-File` selects only files, excluding directories.
- The filter excludes `-sources.jar` and `-javadoc.jar`.
- `@targets` passes each path in the array as a separate argument.
- `$LASTEXITCODE` checks the native process exit status after execution.

If the targets have dependencies outside the JDK, add `--class-path` before `@targets`. Verify that the class path includes all required dependencies and uses `;` between paths on Windows.

## 6. Batching when there are many artifacts

A single command with too many paths can hit the operating system's command-line length limit. When that happens, split the list into smaller batches. Each batch still scans multiple artifacts in a single process.

PowerShell example, up to 25 JARs per batch:

~~~powershell
$targets = @(
    Get-ChildItem .\build\libs -Filter *.jar -File -Recurse |
        Where-Object {
            $_.Name -notlike '*-sources.jar' -and
            $_.Name -notlike '*-javadoc.jar'
        } |
        ForEach-Object { $_.FullName }
)

if ($targets.Count -eq 0) {
    throw "No application JAR files were found."
}

$batchSize = 25

for ($i = 0; $i -lt $targets.Count; $i += $batchSize) {
    $end = [Math]::Min($i + $batchSize - 1, $targets.Count - 1)
    $batch = @($targets[$i..$end])

    Write-Host "Scanning artifacts $($i + 1) to $($end + 1)..."

    & jdeprscan --release 17 @batch

    if ($LASTEXITCODE -ne 0) {
        throw "jdeprscan failed for batch starting at index $i"
    }
}
~~~

If there is a dependency class path, add `--class-path $dependencyPath` to each invocation. Choose the batch size based on path lengths and the command-line limit of your CI environment.

With batching, save the report along with the corresponding target list. If you need to identify which artifact a finding belongs to, scan that artifact individually after the combined scan or use `--verbose` to aid investigation. Verbose mode can print a very large amount of output.

## 7. Scanning multiple JARs with Bash

Bash example on macOS/Linux, finding JARs and passing them via an array to preserve paths with spaces:

~~~bash
targets=()

while IFS= read -r -d '' target; do
    targets+=("$target")
done < <(
    find build/libs -type f -name '*.jar' \
        ! -name '*-sources.jar' \
        ! -name '*-javadoc.jar' \
        -print0
)

if [ "${#targets[@]}" -eq 0 ]; then
    echo "No application JAR files were found." >&2
    exit 2
fi

jdeprscan --release 17 "${targets[@]}"
scan_status=$?

if [ "$scan_status" -ne 0 ]; then
    echo "jdeprscan failed with exit code $scan_status" >&2
    exit "$scan_status"
fi
~~~

A Bash array keeps each path as a separate argument. This avoids errors when filenames contain spaces or special characters.

If the number of targets is large, you can split the array into batches:

~~~bash
batch_size=25

for ((i = 0; i < ${#targets[@]}; i += batch_size)); do
    batch=("${targets[@]:i:batch_size}")

    echo "Scanning artifacts $((i + 1)) to $((i + ${#batch[@]}))..."

    jdeprscan --release 17 "${batch[@]}" || exit $?
done
~~~

If a class path is needed, add `--class-path 'libs/api.jar:libs/util.jar'` to the command inside the loop. On macOS/Linux, `:` separates class path elements.

## 8. Choosing the right `--release`

The `--release` option specifies the Java SE version that provides the deprecated API set to check against. It is not a compile option and does not modify the artifact's bytecode.

Example:

~~~text
jdeprscan --release 17 app.jar plugin.jar
~~~

The command above checks deprecated API usage against the Java SE 17 API set.

When a product supports multiple Java releases, rerun for each supported baseline:

~~~text
jdeprscan --release 17 app.jar plugin.jar
jdeprscan --release 21 app.jar plugin.jar
jdeprscan --release 24 app.jar plugin.jar
~~~

Each run takes only one `--release` value. Do not combine multiple releases into a single invocation. Keep the artifact list identical across runs so reports can be compared.

In the tested JDK 24.0.2, the help lists releases from 8 to 24. Other JDKs may support a different set of releases. Check the help of the exact JDK used in CI.

If the application must run on Java 17 while you are evaluating an upgrade plan to Java 21, generate separate reports for each target release. That way the team can distinguish APIs already deprecated in the current baseline from APIs deprecated in the newer release.

## 9. Finding only APIs deprecated for removal

`--for-removal` restricts results to APIs marked deprecated for removal in the selected release:

~~~text
jdeprscan --release 17 --for-removal app.jar plugin.jar
~~~

This mode is useful for prioritizing upgrade risks. Ordinary deprecated APIs may remain for a long time; `for removal` APIs signal potential removal in a future release and need to be addressed early.

Distinction:

- Without `--for-removal`: scans deprecated APIs in the selected release set.
- With `--for-removal`: scans only the APIs marked for removal.
- `--for-removal` does not mean the artifact is being deleted or the package is being removed.

According to the JDK 24.0.2 help, `--for-removal` cannot be combined with `--release 6`, `7`, or `8`. For release 8, omit `--for-removal` or use an appropriate release supported by the toolchain.

You can generate two separate reports for the same set of artifacts: a full report and a prioritized `for removal` API report.

## 10. Using `--list` to view the deprecated API list

`--list` prints the set of deprecated APIs known to the tool for the selected release:

~~~text
jdeprscan --list --release 17
~~~

This is an API listing operation, not an artifact scan. Do not pass a directory, JAR, class file, or class name when using `--list`.

You can use this list to look up API names and confirm whether an API belongs to the release set being checked. The list can be long; in CI, save it to a file if you need to look up or compare entries.

PowerShell example:

~~~powershell
jdeprscan --list --release 17 |
    Set-Content -Encoding UTF8 .\build\deprecated-java-se-17.txt
~~~

macOS/Linux example:

~~~sh
jdeprscan --list --release 17 > build/deprecated-java-se-17.txt
~~~

Do not confuse `--list` with a scan command. To find where the application uses APIs, run the command with target artifacts and without `--list`.

## 11. Understanding the scan report

A test run on JDK 24.0.2:

~~~text
jdeprscan --release 17 java.lang.Thread java.util.Date
~~~

Output:

~~~text
class java/util/Date uses deprecated method java/util/Date::<init>(IIIIII)V
class java/util/Date uses deprecated method java/util/Date::parse(Ljava/lang/String;)J
~~~

In this run, two target classes were passed in the same command; findings appeared in `java.util.Date`. Each report line indicates the class using the deprecated API and the referenced member.

Several types of information can appear:

- A class uses a deprecated class or interface.
- A method calls a deprecated method.
- A deprecated field is read or written.
- A deprecated constructor is called.

The signature part may use JVM descriptors. For example:

- `I` represents the `int` type.
- `J` represents the `long` type.
- `V` represents the `void` return type.
- `Ljava/lang/String;` represents `java.lang.String`.
- `IIIIII` represents six `int` parameters.

Not every report includes source line numbers. `jdeprscan` analyzes bytecode, so use the class/member name to trace back to the source, locate the call site, and identify the module that owns the code.

## 12. Exit code 0 does not mean zero deprecated usages

An important point for CI integration: `jdeprscan` can return exit code `0` even after printing lines of deprecated API usage.

In the test in the previous section, the command:

~~~text
jdeprscan --release 17 java.lang.Thread java.util.Date
~~~

printed two findings, yet the process still exited with code `0`. Therefore, checking only `$LASTEXITCODE` or `$?` is not enough to enforce a “no deprecated usage” quality gate.

You need to check two things separately:

1. **Tool execution:** whether the process ran successfully and could read the targets.
2. **Scan findings:** whether the report contains lines indicating deprecated API usage.

PowerShell example for a batch:

~~~powershell
$report = & jdeprscan --release 17 @targets 2>&1
$scanExitCode = $LASTEXITCODE

$report | Set-Content -Encoding UTF8 .\build\jdeprscan-report.txt

if ($scanExitCode -ne 0) {
    throw "jdeprscan could not complete successfully."
}

$findings = @(
    $report | Where-Object { "$_" -match ' uses deprecated ' }
)

if ($findings.Count -gt 0) {
    throw "Deprecated Java SE API usages were found. Review jdeprscan-report.txt."
}
~~~

This pattern matches the `uses deprecated` substring in the observed tool output format. If you upgrade the JDK, check the new output and update the parser if the format changes. Keep the raw report intact so reviewers can inspect it.

In projects that already have many findings, you can use an approved baseline: save the current report, compare it with the new report, and block only new findings or `for removal` findings according to policy. Do not remove old findings from the baseline without a remediation plan.

## 13. Organizing reports per artifact

When scanning multiple JARs at once, the output identifies classes and deprecated APIs, but tracing a class back to the exact artifact may require additional build information.

There are three ways to organize this:

**Combined scan:** pass all targets in one command. Suitable for quickly discovering all issues across the product.

**Grouped scan:** split targets by module, plugin, or owning team. Suitable when assigning remediation work by component.

**Per-artifact scan:** run each JAR independently after the combined scan to pinpoint the exact source of a finding. This produces more reports but makes owner assignment straightforward.

Name reports by release and component, for example:

~~~text
reports/
  jdeprscan-java17-all.txt
  jdeprscan-java17-billing.txt
  jdeprscan-java17-report-plugin.txt
  jdeprscan-java21-all.txt
  jdeprscan-java17-for-removal.txt
~~~

Record alongside the report:

- JDK and `jdeprscan` version.
- Selected API release.
- Artifact list and checksums if reproducibility is needed.
- Dependency class path used during the scan.
- Build/commit date.
- Tool exit code.
- Finding count and baseline compared against.

If multiple artifacts contain the same class due to shading or duplicate packaging, a combined report can make it hard to identify the origin artifact. Maintain a target inventory and scan components individually when traceability is needed.

## 14. Scope and limitations to understand

`jdeprscan` focuses on deprecated Java SE APIs. It is useful when upgrading the JDK or checking compatibility across Java releases, but it does not replace all forms of deprecation checking in the ecosystem.

Some limitations:

- The tool reads bytecode; uncompiled source code is not analyzed.
- It targets deprecated Java SE APIs, not general checking of all `@Deprecated` annotations from third-party libraries.
- Calls constructed dynamically via reflection, class/method names loaded from configuration, or runtime paths without direct bytecode references may not be detected as normal call sites.
- Missing dependencies can lead to incomplete class resolution.
- `jdeprscan` does not replace runtime tests, binary compatibility checks, or proprietary vendor/library API checks.
- The JDK 24.0.2 CLI provides `--class-path`; do not assume a `--module-path` option exists like in some other JDK tools.
- The help lists targets as directory, JAR, class file, or class name; do not assume every archive type such as `.jmod` is supported.

For third-party libraries, combine this with compiler warnings, vendor migration guides, dependency analysis, and tools suited to that ecosystem.

## 15. Common errors when scanning multiple artifacts

### Findings only appear in the main application

**Cause:** only `app.jar` was passed, omitting plugins or internal libraries.

**Fix:** collect the artifact list from the full build output and pass all targets to check.

### Dependencies cannot be resolved

**Cause:** `--class-path` is missing JARs or directories containing dependent classes.

**Fix:** add the dependencies to the class path; still pass any dependency that needs to be checked as its own target.

### Wrong class path separator

**Cause:** using `:` on Windows or `;` on Linux/macOS.

**Fix:** use `;` on Windows and `:` on macOS/Linux. Wrap the path list in quotes.

### Paths with spaces are split into multiple arguments

**Cause:** paths are unquoted or the script builds the command as a single string.

**Fix:** use an array and argument splatting in PowerShell; use a Bash array with `"${targets[@]}"` on Unix.

### Accidentally scanning source/Javadoc JARs

**Cause:** picking up all `*.jar` files in the output directory without filtering auxiliary artifacts.

**Fix:** exclude `-sources.jar`, `-javadoc.jar`, and non-distributed artifacts from the target list if they are out of scope.

### Report has findings but CI stays green

**Cause:** only checking the `jdeprscan` exit code.

**Fix:** parse the report or compare against a baseline; do not treat exit code `0` as proof of zero deprecated usage.

### Unknown which JAR a finding belongs to

**Cause:** running a combined scan across multiple artifacts with duplicate classes across JARs.

**Fix:** split by module/team or scan artifacts individually for traceability; store the target inventory with the report.

### `--list` does not run with a JAR list

**Cause:** `--list` is a mode for listing deprecated APIs, not for scanning targets.

**Fix:** remove `--list` when scanning artifacts; use `--list` separately when you need to inspect the API list.

### Newly deprecated APIs in higher releases are not found

**Cause:** using a `--release` lower than the version being evaluated.

**Fix:** run a separate pass for each Java release the product must support or plans to upgrade to.

## 16. Recommended workflow for CI and releases

A multi-artifact scanning pipeline can follow this sequence:

1. Build all modules and plugins to be released.
2. Generate an inventory of actual JARs and class directories.
3. Exclude out-of-scope auxiliary artifacts.
4. Select the Java release to evaluate.
5. Provide dependencies via `--class-path`.
6. Run `jdeprscan` on all targets or in batches.
7. Save the raw report and toolchain information.
8. Check the exit code to detect execution errors.
9. Parse findings or compare against an approved baseline.
10. Prioritize addressing `for removal` APIs.
11. Rescan after fixes and attach the new report to the release.

Example of a combined scan command:

~~~text
jdeprscan --release 17 --class-path "libs/api.jar;libs/common.jar" app.jar billing-plugin.jar report-plugin.jar build/classes
~~~

Example of a command checking only `for removal` APIs:

~~~text
jdeprscan --release 17 --for-removal --class-path "libs/api.jar;libs/common.jar" app.jar billing-plugin.jar report-plugin.jar build/classes
~~~

Release policy should distinguish new findings from time-bound accepted findings. Each finding should have an owner, replacement API, priority, target release for remediation, and verification status.

## 17. Checklist before completing a multi-artifact scan

- [ ] Verified `jdeprscan --version` and `jdeprscan --help`.
- [ ] Listed all in-scope JARs and class directories.
- [ ] Passed each artifact to scan as a target argument.
- [ ] Distinguished targets from dependencies in `--class-path`.
- [ ] Used the correct OS-specific class path separator.
- [ ] Quoted paths with spaces or used shell arrays.
- [ ] Selected the right `--release` for the baseline being checked.
- [ ] Ran `--for-removal` separately if prioritizing APIs at risk of removal.
- [ ] Did not combine `--list` with a target scan.
- [ ] Checked both the exit code and the report contents.
- [ ] Saved the report, tool version, release, and target inventory.
- [ ] Categorized findings by owning artifact/team.
- [ ] Compared against the baseline and handled new findings per policy.
- [ ] Rescanned after replacing deprecated APIs.
- [ ] Kept the final report alongside the release artifacts.

Scanning multiple artifacts with `jdeprscan` checks bytecode across the entire product in a consistent workflow. Passing the right targets, providing dependencies for resolution, choosing the appropriate release, and analyzing the report independently of the exit code help teams catch deprecated Java SE API usage early before an upgrade or release.