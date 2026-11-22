# Comparing Public APIs Between Two Releases Using `japicmp` or Revapi

When releasing a new version of a Java library, you need to know which API elements were added, changed, or removed relative to the previous release. A small source-code edit can break previously compiled applications at runtime, prevent consumer source from recompiling, or alter behavior consumers rely on. Comparing APIs between two releases catches these shifts early prior to shipping.

`japicmp` and `Revapi` are two widely used tools for analyzing API differences in Java libraries. They read the compiled artifacts of the old and new versions, identify changed API elements, and produce reports for developers to evaluate. You can integrate comparison into CI so every API change undergoes review before merging or releasing.

## 1. Defining the Public API to Protect

Before running tools, precisely define the library's "public API". The API is the contract consumers are permitted to call and depend upon across releases.

For a Java library, the API surface typically covers:

- Published packages and classes/interfaces/enums/records.
- Constructors, methods, and fields accessible by consumers.
- Parameter types, return types, generic signatures, and checked exceptions.
- Inheritance hierarchies, implemented interfaces, and modifiers like `static`, `final`, `abstract`.
- Annotations or metadata meaningful to compilers, frameworks, or consumers.
- Nested types, nested classes, annotation types, and enum constants.
- Exported modules/packages if the library uses the Java Platform Module System (JPMS).

Not every class with a `public` modifier belongs to the stability-guaranteed public API. A `public` class sitting inside an internal package not exported by a module may be inaccessible to module consumers. Conversely, an exported, well-documented package generally forms part of the API surface requiring protection.

Distinguish among:

- **Public API:** what the library intentionally publishes to consumers.
- **Protected API:** elements intended for extension classes or subclasses; may form part of the extension contract.
- **Internal implementation:** classes/packages serving internal implementation without consumer guarantees.
- **SPI (Service Provider Interface):** APIs intended for third parties providing implementations or plugins; changes here can affect more than ordinary caller APIs.

Comparison scope must stay consistent across both releases. If the old version filters to only package `com.example.publicapi` while the new version scans the whole artifact, the report can flood with out-of-scope differences.

## 2. Preparing Old and New Artifacts

Both tools compare artifacts, so prepare the exact JARs representing both releases.

- **Old artifact:** published build or approved baseline, e.g., `library-1.4.0.jar`.
- **New artifact:** JAR built from the commit or tag being prepared for release, e.g., `library-1.5.0-SNAPSHOT.jar`.
- **Metadata:** group, artifact, version, classifier, module name, and artifact origin.
- **Dependencies:** dependencies required for tools to analyze supertypes, interfaces, or referenced types.
- **Scope:** which packages/modules belong to the compared API, which access levels count, and which elements are excluded with rationale.

Prefer retrieving the old artifact from your internal release repository or verified artifact store. Avoid checking out old source from a moving branch and rebuilding with a new toolchain when the goal is comparing exactly what consumers received. The released artifact is stronger evidence of the real contract.

The new artifact must be built via the exact release workflow the organization intends to ship with. If the JAR comes from a different task missing generated classes, module descriptors, annotation processing, or bytecode enhancement compared to the actual release package, comparison findings may not match the final product.

Before running tools, verify checksums, versions, and JAR contents. Never compare two identically named files from different environments or commits by mistake. In multi-module libraries, compare each artifact with an independent API; also track inter-module links if one module's public API references types defined in another module.

## 3. How Does `japicmp` Work?

`japicmp` inspects compiled classes across two library versions and reports compatibility-relevant differences. The tool focuses on the Java binary API—the types and members consumer bytecode references.

Commonly detected changes include:

- Removed classes, interfaces, enums, or methods.
- Classes or members with narrowed accessibility.
- Changed return types or parameter types.
- Added or modified constructors, fields, or methods.
- Changed modifiers, inheritance hierarchies, or implemented interfaces.
- Certain generic signature and type-structure changes recognized by the tool.

