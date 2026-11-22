# Planning Deprecated API Replacements in Java

When a Java API is marked **deprecated**, the development team needs to decide how and when to replace it. Replacement should not be just renaming a method: the new API may differ in semantics, time zones, null handling, exceptions, security, performance, or compatibility.

**jdeprscan** supports the inventory step by scanning class files, class directories, and JARs for references to deprecated Java APIs. The scan results serve as input for a migration plan. The tool does not automatically suggest replacement APIs, does not modify source code, and does not prove that the application is safe after migration.

A good plan clearly identifies which APIs are in use, their urgency, replacement options, behavioral differences, testing scope, owners, and completion criteria.

## 1. Why Do We Need an API Replacement Plan?

An API is marked deprecated when platform developers no longer recommend using it. The reasons may include:

- The API has an outdated design or is difficult to use safely.
- A newer API is clearer or supports more use cases.
- The old implementation introduces security risks or is hard to maintain.
- The API no longer fits the current architecture.
- The platform plans to remove the API in a future release.

Deprecated does not mean already removed. A deprecated API may continue working across multiple releases, but continuing to depend on it increases upgrade costs and compatibility risks.

Pay special attention to the annotation:

~~~java
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
}
~~~

- **since** indicates the version in which the API was marked deprecated, if declared in the metadata.
- **forRemoval = true** indicates that the API is intended to be removed in the future.
- **forRemoval = false** or omitting this attribute means the API is deprecated but has not been marked for removal yet.

`forRemoval=true` is a high-priority signal, not a guarantee that the API will definitely be removed in the very next release. Check the documentation and release notes of the target JDK.

## 2. The Role of jdeprscan in Migration

jdeprscan is a bytecode analysis tool included with the JDK. It finds references to deprecated APIs in classes, class directories, or JARs.

It can scan:

- A class file.
- A directory that is the root of a package hierarchy.
- A JAR.
- A fully qualified class name.
- Multiple inputs in a single run.

jdeprscan compares the discovered references against the set of deprecated APIs for the selected Java release. Therefore, you must determine the target Java version before scanning.

### What jdeprscan Helps Answer

- Which artifacts are calling deprecated APIs?
- Which classes in an artifact contain those references?
- Which APIs are deprecated in the target release?
- Which APIs are marked for removal?
- After migration, which references still remain?

### What jdeprscan Does Not Do

- Does not automatically find the best replacement API.
- Does not modify source code or bytecode.
- Does not evaluate whether the replacement API preserves business logic.
- Does not guarantee detection of every call created dynamically via reflection or runtime configuration.
- Does not replace checking deprecated APIs of third-party libraries.
- Does not replace compilation, unit tests, integration tests, and testing on the target JDK.

Therefore, combine jdeprscan with compiler warnings, API documentation, code reviews, and tests.

## 3. First Step: Determine the Target Release

Before scanning, determine which Java release the application will run on. The target release determines the set of deprecated APIs that jdeprscan uses for evaluation.

For example, if the application must remain compatible with Java 17:

~~~bash
jdeprscan --release 17 build/app.jar
~~~

If the target is Java 24:

~~~bash
jdeprscan --release 24 build/app.jar
~~~

Use the release that matches the runtime the team is preparing to support. Do not choose a release just because it is the JDK installed on a developer's machine if the product must run on a different version.

Also record:

- The JDK vendor and version used for building.
- The Java releases supported by the application.
- Dependency library versions.
- The operating system and deployment architecture.
- Build modules or profiles that may produce different artifacts.

When a product supports multiple Java releases, create a scan matrix for each supported release.

## 4. Inventorying Deprecated APIs with jdeprscan

### Viewing the List of Deprecated APIs

List the deprecated APIs of a release:

~~~bash
jdeprscan --list --release 24
~~~

List only APIs marked for removal:

~~~bash
jdeprscan --list --release 24 --for-removal
~~~

The `--list` option only prints the API list; it does not perform a scan. Do not pass any JAR, class, or directory when using this mode.

### Scanning a JAR

~~~bash
jdeprscan --release 24 build/app.jar
~~~

### Scanning a Class Directory

~~~bash
jdeprscan --release 24 build/classes
~~~

The passed directory is the root of the compiled package hierarchy.

### Scanning a Single Class File

~~~bash
jdeprscan --release 24 build/classes/com/example/LegacyAdapter.class
~~~

### Scanning Multiple Artifacts

~~~bash
jdeprscan --release 24 build/app.jar build/plugins build/legacy-helper.jar
~~~

