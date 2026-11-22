
# Distinguishing Deprecated, Scheduled-for-Removal, and Removed APIs

When upgrading the JDK or libraries, a *deprecated* notice is often the first sign that an API needs review. However, a deprecated API can still exist and continue working; an API marked *for removal* expresses stronger intent to remove; and a removed API is no longer part of the target version's contract. These three states have different implications for source code, bytecode, dependencies, and migration plans.

If they are conflated, development teams may prematurely handle APIs with no removal plan, or miss a removed API causing the application to fail to compile or link at runtime. This lesson focuses on reading deprecation states, finding evidence with Java tools, and deciding when to replace an API.

## 1. Three States to Distinguish

| State | Meaning | Is the API Still in the Current Version? | Migration Priority |
|---|---|---|---|
| Deprecated | The API still exists yet is no longer recommended for use | Yes, unless release documentation states otherwise | Plan replacement based on impact and recommendations |
| Deprecated for removal | The API is marked deprecated and platform/library authors indicate intent to remove it | May still exist in the current release | High priority; prepare replacement before upgrading further |
| Removed | The API has been removed from the target version | No longer provided as before | Mandatory to fix if the application still depends on it |

You can visualize the typical lifecycle:

~~~mermaid
flowchart LR
    A["Supported API"] --> B["Deprecated"]
    B --> C["Deprecated for removal"]
    C --> D["Removed"]
    B -. "May persist long-term" .-> B
    C -. "Timing depends on release policy" .-> C
~~~

This is a conceptual model, not a mandatory schedule for every API. An API can remain simply deprecated without ever being removed. Some libraries have their own lifecycle policies; the JDK likewise does not promise every deprecated API will be removed after a fixed number of releases.

### 1.1. Deprecated: Still Usable Yet No Longer Recommended

An API is marked deprecated when the vendor indicates that the API is no longer the recommended option. Reasons can include:

- A newer, safer, clearer, or easier-to-maintain API exists.
- The old design makes extensibility difficult.
- The API no longer fits the current architecture or security policy.
- The API exists only to preserve compatibility with legacy applications.
- The feature has been replaced by another mechanism.

In Java, the **@Deprecated** annotation marks APIs at the class, method, constructor, field, or other permitted declaration level.

Example:

~~~java
public class UserService {
    /**
     * @deprecated Use findUserById instead.
     */
    @Deprecated
    public User find(long id) {
        // Legacy implementation
        return findLegacy(id);
    }

    public User findUserById(long id) {
        return findLegacy(id);
    }
}
~~~

The find(long) method still exists. Old source code can still call it, yet the compiler may emit a warning to inform developers they should switch to findUserById(long).

Deprecated does not mean a runtime error, does not mean the API has been disabled, and does not automatically create a removal deadline. Read the API documentation to learn the reason, suggested replacement, and behavioral differences.

### 1.2. Deprecated for removal: Intent to Remove Exists

Starting in Java 9, the **@Deprecated** annotation gained two attributes:

- **since:** the version in which the API first became deprecated.
- **forRemoval:** indicates whether the API is scheduled for removal in a future release.

Example:

~~~java
/**
 * @deprecated Use the replacement API.
 */
@Deprecated(since = "2.4", forRemoval = true)
public void oldOperation() {
    // Old implementation
}
~~~

When forRemoval = true, the API can still be called in the current version, yet the vendor has expressed clear intent to remove the API in a future release. Modern compilers can emit a dedicated removal warning to distinguish it from regular deprecation.

This state should take higher priority in a migration plan because:

- A subsequent JDK or library upgrade can cause the API to disappear.
- Delaying replacement increases the number of changes that must be handled at once.
- Other dependencies may keep calling that API even after application source is fixed.
- The replacement API may differ in parameters, return types, exceptions, or behavior.

However, forRemoval = true does not specify the exact version in which the API will be removed. Do not assume “it will be removed in the very next release”. Check the vendor's migration documentation, release notes, roadmap, or official support policy.

### 1.3. Removed: API No Longer Present in the Target Version

Once an API is removed, the new version no longer provides the class, method, field, constructor, or module as before. The application must move to a replacement API, a standalone dependency, or another architectural approach.

Impact depends on how it is used:

- If source calls the removed API, the compiler may report that the class or method cannot be found.
- If the application was previously compiled and bytecode still references the removed method, runtime can throw NoSuchMethodError.
- If the class was removed, loading or linking can encounter NoClassDefFoundError.
- If a platform module was removed, the application may lack a module or package previously supplied automatically by the JDK.
- If the replacement API behaves differently, the application may still compile yet require business logic re-testing.