`japicmp` classifies compatibility impact based on bytecode structure and Java compatibility rules. This lets reviewers focus on consumer-breaking changes instead of reading full source-code diffs.

### 3.1. Comparing Two JARs via CLI

Once you have the right `japicmp` CLI distribution, compare both artifacts directly. The example below uses illustrative filenames; substitute actual paths and the `japicmp` version approved by your organization.

~~~bash
java -jar japicmp-<version>-jar-with-dependencies.jar \
  --old target/library-1.4.0.jar \
  --new target/library-1.5.0.jar \
  --only-modified \
  --access-modifier public \
  --html-file target/api-compatibility.html
~~~

Meanings of key flags:

- `--old`: baseline artifact of the previous version.
- `--new`: artifact of the new version under evaluation.
- `--only-modified`: focuses on differing elements instead of listing the entire unchanged API.
- `--access-modifier`: bounds which access levels enter comparison. Pick a level matching the library contract; if protected APIs or SPIs are public commitments, include them in scope.
- `--html-file`: writes an HTML report for reviewers to read and archive as a CI artifact.

CLI filenames and packaging may vary with the selected `japicmp` release. Check `--help` of your exact tool version to confirm options before embedding commands in pipelines. XML output is available if workflows require machine-readable reports or integration with external systems.

### 3.2. Reading `japicmp` Output

Output typically categorizes elements as new, removed, modified, and unchanged, with compatibility assessments on changes. When reviewing a report:

1. Verify the exact old and new artifacts.
2. Check which packages/classes are affected.
3. Check the exact changed member: method, constructor, field, generic type, or modifier.
4. Read the compatibility classification reported by `japicmp`.
5. Cross-check against how real consumers invoke the API.
6. Identify which changes are intentional, which are accidental, and what actions are required.

For example, if `public Result find(String id)` is removed, old consumer bytecode may fail to link against the new JAR and throw `NoSuchMethodError` when that path executes. If a method changes from `public` to `protected`, consumers outside the package or subclass hierarchy may lose access. The report flags structural shifts; testing against old consumers confirms impact in real applications.

### 3.3. Integrating `japicmp` Into Build Workflows

`japicmp` can be invoked via a Maven plugin, a suitable Gradle plugin, or the CLI in CI. Regardless of mechanism, the pipeline must explicitly supply old and new artifacts, API scope, tool version, and report location.

Typical pipeline:

~~~text
Build new artifact
       |
       v
Fetch released baseline artifact
       |
       v
Run japicmp with same API scope
       |
       v
Save HTML/XML report
       |
       v
Classify changes and check policy
       |
       v
Review / fail build per agreed threshold
~~~

Never automatically fail on every difference. A new method is usually acceptable; a removed method may be a breaking change; internal changes outside the public API may not need to block release. Policies must reflect compatibility tiers, SemVer, and the project's committed contracts.

## 4. How Does Revapi Work?

`Revapi` is an extensible API difference analysis framework built around analyzers, filters, transforms, and reporters. For Java, Java API analysis is normally supplied by the `revapi-java` extension. Revapi compares the APIs of old and new artifacts, emitting findings tagged with change codes, severities, and location metadata.

Revapi's strength lies in deep configurability over API identification and finding handling:

- Analyze only packages or elements belonging to the public API.
- Exclude internal elements with explicit justification.
- Tune severity/criticality levels per project policy.
- Suppress an approved finding with narrow, specific scope.
- Transform or normalize certain findings before reporting.
- Use multiple reporters producing outputs tailored to developers or CI.

Revapi should not be viewed as a generic warning list. It generates structured findings enabling teams to decide which changes are accepted, which must be fixed, and which require justification.

### 4.1. Configuring Revapi for Java

In Maven, common integration uses `revapi-maven-plugin` alongside the `revapi-java` analysis extension. The plugin is configured with old and new artifacts and runs its check goal during an appropriate lifecycle phase—commonly `verify` or a dedicated release verification step.