Scanning all relevant artifacts helps find usages in application code and separately packaged libraries. Keep the list of scanned artifacts so you can repeat the same process in the next upgrade.

### Providing a Class Path to Resolve Dependencies

If dependent classes need to be located during analysis, pass a class path:

~~~bash
jdeprscan --release 24 --class-path "lib/*" build/app.jar
~~~

On Windows, wildcards can also be placed in quotes:

~~~powershell
jdeprscan --release 24 --class-path "lib/*" build/app.jar
~~~

Use the exact libraries required to resolve classes. If the class path is missing, results may be incomplete or the tool may emit warnings.

### Scanning Only APIs Marked for Removal

~~~bash
jdeprscan --release 24 --for-removal build/app.jar
~~~

This is a way to prioritize finding higher-risk references. However, an empty result does not mean the application has no deprecated APIs left; it only indicates that this scan found no usages belonging to the selected for-removal set.

### Other Useful Options

| Option | Purpose |
|---|---|
| --release | Select the Java SE release used as the deprecated API set |
| --for-removal | Scan or list only APIs deprecated for removal |
| --class-path | Provide the path to locate dependent classes |
| --list | List deprecated APIs without scanning artifacts |
| --verbose | Print additional information during processing |
| --version | Print the short version of the tool |
| --full-version | Print the full version string |
| --help | Display syntax and options |

Check the current toolchain:

~~~bash
jdeprscan --version
jdeprscan --help
~~~

The releases supported by the tool depend on the installed JDK version. Use `--help` from the exact toolchain in CI to confirm the syntax.

## 5. Prioritizing Findings

Not all findings have the same urgency. Categorize them before scheduling migration.

| Priority | Situation | Action |
|---|---|---|
| P0 — Critical | API deprecated for removal, already in the target release or at risk of removal upon upgrade | Identify a replacement and schedule early remediation |
| P1 — High | Deprecated API with an official replacement or related to security, concurrency, or serialization | Include in the nearest migration plan |
| P2 — Medium | Deprecated API without a removal timeline and still functioning | Record, estimate effort, and monitor |
| P3 — Needs Investigation | Finding in a third-party library, generated code, plugin, or rarely used code path | Identify the owner and handling approach before concluding |

When prioritizing, also consider:

- How frequently the API is called in business flows.
- The impact if the API is removed.
- Whether an equivalent replacement exists.
- The number of affected modules and services.
- Compatibility with the lowest Java version supported by the product.
- Effort and risk of replacement.
- Automated testing and rollback capability.

An API that only appears in tests or build tools may have a different priority than an API used in the main transaction flow. However, do not ignore tests and toolchains because they can also stop working when upgrading the JDK.

## 6. Creating an Inventory and Replacement Plan

Each finding should become a row in the migration inventory. Do not store only the API name; record both the usage location and the replacement decision.

Tracking table template:

| Field | Content to Record |
|---|---|
| Artifact | JAR, module, or directory containing the class |
| Class / member | Class and method/field referencing the API |
| Deprecated API | Full API name and signature |
| Deprecated since | Version when marked deprecated, if available |
| For removal | Yes/no according to metadata |
| Target release | Java release used for evaluation |
| Replacement | Replacement API or design |
| Semantic difference | Behavioral differences to address |
| Owner | Responsible person or team |
| Test plan | Unit, integration, compatibility, and performance tests |
| Target milestone | Planned release |
| Status | Open, Investigating, Planned, In progress, Verified, or Accepted risk |

Example inventory rows:

| Artifact | Deprecated API | Proposed Replacement | Risks to Verify |
|---|---|---|---|
| legacy-report.jar | java.util.Date.getYear() | java.time.LocalDate at a specified ZoneId | Time zones and year calculation |
| security-adapter.jar | Legacy security API | Security API recommended by JDK documentation | Permissions, providers, and authentication behavior |

The replacement in the table is an option to research, not an automatic decision. Confirm it using Javadoc, migration guides, release notes, and actual tests.

## 7. Finding Replacements and Evaluating Semantic Differences

For each deprecated API:

1. Open the Javadoc of the old API and read the deprecation note.
2. Follow the replacement link recommended by the official documentation.
3. Check release notes, migration guides, or related JEPs.
4. Determine whether the replacement exists in the lowest Java release supported by the product.
5. Compare signatures, data types, exceptions, default values, and resource lifecycles.
6. Identify what changes need to be updated in callers, configuration, persistence, or protocols.
7. Create tests proving that the old and new behaviors satisfy the same business contract.