Do not confuse errors caused by a removed API with incompatible bytecode errors. UnsupportedClassVersionError means the JVM does not support the class-file version; NoSuchMethodError or NoClassDefFoundError typically indicates an unsatisfied binary reference at runtime.

## 2. Deprecation Annotations and Documentation in Java

### 2.1. The @Deprecated Annotation

The annotation provides metadata readable by the compiler, IDE, and analysis tools. Starting in Java 9, you can specify the deprecation version and intent to remove:

~~~java
@Deprecated(since = "9")
public void legacyMethod() {
}

@Deprecated(since = "17", forRemoval = true)
public void oldSecurityHook() {
}
~~~

Meaning:

| Attribute | Description |
|---|---|
| No attributes specified | API is deprecated; since defaults to empty string and forRemoval defaults to false |
| since = "9" | Records that the API has been deprecated since version 9 |
| forRemoval = false | Does not declare intent to remove |
| forRemoval = true | Marks the API as scheduled for removal in the future |

since is information supplied by the API author. It is not automatically inferred by the compiler from Git history or release dates. For internal libraries, the team must record the library's own exact release version.

### 2.2. The @deprecated Javadoc Tag

In Javadoc, the @deprecated tag explains to API users why the API is deprecated and what to use instead.

Example:

~~~java
/**
 * Returns the legacy account representation.
 *
 * @deprecated Since 2.4. Use {@link #findAccountById(long)}.
 */
@Deprecated(since = "2.4")
public Account findAccount(long id) {
    return findLegacyAccount(id);
}
~~~

Distinguish:

- The @Deprecated annotation is language/bytecode-level metadata.
- The @deprecated Javadoc tag is documentation content for API readers.
- The annotation may exist while the Javadoc provides very little or incomplete explanation.
- Javadoc may contain a deprecated tag in old documentation while the active bytecode lacks the corresponding annotation, for example because documentation and source fell out of sync.

A good API should have both the annotation and an explanation in Javadoc. Documentation should state the replacement, reason for migrating, and key differences when replacing.

### 2.3. Deprecation in Internal Libraries

For APIs developed by the organization itself, deprecation is a communication contract with consumers. Clearly define:

- Which library version begins marking it deprecated.
- Which version introduced the replacement.
- How long the old API remains operational.
- Whether the API is scheduled for removal.
- Which version may contain the breaking change.
- What consumers must change to migrate.

Example:

~~~java
/**
 * @deprecated Since 3.2. Use {@link #send(Message, DeliveryOptions)}.
 *             This method is planned for removal in a future major release.
 */
@Deprecated(since = "3.2", forRemoval = true)
public void send(Message message) {
    send(message, DeliveryOptions.defaults());
}
~~~

Do not mark forRemoval = true merely to nudge users into migrating if the team does not actually intend to remove it. Inaccurate metadata reduces warning trustworthiness and makes consumer planning difficult.

## 3. How to Read Compiler Warnings

### 3.1. Regular Deprecation Warnings

When source calls a deprecated API, the compiler can emit warnings. Example:

~~~java
public class LegacyClient {
    public void execute() {
        UserService service = new UserService();
        service.find(10L); // Deprecated method
    }
}
~~~

Detailed warnings can be enabled:

~~~bash
javac -Xlint:deprecation -d out src/com/example/*.java
~~~

Depending on compiler version and build setup, messages may point out the deprecated class or method being used. Read the entire warning to identify the call site and API kind.

### 3.2. Removal Warnings

For APIs marked forRemoval = true, modern compilers can emit removal warnings. You can explicitly request displaying them:

~~~bash
javac -Xlint:removal -d out src/com/example/*.java
~~~

To enable both warning groups:

~~~bash
javac -Xlint:deprecation -Xlint:removal -d out src/com/example/*.java
~~~

In build systems, check the actual compiler configuration applied to each module. One module may use a different JDK or have different lint options from another.

### 3.3. Turning Warnings into Controlled Errors

The compiler supports -Werror to turn warnings into compilation errors:

~~~bash
javac -Xlint:deprecation -Xlint:removal -Werror -d out src/com/example/*.java
~~~

Do not enable this immediately on a large codebase with many existing warnings before classifying the baseline. A safer rollout:

1. Collect current warnings per module.
2. Record warnings that already existed prior to migration.
3. Fix newly deprecated or removal APIs.
4. Add CI rules to prevent new warnings from appearing.
5. Gradually reduce the old baseline in batches.

The goal is making warnings actionable. If hundreds of old warnings are ignored, a new warning about an API about to be removed is easily overlooked.

## 4. Tools for Finding Deprecated APIs in the JDK

### 4.1. jdeprscan

jdeprscan is a tool bundled with the JDK for analyzing class files and JARs to find usage of deprecated Java SE APIs. The tool is useful when source code is unavailable, or when inspecting compiled artifacts.

Example:

~~~bash
jdeprscan --release 17 app.jar
~~~

The command above asks the tool to check deprecated APIs against Java 17. Select the release matching the target version to inspect and check the options supported by the JDK running the tool.

To focus on APIs marked scheduled for removal:

~~~bash
jdeprscan --release 17 --for-removal app.jar
~~~

You can supply a classpath for required dependencies in some cases:

~~~bash
jdeprscan --release 17 --class-path "lib/*" app.jar
~~~

Paths and classpath syntax must be adjusted for the OS, artifact layout, and active shell.

Points to remember:

- jdeprscan focuses on deprecated Java SE APIs known to the dataset of the selected JDK/release.
- --for-removal filters APIs with deprecated-for-removal status.
- The tool analyzes static bytecode; it does not observe all runtime execution paths.
- Name-based reflection, dynamically generated methods, native code, or library-specific APIs are not necessarily detected.
- Running the tool against one release does not mean it analyzed all dependencies or every dynamically loaded class of the application.
- The jdeprscan version may limit which releases it understands; check jdeprscan --help and the documentation of the specific JDK.

### 4.2. jdeps Does Not Replace jdeprscan

Both tools are often used together yet answer different questions:

| Tool | Primary Goal | Example |
|---|---|---|
| jdeprscan | Find usage of deprecated Java SE APIs | Deprecated or deprecated-for-removal APIs |
| jdeps | Analyze class/package/module dependencies | Dependencies on JDK internal APIs, packages, or modules |

Example checking internal APIs:

~~~bash
jdeps --jdk-internals --recursive app.jar
~~~

A JDK internal API is not necessarily marked deprecated. Conversely, a public Java SE API may be deprecated without being an internal API. Thus, outputs from the two tools complement each other.

### 4.3. Finding Deprecated APIs in Third-Party Libraries

jdeprscan primarily helps find deprecated APIs of the Java platform. It does not replace reading deprecation metadata of libraries such as Spring, Hibernate, Jackson, or an organization's internal libraries.

For external dependencies:

- Check Javadoc and API references for the exact version.
- Read release notes and migration guides.
- Check @Deprecated annotations in source or bytecode.
- Use IDEs or static analysis tools capable of reading dependency metadata.
- Look for warnings when compiling modules calling the API.
- Inspect the dependency graph to see which version is actually resolved.

If a pre-compiled dependency calls a deprecated method, the application's compiler does not necessarily emit warnings in every case. Scan bytecode, inspect dependency documentation, or use corresponding analysis tools.

## 5. Identifying Removed APIs Across Versions

### 5.1. Comparing APIs by Release

When migrating from an old JDK to a new JDK, determine which APIs/modules were removed across that version span. Evidence sources to use:

- Java SE API Specifications of the source and target versions.
- JDK Release Notes.
- JEPs describing deprecation or removal.
- JDK vendor Migration Guides.
- Framework and dependency release notes.
- Compile/test reports on the target runtime.

Do not only search for the deprecated keyword in current source. A removed API will no longer have an annotation in the target class library to search for. Compare history and documentation across both releases.

### 5.2. Example: Java EE and CORBA Modules Removed from JDK 11

Before Java 11, several Java EE and CORBA modules were distributed with the JDK, such as:

- java.xml.bind (JAXB).
- java.xml.ws (JAX-WS).
- java.activation.
- java.corba.
- java.se.ee aggregate module.

These modules were removed in JDK 11 per the change described in JEP 320. Legacy applications may have used classes like javax.xml.bind.JAXBContext without declaring a separate dependency because the JDK provided them.

After moving to JDK 11, the application may encounter compile errors like “package ... does not exist” or runtime missing-class errors if it still expects those modules to be built in.

The typical approach is declaring an appropriate dependency from the corresponding ecosystem, choosing a version supporting the target JDK, and verifying the actual namespace/API. Do not just add any random JAR: verify version, packages, transitive dependencies, and runtime behavior.

### 5.3. Example: Nashorn JavaScript Engine

Nashorn was deprecated in Java 11 and later removed from JDK 15 under JEP 372. Applications using ScriptEngineManager to look up the JavaScript engine may no longer receive Nashorn from the JDK as before.

Legacy code example:

~~~java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

public class ScriptRunner {
    public Object evaluate(String source) throws Exception {
        ScriptEngine engine =
                new ScriptEngineManager().getEngineByName("nashorn");
        return engine.eval(source);
    }
}
~~~

If the engine is absent, getEngineByName can return null. The application must choose a compatible replacement engine, such as a standalone JavaScript implementation distributed as a dependency, and test differences in syntax, Java integration APIs, security, and performance.

This example shows that removal does not always manifest as a compile error. The engine-lookup API may still exist while the specific implementation is no longer supplied by the JDK.

## 6. Impact on Source Compatibility and Binary Compatibility

### 6.1. Source Compatibility

Source compatibility answers the question: can old source code compile with the target version's APIs and compiler?

If a method or class has been removed, the compiler typically reports a missing symbol error:

~~~text
error: cannot find symbol
~~~

To fix this, replace the call with an alternative API or add the corresponding dependency if the API was separated from the JDK yet remains independently provided.

### 6.2. Binary Compatibility

Binary compatibility answers the question: can previously compiled bytecode link against the new class library/dependency?

For example, an application previously compiled against method:

~~~java
client.oldSend(message);
~~~

If the new runtime library no longer has that method, the JVM may throw:

~~~text
java.lang.NoSuchMethodError
~~~

If the class was removed, the following may appear:

~~~text
java.lang.NoClassDefFoundError
~~~

If a module or package is no longer supplied, errors can appear at compile, module resolution, or class-loading time depending on packaging.

Therefore, rebuilding source with the new JDK is necessary yet insufficient. Check all runtime dependencies and the actual artifact. An old JAR may contain bytecode referencing a removed API even if the main application's source no longer calls it.

### 6.3. Behavioral Compatibility

Even when a replacement API has a similar signature, behavior can differ:

- Default values change.
- Processing order or parsing rules change.
- Exceptions are thrown in cases that previously did not fail.
- Encoding, timezone, or locale differs.
- The new API requires additional configuration or resources.
- The new engine/provider has a different feature set or security limits.

Therefore, replacing an API must be accompanied by regression tests on real business cases.

## 7. Classifying Findings to Plan Migration

Each result should be classified separately to determine urgency:

| Finding Group | Indicator | Action |
|---|---|---|
| Deprecated, not for removal | @Deprecated, forRemoval=false or undeclared | Record replacement, assess cost, and schedule |
| Deprecated for removal | forRemoval=true, [removal] warning | Prioritize replacing before upgrading to a release likely to remove it |
| Removed in target JDK | API/module no longer in target release | Fix before building or deploying on the new runtime |
| Removed from dependency | Class/method missing in resolved library version | Upgrade consumer, temporarily keep compatible version, or swap library |
| Deprecated in external dependency | Library Javadoc/annotations warn | Follow publisher's migration guide and lifecycle policy |
| Implementation/provider missing | Lookup API exists yet implementation vanished | Add standalone provider or choose alternative solution |

A finding should include:

- Full API name and component type.
- Version where deprecation began, if available.
- forRemoval value and confirmation source.
- Last version containing the API or version where removed.
- Dependency or module containing the API.
- Call sites in source/bytecode.
- Recommended replacement.
- Extent of signature and behavioral changes.
- Tests to add.
- Responsible person or team.

## 8. Deprecation/Removal Verification Workflow

### Step 1: Identify Source and Target Versions

Specify the current JDK, target JDK, framework versions, and dependencies. The same API may be deprecated in one release, marked for removal in another, and removed in a subsequent release.

### Step 2: Collect Compile Warnings

Enable deprecation/removal lint across modules. Save warnings by file, class, and method. Separate warnings in application source from warnings originating in generated source or test modules.

### Step 3: Scan Artifacts with jdeprscan

Run jdeprscan with the target release and --for-removal to build a list of Java SE APIs needing attention. If there are multiple JARs or modules, scan each needed artifact and provide an appropriate classpath.

### Step 4: Scan Internal APIs with jdeps

Run jdeps --jdk-internals to find dependencies on internal APIs. This is a distinct risk group from deprecation, so keep a separate report or separate classification in the migration backlog.

### Step 5: Check Dependencies and Release Notes

Cross-check warnings against resolved dependency versions. Read migration guides to determine replacements, target-JDK-supported versions, and config changes.

### Step 6: Check Removed APIs

Compare API Specifications, release notes, and JEPs between source and target. Find packages/modules no longer provided and removed implementations/providers.

### Step 7: Replace and Test

Update call sites, upgrade dependencies, configure providers, and rebuild. Run unit tests, integration tests, and tests on the exact target runtime. Specifically test branches using reflection, service loaders, scripting engines, or APIs called only during specific features.

### Step 8: Prevent New Warnings

After resolving the baseline, configure CI to detect new deprecation/removal warnings. You can apply -Werror to modules with warnings under control, or use equivalent lint/static analysis rules in the build tool.

## 9. Example: Designing an API Lifecycle for an Internal Library

Suppose the account-client library has an old method:

~~~java
public Account get(long id) {
    return repository.find(id);
}
~~~

The team wants to move to a new API with a clearer name and query options support:

~~~java
public Account findById(long id, QueryOptions options) {
    return repository.find(id, options);
}
~~~

This can be rolled out across releases:

**Release 2.4:** add the new API, keep the old API, and mark it deprecated:

~~~java
/**
 * @deprecated Since 2.4. Use {@link #findById(long, QueryOptions)}.
 */