A conceptual structural configuration looks like this; pick plugin and Java analyzer versions per your project's compatibility matrix:

~~~xml
<plugin>
    <groupId>org.revapi</groupId>
    <artifactId>revapi-maven-plugin</artifactId>
    <version>${revapi.maven.plugin.version}</version>
    <dependencies>
        <dependency>
            <groupId>org.revapi</groupId>
            <artifactId>revapi-java</artifactId>
            <version>${revapi.java.version}</version>
        </dependency>
    </dependencies>
    <executions>
        <execution>
            <id>check-public-api</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

This is only the skeleton integrating the plugin and Java analyzer, not a complete copy-paste configuration for every project. Configure baseline/target artifacts, API scope, analysis settings, and reporters according to the documentation of your exact `revapi-maven-plugin` version. Never copy configuration from another plugin version without checking matching parameter names and schemas.

In Gradle projects, integrate via a task or plugin supporting Revapi if your organization has selected and verified one. Without a suitable plugin, run the tool in a dedicated CI step passing old/new artifacts per the tool's supported interface. Crucially, never let the comparison invocation mutate the artifact being released.

### 4.2. Filters and API Scope

Filters tell Revapi to analyze only contracted packages or elements. For example, a library with public API and implementation packages:

~~~text
com.example.payment.api
com.example.payment.spi
com.example.payment.internal
~~~

The team may designate `api` as public API, `spi` as an extension contract checked separately, and `internal` as non-contracted. Classification must rely on product documentation, module exports, and permitted consumer usage—not package names alone.

Overly broad filters create noise causing reviewers to overlook vital findings. Overly narrow filters mask breaking changes. Every include/exclude rule needs an owner and rationale, applied identically across comparisons.

### 4.3. Controlled Ignores

Revapi supports configuring findings to ignore or handle under custom policies. This helps once a change is evaluated and approved, yet can easily hide warnings if abused.

When adding an ignore:

- Target only the exact API element and finding code to suppress.
- Record the business/technical reason and approver.
- Where possible, bound by version or expiration.
- Never ignore whole categories like "all removed methods" just to turn CI green.
- Re-review ignores when shipping the subsequent release.

A breaking change may be approved for a major release, yet must still be documented clearly in release notes and consumer migration guides. Tool ignores alter only reporting or build failure; they do not alter the actual contract.

## 5. Comparing `japicmp` and Revapi

Both tools detect API changes across Java artifacts, yet take different approaches.

| Criterion | japicmp | Revapi |
|---|---|---|
| Focus | Comparing Java binary APIs | Extensible API analysis framework |
| Usage | CLI and Maven/Gradle integration per environment | Maven plugin, analyzer extensions, and CI integration |
| Reporting | Change list and compatibility classification | Findings with codes, severities, filters, transforms, and reporters |
| Scope customization | Access flags and filtering per tool capabilities | Deeply configurable filter/extension mechanism |
| Policies | Suited for binary compatibility checks and breaking thresholds | Suited for granular API policies, ignores, and finding transforms |
| Best fit when | Needing fast, direct reports on Java binary API diffs | Governing API evolution with custom rules and rich reporting |

Choose `japicmp` when the primary objective is quickly comparing two JARs and flagging binary API changes. Choose Revapi when you need an analysis system capable of configuring filters, severities, exceptions, and reporters aligned with organizational policy. Neither tool excludes the other; a project can standardize on one primary tool and supplement with the other when needed, while avoiding duplicate unowned reports.

Neither tool decides whether a change is acceptable from a product perspective. Tools supply structural evidence; developers must cross-reference published contracts, SemVer, real consumers, and migration plans.

## 6. Understanding Compatibility Categories in Reports

### 6.1. Binary Compatibility

Binary compatibility asks whether bytecode compiled against the old version links with the new version without recompiling.

For instance, a compiled consumer calls `PaymentClient.charge(String)`. If the new version deletes this method, runtime can throw `NoSuchMethodError` when that call executes. If classes or interfaces alter structure incompatibly, other linkage errors can arise.