Not every deprecated API has a one-to-one replacement. Sometimes the replacement is a group of classes, a new data model, or a different workflow. In those cases, create a migration design instead of just swapping method names.

### Differences to Check

- **Values and units:** years may be calculated from a different epoch; durations may use milliseconds or `Duration`.
- **Time zones and locales:** date/time results may change depending on `ZoneId` or `Locale`.
- **Nullability:** the replacement may reject `null` or return `Optional`.
- **Exceptions:** the new API may throw different checked or runtime exceptions.
- **Thread safety:** the new class may be mutable or immutable differently from the old class.
- **Resource lifecycle:** the new API may require explicit closing or resource management.
- **Encoding:** the default charset may differ; specify the charset explicitly.
- **Security:** permissions, providers, algorithms, or default policies may change.
- **Serialization:** the serialized form may be incompatible.
- **Performance:** allocation patterns, caching, or complexity may differ.

## 8. Migration Example: Date.getYear() to java.time

A classic example is the `Date.getYear()` method. This method has long been deprecated and returns the year minus 1900. In modern Java, you should migrate to `java.time` and specify the time zone explicitly.

### Old Approach

~~~java
@SuppressWarnings("deprecation")
static int legacyYear(Date date) {
    return date.getYear() + 1900;
}
~~~

The value of `Date.getYear()` is interpreted in the environment's default time zone. The result is a local calendar year, not directly a UTC year.

### New Approach

~~~java
static int migratedYear(Date date, ZoneId zone) {
    return date.toInstant()
            .atZone(zone)
            .getYear();
}
~~~

The new approach converts the instant to local time at the specified `ZoneId` and then retrieves the year. This forces the API designer to decide on the business time zone.

### Runnable Java 17+ Example

Create the file `src/com/example/ApiReplacementPlanDemo.java`:

~~~java
package com.example;

import java.time.Instant;
import java.time.ZoneId;
import java.util.Date;

public class ApiReplacementPlanDemo {

    static int legacyYear(Date date) {
        return date.getYear() + 1900;
    }

    static int migratedYear(Date date, ZoneId zone) {
        return date.toInstant()
                .atZone(zone)
                .getYear();
    }

    public static void main(String[] args) {
        Date value = Date.from(
                Instant.parse("2024-12-31T23:30:00Z")
        );

        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        int year = migratedYear(value, businessZone);

        System.out.println("Migrated year: " + year);
    }
}
~~~

Compile with Java 17:

~~~bash
javac --release 17 -Xlint:deprecation -d out src/com/example/ApiReplacementPlanDemo.java
~~~

The compiler emits a deprecation warning at the `Date.getYear()` call in the `legacyYear` method. This warning is kept in the example to show that the old usage still exists in the bytecode to be scanned.

Run the migrated part:

~~~bash
java -cp out com.example.ApiReplacementPlanDemo
~~~

Output:

~~~text
Migrated year: 2025
~~~

The input timestamp is `2024-12-31 23:30 UTC`. In `Asia/Ho_Chi_Minh`, that moment is `2025-01-01 06:30`, so the local year is `2025`.

### Scanning the Example's Bytecode

~~~bash
jdeprscan --release 17 out
~~~

jdeprscan will find deprecated references still stored in the class files, including the `Date.getYear()` call in the `legacyYear` method. Specific diagnostics may vary by JDK.

You can check APIs marked for removal separately:

~~~bash
jdeprscan --release 17 --for-removal out
~~~

`Date.getYear()` is deprecated but is not an example of for-removal, so it does not appear in this filtered set. That illustrates why you need to run both a full scan and a for-removal scan.

### Migration Decisions to Record

- If you need to preserve the old behavior based on the default time zone, use `ZoneId.systemDefault()` and test in the deployment environment.
- If the business logic depends on a specific time zone, pass an explicit `ZoneId` such as `Asia/Ho_Chi_Minh`.
- If the data is a calendar date that does not represent an instant, consider storing `LocalDate` instead of `Date`.
- Do not just replace `getYear()` with `LocalDate` without specifying a time zone; the result may be off by a year near year-start/year-end boundaries.

This example shows that replacing an API requires preserving the correct meaning of the data, not just eliminating compiler warnings.

## 9. Designing Migration Phases

For large projects, replacing APIs in phases reduces risk and makes progress easier to control.

### Phase 1: Baseline