@Deprecated(since = "2.4")
public Account get(long id) {
    return findById(id, QueryOptions.defaults());
}
~~~

**Release 3.0:** if compatibility policy allows breaking changes, mark the old API for removal in an earlier release or clearly announce the removal timeline. If the API was marked for removal since 2.4, consumers can migrate proactively.

**Release 4.0 or announced release:** remove the old method per the versioning plan and migration guide.

This is only an example of an internal library policy, not a mandatory rule for every project. The team must publish support durations, semantic versioning rules, and how to handle consumers unable to upgrade yet.

## 10. Limitations to Remember When Reading Results

- A deprecated API can remain supported for many years; do not invent deadlines if the vendor has not announced one.
- forRemoval=true is a signal of intent, not an exact removal date.
- An API that is no longer deprecated may have been removed from the target release; searching for warnings in current source will not detect it.
- jdeprscan does not scan every deprecated API of all third-party libraries.
- jdeps finds static dependencies, and does not prove all runtime execution paths.
- Reflection and dynamic class names may not appear in standard compilation or bytecode analysis results.
- A removed implementation/provider can leave lookup APIs compiling while failing to find a provider at runtime.
- A successful build does not prove behavioral compatibility.
- A warning in tests or build tools does not necessarily affect production artifacts, yet still needs clear classification.
- Do not delete old APIs from an internal library before evaluating consumers and the published compatibility policy.