This is the category bytecode comparison tools like `japicmp` excel at catching. Still, findings depend on class scope, dependencies, and how the tool classifies changes.

### 6.2. Source Compatibility

Source compatibility asks whether legacy consumer source code recompiles against the new library without edits.

For example, adding an overload can render a previously clear call ambiguous upon recompilation. Adding an abstract method to an interface can keep old implementing classes from compiling. A change can preserve binary compatibility while breaking source compatibility.

API diff tools detect many structural changes likely to break source, yet do not replace compiling representative consumer code with the target compiler.

### 6.3. Behavioral Compatibility

Behavioral compatibility concerns observable outcomes and side effects. Method signatures remain unchanged while validation rules, defaults, result ordering, thrown exceptions, or side effects shift.

For instance, `findById` previously returned `Optional.empty()` on missing data whereas the new version throws an exception. API diffs may detect zero difference because the signature stayed identical. Contract tests, integration tests, and behavioral tests are essential.

### 6.4. Module and Runtime Compatibility

With JPMS, package `exports`, `requires`, `uses`, and `provides` affect API accessibility and service discovery. At runtime, JDK baselines, native libraries, agents, reflection, serialization, and security settings can trigger failures that class-level API reports cannot foresee.

Thus, API diffs form an important gate yet remain just one slice of an overall compatibility strategy.

## 7. Interpreting Common Changes

| Change | Typical risk | Evaluation action |
|---|---|---|
| Delete public class or method | Old consumers may fail compile or linkage | Identify calling consumers; keep old API or release major version |
| Narrow visibility `public` to `protected`/package-private | External consumers lose access | Check consumer footprint and public contract |
| Change parameter or return type | Alters descriptor or source signature | Check binary/source compatibility and supply overload/adapter if suitable |
| Add abstract method to interface | Existing implementations may fail compile or fail at runtime | Consider default method or new interface; test implementers |
| Add method overload | Can make old source calls ambiguous | Recompile legacy consumers against new version |
| Add new class/method | Usually additive API expansion | Check naming collisions, semantics, and dependencies |
| Change generic signature | Can impact source, reflection, and frameworks | Test generic consumers, reflection, and metadata |
| Change superclass/interface | Can alter inheritance contracts or dispatch | Check subclasses, implementers, and method resolution |
| Change annotations or module exports | Can impact frameworks, compilers, or JPMS | Check annotation processors, runtime discovery, and module consumers |

Do not assume every change in this table always causes an error. Actual impact depends on exact signatures, consumer usage patterns, the JVM/linker, the module system, and committed API scope.

## 8. Establishing Baselines and Policies in CI

For API comparison to deliver lasting value, projects need a clear baseline. Baselines are typically the latest published and accepted release artifact, not an arbitrary build from an active development branch.

A CI workflow can include:

1. Build the candidate artifact via the standard release pipeline.
2. Fetch the baseline artifact by group/artifact/version from a verified repository.
3. Run `japicmp` or Revapi with identical package scope, access levels, and configuration.
4. Archive the report as a pipeline artifact and surface a summary in build results.
5. Enforce policy: warn, require review, or fail builds per defined change categories.
6. Record approved exceptions linked to corresponding issues/release notes.

Policy must match project versioning conventions. Under Semantic Versioning, breaking changes generally require a major version; backward-compatible API additions belong in minor releases; bug fixes preserving the public contract belong in patch releases. Nonetheless, classification must follow real contracts and policy rather than relying blindly on tool-generated labels.

For pull requests, compare the branch artifact against the main branch baseline or latest release. Before shipping, re-run against the official release artifact to prevent discrepancies from build profiles or packaging steps.

In multi-module projects, each module exposing a public API needs its own baseline. If module A exposes a method accepting type `B`, changes in B can impact A's API even when A's JAR itself did not change. Track inter-artifact dependencies and run checks in an appropriate order.

## 9. Limitations and Bias Sources in API Diffs