- Finalize the target JDK and the releases to support.
- Scan all JARs, class directories, and module artifacts.
- Run both a full scan and a `--for-removal` scan.
- Save the results along with the JDK vendor/version and source commit.
- Create the inventory and classify P0/P1/P2/P3.

### Phase 2: Research and Design

- Look up official replacements.
- Compare old and new semantics.
- Identify affected dependencies, callers, and modules.
- Decide whether to use an adapter, facade, or direct change.
- Document cases that do not have a one-to-one replacement.
- Finalize the test plan and owner.

### Phase 3: Small-Scope Replacements

- Split migration by API or bounded context.
- Replace one group of usages with the same semantics in each change.
- Avoid modifying multiple unrelated parts simultaneously.
- If multiple modules use the old API, consider a shared adapter to control behavior.
- Update documentation and usage examples for the new API.

### Phase 4: Testing

- Unit tests for each replacement.
- Integration tests for flows calling across multiple modules.
- Regression tests comparing old and new business results.
- Boundary tests for null, time zone, locale, overflow, and legacy data.
- Compatibility tests with the lowest supported JDK.
- Performance tests if algorithms or resource management changed.
- Serialization and persistence checks if data structures changed.

### Phase 5: Re-scanning and Verification

- Rebuild all artifacts.
- Run jdeprscan against the target release.
- Run `--for-removal` separately to confirm no high-priority usages remain.
- Use `javac -Xlint:deprecation` and `-Xlint:removal` for source code.
- Review any remaining findings and classify accepted risks with justification.
- Confirm there are no runtime errors or regressions.

### Phase 6: Release and Closing Migration

- Deploy by environment or user group.
- Monitor exceptions, logs, metrics, and business behavior.
- Prepare a rollback plan if the replacement causes unintended behavioral changes.
- Update the migration inventory and operational documentation.
- Set a review date for accepted risks.
- Close the migration only when the completion criteria are met.

## 10. Using Compiler Warnings Alongside jdeprscan

jdeprscan inspects compiled bytecode. During development, the compiler can detect deprecated usages right when compiling source code.