## 11. Checklist Before Concluding

### Status Identification

- [ ] Distinguished deprecated, deprecated for removal, and removed.
- [ ] Checked the @Deprecated annotation, since, and forRemoval attributes.
- [ ] Read @deprecated Javadoc and recommended replacements.
- [ ] Verified API status against the exact target JDK/dependency version.
- [ ] Determined whether the API belongs to Java SE, JDK internals, or a third-party library.

### Tool Analysis

- [ ] Enabled -Xlint:deprecation and -Xlint:removal when appropriate.
- [ ] Scanned artifacts with jdeprscan.
- [ ] Ran jdeprscan --for-removal to focus on APIs scheduled for removal.
- [ ] Used jdeps --jdk-internals for internal APIs.
- [ ] Checked the dependency graph and JARs actually present at runtime.

### Migration Evaluation

- [ ] Identified APIs/modules/providers removed between the two releases.
- [ ] Identified replacements and behavioral differences.
- [ ] Checked binary compatibility of dependencies.
- [ ] Updated source, configuration, and dependencies appropriately.
- [ ] Ran tests on the exact target JDK and deployment environment.
- [ ] Established CI rules to prevent unaddressed new warnings.

## Conclusion

Deprecated indicates an API is no longer recommended; deprecated for removal indicates the vendor intends to remove the API; removed means the target version no longer provides that API. Each state requires different handling and priority.

Combine compiler lint, jdeprscan, jdeps, dependency graphs, JDK release notes, and migration guides to compile an accurate inventory. After replacing APIs, rebuild the entire application and test on the target runtime to confirm source compatibility, binary compatibility, and behavior alike. For internal library APIs, clearly publish replacements and lifecycles so consumers have sufficient time to migrate.