API comparisons are meaningful only when inputs and scope are right. Common pitfalls producing missed or spurious findings include:

- Comparing wrong artifacts, wrong classifiers, or wrong versions.
- Candidate artifact missing generated source/classes, bytecode enhancement, or module descriptors present in the release build.
- Package/access-level scopes differing between runs.
- Missing dependencies preventing resolution of supertypes, interfaces, or referenced types.
- Public API accidentally filtered out or internal API swept too broadly into reports.
- Consumers using reflection, string-based lookups, service loaders, or framework conventions poorly captured by structural API diffs.
- Behavioral, performance, security, network, or data shifts undiscoverable from API signatures alone.
- Annotations, generic metadata, or module exports meaningful to frameworks yet ignored under current policy.

If the tool reports class-resolution errors or missing dependencies, never dismiss them and call the API compatible. Supply the required classpath/dependencies or explicitly document report limitations. If reports overflow with noise, check filters before adding blanket ignores.

Internal changes may still appear in reports even though they fall outside the public contract. Filter them out, keeping filters under version control and reviewed as part of API policy. Never use ignores to conceal unreviewed breaking changes.

## 10. Example Release Review Workflow

Suppose library `customer-client` is at version `2.3.0` and the team prepares to release `2.4.0`.

**Step 1 — Select baseline.** Fetch `customer-client-2.3.0.jar` from the artifact repository and verify version/checksum.

**Step 2 — Build candidate.** Build `customer-client-2.4.0-SNAPSHOT.jar` with the exact profile, compiler/toolchain, and packaging steps planned for release.

**Step 3 — Run API diff.** Run `japicmp` or Revapi comparing both JARs under the agreed public/protected API scope. Save HTML/XML or structured reports.

**Step 4 — Classify every finding.** For example, a new method is an expansion; a deleted method is a breaking candidate; internal package edits fall outside contract if filters are verified accurate.

**Step 5 — Check consumers.** Identify applications depending on `customer-client`, compile legacy consumers against the new artifact, and run integration tests on critical flows.

**Step 6 — Release decision.** If unexpected breaking changes appear in a minor release, restore the old API, introduce a deprecation window, or move changes to a major release. If breaking changes are intentional, update the migration guide and require consumer transition plans.

**Step 7 — Save evidence.** Store baseline, candidate, tool version, filter configs, reports, review decisions, and approved exceptions.

## 11. Checklist Before Accepting an API Diff

- [ ] Old artifact is an officially released or approved baseline.
- [ ] New artifact is the exact package intended for release.
- [ ] Both artifacts have verified group/artifact/version/classifier and checksums.
- [ ] `japicmp` or Revapi and extension versions are pinned in the build.
- [ ] Public/protected API scope, packages, and JPMS modules are clearly defined.
- [ ] Dependencies needed to analyze referenced types were supplied.
- [ ] Reports are archived and traceable back to the exact build.
- [ ] Every breaking candidate has been reviewed by an owner.
- [ ] Representative consumers were compiled or tested against the new artifact where appropriate.
- [ ] Behavioral, runtime, security, and data compatibility are tested separately.
- [ ] Ignores/filters have documented rationales, scopes, and approvers.
- [ ] Versioning and release notes accurately reflect the magnitude of change.

## 12. Evaluation Conclusion

`japicmp` and Revapi automate detecting Java API differences between two releases. `japicmp` excels when focusing directly on binary APIs and straightforward change categorization; Revapi excels when needing a customizable framework with filters, severities, exceptions, and reporters. Both depend on accurate baseline artifacts, release-faithful candidate artifacts, and clearly defined API scope.

Tool outputs serve as review inputs, never automatic release approvals in all cases. Teams must pair reports with published contracts, real consumers, source/binary/behavioral compatibility tests, and versioning policies. When every change carries evidence, an owner, and an explicit decision, API comparison becomes a repeatable control gate in CI that lowers the risk of accidentally breaking dependent applications.