~~~bash
javac --release 17 -Xlint:deprecation -Xlint:removal -d out src/com/example/*.java
~~~

Two warning groups are meaningful:

- **deprecation:** use of a deprecated API.
- **removal:** use of an API marked deprecated for removal.

In modern JDKs, you can enable these warnings in the build to detect new usages earlier.

Once the codebase has addressed the old baseline, you can consider turning warnings into errors in CI using the appropriate compiler options. Only enable strict mode after the team has agreed on how to handle existing warnings; otherwise, the build may fail due to a large number of unclassified old findings.

jdeprscan and javac complement each other:

| Tool | Timing | Value |
|---|---|---|
| javac -Xlint:deprecation | When compiling source | Detects new usages immediately during development |
| javac -Xlint:removal | When compiling source | Highlights APIs at risk of removal |
| jdeprscan | After classes/JARs are built | Scans built artifacts, including libraries without source |
| API documentation review | During migration design | Finds replacements and explains semantic changes |
| Automated tests | After replacement | Confirms behavior and compatibility |

## 11. Migrating Third-Party Libraries and Generated Code

Findings in a JAR may come from third-party dependencies rather than application source code.

For each finding:

1. Identify which artifact the class belongs to.
2. Check the current library version.
3. Check whether a newer version has replaced the deprecated API.
4. Read the library's release notes and compatibility notes.
5. Upgrade the dependency in a testable change.
6. If upstream has not fixed it, decide whether to keep it temporarily, replace the library, fork it, or isolate the usage.

Do not directly modify the bytecode of third-party JARs unless the release process is controlled and thoroughly tested.

Generated code also needs to be classified separately. If an old generator repeatedly produces deprecated usages, fix the template or upgrade the generator version; modifying only the generated files may cause the issue to return on the next build.

## 12. Dynamic Dependencies That Static Scanning May Miss

jdeprscan reads references in class files. Some usages do not appear explicitly as static calls:

- Reflection using class or method names loaded from configuration.
- Classes loaded by plugins or `ServiceLoader` depending on the runtime environment.
- API names constructed as strings at runtime.
- Native code calling JNI or accessing components outside the JVM.
- Code generated or loaded after scanning artifacts.

To check these cases:

- Search for class/method name strings in configuration files and resources.
- Inspect plugin registries and `ServiceLoader` providers.
- Run integration tests with actual profiles and plugins.
- Monitor logs, telemetry, and runtime errors.
- Include known dynamic dependencies in the migration inventory.

Do not conclude "no deprecated usages remain" from a single jdeprscan run if the system uses dynamic loading mechanisms.

## 13. Migration Completion Criteria

A migration is only complete when the agreed criteria are met, for example:

- All production artifacts have been scanned against the target release.
- No unapproved for-removal usages remain.
- Remaining deprecated usages have an owner, justification, and review date.
- Source compilation produces no new warnings beyond the approved baseline.
- Unit and integration tests pass.
- Semantic differences have been verified by tests.
- The application runs on the target JDK and supported platforms.
- Performance, security, and compatibility do not degrade beyond acceptable thresholds.
- Documentation and upgrade guides have been updated.
- Post-migration scan results are saved for comparison with the baseline.

Do not set the criterion simply as "jdeprscan prints no lines." There may be intentionally accepted deprecated APIs, dynamic dependencies outside the scan scope, or unscanned artifacts. Criteria should reflect the actual scope of the system.

## 14. Common Mistakes When Planning API Replacements

### Replacing APIs by Name Without Comparing Semantics

Two APIs may share a name or data type but differ in time zones, default values, exceptions, or thread safety. Create a semantic difference table and test edge cases before replacing.

### Scanning Only Application Code

Usages may reside in JARs, plugins, or separately packaged libraries. Scan every artifact deployed with the application and distinguish third-party dependency findings.

### Running Only --for-removal

This option skips deprecated APIs not marked `forRemoval`. Run a full scan first, then run a removal-prioritized scan.

### Choosing the Wrong --release

If you scan using the locally installed JDK while the product targets a different release, the report may not reflect the actual target APIs. Record the target release and use it consistently in CI.

### Treating Findings as Immediate Runtime Errors

Deprecated does not mean the API has been removed. Evaluate priority, support timelines, and compatibility instead of making hasty changes.

### Not Re-scanning After Migration

Source code may have been fixed while an old artifact is still being packaged. Rebuild, re-scan the final artifacts, and save the results.

### Not Checking Reflection and Plugins

Static scans cannot verify every dynamic call. Supplement with configuration searches and integration tests across actual profiles.

### Having No Owner or Deadline

Findings without an owner are often forgotten. Each finding needs a clear owner, target milestone, and status.

## 15. API Replacement Planning Checklist

- Finalize the target Java release and JDK vendor.
- Save the baseline of the source revision and artifact list.
- Run a full jdeprscan on JARs, class directories, and plugins.
- Also run `jdeprscan --for-removal`.
- Identify the class, artifact, and API signature for each finding.
- Prioritize based on `forRemoval`, usage frequency, and impact.
- Look up replacements in Javadoc, migration guides, and release notes.
- Document semantic differences and compatibility risks.
- Assign an owner, target milestone, and test plan.
- Replace in small batches that can be reviewed and rolled back.
- Run deprecation/removal compiler warnings.
- Test boundaries, time zones, locales, security, serialization, and performance where appropriate.
- Re-scan all artifacts after building.
- Investigate reflection, plugins, and dynamic dependencies.
- Track remaining findings with an accepted-risk record.
- Update documentation and close the migration according to agreed criteria.

## 16. Key Terms to Remember

| Term | Meaning |
|---|---|
| Deprecated API | An API no longer recommended for use |
| forRemoval | Attribute indicating the API is intended to be removed in the future |
| jdeprscan | Bytecode scanning tool for finding deprecated usages |
| Target release | The Java release the application is expected to support or deploy on |
| Migration inventory | List of findings, replacements, owners, and statuses |
| Replacement API | The API or design replacing the old usage |
| Semantic difference | Differences in meaning or behavior between old and new APIs |
| Direct dependency | A dependency referenced directly by the application |
| Transitive dependency | A dependency brought in through another library |
| Accepted risk | A finding intentionally retained, with justification and review date |
| Regression test | Testing that confirms old behavior is not broken |
| Compatibility matrix | Matrix of supported JDK versions, libraries, and platforms |

An API replacement plan must combine scan data, official documentation, semantic analysis, and testing. Use jdeprscan to know which usages exist, prioritize for-removal APIs, choose replacements according to the business contract, and only close the migration after building, testing, and re-scanning the final artifacts.

## References

- Oracle JDK 24 — [The jdeprscan Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html)
- Oracle — [Java Deprecation](https://docs.oracle.com/en/java/javase/24/core/java-deprecation.html)
- Oracle JDK 24 — [The javac Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- OpenJDK — [JDK Migration Guide](https://docs.oracle.com/en/java/javase/24/migrate/)